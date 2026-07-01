# ============================================================
# File Name   : test_remove_observability_stack.py
# Description:
#   防止 Observability 技术栈重新进入运行时代码和部署配置。
#
# Responsibilities:
#   - 扫描后端运行时代码、脚本、依赖和本地 compose 配置。
#   - 确保不再出现 Observability SDK、服务、环境变量或同步脚本。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCAN_PATHS = [
    ROOT / "app",
    ROOT / "scripts",
    ROOT / "pyproject.toml",
    ROOT / "requirements.txt",
    ROOT / "requirements-enterprise.txt",
    ROOT / ".env.example",
    ROOT / "docker-compose.yml",
]


def _iter_scan_files():
    for path in SCAN_PATHS:
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and child.suffix in {".py", ".toml", ".txt", ".yml", ".yaml", ".env"}:
                yield child


def test_runtime_stack_has_no_langfuse_references():
    hits: list[str] = []
    for path in _iter_scan_files():
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "langfuse" in line.lower():
                hits.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")

    assert hits == []
