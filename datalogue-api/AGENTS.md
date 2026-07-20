# AGENTS.md

## 项目身份

- 当前目录：数语后端 API（`datalogue-api`）。
- 默认使用中文回复，并继承仓库根目录 `AGENTS.md`；本文件只保留后端特有约束。

## 技术栈与主链

- Python 3.11、FastAPI、SQLAlchemy 2、Pydantic 2、AgentScope 2.0.3。
- 主链：`POST /api/agent-team/tasks/stream` → `AgentTeamTaskRuntime` → `AgentScopeServiceTaskRunner` → AgentScope Service → Agent Team → Datalogue BI 工具 → 查询编译与执行。
- `app/graph/` 是旧 LangGraph 残留，仅保留少量 LLM 调用辅助；新能力默认沿用 AgentScope 主链。

## 必须保持的业务边界

- BI Worker/LLM 只能调用 Datalogue 暴露的安全查询工具，不得自行生成或执行 SQL，也不得读取原始行数据。
- SQL、schema、原始行、数据库原始错误和修复细节只能存在于私有诊断层，不得进入 LLM prompt、用户可见 SSE、artifact 摘要、普通上下文或交接文档正文。
- LLM prompt 统一放在 `app/prompts/`，业务代码从该模块导入，避免散落 prompt 字符串。
- `TeamCreate`、`AgentCreate`、`TeamSay`、`TeamDelete` 使用 AgentScope 官方工具，不自研替代协作协议。

## 后端执行偏好

- 默认只查看和修改直接相关模块，优先运行对应测试文件或最小复现；不因普通修复自动执行全量真实链路、全仓测试或跨层取证。
- 只有问题无法由局部证据定位、涉及 SSE/状态回放/跨层契约，或用户明确要求时，才检查页面回放、trace、后端日志、prompt/token 和最终 payload。
- 截图及临时验证产物放系统临时目录，不写入仓库。
- 新增 Python 文件沿用相邻文件风格，用简短中文注释或文档字符串说明职责；只为复杂边界和非直观决策添加关键注释。

## 按需参考

- 任务路由：`../docs/上下文入口.md`
- 架构与链路：`../docs/architecture/`
- AgentScope 官方文档：`~/code_place/study/agentscope-docs/`
