# LangGraph 工作流节点实现 — NL2DSL2SQL 核心链路

import json
import re
from decimal import Decimal
from typing import Dict, Any

import logging
from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage

from app.graph.llm import get_llm
from app.graph.state import AgentState
from app.models.dataset import SemanticDataset, SemanticMetric, SemanticDimension, DatasetSourceTable, SourceTable, SourceColumn
from app.models.datasource import Datasource
from app.services.datasource import create_engine_for_datasource

logger = logging.getLogger(__name__)

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
    logger.info(f"意图识别节点开始: question={question[:50]}...")
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
    logger.info(f"意图识别结果: intent={intent}")
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
    - 有 dataset_id + 语义层存在 → 构建【语义层】上下文 + 结构化对象
    - 无 dataset_id → 从已连接数据源拉真实表结构 → 【数据源真实表结构】
    """

    def _node(state: AgentState) -> Dict[str, Any]:
        dataset_id = state.get("dataset_id")
        logger.info(f"Schema召回节点开始: dataset_id={dataset_id}")
        if not dataset_id:
            datasource = db.query(Datasource).filter(Datasource.status == "connected").first()
            if datasource:
                logger.info(f"未提供dataset_id，从数据源获取真实表结构: datasource_id={datasource.id}")
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
                    return {"schema_context": "\n".join(lines), "dataset_id": None, "schema_structured": None, "ddl_context": None}
                except Exception as e:
                    logger.error(f"读取数据源Schema失败: {e}")
                    return {"schema_context": f"无法读取数据源 Schema: {e}", "dataset_id": None, "schema_structured": None, "ddl_context": None}
            else:
                return {"schema_context": "", "dataset_id": None, "schema_structured": None, "ddl_context": None}

        ds = db.get(SemanticDataset, dataset_id)
        if not ds:
            logger.warning(f"数据集不存在: dataset_id={dataset_id}")
            return {"schema_context": "", "dataset_id": None, "schema_structured": None, "ddl_context": None}

        metrics = db.query(SemanticMetric).filter(SemanticMetric.dataset_id == ds.id).all()
        dimensions = db.query(SemanticDimension).filter(SemanticDimension.dataset_id == ds.id).all()
        logger.info(f"使用语义层Schema: dataset={ds.name}, metrics={len(metrics)}, dimensions={len(dimensions)}")
        context = "【语义层】\n" + _build_schema_prompt(ds, metrics, dimensions)

        # 构建结构化对象供编译器直接使用，避免正则解析
        structured = {
            "dataset_name": ds.name,
            "tables_json": ds.tables_json or {},
            "metrics": [
                {
                    "name": m.name,
                    "display_name": m.display_name,
                    "expr": m.expr,
                    "table_name": m.table_name,
                    "time_field": m.time_field,
                    "filter_sql": m.filter_sql,
                    "synonyms": m.synonyms or [],
                }
                for m in metrics
            ],
            "dimensions": [
                {
                    "name": d.name,
                    "display_name": d.display_name,
                    "column_name": d.column_name,
                    "table_name": d.table_name,
                    "join_to": d.join_to,
                    "join_key": d.join_key,
                    "synonyms": d.synonyms or [],
                }
                for d in dimensions
            ],
        }

        # 构建所选表的真实 DDL（用于推断路径）
        ddl_lines = ["【所选表结构】", ""]
        selected_links = db.query(DatasetSourceTable).filter(DatasetSourceTable.dataset_id == ds.id).all()
        selected_table_ids = [link.source_table_id for link in selected_links]
        if selected_table_ids:
            tables = db.query(SourceTable).filter(SourceTable.id.in_(selected_table_ids)).all()
            for t in tables:
                ddl_lines.append(f"表: {t.table_name}")
                if t.table_comment:
                    ddl_lines.append(f"  描述: {t.table_comment}")
                if t.business_desc:
                    ddl_lines.append(f"  业务描述: {t.business_desc}")
                cols = db.query(SourceColumn).filter(SourceColumn.table_id == t.id).order_by(SourceColumn.ordinal_position).all()
                for c in cols:
                    col_desc = f"  - {c.column_name} ({c.data_type})"
                    if c.column_comment:
                        col_desc += f" 注释={c.column_comment}"
                    if c.business_desc:
                        col_desc += f" 业务描述={c.business_desc}"
                    if c.semantic_role:
                        col_desc += f" 角色={c.semantic_role}"
                    if c.default_agg:
                        col_desc += f" 默认聚合={c.default_agg}"
                    ddl_lines.append(col_desc)
                ddl_lines.append("")
        else:
            ddl_lines.append("（该数据集尚未选择任何表）")
        ddl_context = "\n".join(ddl_lines)

        return {"schema_context": context, "dataset_id": ds.id, "schema_structured": structured, "ddl_context": ddl_context}

    return _node


# ── 节点 2.5: 指标/维度解析（Metric Resolution）────────────────


def metric_resolution_node(state: AgentState) -> Dict[str, Any]:
    """将用户意图中提取的实体与语义层定义进行匹配解析。
    输出每个 metric/dimension 的匹配详情，供意图卡、审计日志和 dsl_generate 使用。
    """
    entities = state.get("entities", {})
    structured = state.get("schema_structured")
    logger.info("metric_resolution 开始解析实体")

    # 构建语义层名称索引：原始词 -> 定义对象
    metric_map: dict[str, dict] = {}
    dim_map: dict[str, dict] = {}

    if structured:
        for m in structured.get("metrics", []):
            metric_map[m["name"]] = m
            if m.get("display_name"):
                metric_map[m["display_name"]] = m
            for syn in m.get("synonyms", []):
                metric_map[syn] = m
        for d in structured.get("dimensions", []):
            dim_map[d["name"]] = d
            if d.get("display_name"):
                dim_map[d["display_name"]] = d
            for syn in d.get("synonyms", []):
                dim_map[syn] = d

    def _resolve(entity: str, lookup_map: dict) -> dict:
        matched = lookup_map.get(entity)
        if not matched:
            return {"entity": entity, "resolved": None, "status": "unresolved", "match_type": None}
        if entity == matched["name"]:
            match_type = "exact"
        elif entity == matched.get("display_name"):
            match_type = "display_name"
        else:
            match_type = "synonym"
        return {"entity": entity, "resolved": matched["name"], "status": "matched", "match_type": match_type}

    resolved_metrics = [_resolve(em, metric_map) for em in (entities.get("metrics") or []) if em]
    resolved_dimensions = [_resolve(ed, dim_map) for ed in (entities.get("dimensions") or []) if ed]

    all_matched = all(r["status"] == "matched" for r in resolved_metrics)
    unresolved = [r["entity"] for r in resolved_metrics if r["status"] == "unresolved"]

    logger.info(f"metric_resolution 完成: metrics={len(resolved_metrics)}, all_matched={all_matched}, unresolved={unresolved}")

    return {
        "metric_resolution": {
            "metrics": resolved_metrics,
            "dimensions": resolved_dimensions,
            "all_matched": all_matched,
            "unresolved": unresolved,
        }
    }


# ── 节点 3: DSL / SQL 生成 ──────────────────────────────────


def dsl_generate_node(state: AgentState) -> Dict[str, Any]:
    """三条路径：
    1. 【语义层】→ LLM 生成结构化 DSL JSON
    2. 【数据源真实表结构】→ LLM 直接生成 SQL
    3. 完全没有 schema → LLM 猜 SQL
    """
    question = state["question"]
    logger.info(f"DSL生成节点开始: question={question[:50]}...")
    schema = state.get("schema_context", "")
    entities = state.get("entities", {})
    retry_count = state.get("retry_count", 0)
    error = state.get("error")

    llm = get_llm(temperature=0.1)

    has_semantic = bool(schema and "【语义层】" in schema)
    has_real_schema = bool(schema and "【数据源真实表结构】" in schema)
    logger.info(f"DSL生成路径判断: has_semantic={has_semantic}, has_real_schema={has_real_schema}")

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
            logger.info("真实Schema路径: SQL生成成功")
            return {
                "dsl": {"direct_sql": sql},
                "sql": sql,
                "sql_list": [sql],
                "error": None,
                "token_usage": merged,
            }
        logger.warning("真实Schema路径: LLM未生成有效SQL")
        return {
            "dsl": {},
            "sql": None,
            "sql_list": [],
            "error": "LLM 未生成有效 SQL",
            "should_retry": True,
            "token_usage": merged,
        }

    # ── 路径 1: 语义层 DSL（确定性路径 / 推断路径）──
    if has_semantic:
        structured = state.get("schema_structured")
        ddl_context = state.get("ddl_context", "")
        metric_resolution = state.get("metric_resolution") or {}
        all_matched = metric_resolution.get("all_matched", True)
        unresolved = metric_resolution.get("unresolved", [])

        # 推断路径：指标未在语义层中定义，基于表结构让 LLM 直接生成 SQL
        if not all_matched and ddl_context:
            logger.info(f"走推断路径: 未解析指标={unresolved}")
            # 如果数据集没有选择任何表，直接报错，不让 LLM 瞎猜
            if "该数据集尚未选择任何表" in ddl_context:
                return {
                    "dsl": {},
                    "sql": None,
                    "sql_list": [],
                    "generation_mode": "inferred",
                    "error": "该数据集尚未选择任何数据源表，请先在数据集配置中勾选表后再提问。",
                    "should_retry": False,
                    "token_usage": state.get("token_usage"),
                }

            system = SystemMessage(
                content=(
                    "你是一个 SQL 生成专家。用户的问题中涉及的数据指标未在语义层中定义，"
                    "请根据用户问题和以下表结构自由推断合适的字段和聚合方式，"
                    "生成可执行的 SELECT 语句（仅输出 JSON，不要其他说明）：\n\n"
                    '  {"sql": "SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT ..."}\n\n'
                    "规则：\n"
                    "1. 只生成 SELECT，禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE 等操作\n"
                    "2. 严格使用表结构中的表名和列名\n"
                    "3. limit 默认 100，最大 1000\n"
                    "4. 如果用户没有告诉具体的时间范围，时间范围尽量推断，默认近30天\n"
                )
            )
            human_text = f"用户问题: {question}\n\n表结构:\n{ddl_context}"
            if entities:
                human_text += f"\n\n已识别实体: {json.dumps(entities, ensure_ascii=False)}"
            if error:
                human_text += f"\n\n上一轮错误（请修正）: {error}"
            human = HumanMessage(content=human_text)
            response = llm.invoke([system, human])
            result = _safe_json_parse(str(response.content))
            sql = result.get("sql", "")
            usage = _extract_token_usage(response)
            merged = _merge_token_usage(state.get("token_usage") or {}, usage)
            if sql:
                logger.info("推断路径: SQL生成成功")
                return {
                    "dsl": {"direct_sql": sql, "inferred": True},
                    "sql": sql,
                    "sql_list": [sql],
                    "generation_mode": "inferred",
                    "error": None,
                    "token_usage": merged,
                }
            logger.warning("推断路径: LLM未生成有效SQL")
            return {
                "dsl": {},
                "sql": None,
                "sql_list": [],
                "generation_mode": "inferred",
                "error": "LLM 未生成有效 SQL",
                "should_retry": True,
                "token_usage": merged,
            }

        # 确定性路径：指标在语义层中有定义
        logger.info("走确定性路径: 指标全部匹配语义层")

        # 构建 metric_resolution 的提示文本，告诉 LLM 每个实体对应语义层中的哪个 name
        resolution_text = ""
        if metric_resolution:
            res_lines = ["已识别实体解析:"]
            for r in metric_resolution.get("metrics", []):
                if r["status"] == "matched":
                    res_lines.append(f"- 指标 '{r['entity']}' → 语义层名称 '{r['resolved']}' ({r['match_type']})")
                else:
                    res_lines.append(f"- 指标 '{r['entity']}' → 未在语义层中定义")
            for r in metric_resolution.get("dimensions", []):
                if r["status"] == "matched":
                    res_lines.append(f"- 维度 '{r['entity']}' → 语义层名称 '{r['resolved']}' ({r['match_type']})")
                else:
                    res_lines.append(f"- 维度 '{r['entity']}' → 未在语义层中定义")
            resolution_text = "\n".join(res_lines)

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
                "2. 已识别实体解析中给出了用户词到语义层 name 的映射，请严格使用解析后的名称\n"
                "3. 时间范围尽量推断，默认近30天\n"
                "4. 若用户要求排序，加入 order_by\n"
                "5. limit 默认 100，最大 1000\n"
            )
        )
        human_text = f"用户问题: {question}\n\n语义层信息:\n{schema}"
        if resolution_text:
            human_text += f"\n\n{resolution_text}"
        if entities:
            human_text += f"\n\n原始识别实体: {json.dumps(entities, ensure_ascii=False)}"
        if error:
            human_text += f"\n\n上一轮错误（请修正）: {error}"
        human = HumanMessage(content=human_text)
        response = llm.invoke([system, human])
        dsl = _safe_json_parse(str(response.content))
        usage = _extract_token_usage(response)
        merged = _merge_token_usage(state.get("token_usage") or {}, usage)
        logger.info("确定性路径: DSL生成成功")
        return {
            "dsl": dsl,
            "retry_count": retry_count,
            "should_retry": False,
            "generation_mode": "semantic",
            "error": None,
            "token_usage": merged,
        }

    # ── 路径 3: 完全没有 schema，LLM 猜 SQL ──
    logger.info("走无Schema路径: 让LLM猜测SQL")
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
        logger.info("无Schema路径: SQL生成成功")
        return {
            "dsl": {"direct_sql": sql},
            "sql": sql,
            "sql_list": [sql],
            "error": None,
            "token_usage": merged,
        }
    logger.warning("无Schema路径: LLM未生成有效SQL")
    return {
        "dsl": {},
        "sql": None,
        "sql_list": [],
        "error": "LLM 未生成有效 SQL",
        "should_retry": True,
        "token_usage": merged,
    }


# ── 节点 4: DSL 校验 ──────────────────────────────────


def dsl_validate_node(state: AgentState) -> Dict[str, Any]:
    """代码层强校验。优先使用 schema_structured 进行精确校验。"""
    logger.info("DSL校验节点开始")
    dsl = state.get("dsl") or {}
    schema = state.get("schema_context") or ""
    structured = state.get("schema_structured")

    # direct_sql 模式（真实 Schema 或无 Schema 路径）
    if "direct_sql" in dsl:
        sql = dsl.get("direct_sql", "")
        if not sql:
            return {"dsl_valid": False, "error": "LLM 未生成有效 SQL", "should_retry": True}
        return {"dsl_valid": True, "error": None, "should_retry": False}

    # 真实数据源 Schema 模式
    if schema and "【数据源真实表结构】" in schema:
        sql = dsl.get("sql") or ""
        if not sql:
            return {"dsl_valid": False, "error": "LLM 未生成有效 SQL", "should_retry": True}
        return {"dsl_valid": True, "error": None, "should_retry": False}

    # 语义层 DSL 模式
    if not dsl or not isinstance(dsl, dict):
        return {"dsl_valid": False, "error": "DSL 为空或格式错误", "should_retry": True}

    # 优先从结构化对象中提取有效名称
    if structured:
        valid_names = {m["name"] for m in structured.get("metrics", [])}
        valid_names.update({d["name"] for d in structured.get("dimensions", [])})
    else:
        # fallback: 从文本中提取
        valid_names = set()
        for line in schema.split("\n"):
            m = re.match(r"-\s+(\w+)\s+\([^)]+\):", line)
            if m:
                valid_names.add(m.group(1))

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
        logger.warning(f"DSL校验失败: {'; '.join(errors)}")
        return {"dsl_valid": False, "error": "; ".join(errors), "should_retry": True}
    logger.info("DSL校验通过")
    return {"dsl_valid": True, "error": None, "should_retry": False}


# ── 节点 5: DSL 编译器（代码实现）─────────────────────────


def dsl_compiler_node(state: AgentState) -> Dict[str, Any]:
    """将 DSL JSON 翻译为可执行 SQL。
    优先从 schema_structured 中读取结构化配置，支持 JOIN 和多表查询。"""
    logger.info("DSL编译节点开始")
    dsl = state.get("dsl") or {}
    schema = state.get("schema_context") or ""
    structured = state.get("schema_structured")

    # direct_sql 模式
    if "direct_sql" in dsl:
        sql = dsl.get("direct_sql", "")
        if not sql:
            logger.error("direct_sql模式: SQL为空")
            return {"sql": None, "error": "未生成有效 SQL"}
        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant", "truncate"]
        sql_lower = sql.lower()
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", sql_lower):
                logger.error(f"direct_sql模式: SQL包含危险关键字 '{kw}'")
                return {"sql": None, "error": f"SQL 包含危险关键字 '{kw}'，已拦截"}
        logger.info("direct_sql模式: 编译成功")
        return {"sql": sql, "sql_list": [sql], "error": None}

    # 真实数据源 Schema 模式
    if schema and "【数据源真实表结构】" in schema:
        sql = dsl.get("sql") or ""
        if not sql:
            logger.error("真实Schema模式: SQL为空")
            return {"sql": None, "error": "未生成有效 SQL"}
        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant", "truncate"]
        sql_lower = sql.lower()
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", sql_lower):
                logger.error(f"真实Schema模式: SQL包含危险关键字 '{kw}'")
                return {"sql": None, "error": f"SQL 包含危险关键字 '{kw}'，已拦截"}
        logger.info("真实Schema模式: 编译成功")
        return {"sql": sql, "sql_list": [sql], "error": None}

    if not dsl:
        logger.error("DSL为空，无法编译")
        return {"sql": None, "error": "DSL 为空，无法编译"}

    # ── 优先使用结构化对象 ──
    if structured:
        metric_map = {m["name"]: m for m in structured.get("metrics", [])}
        dim_map = {d["name"]: d for d in structured.get("dimensions", [])}
        tables_json = structured.get("tables_json") or {}
    else:
        # fallback: 从文本正则解析（兼容旧逻辑）
        metric_map = {}
        for line in schema.split("\n"):
            m = re.match(r"-\s+(\w+)\s+\([^)]+\):\s+表达式=(.+?)(?:\s+同义词=|\s+过滤=|$)", line)
            if m:
                metric_map[m.group(1)] = {"expr": m.group(2).strip()}
        dim_map = {}
        tables_json_match = re.search(r"tables_json[:=]\s*(\{.*\})", schema, re.DOTALL)
        tables_json = json.loads(tables_json_match.group(1)) if tables_json_match else {}

    # ── 构建 SELECT ──
    selects = []
    used_tables = {}  # alias -> table_name

    for m_name in dsl.get("metrics", []):
        m = metric_map.get(m_name)
        if m:
            expr = m.get("expr", m_name)
            selects.append(f"{expr} AS {m_name}")
            # 记录指标使用的表
            tbl = m.get("table_name")
            if tbl:
                used_tables[tbl] = tbl
        else:
            selects.append(f"{m_name} AS {m_name}")

    for d_name in dsl.get("dimensions", []):
        d = dim_map.get(d_name)
        if d:
            col = d.get("column_name", d_name)
            tbl = d.get("table_name")
            if tbl:
                used_tables[tbl] = tbl
                selects.append(f"{tbl}.{col} AS {d_name}")
            else:
                selects.append(f"{col} AS {d_name}")
        else:
            selects.append(d_name)

    # ── 构建 FROM + JOIN ──
    tables_def = tables_json.get("tables", [])
    joins_def = tables_json.get("joins", [])

    # 确定主表（第一个指标的 table_name 或 tables_json 的第一个表）
    primary_table = None
    primary_alias = None
    if tables_def:
        primary_table = tables_def[0].get("name")
        primary_alias = tables_def[0].get("alias") or primary_table
    elif dsl.get("metrics"):
        first_metric = metric_map.get(dsl["metrics"][0])
        if first_metric:
            primary_table = first_metric.get("table_name")
    if not primary_table:
        primary_table = "orders"
        primary_alias = primary_table

    from_parts = [f'{primary_table} AS "{primary_alias}"' if primary_alias != primary_table else primary_table]

    # 构建 JOIN
    joined_tables = {primary_alias or primary_table}
    for j in joins_def:
        left = j.get("left_table")
        right = j.get("right_table")
        left_key = j.get("left_key")
        right_key = j.get("right_key")
        join_type = j.get("type", "LEFT JOIN")
        alias = j.get("alias") or right
        # 只有当右侧表被使用时才 JOIN
        if right in used_tables or any(d.get("table_name") == right for d in dim_map.values()):
            if alias not in joined_tables:
                from_parts.append(f'{join_type} {right} AS "{alias}" ON "{left}".{left_key} = "{alias}".{right_key}')
                joined_tables.add(alias)

    # ── 构建 WHERE ──
    wheres = []

    # 指标内置过滤条件
    for m_name in dsl.get("metrics", []):
        m = metric_map.get(m_name)
        if m and m.get("filter_sql"):
            wheres.append(f"({m['filter_sql']})")

    # DSL 中的 filters
    for f in dsl.get("filters", []):
        field = f["field"]
        op = f["op"]
        vals = f.get("values", [])
        dim = dim_map.get(field)
        if dim and dim.get("table_name"):
            field = f'"{dim["table_name"]}.{dim["column_name"]}"'
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

    # 时间范围：优先使用第一个指标关联的 time_field
    tr = dsl.get("time_range")
    if tr and tr.get("field"):
        time_field = tr["field"]
        if tr.get("start"):
            wheres.append(f"{time_field} >= '{tr['start']}'")
        if tr.get("end"):
            wheres.append(f"{time_field} <= '{tr['end']}'")
    elif dsl.get("metrics"):
        # 自动推断：使用第一个指标的时间字段
        first_metric = metric_map.get(dsl["metrics"][0])
        if first_metric and first_metric.get("time_field"):
            tf = first_metric["time_field"]
            # 默认近30天
            import datetime
            end = datetime.date.today().isoformat()
            start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            wheres.append(f"{tf} >= '{start}'")
            wheres.append(f"{tf} <= '{end}'")

    # ── 组装 SQL ──
    sql_parts = [f"SELECT {', '.join(selects)}"]
    sql_parts.append(f"FROM {' '.join(from_parts)}")

    if wheres:
        sql_parts.append("WHERE " + " AND ".join(wheres))

    dims = dsl.get("dimensions", [])
    if dims:
        group_cols = []
        for d_name in dims:
            d = dim_map.get(d_name)
            if d and d.get("table_name"):
                group_cols.append(f'"{d["table_name"]}.{d["column_name"]}"')
            else:
                group_cols.append(d_name)
        sql_parts.append(f"GROUP BY {', '.join(group_cols)}")

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
            logger.error(f"DSL编译: SQL包含危险关键字 '{kw}'")
            return {"sql": None, "error": f"SQL 包含危险关键字 '{kw}'，已拦截"}

    logger.info("DSL编译成功")
    return {"sql": sql, "sql_list": [sql], "error": None}


# ── 节点 6: SQL 执行 ──────────────────────────────────


def sql_execute_node(db: Session):
    """执行 SQL 查询（只读），连接真实数据源返回结果集。"""

    def _node(state: AgentState) -> Dict[str, Any]:
        sql = state.get("sql")
        logger.info(f"SQL执行节点开始: sql={sql[:80]}..." if sql else "SQL执行节点开始: SQL为空")
        if not sql:
            logger.warning("SQL为空，跳过执行")
            return {"sql_result": None, "error": "SQL 为空", "should_retry": True}

        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "grant", "truncate"]
        sql_lower = sql.lower()
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", sql_lower):
                logger.error(f"SQL执行: 包含危险关键字 '{kw}'")
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
            logger.error("无可用数据源")
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
                        elif isinstance(val, Decimal):
                            row_dict[col] = float(val)
                        else:
                            row_dict[col] = val
                    rows.append(row_dict)
                result = {"columns": columns, "rows": rows, "row_count": len(rows)}
                logger.info(f"SQL执行成功: 返回 {len(rows)} 行")
                return {"sql_result": result, "error": None, "should_retry": False}
        except Exception as e:
            logger.error(f"SQL执行失败: {e}")
            return {"sql_result": None, "error": f"SQL 执行失败: {str(e)}", "should_retry": True}
        finally:
            engine.dispose()

    return _node


# ── 节点 7: 报告生成 ──────────────────────────────────


async def report_generator_node(state: AgentState) -> Dict[str, Any]:
    """根据 SQL 结果生成自然语言回答和图表推荐。
    使用 astream() 实现真正的 token 级流式，供 astream_events 捕获。"""
    logger.info("报告生成节点开始")
    question = state["question"]
    sql_result = state.get("sql_result")

    if not sql_result:
        logger.warning("无SQL结果，返回默认提示")
        return {"answer": "查询未返回结果，请检查语义层配置。"}

    rows = sql_result.get("rows", [])

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

    full_content = ""
    usage = None
    async for chunk in llm.astream([system, human]):
        full_content += chunk.content
        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
            usage = chunk.usage_metadata

    answer = full_content.strip()

    # 尝试从最后一个 chunk 的 usage_metadata 提取 token 用量
    if usage:
        prompt = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
        completion = usage.get("output_tokens") or usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", prompt + completion)
        token_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
    else:
        token_usage = None

    current_usage = state.get("token_usage") or {}
    merged = _merge_token_usage(current_usage, token_usage or {})

    logger.info("报告生成完成")
    return {"answer": answer, "token_usage": merged}
