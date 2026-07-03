# ============================================================
# File Name   : test_legacy_chat_removed.py
# Description:
#   旧聊天流入口下线后的结构守护测试。
#
# Responsibilities:
#   - 防止重新引入 app.api.chat 旧实现模块。
#   - 防止重新暴露 /api/chat 旧路由。
#
# Author      : yangkai
# Created On  : 2026-07-03
# ============================================================

from pathlib import Path

from app.main import app


def test_legacy_chat_api_module_has_been_removed():
    """旧聊天流实现模块应从代码树删除，避免继续维护废弃链路。"""

    assert not Path("app/api/chat.py").exists()


def test_legacy_chat_routes_are_not_registered():
    """旧 /api/chat 路由组整体下线，包括 stream 和 feedback 兼容入口。"""

    registered_paths = {route.path for route in app.routes}

    assert "/api/chat/stream" not in registered_paths
    assert "/api/chat/feedback" not in registered_paths
