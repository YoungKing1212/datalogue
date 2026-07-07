# 016 · actions 采用固定注册表加受控动作实例

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:29
- 触发：用户确认采用固定 Action Registry + 后端下发受控动作实例

## 决策

第一阶段 `ArtifactCard.actions` 采用固定 Action Registry + 后端下发受控动作实例。系统预先定义可用 `action_type` 白名单；后端只能返回白名单内的动作实例和白名单 payload；前端按 registry 渲染固定按钮和行为；所有动作执行仍必须走受控工具入口、权限校验和事件审计。

## 背景

前面已经确定 `ArtifactCard` 外层强 schema，`preview_payload` 半强 schema。下一步需要决定 `actions` 是前端固定枚举，还是由后端动态下发。

完全固定枚举实现简单但扩展慢；完全后端下发灵活但风险高，容易引入不可控动作、权限绕过或 UI 混乱。因此采用注册表加受控实例的折中模式。

## 选择理由

- 固定 Action Registry 可以保证前端行为、权限边界和测试口径稳定。
- 后端下发受控动作实例，可以根据产物状态、权限、任务上下文动态决定哪些动作可用。
- 白名单 payload 能避免后端把任意参数塞给前端执行，降低越权和注入风险。
- 该模式适合后续 Agentic Shell 扩展，既能支持动作增长，又不牺牲治理边界。

## 被排除方案

- 前端完全固定枚举：最简单，但后续新增动作需要前后端同步发版，扩展慢。
- 后端完全动态下发动作：最灵活，但前端如果照单全收，会破坏权限、审计和 UI 一致性。

## 对架构的影响

- 第一阶段 Action Registry 至少包含：
  - `open_detail`
  - `continue_edit`
  - `analyze_more`
  - `export`
  - `explain`
  - `retry`
  - `change_dataset`
- `ArtifactCard.actions` 中的每个动作实例必须包含：`action_type`、`enabled`、`disabled_reason`、`payload`。
- `action_type` 必须在 registry 中存在，否则前端丢弃并记录 trace-only 事件。
- `payload` 必须按 `action_type` 走白名单 schema，不能携带 raw SQL、raw result、schema、capsule、trace 主体或 `control_plane` 主体。
- 动作点击不直接执行内部能力，必须转为受控工具调用或受控前端导航，例如打开详情、继续编辑、请求解释、重新尝试、切换数据集确认。

## 对开发计划的影响

- P5 需要补充 Action Registry 和每类动作 payload 白名单。
- 前端 `ArtifactCard` 只渲染 registry 内动作，未知动作进入安全忽略路径。
- 后端生成 `actions` 时需要结合权限、产物状态、任务状态和 artifact 引用。
- 事件协议需要记录动作展示、动作点击、动作阻断和动作完成。

## 后续问题

- `refs` 是否需要拆成 `primary_ref` 与 `related_refs`。
- `export` 第一阶段是否进入可用动作，还是只做预留禁用态。
- `continue_edit` 第一阶段由 ReportAgent 承接，还是先作为详情面板动作预留。
- `retry` 是重试整个任务，还是重试最近失败的子任务。
