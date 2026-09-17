# tagger — 三阶段自动打标管线

给任意小说自动打标签，输出每本书的标签列表，每条标签都附**逐字原文证据**。

当前实现（与本文档同步的版本）：本地 chunk 召回 → 本地交叉编码器重排 → LLM 逐条判定。
所有默认值见 `config.py`，下面每个设计决定都附实测依据。

## 架构

```
书籍.txt
  │
  ├── Stage 1  本地 chunk 召回（bge-m3 + FAISS，全在 GPU）
  │     全书切成 2000 字一块，每块单独查索引，取并集
  │     书名作为一次独立查询（只被书名命中的候选记 best_chunk = -1）
  │     → 每块 top-500，并集上限 900，按 best_score 排序
  │     → .stage1_cache.jsonl
  │
  ├── Stage 2  本地重排（bge-reranker-v2-m3 交叉编码器，fp16）
  │     每个候选用它"命中最好的那一块"作为查询打分
  │     max_length=512；查询截到 500 字以免被静默截断
  │     → 并集 → top-120
  │     → .stage2_cache.jsonl
  │
  └── Stage 3  LLM 逐条判定（deepseek-flash）
        120 个候选分 4 批（每批 30），对每个候选独立给 y/n
        证据必须逐字出现在正文里，否则丢弃
        → final.jsonl
```

### 三个关键设计决定（都有实测依据）

**书名不能拼进正文块。** 早期把书名拼到第 0 块开头，本意是"书名是强信号"。
但书名会匹配几百个标签定义，第 0 块向量被污染、成为 15% 候选的最佳命中块
（均匀应为 3–4%），而票数最高的块正是展示给判定模型的块——于是模型只读到了书的开头。
实测：受影响的书 100% 的证据都落在全书前 2%。现在书名走独立查询。

**判定要逐条问，不能"从菜单里挑"。** 早期是"从候选列表里选出匹配的"，实测极不稳定：
同一本书只改候选菜单长度（20/40/80/120），输出从 5 个标签跳到 76 个，两本出现"100% 全收"；
同输入跑两次最低只有 26% 一致，标签数跨度 4–117。改成逐条 y/n 后：同输入两次一致度 95%，
标签数跨度 5–42，且结构上不可能"全收"。

**本地模型默认 fp32，要显式转 fp16。** bge-m3 和重排器都是。实测 3.6 倍 / 3.4 倍加速，
显存 3.3GB → 1.7GB。8GB 卡上不转会撞满显存，触发 Windows 下不可逆的分配器碎片化
（表现为某本书突然慢 60 倍且此后永久变慢）。

## 快速开始

### 环境

- Python 3.10+，CUDA GPU
- bge-m3 → `D:/model/bge-m3/BAAI/bge-m3`
- bge-reranker-v2-m3 → `D:/model/bge-reranker-v2-m3`
- `tagger/data/` 下三个索引文件（见"适配其他领域"，在 .gitignore 里，需自行生成）

```bash
pip install sentence-transformers faiss-cpu numpy
```

### 运行

```bash
export OPENCODE_API_KEY=...        # Stage 3 需要；只跑 1/2 则不需要

# 单本 / 小批量
python -m tagger.pipeline --book-dir /path/to/novels
python -m tagger.pipeline --books books.json --stages 1,2      # 仅本地阶段

# 全库（分片并行 + 断点续跑 + 单实例锁）
python -m tagger.run_corpus                # 只看计划
python -m tagger.run_corpus --go           # 执行
python -m tagger.status                    # 看进度

# 单次调用模式（120 个候选一次问完，省约 4 倍输入；结果与 4 批模式不同，勿混用）
python -m tagger.pipeline --config singlecall --stages 3
```

### 输出

`final.jsonl`，一行一本书：

```json
{"book": "书名.txt",
 "tags": [{"canonical_id": "play.tight_bondage", "tag_name": "紧缚",
           "confidence": 0.9, "evidence": "逐字原文片段"}],
 "status": "ok", "elapsed_s": 63, "candidates_used": 120, "llm_raw": 24}
```

`status` 取值：`ok` 正常／`empty` 模型判定无匹配标签／`all_filtered` 模型有输出但全被校验拦下／
`partial_error`、`partial_rate_limited` 部分批次失败（标签保留但不完整）／`blocked` 内容被网关拦截／
`truncated` 输出被 max_tokens 截断（已翻倍重试一次）。

## 配置

`tagger/config.py`，下列为实测过的默认值：

