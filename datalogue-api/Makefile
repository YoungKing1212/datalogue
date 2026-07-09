# ============================================================================
# Datalogue API — Makefile
# ============================================================================
# 常用开发 / 运维命令入口。首次使用请先运行 `make help`。
# ============================================================================

SHELL := /bin/bash
.ONESHELL:
.SILENT:
.EXPORT_ALL_VARIABLES:

# ── 项目配置 ──────────────────────────────────────────
APP_DIR         := app
TEST_DIR        := tests
VENV_DIR        := .venv
PYTHON          := $(VENV_DIR)/bin/python
PIP             := $(VENV_DIR)/bin/pip
UVICORN         := $(VENV_DIR)/bin/uvicorn
ALEMBIC         := $(VENV_DIR)/bin/alembic
PYTEST          := $(VENV_DIR)/bin/pytest
BLACK           := $(VENV_DIR)/bin/black
RUFF            := $(VENV_DIR)/bin/ruff
MYPY            := $(VENV_DIR)/bin/mypy
DOCKER_IMAGE    := datalogue-api
DOCKER_TAG      := latest
COMPOSE_PROFILE := --profile all

# ── 颜色 ──────────────────────────────────────────────
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
NC     := \033[0m

# ============================================================================
#  帮助
# ============================================================================

.PHONY: help
help: ## 显示此帮助
	@echo "$(CYAN)Datalogue API — 可用命令$(NC)"
	@echo ""
	@echo "$(YELLOW)开发环境$(NC)"
	@echo "  make install        创建 venv 并安装依赖"
	@echo "  make install-dev    安装开发工具 (black/ruff/mypy)"
	@echo "  make dev            启动开发服务器 (热重载)"
	@echo "  make shell          进入 venv shell"
	@echo ""
	@echo "$(YELLOW)测试与代码质量$(NC)"
	@echo "  make test           运行全部测试"
	@echo "  make test-one FILE=xxx  运行单个测试文件"
	@echo "  make test-coverage  带覆盖率报告"
	@echo "  make lint           ruff 检查"
	@echo "  make lint-fix       ruff 自动修复"
	@echo "  make format         black 格式化"
	@echo "  make typecheck      mypy 类型检查"
	@echo ""
	@echo "$(YELLOW)数据库$(NC)"
	@echo "  make migrate        运行所有待迁移"
	@echo "  make migration NAME=xxx  生成新迁移"
	@echo "  make rollback       回滚一步迁移"
	@echo "  make seed           注入测试种子数据"
	@echo ""
	@echo "$(YELLOW)Docker$(NC)"
	@echo "  make docker-build   构建 API 镜像"
	@echo "  make docker-up      启动完整部署 (db+redis+api)"
	@echo "  make docker-down    停止全部容器"
	@echo "  make docker-logs    实时日志"
	@echo "  make docker-shell   进入 API 容器 bash"
	@echo "  make docker-clean   删除全部容器和数据卷"
	@echo ""
	@echo "$(YELLOW)清理$(NC)"
	@echo "  make clean          删除 __pycache__ / .venv / 等"

# ============================================================================
#  开发环境
# ============================================================================

.PHONY: install
install: ## 创建 venv 并安装依赖
	@echo "$(GREEN)>>> 创建 Python 虚拟环境...$(NC)"
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)✓ 安装完成。运行 make dev 启动服务。$(NC)"

.PHONY: install-dev
install-dev: install ## 安装开发工具（black / ruff / mypy）
	$(PIP) install black ruff mypy
	@echo "$(GREEN)✓ 开发工具安装完成。$(NC)"

.PHONY: install-enterprise
install-enterprise: ## 安装企业数据源驱动
	$(PIP) install -r requirements-enterprise.txt
	@echo "$(GREEN)✓ 企业驱动安装完成。$(NC)"

.PHONY: dev
dev: ## 启动开发服务器（热重载 + 自动建表）
	@echo "$(GREEN)>>> 启动开发服务器 http://localhost:8000$(NC)"
	@echo "$(YELLOW)    确保 PostgreSQL 和 Redis 已启动。$(NC)"
	@echo "$(YELLOW)    docker compose up -d db redis$(NC)"
	@echo ""
	$(UVICORN) $(APP_DIR).main:app --reload --host 0.0.0.0 --port 8000

.PHONY: shell
shell: ## 进入 venv shell
	@echo "$(GREEN)>>> 进入 venv shell$(NC)"
	@bash --rcfile <(echo "source $(VENV_DIR)/bin/activate; echo '$(CYAN)venv 已激活$(NC)'")

# ============================================================================
#  测试与代码质量
# ============================================================================

.PHONY: test
test: ## 运行全部测试
	$(PYTEST) $(TEST_DIR)/ -v --tb=short $(ARGS)

