# ============================================================
# File Name   : test_dictionary_column_comments.py
# Description:
#   数据库字典字段注释迁移的回归测试。
#
# Responsibilities:
#   - 校验关键字段注释包含统一的字典标识。
#   - 防止状态、类型、角色等字段遗漏中文含义说明。
#
# Author      : yangkai
# Created On  : 2026-06-22
# ============================================================

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_migration_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "l7m8n9o0p1q2_add_dictionary_column_comments.py"
    )
    spec = spec_from_file_location("dictionary_column_comments_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dictionary_column_comments_have_marker_and_chinese_meanings():
    module = _load_migration_module()

    comments = {
        (table, column): comment
        for table, column, comment in module._DICT_COLUMN_COMMENTS
    }

    expected_fields = {
        ("datasource", "db_type"),
        ("datasource", "status"),
        ("message", "role"),
        ("source_column", "review_status"),
        ("source_column", "ai_semantic_role"),
        ("business_term", "term_type"),
        ("analysis_blueprint", "implementation_type"),
        ("semantic_validation_case", "entry_route"),
        ("conversation_state", "status"),
        ("dataset_subagent_manifest", "review_status"),
    }

    assert expected_fields <= set(comments)
    for key in expected_fields:
        comment = comments[key]
        assert "字典：" in comment
        assert "=" in comment
        assert "；" in comment

    assert "connected=已连接" in comments[("datasource", "status")]
    assert "pending_review=待审核" in comments[("source_column", "review_status")]
    assert "sql_template=SQL 模板" in comments[
        ("analysis_blueprint", "implementation_type")
    ]


def test_late_table_comments_include_conversation_state():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "m8n9o0p1q2r3_add_late_table_comments.py"
    )
    spec = spec_from_file_location("late_table_comments_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    comments = dict(module._TABLE_COMMENTS)

    assert comments["conversation_state"] == "多轮对话会话状态表"
    assert comments["dataset_subagent_manifest"] == "数据集 SubAgent Manifest 版本治理表"
    assert comments["query_artifact"] == "查询产物存储表"


def test_complete_existing_comments_cover_current_known_gaps():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "n9o0p1q2r3s4_complete_existing_comments.py"
    )
    spec = spec_from_file_location("complete_existing_comments_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    table_comments = dict(module._TABLE_COMMENTS)
    column_comments = {
        (table, column): comment
        for table, column, comment in module._COLUMN_COMMENTS
    }

    assert table_comments["checkpoints"] == "LangGraph checkpoint 状态快照表"
    assert table_comments["alembic_version"] == "Alembic 数据库迁移版本表"
    assert column_comments[("conversation_state", "session_id")] == "业务多轮会话 ID"
    assert column_comments[("dataset_subagent_manifest", "manifest_json")] == (
        "Manifest 完整 JSON 定义"
    )
    assert column_comments[("query_artifact", "artifact_id")] == "产物唯一标识"
    assert column_comments[("source_column", "column_comment")] == "数据库原始字段注释"
    assert column_comments[("source_table", "table_comment")] == "数据库原始表注释"
