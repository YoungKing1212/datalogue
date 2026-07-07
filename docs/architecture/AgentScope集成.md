# AgentScope 2.0 集成

## 一、集成方式

AgentScope Service 作为 **FastAPI 子应用** 挂载在 Datalogue API 下：

```python
# app/main.py
mount_agentscope_service(app, settings)
# 挂载路径: /agentscope
```

AgentScope Service 配置（环境变量）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENTSCOPE_SERVICE_ENABLED` | true | 是否启用 |
| `AGENTSCOPE_MOUNT_PATH` | /agentscope | 挂载路径 |
| `AGENTSCOPE_REDIS_HOST` | localhost | Redis 地址 |
| `AGENTSCOPE_REDIS_PORT` | 6379 | Redis 端口 |
| `AGENTSCOPE_WORKSPACE_BASEDIR` | /data/agentscope/workspaces | 工作区目录 |
| `AGENTSCOPE_WORKSPACE_TTL_SECONDS` | 3600 | 工作区 TTL |

## 二、AgentScope Service 内部组件

| 组件 | 说明 |
|------|------|
| **RedisStorage** | Agent/Session/Credential/Message/Schedule 持久化 |
| **RedisMessageBus** | 会话锁、回放日志、收件箱队列、唤醒信号 |
| **LocalWorkspaceManager** | TTL 缓存工作区（文件系统/MCP/skill） |
| **Datalogue Credentials** | LLM 凭证（通过 OpenAPI Schema 动态注册） |
| **Datalogue Tools** | 自定义工具（dataset_query 等） |

## 三、通信方式

```
Datalogue API
    │ HTTP (httpx)
    ▼
AgentScope Service (子应用 in-process)
    │
    ├── POST /agent → 创建/获取 Agent
    ├── POST /sessions → 创建 Session
    ├── POST /chat → 触发聊天
    └── GET /sessions/{id}/stream → SSE 事件流
```

## 四、子应用生命周期

```
Datalogue API 启动
    │
    ├── lifespan()
    │   ├── Base.metadata.create_all()
    │   ├── setup_agentscope_tracing()
    │   └── AsyncExitStack 管理子应用 lifespan
    │       └── AgentScope App 的 Redis 连接池
    │
    └── mount_agentscope_service()
        ├── create_embedded_agentscope_app(settings)
        │   ├── RedisStorage(host, port)
        │   ├── RedisMessageBus(host, port)
        │   └── LocalWorkspaceManager(basedir, ttl)
        └── root_app.mount("/agentscope", agentscope_app)
```

## 五、P0 主链与安全边界

- 唯一产品主链是 `POST /api/agent-team/tasks/stream → AgentScope Agent Team → BI Worker Tools`；Datalogue API 只通过 AgentScope Service 子应用驱动 Leader / Worker 协作。
- Leader Agent 是控制面，负责规划、候选确认、AgentCreate、TeamSay 收敛和多 Worker 扩展；BI Worker Agent 是执行/诊断面，负责通过 Datalogue tools 调用受控 QueryPlan、repair 和 artifact 能力。
- direct-query 仅作为内部 fallback、开发调试或兼容入口；不能把它宣传成产品主入口，也不能为了提速绕过 Leader。
- repair 是一等链路，阶段固定为 Failure Classifier、Private Diagnosis、Repair Planner、User Confirmation、Retry Executor、Artifact Writer。
- SQL、schema、raw rows、原始报错和 RepairPatch 主体只允许在 runtime/tool 私有诊断层流转；AgentScope LLM prompt、SSE、用户可见消息、artifact 摘要和 OpenViking 普通上下文只能获得安全摘要与 refs。

## 六、扩展 Worker 暂缓边界

Report / Python / Audit Worker 可以保留在长期 prompt、事件协议或 worker type 设计中，但当前阶段暂停继续扩展实现。只有当 BI Worker 主链满足“一轮成功率稳定、repair 可闭环、artifact 必达、最终回答不泄露内部计划、Workbench checkpoint 可回放、日志能区分 Leader / Worker / Tool / DB”后，才允许恢复扩展 Worker。

运行时接手和部署前，按 `docs/operations/运行时健康检查.md` 检查 AgentScope Service、Redis、Credential、Leader Agent、Session stream、BI Tool、Artifact API 和 Frontend version。

## 七、Datalogue 注册到 AgentScope 的组件

1. **Leader Agent 规格**（`registry.py`）:
   - 包含 Datalogue 自定义工具（dataset_query, generate_report）
   - 预设 system prompt

2. **Credentials**（`credentials.py`）:
   - 通过 `extra_credentials` 注册自定义凭证类型
   - 提供 JSON Schema 供前端动态渲染表单

3. **Tools**（`tools.py`）:
   - BI 查询与 repair 工具，桥接到 Datalogue BI 工具链，包括候选筛选、上下文准备、schema 证据、QueryPlan 执行、修复计划和 artifact 写入。
   - 在 Worker Agent 上下文中可用，但工具返回值必须先经过安全投影，不能把 SQL、schema、raw rows 或原始报错泄漏到用户可见层。

4. **Progress Bridge**（`progress_bridge.py`）:
   - 后台任务进度订阅通道

5. **Task Context**（`task_context.py`）:
   - 将 Datalogue task 上下文写入 Redis
   - 供 AgentScope Service 侧 Worker 中间件反查
