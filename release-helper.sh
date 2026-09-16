#!/usr/bin/env bash
# Build and publish one Windows helper release from a single version argument.
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly VERSION_FILE="$PROJECT_DIR/recording-helper/version.json"
readonly HELPER_PROJECT="$PROJECT_DIR/recording-helper/HarmonicaRecorder/HarmonicaRecorder.csproj"
readonly GITHUB_REPOSITORY="${HELPER_GITHUB_REPOSITORY:-JikoSchnee/delta-harmonica-macro}"
readonly SERVER_SSH_TARGET="${HELPER_SERVER_SSH_TARGET:-root@47.102.211.4}"
readonly SERVER_PROJECT_DIR="${HELPER_SERVER_PROJECT_DIR:-/opt/delta-harmonica-macro}"
readonly SERVER_CONTAINER_NAME="${HELPER_SERVER_CONTAINER_NAME:-delta-harmonica-macro}"
readonly SERVER_PUBLIC_BASE_URL="${HELPER_SERVER_PUBLIC_BASE_URL:-https://jiko-official.top/delta/downloads}"

SKIP_GITHUB=0
SKIP_SERVER=0
SKIP_VERIFY=0

usage() {
  cat <<'USAGE'
用法：
  ./release-helper.sh <版本号> [--skip-github] [--skip-server] [--skip-verify]

默认会构建 Windows 自包含助手、生成 ZIP、更新 recording-helper/version.json、创建或更新 GitHub Release、上传服务器镜像并校验两份下载文件。
发布前会比较目标版本与 recording-helper/version.json；目标版本未更新或低于当前版本时会停止，并提示下一个可用版本号。

环境变量：
  HELPER_GITHUB_REPOSITORY   GitHub 仓库，默认 JikoSchnee/delta-harmonica-macro
  HELPER_SERVER_SSH_TARGET   服务器 SSH 目标，默认 root@47.102.211.4
  HELPER_SERVER_PROJECT_DIR  服务器项目目录，默认 /opt/delta-harmonica-macro
  HELPER_SERVER_CONTAINER_NAME 正式站点容器名，默认 delta-harmonica-macro
  HELPER_SERVER_PUBLIC_BASE_URL 服务器下载目录 URL
  DOTNET_BIN                 dotnet 可执行文件路径
USAGE
}

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  usage >&2
  exit 0
fi

VERSION="$1"
shift
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "版本号必须是类似 2.0.0 的三段式数字版本号。" >&2
  exit 2
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-github) SKIP_GITHUB=1 ;;
    --skip-server) SKIP_SERVER=1 ;;
    --skip-verify) SKIP_VERIFY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

