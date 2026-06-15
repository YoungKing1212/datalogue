# ============================================================
# File Name   : test_dataset_context.py
# Description:
#   数据集问数上下文组装服务测试。
#
# Responsibilities:
#   - 验证上下文按预算裁剪且优先保留命中资产。
#   - 验证空资产数据集仍能返回最小完整上下文和调试信息。
#
# Author      : yangkai
# Created On  : 2026-06-09
# ============================================================

"""数据集问数上下文组装服务测试。"""


def test_dataset_query_context_trims_large_dataset_and_keeps_matched_metric(
    db_session, sample_dataset
):
    """大数据集裁剪：预算不足时仍保留用户问题命中的资产。"""
    from app.models.dataset import SemanticMetric
    from app.services.dataset_context import build_dataset_query_context

    important = SemanticMetric(
        dataset_id=sample_dataset.id,
        name="important_revenue",
        display_name="关键收入",
        expr="SUM(o.important_revenue)",
        table_name="orders",
        time_field="o.pay_time",
        synonyms=["核心收入"],
    )
    db_session.add(important)
    for idx in range(80):
        db_session.add(
            SemanticMetric(
                dataset_id=sample_dataset.id,
                name=f"noise_metric_{idx}",
                display_name=f"噪音指标{idx}",
                expr=f"SUM(o.noise_{idx})",
                table_name="orders",
                description="这是一段较长的说明，用于制造上下文预算压力。",
            )
        )
    db_session.commit()

    result = build_dataset_query_context(
        db_session,
        sample_dataset.id,
        question="帮我查询关键收入趋势",
        token_budget=600,
    )

    assert "important_revenue" in result["schema_context"]
    assert "关键收入" in result["schema_context"]
    assert result["dataset_context_debug"]["dropped_entries"] > 0
    assert result["dataset_context_debug"]["pinned_retained"] >= 1
    assert result["datasource_context"]["db_type"] == "sqlite"
    assert result["datasource_context"]["dialect"] == "sqlite"
    assert result["dataset_context_debug"]["asset_counts"]["metrics"] >= 83
    assert result["dataset_context_debug"]["retained_counts"]["metrics"] < result[
        "dataset_context_debug"
    ]["asset_counts"]["metrics"]
    assert len(result["schema_structured"]["metrics"]) >= 83


def test_dataset_query_context_empty_assets_returns_minimal_context(
    db_session, sample_datasource
):
    """空资产场景：没有指标、维度、术语和表字段时也返回可解释上下文。"""
    from app.models.dataset import SemanticDataset
    from app.services.dataset_context import build_dataset_query_context

    dataset = SemanticDataset(
        name="空数据集",
        datasource_id=sample_datasource.id,
        tables_json={},
        description="暂无语义资产",
        status="active",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    result = build_dataset_query_context(db_session, dataset.id, question="查一下销售额")

    assert "【数据集问数上下文】" in result["schema_context"]
    assert "【语义层】" in result["schema_context"]
    assert "【指标列表】\n（无）" in result["schema_context"]
    assert "【权限信息】" in result["schema_context"]
    assert "该数据集尚未选择任何表" in result["ddl_context"]
    assert result["schema_structured"]["metrics"] == []
    assert result["schema_structured"]["dimensions"] == []
    assert result["schema_structured"]["fields"] == []
    assert result["schema_structured"]["datasource_context"]["db_type"] == "sqlite"
    assert result["datasource_context"]["default_schema"] == "main"
    assert result["dataset_context_debug"]["asset_counts"] == {
        "metrics": 0,
        "dimensions": 0,
        "terms": 0,
        "blueprints": 0,
        "fields": 0,
        "selected_tables": 0,
    }


def test_dataset_query_context_blueprints_keep_planning_metadata(
    db_session, sample_dataset
):
    """蓝图候选需要保留参数和 SQL 模板，供 SubAgent 规划层判断澄清或参考。"""
    from app.models.dataset import AnalysisBlueprint
    from app.services.dataset_context import build_dataset_query_context

    db_session.add(
        AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="个人日报查询",
            description="按日期查询个人日报",
            when_to_use="用户需要日报时使用",
            trigger_keywords=["日报"],
            parameters=[{"name": "start_date", "type": "date", "required": True}],
            implementation_type="sql_template",
            raw_sql="select * from daily_report where start_date = :start_date",
            status="active",
        )
    )
    db_session.commit()

    result = build_dataset_query_context(
        db_session,
        sample_dataset.id,
        question="查一下日报",
    )

    blueprint = result["schema_structured"]["blueprints"][0]

    assert blueprint["description"] == "按日期查询个人日报"
    assert blueprint["when_to_use"] == "用户需要日报时使用"
    assert blueprint["parameters"][0]["name"] == "start_date"
    assert blueprint["raw_sql"].startswith("select * from daily_report")
