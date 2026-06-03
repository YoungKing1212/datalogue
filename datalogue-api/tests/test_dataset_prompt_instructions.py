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


def _make_dataset(db, prompt_instructions=None) -> SemanticDataset:
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
        "retry_count": 0,
        "error": None,
    }

    nodes_module.dsl_generate_node(state)
    human_msg = fake.last_messages[1]
    assert "【数据集级 LLM 约束" not in human_msg.content
    assert "硬性要求" not in human_msg.content
