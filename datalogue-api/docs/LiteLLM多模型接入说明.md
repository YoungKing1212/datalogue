# LiteLLM 多模型接入说明

## 配置优先级

数语的 LLM 调用按以下顺序解析模型配置：

1. 前端“系统设置 / LLM 模型”中保存的角色绑定模型。
2. `default` 角色绑定模型。
3. `.env` 中的 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL`。

底层继续使用 `ChatOpenAI`，它只负责 OpenAI-compatible 协议通信。LiteLLM Proxy、私有模型网关和大多数国产模型 OpenAI 兼容接口都可以通过同一协议接入。

## LiteLLM Proxy 示例

LiteLLM Proxy 中可以把真实供应商模型注册成业务别名：

```yaml
model_list:
  - model_name: datalogue-intent
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: datalogue-sql
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

  - model_name: datalogue-report
    litellm_params:
      model: qwen/qwen-plus
      api_key: os.environ/DASHSCOPE_API_KEY
```

启动 LiteLLM Proxy 后，在数语前端新增模型配置：

- `Base URL`: `http://localhost:4000/v1`
- `模型名`: `datalogue-intent` / `datalogue-sql` / `datalogue-report`
- `API Key`: LiteLLM Proxy Key；如果 Proxy 未启用鉴权，可保存占位值。

## 角色绑定

系统内置角色：

- `default`：未单独绑定角色时的默认模型。
- `intent`：意图理解与入口路由。
- `dsl`：DSL / SQL 生成。
- `sql_audit`：SQL 执行失败诊断。
- `report`：最终报告解释，负责流式回答。
- `annotation`：表和字段自动标注。
- `blueprint`：分析蓝图 SQL 草稿和业务场景理解。

推荐先配置 `default`，再为 `dsl` 和 `report` 绑定更适合的模型。

## 密钥存储

前端写入的 API Key 会通过后端 `AES_KEY` 加密后保存到 `llm_model_config.api_key_enc`，接口响应只返回 `api_key_set`，不会回传明文 Key。编辑模型时 API Key 留空不会覆盖旧密钥。

## 环境变量兜底

如果数据库中没有启用模型或角色未绑定，系统继续使用 `.env`：

```env
OPENAI_API_KEY=your-openai-compatible-api-key
OPENAI_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL=MiniMax-M2.7
LLM_TIMEOUT_SECONDS=60
```

这保证本地开发和迁移前环境不受影响。
