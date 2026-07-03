# ============================================================
# File Name   : Dockerfile
# Description:
#   Datalogue Web 容器镜像，使用 Vite dev server 承载本地部署页面。
#
# Responsibilities:
#   - 安装前端依赖。
#   - 暴露 5173 端口。
#   - 通过 Vite proxy 把 /api 请求转发到 docker-compose 内的 API 服务。
# ============================================================

FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
