# ============================================================
# File Name   : __init__.py
# Description:
#   LLM 适配包兼容入口。
#
# Responsibilities:
#   - 保留 app.graph.llm 的历史导入路径，避免一次性迁移所有 LLM 调用方。
#   - 明确旧 LangGraph workflow/nodes/state 已退役，不再从包入口导出。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

__all__ = []
