# AgentState — LangGraph 工作流全局状态定义

from typing import TypedDict, Optional, List


class AgentState(TypedDict):
    """NL2DSL2SQL 工作流状态，贯穿 IntentRecognition → ReportGenerator 全链路。"""

    # 输入层
    question: str  # 用户原始问题
    dataset_id: Optional[int]  # 指定数据集（可选）
    history: Optional[List[dict]]  # 历史对话消息（最近 N 轮）

    # 意图识别层
    intent: Optional[str]  # query | chitchat | function
    entities: Optional[dict]  # {"metrics": [], "dimensions": [], "time_range": {}}

    # Schema 召回层
    schema_context: Optional[str]  # 召回的语义层描述文本

    # DSL 层
    dsl: Optional[dict]  # 结构化 DSL JSON
    dsl_valid: bool  # DSL 校验是否通过

    # SQL 层
    sql: Optional[str]  # 编译后的 SQL
    sql_result: Optional[dict]  # 查询结果 {"columns": [], "rows": []}

    # 输出层
    answer: Optional[str]  # 最终自然语言回答
    sql_list: List[str]  # 本轮执行的所有 SQL

    # 控制层
    error: Optional[str]  # 错误信息（用于重试）
    retry_count: int  # 当前重试次数
    should_retry: bool  # 是否触发重试

    # 可观测性
    token_usage: Optional[
        dict
    ]  # 累积 Token 用量 {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