| 参数 | 默认 | 说明 |
|------|------|------|
| `stage1_top_k` | 500 | **每块**召回数（不是每本） |
| `max_candidates` | 900 | 并集上限 |
| `chunk_chars` | 2000 | 切块大小（各阶段共用，必须一致） |
| `chunk_batch_size` | 8 | 每批编码块数（实测 8 比 16 更快且省显存） |
| `bge_fp16` | True | bge-m3 转 fp16 |
| `stage2_top_k` | 120 | 重排后交给判定的候选数 |
| `reranker_fp16` / `reranker_max_length` | True / 512 | 交叉编码器 |
| `judge_mode` | `forced` | `forced`=逐条 y/n；`select`=从菜单挑（不推荐） |
| `forced_batch_size` | 30 | 每批候选数；批大小会显著改变结果 |
| `thinking_enabled` | False | 实测开启无改善 |
| `verify_evidence` | True | 证据必须逐字出现在正文 |
| `confidence_threshold` | 0.75 | 注意：模型实际只输出 0.9，该阈值只能拦下它自评低的 |
| `context_budget_chars` | 12000 | 给判定看的正文下限 |
| `context_ratio` / `context_budget_max` | 0.08 / 100000 | 上下文随书长放大及其上限 |

## 实测成本与性能（RTX 3060 Ti 8GB，4,342 本语料）

| 阶段 | 耗时 | 说明 |
|---|---|---|
| Stage 1 | 约 5 小时 | GPU 串行 |
| Stage 2 | 约 14 小时 | GPU 串行 |
| Stage 3 | 约 7 小时 | API，可按 key 分片并行 |

**成本约 ¥0.066/本**（deepseek-flash，4 批模式，实测标定）。
结构：输入 token 占大头，且 forced 模式会把上下文按批次数重复发送；
缓存命中能显著降低单价（deepseek-flash 有前缀缓存，deepseek-v4-pro 实测没有）。

## 已知局限

1. **召回率约 65%**（以 Gemini 3.7 Flash 为基准，12 本对照）；精确率约 80%。
   实测换模型/开思考/上 pro 均无效：`deepseek-v4-flash-0731` 召回更低（50%），
   pro 贵 18 倍且无缓存。
2. **判定依据是片段，不是全书**。上下文预算 12k–100k 字随书长自适应，
   大书仍有 49% 的证据集中在前 10%——部分是模型偏好引用开头，部分是候选本身偏前。
3. **批大小会改变结果**：4 批×30 与 1 批×120 只有 56% 一致。换批大小等于换一套判定。
4. **证据质量**：约 4% 的标签证据不足 8 字（逐字可核验但只是提示性）。
5. **泛用标签区分度低**：部分标签（通用身体部位词等）会命中 20–30% 的书。

## 适配其他领域

tagger 是通用引擎，换领域只需替换 `tagger/data/` 下三个文件：

| 文件 | 来源 | 说明 |
|------|------|------|
| `retrieval_index.json` | ontology_factory 输出 | 本体条目（含 embedding_text） |
| `retrieval_faiss.index` | `ontology_factory/build_faiss_index.py` | 预计算向量索引 |
| `retrieval_ids.json` | 同上 | 索引行号 → canonical_id |

注意 `*.faiss` / `*.index` 和 `tagger/data/` 都在 `.gitignore` 里（索引是派生数据）。

## 文件结构

```
tagger/
├── data/                     # 索引（.gitignore，需自行生成）
├── config.py                 # 所有参数 + 预设档位
├── chunking.py               # 切块（各阶段共用，必须一致）
├── stage1_recall.py          # chunk 召回 + 书名独立查询
├── stage2_rerank.py          # 交叉编码器重排（TF-IDF+RRF 兜底）
├── stage3_confirm.py         # LLM 逐条判定 + 证据核验 + 去重 + key 轮换
├── prompt_modes.py           # forced / select 两种提示词
├── pipeline.py               # 单次流程编排
├── run_corpus.py             # 全库驱动（分片并行、断点续跑、单实例锁）
├── status.py                 # 进度查看
├── compare_runs.py           # 两次结果对比（含一致度）
├── evaluate.py               # 错误拆解（需人工金标）
├── build_review_queue.py     # 人工复核队列生成
├── build_final_queue.py      # 多层裁决队列（多裁判场景）
├── export_for_gemini.py      # 导出给外部 agent 模型判定
└── load_gemini.py            # 读回其结果
```

## 工程注意事项

- **断点续跑**：Stage 1/2/3 都扫描已有输出并跳过，中断后重跑同一条命令即可。
- **单实例锁**：`run_corpus.py` 拒绝在同一输出目录上并行启动第二份。
  同一目录被多进程写入的后果是缓存记录成倍重复（实测发生过 5 份同时跑）。
- **Stage 2 是 GPU 瓶颈**：耗时由 `stage1_top_k` × 每本块数决定。
- **Stage 3 key 轮换**：余额不足（402 `INSUFFICIENT_BALANCE`）时自动切下一个 key；
  429 限流只等待、不换 key（换 key 会让多个分片抢同一账号）。
