# 语义层 prompt 构建 — 把 SemanticDataset / Metric / Dimension 渲染成 LLM 可读的 schema 文本

import json as _json

from app.models.dataset import SemanticDataset


def build_schema_prompt(dataset: SemanticDataset, metrics: list, dimensions: list) -> str:
    """把语义层（数据集 + 指标 + 维度）拼成供 LLM 阅读的 schema 上下文文本。
    - 指标行包含 expr / table_name / time_field / filter_sql / synonyms
    - 维度行包含 column_name / table_name / enum_values / synonyms
    - tables_json 单独附在头部，供下游编译器解析真实表名

    注意：time_field 必须拼进去——下游 dsl_generate 会让 LLM 选 time_range.field，
    若不告知，LLM 会从 DDL 瞎猜导致用错时间列。
    """
    lines = [f"数据集: {dataset.name}", f"描述: {dataset.description or '无'}", ""]
    if dataset.tables_json:
        lines.append(f"tables_json: {_json.dumps(dataset.tables_json, ensure_ascii=False)}")
        lines.append("")
    # 数据集级 LLM 约束（硬性要求）—— 放在"指标列表"之前，优先被 LLM 看到。
    # 仅当非空才注入，避免噪音。
    if dataset.prompt_instructions and dataset.prompt_instructions.strip():
        lines.append("【数据集级 LLM 约束（硬性要求）】")
        lines.append(dataset.prompt_instructions.strip())
        lines.append("")
    lines.append("【指标列表】")
    for m in metrics:
        synonyms = ", ".join(m.synonyms or [])
        # 必须把 time_field + table_name 拼进去：time_range.field / 主表确定都靠它们
        time_field = f" 时间字段={m.time_field}" if m.time_field else ""
        table = f" 表={m.table_name}" if m.table_name else ""
        lines.append(
            f"- {m.name} ({m.display_name}): 表达式={m.expr}{table}{time_field}"
            f"{' 同义词=' + synonyms if synonyms else ''}"
            f"{' 过滤=' + m.filter_sql if m.filter_sql else ''}"
        )
    lines.append("")
    lines.append("【维度列表】")
    for d in dimensions:
        synonyms = ", ".join(d.synonyms or [])
        enums = ", ".join(d.enum_values or [])
        lines.append(
            f"- {d.name} ({d.display_name}): 字段={d.column_name}"
            f"{' 枚举=' + enums if enums else ''}"
            f"{' 同义词=' + synonyms if synonyms else ''}"
        )
    return "\n".join(lines)


__all__ = ["build_schema_prompt"]
