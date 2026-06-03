# 跨方言 SQL 工具 — 引号转义、null sanitize、方言推断

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dataset import SemanticDataset
from app.models.datasource import Datasource

logger = logging.getLogger(__name__)


def resolve_dialect(db: Optional[Session], dataset_id: Optional[int]) -> str:
    """根据 dataset_id 查 Datasource.db_type 推断目标方言。
    返回小写：postgres / mysql / oracle / sqlite；找不到时回退 postgres。"""
    if not db or not dataset_id:
        return "postgres"
    try:
        ds = db.get(SemanticDataset, dataset_id)
        if not ds:
            return "postgres"
        datasource = db.get(Datasource, ds.datasource_id)
        if not datasource:
            return "postgres"
        return (datasource.db_type or "postgres").lower()
    except Exception as e:
        logger.warning(f"推断方言失败，回退 postgres: {e}")
        return "postgres"


def quote_ident(name: Optional[str], dialect: str) -> str:
    """按方言为 identifier 加引号。
    - postgres / oracle: 双引号 "name"
    - mysql / sqlite: 反引号 `name`
    - name 为空 / None 时返回空串（调用方自行决定是否输出 AS）。"""
    if not name:
        return ""
    if dialect in ("mysql", "sqlite"):
        return f"`{name}`"
    return f'"{name}"'


# `xxx != null` / `xxx <> null` → `xxx IS NOT NULL`
# `xxx = null`  / `xxx == null` → `xxx IS NULL`
# 顺序：先吃 != / <>，再吃 = / ==（避免前一步吃掉后一步想匹配的 token）
_NULL_OP_RE_IS_NOT = re.compile(r"(\b\w+(?:\.\w+)?)\s*(?:!=|<>)\s*null\b", re.IGNORECASE)
_NULL_OP_RE_IS = re.compile(r"(\b\w+(?:\.\w+)?)\s*(?:==|=)\s*null\b", re.IGNORECASE)


def sanitize_filter_sql(s: Optional[str]) -> Optional[str]:
    """把 filter_sql 里的 Python 风格 null 比较替换为标准 SQL。
    避免 LLM 在 row-level filter 中直接写 `finsh_time != null` 这种非标语法。"""
    if not s:
        return s
    s = _NULL_OP_RE_IS_NOT.sub(r"\1 IS NOT NULL", s)
    s = _NULL_OP_RE_IS.sub(r"\1 IS NULL", s)
    return s


# 只读 SQL 危险关键字黑名单（DSL 编译器和 direct_sql 路径共用）
FORBIDDEN_SQL_KEYWORDS = [
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "grant",
    "truncate",
]


def contains_forbidden_keyword(sql: str) -> Optional[str]:
    """扫描 SQL 是否包含危险关键字；命中则返回关键字（小写），否则 None。"""
    if not sql:
        return None
    sql_lower = sql.lower()
    for kw in FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_lower):
            return kw
    return None
