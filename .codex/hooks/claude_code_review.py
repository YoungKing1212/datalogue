# ============================================================
# File Name   : claude_code_review.py
# Description:
#   在 Codex 完成开发需求时调用 Claude Code 执行独立代码审查。
#
# Responsibilities:
#   - 识别开发完成标记，并限定审查范围为当前会话产生的提交和工作区变更。
#   - 调用 Claude Code CLI 进行只读审查，将结论回传给 Codex 并保存本地报告。
#   - 通过变更指纹和文件锁避免同一份代码被重复审查。
#
# Author      : Ken Yang
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REVIEW_MARKER = "<!-- CLAUDE_REVIEW_REQUIRED -->"
PASS_VERDICT = "CLAUDE_REVIEW_VERDICT: PASS"
FAIL_VERDICT = "CLAUDE_REVIEW_VERDICT: FAIL"
STATE_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 600
MAX_FEEDBACK_CHARS = 12_000


def _emit(payload: dict[str, Any]) -> None:
    """Hook 的标准输出必须始终是单个 JSON 对象。"""

    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _run_git(root: Path, *args: str, check: bool = True) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} 执行失败：{message}")
    return completed.stdout


def _resolve_git_root(cwd: str | None) -> Path | None:
    candidate = Path(cwd or os.getcwd()).expanduser().resolve()
    completed = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return Path(completed.stdout.strip()).resolve()


def _resolve_state_dir(root: Path) -> Path:
    override = os.environ.get("CLAUDE_CODE_REVIEW_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()

    git_dir_raw = _run_git(root, "rev-parse", "--git-dir").decode().strip()
    git_dir = Path(git_dir_raw)
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    # 运行状态放进 .git，避免审查报告自身污染下一轮 Git 变更指纹。
    return git_dir.resolve() / "codex-hooks" / "claude-code-review"


def _safe_session_id(session_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in session_id)
    return safe[:120] or "unknown-session"


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)  # 原子替换，避免 Codex 异常退出留下半份状态。


def _current_head(root: Path) -> str | None:
    value = _run_git(root, "rev-parse", "HEAD", check=False).decode().strip()
    return value or None


def _initialize_session(
    root: Path,
    state_path: Path,
    session_id: str,
) -> dict[str, Any]:
    state = _read_state(state_path)
    if state.get("version") == STATE_VERSION and state.get("root") == str(root):
        return state  # resume 事件不能覆盖会话真正的起始提交，否则会漏审已提交改动。

    state = {
        "version": STATE_VERSION,
        "session_id": session_id,
        "root": str(root),
        "base_head": _current_head(root),
        "reviewed": {},
        "created_at": int(time.time()),
    }
    _write_state(state_path, state)
    return state


def _hash_file(hasher: Any, path: Path) -> None:
    if path.is_symlink():
        hasher.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        return
    if not path.is_file():
        return
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)


def _build_change_fingerprint(
    root: Path,
    base_head: str | None,
    current_head: str | None,
) -> tuple[str, bool, list[str]]:
    status = _run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    staged = _run_git(root, "diff", "--cached", "--binary", "--no-ext-diff")
    unstaged = _run_git(root, "diff", "--binary", "--no-ext-diff")

    committed = b""
    if base_head and current_head and base_head != current_head:
        committed = _run_git(
            root,
            "diff",
            "--binary",
            "--no-ext-diff",
            f"{base_head}..{current_head}",
        )

    hasher = hashlib.sha256()
    for value in (str(STATE_VERSION).encode(), status, staged, unstaged, committed):
        hasher.update(value)

    untracked_paths: list[str] = []
    for entry in status.split(b"\0"):
        if not entry.startswith(b"?? "):
            continue
        relative = entry[3:].decode("utf-8", errors="surrogateescape")
        untracked_paths.append(relative)
        hasher.update(relative.encode("utf-8", errors="surrogateescape"))
        _hash_file(hasher, root / relative)  # 未跟踪文件不在 git diff 中，必须单独纳入去重指纹。

    has_commits = bool(base_head and current_head and base_head != current_head)
    return hasher.hexdigest(), bool(status) or has_commits, untracked_paths


