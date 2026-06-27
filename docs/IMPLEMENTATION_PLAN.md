# 实现计划

## 任务 ID

T001

## 目标

补齐并保持 `docs/00_REQUIREMENTS.md`、`docs/01_ARCHITECTURE.md`、`docs/02_DECISIONS.md`、`docs/03_TASKS.md` 的一致性，使其成为 `AGENTS.md` 规定的唯一事实来源。

## 理解分析

当前四个文档均已建立且非空，但存在以下具体问题：

1. **`00_REQUIREMENTS.md` 仍依赖错名文档**：第一段称"本文档由项目根目录 `history_agent.md` 转换整理而来"，将 `history_agent.md` 作为该文档的来源依据，违背"不再依赖错名文档作为事实来源"的验收标准。`history_agent.md` 是历史产物，不应作为当前事实来源。

2. **四文档间缺失彼此引用**：当前各文档独立描述各自内容，缺少对等引用。`AGENTS.md` 规定四文档为"唯一事实来源"，但文档自身未体现这一关系。具体来说：
   - `00_REQUIREMENTS.md` 引用了 `01_ARCHITECTURE.md` 和 `02_DECISIONS.md`，但未引用 `03_TASKS.md`
   - `01_ARCHITECTURE.md` 未显式声明其与 `00_REQUIREMENTS.md` 的对等关系
   - `02_DECISIONS.md` 未引用 `00_REQUIREMENTS.md`

3. **文档内容一致性校验**：经逐段比对，`00_REQUIREMENTS.md` 中的业务规则描述（4.1-4.11）与 `01_ARCHITECTURE.md` 的模块职责划分一致；配置描述与 `02_DECISIONS.md` 的 ADR 决策一致；`03_TASKS.md` 的格式已满足任务 ID、目标、验收标准、约束条件、依赖项五项要求。**未发现实质冲突**。

## 预计变更的文件

| 文件 | 变更类型 |
|------|----------|
| `docs/00_REQUIREMENTS.md` | 修改 — 更新首段，消除对 `history_agent.md` 的依赖，增加对另三文档的引用 |
| `docs/01_ARCHITECTURE.md` | 修改 — 在开头增加对 `00_REQUIREMENTS.md` 的引用 |
| `docs/02_DECISIONS.md` | 修改 — 在开头增加对 `00_REQUIREMENTS.md` 的引用 |
| `docs/03_TASKS.md` | 修改 — 在开头增加对 `00_REQUIREMENTS.md` 的引用 |

**不涉及业务代码变更。**

## 实现策略

### 步骤 1：修改 `00_REQUIREMENTS.md` 首段

将第一段从"本文档由项目根目录 `history_agent.md` 转换整理而来"改写为：

> 本文档是四文档唯一事实来源体系的一部分，与 `docs/01_ARCHITECTURE.md`、`docs/02_DECISIONS.md`、`docs/03_TASKS.md` 共同构成项目规范。本文档描述当前系统应满足的业务能力、处理规则、配置约束和交付要求。若本文档与其他规范文档存在冲突，应先提交审查，不应直接修改实现。
>
> （历史说明：本文档内容源于 `history_agent.md`，现已取代其为业务需求的唯一来源。）

改动要点：
- 明确自身定位为"四文档体系的一部分"
- 将 `history_agent.md` 降级为"历史说明"，不再作为事实来源
- 保留冲突解决规则

### 步骤 2：修改 `01_ARCHITECTURE.md` 开头

在文档头部增加与 `00_REQUIREMENTS.md` 的关系声明。

### 步骤 3：修改 `02_DECISIONS.md` 开头

在文档头部增加与 `00_REQUIREMENTS.md` 的关系声明。

### 步骤 4：修改 `03_TASKS.md` 开头

在文档头部增加与项目整体文档体系的关系声明。

### 步骤 5：验证一致性

- 确认 `00_REQUIREMENTS.md` 不再将 `history_agent.md` 作为事实来源
- 确认四文档之间已建立双向引用
- 确认四文档内容无冲突
- 确认 `03_TASKS.md` 所有任务格式完整

## 架构影响

无架构影响。本任务仅涉及文档层面的编辑，不改变任何代码、模块职责或架构边界。

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 修改后引入新的不准确描述 | 低 | 中 | 逐句审查，仅修改首段，保留所有业务内容不变 |
| 遗漏其他文档间的冲突 | 低 | 低 | 已逐段比对，未发现冲突 |

## 测试策略

本任务无业务代码修改，无法执行自动化测试。验证方式：
- 人工检查四文档新版本内容
- 确认 `grep 'history_agent.md' docs/00_REQUIREMENTS.md` 不再将 `history_agent.md` 作为事实来源

## 考虑的替代方案

1. **完全删除 `history_agent.md` 引用**：过于激进，保留历史说明有助于理解文档沿革。
2. **只改 `00_REQUIREMENTS.md` 不动其他三文档**：无法体现四文档对等关系，不完整。
3. **创建 `04_LESSONS.md`**：超出 T001 验收标准，且约束条件要求"不引入新的文档体系"。

## 决策一致性

- 符合 ADR 体系：不改变任何已有架构决策。
- 符合 CLAUDE.md 工作流程：文档治理是预期产出。
- 符合 AGENTS.md 要求：四文档成为唯一事实来源。

## 预估范围

- 变更文件：4 个（均为 `docs/` 目录下的文档）
- 新增行：约 15 行
- 删除行：约 3 行
- 预计耗时：不需测试，纯文档编辑，约 5 分钟
