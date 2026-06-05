# ============================================================
# File Name   : logging.py
# Description:
#   API 服务日志初始化。
#
# Responsibilities:
#   - 配置结构化和彩色日志输出。
#   - 提供可复用的日志初始化入口。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 统一日志配置 — 带 ANSI 颜色，支持 app.* 命名空间
import logging
import os
import sys

# ── 颜色定义 ─────────────────────────────────────────
_COLORS = {
    "DEBUG": "\033[36m",  # 青色
    "INFO": "\033[32m",  # 绿色
    "WARNING": "\033[33m",  # 黄色
    "ERROR": "\033[31m",  # 红色
    "CRITICAL": "\033[1;31m",  # 亮红
    "RESET": "\033[0m",
    "DIM": "\033[90m",  # 灰色（时间、模块名）
    "BOLD": "\033[1m",
}

# 非终端环境自动禁用颜色
_USE_COLOR = sys.stdout.isatty()


def _c(text: str, color: str) -> str:
    return f"{_COLORS[color]}{text}{_COLORS['RESET']}" if _USE_COLOR else text


class ColoredFormatter(logging.Formatter):
    """带 ANSI 颜色的 Formatter，非终端环境自动降级为纯文本。"""

    def __init__(self, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt, datefmt)

    def format(self, record: logging.LogRecord) -> str:
        level_color = _COLORS.get(record.levelname, _COLORS["RESET"])
        record.levelname_colored = _c(f"{record.levelname:8s}", record.levelname)
        record.name_dim = _c(record.name, "DIM")
        record.asctime_dim = _c(self.formatTime(record), "DIM")
        return super().format(record)


def setup_logging(level: str = "INFO") -> None:
    """统一初始化 app.* / sqlalchemy / uvicorn 的日志配置，全部带颜色输出到 stdout。"""
    app_root = logging.getLogger("app")
    app_root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除旧 handler，防止重复
    if app_root.handlers:
        app_root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    fmt = "%(asctime_dim)s %(levelname_colored)s" " │ %(name_dim)s │ %(message)s"
    formatter = ColoredFormatter(fmt, datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    app_root.addHandler(handler)

    # SQLAlchemy 引擎日志（SQL 语句、参数、执行时间）。
    # 默认 WARNING（关闭），需要看 SQL 时设环境变量 SQL_LOG_LEVEL=INFO 或 DEBUG。
    sqlalchemy_level = getattr(
        logging,
        os.getenv("SQL_LOG_LEVEL", "WARNING").upper(),
        logging.WARNING,
    )
    for sa_name in ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
        sa_log = logging.getLogger(sa_name)
        sa_log.setLevel(sqlalchemy_level)
        # 只加 handler 如果还没有，避免重复
        if not sa_log.handlers:
            sa_log.addHandler(handler)

    # uvicorn / fastapi 的日志也染色（通过 monkey-patch 它们的 formatter）
    for name in ("uvicorn", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        if lg.handlers:
            for h in lg.handlers:
                if isinstance(h, logging.StreamHandler):
                    h.setFormatter(
                        ColoredFormatter(
                            f"%(asctime_dim)s %(levelname_colored)s │ {_COLORS['DIM']}%(name)s{_COLORS['RESET']} │ %(message)s",
                            datefmt="%H:%M:%S",
                        )
                    )
