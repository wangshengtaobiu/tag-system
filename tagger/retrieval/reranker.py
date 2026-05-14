"""
Reranker — Qwen 8B local reranking for candidate tags.
Model: Qwen 2.5 8B Instruct (4-bit quantized).
VRAM: ~5.5 GB (4-bit). Fits RTX 3060 Ti 8GB alongside BGE.
"""
from __future__ import annotations

import time
from typing import Optional

from retrieval import RetrievalResult


class Reranker:
    """Qwen 8B local reranker for candidate tag selection."""

    def __init__(self, model_name: str = "qwen-2.5-8b-instruct",
                 device: str = "cuda", quantization: str = "4bit"):
        self.model_name = model_name
        self.device = device
        self.quantization = quantization
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self):
        """Lazy-load the Qwen model with quantization."""
        if self._loaded:
            return
        print(f"[Reranker] Loading {self.model_name} ({self.quantization}) on {self.device}...")
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            if self.quantization == "4bit":
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype="float16",
                    bnb_4bit_use_double_quant=True,
                )
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=True,
                )
            else:
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    device_map="auto",
                    torch_dtype="float16",
                    trust_remote_code=True,
                )

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
            self._loaded = True
            print(f"[Reranker] Loaded successfully.")
        except ImportError as e:
            print(f"[Reranker] transformers not available: {e}. Using stub.")
            self.model = None
        except Exception as e:
            print(f"[Reranker] Failed to load model: {e}. Using stub.")
            self.model = None

    def unload(self):
        """Free VRAM."""
        if self.model:
            del self.model
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def rerank(self, query_text: str, candidates: list[RetrievalResult],
               top_k: int = 10) -> list[RetrievalResult]:
        """Rerank candidates using Qwen scoring."""
        if not candidates:
            return []

        if self.model is None:
            # Stub reranking: use embedding scores directly
            return sorted(candidates, key=lambda r: r.score, reverse=True)[:top_k]

        t0 = time.time()
        reranked = []

        for candidate in candidates:
            score = self._score_candidate(query_text, candidate)
            candidate.score = score
            reranked.append(candidate)

        reranked.sort(key=lambda r: r.score, reverse=True)
        print(f"[Reranker] {len(candidates)} candidates → {top_k} final in {time.time() - t0:.1f}s")
        return reranked[:top_k]

    def _score_candidate(self, query_text: str, candidate: RetrievalResult) -> float:
        """Score a single candidate using Qwen."""
        prompt = self._build_rerank_prompt(query_text, candidate)
        response = self._generate(prompt, max_tokens=16)
        return self._parse_score(response)

    def _build_rerank_prompt(self, query_text: str, candidate: RetrievalResult) -> str:
        """Build a compact reranking prompt."""
        # Get full entry info from the candidate
        entry_info = ""
        if hasattr(candidate, 'definition'):
            entry_info = candidate.definition[:200]

        return f"""Rate how well this tag matches the text on a scale of 0.0 to 1.0.

Text: {query_text[:300]}

Tag: {candidate.original_name}
Namespace: {candidate.namespace}
Type: {candidate.semantic_type}
Info: {entry_info}

Score (0.0-1.0): """

    def _generate(self, prompt: str, max_tokens: int = 16) -> str:
        """Generate text with Qwen."""
        if self.model is None:
            return "0.85"

        try:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=0,
                do_sample=False,
            )
            return self.tokenizer.decode(outputs[0], skip_special_tokens=True)[len(prompt):]
        except Exception as e:
            print(f"[Reranker] Generation error: {e}")
            return "0.5"

    @staticmethod
    def _parse_score(text: str) -> float:
        """Parse a float score from model output."""
        try:
            # Find first float-like number
            import re
            match = re.search(r"(\d+\.?\d*)", text)
            if match:
                score = float(match.group(1))
                return min(max(score, 0.0), 1.0)
        except (ValueError, AttributeError):
            pass
        return 0.5
