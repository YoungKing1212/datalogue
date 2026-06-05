#!/usr/bin/env python3
"""Send a text message to a Feishu custom bot webhook."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def build_sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_text(webhook: str, text: str, secret: str | None = None) -> None:
    payload: dict[str, object] = {
        "msg_type": "text",
        "content": {"text": text},
    }

    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = build_sign(timestamp, secret)

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Feishu webhook HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise SystemExit(f"Feishu webhook request failed: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        result = {}

    if result.get("code") not in (None, 0):
        raise SystemExit(f"Feishu webhook returned error: {body}")

    print("Feishu message sent.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "message",
        nargs="?",
        help="Message text. If omitted, text is read from stdin.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env.local")

    args = parse_args()
    text = args.message if args.message is not None else sys.stdin.read().strip()
    if not text:
        raise SystemExit("Message text is empty.")

    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        raise SystemExit("Missing FEISHU_WEBHOOK in environment or .env.local.")

    send_text(webhook=webhook, text=text, secret=os.environ.get("FEISHU_SECRET"))


if __name__ == "__main__":
    main()
