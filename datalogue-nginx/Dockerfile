# ============================================================================
# Datalogue Nginx — 反向代理入口（含自签 HTTPS）
# ============================================================================
# 职责：
#   - / → web:3000（前端静态资源）
#   - /api/ → api:8000（后端接口，SSE 关闭 buffering）
#   - /agentscope/ → api:8000（AgentScope 控制平面）
#
# HTTPS 说明：
#   前端登录用 Web Crypto (crypto.subtle) 加密密码，要求"安全上下文"
#   （https / localhost / 127.0.0.1）。为了让局域网 IP 也能登录，nginx
#   在启动时按需生成自签证书。生产建议挂载真正的 CA 证书覆盖。
# ============================================================================

FROM nginx:1.27-alpine

# openssl 用于运行时按需签发自签证书
RUN apk add --no-cache openssl

# 移除默认站点
RUN rm -f /etc/nginx/conf.d/default.conf

COPY datalogue.conf /etc/nginx/conf.d/datalogue.conf
COPY entrypoint.sh /usr/local/bin/datalogue-entrypoint.sh
RUN chmod +x /usr/local/bin/datalogue-entrypoint.sh

# 证书目录（默认自签写入这里，可通过 volume 挂载真实证书覆盖）
VOLUME ["/etc/nginx/certs"]

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/datalogue-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
