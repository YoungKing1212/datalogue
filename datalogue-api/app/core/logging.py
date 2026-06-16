# ============================================================
# File Name   : logging.py
# Description:
#   API 服务日志初始化。
#
# Responsibilities:
#   - 配置结构化和彩色日志输出（stdout）。
#   - 可选地将日志持久化到轮转文件（app.log / error.log）。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

# 统一日志配置 — 带 ANSI 颜色，支持 app.* 命名空间
import logging
import logging.handlers
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


# 写入文件时使用纯文本格式（无 ANSI 转义码）
_FILE_FMT = "%(asctime)s %(levelname)-8s │ %(name)s │ %(message)s"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _make_rotating_handler(
    path: str,
    level: int,
    max_bytes: int,
    backup_count: int,
) -> logging.handlers.RotatingFileHandler:
    """创建轮转文件 handler，使用纯文本格式。"""
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_FILE_DATEFMT))
    return handler


def setup_logging(
    level: str = "INFO",
    log_dir: str = "",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 7,
) -> None:
    """统一初始化 app.* / sqlalchemy / uvicorn 的日志配置。

    Args:
        level:        app.* 日志级别（INFO / DEBUG / WARNING …）
        log_dir:      日志文件目录；空字符串表示仅输出到 stdout，不写文件
        max_bytes:    单个日志文件最大字节数，超出后轮转
        backup_count: 保留的历史文件份数（app.log.1 … app.log.N）
    """
    app_root = logging.getLogger("app")
    app_root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除旧 handler，防止重复
    if app_root.handlers:
        app_root.handlers.clear()

    # ── stdout 彩色 handler ──────────────────────────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    fmt = "%(asctime_dim)s %(levelname_colored)s │ %(name_dim)s │ %(message)s"
    stdout_handler.setFormatter(ColoredFormatter(fmt, datefmt="%H:%M:%S"))
    app_root.addHandler(stdout_handler)

    # ── 文件持久化 handler（可选） ────────────────────────────
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

        # app.log — 全量日志，按大小轮转
        app_root.addHandler(
            _make_rotating_handler(
                os.path.join(log_dir, "app.log"),
                level=getattr(logging, level.upper(), logging.INFO),
                max_bytes=max_bytes,
                backup_count=backup_count,
            )
        )

        # error.log — 仅 ERROR 及以上，便于快速定位异常
        app_root.addHandler(
            _make_rotating_handler(
                os.path.join(log_dir, "error.log"),
                level=logging.ERROR,
                max_bytes=max_bytes,
                backup_count=backup_count,
            )
        )

    # ── SQLAlchemy 引擎日志 ──────────────────────────────────
    # 默认 WARNING（关闭），需要看 SQL 时设环境变量 SQL_LOG_LEVEL=INFO 或 DEBUG。
    sqlalchemy_level = getattr(
        logging,
        os.getenv("SQL_LOG_LEVEL", "WARNING").upper(),
        logging.WARNING,
    )
    for sa_name in ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
        sa_log = logging.getLogger(sa_name)
        sa_log.setLevel(sqlalchemy_level)
        if not sa_log.handlers:
            sa_log.addHandler(stdout_handler)

    # ── uvicorn / fastapi 染色 ────────────────────────────────
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
