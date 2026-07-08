# ============================================================
# File Name   : test_bi_worker_progressive_context_tools.py
# Description:
#   BI Worker 渐进式上下文 Provider 的工具层行为测试。
#
# Responsibilities:
#   - 构造数据集、源表、数据集选表和源字段元数据。
#   - 验证 L0-L3 上下文只按安全层级暴露必要信息。
#
# Author      : yangkai
# Created On  : 2026-07-06
# ============================================================

import pytest

from app.agentscope_service.bi_worker_context import BIWorkerContextProvider
from app.models.dataset import (
    DatasetSourceTable,
    SemanticDataset,
    SourceColumn,
    SourceTable,
)


@pytest.fixture
def employee_dataset(db_session, sample_datasource):
    dataset = SemanticDataset(
        name="员工工作日志数据集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "employee_work_log"}, {"name": "employee_dim"}]},
        description="用于按员工、部门和日期分析工作日志。",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    log_table = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name="public",
        table_name="employee_work_log",
        table_comment="员工工作日志事实表",
        effective_desc="记录员工每日工作日志、日志日期和工作内容。",
        row_count_approx=1200,
    )
    employee_table = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name="public",
        table_name="employee_dim",
        table_comment="员工维度表",
        effective_desc="记录员工姓名、部门和员工编码。",
        row_count_approx=80,
    )
    db_session.add_all([log_table, employee_table])
    db_session.flush()

    db_session.add_all(
        [
            DatasetSourceTable(dataset_id=dataset.id, source_table_id=log_table.id),
            DatasetSourceTable(dataset_id=dataset.id, source_table_id=employee_table.id),
            SourceColumn(
                table_id=log_table.id,
                column_name="log_content",
                data_type="text",
                column_comment="工作日志内容",
                effective_desc="员工填写的工作日志正文。",
                ordinal_position=1,
            ),
            SourceColumn(
                table_id=log_table.id,
                column_name="log_date",
                data_type="date",
                column_comment="日志日期",
                effective_desc="工作日志发生日期。",
                ordinal_position=2,
            ),
            SourceColumn(
                table_id=employee_table.id,
                column_name="employee_name",
                data_type="varchar",
                column_comment="员工姓名",
                effective_desc="员工的中文姓名，用于按人员筛选。",
                suggested_synonyms=["人员", "姓名", "员工"],
                ordinal_position=1,
            ),
            SourceColumn(
                table_id=employee_table.id,
                column_name="department_name",
                data_type="varchar",
                column_comment="部门名称",
                effective_desc="员工所属部门。",
                suggested_synonyms=["部门", "团队"],
                ordinal_position=2,
            ),
        ]
    )
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


