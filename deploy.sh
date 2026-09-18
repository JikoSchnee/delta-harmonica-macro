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
readonly WEBSITE_VERSION_FILE="$PROJECT_DIR/version.json"
readonly DEPLOYED_WEBSITE_VERSION_URL="${DEPLOYED_WEBSITE_VERSION_URL:-https://jiko-official.top/delta/version.json}"

BUMP_VERSION=""
REDEPLOY=0

usage() {
  cat <<'USAGE'
用法：
  ./deploy.sh
  ./deploy.sh --redeploy
  ./deploy.sh --bump-version <新版本号>

部署前会比较本地 version.json 与正式站点版本；版本未更新或低于线上版本时会停止部署。
如需不改版本号重复部署同一版本，可使用 --redeploy；该参数只允许本地与线上版本完全相同。
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--bump-version" ]]; then
  [[ -n "${2:-}" && -z "${3:-}" ]] || { usage >&2; exit 2; }
  BUMP_VERSION="$2"
elif [[ "${1:-}" == "--redeploy" ]]; then
  [[ -z "${2:-}" ]] || { usage >&2; exit 2; }
  REDEPLOY=1
elif [[ $# -gt 0 ]]; then
  echo "未知参数：$1" >&2
  usage >&2
  exit 2
fi

read_version_from_json() {
  python3 - "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("version")
if not isinstance(value, str) or not value.strip():
    raise SystemExit("version.json 缺少有效的 version 字段")
print(value.strip())
PY
}

next_patch_version() {
  python3 - "$1" <<'PY'
import sys

parts = sys.argv[1].split(".")
if len(parts) != 3 or not all(part.isdigit() for part in parts):
    raise SystemExit("无法计算下一个补丁版本")
parts[-1] = str(int(parts[-1]) + 1)
print(".".join(parts))
PY
}

version_is_newer() {
  python3 - "$1" "$2" <<'PY'
import sys

left = tuple(int(part) for part in sys.argv[1].split("."))
right = tuple(int(part) for part in sys.argv[2].split("."))
raise SystemExit(0 if left > right else 1)
PY
}

bump_website_version() {
  python3 - "$PROJECT_DIR/version.json" "$PROJECT_DIR/app.js" "$PROJECT_DIR/README.md" "$PROJECT_DIR/index.html" "$1" <<'PY'
import json
import os
import re
import sys

version_path, app_path, readme_path, index_path, new_version = sys.argv[1:]
if not re.fullmatch(r"\d+\.\d+\.\d+", new_version):
    raise SystemExit("版本号必须是类似 2.0.0 的三段式数字版本号")

with open(version_path, encoding="utf-8") as handle:
    metadata = json.load(handle)
old_version = metadata.get("version")
metadata["version"] = new_version
for index, change in enumerate(metadata.get("changes", [])):
    if isinstance(change, str) and "网页版本" in change and isinstance(old_version, str):
        metadata["changes"][index] = change.replace(old_version, new_version)
temporary_path = f"{version_path}.tmp"
with open(temporary_path, "w", encoding="utf-8") as handle:
    json.dump(metadata, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
os.replace(temporary_path, version_path)

with open(app_path, encoding="utf-8") as handle:
    app_source = handle.read()
app_source, replacements = re.subn(
    r'(const WEBSITE_VERSION = ")[^"]+(";)',
    rf'\g<1>{new_version}\g<2>',
    app_source,
    count=1,
)
if replacements != 1:
    raise SystemExit("app.js 中没有找到 WEBSITE_VERSION")
with open(app_path, "w", encoding="utf-8") as handle:
    handle.write(app_source)

with open(readme_path, encoding="utf-8") as handle:
    readme = handle.read()
readme, replacements = re.subn(
    r'(- 网页版本：)`[^`]+`',
    rf'\g<1>`{new_version}`',
    readme,
    count=1,
)
if replacements != 1:
    raise SystemExit("README.md 中没有找到网页版本说明")
with open(readme_path, "w", encoding="utf-8") as handle:
    handle.write(readme)

with open(index_path, encoding="utf-8") as handle:
    index_source = handle.read()
# 静态资源长期缓存（immutable）依赖 ?v= 标记变化来让浏览器重新下载，
# 因此每次发版都必须把标记一起换掉，否则老用户会一直用本地缓存。
index_source, cache_replacements = re.subn(
    r"\?v=[0-9A-Za-z._-]+",
    f"?v={new_version}",
    index_source,
)
if cache_replacements < 1:
    raise SystemExit("index.html 中没有找到静态资源 ?v= 缓存标记")
index_source, replacements = re.subn(
    r"v\d+\.\d+\.\d+",
    f"v{new_version}",
    index_source,
)
if replacements < 1:
    raise SystemExit("index.html 中没有找到网页版本标记")
with open(index_path, "w", encoding="utf-8") as handle:
    handle.write(index_source)
PY
}

if [[ -n "$BUMP_VERSION" ]]; then
  bump_website_version "$BUMP_VERSION"
  echo "已将网页版本更新为 v${BUMP_VERSION}。"
  echo "请检查变更后重新执行：./deploy.sh"
  exit 0
fi

cleanup() {
  rm -f "$ARCHIVE_PATH"
}
trap cleanup EXIT

cd "$PROJECT_DIR"
echo "[0/4] 正在检查网站版本…"
LOCAL_WEBSITE_VERSION="$(read_version_from_json "$WEBSITE_VERSION_FILE")"
REMOTE_WEBSITE_VERSION="$(curl -fsSL --retry 2 "${DEPLOYED_WEBSITE_VERSION_URL}?t=$(date +%s)" | python3 -c 'import json, sys; value = json.load(sys.stdin).get("version"); print(value.strip() if isinstance(value, str) else "")')"
if [[ -z "$REMOTE_WEBSITE_VERSION" ]]; then
  echo "正式站点版本清单中没有有效的 version 字段，已停止部署。" >&2
  exit 1
fi
if [[ ! "$LOCAL_WEBSITE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ || ! "$REMOTE_WEBSITE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "本地或正式站点版本不是有效的三段式版本号，已停止部署。" >&2
  echo "本地版本：$LOCAL_WEBSITE_VERSION；正式站点版本：$REMOTE_WEBSITE_VERSION" >&2
  exit 1
fi
if ! version_is_newer "$LOCAL_WEBSITE_VERSION" "$REMOTE_WEBSITE_VERSION"; then
  if (( REDEPLOY )) && [[ "$LOCAL_WEBSITE_VERSION" == "$REMOTE_WEBSITE_VERSION" ]]; then
    echo "允许同版本重新部署：正式站点 v$REMOTE_WEBSITE_VERSION → 本地 v$LOCAL_WEBSITE_VERSION"
  else
    NEXT_WEBSITE_VERSION="$(next_patch_version "$REMOTE_WEBSITE_VERSION")"
    echo "本地网页版本未更新或低于正式站点版本，已停止部署。" >&2
    echo "正式站点当前版本：v$REMOTE_WEBSITE_VERSION" >&2
    echo "本地待部署版本：v$LOCAL_WEBSITE_VERSION" >&2
    echo "一键更新并重新部署：" >&2
    echo "  ./deploy.sh --bump-version $NEXT_WEBSITE_VERSION && ./deploy.sh" >&2
    exit 1
  fi
fi
echo "版本检查通过：正式站点 v$REMOTE_WEBSITE_VERSION → 本地 v$LOCAL_WEBSITE_VERSION"

echo "[1/4] 正在打包项目…"
COPYFILE_DISABLE=1 tar -czf "$ARCHIVE_PATH" \
  --exclude='.git' \
  --exclude='.idea' \
  --exclude='.pdmx-cache' \
  --exclude='data' \
  --exclude='downloads' \
  --exclude='recording-helper/downloads' \
  --exclude='server-backups' \
  --exclude='__pycache__' \
  --exclude='._*' \
  .

echo "[2/4] 正在上传到服务器…"
scp "$ARCHIVE_PATH" "$REMOTE_HOST:$REMOTE_ARCHIVE"

echo "[3/4] 正在构建并重启服务…"
ssh "$REMOTE_HOST" "REDEPLOY_MODE=$REDEPLOY bash -s" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

remote_dir='/opt/delta-harmonica-macro'
remote_archive='/tmp/delta-harmonica-macro.tgz'
container_name='delta-harmonica-macro'
image_name='delta-harmonica-macro:latest'
docker_network='study-desk-webdav_default'
maintenance_marker='/app/data/.maintenance'
redeploy_mode="${REDEPLOY_MODE:-0}"
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

# --redeploy 不改版本号，但带 ?v= 的静态资源在浏览器里是一年 immutable 缓存，
# 标记不变的话老用户会一直用本地缓存的旧文件。构建镜像前换一个时间戳标记。
if [[ "$redeploy_mode" == "1" ]]; then
  cache_token="$(date -u +%Y%m%d%H%M%S)"
  sed -i "s/?v=[0-9A-Za-z._-]*/?v=${cache_token}/g" index.html
  if ! grep -q "?v=${cache_token}" index.html; then
    echo 'index.html 中找不到可改写的 ?v= 静态资源缓存标记，已停止部署。' >&2
    exit 1
  fi
  echo "已为本次同版本重部署刷新静态资源缓存标记：?v=${cache_token}"
fi

docker build -t "$image_name" .

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