def _find_claude() -> str | None:
    configured = os.environ.get("CLAUDE_CODE_REVIEW_BIN")
    if configured:
        return str(Path(configured).expanduser())
    discovered = shutil.which("claude")
    if discovered:
        return discovered
    fallbacks = (
        Path.home() / ".local" / "bin" / "claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    )
    return next((str(path) for path in fallbacks if path.is_file()), None)


def _build_prompt(
    root: Path,
    base_head: str | None,
    current_head: str | None,
    untracked_paths: list[str],
) -> str:
    committed_command = (
        f"git diff --find-renames --no-ext-diff {base_head}..{current_head}"
        if base_head and current_head and base_head != current_head
        else "本会话没有已提交的新提交"
    )
    untracked_summary = "、".join(untracked_paths[:30]) or "无"
    if len(untracked_paths) > 30:
        untracked_summary += f"（另有 {len(untracked_paths) - 30} 个）"

    return f"""你是本项目的独立代码审查员。请在只读模式下审查当前开发需求产生的代码变更，严禁修改文件、提交代码或执行有外部副作用的命令。

审查副本目录：{root}
注意：当前目录是 Hook 创建的隔离副本，不是真实工作区；只允许读取和分析。
会话起始提交：{base_head or '无法取得'}
当前提交：{current_head or '无法取得'}
未跟踪文件：{untracked_summary}

请自行读取 AGENTS.md 了解项目规范，并用下列命令确定审查范围：
1. {committed_command}
2. git diff --cached --find-renames --no-ext-diff
3. git diff --find-renames --no-ext-diff
4. git status --short
5. 对未跟踪的源码、测试和配置文件直接读取内容；二进制交付物只核对类型与变更意图，不展开全文。

审查重点：
- 真实缺陷、回归、边界条件、异常与降级路径；
- 安全、权限、敏感信息、并发、数据一致性和外部副作用；
- API/事件/数据库兼容性，以及测试是否覆盖关键行为；
- 是否违反 AGENTS.md 的项目约定。

输出要求：
- 使用中文 Markdown，先给结论，再列问题；每个问题标注 P0/P1/P2/P3、文件和行号、原因及可执行修复建议。
- 只报告能由变更证据支持的问题，不做无依据猜测，不把纯风格偏好当缺陷。
- 有任一需要修复的 P0/P1/P2 问题时，最后一行必须严格输出：{FAIL_VERDICT}
- 没有 P0/P1/P2 问题时，最后一行必须严格输出：{PASS_VERDICT}
"""


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _ensure_snapshot_parent(review_root: Path, target: Path) -> None:
    current = review_root
    for part in target.relative_to(review_root).parts[:-1]:
        current = current / part
        if current.is_symlink() or current.is_file():
            _remove_path(current)  # 禁止父级链接把复制或删除操作导向隔离目录之外。
        current.mkdir(exist_ok=True)


def _copy_review_snapshot(
    root: Path,
    current_head: str | None,
    fingerprint: str,
) -> tuple[Path, Path]:
    container = Path(
        tempfile.mkdtemp(prefix=f"datalogue-claude-{fingerprint[:12]}-"),
    )
    review_root = container / "repo"
    try:
        cloned = subprocess.run(
            ["git", "clone", "--quiet", "--local", "--no-hardlinks", str(root), str(review_root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if cloned.returncode != 0:
            details = cloned.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"创建 Claude Code 隔离审查副本失败：{details}")
        if current_head:
            _run_git(review_root, "checkout", "--quiet", "--detach", current_head)
        _run_git(review_root, "remote", "remove", "origin")  # 副本无需回写来源仓库，也不暴露真实路径。

        paths = _run_git(
            root,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ).split(b"\0")
        for raw_path in paths:
            if not raw_path:
                continue
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            source = root / relative
            target = review_root / relative
            _ensure_snapshot_parent(review_root, target)
            if source.is_symlink():
                _remove_path(target)
                target.symlink_to(os.readlink(source))
            elif source.is_file():
                if target.is_symlink() or target.is_dir():
                    _remove_path(target)  # copy2 会跟随目标链接，必须先解除隔离逃逸路径。
                shutil.copy2(source, target)
            elif not source.exists():
                _remove_path(target)  # 工作区已删除的 tracked 文件也必须从副本移除。

        return container, review_root
    except Exception:
        _cleanup_review_snapshot(container)
        raise


def _cleanup_review_snapshot(container: Path) -> None:
    if not container.exists():
        return
    # 即便未来为副本增加只读权限，也先恢复所有者写权限，确保临时目录可清理。
    for path in sorted(container.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            continue
        try:
            path.chmod(path.stat().st_mode | 0o200)
        except OSError:
            pass
    shutil.rmtree(container, ignore_errors=True)


def _sandbox_profile(protected_root: Path) -> str:
    escaped = str(protected_root).replace("\\", "\\\\").replace('"', '\\"')
    return f'(version 1)\n(allow default)\n(deny file-write* (subpath "{escaped}"))'


def _run_claude(
    root: Path,
    prompt: str,
    protected_root: Path,
) -> tuple[str, str]:
    claude = _find_claude()
    if not claude:
        return "ERROR", "未找到 Claude Code CLI；请确认 `claude` 已安装并完成登录。"

    # Claude Code 的非交互模式可与 plan 权限组合，运行时只允许读取和只读命令。
    command = [
        claude,
        "--print",
        "--permission-mode",
        "plan",
        "--output-format",
        "text",
        "--no-session-persistence",
        "--safe-mode",
        "--setting-sources",
        "",
    ]
    model = os.environ.get("CLAUDE_CODE_REVIEW_MODEL")
    if model:
        command.extend(["--model", model])
    command.append(prompt)

    sandbox_exec = shutil.which("sandbox-exec")
    if sandbox_exec:
        # macOS 上额外禁止 Claude Code 及其子进程写入真实仓库；审查副本位于系统临时目录。
        command = [sandbox_exec, "-p", _sandbox_profile(protected_root), *command]

    timeout_raw = os.environ.get("CLAUDE_CODE_REVIEW_TIMEOUT_SECONDS", "")
    try:
        timeout = max(30, int(timeout_raw or DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS

    try:
        claude_env = os.environ.copy()
        for key in tuple(claude_env):
            if key in {"ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL"} or key.startswith(
                "ANTHROPIC_DEFAULT_",
            ):
                claude_env.pop(key, None)  # 禁止 shell 环境把本次 Claude 审查重新路由到兼容供应商。
        completed = subprocess.run(
            command,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
            env=claude_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "ERROR", f"Claude Code CLI 调用失败：{exc}"

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    provider_output = f"{stdout}\n{stderr}".lower()
    if "api.kimi.com" in provider_output or "moonshot" in provider_output:
        return "ERROR", "检测到 Claude Code 被路由至 Kimi/Moonshot，已拒绝本次审查。"
    if completed.returncode != 0:
        details = stderr or stdout or f"退出码 {completed.returncode}"
        return "ERROR", f"Claude Code CLI 返回失败：{details}"
    if FAIL_VERDICT in stdout:
        return "FAIL", stdout
    if PASS_VERDICT in stdout:
        return "PASS", stdout
    return "ERROR", "Claude Code 未返回约定的 PASS/FAIL 结论。\n\n" + (stdout or stderr)


def _save_report(
    state_dir: Path,
    fingerprint: str,
    verdict: str,
    review: str,
) -> Path:
    reports_dir = state_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"{timestamp}-{fingerprint[:12]}.md"
    path.write_text(
        f"# Claude Code 代码审查\n\n- 结论：{verdict}\n- 变更指纹：`{fingerprint}`\n\n{review}\n",
        encoding="utf-8",
    )
    return path


def _feedback(verdict: str, review: str, report_path: Path) -> dict[str, str]:
    clipped = review[:MAX_FEEDBACK_CHARS]
    if verdict == "PASS":
        action = (
            "Claude Code 独立代码审查已通过。不要再次输出 Claude Code 完成标记；"
            "请在最终回复中向用户说明审查已通过。"
        )
    elif verdict == "FAIL":
        action = (
            "Claude Code 发现需要修复的 P0/P1/P2 问题。请核对并修复成立的问题、重新验证；"
            "代码发生变化且再次完成后，重新输出 Claude Code 完成标记以触发复审。"
        )
    else:
        action = (
            "Claude Code 审查未能正常完成。不要在同一份变更上重复输出 Claude Code 完成标记；"
            "请向用户明确说明失败原因和报告路径。"
        )
    reason = f"{action}\n\n完整报告：{report_path}\n\n{clipped}"
    return {"decision": "block", "reason": reason}


def _handle_stop(
    payload: dict[str, Any],
    root: Path,
    state_dir: Path,
    state_path: Path,
    session_id: str,
) -> dict[str, Any]:
    last_message = str(payload.get("last_assistant_message") or "")
    if REVIEW_MARKER not in last_message:
        return {}

    state = _initialize_session(root, state_path, session_id)
    current_head = _current_head(root)
    base_head = state.get("base_head")
    fingerprint, has_changes, untracked_paths = _build_change_fingerprint(
        root,
        str(base_head) if base_head else None,
        current_head,
    )
    if not has_changes:
        return {}  # 防止纯问答或误标记触发一次没有审查对象的外部模型调用。

    reviewed = state.setdefault("reviewed", {})
    if fingerprint in reviewed:
        return {}  # Stop 被 block 后会再次触发；同一份代码只能审查一次。

    container, review_root = _copy_review_snapshot(
        root,
        current_head,
        fingerprint,
    )
    try:
        snapshot_fingerprint, _, snapshot_untracked = _build_change_fingerprint(
            review_root,
            str(base_head) if base_head else None,
            current_head,
        )
        prompt = _build_prompt(
            review_root,
            str(base_head) if base_head else None,
            current_head,
            snapshot_untracked,
        )
        verdict, review = _run_claude(review_root, prompt, root)
        fingerprint_after, _, _ = _build_change_fingerprint(
            review_root,
            str(base_head) if base_head else None,
            current_head,
        )
        if fingerprint_after != snapshot_fingerprint:
            verdict = "ERROR"
            review = (
                "Claude Code 在审查期间修改了隔离副本，真实工作区未受影响；"
                "本次结论作废，请检查 Claude Code 权限或提示注入风险。"
            )
    finally:
        _cleanup_review_snapshot(container)
    report_path = _save_report(state_dir, fingerprint, verdict, review)

    reviewed[fingerprint] = {
        "verdict": verdict,
        "report_path": str(report_path),
        "reviewed_at": int(time.time()),
    }
    # 长会话只保留最近 30 个指纹，防止本地状态无限增长。
    if len(reviewed) > 30:
        ordered = sorted(reviewed.items(), key=lambda item: item[1].get("reviewed_at", 0))
        state["reviewed"] = dict(ordered[-30:])
    _write_state(state_path, state)
    return _feedback(verdict, review, report_path)


def _unexpected_error_feedback(payload: dict[str, Any], exc: Exception) -> dict[str, str]:
    event = str(payload.get("hook_event_name") or "")
    message = str(payload.get("last_assistant_message") or "")
    if event != "Stop" or REVIEW_MARKER not in message or payload.get("stop_hook_active"):
        return {}
    return {
        "decision": "block",
        "reason": (
            "Claude Code 代码审查 Hook 在调用前异常终止，未生成审查报告。"
            "不要在同一份变更上重复添加完成标记，请向用户说明本次审查未执行。\n\n"
            f"失败原因：{exc}"
        ),
    }


def main() -> int:
    payload: dict[str, Any] = {}
    try:
        loaded = json.load(sys.stdin)
        if not isinstance(loaded, dict):
            _emit({})
            return 0
        payload = loaded

        root = _resolve_git_root(payload.get("cwd"))
        if root is None:
            _emit({})
            return 0

        session_id = str(payload.get("session_id") or "unknown-session")
        state_dir = _resolve_state_dir(root)
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / f"{_safe_session_id(session_id)}.json"
        lock_path = state_dir / f"{_safe_session_id(session_id)}.lock"

        with lock_path.open("a+", encoding="utf-8") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                _emit({})  # 根目录和子目录同时发现 Hook 时，只允许第一个进程调用 Claude Code。
                return 0

            event = str(payload.get("hook_event_name") or "")
            if event == "SessionStart":
                _initialize_session(root, state_path, session_id)
                response: dict[str, Any] = {}
            elif event == "Stop":
                response = _handle_stop(payload, root, state_dir, state_path, session_id)
            else:
                response = {}
            _emit(response)
            return 0
    except Exception as exc:  # 完成标记对应的异常必须显式回送；其他事件仍保持 fail-open。
        print(f"Claude Code code review hook error: {exc}", file=sys.stderr)
        _emit(_unexpected_error_feedback(payload, exc))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
