# LangGraph 工作流节点实现 — NL2DSL2SQL 核心链路

import json
import re
from typing import Dict, Any

from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage

from app.graph.llm import get_llm
from app.graph.state import AgentState
from app.models.dataset import SemanticDataset, SemanticMetric, SemanticDimension
from app.models.datasource import Datasource
from app.services.datasource import create_engine_for_datasource

# ── 工具函数 ─────────────────────────────────────────


def _safe_json_parse(text: str) -> dict:
    """从 LLM 输出中提取 JSON 块并安全解析。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        m2 = re.search(r"\{.*\}", text, re.DOTALL)
        if m2:
            text = m2.group(0)
    try:
        result: dict[str, Any] = json.loads(text.strip())
        return result
    except json.JSONDecodeError:
        return {}


def _extract_token_usage(response) -> dict:
    """从 LangChain AIMessage 中提取 Token 用量。"""
    usage = response.usage_metadata or {}
    prompt = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
    completion = usage.get("output_tokens") or usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _merge_token_usage(current: dict, new_usage: dict) -> dict:
    """合并两轮 Token 用量。"""
    if not current:
        current = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": current.get("prompt_tokens", 0) + new_usage.get("prompt_tokens", 0),
        "completion_tokens": current.get("completion_tokens", 0)
        + new_usage.get("completion_tokens", 0),
        "total_tokens": current.get("total_tokens", 0) + new_usage.get("total_tokens", 0),
    }


def _build_schema_prompt(dataset: SemanticDataset, metrics: list, dimensions: list) -> str:
    """将语义层信息拼接为供 LLM 阅读的 schema 上下文。"""
    import json as _json

    lines = [f"数据集: {dataset.name}", f"描述: {dataset.description or '无'}", ""]
    # 注入 tables_json 供编译器解析真实表名
    if dataset.tables_json:
        lines.append(f"tables_json: {_json.dumps(dataset.tables_json, ensure_ascii=False)}")
        lines.append("")
    lines.append("【指标列表】")
    for m in metrics:
        synonyms = ", ".join(m.synonyms or [])
        lines.append(
            f"- {m.name} ({m.display_name}): 表达式={m.expr}"
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


# ── 节点 1: 意图识别 ──────────────────────────────────


def intent_recognition_node(state: AgentState) -> Dict[str, Any]:
    """识别用户意图，判断是数据查询、闲聊还是功能操作。"""
    question = state["question"]
    history = state.get("history", [])
    llm = get_llm(temperature=0.0)

    system = SystemMessage(
        content=(
            "你是一个意图识别助手。请分析用户输入，输出 JSON：\n"
            '{"intent": "query|chitchat|function", '
            '"entities": {"metrics": [], "dimensions": [], "time_range": null}, '
            '"direct_answer": null}\n'
            "规则：\n"
            "- query: 涉及数据查询、统计、对比、趋势等\n"
            "- chitchat: 问候、闲聊、无关问题\n"
            "- function: 保存、发布、导出等操作指令\n"
            "- 如果是 chitchat，direct_answer 中填入礼貌回复\n"
        )
    )

    human_text = question
    if history and len(history) > 1:
        recent = history[-6:-1] if len(history) > 6 else history[:-1]
        ctx = "\n".join(
            [f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:100]}" for m in recent]
        )
        human_text = f"【历史上下文】\n{ctx}\n\n【当前问题】\n{question}"

    human = HumanMessage(content=human_text)
    response = llm.invoke([system, human])
    result = _safe_json_parse(str(response.content))

    intent = result.get("intent", "query")
    entities = result.get("entities", {})
    direct_answer = result.get("direct_answer")

    answer = direct_answer if intent == "chitchat" else None
    usage = _extract_token_usage(response)
    current_usage = state.get("token_usage") or {}
    merged = _merge_token_usage(current_usage, usage)

    return {
        "intent": intent,
        "entities": entities,
        "answer": answer,
        "token_usage": merged,
    }


# ── 节点 2: Schema 召回（可选）──────────────────────────


def schema_recall_node(db: Session):
    """根据 dataset_id 召回语义层信息，注入 LLM prompt。
    - 有 dataset_id + 语义层存在 → 构建【语义层】上下文
    - 无 dataset_id → 从已连接数据源拉真实表结构 → 【数据源真实表结构】
    """

    def _node(state: AgentState) -> Dict[str, Any]:
        dataset_id = state.get("dataset_id")
        if not dataset_id:
            datasource = db.query(Datasource).filter(Datasource.status == "connected").first()
            if datasource:
                try:
                    from app.services.datasource import get_schema as fetch_schema

                    real_tables = fetch_schema(datasource)
                    lines = ["【数据源真实表结构】", ""]
                    for t in real_tables[:20]:
                        cols = ", ".join(
                            [f"{c['name']} ({c['type']})" for c in t.get("columns", [])]
                        )
                        lines.append(f"表: {t['name']} | 列: {cols}")
                    if len(lines) == 2:
                        lines.append("（数据源无可用表）")
                    return {"schema_context": "\n".join(lines), "dataset_id": None}
                except Exception as e:
                    return {"schema_context": f"无法读取数据源 Schema: {e}", "dataset_id": None}
            else:
                return {"schema_context": "", "dataset_id": None}

        ds = db.get(SemanticDataset, dataset_id)
        if not ds:
            return {"schema_context": "", "dataset_id": None}

        metrics = db.query(SemanticMetric).filter(SemanticMetric.dataset_id == ds.id).all()
        dimensions = db.query(SemanticDimension).filter(SemanticDimension.dataset_id == ds.id).all()
        context = "【语义层】\n" + _build_schema_prompt(ds, metrics, dimensions)
        return {"schema_context": context, "dataset_id": ds.id}

    return _node


# ── 节点 3: DSL / SQL 生成 ──────────────────────────────────


def dsl_generate_node(state: AgentState) -> Dict[str, Any]:
    """三条路径：
    1. 【语义层】→ LLM 生成结构化 DSL JSON
    2. 【数据源真实表结构】→ LLM 直接生成 SQL
    3. 完全没有 schema → LLM 猜 SQL
    """
    question = state["question"]
    schema = state.get("schema_context", "")
    entities = state.get("entities", {})
    retry_count = state.get("retry_count", 0)
    error = state.get("error")

    llm = get_llm(temperature=0.1)

    has_semantic = bool(schema and "【语义层】" in schema)
    has_real_schema = bool(schema and "【数据源真实表结构】" in schema)

    # ── 路径 2: 真实数据源 Schema，直接生成 SQL ──
    if has_real_schema:
        system = SystemMessage(
            content=(
                "你是一个 SQL 生成专家。根据用户问题和你提供的真实表结构，"
                "生成可执行的 SELECT 语句（仅输出 JSON，不要其他说明）：\n\n"
                '  {"sql": "SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT ..."}\n\n'
                "规则：\n"
                "1. 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE 等操作\n"
                "2. 严格使用真实表结构中的表名和列名\n"
                "3. limit 默认 100，最大 1000\n"
            )
        )
        human_text = f"用户问题: {question}\n\n真实表结构:\n{schema}"
        if error:
            human_text += f"\n\n上一轮错误: {error}"
        human = HumanMessage(content=human_text)
        response = llm.invoke([system, human])
        result = _safe_json_parse(str(response.content))
        sql = result.get("sql", "")
        usage = _extract_token_usage(response)
        merged = _merge_token_usage(state.get("token_usage") or {}, usage)
        if sql:
            return {
                "dsl": {"direct_sql": sql},
                "sql": sql,
                "sql_list": [sql],
                "error": None,
                "token_usage": merged,
            }
        return {
            "dsl": {},
            "sql": None,
            "sql_list": [],
            "error": "LLM 未生成有效 SQL",
            "should_retry": True,
            "token_usage": merged,
        }

    # ── 路径 1: 语义层 DSL ──
    if has_semantic:
        system = SystemMessage(
            content=(
                "你是一个数据查询 DSL 生成专家。根据用户问题和提供的语义层信息，"
                "生成符合以下 JSON Schema 的 DSL 对象（仅输出 JSON，不要其他说明）：\n\n"
                "{\n"
                '  "metrics": ["指标英文名，必须在语义层列表中"],\n'
                '  "dimensions": ["维度英文名，可选"],\n'
                '  "filters": [{"field": "字段名", "op": "eq|in|gt|lt|between", "values": []}],\n'
                '  "time_range": {"field": "时间字段", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},\n'
                '  "order_by": [{"field": "字段", "direction": "ASC|DESC"}],\n'
                '  "limit": 100\n'
                "}\n\n"
                "规则：\n"
                "1. metrics 和 dimensions 的值必须严格来自语义层定义的 name\n"
                "2. 时间范围尽量推断，默认近30天\n"
                "3. 若用户要求排序，加入 order_by\n"
                "4. limit 默认 100，最大 1000\n"
            )
        )
        human_text = f"用户问题: {question}\n\n语义层信息:\n{schema}"
        if entities:
            human_text += f"\n\n已识别实体: {json.dumps(entities, ensure_ascii=False)}"
        if error:
            human_text += f"\n\n上一轮错误（请修正）: {error}"
        human = HumanMessage(content=human_text)
        response = llm.invoke([system, human])
        dsl = _safe_json_parse(str(response.content))
        usage = _extract_token_usage(response)
        merged = _merge_token_usage(state.get("token_usage") or {}, usage)
        return {
            "dsl": dsl,
            "retry_count": retry_count,
            "should_retry": False,
            "error": None,
            "token_usage": merged,
        }

    # ── 路径 3: 完全没有 schema，LLM 猜 SQL ──
    system = SystemMessage(
        content=(
            "你是一个 SQL 生成专家。根据用户问题，生成可执行的 SELECT 语句（仅输出 JSON，不要其他说明）：\n\n"
            '  {"sql": "SELECT ..."}\n\n'
            "规则：\n"
            "1. 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP 等\n"
            "2. limit 默认 100\n"
        )
    )
    human_text = f"用户问题: {question}"
    if error:
        human_text += f"\n\n上一轮错误: {error}"
    human = HumanMessage(content=human_text)
    response = llm.invoke([system, human])
    result = _safe_json_parse(str(response.content))
    sql = result.get("sql", "")
    usage = _extract_token_usage(response)
    merged = _merge_token_usage(state.get("token_usage") or {}, usage)
    if sql:
        return {
            "dsl": {"direct_sql": sql},
            "sql": sql,
            "sql_list": [sql],
            "error": None,
            "token_usage": merged,
        }
    return {
        "dsl": {},
        "sql": None,
        "sql_list": [],
        "error": "LLM 未生成有效 SQL",
        "should_retry": True,
        "token_usage": merged,
    }


# ── 节点 4: DSL 校验 ──────────────────────────────────


def _extract_names_from_schema(schema: str) -> set:
    """从语义层 schema_context 文本中提取所有指标名和维度名。"""
    names = set()
    for line in schema.split("\n"):
        m = re.match(r"-\s+(\w+)\s+\([^)]+\):", line)
        if m:
            names.add(m.group(1))
    return names


def dsl_validate_node(state: AgentState) -> Dict[str, Any]:
    """代码层强校验。"""
    dsl = state.get("dsl") or {}
    schema = state.get("schema_context") or ""

    # direct_sql 模式（真实 Schema 或无 Schema 路径）
    if "direct_sql" in dsl:
        sql = dsl.get("direct_sql", "")
        if not sql:
            return {"dsl_valid": False, "error": "LLM 未生成有效 SQL", "should_retry": True}
        return {"dsl_valid": True, "error": None, "should_retry": False}

    # 真实数据源 Schema 模式：直接看 sql 字段
    if schema and "【数据源真实表结构】" in schema:
        sql = dsl.get("sql") or ""
        if not sql:
            return {"dsl_valid": False, "error": "LLM 未生成有效 SQL", "should_retry": True}
        return {"dsl_valid": True, "error": None, "should_retry": False}

    # 语义层 DSL 模式
    if not dsl or not isinstance(dsl, dict):
        return {"dsl_valid": False, "error": "DSL 为空或格式错误", "should_retry": True}

    valid_names = _extract_names_from_schema(schema)
    errors = []
    metrics = dsl.get("metrics", [])
    if not metrics:
        errors.append("metrics 不能为空")
    for m in metrics:
        if m not in valid_names:
            errors.append(f"指标 '{m}' 不在语义层定义中")
    for d in dsl.get("dimensions", []):
        if d not in valid_names:
            errors.append(f"维度 '{d}' 不在语义层定义中")
    for f in dsl.get("filters", []):
        field = f.get("field")
        if field and field not in valid_names:
            errors.append(f"过滤字段 '{field}' 不在语义层定义中")

    if errors:
        return {"dsl_valid": False, "error": "; ".join(errors), "should_retry": True}
    return {"dsl_valid": True, "error": None, "should_retry": False}


# ── 节点 5: DSL 编译器（代码实现）─────────────────────────


def dsl_compiler_node(state: AgentState) -> Dict[str, Any]:
    """将 DSL JSON 翻译为可执行 SQL。"""
    dsl = state.get("dsl") or {}
    schema = state.get("schema_context") or ""

    # direct_sql 模式
    if "direct_sql" in dsl:
        sql = dsl.get("direct_sql", "")
        if not sql:
            return {"sql": None, "error": "未生成有效 SQL"}
        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant", "truncate"]
        sql_lower = sql.lower()
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", sql_lower):
                return {"sql": None, "error": f"SQL 包含危险关键字 '{kw}'，已拦截"}
        return {"sql": sql, "sql_list": [sql], "error": None}

    # 真实数据源 Schema 模式
    if schema and "【数据源真实表结构】" in schema:
        sql = dsl.get("sql") or ""
        if not sql:
            return {"sql": None, "error": "未生成有效 SQL"}
        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant", "truncate"]
        sql_lower = sql.lower()
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", sql_lower):
                return {"sql": None, "error": f"SQL 包含危险关键字 '{kw}'，已拦截"}
        return {"sql": sql, "sql_list": [sql], "error": None}

    if not dsl:
        return {"sql": None, "error": "DSL 为空，无法编译"}

    metric_exprs = {}
    for line in schema.split("\n"):
        m = re.match(r"-\s+(\w+)\s+\([^)]+\):\s+表达式=(.+?)(?:\s+同义词=|\s+过滤=|$)", line)
        if m:
            metric_exprs[m.group(1)] = m.group(2).strip()

    selects = []
    for m in dsl.get("metrics", []):
        expr = metric_exprs.get(m, m)
        selects.append(f"{expr} AS {m}")
    for d in dsl.get("dimensions", []):
        selects.append(d)

    # 从语义层解析表名：优先从 tables_json 中提取，其次从数据集名称推断
    table = "orders"  # 默认兜底
    table_alias = None
    table_match = re.search(r"数据集:\s*(.+)", schema)
    dataset_name = table_match.group(1).strip() if table_match else None

    # 尝试从 schema 中解析 tables_json 里的主表名
    # tables_json 格式: {"tables": [{"name": "orders", "alias": "o"}], "joins": [...]}
    # 注意：使用贪婪匹配 .* 而非 .*?，因为 JSON 内部可能包含嵌套的大括号
    tables_json_match = re.search(r"tables_json[:=]\s*(\{.*\})", schema, re.DOTALL)
    if tables_json_match:
        try:
            tables_json = json.loads(tables_json_match.group(1))
            tables = tables_json.get("tables", [])
            if tables:
                table = tables[0].get("name", table)
                table_alias = tables[0].get("alias")
        except json.JSONDecodeError:
            pass
    elif dataset_name:
        # 无 tables_json 时，尝试将数据集名转为小写下划线格式作为表名
        table = re.sub(r"[^\w]", "_", dataset_name).lower()

    # 构建 FROM 子句：如果有表别名则使用 alias
    from_clause = f"{table} AS {table_alias}" if table_alias else table
    sql_parts = [f"SELECT {', '.join(selects)} FROM {from_clause}"]

    wheres = []
    for f in dsl.get("filters", []):
        field = f["field"]
        op = f["op"]
        vals = f.get("values", [])
        if op == "in" and vals:
            in_list = ", ".join(["'" + str(v) + "'" for v in vals])
            wheres.append(f"{field} IN ({in_list})")
        elif op == "eq" and vals:
            wheres.append(f"{field} = '{vals[0]}'")
        elif op == "gt" and vals:
            wheres.append(f"{field} > '{vals[0]}'")
        elif op == "lt" and vals:
            wheres.append(f"{field} < '{vals[0]}'")
        elif op == "between" and len(vals) >= 2:
            wheres.append(f"{field} BETWEEN '{vals[0]}' AND '{vals[1]}'")

    tr = dsl.get("time_range")
    if tr and tr.get("field"):
        if tr.get("start"):
            wheres.append(f"{tr['field']} >= '{tr['start']}'")
        if tr.get("end"):
            wheres.append(f"{tr['field']} <= '{tr['end']}'")

    if wheres:
        sql_parts.append("WHERE " + " AND ".join(wheres))

    dims = dsl.get("dimensions", [])
    if dims:
        sql_parts.append(f"GROUP BY {', '.join(dims)}")

    ob = dsl.get("order_by", [])
    if ob:
        orders = [f"{o['field']} {o['direction']}" for o in ob]
        sql_parts.append(f"ORDER BY {', '.join(orders)}")

    limit = dsl.get("limit", 100)
    sql_parts.append(f"LIMIT {limit}")
    sql = "\n".join(sql_parts)

    forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant"]
    sql_lower = sql.lower()
    for kw in forbidden:
        if re.search(rf"\b{kw}\b", sql_lower):
            return {"sql": None, "error": f"SQL 包含危险关键字 '{kw}'，已拦截"}

    return {"sql": sql, "sql_list": [sql], "error": None}


# ── 节点 6: SQL 执行 ──────────────────────────────────


def sql_execute_node(db: Session):
    """执行 SQL 查询（只读），连接真实数据源返回结果集。"""

    def _node(state: AgentState) -> Dict[str, Any]:
        sql = state.get("sql")
        if not sql:
            return {"sql_result": None, "error": "SQL 为空", "should_retry": True}

        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant", "truncate"]
        sql_lower = sql.lower()
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", sql_lower):
                return {
                    "sql_result": None,
                    "error": f"SQL 包含危险关键字 '{kw}'，已拦截",
                    "should_retry": False,
                }

        dataset_id = state.get("dataset_id")
        datasource = None
        if dataset_id:
            dataset = db.get(SemanticDataset, dataset_id)
            if dataset:
                datasource = db.get(Datasource, dataset.datasource_id)

        if not datasource:
            datasource = db.query(Datasource).filter(Datasource.status == "connected").first()

        if not datasource:
            return {
                "sql_result": None,
                "error": "无可用数据源，请先在数据源管理中测试连接",
                "should_retry": False,
            }

        engine = create_engine_for_datasource(datasource)
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                result_proxy = conn.execute(text(sql))
                columns = list(result_proxy.keys())
                rows = []
                for row in result_proxy:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if hasattr(val, "isoformat"):
                            row_dict[col] = val.isoformat()
                        else:
                            row_dict[col] = val
                    rows.append(row_dict)
                result = {"columns": columns, "rows": rows, "row_count": len(rows)}
                return {"sql_result": result, "error": None, "should_retry": False}
        except Exception as e:
            return {"sql_result": None, "error": f"SQL 执行失败: {str(e)}", "should_retry": True}
        finally:
            engine.dispose()

    return _node


# ── 节点 7: 报告生成 ──────────────────────────────────


def report_generator_node(state: AgentState) -> Dict[str, Any]:
    """根据 SQL 结果生成自然语言回答和图表推荐。"""
    question = state["question"]
    sql_result = state.get("sql_result")

    if not sql_result:
        return {"answer": "查询未返回结果，请检查语义层配置。"}

    rows = sql_result.get("rows", [])
    sql_result.get("columns", [])

    summary_lines = [f"查询结果共 {len(rows)} 行："]
    for row in rows:
        parts = [f"{k}={v}" for k, v in row.items()]
        summary_lines.append("  " + ", ".join(parts))

    result_text = "\n".join(summary_lines)

    llm = get_llm(temperature=0.3)
    system = SystemMessage(
        content=(
            "你是一个数据分析师。请根据用户问题和 SQL 查询结果，"
            "用中文总结数据洞察，直接回答用户问题。"
            "回复格式要求：\n"
            "1. 使用 **加粗** 强调关键数字和结论（必须用 Markdown 的 ** 语法）\n"
            "2. 使用列表或分段呈现多维度分析\n"
            "3. 不要解释 SQL，只需给出业务结论\n"
            "示例：本周 GMV 为 **123万元**，环比增长 **15%**，其中华南地区贡献最大。"
        )
    )
    human = HumanMessage(content=f"用户问题: {question}\n\n查询结果:\n{result_text}")
    response = llm.invoke([system, human])
    answer = str(response.content).strip()
    usage = _extract_token_usage(response)
    current_usage = state.get("token_usage") or {}
    merged = _merge_token_usage(current_usage, usage)

    return {"answer": answer, "token_usage": merged}
