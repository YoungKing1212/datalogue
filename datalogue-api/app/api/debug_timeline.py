# ============================================================
# File Name   : debug_timeline.py
# Description:
#   BI Worker 调试 timeline 查看 API + 自包含 HTML 页面。
#
# Responsibilities:
#   - 扫描 Redis 中的 timeline 缓存 key，列出可用的调试记录。
#   - 按 worker_session_id + reply_id 读取单条 timeline 内容（JSON）。
#   - 提供自包含 HTML 页面，无需外部前端依赖即可查看步骤时序。
#
# 安全说明：本路由仅用于本地开发排障，数据来自 raw_agent_logs_enabled()
# 开关控制下的临时 Redis 缓存，默认不写入。访问受环境变量
# DATALOGUE_DEBUG_TIMELINE_ENABLED 控制，默认关闭。
#
# Author      : yangkai
# Created On  : 2026-07-14
# ============================================================

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_TIMELINE_KEY_PREFIX = "datalogue:bi_worker_timeline"
_MAX_KEYS_RETURNED = 50


def _debug_timeline_enabled() -> bool:
    """调试 timeline 查看器开关：显式设置环境变量后开启。"""
    env = os.getenv("DATALOGUE_DEBUG_TIMELINE_ENABLED", "false").strip().lower()
    return env in ("1", "true", "yes", "on")


def _check_enabled() -> None:
    if not _debug_timeline_enabled():
        raise HTTPException(
            status_code=404,
            detail="debug timeline viewer is disabled (set DATALOGUE_DEBUG_TIMELINE_ENABLED=true)",
        )


async def _redis_client() -> Redis:
    """创建独立 Redis 客户端，复用 AgentScope Redis 配置。"""
    settings = get_settings()
    redis_url = settings.AGENTSCOPE_REDIS_URL or "redis://localhost:6379/0"
    return Redis.from_url(redis_url, decode_responses=True)


def _parse_timeline_key(key: str) -> dict[str, str] | None:
    """解析 key，提取 worker_session_id 和 reply_id。"""
    suffix = key.removeprefix(f"{_TIMELINE_KEY_PREFIX}:")
    if suffix == key:
        return None
    parts = suffix.split(":", 1)
    if len(parts) != 2:
        return None
    return {"worker_session_id": parts[0], "reply_id": parts[1]}


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------


@router.get("/timelines")
async def list_timelines(
    limit: int = Query(default=20, ge=1, le=_MAX_KEYS_RETURNED),
):
    """列出 Redis 中最近的 timeline 缓存 key。"""
    _check_enabled()

    client = await _redis_client()
    try:
        keys: list[str] = []
        cursor = 0
        pattern = f"{_TIMELINE_KEY_PREFIX}:*"
        while True:
            cursor, batch = await client.scan(cursor, match=pattern, count=50)
            keys.extend(batch)
            if cursor == 0 or len(keys) >= _MAX_KEYS_RETURNED:
                break

        results: list[dict[str, Any]] = []
        for key in keys[:limit]:
            parsed = _parse_timeline_key(key)
            if parsed is None:
                continue
            ttl = await client.ttl(key)
            results.append({**parsed, "ttl_seconds": ttl})

        results.sort(key=lambda r: r["ttl_seconds"], reverse=True)
        return JSONResponse({"count": len(results), "items": results})
    finally:
        await client.aclose()


@router.get("/timelines/{worker_session_id}/{reply_id}")
async def get_timeline(worker_session_id: str, reply_id: str):
    """读取单条 timeline 的完整内容。"""
    _check_enabled()

    client = await _redis_client()
    try:
        key = f"{_TIMELINE_KEY_PREFIX}:{worker_session_id}:{reply_id}"
        raw = await client.get(key)
        if not raw:
            raise HTTPException(status_code=404, detail="timeline not found or expired")
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=404, detail="timeline data corrupted")
        return JSONResponse(data)
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# 自包含 HTML 查看器
# ---------------------------------------------------------------------------

