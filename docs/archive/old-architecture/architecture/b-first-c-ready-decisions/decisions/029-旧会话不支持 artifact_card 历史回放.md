# 029 · 旧会话不支持 artifact_card 历史回放

## 状态

- 状态：已敲定
- 时间：2026-06-26 16:17
- 触发：用户确认旧会话兼容策略为历史 conversation_state / artifact_card 不支持回放

## 决策

第一阶段不为旧会话补齐或迁移 `artifact_card`、C-ready event envelope、`primary_ref` / `related_refs` 或新的 conversation_state 结构。旧会话只保留原有回答和历史消息展示；新的 ArtifactCard、任务时间线和引用回放能力从协议上线后的新会话开始生效。

## 背景

当前计划引入 ArtifactCard、event envelope、refs、retry checkpoint、AgentScopeShellAdapter 等新协议。如果要求旧会话也完整回放新结构，需要做历史数据迁移、兼容解析、缺字段补偿和 UI fallback，会明显扩大第一阶段范围。

## 选择理由

- P0 重点是新主链路正确，不是历史会话数据迁移。
- 旧会话缺少 ArtifactCard 和 event envelope 原始信息，强行回填容易制造不真实的执行证据。
- 不迁移旧会话可以减少状态兼容复杂度，让新协议从上线点开始成为可信真相源。
- 这也符合“query_artifact / conversation_state 是真相源”的原则，不能凭后处理伪造历史 artifact。

## 被排除方案

### 方案 A：为所有旧会话回填 ArtifactCard

不采用。旧会话缺少足够结构化证据，回填会引入不可信 artifact。

### 方案 B：做复杂兼容层，尽量模拟新 UI

不采用。它会拖慢 P0，并让前端长期背负两套复杂协议。

### 方案 C：旧会话只保留原回答，新协议只对新会话生效

采用。旧数据不伪造，新链路从上线后完整落证据。

## 对架构的影响

- 前端历史回放遇到旧消息缺少 `artifact_card` 时，不尝试构造新卡片。
- 后端不做旧 conversation_state 到新 schema 的迁移。
- 不为旧 query artifact 生成新的 `primary_ref` / `related_refs`。
- 可以保留轻量 legacy 标记，但不得把 legacy 标记伪装成新 artifact。

## 对开发计划的影响

- P1 / P2 需要增加旧会话缺失 ArtifactCard 的回归测试。
- 验收口径改为：旧会话不报错、不展示伪造 ArtifactCard；新会话完整展示 ArtifactCard 和引用。
- 文档需要明确协议生效边界，避免误把旧会话不回放当成缺陷。

## 后续问题

- 旧会话 UI 是否需要显示“此历史会话不支持新产物卡回放”的轻量提示？
- 管理员是否需要一个一次性诊断脚本统计旧会话数量，但不做迁移？
- 如果业务强制要求迁移，是否必须重新定义单独的历史迁移项目？
