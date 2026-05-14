# Ontology Factory

**生产级本体标准化系统。v1.0.0**

将原始、非结构化的标签清单转化为冻结的、机器可读的标准化本体。

```
raw_tags.json + domain_profile.json  →  冻结本体 + 检索索引 + 别名图
```

下游消费：冻结后的检索索引供独立 [tagger](../tagger/) 包做文本打标。

---

## 目录结构

```
ontology_factory/
├── profiles/               # 领域配置文件定义
│   ├── domain_profile.schema.json   # 配置文件的 JSON Schema
│   └── adult_profile.json           # 完整的成人标签领域配置
├── stages/                 # 流水线阶段实现 (S1-S8)
│   ├── __init__.py         # 基类、注册表、共享工具
│   ├── s1_triage.py        # 清单去重 + 清理
│   ├── s2_normalize.py     # Flash 批量标准化
│   ├── s3_namespace.py     # 命名空间架构冻结
│   ├── s4_freeze_id.py     # 标准 ID 解析
│   ├── s5_alias.py         # 别名合并
│   ├── s6_validate.py      # 冻结前验证
│   ├── s7_retrieval.py     # 检索索引导出
│   └── s8_freeze.py        # 生产冻结 + 版本管理
├── validators/             # 确定性验证脚本
│   ├── validator.py        # 全部 9 项冻结前检查
│   └── __init__.py
├── review_queue/           # 人机协同审核
│   ├── schema.py           # 审核项模式 + 队列管理器
│   ├── reviewer.py         # 交互式 CLI 审核工具
│   └── __init__.py
├── exports/                # 冻结本体输出
├── prompts/                # LLM 提示词模板
├── config/                 # 配置文件
│   └── factory_config.yaml  # 生产配置
├── docs/                   # 文档
│   ├── 操作手册.md
│   ├── ontology_factory_design.md
│   └── ontology_factory_framework.md
├── run_factory.py          # 主入口：构建本体
└── README.md
```

| 目录 | 职责 |
|-----------|---------------|
| `profiles/` | 领域配置 — 唯一的领域特定文件 |
| `stages/` | 8 阶段流水线编排 (Flash + Pro + Script) |
| `validators/` | 确定性检查 — 零 LLM，零幻觉 |
| `review_queue/` | 人机协同审核队列管理 |
| `exports/` | 冻结输出：本体 JSON、检索索引、清单文件 |
| `prompts/` | 参数化 LLM 提示词模板 |
| `config/` | 工厂运行时配置 |

---

## 快速开始

```bash
# 完整流水线
python run_factory.py \
  --profile profiles/adult_profile.json \
  --input raw_tags.json
```

阶段说明：
- **S1-S8**（默认）：完整流水线
- **仅 S1**：`--end-stage s1` 仅执行分诊
- **跳过 Flash**：`--skip-flash` 仅运行脚本阶段

详见 `docs/操作手册.md`。

---

## 冻结不变量（请勿修改）

| ID | 不变量 |
|----|-----------|
| F1 | 层 A（类型分布）为唯一路由权威 |
| F2 | 仅 4 个路由信号 |
| F3 | 阈值已冻结：flat 0.80，specialized 0.60，其余走 graph |
| F4 | meta_style：tag_count < 10 或 meta_ratio > 0.5 |
| F5 | 4 种本体类型 — 不得新增 |
| F6 | 层 B 仅标注，绝不更改类型 |
| F7 | 仅 4 种 TRUSTED 关系类型 |
| F8 | EXPERIMENTAL 类型绝不进入输出 |
| F9 | 核心产物 100% 关系无关 |
| F10 | 路由中不含置信度字段 |

---

## 关键阈值

| 阈值 | 值 | 含义 |
|-----------|-------|---------|
| auto_accept | 0.85 | 置信度 ≥ 此值：直接接受，无需审核 |
| needs_review | 0.70 | 置信度 < auto_accept 且 ≥ 此值：标记审核 |
| reject | 0.60 | 置信度 < 此值：需要重新标准化 |
| merge_auto | 0.90 | 别名合并置信度 ≥ 此值：自动合并 |
| max_depth | 3 | 标准 ID 段数与父链深度 |

---

## 环境需求

- Python 3.10+
- DeepSeek API Key（pro + flash 两条线）
- `pip install requests pyyaml`

不需要 GPU、本地模型。

---

## Pro 退出边界

初次构建本体并冻结后，修改本体结构才需要 Pro（Architect 模型/人工）：

**需要 Pro（架构演进）：**
- 设计新的命名空间
- 新增本体类型
- 更改标准 ID
- 合并已有的冻结条目
- 更改命名空间分配
- 编写新的领域配置文件

**不需要 Pro（日常维护）：**
- 新增标签（自动获取新的标准 ID）
- 新增别名
- 修正定义中的错别字
- 运行验证检查
- 重新生成检索索引导出