def test_l0_describes_dataset_capability_without_physical_schema(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    context = provider.describe_dataset_capability(employee_dataset.id, "按员工姓名查询工作日志")
    payload = context.model_dump()
    payload_text = str(payload).lower()

    assert payload["datalogue_event_type"] == "bi_worker_l0_capability"
    assert payload["dataset_id"] == employee_dataset.id
    assert payload["dataset_name"] == "员工工作日志数据集"
    assert payload["supported_questions"]
    assert "工作日志" in payload["summary"]
    assert "employee_name" not in payload_text
    assert "select " not in payload_text


def test_l1_recalls_relevant_assets_without_sql_or_rows(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    context = provider.recall_query_assets(employee_dataset.id, "按员工姓名查询工作日志")
    payload = context.model_dump()
    payload_text = str(payload).lower()

    assert payload["datalogue_event_type"] == "bi_worker_l1_assets"
    assert payload["assets"]
    assert any(
        asset["asset_type"] == "table" and asset["name"] == "employee_dim"
        for asset in payload["assets"]
    )
    assert "select " not in payload_text
    assert "raw_rows" not in payload_text


def test_l2_returns_relevant_schema_slice_without_raw_rows(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    context = provider.request_schema_slice(employee_dataset.id, "按员工姓名查询工作日志")
    payload = context.model_dump()
    payload_text = str(payload).lower()

    assert payload["datalogue_event_type"] == "bi_worker_l2_schema_slice"
    assert payload["entities"]
    assert "employee_name" in payload_text
    assert "employee_work_log" in payload_text
    assert "raw_rows" not in payload_text
    assert "select " not in payload_text


def test_l2_returns_context_state_patch_for_worker_passthrough(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    context = provider.request_schema_slice(employee_dataset.id, "按员工姓名查询工作日志")
    payload = context.model_dump()

    assert payload["context_state_patch"]["asset_refs"] == [
        "table:public.employee_work_log",
        "table:public.employee_dim",
    ]
    assert "table:public.employee_work_log.log_date" in payload["context_state_patch"]["field_refs"]
    assert "table:public.employee_dim.employee_name" in payload["context_state_patch"]["field_refs"]
    assert payload["context_state_patch"]["relationship_refs"] == [
        "dataset_selected:table:public.employee_work_log->table:public.employee_dim"
    ]
    assert payload["context_state_usage"] == (
        "将 context_state_patch 合并进后续 L4/L5 的 context_state；不要从自然语言摘要手写 context_state。"
    )


def test_l3_profiles_candidate_values_without_returning_rows(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    context = provider.profile_candidate_values(
        employee_dataset.id,
        "查询杨凯的工作日志",
        probes=[
            {
                "table": "employee_dim",
                "column": "employee_name",
                "values": ["杨凯"],
                "reason": "用户输入的人名需要确认匹配字段。",
            }
        ],
    )
    payload = context.model_dump()
    payload_text = str(payload).lower()

    assert payload["datalogue_event_type"] == "bi_worker_l3_value_profile"
    assert payload["profiles"]
    assert payload["profiles"][0]["coverage"] == "metadata_only"
    assert "employee_name" in payload_text
    assert "raw_rows" not in payload_text
    assert "rows" not in payload_text
    assert "select " not in payload_text


def test_context_provider_raises_dataset_not_found(db_session):
    provider = BIWorkerContextProvider(db_session)

    with pytest.raises(ValueError, match="DATASET_NOT_FOUND"):
        provider.describe_dataset_capability(999999, "查询工作日志")


def test_prepare_query_context_extracts_filter_clues(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    # "按杨凯查询2025年日志" 可匹配第二个姓名模式 + 年份模式
    result = provider.prepare_query_context(employee_dataset.id, "按杨凯查询2025年日志")

    assert "suggested_filters" in result
    assert len(result["suggested_filters"]) >= 2

    clue_types = {item["clue_type"] for item in result["suggested_filters"]}
    assert "person_name" in clue_types
    assert "year" in clue_types

    condition_types = {item["type"] for item in result["missing_conditions"]}
    assert "filter_hint_unresolved" in condition_types

    name_clues = [
        item for item in result["suggested_filters"] if item["clue_type"] == "person_name"
    ]
    assert any("杨凯" in item["value"] for item in name_clues)

    year_clues = [item for item in result["suggested_filters"] if item["clue_type"] == "year"]
    assert any("2025" in item["value"] for item in year_clues)

    # 确认 context_state 中也包含了 suggested_filters
    assert "suggested_filters" in result["context_state"]
    assert len(result["context_state"]["suggested_filters"]) >= 2
    assert result["context_state"]["asset_refs"]
    assert all(ref.startswith("table:public.") for ref in result["context_state"]["asset_refs"])


def test_prepare_query_context_without_filter_clues_returns_empty(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    result = provider.prepare_query_context(employee_dataset.id, "查看所有工作日志")

    assert "suggested_filters" in result
    assert len(result["suggested_filters"]) == 0

    condition_types = {item["type"] for item in result["missing_conditions"]}
    assert "filter_hint_unresolved" not in condition_types


# ============================================================
# 以下测试对应 focus/fields 精确通道、字段上限提升到 32、以及
# 从蓝图 SQL 解析出真实 blueprint_join FK 关系的能力。
# ============================================================


def _make_wide_table(
    db_session,
    sample_datasource,
    dataset,
    *,
    schema_name: str,
    table_name: str,
    column_names: list[str],
    table_comment: str | None = None,
    effective_desc: str | None = None,
    column_effective_desc: str | None = None,
) -> SourceTable:
    """辅助函数：构造一张带 N 列的物理表并加入 dataset.selected_tables。

    column_effective_desc 会写入每一列的 effective_desc，便于让 `_matched_columns`
    的模糊匹配命中（列名含下划线不会被自动切成多个 token）。
    """

    table = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name=schema_name,
        table_name=table_name,
        table_comment=table_comment,
        effective_desc=effective_desc,
        row_count_approx=100,
    )
    db_session.add(table)
    db_session.flush()

    for index, column_name in enumerate(column_names, start=1):
        db_session.add(
            SourceColumn(
                table_id=table.id,
                column_name=column_name,
                data_type="varchar",
                column_comment=None,
                effective_desc=column_effective_desc,
                ordinal_position=index,
            )
        )
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.flush()
    return table


def test_l2_returns_exact_fields_when_focus_lists_column_names(db_session, sample_datasource):
    """focus["fields"] 点名字段应精确返回，即使在 32 列以内的宽表中处于末端。"""

    from app.models.dataset import AnalysisBlueprint  # noqa: F401  # 保持导入一致

    dataset = SemanticDataset(
        name="精确字段测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "wide_table"}]},
        description="用于验证 focus.fields 精确通道",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    # 30 列，account 在第 20 位、deptcode 在第 25 位（1-based）
    columns = [f"col_{i:02d}" for i in range(1, 31)]
    columns[19] = "account"  # 第 20 列
    columns[24] = "deptcode"  # 第 25 列
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="wide_table",
        column_names=columns,
        table_comment="精确字段宽表",
    )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(
        dataset.id,
        "查询数据",
        focus={"fields": ["account", "deptcode"]},
    )
    payload = context.model_dump()

    assert payload["entities"], "至少应返回一个实体"
    fields = payload["entities"][0]["fields"]
    field_names = {f["name"] for f in fields}
    # 精确通道：只返回点名的列
    assert field_names == {"account", "deptcode"}


def test_l2_returns_up_to_32_columns_when_all_match(db_session, sample_datasource):
    """字段上限从 8 提升到 32：20 列表全返回；40 列表被截到 32。"""

    dataset = SemanticDataset(
        name="宽表字段上限测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "twenty_col"}, {"name": "forty_col"}]},
        description="验证字段上限提升至 32",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    # 20 列：都用 "keyword" 前缀，保证与 question 模糊匹配命中
    twenty_cols = [f"keyword_col_{i:02d}" for i in range(1, 21)]
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="twenty_col",
        column_names=twenty_cols,
        table_comment="20 列宽表",
        effective_desc="keyword 命中",
        column_effective_desc="keyword",
    )
    # 40 列：同上
    forty_cols = [f"keyword_col_{i:02d}" for i in range(1, 41)]
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="forty_col",
        column_names=forty_cols,
        table_comment="40 列宽表",
        effective_desc="keyword 命中",
        column_effective_desc="keyword",
    )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(dataset.id, "keyword 查询")
    payload = context.model_dump()

    entities_by_table = {e["table"]: e for e in payload["entities"]}
    assert "twenty_col" in entities_by_table
    assert "forty_col" in entities_by_table
    # 20 列表全部命中：返回 20 条
    assert len(entities_by_table["twenty_col"]["fields"]) == 20
    # 40 列表被硬上限截断至 32
    assert len(entities_by_table["forty_col"]["fields"]) == 32


def test_l2_returns_blueprint_join_relationships_from_call_template(db_session, sample_datasource):
    """从蓝图 call_template 解析真实 LEFT JOIN 得到 blueprint_join 关系。"""

    from app.models.dataset import AnalysisBlueprint

    dataset = SemanticDataset(
        name="蓝图 join 测试集",
        datasource_id=sample_datasource.id,
        tables_json={
            "tables": [
                {"name": "plan_task_daily_record"},
                {"name": "eas_personofile"},
            ]
        },
        description="验证蓝图真实 join 关系",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="plan_task_daily_record",
        column_names=["id", "account"],
        table_comment="日报表",
    )
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="eas_personofile",
        column_names=["person_card", "name"],
        table_comment="人员档案",
    )

    blueprint = AnalysisBlueprint(
        dataset_id=dataset.id,
        name="日报关联人员",
        description="日报与人员档案 LEFT JOIN",
        call_template=(
            "SELECT p.id FROM plan_task_daily_record p "
            "LEFT JOIN eas_personofile ep ON p.account = ep.person_card"
        ),
        status="active",
    )
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(dataset)
    db_session.refresh(blueprint)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(dataset.id, "查询日报")
    payload = context.model_dump()

    joins = [r for r in payload["relationships"] if r["relationship_type"] == "blueprint_join"]
    assert len(joins) == 1, f"应恰好返回一条 blueprint_join，实际：{joins}"
    rel = joins[0]
    assert rel["join_type"] == "left"
    assert rel["join_keys"] == [{"left_field": "account", "right_field": "person_card"}]
    assert rel["left_asset_ref"] == "table:pm_tenant.plan_task_daily_record"
    assert rel["right_asset_ref"] == "table:pm_tenant.eas_personofile"
    assert rel["source_blueprint_id"] == blueprint.id


def test_l2_ignores_malformed_blueprint_sql(db_session, sample_datasource):
    """蓝图 call_template 无法解析时不抛异常，也不产出 blueprint_join。"""

    from app.models.dataset import AnalysisBlueprint

    dataset = SemanticDataset(
        name="蓝图坏 SQL 测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "t1"}, {"name": "t2"}]},
        description="验证坏 SQL 静默降级",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t1",
        column_names=["a", "b"],
    )
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t2",
        column_names=["a", "b"],
    )
    db_session.add(
        AnalysisBlueprint(
            dataset_id=dataset.id,
            name="坏蓝图",
            call_template="!!! not sql at all",
            status="active",
        )
    )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    # 不应抛异常
    context = provider.request_schema_slice(dataset.id, "查询")
    payload = context.model_dump()

    joins = [r for r in payload["relationships"] if r["relationship_type"] == "blueprint_join"]
    assert joins == []
    # 但软关系仍在（两张表都被选中）
    soft = [
        r for r in payload["relationships"] if r["relationship_type"] == "dataset_selected_together"
    ]
    assert soft, "坏 SQL 不应影响软关系产出"


def test_l2_ignores_non_equi_join(db_session, sample_datasource):
    """ON 里非等值条件（>/</!=）不算 join_keys，跳过该 blueprint。"""

    from app.models.dataset import AnalysisBlueprint

    dataset = SemanticDataset(
        name="非等值 join 测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "t1"}, {"name": "t2"}]},
        description="验证 > 不视为 equi-join",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t1",
        column_names=["a", "b"],
    )
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t2",
        column_names=["a", "b"],
    )
    db_session.add(
        AnalysisBlueprint(
            dataset_id=dataset.id,
            name="非等值蓝图",
            call_template="SELECT p.a FROM t1 p LEFT JOIN t2 ep ON p.a > ep.b",
            status="active",
        )
    )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(dataset.id, "查询")
    payload = context.model_dump()

    joins = [r for r in payload["relationships"] if r["relationship_type"] == "blueprint_join"]
    assert joins == [], "非等值 join 不应产出 blueprint_join"


def test_l2_multi_join_and_inner_join(db_session, sample_datasource):
    """同一蓝图内的 INNER JOIN + LEFT JOIN 分别落成两条 blueprint_join。"""

    from app.models.dataset import AnalysisBlueprint

    dataset = SemanticDataset(
        name="多 join 混合测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "t1"}, {"name": "t2"}, {"name": "t3"}]},
        description="验证 INNER + LEFT 分别产出",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t1",
        column_names=["a", "x"],
    )
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t2",
        column_names=["b"],
    )
    _make_wide_table(
        db_session,
        sample_datasource,
        dataset,
        schema_name="pm_tenant",
        table_name="t3",
        column_names=["y"],
    )
    blueprint = AnalysisBlueprint(
        dataset_id=dataset.id,
        name="多 join 蓝图",
        call_template=(
            "SELECT * FROM t1 p " "INNER JOIN t2 e ON p.a = e.b " "LEFT JOIN t3 d ON p.x = d.y"
        ),
        status="active",
    )
    db_session.add(blueprint)
    db_session.commit()
    db_session.refresh(dataset)
    db_session.refresh(blueprint)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(dataset.id, "查询")
    payload = context.model_dump()

    joins = [r for r in payload["relationships"] if r["relationship_type"] == "blueprint_join"]
    assert len(joins) == 2, f"应得到两条 blueprint_join：{joins}"

    by_right = {r["right_asset_ref"]: r for r in joins}
    inner_rel = by_right["table:pm_tenant.t2"]
    left_rel = by_right["table:pm_tenant.t3"]

    assert inner_rel["join_type"] == "inner"
    assert inner_rel["left_asset_ref"] == "table:pm_tenant.t1"
    assert inner_rel["join_keys"] == [{"left_field": "a", "right_field": "b"}]

    assert left_rel["join_type"] == "left"
    assert left_rel["left_asset_ref"] == "table:pm_tenant.t1"
    assert left_rel["join_keys"] == [{"left_field": "x", "right_field": "y"}]
