# ============================================================
# File Name   : test_dataset_prompt_instructions.py
# Description:
#   数据集提示词约束功能测试。
#
# Responsibilities:
#   - 验证提示词约束的持久化。
#   - 确保自定义指令进入语义上下文。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""数据集级 LLM 约束（prompt_instructions）注入测试。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import (
    SemanticDataset,
    SemanticMetric,
    SemanticDimension,
    Datasource,
)
from app.utils.prompt import build_schema_prompt


@pytest.fixture
def db():
    """内存 SQLite。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_dataset(db, prompt_instructions=None, query_constraints=None) -> SemanticDataset:
    """最小数据集（含 1 指标 1 维度）。"""
    ds_src = Datasource(name="t", db_type="mysql", host="x", port=3306,
                        database_name="testdb", username="u", password_enc="x")
    db.add(ds_src)
    db.flush()
    ds = SemanticDataset(
        name="零售数据集",
        description="业务描述",
        datasource_id=ds_src.id,
        prompt_instructions=prompt_instructions,
        query_constraints=query_constraints,
    )
    db.add(ds)
    db.flush()
    db.add(SemanticMetric(dataset_id=ds.id, name="gmv", display_name="GMV",
                          expr="SUM(amt)", table_name="t_order"))
    db.add(SemanticDimension(dataset_id=ds.id, name="region", display_name="地区",
                             column_name="region", table_name="t_order"))
    db.commit()
    db.refresh(ds)
    return ds


class TestBuildSchemaPromptInstructions:
    """验证 build_schema_prompt 对 prompt_instructions 字段的处理。"""

    def test_none_not_injected(self, db):
        """字段为 None → 不应注入"数据集级 LLM 约束"段。"""
        ds = _make_dataset(db, prompt_instructions=None)
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "【数据集级 LLM 约束" not in out

    def test_empty_string_not_injected(self, db):
        """字段为空串 → 不注入。"""
        ds = _make_dataset(db, prompt_instructions="")
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "【数据集级 LLM 约束" not in out

    def test_whitespace_only_not_injected(self, db):
        """只有空格 → trim 后视为空，不注入。"""
        ds = _make_dataset(db, prompt_instructions="   \n  \t  ")
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "【数据集级 LLM 约束" not in out

    def test_real_text_injected(self, db):
        """有实际内容 → 必须出现，且被 trim。"""
        ds = _make_dataset(db, prompt_instructions="  金额保留两位小数  \n")
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "【数据集级 LLM 约束（硬性要求）】" in out
        assert "金额保留两位小数" in out
        # 不能有前导 / 尾部空白
        assert "  金额保留两位小数  " not in out

    def test_positioned_before_metric_list(self, db):
        """约束段必须出现在"【指标列表】"之前（LLM 优先级高）。"""
        ds = _make_dataset(db, prompt_instructions="订单状态: 1=待支付")
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        pos_constraint = out.index("【数据集级 LLM 约束")
        pos_metrics = out.index("【指标列表】")
        assert pos_constraint < pos_metrics, (
            f"约束段必须在指标列表前（constraint@{pos_constraint}, "
            f"metrics@{pos_metrics}）"
        )

    def test_multiline_preserved(self, db):
        """多行约束保留换行。"""
        ds = _make_dataset(
            db,
            prompt_instructions="第一行\n第二行\n第三行",
        )
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "第一行\n第二行\n第三行" in out

    def test_query_constraints_default_injected(self, db):
        """查询约束默认开启，并注入 SQL 生成规则。"""
        ds = _make_dataset(db, query_constraints=None)
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "【SQL 生成查询约束（硬性要求）】" in out
        assert "默认查询最近 30 天" in out
        assert "默认 LIMIT 100" in out

    def test_query_constraints_can_be_customized(self, db):
        """查询约束支持数据集级自定义。"""
        ds = _make_dataset(
            db,
            query_constraints={
                "enabled": True,
                "default_time_range_days": 14,
                "default_limit": 50,
                "max_limit": 500,
            },
        )
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "默认查询最近 14 天" in out
        assert "默认 LIMIT 50" in out
        assert "最大不能超过 500" in out

    def test_query_constraints_can_be_disabled(self, db):
        """禁用查询约束后不再注入默认时间范围和 LIMIT。"""
        ds = _make_dataset(db, query_constraints={"enabled": False})
        out = build_schema_prompt(ds, ds.metrics, ds.dimensions)
        assert "【SQL 生成查询约束" not in out


# ── 回归：推断路径 (ddl_context 走 ddl，schema_context 不参与) 必须也能注入约束 ──


class _FakeLLMResponse:
    """最小假 LLM 响应，捕获 invoke 的入参。"""

    def __init__(self):
        self.last_messages = None
        self.content = '{"sql": "SELECT 1"}'
        self.usage_metadata = None  # 让 _extract_token_usage 不报错

    def invoke(self, messages):
        self.last_messages = messages
        return self


def test_dsl_generate_inferred_path_includes_constraint(monkeypatch):
    """回归：推断路径使用 ddl_context 而非 schema_context，必须在 human_text
    里手动追加 dataset_prompt_instructions，否则约束丢失。"""
    from app.graph import nodes as nodes_module

    fake = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **kw: fake)

    state = {
        "question": "查询杨凯 2024 年的日志",
        "entities": {"metrics": ["日志"], "dimensions": ["杨凯"]},
        "schema_context": "【语义层】\n数据集: x\n（不参与推断路径）",
        "ddl_context": "表: t_log\n  - person_name (varchar)",
        "metric_resolution": {
            "all_matched": False,
            "unresolved": ["日志"],
            "metrics": [],
            "dimensions": [],
        },
        "dataset_prompt_instructions": "用户说'杨凯'时翻译为 person_name='杨凯'",
        "query_constraints": {
            "enabled": True,
            "default_time_range_days": 14,
            "default_limit": 50,
            "max_limit": 500,
        },
        "retry_count": 0,
        "error": None,
    }

    result = nodes_module.dsl_generate_node(state)
    assert result.get("error") is None, f"unexpected error: {result.get('error')}"

    # 抓取实际发往 LLM 的 human 消息
    assert fake.last_messages is not None
    human_msg = fake.last_messages[1]  # [system, human]
    assert "【数据集级 LLM 约束（硬性要求）】" in human_msg.content
    assert "person_name='杨凯'" in human_msg.content
    system_msg = fake.last_messages[0]
    assert "默认查询最近 14 天" in system_msg.content
    assert "默认 LIMIT 50" in system_msg.content


def test_dsl_generate_inferred_path_omits_constraint_when_empty(monkeypatch):
    """反向：dataset_prompt_instructions 为空时，human_text 不应有"硬性要求"段。"""
    from app.graph import nodes as nodes_module

    fake = _FakeLLMResponse()
    monkeypatch.setattr(nodes_module, "get_llm", lambda **kw: fake)

    state = {
        "question": "查询杨凯 2024 年的日志",
        "entities": {"metrics": ["日志"]},
        "schema_context": "",
        "ddl_context": "表: t_log",
        "metric_resolution": {
            "all_matched": False,
            "unresolved": ["日志"],
            "metrics": [],
            "dimensions": [],
        },
        "dataset_prompt_instructions": None,
        "query_constraints": {"enabled": False},
        "retry_count": 0,
        "error": None,
    }

    nodes_module.dsl_generate_node(state)
    human_msg = fake.last_messages[1]
    assert "【数据集级 LLM 约束" not in human_msg.content
    assert "硬性要求" not in human_msg.content
    system_msg = fake.last_messages[0]
    assert "默认查询最近" not in system_msg.content
    assert "默认 LIMIT" not in system_msg.content


def test_dsl_compiler_uses_dataset_default_limit(monkeypatch):
    """DSL 没有 limit 时，编译器使用数据集查询约束的默认 LIMIT。"""
    from app.graph import nodes as nodes_module

    monkeypatch.setattr(nodes_module, "_resolve_dialect", lambda db, dataset_id: "mysql")
    result = nodes_module.dsl_compiler_node(db=None)(
        {
            "dataset_id": 1,
            "dsl": {"metrics": ["gmv"]},
            "schema_structured": {
                "tables_json": {"tables": [{"name": "t_order", "alias": "o"}]},
                "metrics": [
                    {
                        "name": "gmv",
                        "expr": "SUM(o.amt)",
                        "table_name": "t_order",
                        "time_field": None,
                        "filter_sql": None,
                    }
                ],
                "dimensions": [],
            },
            "schema_context": "【语义层】",
            "query_constraints": {"enabled": True, "default_limit": 20, "max_limit": 200},
        }
    )
    assert "LIMIT 20" in result["sql"]


def test_dsl_compiler_clamps_limit(monkeypatch):
    """DSL limit 超过上限时，编译器按数据集 max_limit 截断。"""
    from app.graph import nodes as nodes_module

    monkeypatch.setattr(nodes_module, "_resolve_dialect", lambda db, dataset_id: "mysql")
    result = nodes_module.dsl_compiler_node(db=None)(
        {
            "dataset_id": 1,
            "dsl": {"metrics": ["gmv"], "limit": 9999},
            "schema_structured": {
                "tables_json": {"tables": [{"name": "t_order", "alias": "o"}]},
                "metrics": [
                    {
                        "name": "gmv",
                        "expr": "SUM(o.amt)",
                        "table_name": "t_order",
                        "time_field": None,
                        "filter_sql": None,
                    }
                ],
                "dimensions": [],
            },
            "schema_context": "【语义层】",
            "query_constraints": {"enabled": True, "default_limit": 20, "max_limit": 200},
        }
    )
    assert "LIMIT 200" in result["sql"]
