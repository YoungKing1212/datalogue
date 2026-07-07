# Native Handoff Child 消息模板
# AgentScope native handoff 时构造 DatasetAgent 子运行消息；花括号字段由运行时填充。

NATIVE_HANDOFF_CHILD_MESSAGE_TEMPLATE = """\
AgentScope native handoff: 请作为 DatasetAgent 子运行执行已确认任务。
handoff_id: {handoff_id}
parent_agent: bi_agent
child_agent: dataset_agent
child_run_id: {child_run_id}
dataset_id: {dataset_id}
task_goal: {task_goal}
confirmed_question: {confirmed_question}
routing_rationale: {routing_rationale}
只能返回安全 JSON：event_type、child_run_id、artifact_ref、checkpoint_ref、answer_summary、row_count、column_count。"""

__all__ = ["NATIVE_HANDOFF_CHILD_MESSAGE_TEMPLATE"]
