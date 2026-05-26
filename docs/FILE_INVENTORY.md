# 仓库文件清单 File Inventory — v0.1-stable

## 根目录 Root

| 文件 | 用途 | 语言 |
|------|------|------|
| `.gitignore` | Git 排除规则（runtime artifacts、secrets、大文件） | EN |
| `LICENSE` | MIT 许可证全文 | EN |
| `README.md` | 项目主文档：架构、模块、快速开始、状态 | 中文+EN |
| `requirements.txt` | Python 依赖（requests, pyyaml） | EN |
| `RELEASE_NOTES_v0.1.md` | v0.1-stable 发布说明（已移至 docs/） | 见 docs/ |

## 文档 docs/

### 公开文档 docs/specs/

| 文件 | 用途 | 语言 |
|------|------|------|
| `docs/specs/tag-system-design.md` | 系统架构设计文档（全链路：acquisition→enrichment→ontology→tagger） | 中文 |

### 发布文档 docs/

| 文件 | 用途 | 语言 |
|------|------|------|
| `docs/RELEASE_NOTES_v0.1.md` | v0.1-stable 发布说明：新功能、指标、已知限制、路线图 | 中文+EN |
| `docs/DOCUMENTATION_LOCALIZATION_REPORT.md` | 文档本地化报告：哪些已双语化、哪些保持英文、术语表 | 中文+EN |

### 内部文档 docs/internal/（gitignored 外的历史产物）

| 文件 | 用途 | 语言 |
|------|------|------|
| `docs/internal/2026-05-24-tag-system-architecture-redesign.md` | 架构重设计历史记录 | EN |
| `docs/internal/AUDIT_REPORT.md` | release audit 报告 | EN |
| `docs/internal/FINAL_RELEASE_SUMMARY.md` | 发布最终总结 | EN |
| `docs/internal/GITHUB_VISIBILITY.md` | GitHub 公开可见性评估 | EN |
| `docs/internal/IMPLEMENTATION_PLAN.md` | 实现计划（agent 产物） | EN |
| `docs/internal/LICENSE_RECOMMENDATION.md` | 许可证选择建议 | EN |
| `docs/internal/README_AUDIT.md` | README 审计记录 | EN |
| `docs/internal/RELEASE_BLOCKING_CHECK.md` | 发布阻塞检查清单 | EN |
| `docs/internal/RELEASE_GIT_AUDIT.md` | Git 仓库审计 | EN |
| `docs/internal/RELEASE_PRECHECK.md` | 发布前预检查 | EN |
| `docs/internal/SKILL_USAGE_PLAN.md` | Agent skill 使用计划 | EN |
| `docs/internal/TEST_LAYOUT_PLAN.md` | 测试目录布局计划 | EN |

## tag_acquisition/ — 标签采集模块

### 源码

| 文件 | 用途 |
|------|------|
| `tag_acquisition/__init__.py` | Python package 标记 |
| `tag_acquisition/run.py` | 入口：命令行运行采集 pipeline |
| `tag_acquisition/collector.py` | Pixiv API 采集器 |
| `tag_acquisition/normalize.py` | Surface form 归一化（全角→半角、空白清理） |
| `tag_acquisition/split.py` | 复合 tag 拆分（delimiter policy、保护短语） |
| `tag_acquisition/filter.py` | 质量过滤（长度、噪声、黑名单） |
| `tag_acquisition/corpus.py` | 语料快照管理（追加式导出） |
| `tag_acquisition/schema.py` | 输入/输出数据结构定义 |
| `tag_acquisition/analyze_noise.py` | 噪声模式分析工具 |
| `tag_acquisition/config.yaml` | 采集配置（分隔符、黑名单、质量阈值） |

### 文档

| 文件 | 用途 | 语言 |
|------|------|------|
| `tag_acquisition/README.md` | 模块文档：pipeline 流程、schema、配置、快照机制 | 中文+EN |

## ontology_factory/ — 本体工厂模块

### 入口

| 文件 | 用途 |
|------|------|
| `ontology_factory/run_factory.py` | Pipeline 总入口：参数解析、stage 路由、执行调度 |
| `ontology_factory/collect_observation.py` | 观测数据收集工具（指标、失败案例） |

### 配置

| 文件 | 用途 |
|------|------|
| `ontology_factory/config/factory_config.yaml` | 运行时配置：模型路由、stage 参数、confidence 阈值、ID 规范、alias 策略、版本控制 |
| `ontology_factory/profiles/adult_profile.json` | 成人内容 domain profile：namespace 地图、语义类型、类别 |
| `ontology_factory/profiles/domain_profile.schema.json` | Domain profile 的 JSON Schema 定义 |

### Stages（S0–S8）

