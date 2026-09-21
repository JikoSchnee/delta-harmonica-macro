#!/usr/bin/env bash
# 启动带本地登录、积分和匿名统计的站点预览。
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PORT="${DELTA_PREVIEW_PORT:-8765}"
readonly ANALYTICS_TOKEN="${DELTA_LOCAL_ANALYTICS_TOKEN:-local-preview-analytics}"
readonly AUTH_SECRET="${DELTA_PREVIEW_AUTH_SECRET:-local-points-smoke-secret}"
readonly TEST_EMAIL="${DELTA_PREVIEW_TEST_EMAIL:-points100-test@example.invalid}"
readonly TEST_CODE="${DELTA_PREVIEW_TEST_CODE:-100100}"

cd "$PROJECT_DIR"
printf '本地预览已准备就绪：\n'
printf '  站点： http://127.0.0.1:%s/\n' "$PORT"
printf '  数据后台：http://127.0.0.1:%s/admin/analytics.html\n' "$PORT"
printf '  本地管理令牌：%s\n' "$ANALYTICS_TOKEN"
printf '  测试账号：%s\n' "$TEST_EMAIL"
printf '  固定验证码：%s\n' "$TEST_CODE"
printf '按 Ctrl+C 停止服务。\n\n'

exec env \
  DELTA_AUTH_SECRET="$AUTH_SECRET" \
  DELTA_FIXED_TEST_LOGIN_EMAIL="$TEST_EMAIL" \
  DELTA_FIXED_TEST_LOGIN_CODE="$TEST_CODE" \
  DELTA_ANALYTICS_ADMIN_TOKEN="$ANALYTICS_TOKEN" \
  python3 tools/local_library_server.py \
    --port "$PORT" \
    --public \
    --auth-code-log-only \
    --insecure-auth-cookies
