#!/usr/bin/env bash
# Publish the PowerShell OBS stream monitor to a GitHub Release and the website server.
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SOURCE_DIR="$PROJECT_DIR/recording-helper/ObsStreamMonitor"
readonly VERSION_FILE="$SOURCE_DIR/version.json"
readonly GITHUB_REPOSITORY="${OBS_MONITOR_GITHUB_REPOSITORY:-JikoSchnee/delta-harmonica-macro}"
readonly SERVER_SSH_TARGET="${OBS_MONITOR_SERVER_SSH_TARGET:-root@47.102.211.4}"
readonly SERVER_PROJECT_DIR="${OBS_MONITOR_SERVER_PROJECT_DIR:-/opt/delta-harmonica-macro}"
readonly SERVER_CONTAINER_NAME="${OBS_MONITOR_SERVER_CONTAINER_NAME:-delta-harmonica-macro}"
readonly SERVER_PUBLIC_BASE_URL="${OBS_MONITOR_SERVER_PUBLIC_BASE_URL:-https://jiko-official.top/delta/downloads}"

if [[ $# -ne 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  cat <<'USAGE'
用法：./release-obs-monitor.sh <版本号>

打包 OBS 开播监听助手，发布到 GitHub Release 和网站服务器，校验两份下载文件，
并更新 recording-helper/ObsStreamMonitor/version.json 中的网站下载链接。

环境变量：
  OBS_MONITOR_GITHUB_REPOSITORY       GitHub 仓库，默认 JikoSchnee/delta-harmonica-macro
  OBS_MONITOR_SERVER_SSH_TARGET       服务器 SSH 目标，默认 root@47.102.211.4
  OBS_MONITOR_SERVER_PROJECT_DIR      服务器项目目录，默认 /opt/delta-harmonica-macro
  OBS_MONITOR_SERVER_CONTAINER_NAME   正式站点容器名，默认 delta-harmonica-macro
  OBS_MONITOR_SERVER_PUBLIC_BASE_URL  服务器下载目录 URL
USAGE
  exit 0
fi

VERSION="$1"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "版本号必须是三段式数字，例如 1.0.0。" >&2; exit 2; }

CURRENT_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$VERSION_FILE")"
python3 - "$VERSION" "$CURRENT_VERSION" <<'PY'
import sys
target = tuple(map(int, sys.argv[1].split(".")))
current = tuple(map(int, sys.argv[2].split(".")))
if target <= current:
    raise SystemExit(f"OBS 助手版本必须高于当前版本 {sys.argv[2]}。")
PY

for command in zip unzip python3; do command -v "$command" >/dev/null || { echo "找不到必需命令：$command" >&2; exit 1; }; done
command -v gh >/dev/null || { echo '找不到 GitHub CLI：gh。' >&2; exit 1; }
command -v ssh >/dev/null || { echo '找不到 ssh。' >&2; exit 1; }
command -v scp >/dev/null || { echo '找不到 scp。' >&2; exit 1; }
command -v curl >/dev/null || { echo '找不到 curl。' >&2; exit 1; }

readonly ARCHIVE_NAME="${VERSION}-ObsStreamMonitor-win-x64.zip"
readonly RELEASE_TAG="obs-monitor-v${VERSION}"
readonly GITHUB_DOWNLOAD_URL="https://github.com/${GITHUB_REPOSITORY}/releases/download/${RELEASE_TAG}/${ARCHIVE_NAME}"
readonly SERVER_DOWNLOAD_URL="${SERVER_PUBLIC_BASE_URL%/}/${ARCHIVE_NAME}"
readonly BUILD_ROOT="$(mktemp -d /private/tmp/obs-monitor-release.XXXXXX)"
readonly PACKAGE_PATH="$BUILD_ROOT/$ARCHIVE_NAME"
cleanup() { rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

echo "[1/6] 生成 ${ARCHIVE_NAME}…"
COPYFILE_DISABLE=1 zip -j -q "$PACKAGE_PATH" \
  "$SOURCE_DIR/ObsStreamMonitor.ps1" \
  "$SOURCE_DIR/Start.cmd" \
  "$SOURCE_DIR/README.txt"
unzip -tq "$PACKAGE_PATH"
SHA256="$(shasum -a 256 "$PACKAGE_PATH" | awk '{print $1}')"

echo "[2/6] 发布 GitHub Release ${RELEASE_TAG}…"
if gh release view "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  gh release upload "$RELEASE_TAG" "$PACKAGE_PATH" --repo "$GITHUB_REPOSITORY" --clobber
else
  gh release create "$RELEASE_TAG" "$PACKAGE_PATH" \
    --repo "$GITHUB_REPOSITORY" \
    --title "OBS 开播监听助手 v$VERSION" \
    --notes-file "$SOURCE_DIR/README.txt"
fi

echo "[3/6] 上传服务器并同步到运行中的网站容器…"
ssh "$SERVER_SSH_TARGET" "mkdir -p -- '$SERVER_PROJECT_DIR/downloads'"
scp "$PACKAGE_PATH" "$SERVER_SSH_TARGET:$SERVER_PROJECT_DIR/downloads/$ARCHIVE_NAME"
ssh "$SERVER_SSH_TARGET" "set -eu
  docker inspect '$SERVER_CONTAINER_NAME' >/dev/null 2>&1
  docker exec '$SERVER_CONTAINER_NAME' mkdir -p /app/downloads
  docker cp '$SERVER_PROJECT_DIR/downloads/$ARCHIVE_NAME' '$SERVER_CONTAINER_NAME:/app/downloads/$ARCHIVE_NAME'
"

echo "[4/6] 校验 GitHub 下载…"
VERIFY_DIR="$(mktemp -d /private/tmp/obs-monitor-verify.XXXXXX)"
trap 'rm -rf "$BUILD_ROOT" "$VERIFY_DIR"' EXIT
curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --output "$VERIFY_DIR/github.zip" "$GITHUB_DOWNLOAD_URL"
test "$(shasum -a 256 "$VERIFY_DIR/github.zip" | awk '{print $1}')" = "$SHA256"

echo "[5/6] 校验服务器下载…"
curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --output "$VERIFY_DIR/server.zip" "$SERVER_DOWNLOAD_URL"
test "$(shasum -a 256 "$VERIFY_DIR/server.zip" | awk '{print $1}')" = "$SHA256"

echo "[6/6] 更新网站下载链接清单…"
python3 - "$VERSION_FILE" "$VERSION" "$RELEASE_TAG" "$GITHUB_DOWNLOAD_URL" "$SERVER_DOWNLOAD_URL" "$SHA256" <<'PY'
import json
import os
import sys

path, version, tag, github_url, server_url, sha256 = sys.argv[1:]
manifest = {
    "version": version,
    "releaseTag": tag,
    "githubDownloadUrl": github_url,
    "serverDownloadUrl": server_url,
    "sha256": sha256,
}
temporary = path + ".tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
os.replace(temporary, path)
PY

echo "OBS 助手 v$VERSION 发布完成。"
echo "GitHub：$GITHUB_DOWNLOAD_URL"
echo "服务器：$SERVER_DOWNLOAD_URL"
echo "SHA-256：$SHA256"
