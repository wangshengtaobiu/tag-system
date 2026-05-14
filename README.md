# tag-system

成人内容标签体系 — 从采集到打标的完整工具链。

```
tag_acquisition/          # Part 1: Pixiv 采集 + AI 初洗（待完善）
    ↓ raw_tags.json
ontology_factory/         # Part 2: 本体冻结与标准化
    ↓ ontology_export_v1.json
tagger/                   # Part 3: 本地模型打标
```

## 模块说明

| 模块 | 状态 | 功能 |
|------|------|------|
| `ontology_factory/` | 生产就绪 | 8 阶段流水线，DeepSeek API 驱动，冻结为本体 JSON |
| `tagger/` | 就绪 | BGE 嵌入 + FAISS 检索 + Qwen 8B 精排，本地推理打标 |
| `tag_acquisition/` | 待完善 | Pixiv 标签采集、热度获取、AI 初洗生成 raw_tags.json |

## 快速开始

```bash
# Part 2: 本体冻结
cd ontology_factory
pip install requests pyyaml
python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json

# Part 3: 打标
cd tagger
pip install numpy sentence-transformers faiss-cpu
python run_tagger.py --index ../ontology_factory/exports/retrieval_index.json --input novels/
```

## 环境

- Python 3.10+
- ontology_factory: 仅需 `requests` + `pyyaml` + DeepSeek API Key
- tagger: 可选 `sentence-transformers` + `faiss` + `transformers`（本地 GPU 推理）
