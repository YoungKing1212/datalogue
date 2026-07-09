# ============================================================
# File Name   : schema_formatter.py
# Description:
#   Schema 紧凑序列化工具。
#
# Responsibilities:
#   - 把 schema_structured["fields"] 列表转为紧凑单行文本，压缩 token 用量。
#   - 过滤 unused 角色字段，避免无用信息进入 prompt。
#   - 枚举维度字段把样例内联到注释括号中，减少重复冗余。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

from typing import Any

# 角色码映射 — "unused" 故意不在此映射中，下游直接过滤
ROLE_CODE: dict[str, str] = {
    "metric_candidate": "M",
    "dimension_candidate": "D",
    "time_field": "T",
    "id_field": "I",
}

# unused 角色集合，供外部判断
UNUSED_ROLES = {"unused"}


def _is_enum_dim(role: str, sample_values: list) -> bool:
    """判断是否为可内联样例的枚举维度字段。"""
    return role == "dimension_candidate" and bool(sample_values) and len(set(str(v) for v in sample_values)) <= 6


def format_fields_compact(fields: list[dict[str, Any]]) -> str:
    """把 schema_structured["fields"] 转为紧凑单行格式。

    行格式：name:type "desc(样例a/b/c)" [role_code[,agg]]
    - unused 角色字段直接跳过
    - 枚举维度字段把样例嵌入 desc 括号中
    """
    lines = []
    for f in fields:
        role = f.get("semantic_role") or ""
        if role in UNUSED_ROLES or not role:
            continue

        name = f.get("name") or f.get("column_name") or ""
        data_type = (f.get("data_type") or "").upper()
        desc = (
            f.get("effective_desc")
            or f.get("business_desc")
            or f.get("ai_description")
            or f.get("column_comment")
            or ""
        ).strip()

        sample_values = f.get("sample_values") or []

        # 枚举维度：样例内联到 desc 括号
        if _is_enum_dim(role, sample_values):
            unique_samples = list(dict.fromkeys(str(v) for v in sample_values))[:4]
            inline = "/".join(unique_samples)
            desc = f"{desc}({inline})" if desc else f"({inline})"
            sample_values = []  # 已内联，不再单独附加

        role_code = ROLE_CODE.get(role, "")
        default_agg = (f.get("default_agg") or "").upper()
        agg_suffix = f",{default_agg}" if role_code == "M" and default_agg and default_agg != "NONE" else ""
        role_tag = f" [{role_code}{agg_suffix}]" if role_code else ""

        # 非枚举字段最多附加 3 个样例
        sample_tag = ""
        if sample_values:
            remaining = [str(v) for v in sample_values[:3]]
            sample_tag = f" 样例={','.join(remaining)}"

        desc_part = f' "{desc}"' if desc else ""
        lines.append(f"{name}:{data_type}{desc_part}{role_tag}{sample_tag}")

    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """粗粒度估算文本 token 数，用于埋点统计，不影响业务逻辑。"""
    return max(1, len(text) // 4)
