# 018 · export 第一阶段进入 Action Registry 但默认禁用

## 状态

- 状态：已敲定
- 时间：2026-06-26 12:39
- 触发：用户确认采用方案 2，并强调第一阶段先把核心链路跑通

## 决策

`export` 第一阶段进入固定 Action Registry，但默认作为预留禁用态。第一阶段不生成导出文件、不开放完整数据导出、不导出 raw result，只允许后端按产物类型、权限和功能开关返回 `enabled=false` 与明确的 `disabled_reason`。

## 背景

前面已经确定 `actions` 采用固定注册表加后端受控动作实例，并确定 `ArtifactCard` 使用 `primary_ref` 与 `related_refs` 表达主产物和辅助引用。接下来需要决定 `export` 是否第一阶段就做成可用能力。

如果第一阶段完全不展示 `export`，产品闭环会偏弱；如果第一阶段直接开放导出，又会引入文件生成、权限、脱敏、下载链路和审计事件，容易挤占核心链路建设。

## 选择理由

- 符合“先把核心链路跑通”的阶段目标，把第一阶段重点放在 BI 查询、产物卡、引用、动作协议和事件链路上。
- `export` 进入 Action Registry，可以提前稳定前后端协议、按钮位置、禁用原因、事件审计和后续启用路径。
- 默认禁用能避免导出链路提前承诺能力，降低敏感数据泄露、权限绕过和文件生命周期管理风险。
- 后续启用时可以在同一 action 类型下逐步放开轻量报告导出，再扩展到图表、工作台产物或受控数据文件。

## 被排除方案

- 第一阶段完全不出现 `export`：实现最简单，但用户看到报告或图表后没有导出预期，C 产品形态不完整。
- 第一阶段开放极小范围导出：产品闭环更强，但仍需要处理文件生成、下载、权限、敏感内容扫描和审计，第一阶段成本偏高。

## 对架构的影响

- Action Registry 第一阶段保留 `export`。
- `export` action 实例默认结构为：

```text
action_type: export
enabled: false
disabled_reason: 导出能力将在后续版本开放
payload:
  primary_ref
  export_formats
  feature_flag
```

- 后端可以根据 `artifact_type`、权限、功能开关和产物状态决定是否下发禁用原因，但第一阶段不得返回可执行导出 payload。
- 前端渲染 `export` 时必须尊重 `enabled=false`，展示禁用态和 `disabled_reason`，不得自行构造下载链接。
- 审计事件只记录用户看到或点击了禁用导出入口，不记录不存在的导出文件。

## 对开发计划的影响

- P5 需要在 `ArtifactCard` 动作协议中加入 `export` 禁用态渲染。
- P5 需要在事件协议中预留 `export.disabled_shown` 或同类 trace-only 事件。
- P5 不实现文件生成、下载链接、导出任务队列、Excel/CSV/Markdown 生成和完整数据导出。
- P6 或后续 C-ready 阶段再补导出权限、脱敏规则、文件生命周期、下载审计和格式白名单。

## 后续问题

- `continue_edit` 第一阶段由 ReportAgent 承接，还是先作为详情面板动作预留。
- `retry` 是重试整个任务，还是重试最近失败的子任务。
- `role` 何时从预留字段升级为强枚举。
