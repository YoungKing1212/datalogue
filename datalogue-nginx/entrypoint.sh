#!/bin/sh
# ============================================================================
# Datalogue Nginx — 启动脚本
# ============================================================================
# 首次启动或证书缺失时，用 openssl 生成自签 TLS 证书；已存在则复用。
#
# 环境变量：
#   NGINX_TLS_HOSTS   逗号分隔的 SAN 列表，如 "localhost,192.168.1.10,datalogue.local"
#                     默认: "localhost,127.0.0.1"
#   NGINX_TLS_DAYS    证书有效期（天），默认 3650
#
# Web Crypto (crypto.subtle) 需要"安全上下文"，https 或 localhost/127.0.0.1
# 才允许调用。生产用真正的 CA 证书；开发 / 内网走自签即可。
# ============================================================================
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_FILE="${CERT_DIR}/datalogue.crt"
KEY_FILE="${CERT_DIR}/datalogue.key"
HOSTS="${NGINX_TLS_HOSTS:-localhost,127.0.0.1}"
DAYS="${NGINX_TLS_DAYS:-3650}"

mkdir -p "${CERT_DIR}"

if [ ! -s "${CERT_FILE}" ] || [ ! -s "${KEY_FILE}" ]; then
    echo "[datalogue-nginx] 生成自签证书 → ${CERT_FILE} (SAN: ${HOSTS})"

    # 把 HOSTS 拆成 SAN 列表；IP 走 IP:, 其他走 DNS:
    SAN=""
    OLD_IFS="${IFS}"
    IFS=','
    for h in ${HOSTS}; do
        h=$(echo "${h}" | xargs)  # trim
        [ -z "${h}" ] && continue
        # 简易 IPv4 判定
        if echo "${h}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
            SAN="${SAN}IP:${h},"
        else
            SAN="${SAN}DNS:${h},"
        fi
    done
    IFS="${OLD_IFS}"
    SAN="${SAN%,}"  # 去尾逗号

    openssl req -x509 -newkey rsa:2048 -sha256 \
        -days "${DAYS}" -nodes \
        -subj "/CN=datalogue-local" \
        -addext "subjectAltName=${SAN}" \
        -keyout "${KEY_FILE}" \
        -out "${CERT_FILE}" 2>&1 | tail -3

    chmod 600 "${KEY_FILE}"
    echo "[datalogue-nginx] 证书生成完成"
else
    echo "[datalogue-nginx] 复用已有证书 ${CERT_FILE}"
fi

exec "$@"
