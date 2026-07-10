# ============================================================
# File Name   : test_navigation_counts.py
# Description:
#   侧栏导航统计接口的 API 回归测试。
#
# Responsibilities:
#   - 验证左侧功能栏 badge 使用数据库真实数量。
#   - 验证没有持久化真相源的功能项不会返回假数量。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from app.core import models
from app.api.deps import get_current_user


def _authenticated_client(client):
    """导航统计属于登录后工作台信息，测试中用依赖覆盖模拟已登录用户。"""

    client.app.dependency_overrides[get_current_user] = lambda: models.User(
        id=1,
        username="tester",
        is_active=True,
    )
    return client


def test_navigation_counts_require_login(client):
    """未登录不能读取系统规模统计，避免暴露数据集、数据源等数量。"""

    response = client.get("/api/navigation/counts")

    assert response.status_code == 401


def test_navigation_counts_return_database_backed_values(client, db_session, sample_dataset):
    """侧栏数量必须来自数据库表，不能继续使用前端写死演示数字。"""

    db_session.add(models.AgentTeamTask(task_id="task-1", task_source="chat", task_type="bi_query"))
    db_session.add(models.AgentTeamTask(task_id="task-2", task_source="chat", task_type="bi_query"))
    db_session.add(models.Conversation(title="正常会话", archived=False))
    db_session.add(models.Conversation(title="归档会话", archived=True))
    db_session.add(
        models.BusinessTerm(
            dataset_id=sample_dataset.id,
            name="gross_margin",
            display_name="毛利率",
            definition="毛利 / 收入",
            status="active",
        )
    )
    db_session.add(
        models.AnalysisBlueprint(
            dataset_id=sample_dataset.id,
            name="区域归因",
            status="active",
        )
    )
    db_session.add(
        models.SemanticValidationCase(
            dataset_id=sample_dataset.id,
            question="为什么收入下降",
            status="failed",
        )
    )
    db_session.add(
        models.SemanticValidationCase(
            dataset_id=sample_dataset.id,
            question="通过样例",
            status="passed",
        )
    )
    db_session.commit()

    _authenticated_client(client)
    response = client.get("/api/navigation/counts")

    assert response.status_code == 200
    assert response.json() == {
        "dashboard": 2,
        "history": 1,
        "datasets": 1,
        "knowledge": 2,
        "review": 1,
        "datasources": 1,
        "apis": None,
    }
