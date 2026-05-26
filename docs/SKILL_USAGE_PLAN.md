# tag-system 技能使用规划

## 铁律

1. **不做没有依据的断言** — 说"代码有问题"前先读代码，说"模块成熟"先看实际运行结果
2. **事实与推测分离** — 事实是从代码/文件中看到的，推测是基于经验猜的，输出时明确标注
3. **不确定就说"不确定"** — 不编造、不脑补、不替用户做决定
4. **用工具代替记忆** — 不记得代码 → Read，不确定引用 → Grep，不确定能不能跑 → Bash
5. **每次对话开始先检查技能** — 按 superpowers 规则，技能优先于默认行为

---

## 项目阶段总览

```
阶段1: tag_acquisition (采集)    ✅ 已完成
阶段2: ontology_factory (本体)   ✅ v1.0.0 已冻结
阶段3: tagger (打标)             ❌ 待开发  ← 当前焦点
```

## 技能清单与映射

| 技能 | 用途 | 何时调用 |
|------|------|----------|
| `using-superpowers` | 技能使用纪律 | 每次对话开始，确保技能优先 |
| `brainstorming` | 需求探索与设计 | 开始新功能/模块前 |
| `writing-plans` | 实现计划编写 | 设计确认后、编码前 |
| `executing-plans` | 计划执行 | 有计划后、编码时 |
| `subagent-driven-development` | 并行任务执行 | 多模块并行开发 |
| `systematic-debugging` | 问题排查 | 遇到 bug/测试失败时 |
| `test-driven-development` | 测试驱动开发 | 写功能代码前 |
| `verification-before-completion` | 完成前验证 | 声称完成/提交前 |
| `requesting-code-review` | 代码审查 | 功能完成后 |
| `receiving-code-review` | 审查反馈处理 | 收到审查意见后 |
| `finishing-a-development-branch` | 分支完成 | 开发完成、准备合并时 |
| `using-git-worktrees` | 隔离开发 | 需要独立工作区时 |
| `writing-skills` | 创建/修改技能 | 需要新技能时 |
| `dispatching-parallel-agents` | 并行代理分发 | 2+ 独立任务时 |

## 阶段3 (tagger) 完整流程

### Step 1: 需求探索与设计

**调用**: `Skill("brainstorming")`

**触发条件**: 开始 tagger 开发时

**用户提示词示例**:
```
"开始开发 tagger 模块"
"给 tag-system 加一个自动打标功能"
```

**技能内部流程**:
1. 探索项目上下文 — **必须读实际文件、运行实际命令，不做推测**
2. 问澄清问题（一次一个）
3. 提出 2-3 个方案 — **每个方案的优缺点必须基于实际代码/数据/运行结果，不编造**
4. 展示设计，逐步确认
5. 写设计文档到 `docs/superpowers/specs/YYYY-MM-DD-tagger-design.md`
6. 规范自查 — **逐条检查：这个结论有代码/文件/运行结果支撑吗？**
7. 用户审查规范
8. 调用 `writing-plans`

### Step 2: 实现计划

**调用**: `Skill("writing-plans")`

**触发条件**: brainstorming 设计确认后

**用户提示词示例**:
```
"根据 tagger 设计写实现计划"
```

**技能内部流程**:
1. 读取设计文档
2. 拆解为可执行的步骤
3. 定义每个步骤的输入/输出/验证标准
4. 输出计划文件
5. 调用 `executing-plans`

### Step 3: 执行开发

**调用**: `Skill("executing-plans")`

**触发条件**: 实现计划完成后

**用户提示词示例**:
```
"执行 tagger 实现计划"
```

**技能内部流程**:
1. 在隔离会话中执行（或当前会话用 subagent-driven-development）
2. 按步骤实现
3. 每个步骤完成后验证
4. 遇到问题时调用 `systematic-debugging`

### Step 4: 并行开发（可选）

**调用**: `Skill("subagent-driven-development")` 或 `Skill("dispatching-parallel-agents")`

**触发条件**: tagger 有多个独立模块可并行时（如 embedding 模块 + FAISS 模块 + rerank 模块）

**用户提示词示例**:
```
"用子代理并行开发 tagger 的各个模块"
```

### Step 5: 测试

**调用**: `Skill("test-driven-development")`

**触发条件**: 写功能代码前

**用户提示词示例**:
```
"用 TDD 方式开发 tagger 的检索模块"
```

### Step 6: 调试（按需）

**调用**: `Skill("systematic-debugging")`

**触发条件**: 遇到 bug、测试失败、行为异常时

**用户提示词示例**:
```
"tagger 的 FAISS 检索结果不对，排查一下"
```

### Step 7: 完成前验证

**调用**: `Skill("verification-before-completion")`

**触发条件**: 声称功能完成/准备提交前

**用户提示词示例**:
```
"tagger 开发完了，验证一下"
```

**技能内部流程**:
1. 运行所有测试
2. 检查代码质量
3. 确认无遗留问题
4. 验证通过才允许提交

### Step 8: 代码审查

**调用**: `Skill("requesting-code-review")`

**触发条件**: 功能完成、验证通过后

**用户提示词示例**:
```
"审查 tagger 模块的代码"
```

### Step 9: 处理审查意见

**调用**: `Skill("receiving-code-review")`

**触发条件**: 收到审查意见后

**用户提示词示例**:
```
"审查意见说 embedding 模块有问题，处理一下"
```

### Step 10: 完成分支

**调用**: `Skill("finishing-a-development-branch")`

**触发条件**: 所有审查通过、准备合并时

**用户提示词示例**:
```
"tagger 分支开发完成，准备合并"
```

## 通用规则

1. **每次对话开始**: 先检查是否有适用技能（`using-superpowers`）
2. **任何创意工作前**: 必须 `brainstorming`，不能跳过直接写代码
3. **编码前**: 必须有书面计划（`writing-plans` → `executing-plans`）
4. **遇到问题时**: 必须 `systematic-debugging`，不能盲目试错
5. **声称完成前**: 必须 `verification-before-completion`，先验证再断言
6. **用户指令优先**: 用户说怎么做就怎么做，技能不覆盖用户意图

## 快速参考：一句话触发

| 场景 | 触发词 | 技能 |
|------|--------|------|
| 开始新功能 | "开始开发 XXX" | brainstorming |
| 有计划要执行 | "执行计划" | executing-plans |
| 写代码前 | "用 TDD 方式" | test-driven-development |
| 出 bug 了 | "排查/修复 XXX" | systematic-debugging |
| 做完了要提交 | "验证一下" | verification-before-completion |
| 要审查代码 | "审查 XXX" | requesting-code-review |
| 审查完了 | "合并分支" | finishing-a-development-branch |
