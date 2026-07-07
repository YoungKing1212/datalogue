# 027 · SOUL.md 抽成 Datalogue 内部契约并同步到外部 Skill

## 状态

- 状态：已敲定
- 时间：2026-06-26 16:17
- 触发：用户确认 SOUL.md 归属采用“抽成 Datalogue 内部契约再同步出去”

## 决策

`SOUL.md` 的真相源放回 Datalogue 内部，作为 BI 能力不可越界契约；Hermes skill、AgentScopeShellAdapter 或未来外部 Agent 使用的 `SOUL.md` 都从 Datalogue 内部契约同步生成或复制，不再把外部 skill 包里的 `SOUL.md` 当成唯一主版本。

## 背景

当前路线中，BI 内核需要同时被 LeadAgent、DatasetAgent、Hermes-style Skill、`ask_bi`、AgentScopeShellAdapter 和未来 Agentic Shell 复用。如果 `SOUL.md` 只放在 Hermes skill 包内，Datalogue 内部主链、测试、同步和未来 AgentScope adapter 都会缺少一个稳定契约源。

## 选择理由

- BI 安全边界属于 Datalogue 内核，不属于某一个外部 skill 包。
- 内部契约可以被测试、代码加载、文档审计和同步流程共同引用。
- Hermes skill 和未来 AgentScope adapter 都应该消费同一个契约版本，避免多份 SOUL 漂移。
- 后续如果要升级权限、SQL、artifact、trace 或 control plane 规则，只需要改 Datalogue 内部契约，再同步到外部入口。

## 被排除方案

### 方案 A：继续只维护 Hermes skill 包内的 SOUL.md

不采用。它容易让外部 skill 成为主版本，Datalogue 内核反而缺少可测试、可审计的契约源。

### 方案 B：每个入口各维护一份 SOUL.md

不采用。它会导致 LeadAgent、Hermes、AgentScope、DatasetAgent 的边界规则不一致，增加安全和回归风险。

### 方案 C：Datalogue 内部契约为主，外部入口同步

采用。内部契约作为 source of truth，外部 skill 和 adapter 只是同步目标。

## 对架构的影响

- 新增 Datalogue 内部 SOUL 契约文件，例如 `datalogue-api/app/contracts/BI_SOUL.md`。
- Hermes skill 包内 `hermes-skills/datalogue/SOUL.md` 变成同步目标。
- AgentScopeShellAdapter 初始化时读取或引用 Datalogue 内部 SOUL 契约，不直接依赖 Hermes skill 目录。
- 测试需要覆盖内部契约和同步目标的一致性。

## 对开发计划的影响

- P0 需要新增“SOUL 内部契约与同步”任务。
- 正式开发计划需要补 `BI_SOUL.md`、同步脚本或同步服务、契约一致性测试。
- 后续发布流程需要把 SOUL 契约变更纳入审核。

## 后续问题

- 内部契约文件最终放在 `datalogue-api/app/contracts/BI_SOUL.md`，还是放在 `docs/architecture/contracts/BI_SOUL.md` 后由代码读取？
- 同步到 Hermes skill 是手动命令、测试校验，还是发布流程自动执行？
- AgentScopeShellAdapter 是直接读取 Markdown，还是转成结构化 policy 后注入 system prompt？
