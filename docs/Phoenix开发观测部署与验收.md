# Phoenix 开发观测后台部署与验收

Phoenix 是数语内部开发人员使用的链路观测后台，不对终端用户开放。它接收问数任务根链、Agent、模型、工具、查询计划、受控 SQL 执行和产物写入的 OpenTelemetry 数据；SQL、Schema、模型 I/O 和工具结果按团队约定可见，但任何数据库凭证、HTTP `Authorization`/`Cookie`、API Key 都不得写入 span 属性或日志。Phoenix 与业务共用 PostgreSQL 的 `datalogue` 数据库，但所有 Phoenix 表均位于独立的 `phoenix` Schema。

## 首次部署

在仓库根目录的部署机密 `.env`（不要提交）设置以下值：

```dotenv
DB_PASSWORD=<现有 datalogue PostgreSQL 密码>
PHOENIX_SECRET=<至少 32 字符的随机 JWT 签名密钥>
PHOENIX_ADMIN_INITIAL_PASSWORD=<符合强密码规则的管理员密码>
PHOENIX_PORT=6006
```

先启动根 Compose 中的 PostgreSQL，再使用独立 Compose 启动 Phoenix：

```bash
docker compose up -d db
docker compose -f docker-compose.phoenix.yml up -d
```

通过 SSH 隧道访问管理页面，避免将 UI 或 OTLP collector 暴露到公网：

```bash
ssh -N -L 6006:127.0.0.1:6006 <部署机用户>@<部署机地址>
```

浏览器打开 `http://127.0.0.1:6006`，以 `admin@localhost` 登录。管理员应完成以下配置：

1. 创建 system API key，名称为 `datalogue-otel-writer`；只在创建时复制一次。
2. 创建开发人员账号并赋予 `viewer`，开发人员只读 Trace；账号、角色及 system key 均由管理员维护。
3. 将 system key 写回部署机密 `.env`，然后启用 API 导出：

```dotenv
PHOENIX_SYSTEM_API_KEY=<datalogue-otel-writer 的值>
PHOENIX_PROJECT_NAME=datalogue-production
AGENTSCOPE_OTEL_TRACING_ENABLED=true
AGENTSCOPE_OTEL_EXPORTER_ENABLED=true
```

最后执行 `docker compose up -d api` 重建 API 容器。API 不依赖 Phoenix 的健康状态：Phoenix 停机时 Batch exporter 会失败但不会阻断问数主链或 `/health`。

## 本地直启后端

本地开发通常不使用 Docker Compose 启动 API。独立 Phoenix Compose 已将 UI 与 OTLP gRPC 绑定到宿主机回环地址：

```bash
docker compose up -d db
docker compose -f docker-compose.phoenix.yml up -d
```

在 `datalogue-api/.env` 中填入刚创建的 system key，并开启 exporter：

```dotenv
AGENTSCOPE_OTEL_EXPORTER_ENABLED=true
AGENTSCOPE_OTEL_EXPORTER_ENDPOINT=127.0.0.1:4317
AGENTSCOPE_OTEL_EXPORTER_INSECURE=true
AGENTSCOPE_OTEL_EXPORTER_AUTH_TOKEN=<datalogue-otel-writer 的值>
AGENTSCOPE_OTEL_EXPORTER_PROJECT_NAME=datalogue-development
```

然后按原有方式在宿主机启动 API。`4317` 仅绑定到 `127.0.0.1`，不会对局域网或公网暴露。

## 验收清单

1. 发起一次真实问数。在 `datalogue-production` 项目中应出现 `datalogue.agent_team.task` 根 span；AgentScope 的 Agent Reply、模型、工具及 HTTP 调用须是其后代。
2. 模型 span 应展示 `gen_ai.usage.*` 对应的输入、输出和总 Token；`datalogue.bi.sql.execute` 应展示 SQL 与耗时；`datalogue.artifact.persist` 应展示 artifact 引用。
3. 停止 Phoenix 后再次发起问数，确认 SSE、任务状态和 `/health` 均正常；恢复 Phoenix 后继续接收新链路。
4. 确认项目默认留存为 14 天；Phoenix 表仅位于 `datalogue` 数据库的 `phoenix` Schema，不应出现在业务默认 `public` Schema。

14 天稳定运行并完成上述验收后，另行清理旧 Redis timeline 缓存及其测试；本次仅移除了其自建 `/api/debug` 展示层，缓存仍作为无 UI 的短期排障兜底。