| 文件 | 用途 | 需要 API |
|------|------|----------|
| `ontology_factory/stages/__init__.py` | Stage 注册表 |
| `ontology_factory/stages/s0_enrich.py` | S0: LLM 语义化（分类、定义、上位 tag、示例词） | Flash |
| `ontology_factory/stages/s1_triage.py` | S1: 库存分拣（去重、空名清理、字段统一） | 否 |
| `ontology_factory/stages/s2_normalize.py` | S2: LLM 语义标准化（canonical_id、namespace、语义类型） | Flash |
| `ontology_factory/stages/s3_namespace.py` | S3: 命名空间架构校验 | 否 |
| `ontology_factory/stages/s4_freeze_id.py` | S4: ID 冻结（截断过深 ID、人工修正、重复检查） | 否 |
| `ontology_factory/stages/s5_alias.py` | S5: 别名折叠（同义词合并、别名图构建） | 否 |
| `ontology_factory/stages/s6_validate.py` | S6: 验证审计（9 项确定性检查） | 否 |
| `ontology_factory/stages/s7_retrieval.py` | S7: 检索导出（向量检索就绪索引） | 否 |
| `ontology_factory/stages/s8_freeze.py` | S8: 生产冻结（版本化打包、冻结清单） | 否 |

### Validators

| 文件 | 用途 |
|------|------|
| `ontology_factory/validators/__init__.py` | Validator 注册表 |
| `ontology_factory/validators/validator.py` | 9 项验证检查（重复 ID、循环检测、深度检查、namespace 合法性等） |

### Review Queue

| 文件 | 用途 |
|------|------|
| `ontology_factory/review_queue/__init__.py` | Review queue package |
| `ontology_factory/review_queue/schema.py` | Review item 数据结构 |
| `ontology_factory/review_queue/reviewer.py` | 人工 review 工具（终端交互） |

### 文档

| 文件 | 用途 | 语言 |
|------|------|------|
| `ontology_factory/README.md` | 模块文档：核心概念、9 阶段表、S0 Contract、Review Queue、输出结构 | 中文+EN |
| `ontology_factory/MANUAL.md` | 完整操作手册（605 行，从零开始跑通的教程） | 中文 |
| `ontology_factory/docs/ontology_factory_design.md` | Domain Profile 编写指南 + 架构设计 | 中文 |

### 导出目录 exports/

| 文件 | 用途 |
|------|------|
| `ontology_factory/exports/.gitkeep` | 保持目录存在 |
| `ontology_factory/exports/ontology_export_v1_0_0.json` | 冻结 ontology 主文件（上次运行产物） |
| `ontology_factory/exports/retrieval_index.json` | 检索索引（上次运行产物） |

### 运行时产物 work/（gitignored）

| 文件/目录 | 用途 |
|-----------|------|
| `work/*.json` | 各 stage 中间输出（enriched_tags, inventory_clean, stage2_normalized 等） |
| `work/pipeline*.log` | Pipeline 运行日志 |
| `work/ontology_versions/` | 版本化 ontology 快照（latest/, v1_0_0/） |
| `work/alias_graph.json` | 别名图 |
| `work/validation_report.json` | S6 验证报告 |
| `work/retrieval_index.json` | S7 检索索引 |

### 其他

| 文件 | 说明 |
|------|------|
| `ontology_factory/tag.json` | 生产数据集（1178 条, 645KB）— gitignored |

## tests/ — 测试数据

| 文件 | 用途 |
|------|------|
| `tests/README.md` | 测试数据文档：文件列表、使用方法、指标 |
| `tests/data/acquisition/raw_30.json` | 30 条原始格式 tag（`{label, count}`） |
| `tests/data/acquisition/adversarial_30.json` | 30 条边界用例（日语、缩写、歧义词） |
| `tests/data/acquisition/small_50.json` | 50 条真实 tag（已语义化格式） |
| `tests/data/acquisition/medium_200.json` | 200 条真实 tag（已语义化格式） |
| `tests/data/ontology/smoke_20.json` | 20 条已语义化 tag（快速冒烟测试） |

## Metrics（gitignored — 运行时生成）

| 文件 | 用途 |
|------|------|
| `ontology_factory/metrics/observation_report_20260524.md` | 真实数据观测报告（30→50→200 趋势分析） |
| `ontology_factory/metrics/v0.1-stable_STATUS.md` | v0.1-stable 状态报告（pipeline 各 stage 状态） |
| `ontology_factory/metrics/v0.1-stable_baseline.json` | 基线指标（JSON 格式） |
| `ontology_factory/metrics/v0.1-stable_entries.json` | 条目回归数据 |
| `ontology_factory/metrics/real_50_v1_summary.json` | 50 条运行摘要 |
| `ontology_factory/metrics/real_200_v1_summary.json` | 200 条运行摘要 |
| `ontology_factory/metrics/failed_cases/` | 失败案例数据集（dropped、placeholders、review items、aliases、malformed） |

## Python 缓存（gitignored）

| 模式 | 说明 |
|------|------|
| `**/__pycache__/*.pyc` | Python 字节码缓存 |

---

## 统计 Statistics

| 类别 | 数量 |
|------|------|
| Python 源码 | ~25 个 .py 文件 |
| 配置文件 | 3 个（factory_config.yaml, config.yaml, adult_profile.json） |
| 公开文档（中文+EN） | 5 个 README + 1 发布说明 + 1 本地化报告 |
| 中文设计文档 | 3 个（tag-system-design, MANUAL, ontology_factory_design） |
| 内部文档（EN） | 11 个（一次性 audit 产物） |
| 测试数据 | 5 个 JSON 文件 |
| Schema 定义 | 2 个（domain_profile.schema.json + 各模块内联 schema） |
