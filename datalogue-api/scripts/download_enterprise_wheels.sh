#!/usr/bin/env bash
# ============================================================
# File Name   : download_enterprise_wheels.sh
# Description:
#   下载企业数据源可选驱动的离线 wheel 包。
#
# Responsibilities:
#   - 在有互联网访问的构建机上生成 wheelhouse 离线依赖目录。
#   - 为纯内网部署准备 Oracle、Hive、Trino、SQL Server、ClickHouse、BigQuery 驱动。
#
# Author      : yangkai
# Created On  : 2026-06-10
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQUIREMENTS_FILE="${PROJECT_DIR}/requirements-enterprise.txt"
WHEELHOUSE_DIR="${1:-${PROJECT_DIR}/wheelhouse}"

mkdir -p "${WHEELHOUSE_DIR}"

has_pip() {
  "$1" -m pip --version >/dev/null 2>&1
}

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="${PYTHON}"
  if ! has_pip "${PYTHON_BIN}"; then
    echo "指定的 Python 解释器不可用或未安装 pip：${PYTHON_BIN}" >&2
    echo "请先安装 pip，或改用 PYTHON=/path/to/python 指定可执行 'python -m pip' 的解释器。" >&2
    exit 1
  fi
elif [[ -x "${PROJECT_DIR}/.venv/bin/python" ]] && has_pip "${PROJECT_DIR}/.venv/bin/python"; then
  PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1 && has_pip "$(command -v python3)"; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1 && has_pip "$(command -v python)"; then
  PYTHON_BIN="$(command -v python)"
else
  # macOS 官方 Python 安装路径兜底（非交互式 bash 的 PATH 可能不含该目录）
  _MACOS_PY=""
  for _p in \
    /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3; do
    # shellcheck disable=SC2086
    for _resolved in $_p; do
      if [[ -x "${_resolved}" ]] && has_pip "${_resolved}"; then
        _MACOS_PY="${_resolved}"
        break 2
      fi
    done
  done
  if [[ -n "${_MACOS_PY}" ]]; then
    PYTHON_BIN="${_MACOS_PY}"
  fi
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "未找到可执行 'python -m pip' 的 Python 解释器。" >&2
  echo "请先安装 pip，或通过 PYTHON=/path/to/python 指定可用解释器。" >&2
  exit 1
fi

echo "使用 Python 解释器：${PYTHON_BIN}"

"${PYTHON_BIN}" -m pip download \
  --dest "${WHEELHOUSE_DIR}" \
  --requirement "${REQUIREMENTS_FILE}"

cat <<EOF
企业数据源离线依赖已下载到：
  ${WHEELHOUSE_DIR}

内网安装示例：
  ${PYTHON_BIN} -m pip install --no-index --find-links ${WHEELHOUSE_DIR} -r ${REQUIREMENTS_FILE}
EOF
