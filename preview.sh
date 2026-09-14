#!/usr/bin/env bash
# 启动仅供本机使用、且已开启匿名统计的站点预览。
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PORT="${DELTA_PREVIEW_PORT:-8765}"
readonly ANALYTICS_TOKEN="${DELTA_LOCAL_ANALYTICS_TOKEN:-local-preview-analytics}"

cd "$PROJECT_DIR"
printf '本地预览已准备就绪：\n'
printf '  站点： http://127.0.0.1:%s/\n' "$PORT"
printf '  数据后台：http://127.0.0.1:%s/admin/analytics.html\n' "$PORT"
printf '  本地管理令牌：%s\n' "$ANALYTICS_TOKEN"
printf '按 Ctrl+C 停止服务。\n\n'

exec env DELTA_ANALYTICS_ADMIN_TOKEN="$ANALYTICS_TOKEN" \
  python3 tools/local_library_server.py --port "$PORT"
