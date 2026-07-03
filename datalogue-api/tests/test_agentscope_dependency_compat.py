# ============================================================
# File Name   : test_agentscope_dependency_compat.py
# Description:
#   校验 AgentScope 2.0 运行依赖在项目虚拟环境内可正常导入。
#
# Responsibilities:
#   - 捕捉 AgentScope 与 MCP SDK 版本不兼容导致 uvicorn worker 启动失败的问题。
#   - 保证 middleware/toolkit 依赖的 AgentScope tool 模块可用。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================

from __future__ import annotations


def test_agentscope_toolkit_imports_with_project_dependency_set():
    """AgentScope Toolkit 导入失败会直接导致 FastAPI worker 无法启动。"""

    from agentscope.tool import Toolkit
    from mcp.client import streamable_http

    assert Toolkit is not None
    assert hasattr(streamable_http, "streamable_http_client")
