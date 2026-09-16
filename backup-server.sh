#!/usr/bin/env bash
# Stream a complete deployment backup from the server to the local machine.
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SERVER_SSH_TARGET="${BACKUP_SERVER_SSH_TARGET:-root@47.102.211.4}"
readonly SERVER_PROJECT_DIR="${BACKUP_SERVER_PROJECT_DIR:-/opt/delta-harmonica-macro}"
readonly SERVER_CONTAINER_NAME="${BACKUP_SERVER_CONTAINER_NAME:-delta-harmonica-macro}"
readonly SERVER_VOLUME_NAME="${BACKUP_SERVER_VOLUME_NAME:-delta-harmonica-data}"
readonly DEFAULT_BACKUP_DIR="${PROJECT_DIR}/../delta-harmonica-backups"

usage() {
  cat <<'USAGE'
用法：
  ./backup-server.sh
  ./backup-server.sh --output-dir <本地备份目录>

默认会备份：
  - 服务器项目目录 /opt/delta-harmonica-macro
  - Docker 数据卷 delta-harmonica-data:/app/data
  - 容器内 /app/downloads
  - 容器环境变量与 Docker 配置

环境变量：
  BACKUP_SERVER_SSH_TARGET     SSH 目标，默认 root@47.102.211.4
  BACKUP_SERVER_PROJECT_DIR    服务器项目目录
  BACKUP_SERVER_CONTAINER_NAME 容器名，默认 delta-harmonica-macro
  BACKUP_SERVER_VOLUME_NAME    数据卷名，默认 delta-harmonica-data
USAGE
}

BACKUP_DIR="$DEFAULT_BACKUP_DIR"
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
elif [[ "${1:-}" == "--output-dir" ]]; then
  [[ -n "${2:-}" && -z "${3:-}" ]] || { usage >&2; exit 2; }
  BACKUP_DIR="$2"
elif [[ $# -gt 0 ]]; then
  echo "未知参数：$1" >&2
  usage >&2
  exit 2
fi

if ! command -v ssh >/dev/null 2>&1; then
  echo "找不到必需命令：ssh" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
BACKUP_STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_NAME="delta-harmonica-macro-server-${BACKUP_STAMP}.tgz"
ARCHIVE_PATH="$BACKUP_DIR/${ARCHIVE_NAME}"
PARTIAL_PATH="${ARCHIVE_PATH}.part"
cleanup() { rm -f "$PARTIAL_PATH"; }
trap cleanup EXIT

echo "正在从 ${SERVER_SSH_TARGET} 打包服务器数据…"
REMOTE_ARGS="$(printf '%q ' "$SERVER_PROJECT_DIR" "$SERVER_CONTAINER_NAME" "$SERVER_VOLUME_NAME")"
ssh "$SERVER_SSH_TARGET" "bash -s -- $REMOTE_ARGS" > "$PARTIAL_PATH" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

project_dir="$1"
container_name="$2"
volume_name="$3"
stage_dir="$(mktemp -d /tmp/delta-harmonica-backup.XXXXXX)"

cleanup() {
  rm -rf "$stage_dir"
}
trap cleanup EXIT

docker container inspect "$container_name" >/dev/null 2>&1 || {
  echo "找不到运行中的 Docker 容器：$container_name" >&2
  exit 1
}
docker volume inspect "$volume_name" >/dev/null 2>&1 || {
  echo "找不到 Docker 数据卷：$volume_name" >&2
  exit 1
}
[[ -d "$project_dir" ]] || {
  echo "找不到服务器项目目录：$project_dir" >&2
  exit 1
}

mkdir -p "$stage_dir/project" "$stage_dir/data" "$stage_dir/runtime-downloads"
cp -a "$project_dir/." "$stage_dir/project/"
docker cp "$container_name:/app/data/." "$stage_dir/data/"
if docker exec "$container_name" test -d /app/downloads; then
  docker cp "$container_name:/app/downloads/." "$stage_dir/runtime-downloads/"
fi

docker inspect "$container_name" > "$stage_dir/container-inspect.json"
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container_name" > "$stage_dir/container-env.txt"
docker volume inspect "$volume_name" > "$stage_dir/volume-inspect.json"

tar -czf - -C "$stage_dir" .
REMOTE_SCRIPT

mv "$PARTIAL_PATH" "$ARCHIVE_PATH"
chmod 600 "$ARCHIVE_PATH"
ARCHIVE_SHA256="$(shasum -a 256 "$ARCHIVE_PATH" | awk '{print $1}')"
ARCHIVE_SIZE="$(du -h "$ARCHIVE_PATH" | awk '{print $1}')"

echo "备份完成：$ARCHIVE_PATH"
echo "文件大小：$ARCHIVE_SIZE"
echo "SHA-256：$ARCHIVE_SHA256"
echo "查看内容：tar -tzf "$ARCHIVE_PATH" | head"
