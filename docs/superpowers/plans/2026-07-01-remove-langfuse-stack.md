# Remove Langfuse Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除项目运行时代码、依赖和本地部署里的 Langfuse 技术栈，暂时不引入替代 Trace provider。

**Architecture:** 保留问数主链所需的最小本地 step 状态和消息反馈；外部观测 SDK、Prompt 远端同步、Trace 深链、Trace UI/API 和本地 Langfuse compose 服务全部退出。运行时保留无外部副作用的 no-op tracer 兼容既有调用点，避免本次拆除扩大到 AgentScope 主链重构。

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, Docker Compose.

---

### Task 1: Runtime Guard

**Files:**
- Create: `datalogue-api/tests/test_remove_langfuse_stack.py`

- [ ] **Step 1: Write the failing test**
  - 新增扫描测试，覆盖 `app/`、`scripts/`、`pyproject.toml`、`requirements.txt`、`.env.example` 和 `docker-compose.yml`。

- [ ] **Step 2: Run test to verify it fails**
  - Run: `cd datalogue-api && python3 -m pytest tests/test_remove_langfuse_stack.py -q`
  - Expected: FAIL，指出现存 Langfuse 配置、依赖或 SDK 调用。

### Task 2: Backend Removal

**Files:**
- Modify: `datalogue-api/app/core/config.py`
- Modify: `datalogue-api/app/services/observability/tracer.py`
- Modify: `datalogue-api/app/services/observability/prompts.py`
- Modify: `datalogue-api/app/services/observability/feedback.py`
- Modify: `datalogue-api/app/api/chat.py`
- Modify: `datalogue-api/app/api/conversation.py`
- Delete: `datalogue-api/scripts/seed_langfuse_prompts.py`

- [ ] **Step 1: Remove settings and SDK calls**
  - 删除 `LANGFUSE_*` settings、SDK import、远端 prompt 拉取、远端 score 写入。

- [ ] **Step 2: Keep local no-op compatibility**
  - `DatalogueTracer` 不创建外部 trace，不 flush，不 score，只保留主链调用签名。

### Task 3: Deploy and UI Removal

**Files:**
- Modify: `datalogue-api/docker-compose.yml`
- Delete: `datalogue-api/docker/postgres/init-langfuse-db.sh`
- Modify: `datalogue-api/pyproject.toml`
- Modify: `datalogue-api/requirements.txt`
- Modify: `datalogue-api/uv.lock`
- Modify: `datalogue-web/src/App.jsx`
- Modify: `datalogue-web/src/components/sidebar.jsx`

- [ ] **Step 1: Remove deployment services and dependency**
  - 删除 Langfuse service、worker、ClickHouse、MinIO、Redis、初始化脚本和 Python dependency。

- [ ] **Step 2: Hide Trace UI entry points**
  - 去掉查询审计路由和入口；聊天页不主动打开 Trace 面板。

### Task 4: Verification and Memory

**Files:**
- Modify: `.codex/project-memory.md`

- [ ] **Step 1: Run focused backend tests**
  - Run: `cd datalogue-api && python3 -m pytest tests/test_remove_langfuse_stack.py tests/test_observability.py tests/test_chat.py -q`

- [ ] **Step 2: Run frontend checks**
  - Run: `cd datalogue-web && npm run lint && npm run build`

- [ ] **Step 3: Update project memory**
  - 记录完成时间、涉及文件、关键改动、验证方式和残留风险。