read_version_from_json() {
  python3 - "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("version")
if not isinstance(value, str) or not value.strip():
    raise SystemExit("版本清单缺少有效的 version 字段")
print(value.strip())
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

CURRENT_HELPER_VERSION="$(read_version_from_json "${VERSION_FILE}")"
if [[ ! "$CURRENT_HELPER_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "当前助手版本不是有效的三段式版本号：$CURRENT_HELPER_VERSION" >&2
  exit 1
fi
if ! version_is_newer "$VERSION" "$CURRENT_HELPER_VERSION"; then
  NEXT_HELPER_VERSION="$(next_patch_version "$CURRENT_HELPER_VERSION")"
  echo "助手版本未更新或低于当前版本，已停止发布。" >&2
  echo "当前版本：v$CURRENT_HELPER_VERSION" >&2
  echo "目标版本：v$VERSION" >&2
  echo "请 bump version 后重新执行，例如：" >&2
  echo "  ./release-helper.sh $NEXT_HELPER_VERSION" >&2
  exit 1
fi

readonly ARCHIVE_NAME="${VERSION}-HarmonicaRecorder-win-x64.zip"
readonly RELEASE_TAG="helper-v${VERSION}"
readonly GITHUB_DOWNLOAD_URL="https://github.com/${GITHUB_REPOSITORY}/releases/download/${RELEASE_TAG}/${ARCHIVE_NAME}"
readonly SERVER_DOWNLOAD_URL="${SERVER_PUBLIC_BASE_URL%/}/${ARCHIVE_NAME}"

find_dotnet() {
  if [[ -n "${DOTNET_BIN:-}" && -x "$DOTNET_BIN" ]]; then
    printf '%s\n' "$DOTNET_BIN"
    return
  fi
  if command -v dotnet >/dev/null 2>&1; then
    command -v dotnet
    return
  fi
  if [[ -x /private/tmp/dotnet/dotnet ]]; then
    printf '%s\n' /private/tmp/dotnet/dotnet
    return
  fi
  echo "找不到 dotnet。请安装 .NET 8 SDK，或设置 DOTNET_BIN。" >&2
  exit 1
}

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "找不到必需命令：$1" >&2
    exit 1
  }
}

readonly DOTNET="$(find_dotnet)"
require_command zip
require_command unzip
require_command python3
if (( ! SKIP_GITHUB )); then require_command gh; fi
if (( ! SKIP_SERVER )); then require_command ssh; require_command scp; fi
if (( ! SKIP_VERIFY )); then require_command curl; fi

readonly BUILD_ROOT="$(mktemp -d /private/tmp/harmonica-recorder-release.XXXXXX)"
readonly PUBLISH_DIR="$BUILD_ROOT/publish"
readonly PACKAGE_DIR="$BUILD_ROOT/package"
readonly PACKAGE_PATH="$BUILD_ROOT/$ARCHIVE_NAME"
cleanup() { rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

cd "$PROJECT_DIR"
echo "[1/7] 构建 HarmonicaRecorder v${VERSION}…"
"$DOTNET" publish "$HELPER_PROJECT" \
  -c Release \
  -r win-x64 \
  --self-contained true \
  -p:Version="$VERSION" \
  -p:AssemblyVersion="${VERSION}.0" \
  -p:FileVersion="${VERSION}.0" \
  -p:PublishSingleFile=true \
  -p:IncludeNativeLibrariesForSelfExtract=true \
  -o "$PUBLISH_DIR"

[[ -f "$PUBLISH_DIR/HarmonicaRecorder.exe" ]] || { echo "构建完成但没有找到 HarmonicaRecorder.exe。" >&2; exit 1; }

echo "[2/7] 生成 ${ARCHIVE_NAME}…"
mkdir -p "$PACKAGE_DIR" "$PROJECT_DIR/downloads" "$PROJECT_DIR/recording-helper/downloads"
cp "$PUBLISH_DIR/HarmonicaRecorder.exe" "$PACKAGE_DIR/"
cp "$PROJECT_DIR/recording-helper/package/Install.cmd" "$PROJECT_DIR/recording-helper/package/README.txt" "$PROJECT_DIR/recording-helper/package/Uninstall.cmd" "$PACKAGE_DIR/"
rm -f "$PACKAGE_PATH"
COPYFILE_DISABLE=1 zip -j -q "$PACKAGE_PATH" \
  "$PACKAGE_DIR/Install.cmd" \
  "$PACKAGE_DIR/HarmonicaRecorder.exe" \
  "$PACKAGE_DIR/README.txt" \
  "$PACKAGE_DIR/Uninstall.cmd"

SHA256="$(sha256_of "$PACKAGE_PATH")"
cp "$PACKAGE_PATH" "$PROJECT_DIR/downloads/$ARCHIVE_NAME"
cp "$PACKAGE_PATH" "$PROJECT_DIR/recording-helper/downloads/$ARCHIVE_NAME"

echo "[3/7] 更新唯一助手版本清单…"
python3 - "$VERSION_FILE" "$VERSION" "$RELEASE_TAG" "$GITHUB_DOWNLOAD_URL" "$SERVER_DOWNLOAD_URL" "$SHA256" <<'PY'
import json
import os
import re
import sys

path, version, release_tag, github_url, server_url, sha256 = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as handle:
        previous = json.load(handle)
except (FileNotFoundError, json.JSONDecodeError):
    previous = {}

prefix = ".".join(version.split(".")[:2])
prefixes = []
for item in previous.get("compatibleHelperPrefixes", []):
    if isinstance(item, str) and item.strip() and item.strip() not in prefixes:
        prefixes.append(item.strip())
previous_version = previous.get("version")
if not prefixes and isinstance(previous_version, str) and re.fullmatch(r"\d+\.\d+\.\d+", previous_version):
    prefixes.append(".".join(previous_version.split(".")[:2]))
if prefix not in prefixes:
    prefixes.append(prefix)

compatible_web_versions = previous.get("compatibleWebVersions")
if not isinstance(compatible_web_versions, list) or not compatible_web_versions:
    compatible_web_versions = ["1.1.x"]

manifest = {
    "version": version,
    "compatibleHelperPrefixes": prefixes,
    "compatibleWebVersions": compatible_web_versions,
    "releaseTag": release_tag,
    "downloadUrl": github_url,
    "githubDownloadUrl": github_url,
    "serverDownloadUrl": server_url,
    "sha256": sha256,
}
temporary_path = f"{path}.tmp"
with open(temporary_path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
os.replace(temporary_path, path)
PY

echo "[4/7] 发布 GitHub Release ${RELEASE_TAG}…"
if (( SKIP_GITHUB )); then
  echo "  已跳过 GitHub。"
elif gh release view "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  gh release upload "$RELEASE_TAG" "$PACKAGE_PATH" --repo "$GITHUB_REPOSITORY" --clobber
else
  gh release create "$RELEASE_TAG" "$PACKAGE_PATH" \
    --repo "$GITHUB_REPOSITORY" \
    --title "Harmonica Recorder v$VERSION" \
    --generate-notes
fi

echo "[5/7] 上传服务器镜像…"
if (( SKIP_SERVER )); then
  echo "  已跳过服务器。"
else
  ssh "$SERVER_SSH_TARGET" "mkdir -p -- '$SERVER_PROJECT_DIR/downloads'"
  scp "$PACKAGE_PATH" "$SERVER_SSH_TARGET:$SERVER_PROJECT_DIR/downloads/$ARCHIVE_NAME"
  # 正式站点从 Docker 容器的 /app 提供静态文件；宿主机项目目录没有挂载
  # 到容器，因此仅 scp 到 SERVER_PROJECT_DIR 不会让下载地址立即可用。
  ssh "$SERVER_SSH_TARGET" "set -eu
    docker inspect '$SERVER_CONTAINER_NAME' >/dev/null 2>&1
    docker exec '$SERVER_CONTAINER_NAME' mkdir -p /app/downloads
    docker cp '$SERVER_PROJECT_DIR/downloads/$ARCHIVE_NAME' '$SERVER_CONTAINER_NAME:/app/downloads/$ARCHIVE_NAME'
  "
fi

echo "[6/7] 校验本地两份 ZIP…"
test "$(sha256_of "$PROJECT_DIR/downloads/$ARCHIVE_NAME")" = "$SHA256"
test "$(sha256_of "$PROJECT_DIR/recording-helper/downloads/$ARCHIVE_NAME")" = "$SHA256"
unzip -tq "$PACKAGE_PATH"

echo "[7/7] 校验远程下载…"
if (( SKIP_VERIFY )); then
  echo "  已跳过 HTTP 校验。"
else
  VERIFY_DIR="$(mktemp -d /private/tmp/harmonica-recorder-verify.XXXXXX)"
  trap 'rm -rf "$BUILD_ROOT" "$VERIFY_DIR"' EXIT
  echo "  校验 GitHub：$GITHUB_DOWNLOAD_URL"
  curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --output "$VERIFY_DIR/github.zip" "$GITHUB_DOWNLOAD_URL"
  echo "  校验服务器：$SERVER_DOWNLOAD_URL"
  curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --output "$VERIFY_DIR/server.zip" "$SERVER_DOWNLOAD_URL"
  test "$(sha256_of "$VERIFY_DIR/github.zip")" = "$SHA256"
  test "$(sha256_of "$VERIFY_DIR/server.zip")" = "$SHA256"
fi

echo "发布完成：$ARCHIVE_NAME"
echo "SHA-256：$SHA256"
