# Datalogue API

数语 AI 原生智能问数平台后端服务。

## 技术栈

- FastAPI + Uvicorn
- SQLAlchemy 2.0 + Alembic
- PostgreSQL + pgvector
- LangGraph (Phase 2 接入)

## 快速开始

### 1. 环境准备

```bash
# 复制环境变量
cp .env.example .env
# 编辑 .env 填入你的数据库地址和 LLM API Key
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 数据库迁移

```bash
# 创建数据库（首次）
createdb datalogue

# 运行迁移
alembic upgrade head
```

### 4. 启动服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/docs 查看自动生成的 API 文档。

## 项目结构

```
datalogue-api/
├── main.py                 # FastAPI 入口
├── requirements.txt
├── alembic/                # 数据库迁移
│   └── versions/
├── app/
│   ├── core/               # 配置、数据库、安全
│   │   ├── config.py
│   │   ├── database.py
│   │   └── security.py
│   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── datasource.py
│   │   ├── dataset.py
│   │   └── conversation.py
│   ├── schemas/            # Pydantic 校验模型
│   ├── api/                # API 路由
│   │   ├── datasource.py
│   │   ├── dataset.py
│   │   ├── conversation.py
│   │   └── chat.py
│   ├── services/           # 业务逻辑
│   └── graph/              # LangGraph Agent 工作流
└── tests/
```

## API 概览

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/datasource` | 数据源列表 |
| POST | `/api/datasource` | 创建数据源 |
| GET | `/api/dataset` | 数据集列表 |
| POST | `/api/dataset` | 创建数据集 |
| POST | `/api/dataset/{id}/metric` | 添加指标 |
| POST | `/api/dataset/{id}/dimension` | 添加维度 |
| GET | `/api/conversation` | 对话列表 |
| GET | `/api/conversation/{id}` | 对话详情 |
| POST | `/api/chat/stream` | 流式问数 (SSE) |
| POST | `/api/chat/feedback` | 人工反馈 |
