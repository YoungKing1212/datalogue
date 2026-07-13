# ============================================================================
# Datalogue Nginx — 反向代理入口
# ============================================================================
# 职责：
#   - / → web:3000（前端静态资源）
#   - /api/ → api:8000（后端接口，SSE 关闭 buffering）
#   - /agentscope/ → api:8000（AgentScope 控制平面）
#
# 前端与后端各自独立容器，nginx 作为唯一对外入口，避免把静态服务与反代绑死。
# ============================================================================

FROM nginx:1.27-alpine

# 移除默认站点，避免冲突
RUN rm -f /etc/nginx/conf.d/default.conf

COPY datalogue.conf /etc/nginx/conf.d/datalogue.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
