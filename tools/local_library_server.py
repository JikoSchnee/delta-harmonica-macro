#!/usr/bin/env python3
"""Serve the static app locally and maintain the checked-in community library.

Run from any directory:
  python3 tools/local_library_server.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIRECTORY))

from import_community_scores import dedupe_key, validate_package, write_library  # noqa: E402


SOURCE_DIRECTORY = REPOSITORY_ROOT / "data" / "community-scores"
LIBRARY_OUTPUT = REPOSITORY_ROOT / "data" / "community-songs.js"
MAX_REQUEST_BYTES = 1_000_000


def source_paths() -> list[Path]:
    """Include the canonical source directory and legacy root-level score packages."""
    paths: list[Path] = []
    if SOURCE_DIRECTORY.exists():
        paths.extend(sorted([*SOURCE_DIRECTORY.rglob("*.deltamusic"), *SOURCE_DIRECTORY.rglob("*.harmonica-score.json")]))
    paths.extend(sorted([*REPOSITORY_ROOT.glob("*.deltamusic"), *REPOSITORY_ROOT.glob("*.harmonica-score.json")]))
    return paths


def read_scores() -> list[tuple[Path, dict[str, Any]]]:
    scores: list[tuple[Path, dict[str, Any]]] = []
    seen: dict[str, Path] = {}
    for path in source_paths():
        try:
            score = validate_package(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"无法读取曲库源文件 {path.relative_to(REPOSITORY_ROOT)}：{error}") from error
        key = dedupe_key(score)
        if key in seen:
            raise ValueError(
                "曲库源文件存在重复的歌名、歌手/作者和共享人："
                f"{seen[key].relative_to(REPOSITORY_ROOT)}、{path.relative_to(REPOSITORY_ROOT)}"
            )
        seen[key] = path
        scores.append((path, score))
    return scores


def filename_for(score: dict[str, Any]) -> str:
    readable = "-".join(score[field] for field in ("title", "artist", "sharedBy"))
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", readable).strip("-")[:72] or "community-score"
    digest = hashlib.sha256(dedupe_key(score).encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}.deltamusic"


def write_json_atomically(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def is_canonical_source(path: Path) -> bool:
    try:
        path.relative_to(SOURCE_DIRECTORY)
        return True
    except ValueError:
        return False


def save_score(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    score = validate_package(payload)
    existing_scores = read_scores()
    matches = [(path, item) for path, item in existing_scores if dedupe_key(item) == dedupe_key(score)]
    if len(matches) > 1:
        raise ValueError("曲库中存在多个相同身份的曲目，请先手动整理源文件。")

    existing_path = matches[0][0] if matches else None
    destination = existing_path if existing_path and is_canonical_source(existing_path) else SOURCE_DIRECTORY / filename_for(score)
    package = {
        "format": "delta-music",
        "version": 1,
        **{field: score[field] for field in ("title", "artist", "sharedBy", "key", "meter", "bpm", "jianpu")},
        **({"displayUrl": score["displayUrl"]} if score.get("displayUrl") else {}),
    }
    write_json_atomically(destination, package)
    if existing_path and existing_path != destination:
        existing_path.unlink()

    rebuilt_scores = [item for _, item in read_scores()]
    write_library(LIBRARY_OUTPUT, rebuilt_scores)
    return ("updated" if matches else "created"), rebuilt_scores


class LocalLibraryRequestHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def request_is_local(self) -> bool:
        host, port = self.server.server_address[:2]
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == port

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/api/local-library/status":
            if not self.request_is_local():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "维护接口只允许本机访问。"})
                return
            self.send_json(HTTPStatus.OK, {"localLibrary": True})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/local-library/songs":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到维护接口。"})
            return
        if not self.request_is_local():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "维护接口只允许本机访问。"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if length < 1 or length > MAX_REQUEST_BYTES:
                raise ValueError("请求内容过大或为空。")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            action, songs = save_score(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法写入本地曲库。"})
            return
        self.send_json(HTTPStatus.OK, {"action": action, "songs": songs})


def main() -> int:
    parser = argparse.ArgumentParser(description="启动仅限本机的 Harmonica Deck 曲库维护服务")
    parser.add_argument("--port", type=int, default=8765, help="本地端口（默认：8765）")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")

    handler = lambda *args_, **kwargs: LocalLibraryRequestHandler(*args_, directory=str(REPOSITORY_ROOT), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"本地维护服务已启动：http://127.0.0.1:{args.port}/")
    print("仅监听 127.0.0.1；按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地维护服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
