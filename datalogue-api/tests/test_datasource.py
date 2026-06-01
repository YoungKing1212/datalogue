"""
数据源管理 API 测试
"""


class TestDatasourceAPI:
    """测试 /api/datasource 路由"""

    def test_list_datasources_empty(self, client):
        """空数据源列表应返回 []"""
        resp = client.get("/api/datasource")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_datasource(self, client):
        """创建数据源"""
        payload = {
            "name": "MySQL 生产库",
            "db_type": "mysql",
            "host": "192.168.1.10",
            "port": 3306,
            "database_name": "production",
            "username": "admin",
            "password": "secret123",
        }
        resp = client.post("/api/datasource", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "MySQL 生产库"
        assert data["db_type"] == "mysql"
        assert data["host"] == "192.168.1.10"
        assert data["port"] == 3306
        assert data["id"] is not None
        # 密码不应返回
        assert "password" not in data
        assert "password_enc" not in data

    def test_get_datasource(self, client):
        """获取单个数据源详情"""
        # 先创建
        payload = {
            "name": "Test DB",
            "db_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database_name": "test",
            "username": "user",
            "password": "pass",
        }
        created = client.post("/api/datasource", json=payload).json()

        resp = client.get(f"/api/datasource/{created['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test DB"

    def test_get_datasource_not_found(self, client):
        """获取不存在的数据源应返回 404"""
        resp = client.get("/api/datasource/99999")
        assert resp.status_code == 404

    def test_update_datasource(self, client):
        """更新数据源"""
        payload = {
            "name": "Old Name",
            "db_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database_name": "db",
            "username": "user",
            "password": "pass",
        }
        created = client.post("/api/datasource", json=payload).json()

        resp = client.put(
            f"/api/datasource/{created['id']}",
            json={"name": "New Name", "host": "newhost"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["host"] == "newhost"
        assert data["port"] == 5432  # 未修改字段保持原值

    def test_delete_datasource(self, client):
        """删除数据源"""
        payload = {
            "name": "To Delete",
            "db_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database_name": "db",
            "username": "user",
            "password": "pass",
        }
        created = client.post("/api/datasource", json=payload).json()

        resp = client.delete(f"/api/datasource/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 确认已删除
        resp = client.get(f"/api/datasource/{created['id']}")
        assert resp.status_code == 404

    def test_list_datasources_with_data(self, client):
        """创建后列表应包含数据"""
        for i in range(3):
            client.post(
                "/api/datasource",
                json={
                    "name": f"DB {i}",
                    "db_type": "postgres",
                    "host": "localhost",
                    "port": 5432,
                    "database_name": f"db{i}",
                    "username": "user",
                    "password": "pass",
                },
            )

        resp = client.get("/api/datasource")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        # 默认按 id desc 排序
        assert data[0]["name"] == "DB 2"
