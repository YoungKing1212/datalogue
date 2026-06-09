# DSL 生成节点 Prompt（含四条路径）


def build_real_schema_system(query_rules: str = "") -> str:
    """路径 2：真实数据源 Schema，直接生成 SQL。"""
    return (
        "你是一个 SQL 生成专家。根据用户问题和你提供的真实表结构，"
        "生成可执行的 SELECT 语句（仅输出 JSON，不要其他说明）：\n\n"
        '  {"sql": "SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT ..."}\n\n'
        "规则：\n"
        "1. 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE 等操作\n"
        "2. 严格使用真实表结构中的表名和列名\n"
        f"{query_rules}"
    )


def build_inferred_system(query_rules: str = "") -> str:
    """路径 1 推断分支：指标未在语义层定义，基于表结构推断 SQL。"""
    return (
        "你是一个 SQL 生成专家。用户的问题中涉及的数据指标未在语义层中定义，"
        "请根据用户问题和以下表结构自由推断合适的字段和聚合方式，"
        "生成可执行的 SELECT 语句（仅输出 JSON，不要其他说明）：\n\n"
        '  {"sql": "SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT ..."}\n\n'
        "规则：\n"
        "1. 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE 等操作\n"
        "2. 严格使用表结构中的表名和列名\n"
        f"{query_rules}"
    )


def build_semantic_system(
    dsl_limit_example: str,
    semantic_time_rule: str,
    semantic_limit_rule: str,
) -> str:
    """路径 1 确定性分支：指标在语义层中有定义，生成 NL2DSL v2 JSON。"""
    return (
        "你是一个数据查询 DSL 生成专家。根据用户问题和提供的语义层信息，"
        "生成符合 NL2DSL v2 JSON Schema 的 DSL 对象（仅输出 JSON，不要其他说明）：\n\n"
        "{\n"
        '  "version": "2.0",\n'
        '  "metrics": [{"name": "指标英文名，必须在语义层列表中", "asset_type": "metric", "asset_id": 1, "confidence": 0.0}],\n'
        '  "dimensions": [{"name": "维度英文名，可选", "asset_type": "dimension", "asset_id": 1, "confidence": 0.0}],\n'
        '  "terms": [{"name": "业务术语英文名，可选", "asset_type": "term", "asset_id": 1, "confidence": 0.0}],\n'
        '  "blueprints": [{"name": "分析蓝图名称，可选", "asset_type": "blueprint", "asset_id": 1, "confidence": 0.0}],\n'
        '  "filters": [{"field": {"name": "字段或维度名", "asset_type": "dimension|field|column", "asset_id": 1, "confidence": 0.0}, "op": "eq|in|gt|gte|lt|lte|neq|between", "values": []}],\n'
        '  "time_range": {"field": "时间字段", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},\n'
        '  "order_by": [{"field": {"name": "指标或维度名", "asset_type": "metric|dimension|field", "asset_id": 1}, "direction": "ASC|DESC"}],\n'
        f'  "limit": {dsl_limit_example},\n'
        '  "confidence": 0.0,\n'
        '  "ambiguities": [{"text": "原始歧义词", "reason": "歧义原因", "candidates": [{"name": "候选资产", "asset_type": "metric", "asset_id": 1, "confidence": 0.0}], "resolution_hint": "需要用户确认的问题"}]\n'
        "}\n\n"
        "规则：\n"
        "1. metrics 和 dimensions 的值必须严格来自语义层定义的 name\n"
        "2. 已识别实体解析和可引用语义资产中给出了用户词到语义层 name / asset_id 的映射，请严格使用解析后的名称和 ID\n"
        f"{semantic_time_rule}"
        "4. 若用户要求排序，加入 order_by\n"
        f"{semantic_limit_rule}"
        "6. time_range.field 必须使用所选指标在语义层中声明的 time_field，不要从 DDL 自由发挥\n"
        "7. asset_id 必须来自可引用语义资产；找不到 ID 时填 null，不要编造\n"
        "8. 如果一个词可能对应多个资产，把候选写入 ambiguities，不要丢失歧义\n"
    )


def build_no_schema_system(query_rules: str = "") -> str:
    """路径 3：完全没有 schema，LLM 猜测 SQL。"""
    return (
        "你是一个 SQL 生成专家。根据用户问题，生成可执行的 SELECT 语句（仅输出 JSON，不要其他说明）：\n\n"
        '  {"sql": "SELECT ..."}\n\n'
        "规则：\n"
        "1. 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP 等\n"
        f"{query_rules}"
    )
