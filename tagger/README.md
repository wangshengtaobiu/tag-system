# Tagger — 下游打标系统

独立的下游打标包。使用冻结本体做本地推理，为小说/文本自动匹配标签。

```
输入文本 → 分块 → BGE 嵌入 → FAISS top-50 召回 → (Qwen 8B 精排) → top-K 标签
```

---

## 环境

| 要求 | 说明 |
|------|------|
| Python | 3.10+ |
| GPU | 可选。BGE 约 1.3GB 显存，Qwen 约 5.5GB，合计约 7.3GB（RTX 3060 Ti 可运行） |
| 联网 | 首次运行时从 HuggingFace 下载模型，后续离线可用 |

## 安装依赖

```bash
# 最小安装（仅 BGE，无 GPU 或 CPU 模式）
pip install numpy sentence-transformers faiss-cpu

# 完整安装（含 Qwen 精排，需 GPU + CUDA）
pip install numpy sentence-transformers faiss-gpu transformers torch bitsandbytes
```

> 未装 `sentence-transformers` / `faiss` / `transformers` 时自动回退占位模式，不会报错。

## 输入

### 索引文件（必需）

由 Ontology Factory 的 S7 产出的 `retrieval_index.json`，或者 `ontology_export_v1.json`（自动转换）。

### 待打标文本

三种方式：

```bash
# 1. 单个文件
python run_tagger.py --index retrieval_index.json --input chapter1.txt

# 2. 目录（所有 .txt + .json）
python run_tagger.py --index retrieval_index.json --input novels/

# 3. 直接文本
python run_tagger.py --index retrieval_index.json --text "这段小说的内容..."
```

JSON 格式：
```json
[
  {"id": "chapter1", "text": "小说正文..."},
  {"id": "chapter2", "text": "小说正文..."}
]
```

## 运行

```bash
cd tagger

# 基础模式（BGE 嵌入 + FAISS 检索）
python run_tagger.py --index ../ontology_factory/exports/retrieval_index.json --input novels/

# 完整模式（+ Qwen 8B 精排）
python run_tagger.py --index ../ontology_factory/exports/retrieval_index.json --input novels/ --rerank

# CPU 模式
python run_tagger.py --index retrieval_index.json --input novels/ --device cpu

# 过滤命名空间
python run_tagger.py --index retrieval_index.json --input novels/ --namespace sexual_behavior
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--index` / `-i` | 索引文件路径（必填） | — |
| `--input` | 输入文本文件/目录 | — |
| `--text` / `-t` | 直接输入文本 | — |
| `--output` / `-o` | 输出文件 | `tagging_results.json` |
| `--rerank` | 启用 Qwen 8B 精排 | 关闭 |
| `--namespace` / `-n` | 按命名空间过滤 | 不过滤 |
| `--category` | 按分类过滤 | 不过滤 |
| `--semantic-type` | 按语义类型过滤 | 不过滤 |
| `--min-confidence` | 最低置信度阈值 | 0.70 |
| `--top-k` | 每条文本最多输出标签数 | 10 |
| `--chunk-size` | 文本分块大小 | 512 |
| `--no-chunk` | 关闭分块 | 分块 |
| `--device` | cuda / cpu | cuda |
| `--quantization` | Qwen 量化方式 | 4bit |

## 输出

`tagging_results.json`：
```json
{
  "meta": {
    "date": "2026-05-14T...",
    "total_texts": 5,
    "total_time_seconds": 12.3
  },
  "results": [
    {
      "text_id": "chapter1",
      "tags": [
        {
          "canonical_id": "sexual_behavior.oral_sex",
          "name": "口交",
          "namespace": "sexual_behavior",
          "semantic_type": "sexual_act",
          "score": 0.9231,
          "confidence": 0.90
        }
      ],
      "rejected": [],
      "total_candidates": 15,
      "duration_seconds": 2.4
    }
  ]
}
```

## 目录结构

```
tagger/
├── retrieval/
│   ├── __init__.py     # 配置类和数据结构
│   ├── embedder.py     # BGE 嵌入
│   ├── indexer.py      # FAISS 索引
│   ├── retriever.py    # 检索编排
│   └── reranker.py     # Qwen 精排
├── run_tagger.py       # 入口
├── tagger_config.yaml  # 默认配置
└── README.md
```

## 与原 Ontology Factory 的关系

- 上游：Ontology Factory 的 S7 产出 `retrieval_index.json` → 作为 Tagger 的 `--index` 输入
- 解耦：Tagger 不 import 任何 ontology_factory 代码，完全独立运行
- 回退：所有本地模型依赖都可优雅降级（未装库→占位模式，不影响代码运行）
