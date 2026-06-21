#!/usr/bin/env bash
set -euo pipefail

# 为合并后的本地 PostgreSQL 实例创建 Langfuse 独立用户和数据库。
# 该脚本仅在 datalogue_pgdata 首次初始化时由 postgres entrypoint 执行；
# 已存在的本地卷需要手动执行同等的 CREATE ROLE / CREATE DATABASE 操作。

langfuse_user="${LANGFUSE_POSTGRES_USER:-langfuse}"
langfuse_password="${LANGFUSE_POSTGRES_PASSWORD:-langfuse}"
langfuse_db="${LANGFUSE_POSTGRES_DB:-langfuse}"

if ! psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v langfuse_user="$langfuse_user" \
  -tAc "SELECT 1 FROM pg_roles WHERE rolname = :'langfuse_user';" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v langfuse_user="$langfuse_user" \
    -v langfuse_password="$langfuse_password" \
    -c "CREATE ROLE :\"langfuse_user\" LOGIN PASSWORD :'langfuse_password';"
else
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v langfuse_user="$langfuse_user" \
    -v langfuse_password="$langfuse_password" \
    -c "ALTER ROLE :\"langfuse_user\" WITH LOGIN PASSWORD :'langfuse_password';"
fi

if ! psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v langfuse_db="$langfuse_db" \
  -tAc "SELECT 1 FROM pg_database WHERE datname = :'langfuse_db';" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v langfuse_db="$langfuse_db" \
    -v langfuse_user="$langfuse_user" \
    -c 'CREATE DATABASE :"langfuse_db" OWNER :"langfuse_user";'
fi
