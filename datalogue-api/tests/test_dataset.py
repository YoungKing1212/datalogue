"""
语义数据集管理 API 测试
"""


class TestDatasetAPI:
    """测试 /api/dataset 路由"""

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
