# ============================================================================
# Datalogue Web — 多阶段构建
# ============================================================================
# Stage 1 (builder): 编译 Vite 产物到 /app/dist
# Stage 2 (runtime): 用 node + `serve` 托管静态文件（SPA 回退）
#
# 本容器不做反代 — 反代由独立的 nginx 容器完成（见 datalogue-nginx/）。
# 内部监听 3000，不对外映射端口，只在 docker 网络里被 nginx 消费。
# ============================================================================

# ── Stage 1: 构建 ────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: 静态服务 ────────────────────────────────
FROM node:22-alpine AS production

WORKDIR /app

# `serve` 是一个轻量 SPA 静态服务器（自动回退 index.html）
RUN npm install -g serve@14

COPY --from=builder /app/dist ./dist

# 非 root 运行
RUN addgroup -g 1001 -S web \
    && adduser -u 1001 -S web -G web \
    && chown -R web:web /app
USER web

EXPOSE 3000

# healthcheck: 探 index.html
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

# -s: SPA 模式（所有未匹配路径回退到 index.html）
# -l: listen 3000
# --no-clipboard --no-request-logging: 生产环境降噪
CMD ["serve", "-s", "dist", "-l", "3000", "--no-clipboard", "--no-request-logging"]
