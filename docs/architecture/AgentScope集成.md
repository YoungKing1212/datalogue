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

## 五、Datalogue 注册到 AgentScope 的组件

1. **Leader Agent 规格**（`registry.py`）:
   - 包含 Datalogue 自定义工具（dataset_query, generate_report）
   - 预设 system prompt

2. **Credentials**（`credentials.py`）:
   - 通过 `extra_credentials` 注册自定义凭证类型
   - 提供 JSON Schema 供前端动态渲染表单

3. **Tools**（`tools.py`）:
   - `dataset_query`: BI 查询工具，桥接到 Datalogue BI 工具链
   - 在 Worker Agent 上下文中可用

4. **Progress Bridge**（`progress_bridge.py`）:
   - 后台任务进度订阅通道

5. **Task Context**（`task_context.py`）:
   - 将 Datalogue task 上下文写入 Redis
   - 供 AgentScope Service 侧 Worker 中间件反查