.PHONY: test-one
test-one: ## 运行单个测试文件: make test-one FILE=tests/test_dataset.py
ifndef FILE
	@echo "$(RED)错误: 请指定 FILE 参数，如 make test-one FILE=tests/test_dataset.py$(NC)"
	@exit 1
endif
	$(PYTEST) $(FILE) -v --tb=short $(ARGS)

.PHONY: test-coverage
test-coverage: ## 运行测试并生成覆盖率报告
	$(PYTEST) $(TEST_DIR)/ --cov=$(APP_DIR) --cov-report=term --cov-report=html $(ARGS)
	@echo "$(GREEN)✓ 覆盖率报告: htmlcov/index.html$(NC)"

.PHONY: lint
lint: ## ruff 检查
	$(RUFF) check $(APP_DIR)/ $(TEST_DIR)/

.PHONY: lint-fix
lint-fix: ## ruff 自动修复
	$(RUFF) check --fix $(APP_DIR)/ $(TEST_DIR)/

.PHONY: format
format: ## black 格式化
	$(BLACK) $(APP_DIR)/ $(TEST_DIR)/

.PHONY: typecheck
typecheck: ## mypy 类型检查
	$(MYPY) $(APP_DIR)/

# ============================================================================
#  数据库
# ============================================================================

.PHONY: migrate
migrate: ## 运行所有待迁移
	$(ALEMBIC) upgrade head
	@echo "$(GREEN)✓ 迁移完成$(NC)"

.PHONY: migration
migration: ## 生成新迁移: make migration NAME=add_user_table
ifndef NAME
	@echo "$(RED)错误: 请指定 NAME 参数，如 make migration NAME=add_user_table$(NC)"
	@exit 1
endif
	$(ALEMBIC) revision --autogenerate -m "$(NAME)"

.PHONY: rollback
rollback: ## 回滚一步迁移
	$(ALEMBIC) downgrade -1
	@echo "$(GREEN)✓ 已回滚一步$(NC)"

.PHONY: seed
seed: ## 注入测试种子数据
	$(PYTHON) scripts/seed_data.py
	@echo "$(GREEN)✓ 种子数据已注入$(NC)"

.PHONY: db-check
db-check: ## 查看当前迁移版本
	$(ALEMBIC) current

# ============================================================================
#  Docker
# ============================================================================

.PHONY: docker-build
docker-build: ## 构建 API 镜像
	@echo "$(GREEN)>>> 构建 $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		-f Dockerfile .
	@echo "$(GREEN)✓ 构建完成: $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"

.PHONY: docker-build-prod
docker-build-prod: ## 生产构建（多阶段，含 enterprise 依赖）
	@echo "$(GREEN)>>> 生产构建 $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) \
		--target production \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		-f Dockerfile .
	@echo "$(GREEN)✓ 生产构建完成$(NC)"

.PHONY: docker-up
docker-up: ## 启动完整部署 (db + redis + api)
	@echo "$(GREEN)>>> 启动完整部署$(NC)"
	docker compose $(COMPOSE_PROFILE) up -d
	@echo "$(GREEN)✓ 已启动。API: http://localhost:${API_PORT:-8000}$(NC)"

.PHONY: docker-up-infra
docker-up-infra: ## 仅启动基础设施 (db + redis)
	@echo "$(GREEN)>>> 启动基础设施$(NC)"
	docker compose up -d db redis
	@echo "$(GREEN)✓ 基础设施已启动$(NC)"

.PHONY: docker-down
docker-down: ## 停止全部容器
	docker compose $(COMPOSE_PROFILE) down

.PHONY: docker-logs
docker-logs: ## 实时日志
	docker compose logs -f $(SERVICE)

.PHONY: docker-shell
docker-shell: ## 进入 API 容器 bash
	docker compose exec api bash

.PHONY: docker-psql
docker-psql: ## 连接数据库
	docker compose exec db psql -U datalogue datalogue

.PHONY: docker-clean
docker-clean: ## 删除全部容器和数据卷
	@echo "$(RED)警告: 这将删除所有数据卷！$(NC)"
	@read -p "确认? [y/N] " confirm; \
	if [ "$$confirm" = "y" ]; then \
		docker compose $(COMPOSE_PROFILE) down -v; \
		echo "$(GREEN)✓ 已清理$(NC)"; \
	fi

.PHONY: docker-migrate
docker-migrate: ## 在 API 容器内运行迁移
	docker compose exec api alembic upgrade head

# ============================================================================
#  清理
# ============================================================================

.PHONY: clean
clean: ## 删除临时文件和缓存
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	rm -rf *.egg-info dist build
	@echo "$(GREEN)✓ 已清理$(NC)"

.PHONY: clean-all
clean-all: clean ## 深度清理（包括 venv）
	rm -rf $(VENV_DIR)
	@echo "$(GREEN)✓ 深度清理完成$(NC)"
