# LeadAgent Planner Projection M1 实施计划

## 目标

在不改变默认生产行为的前提下，为 LeadAgent 规划器增加可灰度启用的输入投影层。M1 只收敛 Planner / Skill Selector 的输入面，保留原始路径作为默认关闭兼容路径，并补齐单元测试和观测元数据。

## 任务

1. Projection Contracts
   - 新增 `app/services/lead_agent_planner_projection.py`。
   - 提供 Skill Selector 输入投影、Tool Planner 输入投影和投影指标构造函数。
   - 投影内容只包含 Planner 所需的候选技能、短上下文、问题和候选工具，不携带原始大上下文字段。

2. Feature Flag
   - 在 `Settings` 增加 `LEAD_AGENT_PLANNER_USE_PROJECTION: bool = False`。
   - 默认关闭，M1 不通过环境外的隐式路径启用。

3. Wire Projection Into Planner Payloads
   - 在 `lead_agent.py` 中读取开关。
   - 开启时将 Skill Selector / Tool Planner LLM 输入替换为投影输入。
   - Langfuse generation metadata 增加 `projection_enabled` 与投影前后字符量指标。

4. Default-Off Compatibility
   - 关闭开关时保持原始 payload 结构不变。
   - 用现有测试和新增断言防止默认路径行为漂移。

5. Control-Plane Regression Tests
   - 覆盖开关开启时不向 LLM payload 泄露原始大上下文字段。
   - 覆盖 Langfuse metadata 记录投影启用状态和 schema version。

6. Verification and Project Memory
   - 运行聚焦后端测试。
   - 更新 `.codex/project-memory.md`，记录完成时间、涉及文件、关键改动、验证方式和后续风险。

## M1 边界

- 不重写 LeadAgent 节点流转。
- 不改变 DatasetSubAgentRequest 契约。
- 不默认启用投影。
- 不在 M1 引入新的规划策略枚举。
