# ============================================================
# File Name   : json_utils.py
# Description:
#   JSON 提取和规范化工具。
#
# Responsibilities:
#   - 从模型混合输出中解析 JSON 片段。
#   - 为图节点提供宽容 JSON 处理能力。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# LLM 输出 JSON 解析工具 — 容错处理 markdown code block + 裸 JSON

import json
import re
from typing import Any


def safe_json_parse(text: str) -> dict:
    """从 LLM 输出中安全提取 JSON 对象。

    匹配优先级：
    1) ```json ... ``` 代码块（**优先**，避免 LLM 在 <think> 里写的 ```sql 示例被误吃）
    2) 内容以 { 开头的 ``` ... ``` 代码块
    3) 文本中第一个 { ... } 区间
    4) json.loads 失败时返回空 dict
    """
    if not text:
        return {}

    # 1) 显式 ```json ... ``` 代码块
    m = re.search(r"```json\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            result: dict[str, Any] = json.loads(m.group(1).strip())
            return result
        except json.JSONDecodeError:
            pass

    # 2) 任意 ``` ... ``` 代码块，要求内容以 { 开头
    m2 = re.search(r"```\w*\s*(\{.*?\})```", text, re.DOTALL)
    if m2:
        try:
            result = json.loads(m2.group(1).strip())
            return result
        except json.JSONDecodeError:
            pass

    # 3) 任意 { ... } 区间
    m3 = re.search(r"\{.*\}", text, re.DOTALL)
    if m3:
        try:
            result = json.loads(m3.group(0).strip())
            return result
        except json.JSONDecodeError:
            pass

    return {}
