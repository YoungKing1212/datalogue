#!/usr/bin/env bash
# ============================================================================
# Datalogue API — Docker 构建与发布脚本
# ============================================================================
# 用法:
#   ./scripts/docker-build.sh              # 构建 latest 标签
#   ./scripts/docker-build.sh --version    # 使用 git tag/SHA 作为版本号
#   ./scripts/docker-build.sh --enterprise # 包含企业数据源驱动
#   ./scripts/docker-build.sh --push       # 构建 + 推送到 registry
#   ./scripts/docker-build.sh --help       # 显示完整帮助
# ============================================================================

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────
APP_NAME="datalogue-api"
DOCKERFILE="Dockerfile"
REGISTRY="${DOCKER_REGISTRY:-}"           # 例如 registry.example.com
REGISTRY_USER="${DOCKER_REGISTRY_USER:-}"
REGISTRY_PASS="${DOCKER_REGISTRY_PASS:-}"
PLATFORMS="linux/amd64,linux/arm64"       # 多架构构建

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 解析参数 ──────────────────────────────────────────
USE_VERSION=false
ENTERPRISE=false
PUSH=false
CLEAN=false
TARGET="production"
VERSION=""
EXTRA_TAGS=""

usage() {
    cat <<EOF
${CYAN}Datalogue API — Docker 构建脚本${NC}

用法:
  $(basename "$0") [选项]

选项:
  -v, --version     用 git tag 或 commit SHA 作为镜像版本
  -e, --enterprise  安装企业数据源驱动 (Oracle/Hive/SQL Server/...)
  -p, --push        构建后推送到镜像仓库 (\$DOCKER_REGISTRY)
  -t, --tag TEXT    额外添加自定义标签 (可重复: -t v1 -t stable)
  --dev             构建开发镜像 (热重载)
  --clean           构建前清理 Docker 缓存 (--no-cache)
  -h, --help        显示此帮助
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--version)   USE_VERSION=true ; shift ;;
        -e|--enterprise) ENTERPRISE=true ; shift ;;
        -p|--push)      PUSH=true ; shift ;;
        -t|--tag)       EXTRA_TAGS="${EXTRA_TAGS} $2" ; shift 2 ;;
        --dev)          TARGET="development" ; shift ;;
        --clean)        CLEAN=true ; shift ;;
        -h|--help)      usage ;;
        *)              echo "${RED}未知参数: $1${NC}" ; usage ;;
    esac
done

# ── 确定版本号 ────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ "$USE_VERSION" = true ]; then
    # 优先使用 git tag，没有 tag 则用 commit SHA
    GIT_TAG="$(git describe --tags --exact-match 2>/dev/null || true)"
    GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")"
    if [ -n "$GIT_TAG" ]; then
        VERSION="${GIT_TAG}"
    else
        VERSION="${GIT_SHA}"
    fi
    echo -e "${CYAN}版本:${NC} ${VERSION} (git: ${GIT_SHA})"
else
    VERSION="latest"
    echo -e "${CYAN}版本:${NC} latest"
fi

# ── 构建参数 ──────────────────────────────────────────
BUILD_ARGS=()
if [ "$ENTERPRISE" = true ]; then
    BUILD_ARGS+=(--build-arg ENTERPRISE_DEPS=1)
    echo -e "${YELLOW}企业数据源驱动:${NC} 已启用"
fi

if [ "$CLEAN" = true ]; then
    BUILD_ARGS+=(--no-cache)
    echo -e "${YELLOW}缓存策略:${NC} --no-cache"
fi

# ── 镜像标签 ──────────────────────────────────────────
LOCAL_TAG="${APP_NAME}:${VERSION}"
TAGS=("${LOCAL_TAG}")
if [ -n "$EXTRA_TAGS" ]; then
    for tag in $EXTRA_TAGS; do
        TAGS+=("${APP_NAME}:${tag}")
    done
fi

# ── 打印构建信息 ──────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${CYAN}  Datalogue API 构建${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "  目标:       ${TARGET}"
echo -e "  版本:       ${VERSION}"
echo -e "  本地标签:   ${LOCAL_TAG}"
echo -e "  额外标签:   ${EXTRA_TAGS:-无}"
echo -e "  企业驱动:   ${ENTERPRISE}"
echo -e "  推送:       ${PUSH} → ${REGISTRY}"
echo -e "  缓存清理:   ${CLEAN}"
echo -e "${CYAN}────────────────────────────────────────────${NC}"
echo ""

# ── 构建镜像 ──────────────────────────────────────────
echo -e "${GREEN}>>> 构建镜像...${NC}"

BUILD_CMD=(
    docker build
    -f "${DOCKERFILE}"
    --target "${TARGET}"
    "${BUILD_ARGS[@]}"
    -t "${LOCAL_TAG}"
)

# 添加额外标签
for tag in "${TAGS[@]:1}"; do
    BUILD_CMD+=(-t "$tag")
done

BUILD_CMD+=(".")

echo "${BUILD_CMD[@]}"
"${BUILD_CMD[@]}"

echo -e "${GREEN}✓ 构建成功: ${LOCAL_TAG}${NC}"

# ── 推送到镜像仓库 ────────────────────────────────────
if [ "$PUSH" = true ]; then
    if [ -z "$REGISTRY" ]; then
        echo -e "${RED}错误: --push 需要设置 \$DOCKER_REGISTRY 环境变量${NC}"
        exit 1
    fi

    # 登录
    if [ -n "$REGISTRY_USER" ] && [ -n "$REGISTRY_PASS" ]; then
        echo "$REGISTRY_PASS" | docker login "$REGISTRY" -u "$REGISTRY_USER" --password-stdin
    fi

    # 为每个标签添加 registry 前缀并推送
    for tag in "${TAGS[@]}"; do
        REMOTE_TAG="${REGISTRY}/${tag}"
        echo -e "${GREEN}>>> 推送 ${REMOTE_TAG}${NC}"
        docker tag "${tag}" "${REMOTE_TAG}"
        docker push "${REMOTE_TAG}"
    done

    echo -e "${GREEN}✓ 推送完成${NC}"
fi

# ── 构建摘要 ──────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Datalogue API 构建完成${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
docker images --filter "reference=${APP_NAME}" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
echo -e "${CYAN}────────────────────────────────────────────${NC}"
echo ""
echo -e "快速启动:"
echo -e "  ${YELLOW}cd .. && docker compose up -d${NC}"
echo -e ""
echo -e "查看文档:"
echo -e "  ${YELLOW}docs/docker-deployment.md${NC}"
