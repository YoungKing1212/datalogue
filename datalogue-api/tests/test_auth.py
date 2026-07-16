# ============================================================
# File Name   : test_auth.py
# Description:
#   认证接口回归测试。
#
# Responsibilities:
#   - 校验注册、登录、获取当前用户与刷新令牌流程。
#   - 验证错误凭证和未登录访问时的返回状态。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from fastapi.routing import APIRoute

from app.api.deps import get_current_user, require_api_admin, require_api_user
from app.core import models
from app.core.security import encrypt_auth_password
from app.main import app


def _login(client, username: str, plain_password: str):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password_enc": encrypt_auth_password(plain_password)},
    )


def _login_admin(client, db_session):
    from app.core import models
    from app.core.security import hash_password

    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    if admin is None:
        admin = models.User(
            username="admin",
            hashed_password=hash_password("admin"),
            full_name="系统管理员",
            role="admin",
            is_superuser=True,
            is_active=True,
        )
        db_session.add(admin)
        db_session.commit()

    login_res = _login(client, "admin", "admin")
    assert login_res.status_code == 200
    return login_res.json()["access_token"]


def test_register_login_me_flow(client, db_session):
    admin_token = _login_admin(client, db_session)
    register_payload = {
        "username": "ken",
        "password": "secret123",
        "email": "ken@example.com",
        "full_name": "Ken Yang",
    }
    register_res = client.post(
        "/api/auth/register",
        json=register_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert register_res.status_code == 201
    assert register_res.json()["username"] == "ken"
    assert register_res.json()["role"] == "user"

    login_res = _login(client, "ken", "secret123")
    assert login_res.status_code == 200
    access_token = login_res.json()["access_token"]
    assert access_token

    me_res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "ken"
    assert me_res.json()["role"] == "user"


def test_refresh_and_logout_flow(client, db_session):
    admin_token = _login_admin(client, db_session)
    create_res = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "secret123", "email": "alice@example.com"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_res.status_code == 201
    login_res = _login(client, "alice", "secret123")
    assert login_res.status_code == 200

    refresh_res = client.post("/api/auth/refresh", json={})
    assert refresh_res.status_code == 200
    refreshed_token = refresh_res.json()["access_token"]
    assert refreshed_token

    logout_res = client.post(
        "/api/auth/logout",
        json={},
    )
    assert logout_res.status_code == 204

    refresh_after_logout = client.post("/api/auth/refresh", json={})
    assert refresh_after_logout.status_code == 401


def test_login_failure_and_me_unauthorized(client):
    login_res = _login(client, "not-exists", "wrong")
    assert login_res.status_code == 401

    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 401


def test_register_requires_admin(client):
    register_res = client.post(
        "/api/auth/register",
        json={"username": "noadmin", "password": "secret123"},
    )
    assert register_res.status_code == 401


def test_business_api_uses_unified_login_interceptor(client):
    """业务路由未携带 access token 时，应在进入端点前统一返回 401。"""

    saved_override = client.app.dependency_overrides.pop(require_api_user)
    try:
        response = client.get("/api/dataset")
    finally:
        client.app.dependency_overrides[require_api_user] = saved_override

    assert response.status_code == 401


def test_llm_control_plane_requires_admin(client):
    """普通登录用户即使通过统一登录拦截，也不能访问模型密钥控制面。"""

    saved_override = client.app.dependency_overrides.pop(require_api_admin)
    client.app.dependency_overrides[get_current_user] = lambda: models.User(
        id=2,
        username="normal-user",
        role="user",
        is_superuser=False,
        is_active=True,
    )
    try:
        response = client.get("/api/agentscope-control/credentials")
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)
        client.app.dependency_overrides[require_api_admin] = saved_override

    assert response.status_code == 403


def test_all_api_routes_keep_unified_auth_boundary():
    """除登录、刷新和退出外，所有 /api 路由都必须挂载统一鉴权依赖。"""

    public_routes = {
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/refresh"),
        ("POST", "/api/auth/logout"),
    }
    admin_prefixes = ("/api/llm", "/api/agentscope-control")

    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        methods = route.methods or set()
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        for method in methods:
            if (method, route.path) in public_routes:
                continue
            expected_dependency = (
                require_api_admin if route.path.startswith(admin_prefixes) else require_api_user
            )
            assert expected_dependency in dependency_calls, (
                f"{method} {route.path} 未挂载统一鉴权依赖"
            )


def test_manage_user_edit_reset_password_and_delete(client, db_session):
    admin_token = _login_admin(client, db_session)

    create_res = client.post(
        "/api/auth/register",
        json={
            "username": "manage_target",
            "password": "secret123",
            "email": "target@example.com",
            "full_name": "待管理用户",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_res.status_code == 201
    user_id = create_res.json()["id"]

    update_res = client.patch(
        f"/api/auth/users/{user_id}",
        json={
            "full_name": "已更新姓名",
            "email": "updated@example.com",
            "role": "admin",
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["full_name"] == "已更新姓名"
    assert update_res.json()["email"] == "updated@example.com"
    assert update_res.json()["role"] == "admin"

    reset_res = client.post(
        f"/api/auth/users/{user_id}/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reset_res.status_code == 204

    relogin_res = _login(client, "manage_target", "manage_target@123456")
    assert relogin_res.status_code == 200

    delete_res = client.delete(
        f"/api/auth/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_res.status_code == 204

    login_after_delete = _login(client, "manage_target", "manage_target@123456")
    assert login_after_delete.status_code == 401


def test_login_requires_encrypted_password(client, db_session):
    _login_admin(client, db_session)
    bad_res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert bad_res.status_code == 422


def test_bootstrap_admin_preserves_existing_account(monkeypatch, db_session):
    from app import main as main_module
    from app.core import models
    from app.core.security import hash_password, verify_password

    admin = models.User(
        username=main_module.settings.BOOTSTRAP_ADMIN_USERNAME,
        hashed_password=hash_password("custom-password"),
        full_name="已维护管理员",
        role="user",
        is_superuser=False,
        is_active=False,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    class SessionProxy:
        """避免 bootstrap 测试关闭 pytest 统一管理的数据库会话。"""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            pass

    monkeypatch.setattr(main_module, "SessionLocal", lambda: SessionProxy(db_session))

    main_module._bootstrap_admin_if_needed()
    db_session.refresh(admin)

    assert verify_password("custom-password", admin.hashed_password)
    assert admin.full_name == "已维护管理员"
    assert admin.role == "user"
    assert admin.is_superuser is False
    assert admin.is_active is False