_TIMELINE_VIEWER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BI Worker Timeline 调试查看器</title>
<style>
  :root {
    --bg: #f8fafc; --card-bg: #fff; --border: #e2e8f0;
    --text: #0f172a; --text-muted: #64748b; --text-sm: #475569;
    --thinking: #dbeafe; --thinking-border: #93c5fd; --thinking-text: #1e40af;
    --tool-call: #fef3c7; --tool-call-border: #fcd34d; --tool-call-text: #92400e;
    --tool-result: #dcfce7; --tool-result-border: #86efac; --tool-result-text: #166534;
    --text-block: #f1f5f9; --text-block-border: #cbd5e1; --text-block-text: #334155;
    --accent: #3b82f6; --danger: #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }
  .app { display: flex; height: 100vh; }
  .sidebar { width: 320px; min-width: 320px; background: var(--card-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  .sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); }
  .sidebar-header h1 { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
  .sidebar-header p { font-size: 12px; color: var(--text-muted); }
  .sidebar-list { flex: 1; overflow-y: auto; padding: 8px; }
  .sidebar-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; border: 1px solid transparent; font-size: 13px; transition: background .15s; }
  .sidebar-item:hover { background: #f1f5f9; }
  .sidebar-item.active { background: #eff6ff; border-color: var(--accent); }
  .sidebar-item .id { font-family: monospace; font-size: 11px; color: var(--text-muted); word-break: break-all; }
  .sidebar-item .meta { color: var(--text-muted); font-size: 11px; margin-top: 2px; }
  .main { flex: 1; overflow-y: auto; padding: 24px; }
  .empty-state { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 14px; }
  .timeline-step { border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; background: var(--card-bg); }
  .step-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; cursor: pointer; user-select: none; }
  .step-index { font-size: 12px; color: var(--text-muted); font-family: monospace; min-width: 36px; }
  .step-badge { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
  .badge-thinking { background: var(--thinking); color: var(--thinking-text); border: 1px solid var(--thinking-border); }
  .badge-tool_call { background: var(--tool-call); color: var(--tool-call-text); border: 1px solid var(--tool-call-border); }
  .badge-tool_result { background: var(--tool-result); color: var(--tool-result-text); border: 1px solid var(--tool-result-border); }
  .badge-text { background: var(--text-block); color: var(--text-block-text); border: 1px solid var(--text-block-border); }
  .step-tool-name { font-size: 13px; font-weight: 500; color: var(--text-sm); }
  .step-body { font-size: 13px; line-height: 1.6; color: var(--text-sm); white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; background: #f8fafc; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12px; display: none; }
  .step-body.open { display: block; }
  .step-expand-icon { font-size: 12px; color: var(--text-muted); transition: transform .2s; }
  .step-expand-icon.open { transform: rotate(90deg); }
  .header-row { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
  .header-row h2 { font-size: 18px; font-weight: 600; }
  .header-meta { font-size: 12px; color: var(--text-muted); }
  .step-summary { font-size: 12px; color: var(--text-muted); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 600px; }
  .error-banner { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
  .refresh-btn { font-size: 12px; padding: 4px 12px; border: 1px solid var(--border); border-radius: 4px; background: var(--card-bg); cursor: pointer; color: var(--text-sm); }
  .refresh-btn:hover { background: #f1f5f9; }
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1>🧪 BI Worker Timeline</h1>
      <p>调试查看器 · 实时读取 Redis 缓存</p>
    </div>
    <div class="sidebar-list" id="sidebar-list">
      <div class="empty-state">加载中...</div>
    </div>
  </aside>
  <main class="main" id="main-content">
    <div class="empty-state">← 从左侧选择一个 timeline 查看详情</div>
  </main>
</div>
<script>
const API_BASE = '/api/debug';

let activeKey = null;

async function loadList() {
  const listEl = document.getElementById('sidebar-list');
  try {
    const resp = await fetch(API_BASE + '/timelines?limit=50');
    if (!resp.ok) {
      listEl.innerHTML = '<div class="empty-state">加载失败: ' + resp.status + '</div>';
      return;
    }
    const data = await resp.json();
    if (!data.items || data.items.length === 0) {
      listEl.innerHTML = '<div class="empty-state" style="padding:20px">暂无 timeline 记录<br><small style="color:#94a3b8">请先开启 AGENT_DEBUG_RAW_LOGS=true 触发一次问数</small></div>';
      return;
    }
    listEl.innerHTML = data.items.map(item => {
      const key = item.worker_session_id + '/' + item.reply_id;
      const shortSid = item.worker_session_id.slice(0, 12) + '...';
      const shortRid = item.reply_id.slice(0, 12) + '...';
      const ttl = item.ttl_seconds > 0 ? Math.floor(item.ttl_seconds / 60) + 'm' + (item.ttl_seconds % 60) + 's' : '已过期';
      return '<div class="sidebar-item" data-key="' + key + '" onclick="selectTimeline(\'' + item.worker_session_id + '\',\'' + item.reply_id + '\')">'
        + '<div class="id">session: ' + shortSid + '</div>'
        + '<div class="id">reply: ' + shortRid + '</div>'
        + '<div class="meta">TTL: ' + ttl + '</div>'
        + '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div class="empty-state">网络错误: ' + e.message + '</div>';
  }
}

async function selectTimeline(wsid, rid) {
  activeKey = wsid + '/' + rid;
  // highlight
  document.querySelectorAll('.sidebar-item').forEach(el => {
    el.classList.toggle('active', el.dataset.key === activeKey);
  });
  const main = document.getElementById('main-content');
  main.innerHTML = '<div class="empty-state">加载中...</div>';
  try {
    const resp = await fetch(API_BASE + '/timelines/' + encodeURIComponent(wsid) + '/' + encodeURIComponent(rid));
    if (!resp.ok) {
      main.innerHTML = '<div class="error-banner">加载失败: HTTP ' + resp.status + '</div>';
      return;
    }
    const data = await resp.json();
    const timeline = data.timeline || [];
    if (!timeline.length) {
      main.innerHTML = '<div class="empty-state">该 timeline 为空（无步骤记录）</div>';
      return;
    }
    let html = '<div class="header-row"><div><h2>Timeline 详情</h2>'
      + '<div class="header-meta">session: ' + wsid + ' | reply: ' + rid + ' | 共 ' + timeline.length + ' 步</div>'
      + '</div></div>';
    timeline.forEach(step => {
      const stepType = step.type || 'unknown';
      const badgeClass = 'badge-' + stepType;
      const toolName = step.tool_name ? ' <span class="step-tool-name">' + escapeHtml(step.tool_name) + '</span>' : '';
      let bodyContent = '';
      if (stepType === 'thinking') {
        bodyContent = step.thinking || '';
      } else if (stepType === 'tool_call') {
        bodyContent = '📥 入参:\\n' + (step.input || '(空)');
      } else if (stepType === 'tool_result') {
        bodyContent = '📤 状态: ' + (step.state || '?') + '\\n📤 输出:\\n' + (step.output || '(空)');
      } else if (stepType === 'text') {
        bodyContent = step.text || '';
      }
      const summary = bodyContent.slice(0, 120).replace(/\\n/g, ' ');
      html += '<div class="timeline-step">'
        + '<div class="step-header" onclick="toggleStep(this)">'
        + '<span class="step-expand-icon">▶</span>'
        + '<span class="step-index">#' + step.step + '</span>'
        + '<span class="step-badge ' + badgeClass + '">' + stepType + '</span>'
        + toolName
        + '</div>'
        + '<div class="step-summary">' + escapeHtml(summary) + '</div>'
        + '<div class="step-body">' + escapeHtml(bodyContent) + '</div>'
        + '</div>';
    });
    main.innerHTML = html;
  } catch (e) {
    main.innerHTML = '<div class="error-banner">加载出错: ' + e.message + '</div>';
  }
}

function toggleStep(header) {
  const body = header.nextElementSibling.nextElementSibling;
  const icon = header.querySelector('.step-expand-icon');
  const isOpen = body.classList.contains('open');
  body.classList.toggle('open');
  icon.classList.toggle('open');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// init
loadList();
</script>
</body>
</html>"""


@router.get("/viewer", response_class=HTMLResponse)
async def timeline_viewer():
    """自包含 HTML 调试查看器页面。"""
    _check_enabled()
    return HTMLResponse(_TIMELINE_VIEWER_HTML)


@router.get("/viewer/{worker_session_id}/{reply_id}", response_class=HTMLResponse)
async def timeline_viewer_direct(worker_session_id: str, reply_id: str):
    """直接打开指定 timeline 的查看器（带页内跳转参数）。"""
    _check_enabled()
    # 注入一段 JS 在页面加载后自动选中指定的 timeline
    html = _TIMELINE_VIEWER_HTML.replace(
        "// init\nloadList();",
        "// init (direct link)\nloadList().then(function() { selectTimeline('"
        + worker_session_id
        + "','"
        + reply_id
        + "'); });",
    )
    return HTMLResponse(html)
