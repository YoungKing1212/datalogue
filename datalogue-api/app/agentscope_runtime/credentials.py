# ============================================================
# File Name   : credentials.py
# Description:
#   Datalogue 注入 AgentScope Service 的 credential schema facade。
#
# Responsibilities:
#   - 暴露 DatalogueLLMCredential 作为新目录的稳定入口。
#   - 保持 credential schema 与旧实现一致，避免设置页模型配置迁移时出现双实现。
#
# Author      : yangkai
# Created On  : 2026-07-09
# ============================================================

from __future__ import annotations

from app.runtime.engine.credentials import DatalogueLLMCredential

__all__ = ["DatalogueLLMCredential"]
