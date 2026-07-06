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
    assert any(asset["asset_type"] == "table" and asset["name"] == "employee_dim" for asset in payload["assets"])
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
