# ============================================================
# File Name   : seed_langfuse_prompts.py
# Description:
#   将当前代码内 Prompt 批量创建到 Langfuse Prompt Manager。
#
# Responsibilities:
#   - 读取 Datalogue Prompt 注册表，生成待同步清单。
#   - 支持 dry-run 预览和 --apply 实际创建 Langfuse prompt 版本。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.observability.prompt_registry import (  # noqa: E402
    get_registered_prompts,
    sync_registered_prompts,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把 Datalogue 当前代码内 Prompt 创建到 Langfuse Prompt Manager。"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入 Langfuse；不传时只预览待同步 Prompt。",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="写入的 Langfuse label，默认读取 LANGFUSE_PROMPT_LABEL。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使远程同 label 内容未变化，也创建一个新版本。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果，便于脚本集成。",
    )
    return parser


def _create_langfuse_client():
    settings = get_settings()
    try:
        from langfuse import Langfuse
    except Exception as exc:  # pragma: no cover - 依赖缺失时给 CLI 友好错误
        raise RuntimeError("当前 Python 环境未安装 langfuse，请先安装项目依赖。") from exc

    base_url = settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise RuntimeError("缺少 LANGFUSE_PUBLIC_KEY 或 LANGFUSE_SECRET_KEY。")
    if not base_url:
        raise RuntimeError("缺少 LANGFUSE_BASE_URL 或 LANGFUSE_HOST。")

    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        base_url=base_url,
        environment=settings.LANGFUSE_ENVIRONMENT,
        release=settings.LANGFUSE_RELEASE,
    )


def _print_table(results: list[dict[str, Any]]) -> None:
    print("name | 中文名称 | 中文描述 | label | action | version | reason")
    print("--- | --- | --- | --- | --- | --- | ---")
    for item in results:
        print(
            f"{item['name']} | {item.get('display_name') or ''} | "
            f"{item.get('description') or ''} | {item['label']} | {item['action']} | "
            f"{item.get('version') or ''} | {item.get('reason') or ''}"
        )


def main() -> int:
    args = _build_parser().parse_args()
    settings = get_settings()
    label = args.label or settings.LANGFUSE_PROMPT_LABEL
    prompts = get_registered_prompts()

    if args.apply:
        client = _create_langfuse_client()
    else:
        client = None

    results = sync_registered_prompts(
        client,
        prompts=prompts,
        label=label,
        apply=args.apply,
        skip_unchanged=not args.force,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"Langfuse Prompt seed mode: {mode}, label={label}, count={len(results)}")
        _print_table(results)
        if not args.apply:
            print("\n未写入 Langfuse。确认无误后执行：")
            print("./.venv/bin/python scripts/seed_langfuse_prompts.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
