"""Adjustable parameters for the 3-stage tagging pipeline.

Modify values here, then run pipeline.py or compare.py.
All slice sizes are in characters.
"""

import os

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SliceConfig:
    """How to slice each book for BGE query vs DeepSeek context."""
    # Stage 1: BGE retrieval query — short is better for semantic focus
    query_head_chars: int = 2000
    query_tail_chars: int = 0  # BGE query: head only, no tail

    # Stage 3: DeepSeek confirmation context — longer for accuracy
    head_chars: int = 3000
    tail_chars: int = 1000


@dataclass
class PipelineConfig:
    # ============ 必需输入（更换本体时替换 tagger/data/ 下的文件） ============
    # retrieval_index.json: 本体条目列表，每条含 canonical_id / original_name / embedding_text / semantic_summary / retrieval_aliases
    ontology_path: str = "tagger/data/retrieval_index.json"
    # retrieval_faiss.index: 由 build_faiss_index.py 从 ontology 的 embedding_text 字段预计算
    faiss_index: str = "tagger/data/retrieval_faiss.index"
    # retrieval_ids.json: canonical_id 列表，与 FAISS 索引行号一一对应
    faiss_ids: str = "tagger/data/retrieval_ids.json"
    # BGE-M3 模型路径
    bge_model: str = "D:/model/bge-m3/BAAI/bge-m3"
    # Same finding as the reranker: the checkpoint loads as fp32 by default and
    # chunk-level recall is now the heaviest local step, so cast to fp16 on CUDA.
    bge_fp16: bool = True

    # Stage 1: BGE recall
    # A book is split into chunks and each chunk queries the index separately;
    # candidates are the union, tagged with which chunk(s) recalled them. A
    # single head-only query was measured to miss ~40% of the union.
    stage1_top_k: int = 500          # per-chunk top-k (not per book)
    chunk_chars: int = 2000
    chunk_batch_size: int = 8        # chunks encoded per forward pass (8 measured
                                     # faster than 16 and uses less VRAM)
    max_candidates: int = 900        # cap on the union handed to stage 2

    # Stage 2: rerank (cross-encoder if available, else char-level TF-IDF)
    # 120 is what all the measured results are based on: at 40 the judge gets
    # roughly half as many tags per book (11 vs 22).
    stage2_top_k: int = 120
    use_reranker: bool = True
    # BAAI/bge-reranker-v2-m3 (0.6B, 2.27GB, drop-in CrossEncoder)
    # or tomaarsen/Qwen3-Reranker-0.6B-seq-cls (0.6B, 2.38GB, also a plain CrossEncoder)
    reranker_model: str = "D:/model/bge-reranker-v2-m3"
    # Measured on a 3060 Ti for 500 candidates: fp32/1024 = 39.6s, fp16/512 = 7.7s
    # per book. The checkpoint ships as F32, so fp16 is a 3.4x win for free.
    reranker_fp16: bool = True
    reranker_max_length: int = 512
    reranker_batch_size: int = 32
    # Keep the query inside reranker_max_length so nothing is silently truncated
    # (500 Chinese chars + the tag passage measures 494 tokens at max_length=512;
    #  600 chars already pins the ceiling and eats the definition tail).
    rerank_query_chars: int = 500

    # Stage 3: LLM confirmation
    confidence_threshold: float = 0.75
    # How the judge is asked.
    #   "forced"  — every candidate gets its own y/n verdict in a fixed schema.
    #               Measured much more reliable: same-input Jaccard 95% vs 84%,
    #               tag counts 5-42 vs 4-117, and it cannot "accept everything".
    #   "select"  — the old "pick from this list" framing, kept for comparison.
    # Reasoning. The API judges ran with thinking FORCED OFF (to save tokens)
    # while Gemini ran with thinking on -- the most likely source of the
    # residual recall gap. Set True to omit the disable flag.
    thinking_enabled: bool = False
    # Only send the first N candidates to the judge (0 = all). Cost scales with
    # this, since output is one entry per candidate and the context repeats per batch.
    judged_candidates: int = 0
    # Concurrent judge calls within one process. The gateway allows ~20 requests
    # per 28s per ACCOUNT, and separate keys belong to separate accounts, so one
    # key per shard + a few workers per shard multiplies throughput; without the
    # in-shard concurrency the extra accounts buy nothing (latency-bound, not
    # rate-bound).
    stage3_workers: int = 4
    judge_mode: str = "forced"
    forced_batch_size: int = 30      # candidates per forced-mode call
    # Output budget. The caller scales this with the candidate count
    # (500 + 160/candidate, capped at 16000); too small a value silently
    # truncates the reply and used to look like "this book has no tags".
    max_output_tokens: int = 4000
    # 1 = single pass (recommended). >1 = self-consistency sampling at
    # vote_temperature, keeping tags present in >= ceil(N/2) passes (majority).
    # At temperature 0 the N passes are identical, so voting does nothing —
    # never set vote_passes>1 together with vote_temperature=0.
    vote_passes: int = 1
    vote_temperature: float = 0.7
    # machine-verify that the quoted evidence really occurs in the source text
    verify_evidence: bool = True
    evidence_against_full_text: bool = True
    min_evidence_chars: int = 6
    # pairwise resolution for tags whose `distinction` points at another emitted tag
    disambiguate_confusions: bool = True
    # 0 = feed the whole slice_text (head+tail per SliceConfig); >0 caps it
    prompt_context_chars: int = 0
    # Stage 3 sees the chunks that actually recalled the candidates (plus the
    # opening), not just the book head — otherwise it cannot quote evidence for
    # a tag introduced at chunk 47.
    context_budget_chars: int = 12000      # floor
    # ...but scale with book length, or a 300k-char book gets the same 12k as a
    # 20k one and 41% of its candidates are judged without their own chunk shown
    context_ratio: float = 0.08
    context_budget_max: int = 100000

    # Slice settings
    slice: SliceConfig = field(default_factory=SliceConfig)

    # API settings
    opencode_model: str = "deepseek-flash"
    api_url: str = "https://tokenrhythm.studio/v1/chat/completions"
    api_key: str = os.environ.get("OPENCODE_API_KEY", "")
    # Priority-ordered pool. Rotation only kicks in when a key is rejected for
    # auth/balance reasons, so the first key is spent down before the next is
    # touched. Separate keys are separate accounts -> independent rate limits.
    api_keys: list = field(default_factory=lambda: [
        k.strip() for k in os.environ.get("OPENCODE_API_KEYS", "").split(",") if k.strip()])
    opencode_timeout: int = 120
    # Extra fields merged into the /chat/completions payload, for local servers:
    #   {"response_format": {...}}                          LM Studio / llama.cpp JSON schema
    #   {"chat_template_kwargs": {"enable_thinking": False}} Qwen3 hybrid thinking models
    extra_payload: dict = field(default_factory=dict)

    # Output directory
    work_dir: str = "work"


