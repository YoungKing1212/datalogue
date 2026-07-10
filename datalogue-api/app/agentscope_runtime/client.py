# ============================================================
# File Name   : client.py
# Description:
#   AgentScope Service REST/SSE client 的目标 facade。
#
# Responsibilities:
#   - 暴露 AgentScopeServiceClient 作为新目录的稳定入口。
#   - 避免在目录治理早期复制 HTTP 协议适配逻辑。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.client import DEFAULT_AGENTSCOPE_USER_ID, AgentScopeServiceClient

__all__ = ["DEFAULT_AGENTSCOPE_USER_ID", "AgentScopeServiceClient"]
