# ============================================================
# File Name   : test_agentic_shell_chat_stream_removed.py
# Description:
#   /api/chat/stream 硬切删除测试。
#
# Responsibilities:
#   - 确认旧 chat stream 不再是执行入口。
#   - 防止后续改动重新把 /api/chat/stream 接回 runtime。
#
# Author      : yangkai
# Created On  : 2026-07-02
# ============================================================


def test_chat_stream_route_is_removed(client):
    response = client.post("/api/chat/stream", json={"question": "统计合同总金额"})

    assert response.status_code in {404, 405}
