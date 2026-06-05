"""
语义数据集管理 API 测试
"""

from app import models


class TestDatasetAPI:
    """测试 /api/dataset 路由"""

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
