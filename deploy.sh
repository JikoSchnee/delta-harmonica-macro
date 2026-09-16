#!/usr/bin/env bash
# 一键部署到 jiko-official.top 的 Delta 服务。
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REMOTE_HOST="root@47.102.211.4"
readonly REMOTE_DIR="/opt/delta-harmonica-macro"
readonly ARCHIVE_PATH="/private/tmp/delta-harmonica-macro.tgz"
readonly REMOTE_ARCHIVE="/tmp/delta-harmonica-macro.tgz"
readonly CONTAINER_NAME="delta-harmonica-macro"
readonly IMAGE_NAME="delta-harmonica-macro:latest"
readonly DOCKER_NETWORK="study-desk-webdav_default"

cleanup() {
  rm -f "$ARCHIVE_PATH"
}
trap cleanup EXIT

cd "$PROJECT_DIR"
echo "[1/4] 正在打包项目…"
COPYFILE_DISABLE=1 tar -czf "$ARCHIVE_PATH" \
  --exclude='.git' \
  --exclude='.idea' \
  --exclude='.pdmx-cache' \
  --exclude='data/analytics' \
  --exclude='__pycache__' \
  --exclude='._*' \
  .

echo "[2/4] 正在上传到服务器…"
scp "$ARCHIVE_PATH" "$REMOTE_HOST:$REMOTE_ARCHIVE"

echo "[3/4] 正在构建并重启服务…"
ssh "$REMOTE_HOST" 'bash -s' <<'REMOTE_SCRIPT'
set -Eeuo pipefail

remote_dir='/opt/delta-harmonica-macro'
remote_archive='/tmp/delta-harmonica-macro.tgz'
container_name='delta-harmonica-macro'
image_name='delta-harmonica-macro:latest'
docker_network='study-desk-webdav_default'
maintenance_marker='/app/data/.maintenance'
preserved_env=()

# 先取回所有 DELTA_* 配置，但暂时不删除旧容器：这样新镜像构建期间旧版本仍然在线。
if docker container inspect "$container_name" >/dev/null 2>&1; then
  while IFS= read -r env_var; do
    [[ -n "$env_var" ]] && preserved_env+=(-e "$env_var")
  done < <(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container_name" | awk '/^DELTA_/')
fi

mkdir -p "$remote_dir"
tar --warning=no-unknown-keyword -xzf "$remote_archive" -C "$remote_dir"
cd "$remote_dir"
docker build -t "$image_name" .

# 数据卷会覆盖镜像内的 /app/data。先补入仓库中已审核、但数据卷还没有的谱子，
# 再从数据卷内的完整谱源重建曲库，既不会漏掉新收录的曲目，也不会覆盖用户直传。
docker run --rm \
  -v delta-harmonica-data:/app/data \
  -v "$remote_dir/data:/seed:ro" \
  --entrypoint sh "$image_name" -c '
    set -eu
    mkdir -p /app/data/community-scores
    cp -n /seed/community-scores/. /app/data/community-scores/
    python3 tools/import_community_scores.py /app/data/community-scores \
      --report /tmp/community-score-review.json \
      --output /app/data/community-songs.js
  '

# 构建和数据导入都完成后再进入维护页，避免用户在准备阶段看到更新提示。
docker run --rm \
  -v delta-harmonica-data:/app/data \
  --entrypoint sh "$image_name" -c "touch '$maintenance_marker'"

# 切换期间由旧容器和新容器共同读取持久化维护标记；即使新容器启动失败，
# 站点也会显示“正在更新”，而不是把连接失败暴露成 502。
if docker container inspect "$container_name" >/dev/null 2>&1; then
  docker rm -f "$container_name"
fi

run_args=(
  -d
  --name "$container_name"
  --restart unless-stopped
  --network "$docker_network"
  -v delta-harmonica-data:/app/data
)
run_args+=("${preserved_env[@]}")

docker run "${run_args[@]}" "$image_name" --public --trust-proxy --port 8765

echo '新容器已启动，正在等待服务就绪…'
for attempt in {1..30}; do
  if docker exec "$container_name" python3 -c '
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8765/api/public-library/status", timeout=2) as response:
    raise SystemExit(0 if response.status == 200 else 1)
' >/dev/null 2>&1; then
    docker run --rm \
      -v delta-harmonica-data:/app/data \
      --entrypoint sh "$image_name" -c "rm -f '$maintenance_marker'"
    exit 0
  fi
  sleep 1
done

echo '新容器在 30 秒内未就绪；已保留“正在更新”提示，请检查服务器容器日志。' >&2
exit 1
REMOTE_SCRIPT

echo "[4/4] 正在验证正式站点…"
for attempt in {1..15}; do
  if response="$(curl -fsS 'https://jiko-official.top/delta/api/public-library/status' 2>/dev/null)"; then
    printf '%s\n部署完成。\n' "$response"
    exit 0
  fi
  printf '  服务启动中，等待后重试（%s/15）…\n' "$attempt"
  sleep 2
done

echo '部署完成，但正式站点在 30 秒内仍未通过验证；请检查服务器容器日志。' >&2
exit 1
