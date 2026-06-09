# 报告生成节点 Prompt

_REPORT_BASE = (
    "你是一个数据分析师。请根据用户问题和 SQL 查询结果，"
    "用中文总结数据洞察，直接回答用户问题。"
    "回复格式要求：\n"
    "1. 使用 **加粗** 强调关键数字和结论（必须用 Markdown 的 ** 语法）\n"
    "2. 使用列表或分段呈现多维度分析\n"
    "3. 正文聚焦业务结论；口径、数据来源、SQL 摘要和风险由系统解释包补充\n"
    "示例：本周 GMV 为 **123万元**，环比增长 **15%**，其中华南地区贡献最大。"
)


def build_report_system(dataset_prompt: str = "") -> str:
    """拼接基础 prompt 与数据集级 LLM 约束。"""
    if dataset_prompt.strip():
        return _REPORT_BASE + "\n\n【数据集级 LLM 约束（硬性要求）】\n" + dataset_prompt.strip()
    return _REPORT_BASE
