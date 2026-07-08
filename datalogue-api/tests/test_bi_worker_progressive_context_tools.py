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
    # 新契约:entities 只返回表清单元数据,不再暴露 fields 详情。
    required_keys = {
        "asset_ref",
        "table",
        "schema",
        "description",
        "row_count_approx",
        "column_count",
    }
    for entity in payload["entities"]:
        assert required_keys.issubset(
            entity.keys()
        ), f"实体应包含 {required_keys},实际:{set(entity.keys())}"
        assert "fields" not in entity, "request_schema_slice 不应再返回 fields"
    assert "employee_work_log" in payload_text
    assert "raw_rows" not in payload_text
    assert "select " not in payload_text


def test_l2_returns_context_state_patch_for_worker_passthrough(db_session, employee_dataset):
    provider = BIWorkerContextProvider(db_session)

    context = provider.request_schema_slice(employee_dataset.id, "按员工姓名查询工作日志")
    payload = context.model_dump()

    # 新契约:asset_refs 非空(全量表清单),field_refs 为空(fields 已剥离)。
    assert payload["context_state_patch"]["asset_refs"], "asset_refs 应非空"
    assert payload["context_state_patch"]["field_refs"] == []
    assert payload["context_state_usage"], "context_state_usage 应非空"


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


# ============================================================
# request_schema_slice 全量表清单 + describe_tables 精确点名详情。
# ============================================================


def test_l2_returns_all_tables_without_question_matching(db_session, sample_datasource):
    """request_schema_slice 不再模糊过滤,应返回 dataset 全量表清单。"""

    dataset = SemanticDataset(
        name="全量表清单测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": f"tab_{i}"} for i in range(5)]},
        description="用于验证全量返回",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    for index in range(5):
        _make_wide_table(
            db_session,
            sample_datasource,
            dataset,
            schema_name="pm_tenant",
            table_name=f"tab_{index}",
            column_names=["c1", "c2"],
            table_comment=f"表 {index} 描述",
        )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(dataset.id, "完全不相关的内容")
    payload = context.model_dump()

    assert len(payload["entities"]) == 5, "应返回 dataset 全量 5 张表"
    for entity in payload["entities"]:
        assert "fields" not in entity, "新契约:entities 不再含 fields"


def test_l2_entities_include_row_count_and_column_count(db_session, sample_datasource):
    """entities 元素需暴露 row_count_approx 与 column_count 两个新增指标。"""

    dataset = SemanticDataset(
        name="行数列数元数据测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "row_col_meta"}]},
        description="验证 row_count_approx / column_count",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    table = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name="pm_tenant",
        table_name="row_col_meta",
        table_comment="行数列数元数据表",
        row_count_approx=1234,
    )
    db_session.add(table)
    db_session.flush()
    for index, name in enumerate(("c1", "c2", "c3"), start=1):
        db_session.add(
            SourceColumn(
                table_id=table.id,
                column_name=name,
                data_type="varchar",
                ordinal_position=index,
            )
        )
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    context = provider.request_schema_slice(dataset.id, "任意问题")
    payload = context.model_dump()

    entity = payload["entities"][0]
    assert entity["row_count_approx"] == 1234
    assert entity["column_count"] == 3


def test_describe_tables_returns_fields_with_sample_values(db_session, sample_datasource):
    """describe_tables 精确点名返回字段清单和前 3 条样例值(字符串化)。"""

    dataset = SemanticDataset(
        name="样例值测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "sample_table"}]},
        description="验证 sample_values 前 3 条",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    table = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name="pm_tenant",
        table_name="sample_table",
        table_comment="样例值表",
        row_count_approx=100,
    )
    db_session.add(table)
    db_session.flush()
    column_defs = [
        ("col_a", None),
        ("col_b", None),
        ("col_c", None),
        ("col_d", None),
        ("col_with_samples", [1, 2, 3, 4, 5]),
    ]
    for index, (name, samples) in enumerate(column_defs, start=1):
        db_session.add(
            SourceColumn(
                table_id=table.id,
                column_name=name,
                data_type="varchar",
                ordinal_position=index,
                sample_values=samples,
            )
        )
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    payload = provider.describe_tables(dataset.id, ["sample_table"])

    assert payload["datalogue_event_type"] == "bi_worker_l2_table_detail"
    entity = payload["entities"][0]
    assert entity["status"] == "ok"
    assert len(entity["fields"]) == 5
    sample_field = next(f for f in entity["fields"] if f["name"] == "col_with_samples")
    assert sample_field["sample_values"] == ["1", "2", "3"]
    assert sample_field["sample_source"] == "metadata"
    assert "table:pm_tenant.sample_table.col_with_samples" in payload["context_state_patch"][
        "field_refs"
    ]
    assert payload["context_state_usage"].startswith("将 context_state_patch 合并进后续")


def test_describe_tables_marks_unavailable_when_no_samples(db_session, sample_datasource):
    """无 sample_values 时,sample_values 应为空列表并标记 sample_source=unavailable。"""

    dataset = SemanticDataset(
        name="无样例值测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "empty_sample"}]},
        description="验证无样例值降级",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    table = SourceTable(
        datasource_id=sample_datasource.id,
        schema_name="pm_tenant",
        table_name="empty_sample",
        table_comment="无样例值表",
    )
    db_session.add(table)
    db_session.flush()
    db_session.add(
        SourceColumn(
            table_id=table.id,
            column_name="col_none",
            data_type="varchar",
            ordinal_position=1,
            sample_values=None,
        )
    )
    db_session.add(DatasetSourceTable(dataset_id=dataset.id, source_table_id=table.id))
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    payload = provider.describe_tables(dataset.id, ["empty_sample"])

    field = payload["entities"][0]["fields"][0]
    assert field["sample_values"] == []
    assert field["sample_source"] == "unavailable"


def test_describe_tables_returns_not_found_for_missing_table(db_session, sample_datasource):
    """未包含在 dataset 内的表名应返回 status=not_found 占位实体。"""

    dataset = SemanticDataset(
        name="不存在表测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "t1"}, {"name": "t2"}]},
        description="验证 not_found 处理",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    for name in ("t1", "t2"):
        _make_wide_table(
            db_session,
            sample_datasource,
            dataset,
            schema_name="pm_tenant",
            table_name=name,
            column_names=["c"],
        )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    payload = provider.describe_tables(dataset.id, ["t1", "not_exist_table"])

    assert len(payload["entities"]) == 2
    assert payload["entities"][0]["status"] == "ok"
    assert payload["entities"][0]["table"] == "t1"
    assert payload["entities"][1]["status"] == "not_found"
    assert payload["entities"][1]["table"] == "not_exist_table"


def test_describe_tables_supports_multi_table_batch(db_session, sample_datasource):
    """多表点名应保持入参顺序返回。"""

    dataset = SemanticDataset(
        name="多表批量测试集",
        datasource_id=sample_datasource.id,
        tables_json={"tables": [{"name": "a"}, {"name": "b"}, {"name": "c"}]},
        description="验证多表顺序",
        status="active",
    )
    db_session.add(dataset)
    db_session.flush()

    for name in ("a", "b", "c"):
        _make_wide_table(
            db_session,
            sample_datasource,
            dataset,
            schema_name="pm_tenant",
            table_name=name,
            column_names=["c"],
        )
    db_session.commit()
    db_session.refresh(dataset)

    provider = BIWorkerContextProvider(db_session)
    payload = provider.describe_tables(dataset.id, ["a", "b", "c"])

    assert [entity["table"] for entity in payload["entities"]] == ["a", "b", "c"]
