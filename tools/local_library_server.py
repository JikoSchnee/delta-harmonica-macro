#!/usr/bin/env python3
"""Serve the static app and maintain its community library.

Run from any directory:
  python3 tools/local_library_server.py

Use --public only when deploying this app behind a public-facing web server.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
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
MAX_ANALYTICS_REQUEST_BYTES = 25_000
PUBLIC_UPLOAD_COOLDOWN_SECONDS = 30
LIBRARY_LOCK = threading.Lock()
ANALYTICS_LOCK = threading.Lock()
ANALYTICS_DIRECTORY = REPOSITORY_ROOT / "data" / "analytics"
DEFAULT_ANALYTICS_RETENTION_DAYS = 90
ACTIVE_VISITOR_WINDOW_SECONDS = 300
ANALYTICS_EVENTS = {
    "page_view", "directory_selected", "library_search", "song_loaded", "input_mode_selected",
    "midi_import_opened", "midi_selection_applied", "score_imported", "preview_started",
    "macro_section_opened", "score_downloaded", "community_upload_succeeded", "macro_downloaded",
    "lua_copied", "tour_started", "heartbeat",
}
ANALYTICS_ENUMERATIONS = {
    "entry": {"direct", "search", "social", "referral", "internal"},
    "origin": {"builtin", "community", "pdmx", "imported", "midi"},
    "mode": {"jianpu", "record", "precise", "keyboard"},
    "format": {"lua", "synapse_3", "synapse_4", "rog", "deltamusic"},
    "directory": {"library", "midi", "manual"},
}


class DuplicateScoreError(ValueError):
    """Raised when a public upload would replace an existing community score."""


def analytics_event_path(day: date) -> Path:
    return ANALYTICS_DIRECTORY / f"events-{day.isoformat()}.ndjson"


def clean_analytics_properties(event: str, value: Any) -> dict[str, Any]:
    """Keep analytics intentionally anonymous and bounded at the API boundary."""
    if not isinstance(value, dict):
        return {}
    properties: dict[str, Any] = {}
    for field, allowed in ANALYTICS_ENUMERATIONS.items():
        candidate = value.get(field)
        if candidate in allowed:
            properties[field] = candidate
    # Search text, score titles, MIDI file names and free-form user input are never accepted.
    if event == "library_search" and isinstance(value.get("query_length"), int):
        properties["query_length"] = min(128, max(0, value["query_length"]))
    return properties


def parse_analytics_payload(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ValueError("统计事件格式无效。")
    session = payload.get("session")
    if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", session):
        raise ValueError("统计会话标识无效。")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 20:
        raise ValueError("统计事件数量无效。")
    cleaned: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, dict) or item.get("event") not in ANALYTICS_EVENTS:
            raise ValueError("统计事件类型无效。")
        cleaned.append({"event": item["event"], "properties": clean_analytics_properties(item["event"], item.get("properties"))})
    return session, cleaned


def cleanup_analytics(retention_days: int, today: date) -> None:
    cutoff = today - timedelta(days=retention_days)
    for path in ANALYTICS_DIRECTORY.glob("events-*.ndjson") if ANALYTICS_DIRECTORY.exists() else []:
        match = re.fullmatch(r"events-(\d{4}-\d{2}-\d{2})\.ndjson", path.name)
        if not match:
            continue
        try:
            if date.fromisoformat(match.group(1)) < cutoff:
                path.unlink()
        except (OSError, ValueError):
            continue


def record_analytics_events(session: str, events: list[dict[str, Any]], retention_days: int) -> None:
    now = datetime.now(timezone.utc)
    record_time = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    path = analytics_event_path(now.date())
    lines = [json.dumps({"time": record_time, "session": session, "event": item["event"], "properties": item["properties"]}, ensure_ascii=False, separators=(",", ":")) for item in events]
    with ANALYTICS_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
        cleanup_analytics(retention_days, now.date())


def analytics_label(event: dict[str, Any]) -> str:
    properties = event.get("properties") or {}
    labels = {
        "page_view": "访问",
        "directory_selected": f"入口:{properties.get('directory', '其他')}",
        "song_loaded": f"选曲:{properties.get('origin', '其他')}",
        "input_mode_selected": f"模式:{properties.get('mode', '其他')}",
        "midi_import_opened": "导入 MIDI",
        "midi_selection_applied": "生成 MIDI 谱",
        "score_imported": "导入谱子",
        "preview_started": "试听",
        "macro_section_opened": "宏导出区",
        "macro_downloaded": f"下载:{properties.get('format', '宏')}",
        "score_downloaded": "下载谱子",
        "community_upload_succeeded": "上传曲库",
        "lua_copied": "复制 Lua",
        "tour_started": "打开教程",
    }
    return labels.get(event["event"], event["event"])


def build_analytics_report(days: int) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    records: list[dict[str, Any]] = []
    for offset in range(days):
        path = analytics_event_path(start + timedelta(days=offset))
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if isinstance(item, dict) and isinstance(item.get("session"), str) and item.get("event") in ANALYTICS_EVENTS:
                    records.append(item)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

    sessions = {item["session"] for item in records}
    page_views = sum(item["event"] == "page_view" for item in records)
    event_counts = Counter(item["event"] for item in records)
    event_sessions: dict[str, set[str]] = defaultdict(set)
    daily_sessions: dict[str, set[str]] = defaultdict(set)
    daily_views: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    journeys: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        event_sessions[item["event"]].add(item["session"])
        day = str(item.get("time", ""))[:10]
        if day:
            daily_sessions[day].add(item["session"])
            if item["event"] == "page_view":
                daily_views[day] += 1
        if item["event"] == "page_view":
            source_counts[(item.get("properties") or {}).get("entry", "direct")] += 1
        journeys[item["session"]].append(item)

    path_counts: Counter[str] = Counter()
    for journey in journeys.values():
        labels: list[str] = []
        for item in journey:
            label = analytics_label(item)
            if not labels or labels[-1] != label:
                labels.append(label)
        if len(labels) >= 2:
            path_counts[" → ".join(labels[:7])] += 1

    funnel_groups = {
        "访问页面": {"page_view"},
        "选择入口": {"directory_selected"},
        "获得曲谱": {"song_loaded", "midi_selection_applied", "score_imported"},
        "开始试听": {"preview_started"},
        "前往导出": {"macro_section_opened"},
        "完成宏导出": {"macro_downloaded", "lua_copied"},
    }
    funnel = [{"name": name, "sessions": len(set().union(*(event_sessions[event] for event in events)))} for name, events in funnel_groups.items()]
    timeline = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        timeline.append({"day": day, "sessions": len(daily_sessions[day]), "pageViews": daily_views[day]})
    return {
        "rangeDays": days,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": {"sessions": len(sessions), "pageViews": page_views, "events": len(records), "macroDownloads": event_counts["macro_downloaded"]},
        "timeline": timeline,
        "sources": [{"name": name, "count": count} for name, count in source_counts.most_common(8)],
        "events": [{"name": name, "count": count, "sessions": len(event_sessions[name])} for name, count in event_counts.most_common()],
        "funnel": funnel,
        "paths": [{"path": path, "sessions": count} for path, count in path_counts.most_common(12)],
    }


def build_public_analytics_summary() -> dict[str, int]:
    """Return only aggregate counts suitable for the public site header."""
    now = datetime.now(timezone.utc)
    today_sessions: set[str] = set()
    latest_seen: dict[str, datetime] = {}
    path = analytics_event_path(now.date())
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if not isinstance(item, dict) or not isinstance(item.get("session"), str):
                    continue
                try:
                    recorded_at = datetime.fromisoformat(str(item.get("time", "")).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if item.get("event") == "page_view":
                    today_sessions.add(item["session"])
                if recorded_at <= now and recorded_at > latest_seen.get(item["session"], datetime.min.replace(tzinfo=timezone.utc)):
                    latest_seen[item["session"]] = recorded_at
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    cutoff = now - timedelta(seconds=ACTIVE_VISITOR_WINDOW_SECONDS)
    return {
        "activeVisitors": sum(recorded_at >= cutoff for recorded_at in latest_seen.values()),
        "todayVisitors": len(today_sessions),
        "activeWindowSeconds": ACTIVE_VISITOR_WINDOW_SECONDS,
    }


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


def save_score(payload: Any, *, allow_replace: bool = True) -> tuple[str, list[dict[str, Any]]]:
    """Validate, store, and expose one score while serialising concurrent uploads."""
    score = validate_package(payload)
    with LIBRARY_LOCK:
        existing_scores = read_scores()
        matches = [(path, item) for path, item in existing_scores if dedupe_key(item) == dedupe_key(score)]
        if len(matches) > 1:
            raise ValueError("曲库中存在多个相同身份的曲目，请先手动整理源文件。")
        if matches and not allow_replace:
            raise DuplicateScoreError("该歌名、歌手/作者和共享人组合已存在，不能覆盖已上传曲目。")

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
        _, port = self.server.server_address[:2]
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == port

    def request_is_same_origin(self) -> bool:
        """Block browser cross-site POSTs; public uploads are intended for this UI only."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        try:
            request_host = urlparse(f"//{self.headers.get('Host', '')}")
            origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            request_port = request_host.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            return False
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.hostname.casefold() == (request_host.hostname or "").casefold()
            and origin_port == request_port
        )

    def read_payload(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as error:
            raise ValueError("请求缺少有效的内容长度。") from error
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise ValueError("请求内容过大或为空。")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def read_analytics_payload(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as error:
            raise ValueError("统计请求缺少有效的内容长度。") from error
        if length < 1 or length > MAX_ANALYTICS_REQUEST_BYTES:
            raise ValueError("统计请求内容过大或为空。")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def is_analytics_admin(self) -> bool:
        configured = self.server.analytics_admin_token
        header = self.headers.get("Authorization", "")
        supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
        return bool(configured) and hmac.compare_digest(supplied, configured)

    def allow_public_upload(self) -> bool:
        """Provide a small per-IP cooldown; production should also use proxy/WAF limits."""
        now = time.monotonic()
        forwarded_for = self.headers.get("X-Forwarded-For", "") if self.server.trust_proxy else ""
        client = forwarded_for.split(",", 1)[0].strip() or self.client_address[0]
        with self.server.upload_rate_limit_lock:
            previous = self.server.last_public_uploads.get(client)
            if previous is not None and now - previous < PUBLIC_UPLOAD_COOLDOWN_SECONDS:
                return False
            self.server.last_public_uploads[client] = now
        return True

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/analytics/summary":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            self.send_json(HTTPStatus.OK, build_public_analytics_summary())
            return
        if path == "/api/admin/analytics":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            if not self.is_analytics_admin():
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "管理令牌无效。"})
                return
            try:
                query = urlparse(self.path).query
                requested_days = next((int(value.split("=", 1)[1]) for value in query.split("&") if value.startswith("days=") and "=" in value), 30)
            except ValueError:
                requested_days = 30
            days = min(self.server.analytics_retention_days, max(1, requested_days))
            self.send_json(HTTPStatus.OK, build_analytics_report(days))
            return
        if path == "/api/public-library/status":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共上传未启用。"})
                return
            self.send_json(HTTPStatus.OK, {"publicLibrary": True})
            return
        if path == "/api/local-library/status":
            if not self.request_is_local():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "维护接口只允许本机访问。"})
                return
            self.send_json(HTTPStatus.OK, {"localLibrary": True})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/analytics/events":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的统计请求。"})
                return
            try:
                session, events = parse_analytics_payload(self.read_analytics_payload())
                record_analytics_events(session, events, self.server.analytics_retention_days)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法记录统计事件。"})
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path == "/api/public-library/songs":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共上传未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的上传请求。"})
                return
            if not self.allow_public_upload():
                self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "上传过于频繁，请 30 秒后再试。"})
                return
            try:
                _, songs = save_score(self.read_payload(), allow_replace=False)
            except DuplicateScoreError as error:
                self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法上传曲目。"})
                return
            self.send_json(HTTPStatus.CREATED, {"action": "created", "songs": songs})
            return
        if path != "/api/local-library/songs":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到维护接口。"})
            return
        if not self.request_is_local():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "维护接口只允许本机访问。"})
            return
        try:
            action, songs = save_score(self.read_payload())
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法写入本地曲库。"})
            return
        self.send_json(HTTPStatus.OK, {"action": action, "songs": songs})


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 Harmonica Deck 静态站点与曲库服务")
    parser.add_argument("--port", type=int, default=8765, help="本地端口（默认：8765）")
    parser.add_argument("--public", action="store_true", help="监听所有网卡，并启用匿名上传到公共曲库")
    parser.add_argument("--trust-proxy", action="store_true", help="使用反向代理传入的 X-Forwarded-For 做公共上传限流")
    parser.add_argument("--analytics-admin-token", default=os.environ.get("DELTA_ANALYTICS_ADMIN_TOKEN", ""), help="启用内置分析并保护管理接口的令牌；也可设 DELTA_ANALYTICS_ADMIN_TOKEN")
    parser.add_argument("--analytics-retention-days", type=int, default=DEFAULT_ANALYTICS_RETENTION_DAYS, help=f"匿名事件保留天数（默认 {DEFAULT_ANALYTICS_RETENTION_DAYS}，最多 365）")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    if not 1 <= args.analytics_retention_days <= 365:
        parser.error("统计保留天数必须在 1 到 365 之间")

    handler = lambda *args_, **kwargs: LocalLibraryRequestHandler(*args_, directory=str(REPOSITORY_ROOT), **kwargs)
    host = "0.0.0.0" if args.public else "127.0.0.1"
    server = ThreadingHTTPServer((host, args.port), handler)
    server.public_library = args.public
    server.trust_proxy = args.trust_proxy
    server.analytics_admin_token = args.analytics_admin_token
    server.analytics_enabled = bool(args.analytics_admin_token)
    server.analytics_retention_days = args.analytics_retention_days
    server.last_public_uploads: dict[str, float] = {}
    server.upload_rate_limit_lock = threading.Lock()
    if args.public:
        print(f"公共曲库服务已启动：http://0.0.0.0:{args.port}/")
        print("公共上传已启用；部署时请通过 HTTPS 反向代理，并配置 WAF 或限流。")
    else:
        print(f"本地维护服务已启动：http://127.0.0.1:{args.port}/")
        print("仅监听 127.0.0.1；按 Ctrl+C 停止。")
    if server.analytics_enabled:
        print(f"站内匿名分析已启用：/admin/analytics.html（事件保留 {server.analytics_retention_days} 天）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地维护服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