# Pre-built config sets for comparison
CONFIGS = {
    "default": PipelineConfig(),
    "big_slice": PipelineConfig(
        slice=SliceConfig(
            query_head_chars=2000,
            head_chars=6000,
            tail_chars=2000,
        )
    ),
    "small_slice": PipelineConfig(
        slice=SliceConfig(
            query_head_chars=500,
            head_chars=2000,
            tail_chars=500,
        )
    ),
    "mid_slice": PipelineConfig(
        slice=SliceConfig(
            query_head_chars=1500,
            head_chars=4500,
            tail_chars=1500,
        )
    ),
    "deep_k": PipelineConfig(
        stage1_top_k=500,
        stage2_top_k=300,
    ),
    # Local uncensored judge: load an abliterated GGUF in LM Studio, start its
    # OpenAI-compatible server (default :1234), then
    #   python -m tagger.pipeline --config local --book-dir <dir>
    # LM Studio ignores the model string and uses whatever is loaded.
    "local": PipelineConfig(
        opencode_model="local-model",
        api_url="http://127.0.0.1:1234/v1/chat/completions",
        api_key="lm-studio",
        opencode_timeout=600,
    ),
    # Coverage experiment: identical to default except that the reranker hands
    # the judge 120 candidates instead of 40, to find out whether the 40-slot
    # budget is capping how many tags a book can receive.
    "wide": PipelineConfig(
        stage2_top_k=120,
    ),
    # Second judge for the agreement study: identical candidates and identical
    # prompt, different model. deepseek-v4-pro-0813 had 100% evidence validity
    # in probing. Where the two agree is the high-confidence set; where they
    # disagree is the human review queue.
    "verify": PipelineConfig(
        stage2_top_k=120,
        opencode_model="deepseek-v4-pro-0813",
    ),
    # Same as verify but second judge only, used to re-measure agreement now that
    # the judge is asked per-candidate instead of being handed a menu.
    "forced_pro": PipelineConfig(
        stage2_top_k=120,
        opencode_model="deepseek-v4-pro-0813",
        judge_mode="forced",
    ),
    # Experiment: can an API judge reach Gemini's level?
    "think_flash": PipelineConfig(stage2_top_k=120, thinking_enabled=True),
    "v4flash": PipelineConfig(stage2_top_k=120, opencode_model="deepseek-v4-flash-0731"),
    "think_v4flash": PipelineConfig(stage2_top_k=120, opencode_model="deepseek-v4-flash-0731",
                                    thinking_enabled=True),
    "think_pro": PipelineConfig(stage2_top_k=120, opencode_model="deepseek-v4-pro-0813",
                                thinking_enabled=True),
    # Cross-family judges: their errors should be decorrelated from deepseek's,
    # which is the only remaining way an API-only run could reach the tags
    # deepseek jointly misses.
    "seed": PipelineConfig(stage2_top_k=120, opencode_model="seed-2.1-pro"),
    # Budget experiments: cheap ways to create diversity instead of paying for pro.
    "ctx8k": PipelineConfig(stage2_top_k=120, context_budget_chars=8000),
    "c60": PipelineConfig(stage2_top_k=120, judged_candidates=60),
    # Is 120 candidates the right budget? The tag count was still climbing at
    # 120 in every measurement, so this tests whether more candidates add recall.
    "c240": PipelineConfig(stage2_top_k=240),
    # One call per book: all 120 candidates judged at once, so the context is sent
    # once instead of 4x. 4x cheaper on input; unvalidated, so compare first.
    "singlecall": PipelineConfig(stage2_top_k=120, forced_batch_size=120),
    "pro60_1call": PipelineConfig(stage2_top_k=120, opencode_model="deepseek-v4-pro-0813",
                                  judged_candidates=60, forced_batch_size=60),
    "glm_think": PipelineConfig(stage2_top_k=120, opencode_model="glm-5.3",
                                thinking_enabled=True),
}
