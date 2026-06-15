# ============================================================
# File Name   : test_think_utils.py
# Description:
#   Think 标签清理工具回归测试。
#
# Responsibilities:
#   - 验证最终文本中的 Think 块清理。
#   - 验证流式 token 跨 chunk 的 Think 块过滤。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from app.utils.think import (
    filter_think_stream_chunk,
    flush_think_stream_state,
    new_think_stream_state,
    strip_think_blocks,
)


def test_strip_think_blocks_supports_case_and_attributes():
    """完整文本清理应兼容大小写和带属性的 Think 标签。"""

    text = "<Think mode='trace'>内部过程</Think>答案"

    assert strip_think_blocks(text) == "答案"


def test_filter_think_stream_chunk_handles_split_tags():
    """流式过滤应拦截跨 chunk 的 Think 标签和内部内容。"""

    state = new_think_stream_state()
    chunks = ["<Thi", "nk>内部", "</Thi", "nk>最终"]

    visible = "".join(filter_think_stream_chunk(chunk, state) for chunk in chunks)
    visible += flush_think_stream_state(state)

    assert visible == "最终"


def test_filter_think_stream_chunk_flushes_plain_suffix():
    """流结束时不应丢失被暂存的普通文本尾巴。"""

    state = new_think_stream_state()
    visible = filter_think_stream_chunk("最终<thi", state)
    visible += flush_think_stream_state(state)

    assert visible == "最终<thi"
