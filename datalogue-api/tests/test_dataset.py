# ============================================================
# File Name   : test_dataset.py
# Description:
#   语义数据集治理 API 测试。
#
# Responsibilities:
#   - 验证数据集、指标、维度、字段、术语和转化流程。
#   - 覆盖 YAML 导入导出和审核工作流。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
语义数据集管理 API 测试
"""

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app import models


class TestDatasetAPI:
    """测试 /api/dataset 路由"""

    def _manifest_manual_fields(self):
        return {
            "description": (
                "订单销售数据集用于分析门店订单在日、周、月范围内的GMV、订单数、地区和品类表现，"
                "覆盖销售运营人员查看各区域成交趋势、品类结构、异常波动和门店经营质量，不覆盖库存、会员画像和售后工单。"
            ),
            "business_domain": ["销售运营"],
            "sample_questions": [
                "最近30日GMV趋势如何",
                "按地区统计本月订单数",
                "各品类销售额排名",
                "华东区域订单量是多少",
                "本周门店成交金额变化",
            ],
            "routing_negative_examples": [
                "库存周转率是多少",
                "会员画像年龄分布",
                "售后工单处理时长",
            ],
            "permission_scope": {
                "status": "allowed",
                "description": "允许在测试数据集绑定范围内执行 SubAgent 查询。",
            },
        }

    def _create_selected_table_with_columns(self, db_session, sample_dataset, sample_datasource):
        table = models.SourceTable(
            datasource_id=sample_datasource.id,
            schema_name="public",
            table_name="orders_detail",
            table_comment="订单明细表",
        )
        db_session.add(table)
        db_session.flush()
        amount_col = models.SourceColumn(
            table_id=table.id,
            column_name="amount",
            data_type="numeric",
            column_comment="订单金额",
            ai_description="订单实付金额",
            ai_semantic_role="metric_candidate",
            ai_suggested_agg="SUM",
            ai_confidence=0.91,
            ai_reason="金额字段适合作为求和指标",
            suggested_synonyms=["销售额", "成交金额"],
            review_status="pending_review",
            ordinal_position=1,
        )
        region_col = models.SourceColumn(
            table_id=table.id,
            column_name="region",
            data_type="varchar",
            column_comment="销售区域",
            ai_description="订单所属销售区域",
            ai_semantic_role="dimension_candidate",
            ai_confidence=0.88,
            suggested_synonyms=["区域"],
            suggested_enum_values=["华东", "华南"],
            sample_values=["华东", "华南", "华北"],
            review_status="pending_review",
            ordinal_position=2,
        )
        time_col = models.SourceColumn(
            table_id=table.id,
            column_name="created_at",
            data_type="timestamp",
            ai_semantic_role="time_field",
            ordinal_position=3,
        )
        db_session.add_all([amount_col, region_col, time_col])
        db_session.flush()
        db_session.add(
            models.DatasetSourceTable(
                dataset_id=sample_dataset.id,
                source_table_id=table.id,
            )
        )
        db_session.commit()
        return amount_col, region_col

    def _patch_sql_preview_engine(self, monkeypatch):
        """构造只给 SQL preview 使用的业务库 Engine，避免测试直连真实外部数据源。"""

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE orders_detail ("
                    "id INTEGER PRIMARY KEY, region TEXT, amount NUMERIC, created_at TEXT)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO orders_detail (region, amount, created_at) VALUES "
                    "('华东', 120.5, '2026-06-01'),"
                    "('华南', 80, '2026-06-02')"
                )
            )
        monkeypatch.setattr(
            "app.domains.query_execution.preview.create_engine_for_datasource",
            lambda _datasource: engine,
        )
        return engine

    def test_sql_preview_select_returns_rows(
        self, client, db_session, sample_dataset, sample_datasource, monkeypatch
    ):
        """合法 SELECT 只读 SQL 可通过数据集绑定数据源返回列、行和行数。"""

        self._create_selected_table_with_columns(db_session, sample_dataset, sample_datasource)
        self._patch_sql_preview_engine(monkeypatch)

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/sql/preview",
            json={
                "question": "按地区统计订单数",
                "sql": "SELECT region, COUNT(*) AS cnt FROM orders_detail GROUP BY region",
                "limit": 10,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_id"] == sample_dataset.id
        assert data["sql_guard"]["ok"] is True
        assert "LIMIT" in data["sql"].upper()
        assert data["columns"] == ["region", "cnt"]
        assert data["row_count"] == 2
        assert {row["region"] for row in data["rows"]} == {"华东", "华南"}

    def test_sql_preview_blocks_dml(
        self, client, db_session, sample_dataset, sample_datasource, monkeypatch
    ):
        """DELETE/UPDATE/INSERT/DROP 等写入类 SQL 必须被 SQL Guard 拦截。"""

        self._create_selected_table_with_columns(db_session, sample_dataset, sample_datasource)
        self._patch_sql_preview_engine(monkeypatch)

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/sql/preview",
            json={"sql": "DELETE FROM orders_detail WHERE id = 1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["rows"] == []
        assert data["row_count"] == 0
        assert data["sql_guard"]["ok"] is False
        assert data["sql_guard"]["code"] in {"FORBIDDEN_KEYWORD", "NOT_READONLY"}
        assert data["error"]

    def test_dataset_capability_manifest_endpoint(self, client, sample_dataset):
        """能力清单调试接口只返回业务摘要，不暴露字段、表和 SQL。"""

        resp = client.get(f"/api/dataset/{sample_dataset.id}/capability-manifest")

        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_id"] == sample_dataset.id
        assert data["schema_version"] == "capability_manifest.v1"
        assert "GMV" in data["metrics"]
        assert "地区" in data["dimensions"]
        serialized = str(data)
        assert "expr" not in serialized
        assert "table_name" not in serialized
        assert "raw_sql" not in serialized

    def test_sql_preview_blocks_unselected_table(
        self, client, db_session, sample_dataset, sample_datasource, monkeypatch
    ):
        """SQL 只能访问当前数据集已选择的 source tables。"""

        self._create_selected_table_with_columns(db_session, sample_dataset, sample_datasource)
        self._patch_sql_preview_engine(monkeypatch)

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/sql/preview",
            json={"sql": "SELECT * FROM unselected_orders LIMIT 10"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sql_guard"]["ok"] is False
        assert data["sql_guard"]["code"] == "SQL_GUARD_BLOCKED"
        assert "未授权" in data["error"]

    def test_sql_preview_clamps_limit(
        self, client, db_session, sample_dataset, sample_datasource, monkeypatch
    ):
        """超过数据集 max_limit 的 LIMIT 会被 Guard 裁剪后再执行。"""

        self._create_selected_table_with_columns(db_session, sample_dataset, sample_datasource)
        sample_dataset.query_constraints = {
            "enabled": True,
            "default_time_range_days": 30,
            "default_limit": 5,
            "max_limit": 1,
        }
        db_session.commit()
        self._patch_sql_preview_engine(monkeypatch)

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/sql/preview",
            json={"sql": "SELECT id, region FROM orders_detail LIMIT 99"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sql_guard"]["ok"] is True
        assert data["row_count"] == 1
        assert any("裁剪为 1" in warning for warning in data["sql_guard"]["warnings"])

    def test_sql_preview_missing_datasource_returns_structured_error(
        self, client, db_session, sample_dataset
    ):
        """数据集绑定的数据源缺失时，不进入 SQL 执行，返回结构化错误。"""

        sample_dataset.datasource_id = 999999
        db_session.commit()

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/sql/preview",
            json={"sql": "SELECT 1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_id"] == sample_dataset.id
        assert data["columns"] == []
        assert data["rows"] == []
        assert data["row_count"] == 0
        assert data["sql_guard"]["ok"] is False
        assert "数据源" in data["error"]

    def test_list_datasets_empty(self, client):
        """空数据集列表"""
        resp = client.get("/api/dataset")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_get_dataset(self, client, sample_datasource):
        """创建并获取数据集"""
        payload = {
            "name": "销售分析数据集",
            "datasource_id": sample_datasource.id,
            "tables_json": {"tables": [{"name": "sales", "alias": "s"}]},
            "description": "销售数据分析",
            "status": "active",
        }
        resp = client.post("/api/dataset", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "销售分析数据集"
        assert data["datasource_id"] == sample_datasource.id
        assert data["status"] == "active"
        assert data["query_constraints"]["enabled"] is True
        assert data["query_constraints"]["default_time_range_days"] == 30
        assert data["query_constraints"]["default_limit"] == 100

    def test_manifest_publish_requires_manual_quality_fields(self, client, sample_dataset):
        """发布 Manifest 时必须补齐 B 类人工字段。"""
        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/publish",
            json={"manual_fields": {"description": "太短", "business_domain": []}},
        )
        assert resp.status_code == 400
        lint = resp.json()["detail"]["lint"]
        assert {item["code"] for item in lint} >= {
            "description_length",
            "business_domain_required",
            "sample_questions_count",
            "routing_negative_examples_count",
        }

    def test_manifest_publish_versions_and_keeps_history(self, client, sample_dataset):
        """发布 Manifest 会递增版本、切 current，并保留历史版本。"""
        manual = self._manifest_manual_fields()
        draft_resp = client.put(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest",
            json={"manual_fields": manual, "created_by": "tester"},
        )
        assert draft_resp.status_code == 200
        assert draft_resp.json()["manifest_version"] == "draft"

        first = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/publish",
            json={"created_by": "tester"},
        )
        assert first.status_code == 200
        assert first.json()["manifest_version"] == "v1"
        assert first.json()["is_current"] is True
        assert first.json()["manifest_json"]["manual_fields"]["business_domain"] == ["销售运营"]

        second_manual = {
            **manual,
            "sample_questions": [*manual["sample_questions"][:-1], "最近7日订单数趋势如何"],
        }
        second = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/publish",
            json={"manual_fields": second_manual, "created_by": "tester"},
        )
        assert second.status_code == 200
        assert second.json()["manifest_version"] == "v2"

        currents = client.get("/api/dataset/subagent-manifests/current")
        assert currents.status_code == 200
        assert [item["manifest_version"] for item in currents.json()] == ["v2"]

    def test_manifest_marks_current_needs_review_after_schema_change(
        self, client, sample_dataset
    ):
        """指标变更后 current Manifest 标记 needs_review，B 类字段不被改写。"""
        manual = self._manifest_manual_fields()
        published = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/publish",
            json={"manual_fields": manual},
        )
        assert published.status_code == 200
        old_bound = published.json()["bound_schema_version"]

        add_metric = client.post(
            f"/api/dataset/{sample_dataset.id}/metric",
            json={
                "name": "refund_amount",
                "display_name": "退款金额",
                "expr": "SUM(o.refund_amount)",
                "description": "退款金额合计",
            },
        )
        assert add_metric.status_code == 200

        detail = client.get(f"/api/dataset/{sample_dataset.id}/subagent-manifest")
        assert detail.status_code == 200
        data = detail.json()
        assert data["stale"] is True
        assert data["current_manifest"]["review_status"] == "needs_review"
        assert data["current_manifest"]["bound_schema_version"] == old_bound
        assert data["manual_fields"] == manual

    def test_manifest_route_check_positive_and_negative(self, client, sample_dataset):
        """route-check 对正例命中，对负例避让。"""
        manual = self._manifest_manual_fields()
        publish = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/publish",
            json={"manual_fields": manual},
        )
        assert publish.status_code == 200

        positive = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/route-check",
            json={"questions": ["最近30日GMV趋势如何"], "expected": "positive"},
        )
        assert positive.status_code == 200
        assert positive.json()["results"][0]["decision"] == "hit"
        assert positive.json()["results"][0]["top_dataset_id"] == sample_dataset.id

        negative = client.post(
            f"/api/dataset/{sample_dataset.id}/subagent-manifest/route-check",
            json={"questions": ["库存周转率是多少"], "expected": "negative"},
        )
        assert negative.status_code == 200
        assert negative.json()["results"][0]["decision"] == "miss"

    def test_create_dataset_with_prompt_instructions(self, client, sample_datasource):
        """新建数据集时可填 prompt_instructions，后续 GET 能取回。"""
        payload = {
            "name": "约束测试数据集",
            "datasource_id": sample_datasource.id,
            "prompt_instructions": "金额保留两位小数；用户说'杨凯'时翻译为 person_name='杨凯'",
        }
        resp = client.post("/api/dataset", json=payload)
        assert resp.status_code == 200
        ds_id = resp.json()["id"]
        # GET 应能取回
        get_resp = client.get(f"/api/dataset/{ds_id}")
        assert get_resp.status_code == 200
        assert "金额保留两位小数" in get_resp.json()["prompt_instructions"]

    def test_update_dataset_query_constraints(self, client, sample_dataset):
        """PUT 部分更新能修改 SQL 生成查询约束。"""
        resp = client.put(
            f"/api/dataset/{sample_dataset.id}",
            json={
                "query_constraints": {
                    "enabled": True,
                    "default_time_range_days": 14,
                    "default_limit": 50,
                    "max_limit": 500,
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query_constraints"]["enabled"] is True
        assert data["query_constraints"]["default_time_range_days"] == 14
        assert data["query_constraints"]["default_limit"] == 50
        assert data["query_constraints"]["max_limit"] == 500

    def test_update_dataset_query_constraints_clamps_limit(self, client, sample_dataset):
        """查询约束保存时会裁剪到安全范围。"""
        resp = client.put(
            f"/api/dataset/{sample_dataset.id}",
            json={
                "query_constraints": {
                    "enabled": True,
                    "default_time_range_days": 0,
                    "default_limit": 5000,
                    "max_limit": 200,
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()["query_constraints"]
        assert data["default_time_range_days"] == 1
        assert data["default_limit"] == 200
        assert data["max_limit"] == 200

    def test_update_dataset_prompt_instructions(self, client, sample_dataset):
        """PUT 部分更新能修改 prompt_instructions 字段。"""
        # 先确认初值
        assert sample_dataset.prompt_instructions in (None, "")
        # 部分更新：只发 prompt_instructions，其他字段不变
        resp = client.put(
            f"/api/dataset/{sample_dataset.id}",
            json={"prompt_instructions": "订单状态: 1=待支付, 2=已支付"},
        )
        assert resp.status_code == 200
        # 再 GET 验证
        get_resp = client.get(f"/api/dataset/{sample_dataset.id}")
        assert "订单状态" in get_resp.json()["prompt_instructions"]

    def test_update_dataset_other_fields_unchanged(self, client, sample_dataset):
        """PUT 时只发一个字段，其他字段不能被清空。"""
        original_name = sample_dataset.name
        original_desc = sample_dataset.description
        client.put(
            f"/api/dataset/{sample_dataset.id}",
            json={"prompt_instructions": "新约束"},
        )
        get_resp = client.get(f"/api/dataset/{sample_dataset.id}")
        data = get_resp.json()
        assert data["name"] == original_name
        assert data["description"] == original_desc
        assert data["prompt_instructions"] == "新约束"

    def test_add_metric(self, client, sample_dataset):
        """向数据集添加指标"""
        payload = {
            "name": "revenue",
            "display_name": "营收",
            "expr": "SUM(s.amount)",
            "synonyms": ["收入", "营业额"],
            "description": "总营收",
        }
        resp = client.post(f"/api/dataset/{sample_dataset.id}/metric", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "revenue"
        assert data["dataset_id"] == sample_dataset.id

    def test_add_metric_dataset_not_found(self, client):
        """向不存在的数据集添加指标应 404"""
        resp = client.post(
            "/api/dataset/99999/metric",
            json={
                "name": "x",
                "display_name": "X",
                "expr": "SUM(x)",
            },
        )
        assert resp.status_code == 404

    def test_convert_metric_candidate_column(self, client, db_session, sample_dataset, sample_datasource):
        """度量候选字段可转换为指标，重复转换不重复创建。"""
        amount_col, _ = self._create_selected_table_with_columns(
            db_session, sample_dataset, sample_datasource
        )

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/columns/{amount_col.id}/convert-metric"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["metric"]["expr"] == "SUM(amount)"
        assert data["metric"]["table_name"] == "orders_detail"
        assert data["metric"]["time_field"] == "created_at"
        assert data["column"]["review_status"] == "converted_to_metric"
        assert data["column"]["converted_metric_id"] == data["metric"]["id"]

        second = client.post(
            f"/api/dataset/{sample_dataset.id}/columns/{amount_col.id}/convert-metric"
        )
        assert second.status_code == 200
        assert second.json()["existing"] is True
        metrics = client.get(f"/api/dataset/{sample_dataset.id}/metrics").json()
        assert len([m for m in metrics if m["expr"] == "SUM(amount)"]) == 1

    def test_convert_dimension_candidate_column(self, client, db_session, sample_dataset, sample_datasource):
        """维度候选字段可转换为维度，枚举优先使用 AI 推荐。"""
        _, region_col = self._create_selected_table_with_columns(
            db_session, sample_dataset, sample_datasource
        )

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/columns/{region_col.id}/convert-dimension"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["dimension"]["column_name"] == "region"
        assert data["dimension"]["enum_values"] == ["华东", "华南"]
        assert data["column"]["review_status"] == "converted_to_dimension"
        assert data["column"]["converted_dimension_id"] == data["dimension"]["id"]

    def test_update_column_review_status(self, client, db_session, sample_dataset, sample_datasource):
        """字段审核状态可更新为 confirmed / ignored。"""
        amount_col, _ = self._create_selected_table_with_columns(
            db_session, sample_dataset, sample_datasource
        )

        resp = client.patch(
            f"/api/dataset/{sample_dataset.id}/columns/{amount_col.id}/review-status",
            json={"review_status": "ignored"},
        )
        assert resp.status_code == 200
        assert resp.json()["column"]["review_status"] == "ignored"

    def test_convert_column_requires_selected_table(
        self, client, db_session, sample_dataset, sample_datasource
    ):
        """不能转换当前数据集未选择表中的字段。"""
        table = models.SourceTable(
            datasource_id=sample_datasource.id,
            schema_name="public",
            table_name="unselected_orders",
        )
        db_session.add(table)
        db_session.flush()
        col = models.SourceColumn(
            table_id=table.id,
            column_name="amount",
            data_type="numeric",
            ai_semantic_role="metric_candidate",
            ai_suggested_agg="SUM",
        )
        db_session.add(col)
        db_session.commit()

        resp = client.post(
            f"/api/dataset/{sample_dataset.id}/columns/{col.id}/convert-metric"
        )
        assert resp.status_code == 404

    def test_add_dimension(self, client, sample_dataset):
        """向数据集添加维度"""
        payload = {
            "name": "channel",
            "display_name": "渠道",
            "column_name": "s.channel",
            "enum_values": ["线上", "线下"],
            "synonyms": ["通路"],
        }
        resp = client.post(f"/api/dataset/{sample_dataset.id}/dimension", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "channel"
        assert data["column_name"] == "s.channel"

    def test_business_term_crud_and_asset_link(self, client, sample_dataset):
        """业务术语可创建、更新并关联指标资产。"""
        payload = {
            "name": "gmv",
            "display_name": "商品交易总额",
            "term_type": "metric_concept",
            "definition": "商品成交总金额",
            "aliases": ["销售额", "成交额"],
            "status": "active",
        }
        resp = client.post(f"/api/dataset/{sample_dataset.id}/terms", json=payload)
        assert resp.status_code == 200
        term = resp.json()
        assert term["display_name"] == "商品交易总额"
        assert term["aliases"] == ["销售额", "成交额"]

        metric_id = client.get(f"/api/dataset/{sample_dataset.id}/metrics").json()[0]["id"]
        link_resp = client.post(
            f"/api/dataset/{sample_dataset.id}/terms/{term['id']}/link-assets",
            json={"links": [{"asset_type": "metric", "asset_id": metric_id}]},
        )
        assert link_resp.status_code == 200
        assert link_resp.json()["asset_links"][0]["asset_type"] == "metric"

        update_resp = client.put(
            f"/api/dataset/{sample_dataset.id}/terms/{term['id']}",
            json={"definition": "已确认的商品交易总额口径"},
        )
        assert update_resp.status_code == 200
        updated_term = update_resp.json()
        assert "已确认" in updated_term["definition"]
        assert updated_term["aliases"] == ["销售额", "成交额"]

    def test_business_term_duplicate_name_conflict(self, client, sample_dataset):
        """同一数据集下业务术语名称不能重复。"""
        payload = {"name": "revenue", "display_name": "收入", "term_type": "metric_concept"}
        assert client.post(f"/api/dataset/{sample_dataset.id}/terms", json=payload).status_code == 200
        resp = client.post(f"/api/dataset/{sample_dataset.id}/terms", json=payload)
        assert resp.status_code == 409

    def test_discover_business_terms(self, client, sample_dataset):
        """可从现有指标/维度发现候选术语。"""
        resp = client.post(f"/api/dataset/{sample_dataset.id}/terms/discover")
        assert resp.status_code == 200
        candidates = resp.json()["candidates"]
        names = {c["name"] for c in candidates}
        assert "gmv" in names
        assert "region" in names

    def test_check_business_term_conflicts(self, client, sample_dataset):
        """冲突检测能发现同义词碰撞。"""
        client.post(
            f"/api/dataset/{sample_dataset.id}/terms",
            json={
                "name": "gmv",
                "display_name": "商品交易总额",
                "term_type": "metric_concept",
                "aliases": ["销售额"],
            },
        )
        client.post(
            f"/api/dataset/{sample_dataset.id}/terms",
            json={
                "name": "revenue",
                "display_name": "收入",
                "term_type": "metric_concept",
                "aliases": ["销售额"],
            },
        )
        resp = client.post(f"/api/dataset/{sample_dataset.id}/terms/conflicts/check")
        assert resp.status_code == 200
        assert any(c["type"] == "alias_collision" for c in resp.json()["conflicts"])

    def test_list_metrics(self, client, sample_dataset):
        """获取数据集指标列表"""
        resp = client.get(f"/api/dataset/{sample_dataset.id}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {m["name"] for m in data}
        assert names == {"gmv", "order_count"}

    def test_list_dimensions(self, client, sample_dataset):
        """获取数据集维度列表"""
        resp = client.get(f"/api/dataset/{sample_dataset.id}/dimensions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert names == {"region", "category"}

    def test_delete_metric(self, client, sample_dataset):
        """删除指标"""
        # sample_dataset 已有 gmv 和 order_count
        metrics = client.get(f"/api/dataset/{sample_dataset.id}/metrics").json()
        gmv_id = next(m["id"] for m in metrics if m["name"] == "gmv")

        resp = client.delete(f"/api/dataset/{sample_dataset.id}/metric/{gmv_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 确认已删除
        metrics = client.get(f"/api/dataset/{sample_dataset.id}/metrics").json()
        assert len(metrics) == 1
        assert metrics[0]["name"] == "order_count"

    def test_delete_dimension(self, client, sample_dataset):
        """删除维度"""
        dims = client.get(f"/api/dataset/{sample_dataset.id}/dimensions").json()
        region_id = next(d["id"] for d in dims if d["name"] == "region")

        resp = client.delete(f"/api/dataset/{sample_dataset.id}/dimension/{region_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        dims = client.get(f"/api/dataset/{sample_dataset.id}/dimensions").json()
        assert len(dims) == 1
        assert dims[0]["name"] == "category"

    def test_filter_by_datasource(self, client, sample_datasource, sample_dataset):
        """按数据源 ID 过滤数据集"""
        # 创建第二个数据源和数据集

        client.app.dependency_overrides.get("get_db")
        # 通过 API 创建另一个
        resp = client.post(
            "/api/datasource",
            json={
                "name": "Other DB",
                "db_type": "postgres",
                "host": "other",
                "port": 5432,
                "database_name": "other",
                "username": "u",
                "password": "p",
            },
        )
        other_ds_id = resp.json()["id"]

        resp = client.post(
            "/api/dataset",
            json={
                "name": "Other Dataset",
                "datasource_id": other_ds_id,
            },
        )

        # 过滤
        resp = client.get(f"/api/dataset?datasource_id={sample_datasource.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "测试数据集"
