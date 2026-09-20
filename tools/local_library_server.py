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
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import hmac
import io
import json
import os
import queue
import re
import secrets
import shutil
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
import uuid
import zipfile
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
MAINTENANCE_MARKER = REPOSITORY_ROOT / "data" / ".maintenance"
MAINTENANCE_PAGE = REPOSITORY_ROOT / "maintenance.html"
TOOLS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIRECTORY))

from import_community_scores import (  # noqa: E402
    FORMAT,
    REMIX_CODE_PATTERN,
    VERSION,
    canonical_package,
    dedupe_key,
    legacy_admin_id_for_score,
    legacy_analytics_score_id,
    remix_code_for_score,
    validate_package,
    write_library,
)


DATA_DIRECTORY = REPOSITORY_ROOT / "data"
SOURCE_DIRECTORY = DATA_DIRECTORY / "community-scores"
LIBRARY_OUTPUT = REPOSITORY_ROOT / "data" / "community-songs.js"
MAX_REQUEST_BYTES = 1_000_000
MAX_ANALYTICS_REQUEST_BYTES = 25_000
PUBLIC_UPLOAD_RATE_WINDOW_SECONDS = 30
PUBLIC_UPLOAD_RATE_LIMIT = 5
PUBLIC_EXPORT_COUNT_REFRESH_SECONDS = 10 * 60
PUBLIC_ANALYTICS_SUMMARY_CACHE_SECONDS = 60
PUBLIC_RANKINGS_CACHE_SECONDS = 5 * 60
PUBLIC_DONORS_CACHE_SECONDS = 60
PUBLIC_RANKING_SONG_LIMIT = 10
PUBLIC_RANKING_USER_LIMIT = 20
USER_ID_EFFECTS = ("default", "ice", "violet", "ember", "aurora")
# 配色分级：contribution 需要贡献达到 min 次，supporter 需要进入打赏名单。
# 贡献梯度 50 / 100 / 500，配色走蓝→紫→橙的稀有度阶梯；调整档位只需要改这张表。
# （styles.css 里还留了 gold / rose 两套备用配色，将来要用再加回这里和选择界面。）
USER_ID_EFFECT_UNLOCKS: dict[str, dict[str, Any]] = {
    "ice": {"kind": "contribution", "min": 50},
    "violet": {"kind": "contribution", "min": 100},
    "ember": {"kind": "contribution", "min": 500},
    "aurora": {"kind": "supporter"},
}
USER_ID_EFFECT_CONTRIBUTION_THRESHOLDS = (50, 100, 500)
AUTH_CODE_TTL_SECONDS = 10 * 60
AUTH_CODE_MAX_ATTEMPTS = 5
AUTH_CODE_EMAIL_LIMIT = 5
AUTH_CODE_IP_LIMIT = 12
AUTH_CODE_RATE_WINDOW_SECONDS = 60 * 60
AUTH_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
AUTH_DATABASE_TIMEOUT_SECONDS = 3
AUTH_MAIL_QUEUE_MAXSIZE = 64
AUTH_MAIL_WORKERS = 2
AUTH_SMTP_TIMEOUT_SECONDS = 15
AUTH_MAIL_TICKET_TTL_SECONDS = 15 * 60
AUTH_MAIL_TICKET_LIMIT = 256
REQUEST_SOCKET_TIMEOUT_SECONDS = 30
MAX_REQUEST_THREADS = 128
OAUTH_STATE_TTL_SECONDS = 10 * 60
OAUTH_HTTP_TIMEOUT_SECONDS = 15
GZIP_MIN_BYTES = 1024
GZIP_LEVEL = 6
COMPRESSED_ASSET_CACHE_MAX_BYTES = 48 * 1024 * 1024
COMPRESSIBLE_CONTENT_TYPES = (
    "text/",
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "image/svg+xml",
)
AUTH_COOKIE_NAME = "delta_auth_session"
OAUTH_STATE_COOKIE_NAME = "delta_oauth_state"
ADMIN_EMAIL = "274492469@qq.com"
LEGACY_OWNER_EMAIL = "274492469@qq.com"
LEGACY_OWNER_USER_ID = "jiko"
EXPORT_PROVIDER_EMAILS = {
    "mchose": "127709492@qq.com",
    "rog": "1960046012@qq.com",
}
EXPORT_BRAND_DEFINITIONS = (
    {"id": "logitech", "label": "Logitech", "subLabel": "G HUB"},
    {"id": "razer", "label": "Razer", "subLabel": "SYNAPSE"},
    {"id": "mchose", "label": "迈从", "subLabel": "MCHOSE"},
    {"id": "rog", "label": "ROG", "subLabel": "ARMOURY CRATE"},
    {"id": "atk", "label": "ATK", "subLabel": "MOUSE · KEYBOARD"},
    {"id": "vgn", "label": "VGN", "subLabel": "MOUSE · KEYBOARD"},
    {"id": "rapoo", "label": "Rapoo", "subLabel": "雷柏"},
    {"id": "aula", "label": "AULA", "subLabel": "MOUSE · KEYBOARD"},
    {"id": "recorder", "label": "通用录制", "subLabel": "RECORDER"},
)
EXPORT_METHOD_DEFINITIONS = (
    {"id": "logitech", "title": "Logitech G HUB", "description": "Lua 脚本 · 手动粘贴"},
    {"id": "razer-synapse-3", "title": "Razer Synapse 3", "description": "XML · 实验性兼容"},
    {"id": "razer-synapse-4", "title": "Razer Synapse 4", "description": "XML · 实验性兼容"},
    {"id": "mchose", "title": "迈从 MCHOSE", "description": "JSON · 宏文件"},
    {"id": "rog", "title": "ROG Armoury Crate", "description": "GMAC · 宏配置文件"},
    {"id": "recording-helper", "title": "口琴鼠标宏录制助手", "description": "Windows 64 位 · 一键录制"},
    {"id": "manual-entry", "title": "手动输入宏", "description": "三角洲键盘模式 · 谱子预览"},
)
EXPORT_BRAND_IDS = {item["id"] for item in EXPORT_BRAND_DEFINITIONS}
EXPORT_METHOD_IDS = {item["id"] for item in EXPORT_METHOD_DEFINITIONS}
EXPORT_DEFAULT_BRANDS = {
    "recording-helper": ["logitech", "razer", "mchose", "rog", "atk", "vgn", "rapoo", "aula", "recorder"],
    "manual-entry": ["logitech", "razer", "mchose", "rog", "atk", "vgn", "rapoo", "aula", "recorder"],
    "logitech": ["logitech"],
    "razer-synapse-3": ["razer"],
    "razer-synapse-4": ["razer"],
    "mchose": ["mchose"],
    "rog": ["rog"],
}
AUTH_DATABASE = DATA_DIRECTORY / "auth.sqlite3"
HOT_RANKING_DATABASE = DATA_DIRECTORY / "hot-rankings.sqlite3"
# User IDs may contain Unicode letters/numbers (including Chinese characters)
# while retaining the existing underscore support.
USER_ID_PATTERN = re.compile(r"^[\w]{3,24}$", re.UNICODE)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LIBRARY_LOCK = threading.Lock()
ANALYTICS_LOCK = threading.Lock()
AUTH_LOCK = threading.Lock()
HOT_RANKING_LOCK = threading.Lock()
ANALYTICS_DIRECTORY = DATA_DIRECTORY / "analytics"
DEFAULT_ANALYTICS_RETENTION_DAYS = 90
ACTIVE_VISITOR_WINDOW_SECONDS = 300
ANALYTICS_EVENTS = {
    "page_view", "directory_selected", "library_search", "song_loaded", "input_mode_selected",
    "midi_import_opened", "midi_selection_applied", "score_imported", "preview_started",
    "macro_section_opened", "export_mode_selected", "score_downloaded", "community_upload_succeeded", "macro_downloaded",
    "macro_exported", "lua_copied", "score_edit_opened", "score_edit_saved", "tour_started", "heartbeat",
}
ANALYTICS_ENUMERATIONS = {
    "entry": {"direct", "search", "social", "referral", "internal"},
    "origin": {"builtin", "community", "imported", "midi"},
    "mode": {"jianpu", "record", "precise", "keyboard"},
    "export_mode": {"general", "special"},
    "format": {"lua", "synapse_3", "synapse_4", "rog", "recorder", "deltamusic"},
    "directory": {"library", "midi", "manual"},
}
ANALYTICS_SCORE_ID_PATTERN = re.compile(r"^s[0-9a-f]{8}$")
LEGACY_ADMIN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$", re.IGNORECASE)
SCORE_EXPORT_EVENTS = {"macro_exported", "macro_downloaded", "lua_copied"}
HOT_RANKING_METRIC_VERSION = 3
OAUTH_PROVIDER_LABELS = {"qq": "QQ", "wechat": "微信"}
SINGLE_FLIGHT_WAIT_SECONDS = 30


class DuplicateScoreError(ValueError):
    """Raised when a public upload would replace an existing community score."""

    def __init__(self, message: str, *, owned_by_requester: bool = False) -> None:
        super().__init__(message)
        self.owned_by_requester = owned_by_requester


class SingleFlightCache:
    """Cache computed values by key with a TTL, computing each key only once at a time.

    Without this, every open tab that refreshes at the same moment notices the
    expired cache and starts the same expensive scan, so the cost of one rebuild
    gets multiplied by the number of waiting clients.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[float, Any]] = {}
        self._flights: dict[str, threading.Event] = {}

    def value(self, key: str, ttl: float, compute: Callable[[], Any]) -> Any:
        with self._lock:
            cached = self._values.get(key)
            if cached is not None and time.monotonic() - cached[0] < ttl:
                return cached[1]
            flight = self._flights.get(key)
            if flight is None:
                flight = threading.Event()
                self._flights[key] = flight
                leads = True
            else:
                leads = False
        if not leads:
            # 等领先者算完并复用结果；等超时或领先者失败时自己算一次，避免请求挂住。
            flight.wait(SINGLE_FLIGHT_WAIT_SECONDS)
            with self._lock:
                cached = self._values.get(key)
            if cached is not None:
                # 超时仍可退回上一份数据，好过让请求线程再叠加一次重算。
                return cached[1]
            return compute()
        try:
            value = compute()
        except BaseException:
            with self._lock:
                self._flights.pop(key, None)
            flight.set()
            raise
        with self._lock:
            self._values[key] = (time.monotonic(), value)
            self._flights.pop(key, None)
        flight.set()
        return value

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._values.clear()
            else:
                self._values.pop(key, None)


PUBLIC_ANALYTICS_SUMMARY_CACHE = SingleFlightCache()
PUBLIC_RANKINGS_CACHE = SingleFlightCache()
PUBLIC_DONORS_CACHE = SingleFlightCache()
EXPORT_EVENT_COUNT_CACHE = SingleFlightCache()


def analytics_event_path(day: date) -> Path:
    return ANALYTICS_DIRECTORY / f"events-{day.isoformat()}.ndjson"


def clean_analytics_properties(event: str, value: Any) -> dict[str, Any]:
    """Keep analytics bounded at the API boundary while naming score operations."""
    if not isinstance(value, dict):
        return {}
    properties: dict[str, Any] = {}
    for field, allowed in ANALYTICS_ENUMERATIONS.items():
        candidate = value.get(field)
        if candidate in allowed:
            properties[field] = candidate
    score_id = value.get("score_id")
    if isinstance(score_id, str) and (ANALYTICS_SCORE_ID_PATTERN.fullmatch(score_id) or REMIX_CODE_PATTERN.fullmatch(score_id)):
        properties["score_id"] = score_id.upper() if REMIX_CODE_PATTERN.fullmatch(score_id) else score_id.lower()
        for field, limit in (("score_title", 120), ("score_artist", 120), ("score_shared_by", 64)):
            candidate = value.get(field)
            if isinstance(candidate, str):
                cleaned = " ".join(candidate.split())[:limit]
                if cleaned:
                    properties[field] = cleaned
    # Search text, MIDI file names and free-form user input are never accepted.
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


def record_analytics_events(
    session: str,
    events: list[dict[str, Any]],
    retention_days: int,
    actor_key: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    record_time = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    path = analytics_event_path(now.date())
    lines = []
    for item in events:
        record = {"time": record_time, "session": session, "event": item["event"], "properties": item["properties"]}
        if item["event"] in SCORE_EXPORT_EVENTS:
            # Keep the stable account identity server-side and opaque. Legacy
            # records without this field fall back to their anonymous session.
            record["actor"] = actor_key or session
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
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
        "export_mode_selected": f"导出板块:{properties.get('export_mode', '其他')}",
        "macro_downloaded": f"下载:{properties.get('format', '宏')}",
        "macro_exported": f"导出:{properties.get('format', '宏')}",
        "score_downloaded": "下载谱子",
        "community_upload_succeeded": "上传曲库",
        "lua_copied": "复制 Lua",
        "score_edit_opened": "打开编辑",
        "score_edit_saved": "保存编辑",
        "tour_started": "打开教程",
    }
    return labels.get(event["event"], event["event"])


def analytics_record_time(item: dict[str, Any]) -> datetime | None:
    """Parse an event timestamp without letting malformed records break reports."""
    try:
        value = datetime.fromisoformat(str(item.get("time", "")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def analytics_export_key(item: dict[str, Any]) -> tuple[str, str, str]:
    """Collapse the paired client events emitted by one successful export."""
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    actor = item.get("actor") if isinstance(item.get("actor"), str) and item.get("actor") else item.get("session", "")
    score_id = properties.get("score_id") if isinstance(properties.get("score_id"), str) else item.get("event", "")
    return str(actor), str(score_id), str(item.get("time", ""))


def build_analytics_report(days: int) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
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

    score_aliases = analytics_score_aliases()

    sessions = {item["session"] for item in records}
    page_views = sum(item["event"] == "page_view" for item in records)
    today_sessions: set[str] = set()
    today_page_views = 0
    today_events = 0
    today_latest_seen: dict[str, datetime] = {}
    event_counts = Counter(item["event"] for item in records)
    event_sessions: dict[str, set[str]] = defaultdict(set)
    daily_sessions: dict[str, set[str]] = defaultdict(set)
    daily_views: Counter[str] = Counter()
    daily_exports: Counter[str] = Counter()
    daily_export_keys: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    daily_hourly_sessions: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    daily_hourly_views: dict[str, Counter[str]] = defaultdict(Counter)
    hourly_sessions: dict[str, set[str]] = defaultdict(set)
    hourly_views: Counter[str] = Counter()
    hourly_exports: Counter[str] = Counter()
    hourly_export_keys: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    hourly_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    source_counts: Counter[str] = Counter()
    journeys: dict[str, list[dict[str, Any]]] = defaultdict(list)
    score_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "sessions": set(),
        "scoreTitle": "",
        "scoreArtist": "",
        "loaded": 0,
        "editOpened": 0,
        "editSaved": 0,
        "formats": Counter(),
        "exportActors": set(),
    })
    score_edit_events = {"score_edit_opened", "score_edit_saved"}
    score_export_events = SCORE_EXPORT_EVENTS
    for item in records:
        event_sessions[item["event"]].add(item["session"])
        recorded_at = analytics_record_time(item)
        day = recorded_at.date().isoformat() if recorded_at else ""
        if recorded_at and recorded_at.date() == today:
            today_events += 1
            if item["event"] == "page_view":
                today_sessions.add(item["session"])
                today_page_views += 1
            if recorded_at > today_latest_seen.get(item["session"], datetime.min.replace(tzinfo=timezone.utc)):
                today_latest_seen[item["session"]] = recorded_at
        if day:
            daily_sessions[day].add(item["session"])
            hour = recorded_at.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z") if recorded_at else ""
            if hour:
                daily_hourly_sessions[day][hour].add(item["session"])
                if item["event"] == "page_view":
                    daily_hourly_views[day][hour] += 1
            if item["event"] == "page_view":
                daily_views[day] += 1
            if item["event"] in SCORE_EXPORT_EVENTS:
                export_key = analytics_export_key(item)
                if export_key not in daily_export_keys[day]:
                    daily_export_keys[day].add(export_key)
                    daily_exports[day] += 1
        if recorded_at and recorded_at >= hourly_start:
            hour = recorded_at.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
            hourly_sessions[hour].add(item["session"])
            if item["event"] == "page_view":
                hourly_views[hour] += 1
            if item["event"] in SCORE_EXPORT_EVENTS:
                export_key = analytics_export_key(item)
                if export_key not in hourly_export_keys[hour]:
                    hourly_export_keys[hour].add(export_key)
                    hourly_exports[hour] += 1
        if item["event"] == "page_view":
            source_counts[(item.get("properties") or {}).get("entry", "direct")] += 1
        journeys[item["session"]].append(item)
        properties = item.get("properties") or {}
        score_id = canonical_analytics_score_id(properties.get("score_id"), score_aliases)
        if score_id:
            stats = score_stats[score_id]
            stats["scoreTitle"] = str(properties.get("score_title") or stats["scoreTitle"])
            stats["scoreArtist"] = str(properties.get("score_artist") or stats["scoreArtist"])
            stats["sessions"].add(item["session"])
            if item["event"] in {"song_loaded", "score_imported", "midi_selection_applied"}:
                stats["loaded"] += 1
            if item["event"] in score_edit_events:
                stats["editOpened"] += item["event"] == "score_edit_opened"
                stats["editSaved"] += item["event"] == "score_edit_saved"
            if item["event"] in score_export_events:
                actor = item.get("actor") if isinstance(item.get("actor"), str) and item.get("actor") else item["session"]
                if actor not in stats["exportActors"]:
                    stats["exportActors"].add(actor)
                    format_name = properties.get("format") or item["event"].removesuffix("_downloaded").replace("_", " ")
                    stats["formats"][format_name] += 1

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
        "完成宏导出": {"macro_exported", "macro_downloaded", "lua_copied"},
    }
    funnel = [{"name": name, "sessions": len(set().union(*(event_sessions[event] for event in events)))} for name, events in funnel_groups.items()]
    timeline = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        timeline.append({"day": day, "sessions": len(daily_sessions[day]), "pageViews": daily_views[day], "scoreExports": daily_exports[day]})
    hourly_timeline = []
    for offset in range(24):
        hour = (hourly_start + timedelta(hours=offset)).isoformat().replace("+00:00", "Z")
        hourly_timeline.append({"hour": hour, "sessions": len(hourly_sessions[hour]), "pageViews": hourly_views[hour], "scoreExports": hourly_exports[hour]})
    daily_hourly_timeline = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        hours = []
        for hour_index in range(24):
            hour = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) + timedelta(days=offset, hours=hour_index)
            hour_key = hour.isoformat().replace("+00:00", "Z")
            hours.append({"hour": hour_key, "sessions": len(daily_hourly_sessions[day][hour_key]), "pageViews": daily_hourly_views[day][hour_key]})
        daily_hourly_timeline.append({"day": day, "hours": hours})
    score_operations = []
    for score_id, stats in score_stats.items():
        edit_count = stats["editOpened"] + stats["editSaved"]
        export_count = len(stats["exportActors"])
        operation_count = stats["loaded"] + edit_count + export_count
        if not operation_count:
            continue
        score_operations.append({
            "scoreId": score_id,
            "scoreTitle": stats["scoreTitle"],
            "scoreArtist": stats["scoreArtist"],
            "loaded": stats["loaded"],
            "edits": edit_count,
            "editOpened": stats["editOpened"],
            "editSaved": stats["editSaved"],
            "exports": export_count,
            "operations": operation_count,
            "sessions": len(stats["sessions"]),
            "formats": dict(stats["formats"].most_common()),
        })
    score_operations.sort(key=lambda item: (-item["operations"], item["scoreId"]))
    return {
        "rangeDays": days,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": {
            "timezone": "UTC",
            "todayDate": today.isoformat(),
            "today": {
                "uniqueVisitors": len(today_sessions),
                "pageViews": today_page_views,
                "events": today_events,
                "activeVisitors": sum(recorded_at >= now - timedelta(seconds=ACTIVE_VISITOR_WINDOW_SECONDS) for recorded_at in today_latest_seen.values()),
            },
            "range": {
                "uniqueVisitors": len(sessions),
                "pageViews": page_views,
                "events": len(records),
                "macroDownloads": event_counts["macro_downloaded"],
            },
            # Keep the old keys for the standalone analytics page and older clients.
            "sessions": len(sessions),
            "pageViews": page_views,
            "events": len(records),
            "macroDownloads": event_counts["macro_downloaded"],
        },
        "timeline": timeline,
        "hourlyTimeline": hourly_timeline,
        "dailyHourlyTimeline": daily_hourly_timeline,
        "sources": [{"name": name, "count": count} for name, count in source_counts.most_common(8)],
        "events": [{"name": name, "count": count, "sessions": len(event_sessions[name])} for name, count in event_counts.most_common()],
        "scoreOperations": score_operations[:100],
        "funnel": funnel,
        "paths": [{"path": path, "sessions": count} for path, count in path_counts.most_common(12)],
    }


def compute_registered_account_count() -> int:
    """Return the aggregate account count without exposing account details."""
    if not AUTH_DATABASE.exists():
        return 0
    try:
        with AUTH_LOCK, auth_database() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM accounts").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["total"] or 0) if row else 0


def compute_public_analytics_summary() -> dict[str, int]:
    """Count active visitors, today's raw page views, and registered accounts for the public header."""
    now = datetime.now(timezone.utc)
    today_page_views = 0
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
                if item.get("event") not in ANALYTICS_EVENTS or recorded_at > now:
                    continue
                session = item["session"]
                if recorded_at > latest_seen.get(session, datetime.min.replace(tzinfo=timezone.utc)):
                    latest_seen[session] = recorded_at
                if item.get("event") == "page_view":
                    today_page_views += 1
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    return {
        "activeVisitors": sum(recorded_at >= now - timedelta(seconds=ACTIVE_VISITOR_WINDOW_SECONDS) for recorded_at in latest_seen.values()),
        "todayPageViews": today_page_views,
        "registeredUsers": compute_registered_account_count(),
    }


def build_public_analytics_summary() -> dict[str, int]:
    """Return only aggregate counts suitable for the public site header."""
    return PUBLIC_ANALYTICS_SUMMARY_CACHE.value(
        "public-analytics-summary",
        PUBLIC_ANALYTICS_SUMMARY_CACHE_SECONDS,
        compute_public_analytics_summary,
    )


def sqlite_snapshot(path: Path) -> bytes:
    """Read a consistent SQLite snapshot without copying a live journal file."""
    if not path.exists():
        return b""
    try:
        source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            serialize = getattr(source, "serialize", None)
            return serialize() if callable(serialize) else path.read_bytes()
        finally:
            source.close()
    except sqlite3.Error:
        return path.read_bytes()


def build_data_backup() -> tuple[bytes, str]:
    """Create a restorable archive of persistent data only, never application source."""
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, bytes]] = []
    for path in sorted(DATA_DIRECTORY.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name == ".maintenance":
            continue
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        body = sqlite_snapshot(path) if path in {AUTH_DATABASE, HOT_RANKING_DATABASE} else path.read_bytes()
        entries.append((relative, body))

    manifest = {
        "format": "delta-harmonica-data-backup",
        "version": 1,
        "createdAt": now_iso_timestamp(),
        "contents": "仅包含 data/ 下的用户与站点持久化数据，不包含源代码、静态资源或临时维护标记。",
        "restore": [
            "停止站点服务。",
            "将压缩包内的 data/ 目录覆盖到项目根目录。",
            "确认 data/auth.sqlite3、data/community-scores/、data/analytics/ 和其他 data/ 文件均已恢复。",
            "重新启动站点服务。",
        ],
        "files": [{"path": path, "bytes": len(body)} for path, body in entries],
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        bundle.writestr("BACKUP-MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for path, body in entries:
            bundle.writestr(path, body)
    filename = f"delta-harmonica-data-backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.zip"
    return archive.getvalue(), filename


def analytics_score_id(score: dict[str, Any], origin: str = "community") -> str:
    """Use the immutable remix code for community scores."""
    remix_code = score.get("remixCode")
    if origin == "community" and isinstance(remix_code, str) and REMIX_CODE_PATTERN.fullmatch(remix_code.strip()):
        return remix_code.strip().upper()
    identity = "\u241f".join(
        str(score.get(field, "")).strip().lower()
        for field in ("title", "artist", "sharedBy")
    )
    identity = f"{origin}\u241f{identity}"
    value = 2166136261
    for character in identity:
        value ^= ord(character)
        value = (value * 16777619) & 0xFFFFFFFF
    return f"s{value:08x}"


def analytics_score_aliases() -> dict[str, str]:
    """Map pre-remix-code analytics IDs onto the current immutable score IDs."""
    aliases: dict[str, str] = {}
    for _, score in read_scores():
        current_id = analytics_score_id(score)
        aliases[legacy_analytics_score_id(score)] = current_id
        persisted_legacy = score.get("analyticsId")
        if isinstance(persisted_legacy, str) and ANALYTICS_SCORE_ID_PATTERN.fullmatch(persisted_legacy.strip().lower()):
            aliases[persisted_legacy.strip().lower()] = current_id
        for legacy_id in score.get("legacyAnalyticsIds", []):
            if isinstance(legacy_id, str) and ANALYTICS_SCORE_ID_PATTERN.fullmatch(legacy_id.strip().lower()):
                aliases[legacy_id.strip().lower()] = current_id
    return aliases


def canonical_analytics_score_id(value: Any, aliases: dict[str, str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if REMIX_CODE_PATTERN.fullmatch(normalized):
        return normalized.upper()
    legacy = normalized.lower()
    if ANALYTICS_SCORE_ID_PATTERN.fullmatch(legacy):
        return aliases.get(legacy, legacy)
    return None


def line_has_score_export_event(line: str) -> bool:
    """Cheap pre-filter so ordinary heartbeat lines never reach the JSON parser.

    Export events are rare compared with heartbeats and page views, and the
    writers always emit the event name as a quoted JSON string, so a substring
    test cannot drop a real export record.
    """
    return any(f'"{name}"' in line for name in SCORE_EXPORT_EVENTS)


def export_event_counts_for_period(retention_days: int) -> tuple[Counter[str], Counter[str]]:
    """Scan the window once: deduplicated exports per score and per actor."""
    safe_days = max(1, retention_days)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=safe_days - 1)
    exports: Counter[str] = Counter()
    actor_exports: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    aliases = analytics_score_aliases()
    for offset in range(safe_days):
        path = analytics_event_path(start + timedelta(days=offset))
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line_has_score_export_event(line):
                    continue
                item = json.loads(line)
                if not isinstance(item, dict) or item.get("event") not in SCORE_EXPORT_EVENTS:
                    continue
                properties = item.get("properties")
                score_id = properties.get("score_id") if isinstance(properties, dict) else None
                canonical_id = canonical_analytics_score_id(score_id, aliases)
                if not canonical_id:
                    continue
                actor = item.get("actor") if isinstance(item.get("actor"), str) and item.get("actor") else item.get("session")
                if not isinstance(actor, str):
                    continue
                export_key = (canonical_id, actor)
                if export_key in seen:
                    continue
                seen.add(export_key)
                exports[canonical_id] += 1
                actor_exports[actor] += 1
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return exports, actor_exports


def score_export_counts_for_period(retention_days: int) -> Counter[str]:
    """Read export totals once for the daily hot-ranking job."""
    return export_event_counts_for_period(retention_days)[0]


def candidate_analytics_days(target_date: date) -> list[date]:
    """Days whose UTC-named log file can contain records of one local calendar day."""
    local_zone = datetime.now().astimezone().tzinfo
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=local_zone)
    day_end = day_start + timedelta(days=1)
    return sorted({
        day_start.astimezone(timezone.utc).date(),
        (day_end - timedelta(microseconds=1)).astimezone(timezone.utc).date(),
    })


def yesterday_export_ranking() -> list[dict[str, Any]]:
    """Return unique-actor score exports for the previous local calendar day."""
    target_date = datetime.now().astimezone().date() - timedelta(days=1)
    exports: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    aliases = analytics_score_aliases()
    if not ANALYTICS_DIRECTORY.exists():
        return []
    # 只读覆盖目标本地日的那一到两个日志文件，不再遍历整个保留期目录。
    for day in candidate_analytics_days(target_date):
        path = analytics_event_path(day)
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            if not line_has_score_export_event(line):
                continue
            try:
                item = json.loads(line)
                recorded_at = datetime.fromisoformat(str(item.get("time", "")).replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if recorded_at.astimezone().date() != target_date or item.get("event") not in SCORE_EXPORT_EVENTS:
                continue
            properties = item.get("properties")
            score_id = properties.get("score_id") if isinstance(properties, dict) else None
            actor = item.get("actor") if isinstance(item.get("actor"), str) and item.get("actor") else item.get("session")
            canonical_id = canonical_analytics_score_id(score_id, aliases)
            if not canonical_id or not isinstance(actor, str):
                continue
            export_key = (canonical_id, actor)
            if export_key not in seen:
                seen.add(export_key)
                exports[canonical_id] += 1
    ordered = sorted(exports.items(), key=lambda item: (-item[1], item[0]))[:PUBLIC_RANKING_SONG_LIMIT]
    return [{"rank": rank, "scoreId": score_id, "exports": count} for rank, (score_id, count) in enumerate(ordered, start=1)]


def usage_ranking(server: ThreadingHTTPServer, auth_enabled: bool, retention_days: int) -> list[dict[str, Any]]:
    """Rank accounts by how many distinct scores they exported in the window.

    Export events carry an opaque actor key: an HMAC of the account id for
    logged-in users, or the anonymous session otherwise. Only actors that map
    back to a registered account can appear here.
    """
    if not auth_enabled:
        return []
    actor_counts = cached_actor_export_counts(retention_days)
    if not actor_counts:
        return []
    try:
        with AUTH_LOCK, auth_database() as connection:
            rows = connection.execute("SELECT id, user_id FROM accounts").fetchall()
    except sqlite3.OperationalError:
        return []
    users_by_actor = {analytics_actor_key(server, str(row["id"])): str(row["user_id"]) for row in rows}
    totals: Counter[str] = Counter()
    for actor, count in actor_counts.items():
        user_id = users_by_actor.get(actor)
        if user_id:
            totals[user_id] += count
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))
    return [
        {"rank": rank, "userId": user_id, "exports": count}
        for rank, (user_id, count) in enumerate(ordered[:PUBLIC_RANKING_USER_LIMIT], start=1)
    ]


def public_owned_scores(auth_enabled: bool) -> list[tuple[str, str]]:
    """Return immutable remix codes paired with their account user IDs."""
    if not auth_enabled:
        return []
    public_scores = {score["remixCode"]: score for path, score in read_scores() if is_canonical_source(path)}
    if not public_scores:
        return []
    with AUTH_LOCK, auth_database() as connection:
        rows = connection.execute(
            "SELECT accounts.user_id AS user_id, score_owners.remix_code AS remix_code "
            "FROM score_owners JOIN accounts ON accounts.id = score_owners.account_id"
        ).fetchall()
    return [
        (str(row["user_id"]), public_scores[str(row["remix_code"])]["remixCode"])
        for row in rows
        if str(row["remix_code"]) in public_scores
    ]


def upload_ranking(auth_enabled: bool) -> list[dict[str, Any]]:
    """Count each account's currently published, owned community scores."""
    counts: Counter[str] = Counter(user_id for user_id, _ in public_owned_scores(auth_enabled))
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))
    return [{"rank": rank, "userId": user_id, "uploads": count} for rank, (user_id, count) in enumerate(ordered, start=1)]


def contribution_ranking(auth_enabled: bool, retention_days: int) -> list[dict[str, Any]]:
    """Sum deduplicated exports for each account's currently published scores."""
    if not auth_enabled:
        return []
    exports_by_score = cached_score_export_counts(retention_days)
    counts: Counter[str] = Counter()
    for user_id, score_id in public_owned_scores(auth_enabled):
        counts[user_id] += exports_by_score.get(score_id, 0)
    ordered = sorted(
        ((user_id, count) for user_id, count in counts.items() if count > 0),
        key=lambda item: (-item[1], item[0].casefold(), item[0]),
    )
    return [{"rank": rank, "userId": user_id, "exports": count} for rank, (user_id, count) in enumerate(ordered, start=1)]


def compute_public_rankings(server: ThreadingHTTPServer, auth_enabled: bool, retention_days: int) -> dict[str, Any]:
    """Assemble the public leaderboards for the homepage."""
    safe_days = max(1, retention_days)
    yesterday = datetime.now().astimezone().date() - timedelta(days=1)
    return {
        "rankingDate": yesterday.isoformat(),
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "uploads": upload_ranking(auth_enabled),
        "contributions": contribution_ranking(auth_enabled, safe_days),
        "yesterdayExports": yesterday_export_ranking(),
        "usage": usage_ranking(server, auth_enabled, safe_days),
        "usageWindowDays": safe_days,
        "userEffects": public_user_effects(server),
    }


def build_public_rankings(server: ThreadingHTTPServer, auth_enabled: bool, retention_days: int) -> dict[str, Any]:
    """Build the privacy-safe rankings consumed by the public homepage."""
    return PUBLIC_RANKINGS_CACHE.value(
        f"public-rankings:{int(bool(auth_enabled))}:{max(1, retention_days)}",
        PUBLIC_RANKINGS_CACHE_SECONDS,
        lambda: compute_public_rankings(server, auth_enabled, retention_days),
    )


def hot_ranking_database() -> sqlite3.Connection:
    HOT_RANKING_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(HOT_RANKING_DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_hot_ranking_database() -> None:
    with HOT_RANKING_LOCK, hot_ranking_database() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS daily_hot_rankings ("
            "ranking_date TEXT PRIMARY KEY, generated_at TEXT NOT NULL, "
            "retention_days INTEGER NOT NULL, scores_json TEXT NOT NULL, "
            "metric_version INTEGER NOT NULL DEFAULT 1)"
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(daily_hot_rankings)").fetchall()}
        if "metric_version" not in columns:
            connection.execute("ALTER TABLE daily_hot_rankings ADD COLUMN metric_version INTEGER NOT NULL DEFAULT 1")


def build_daily_hot_ranking(retention_days: int, ranking_date: str | None = None) -> dict[str, Any]:
    counts = score_export_counts_for_period(retention_days)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "rankingDate": ranking_date or datetime.now().astimezone().date().isoformat(),
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scores": [
            {"scoreId": score_id, "exports": count, "rank": rank}
            for rank, (score_id, count) in enumerate(ordered, start=1)
        ],
    }


def get_daily_hot_ranking(retention_days: int) -> dict[str, Any]:
    """Return today's persisted ranking; calculate it at most once per day."""
    safe_days = max(1, retention_days)
    ranking_date = datetime.now().astimezone().date().isoformat()
    initialize_hot_ranking_database()
    with HOT_RANKING_LOCK, hot_ranking_database() as connection:
        row = connection.execute(
            "SELECT ranking_date, generated_at, retention_days, scores_json, metric_version "
            "FROM daily_hot_rankings WHERE ranking_date = ?",
            (ranking_date,),
        ).fetchone()
        if row and row["retention_days"] == safe_days and row["metric_version"] == HOT_RANKING_METRIC_VERSION:
            try:
                scores = json.loads(row["scores_json"])
                if isinstance(scores, list):
                    return {"rankingDate": row["ranking_date"], "generatedAt": row["generated_at"], "scores": scores}
            except (TypeError, json.JSONDecodeError):
                pass
        ranking = build_daily_hot_ranking(safe_days, ranking_date)
        connection.execute(
            "INSERT INTO daily_hot_rankings(ranking_date, generated_at, retention_days, scores_json, metric_version) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(ranking_date) DO UPDATE SET "
            "generated_at = excluded.generated_at, retention_days = excluded.retention_days, "
            "scores_json = excluded.scores_json, metric_version = excluded.metric_version",
            (ranking["rankingDate"], ranking["generatedAt"], safe_days, json.dumps(ranking["scores"], separators=(",", ":")), HOT_RANKING_METRIC_VERSION),
        )
        return ranking


def cached_export_event_counts(retention_days: int) -> tuple[Counter[str], Counter[str]]:
    """Share one scan of the retention window between every derived leaderboard."""
    safe_days = max(1, retention_days)
    return EXPORT_EVENT_COUNT_CACHE.value(
        f"export-event-counts:{safe_days}",
        PUBLIC_EXPORT_COUNT_REFRESH_SECONDS,
        lambda: export_event_counts_for_period(safe_days),
    )


def cached_score_export_counts(retention_days: int) -> Counter[str]:
    """Deduplicated export totals per score."""
    return cached_export_event_counts(retention_days)[0]


def cached_actor_export_counts(retention_days: int) -> Counter[str]:
    """Deduplicated export totals per actor, from the same cached scan."""
    return cached_export_event_counts(retention_days)[1]


def build_public_score_export_summary(retention_days: int) -> dict[str, Any]:
    """Return export totals from the shared cached scan, independent of the daily hot ranking."""
    counts = cached_score_export_counts(retention_days)
    return {
        "rankingDate": datetime.now().astimezone().date().isoformat(),
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scores": [
            {"scoreId": score_id, "exports": count, "rank": rank}
            for rank, (score_id, count) in enumerate(sorted(counts.items(), key=lambda item: (-item[1], item[0])), start=1)
        ],
    }


def hot_ranking_scheduler(retention_days: int, stop_event: threading.Event) -> None:
    """Refresh the ranking at the next local midnight and every midnight after it."""
    while True:
        now = datetime.now().astimezone()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = max(1, (next_midnight - now).total_seconds())
        if stop_event.wait(wait_seconds):
            return
        try:
            get_daily_hot_ranking(retention_days)
        except (OSError, sqlite3.Error, ValueError) as error:
            print(f"热门曲库每日排行更新失败：{error}", file=sys.stderr)


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
        key = score["remixCode"]
        if key in seen:
            raise ValueError(
                f"曲库源文件存在重复的改曲码 {key}："
                f"{seen[key].relative_to(REPOSITORY_ROOT)}、{path.relative_to(REPOSITORY_ROOT)}"
            )
        seen[key] = path
        scores.append((path, score))
    return scores


def filename_for(score: dict[str, Any]) -> str:
    readable = "-".join(score[field] for field in ("title", "artist", "sharedBy"))
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", readable).strip("-")[:72] or "community-score"
    return f"{slug}-{score['remixCode'].lower()}.deltamusic"


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


def legacy_admin_id(score: dict[str, Any]) -> str:
    aliases = score.get("legacyAdminIds")
    if isinstance(aliases, list):
        for value in aliases:
            if isinstance(value, str) and LEGACY_ADMIN_ID_PATTERN.fullmatch(value.strip().lower()):
                return value.strip().lower()
    return legacy_admin_id_for_score(score)


def normalize_remix_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().upper()
    return candidate if REMIX_CODE_PATTERN.fullmatch(candidate) else None


def resolve_score_reference(payload: Any, *, allow_metadata: bool = True) -> tuple[Path, dict[str, Any]]:
    """Resolve the immutable remix code, with legacy request compatibility."""
    if not isinstance(payload, dict):
        raise ValueError("曲目标识无效。")
    scores = [(path, score) for path, score in read_scores() if is_canonical_source(path)]
    remix_code = normalize_remix_code(payload.get("remixCode")) or normalize_remix_code(payload.get("id"))
    if remix_code:
        matches = [(path, score) for path, score in scores if score["remixCode"] == remix_code]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise FileNotFoundError("未找到该改曲码对应的曲目。")
        raise ValueError("改曲码对应多个源文件，请先整理曲库。")

    legacy_id = payload.get("legacyId") or payload.get("id")
    if isinstance(legacy_id, str) and LEGACY_ADMIN_ID_PATTERN.fullmatch(legacy_id.strip()):
        target_legacy_id = legacy_id.strip().lower()
        matches = [
            (path, score) for path, score in scores
            if target_legacy_id in {
                legacy_admin_id(score),
                *[value.strip().lower() for value in score.get("legacyAdminIds", []) if isinstance(value, str)],
            }
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise FileNotFoundError("未找到该曲目。")
        raise ValueError("旧曲目标识对应多个源文件，请先整理曲库。")

    requested_path = payload.get("file")
    if isinstance(requested_path, str) and requested_path.strip():
        candidate = (REPOSITORY_ROOT / requested_path.strip()).resolve()
        matches = [(path, score) for path, score in scores if path.resolve() == candidate]
        if len(matches) == 1:
            return matches[0]

    if allow_metadata:
        fields = ("title", "artist", "sharedBy")
        if all(isinstance(payload.get(field), str) and payload[field].strip() for field in fields):
            identity = {field: payload[field].strip() for field in fields}
            matches = [(path, score) for path, score in scores if dedupe_key(score) == dedupe_key(identity)]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError("歌名、作者和共享人无法唯一定位曲目，请改用改曲码。")
    raise FileNotFoundError("未找到该曲目。")


def score_owner_account_id(path: Path, score: dict[str, Any] | None = None) -> str | None:
    relative = str(path.relative_to(REPOSITORY_ROOT))
    with AUTH_LOCK, auth_database() as connection:
        if score and score.get("remixCode"):
            row = connection.execute("SELECT account_id FROM score_owners WHERE remix_code = ?", (score["remixCode"],)).fetchone()
        else:
            row = connection.execute("SELECT account_id FROM score_owners WHERE score_path = ?", (relative,)).fetchone()
    return row["account_id"] if row else None


def same_score_metadata(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Require all public identity fields before an edit can replace a score."""
    return all(
        str(left.get(field, "")).strip().casefold() == str(right.get(field, "")).strip().casefold()
        for field in ("title", "artist", "sharedBy")
    )


def reset_uploaded_identity(score: dict[str, Any]) -> None:
    """Discard a stale client identity and derive a new score identity."""
    score["remixCode"] = remix_code_for_score(score)
    score.pop("analyticsId", None)
    score["legacyAnalyticsIds"] = []
    score["legacyAdminIds"] = [legacy_admin_id_for_score(score)]


def save_score(
    payload: Any,
    *,
    allow_replace: bool = True,
    owner_account_id: str | None = None,
    replace_existing: bool = False,
) -> tuple[str, list[dict[str, Any]], Path]:
    """Validate, store, and expose one score while serialising concurrent uploads."""
    incoming_code = normalize_remix_code(payload.get("remixCode")) if isinstance(payload, dict) else None
    score = validate_package(payload)
    with LIBRARY_LOCK:
        existing_scores = read_scores()
        matches = [(path, item) for path, item in existing_scores if item["remixCode"] == score["remixCode"]]
        can_replace = bool(matches and replace_existing and same_score_metadata(score, matches[0][1]))
        stale_code = bool(incoming_code and incoming_code != remix_code_for_score(score))
        if (stale_code and not can_replace) or (matches and not can_replace):
            # A viewed score or a stale package may carry another score's code.
            # Re-key it from the submitted content and never let that request
            # replace the code it accidentally referenced.
            reset_uploaded_identity(score)
            matches = [(path, item) for path, item in existing_scores if item["remixCode"] == score["remixCode"]]
            allow_replace = False
        if not matches and owner_account_id and not incoming_code and replace_existing:
            owned_title_artist_matches = [
                (path, item)
                for path, item in existing_scores
                if item["title"].casefold() == score["title"].casefold()
                and item["artist"].casefold() == score["artist"].casefold()
                and item["sharedBy"].casefold() == score["sharedBy"].casefold()
                and score_owner_account_id(path) == owner_account_id
            ]
            if len(owned_title_artist_matches) > 1:
                raise ValueError("我的曲库中存在多个相同歌名和作者的曲目，请先手动整理源文件。")
            matches = owned_title_artist_matches
        if len(matches) > 1:
            raise ValueError("曲库中存在重复改曲码，请先手动整理源文件。")
        if matches and not allow_replace:
            owned_by_requester = owner_account_id and len(matches) == 1 and score_owner_account_id(matches[0][0]) == owner_account_id
            if owned_by_requester:
                raise DuplicateScoreError("同一账号已有同名曲目，是否确认覆盖？", owned_by_requester=True)
            raise DuplicateScoreError("该改曲码已存在，不能覆盖已上传曲目。")
        if matches and allow_replace and owner_account_id:
            owned_by_requester = len(matches) == 1 and score_owner_account_id(matches[0][0]) == owner_account_id
            if not owned_by_requester:
                raise DuplicateScoreError("该曲目不属于当前账号，不能覆盖已上传曲目。")

        existing_path = matches[0][0] if matches else None
        existing_score = matches[0][1] if matches else None
        if existing_score:
            score["remixCode"] = existing_score["remixCode"]
            if existing_score.get("analyticsId"):
                score["analyticsId"] = existing_score["analyticsId"]
            else:
                score.pop("analyticsId", None)
            if existing_score.get("legacyAnalyticsIds"):
                score["legacyAnalyticsIds"] = existing_score["legacyAnalyticsIds"]
            else:
                score.pop("legacyAnalyticsIds", None)
            score["legacyAdminIds"] = existing_score.get("legacyAdminIds") or [legacy_admin_id(existing_score)]
            if existing_score.get("sponsor") and not score.get("sponsor"):
                score["sponsor"] = existing_score["sponsor"]
        score["createdAt"] = existing_score.get("createdAt") if existing_score else now_iso_timestamp()
        destination = existing_path if existing_path and is_canonical_source(existing_path) else SOURCE_DIRECTORY / filename_for(score)
        package = canonical_package(score)
        write_json_atomically(destination, package)
        if existing_path and existing_path != destination:
            existing_path.unlink()

        rebuilt_scores = [item for _, item in read_scores()]
        write_library(LIBRARY_OUTPUT, rebuilt_scores)
        return ("updated" if matches else "created"), rebuilt_scores, destination


def update_owned_score(account_id: str, user_id: str, payload: Any) -> tuple[str, list[dict[str, Any]], Path]:
    """Update a user's score metadata and notation without allowing ownership changes."""
    if not isinstance(payload, dict) or not isinstance(payload.get("original"), dict):
        raise ValueError("曲目编辑请求格式无效。")
    original = payload["original"]
    original_code = normalize_remix_code(original.get("remixCode"))
    original_title = original.get("title")
    original_artist = original.get("artist")
    if not original_code and (not isinstance(original_title, str) or not original_title.strip() or len(original_title.strip()) > 48):
        raise ValueError("原曲歌名无效。")
    if not original_code and (not isinstance(original_artist, str) or not original_artist.strip() or len(original_artist.strip()) > 64):
        raise ValueError("原曲歌手/作者无效。")
    candidate = validate_package({
        "format": FORMAT,
        "version": VERSION,
        "title": payload.get("title"),
        "artist": payload.get("artist"),
        "sharedBy": user_id,
        "key": payload.get("key"),
        "meter": payload.get("meter"),
        "bpm": payload.get("bpm"),
        "jianpu": payload.get("jianpu"),
        "displayUrl": payload.get("displayUrl"),
        "declaration": payload.get("declaration"),
    })
    with LIBRARY_LOCK:
        existing_scores = read_scores()
        matches = []
        for path, score in existing_scores:
            if not is_canonical_source(path) or score_owner_account_id(path, score) != account_id:
                continue
            if original_code and score["remixCode"] == original_code:
                matches.append((path, score))
            elif not original_code and score["title"].casefold() == original_title.strip().casefold() and score["artist"].casefold() == original_artist.strip().casefold():
                matches.append((path, score))
        if not matches:
            raise FileNotFoundError("未找到属于当前账号的曲目。")
        if len(matches) > 1:
            raise ValueError("我的曲库中存在多个相同歌名和作者的曲目，请先手动整理源文件。")
        existing_path, existing_score = matches[0]
        candidate["remixCode"] = existing_score["remixCode"]
        if existing_score.get("analyticsId"):
            candidate["analyticsId"] = existing_score["analyticsId"]
        else:
            candidate.pop("analyticsId", None)
        if existing_score.get("legacyAnalyticsIds"):
            candidate["legacyAnalyticsIds"] = existing_score["legacyAnalyticsIds"]
        else:
            candidate.pop("legacyAnalyticsIds", None)
        candidate["legacyAdminIds"] = existing_score.get("legacyAdminIds") or [legacy_admin_id(existing_score)]
        if existing_score.get("sponsor"):
            candidate["sponsor"] = existing_score["sponsor"]
        # Keep compatibility with older clients that do not send declaration;
        # an explicit empty declaration still clears the stored value.
        if "declaration" not in payload and existing_score.get("declaration"):
            candidate["declaration"] = existing_score["declaration"]
        destination = existing_path
        candidate["createdAt"] = existing_score.get("createdAt") or now_iso_timestamp()
        package = canonical_package(candidate)
        write_json_atomically(destination, package)
        rebuilt_scores = [item for _, item in read_scores()]
        write_library(LIBRARY_OUTPUT, rebuilt_scores)
        return "updated", rebuilt_scores, destination


def auth_database() -> sqlite3.Connection:
    """Open the small persistent account store with safe per-request settings."""
    AUTH_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_DATABASE, timeout=AUTH_DATABASE_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {AUTH_DATABASE_TIMEOUT_SECONDS * 1000}")
    return connection


def initialize_auth_database() -> None:
    with AUTH_LOCK, auth_database() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                user_id TEXT NOT NULL UNIQUE COLLATE NOCASE,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_id_history (
                user_id TEXT PRIMARY KEY COLLATE NOCASE,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                reserved_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS email_codes (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                code_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oauth_identities (
                provider TEXT NOT NULL,
                subject TEXT NOT NULL,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                display_name TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                PRIMARY KEY(provider, subject),
                UNIQUE(account_id, provider)
            );
            CREATE TABLE IF NOT EXISTS score_owners (
                remix_code TEXT PRIMARY KEY,
                score_path TEXT NOT NULL UNIQUE,
                account_id TEXT NOT NULL REFERENCES accounts(id)
            );
            CREATE TABLE IF NOT EXISTS recommended_scores (
                remix_code TEXT PRIMARY KEY,
                title TEXT NOT NULL COLLATE NOCASE,
                artist TEXT NOT NULL COLLATE NOCASE,
                shared_by TEXT NOT NULL COLLATE NOCASE,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS export_method_brands (
                method_id TEXT NOT NULL,
                brand_id TEXT NOT NULL,
                PRIMARY KEY(method_id, brand_id)
            );
            CREATE TABLE IF NOT EXISTS donations (
                account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                amount_cents INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_effects (
                account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                effect TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effect_unlock_notices (
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                effect TEXT NOT NULL,
                notified_at INTEGER NOT NULL,
                PRIMARY KEY(account_id, effect)
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
        """)
        # 早期本地库可能已经建过没有 created_at 的 donations 表，这里补齐列。
        donation_columns = {row[1] for row in connection.execute("PRAGMA table_info(donations)").fetchall()}
        if "created_at" not in donation_columns:
            connection.execute("ALTER TABLE donations ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
        for method_id, brand_ids in EXPORT_DEFAULT_BRANDS.items():
            existing = connection.execute(
                "SELECT 1 FROM export_method_brands WHERE method_id = ? LIMIT 1",
                (method_id,),
            ).fetchone()
            if existing:
                continue
            connection.executemany(
                "INSERT OR IGNORE INTO export_method_brands(method_id, brand_id) VALUES (?, ?)",
                [(method_id, brand_id) for brand_id in brand_ids],
            )


def migrate_identity_tables() -> None:
    """Migrate path/metadata keyed rows to immutable remix-code keys."""
    with AUTH_LOCK, auth_database() as connection:
        owner_columns = {row[1] for row in connection.execute("PRAGMA table_info(score_owners)").fetchall()}
        if "remix_code" not in owner_columns:
            connection.execute(
                "CREATE TABLE score_owners_v2 (remix_code TEXT PRIMARY KEY, score_path TEXT NOT NULL UNIQUE, account_id TEXT NOT NULL REFERENCES accounts(id))"
            )
            rows = connection.execute("SELECT score_path, account_id FROM score_owners").fetchall()
            for row in rows:
                path = (REPOSITORY_ROOT / row["score_path"]).resolve()
                if not path.exists():
                    continue
                score = validate_package(json.loads(path.read_text(encoding="utf-8")))
                connection.execute(
                    "INSERT INTO score_owners_v2(remix_code, score_path, account_id) VALUES (?, ?, ?)",
                    (score["remixCode"], row["score_path"], row["account_id"]),
                )
            connection.execute("DROP TABLE score_owners")
            connection.execute("ALTER TABLE score_owners_v2 RENAME TO score_owners")

        recommendation_columns = {row[1] for row in connection.execute("PRAGMA table_info(recommended_scores)").fetchall()}
        if "remix_code" not in recommendation_columns:
            connection.execute(
                "CREATE TABLE recommended_scores_v2 (remix_code TEXT PRIMARY KEY, title TEXT NOT NULL COLLATE NOCASE, artist TEXT NOT NULL COLLATE NOCASE, shared_by TEXT NOT NULL COLLATE NOCASE, created_at INTEGER NOT NULL)"
            )
            rows = connection.execute("SELECT title, artist, shared_by, created_at FROM recommended_scores").fetchall()
            current_scores = [score for path, score in read_scores() if is_canonical_source(path)]
            for row in rows:
                matches = [score for score in current_scores if dedupe_key(score) == dedupe_key({"title": row["title"], "artist": row["artist"], "sharedBy": row["shared_by"]})]
                if len(matches) == 1:
                    score = matches[0]
                    connection.execute(
                        "INSERT INTO recommended_scores_v2(remix_code, title, artist, shared_by, created_at) VALUES (?, ?, ?, ?, ?)",
                        (score["remixCode"], score["title"], score["artist"], score["sharedBy"], row["created_at"]),
                    )
            connection.execute("DROP TABLE recommended_scores")
            connection.execute("ALTER TABLE recommended_scores_v2 RENAME TO recommended_scores")


def now_timestamp() -> int:
    return int(time.time())


def now_iso_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("请输入有效的邮箱地址。")
    return email


def validate_user_id(value: Any) -> str:
    user_id = str(value or "").strip()
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise ValueError("用户 ID 应为 3–24 个字母、数字、中文字符或下划线。")
    return user_id


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        visible = local[:1] + "*"
    else:
        visible = local[:2] + "***"
    return f"{visible}@{domain}"


def is_admin_account(account: sqlite3.Row | dict[str, Any] | None) -> bool:
    return bool(account and str(account["email"]).casefold() == ADMIN_EMAIL.casefold())


def account_payload(server: ThreadingHTTPServer, account: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    email = str(account["email"])
    if email.endswith("@oauth.invalid"):
        provider = "QQ" if email.startswith("qq_") else "微信"
        credential = f"{provider} 登录账号"
    else:
        credential = mask_email(email)
    return {
        "userId": account["user_id"],
        "email": credential,
        "isAdmin": is_admin_account(account),
        "effectState": account_effect_state(server, account),
    }


def export_provider_payload() -> dict[str, str]:
    """Return only the current provider IDs used on the export cards."""
    initialize_auth_database()
    with AUTH_LOCK, auth_database() as connection:
        rows = connection.execute(
            "SELECT email, user_id FROM accounts WHERE lower(email) IN (?, ?)",
            tuple(email.casefold() for email in EXPORT_PROVIDER_EMAILS.values()),
        ).fetchall()
    user_ids = {str(row["email"]).casefold(): str(row["user_id"]).strip() for row in rows}
    return {
        provider: user_ids.get(email.casefold(), "")
        for provider, email in EXPORT_PROVIDER_EMAILS.items()
    }


def export_methods_payload() -> dict[str, Any]:
    """Return the fixed export method and brand catalogue for the public UI."""
    initialize_auth_database()
    with AUTH_LOCK, auth_database() as connection:
        rows = connection.execute(
            "SELECT method_id, brand_id FROM export_method_brands ORDER BY method_id, brand_id"
        ).fetchall()
    bindings: dict[str, set[str]] = {method_id: set() for method_id in EXPORT_METHOD_IDS}
    for row in rows:
        if row["method_id"] in bindings and row["brand_id"] in EXPORT_BRAND_IDS:
            bindings[row["method_id"]].add(row["brand_id"])
    return {
        "brands": [dict(item) for item in EXPORT_BRAND_DEFINITIONS],
        "methods": [
            {**dict(method), "brandIds": [brand["id"] for brand in EXPORT_BRAND_DEFINITIONS if brand["id"] in bindings[method["id"]]] or list(EXPORT_DEFAULT_BRANDS[method["id"]])}
            for method in EXPORT_METHOD_DEFINITIONS
        ],
    }


def update_export_methods(payload: Any) -> dict[str, Any]:
    """Validate and persist the complete export-method brand mapping."""
    if not isinstance(payload, dict) or not isinstance(payload.get("methods"), list):
        raise ValueError("导出方式配置格式无效。")
    submitted: dict[str, list[str]] = {}
    for item in payload["methods"]:
        if not isinstance(item, dict):
            raise ValueError("导出方式配置项无效。")
        method_id = item.get("id")
        brand_ids = item.get("brandIds")
        if not isinstance(method_id, str) or method_id not in EXPORT_METHOD_IDS or method_id in submitted:
            raise ValueError("导出方式 ID 无效或重复。")
        if not isinstance(brand_ids, list) or not brand_ids:
            raise ValueError("每个导出方式至少需要选择一个适用品牌。")
        cleaned = [str(brand_id).strip() for brand_id in brand_ids]
        if len(cleaned) != len(set(cleaned)) or any(brand_id not in EXPORT_BRAND_IDS for brand_id in cleaned):
            raise ValueError("适用品牌 ID 无效或重复。")
        submitted[method_id] = cleaned
    if set(submitted) != EXPORT_METHOD_IDS:
        raise ValueError("必须同时提交全部导出方式配置。")

    initialize_auth_database()
    with AUTH_LOCK, auth_database() as connection:
        connection.execute("DELETE FROM export_method_brands")
        connection.executemany(
            "INSERT INTO export_method_brands(method_id, brand_id) VALUES (?, ?)",
            [(method_id, brand_id) for method_id, brand_ids in submitted.items() for brand_id in brand_ids],
        )
    return export_methods_payload()


def recommendation_identity(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("推荐曲目请求格式无效。")
    remix_code = normalize_remix_code(payload.get("remixCode"))
    if remix_code:
        _, score = resolve_score_reference({"remixCode": remix_code}, allow_metadata=False)
        return {"remixCode": remix_code, "title": score["title"], "artist": score["artist"], "sharedBy": score["sharedBy"]}
    identity: dict[str, str] = {}
    for field, limit, label in (("title", 48, "歌名"), ("artist", 64, "歌手/作者"), ("sharedBy", 48, "共享人")):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"推荐曲目中的{label}无效。")
        identity[field] = value.strip()
    _, score = resolve_score_reference(identity)
    return {"remixCode": score["remixCode"], **identity}


def list_recommendations() -> list[dict[str, str]]:
    with AUTH_LOCK, auth_database() as connection:
        rows = connection.execute(
            "SELECT remix_code AS remixCode, title, artist, shared_by AS sharedBy FROM recommended_scores ORDER BY created_at, remix_code"
        ).fetchall()
    return [{"remixCode": row["remixCode"], "title": row["title"], "artist": row["artist"], "sharedBy": row["sharedBy"]} for row in rows]


def admin_library_catalog() -> list[dict[str, Any]]:
    """Return the editable community catalogue for the private admin console."""
    with AUTH_LOCK, auth_database() as connection:
        owner_rows = connection.execute(
            "SELECT remix_code, accounts.user_id FROM score_owners "
            "JOIN accounts ON accounts.id = score_owners.account_id"
        ).fetchall()
        recommendation_rows = connection.execute(
            "SELECT remix_code FROM recommended_scores"
        ).fetchall()
    owners = {row["remix_code"]: row["user_id"] for row in owner_rows}
    recommendations = {row["remix_code"] for row in recommendation_rows}
    items: list[dict[str, Any]] = []
    for path, score in read_scores():
        items.append({
            "id": score["remixCode"],
            "remixCode": score["remixCode"],
            "legacyId": legacy_admin_id(score),
            "title": score["title"],
            "artist": score["artist"],
            "sharedBy": score["sharedBy"],
            "sponsor": score.get("sponsor", ""),
            "key": score["key"],
            "meter": score["meter"],
            "bpm": score["bpm"],
            "displayUrl": score.get("displayUrl", ""),
            "declaration": score.get("declaration", ""),
            "source": score.get("source", "社区投稿"),
            "owner": owners.get(score["remixCode"], "—"),
            "recommended": score["remixCode"] in recommendations,
            "file": str(path.relative_to(REPOSITORY_ROOT)),
            "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        })
    return items


def admin_score_by_id(score_id: Any) -> tuple[Path, dict[str, Any]]:
    """Resolve a remix-code ID, retaining legacy 12-character compatibility."""
    return resolve_score_reference({"id": score_id})


def admin_sponsor_user_id(value: Any, existing_score: dict[str, Any]) -> str:
    """Resolve the selected sponsor account to its current public user ID."""
    if value is None:
        return str(existing_score.get("sponsor", "")).strip()
    account_id = str(value).strip()
    if not account_id:
        return ""
    with AUTH_LOCK, auth_database() as connection:
        row = connection.execute("SELECT user_id FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise ValueError("所选赞助人账号不存在。")
    return str(row["user_id"]).strip()


def admin_update_score(payload: Any) -> list[dict[str, Any]]:
    """Update admin-editable fields and optionally replace a score package.

    The existing sharedBy value is deliberately taken from the stored package.
    It is never accepted from the request or replacement file, so an admin
    cannot accidentally move a score's author/account binding.
    """
    if not isinstance(payload, dict):
        raise ValueError("曲目编辑请求格式无效。")
    existing_path, existing_score = admin_score_by_id(payload.get("remixCode") or payload.get("id"))
    replacement_bytes = payload.get("_fileBytes")
    replacement_name = str(payload.get("_fileName") or "").strip()
    replacement_score: dict[str, Any] | None = None
    if replacement_bytes is not None:
        if not isinstance(replacement_bytes, bytes) or not replacement_bytes:
            raise ValueError("替换文件为空。")
        if len(replacement_bytes) > MAX_REQUEST_BYTES:
            raise ValueError("替换文件不能超过 1 MB。")
        if replacement_name and not replacement_name.casefold().endswith(".deltamusic"):
            raise ValueError("只支持替换 .deltamusic 文件。")
        try:
            replacement_payload = json.loads(replacement_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("替换文件不是有效的 .deltamusic JSON 文件。") from error
        replacement_score = validate_package(replacement_payload)

    source_score = replacement_score or existing_score
    # These are the only editable fields. sharedBy intentionally comes from
    # the existing stored score even when a replacement file contains one.
    candidate_payload = {
        "format": FORMAT,
        "version": VERSION,
        "title": payload.get("title", source_score["title"]),
        "artist": payload.get("artist", source_score["artist"]),
        "sharedBy": existing_score["sharedBy"],
        "sponsor": admin_sponsor_user_id(payload.get("sponsorAccountId"), existing_score),
        "key": payload.get("key", source_score["key"]),
        "meter": payload.get("meter", source_score["meter"]),
        "bpm": payload.get("bpm", source_score["bpm"]),
        "jianpu": source_score["jianpu"],
        "displayUrl": payload.get("displayUrl", source_score.get("displayUrl")),
        "declaration": payload.get("declaration", source_score.get("declaration")),
        "createdAt": existing_score.get("createdAt"),
        "remixCode": existing_score.get("remixCode"),
        "legacyAdminIds": existing_score.get("legacyAdminIds") or [legacy_admin_id(existing_score)],
    }
    if existing_score.get("analyticsId"):
        candidate_payload["analyticsId"] = existing_score["analyticsId"]
    if existing_score.get("legacyAnalyticsIds"):
        candidate_payload["legacyAnalyticsIds"] = existing_score["legacyAnalyticsIds"]
    candidate = validate_package(candidate_payload)
    with LIBRARY_LOCK:
        destination = existing_path
        package = canonical_package({
            **candidate,
            # Legacy community scores may not have a createdAt field. Keep
            # their original timestamp when present, otherwise backfill it
            # while saving so admin edits never fail with KeyError.
            "createdAt": candidate.get("createdAt") or now_iso_timestamp(),
        })
        write_json_atomically(destination, package)
        rebuilt_scores = [item for _, item in read_scores()]
        write_library(LIBRARY_OUTPUT, rebuilt_scores)
        return rebuilt_scores


def admin_user_catalog() -> list[dict[str, Any]]:
    """Return privacy-safe account rows and lightweight activity counts."""
    now = now_timestamp()
    with AUTH_LOCK, auth_database() as connection:
        rows = connection.execute(
            "SELECT accounts.id, accounts.email, accounts.user_id, accounts.created_at, accounts.updated_at, "
            "MAX(COALESCE(donations.amount_cents, 0)) AS donation_cents, "
            "COUNT(DISTINCT score_owners.remix_code) AS uploads, "
            "COUNT(DISTINCT CASE WHEN sessions.expires_at > ? THEN sessions.token_hash END) AS active_sessions "
            "FROM accounts "
            "LEFT JOIN score_owners ON score_owners.account_id = accounts.id "
            "LEFT JOIN sessions ON sessions.account_id = accounts.id "
            "LEFT JOIN donations ON donations.account_id = accounts.id "
            "GROUP BY accounts.id ORDER BY accounts.created_at DESC",
            (now,),
        ).fetchall()
    return [{
        "id": row["id"],
        "userId": row["user_id"],
        "email": mask_email(str(row["email"])),
        "role": "管理员" if is_admin_account(row) else "用户",
        "donationCents": int(row["donation_cents"] or 0),
        "uploads": row["uploads"],
        "active": bool(row["active_sessions"]),
        "registeredAt": datetime.fromtimestamp(row["created_at"], timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "updatedAt": datetime.fromtimestamp(row["updated_at"], timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    } for row in rows]


def public_donor_list() -> list[dict[str, Any]]:
    """Return the supporter wall: user IDs only, never amounts or emails."""
    if not AUTH_DATABASE.exists():
        return []
    try:
        with AUTH_LOCK, auth_database() as connection:
            rows = connection.execute(
                "SELECT accounts.user_id AS user_id "
                "FROM donations JOIN accounts ON accounts.id = donations.account_id "
                "WHERE donations.amount_cents > 0 "
                "ORDER BY donations.created_at ASC, donations.updated_at ASC, accounts.user_id COLLATE NOCASE ASC",
            ).fetchall()
    except sqlite3.OperationalError:
        # 认证库存在但没有 donations 表（旧库尚未迁移）时，空名单好过整站报错。
        return []
    return [{"userId": str(row["user_id"])} for row in rows]


def build_public_donors() -> dict[str, Any]:
    """Serve the cached supporter wall so concurrent tabs share one query."""
    donors = PUBLIC_DONORS_CACHE.value("public-donors", PUBLIC_DONORS_CACHE_SECONDS, public_donor_list)
    return {"donors": donors, "total": len(donors)}


MAX_DONATION_CENTS = 10_000_000


def admin_set_donation(payload: Any) -> dict[str, Any]:
    """Record (or clear) one supporter's donation total. Admin console only."""
    if not isinstance(payload, dict):
        raise ValueError("请求内容无效。")
    account_id = str(payload.get("accountId") or "").strip()
    if not account_id:
        raise ValueError("缺少账号标识。")
    raw_amount = payload.get("amountCents")
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, float)):
        raise ValueError("打赏金额无效。")
    amount_cents = int(round(float(raw_amount)))
    if amount_cents < 0 or amount_cents > MAX_DONATION_CENTS:
        raise ValueError("打赏金额需要在 0 元到 10 万元之间。")
    with AUTH_LOCK, auth_database() as connection:
        if not connection.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone():
            raise ValueError("账号不存在。")
        if amount_cents == 0:
            connection.execute("DELETE FROM donations WHERE account_id = ?", (account_id,))
        else:
            now = now_timestamp()
            connection.execute(
                "INSERT INTO donations(account_id, amount_cents, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(account_id) DO UPDATE SET amount_cents=excluded.amount_cents, updated_at=excluded.updated_at",
                (account_id, amount_cents, now, now),
            )
    PUBLIC_DONORS_CACHE.invalidate()
    PUBLIC_RANKINGS_CACHE.invalidate()
    return {"accountId": account_id, "amountCents": amount_cents}


def account_effect_value(connection: sqlite3.Connection, account_id: str) -> str:
    """Return the stored ID effect, falling back to the default when unset."""
    row = connection.execute("SELECT effect FROM account_effects WHERE account_id = ?", (account_id,)).fetchone()
    effect = str(row["effect"]) if row else ""
    return effect if effect in USER_ID_EFFECTS else "default"


def account_contribution_exports(server: ThreadingHTTPServer, user_id: str) -> int:
    """Deduplicated exports of the songs this account published."""
    if not user_id or not (server.auth_enabled and server.analytics_enabled):
        return 0
    counts = cached_score_export_counts(server.analytics_retention_days)
    if not counts:
        return 0
    return sum(counts.get(score_id, 0) for owner, score_id in public_owned_scores(True) if owner == user_id)


def account_effect_state(server: ThreadingHTTPServer, account: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Describe which ID effects an account may show and which one is active."""
    account_id = str(account["id"])
    with AUTH_LOCK, auth_database() as connection:
        selected = account_effect_value(connection, account_id)
        donation = connection.execute("SELECT amount_cents FROM donations WHERE account_id = ?", (account_id,)).fetchone()
        announced = {str(row["effect"]) for row in connection.execute(
            "SELECT effect FROM effect_unlock_notices WHERE account_id = ?", (account_id,)
        ).fetchall()}
    supporter = bool(donation and int(donation["amount_cents"]) > 0)
    exports = account_contribution_exports(server, str(account["user_id"]))
    unlocked = ["default"]
    for effect, rule in USER_ID_EFFECT_UNLOCKS.items():
        if rule["kind"] == "contribution" and exports >= int(rule.get("min", 0)):
            unlocked.append(effect)
        elif rule["kind"] == "supporter" and supporter:
            unlocked.append(effect)
    return {
        # 解锁条件失效时（例如打赏被撤销）回落到默认，不回写数据库。
        "effect": selected if selected in unlocked else "default",
        "unlockedEffects": unlocked,
        "contributionExports": exports,
        "contributionThresholds": list(USER_ID_EFFECT_CONTRIBUTION_THRESHOLDS),
        "effectUnlocks": {effect: dict(rule) for effect, rule in USER_ID_EFFECT_UNLOCKS.items()},
        "supporter": supporter,
        "retentionDays": server.analytics_retention_days if server.analytics_enabled else 0,
        # 首次解锁的特效只会提醒一次；前端展示后回执给服务端记档。
        "pendingUnlocks": [effect for effect in unlocked if effect != "default" and effect not in announced],
    }


def public_user_effects(server: ThreadingHTTPServer) -> dict[str, str]:
    """Map user IDs to the flowing-light effect they currently show."""
    if not (AUTH_DATABASE.exists() and server.auth_enabled):
        return {}
    try:
        with AUTH_LOCK, auth_database() as connection:
            rows = connection.execute(
                "SELECT accounts.user_id AS user_id, account_effects.effect AS effect, "
                "COALESCE(donations.amount_cents, 0) AS amount_cents "
                "FROM account_effects JOIN accounts ON accounts.id = account_effects.account_id "
                "LEFT JOIN donations ON donations.account_id = accounts.id "
                "WHERE account_effects.effect != 'default'",
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    if not rows:
        return {}
    exports_by_score = cached_score_export_counts(server.analytics_retention_days) if server.analytics_enabled else {}
    owned_by_user: dict[str, list[str]] = {}
    for owner, score_id in public_owned_scores(True):
        owned_by_user.setdefault(owner, []).append(score_id)
    effects: dict[str, str] = {}
    for row in rows:
        effect = str(row["effect"])
        user_id = str(row["user_id"])
        rule = USER_ID_EFFECT_UNLOCKS.get(effect)
        if not rule:
            continue
        if rule["kind"] == "contribution":
            total = sum(exports_by_score.get(score_id, 0) for score_id in owned_by_user.get(user_id, []))
            if total >= int(rule.get("min", 0)):
                effects[user_id] = effect
        elif rule["kind"] == "supporter" and int(row["amount_cents"] or 0) > 0:
            effects[user_id] = effect
    return effects


def set_account_effect(server: ThreadingHTTPServer, account: sqlite3.Row | dict[str, Any], requested: Any) -> None:
    """Persist one account's ID effect after checking its unlock state."""
    effect = str(requested or "").strip()
    if effect not in USER_ID_EFFECTS:
        raise ValueError("未知的 ID 特效。")
    state = account_effect_state(server, account)
    if effect not in state["unlockedEffects"]:
        raise ValueError("该特效尚未解锁。")
    with AUTH_LOCK, auth_database() as connection:
        connection.execute(
            "INSERT INTO account_effects(account_id, effect, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(account_id) DO UPDATE SET effect=excluded.effect, updated_at=excluded.updated_at",
            (str(account["id"]), effect, now_timestamp()),
        )
    PUBLIC_RANKINGS_CACHE.invalidate()


def mark_effect_notices(server: ThreadingHTTPServer, account: sqlite3.Row | dict[str, Any], requested: Any) -> None:
    """Record that the unlock popup for these effects has been shown."""
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list):
        raise ValueError("请求格式无效。")
    effects = {str(item) for item in requested if str(item) in USER_ID_EFFECTS}
    unlocked = set(account_effect_state(server, account)["unlockedEffects"])
    effects &= unlocked - {"default"}
    if not effects:
        return
    now = now_timestamp()
    with AUTH_LOCK, auth_database() as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO effect_unlock_notices(account_id, effect, notified_at) VALUES (?, ?, ?)",
            [(str(account["id"]), effect, now) for effect in sorted(effects)],
        )


def admin_delete_score(payload: Any) -> list[dict[str, Any]]:
    """Delete one canonical community score and its admin metadata."""
    existing_path, existing_score = resolve_score_reference(payload)
    with LIBRARY_LOCK:
        existing_path.unlink()
        with AUTH_LOCK, auth_database() as connection:
            connection.execute("DELETE FROM score_owners WHERE remix_code = ?", (existing_score["remixCode"],))
            connection.execute("DELETE FROM recommended_scores WHERE remix_code = ?", (existing_score["remixCode"],))
        songs = [item for _, item in read_scores()]
        write_library(LIBRARY_OUTPUT, songs)
        return songs


def add_recommendation(payload: Any) -> list[dict[str, str]]:
    identity = recommendation_identity(payload)
    with AUTH_LOCK, auth_database() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO recommended_scores(remix_code, title, artist, shared_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (identity["remixCode"], identity["title"], identity["artist"], identity["sharedBy"], now_timestamp()),
        )
    return list_recommendations()


def remove_recommendation(payload: Any) -> list[dict[str, str]]:
    identity = recommendation_identity(payload)
    with AUTH_LOCK, auth_database() as connection:
        result = connection.execute(
            "DELETE FROM recommended_scores WHERE remix_code = ?",
            (identity["remixCode"],),
        )
        if result.rowcount < 1:
            raise FileNotFoundError("推荐曲目不存在。")
    return list_recommendations()


def auth_digest(server: ThreadingHTTPServer, value: str) -> str:
    return hmac.new(server.auth_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def analytics_actor_key(server: ThreadingHTTPServer, account_id: str) -> str:
    """Return an opaque, stable identity for authenticated export deduplication."""
    return auth_digest(server, f"analytics:{account_id}")


def oauth_provider_label(provider: str) -> str:
    return OAUTH_PROVIDER_LABELS.get(provider, provider)


def oauth_config(server: ThreadingHTTPServer, provider: str) -> dict[str, str] | None:
    return server.oauth_providers.get(provider)


def issue_oauth_state(server: ThreadingHTTPServer, provider: str) -> str:
    state = secrets.token_urlsafe(32)
    now = now_timestamp()
    with server.oauth_state_lock:
        server.oauth_states = {
            key: value for key, value in server.oauth_states.items()
            if value["expires_at"] > now
        }
        server.oauth_states[state] = {"provider": provider, "expires_at": now + OAUTH_STATE_TTL_SECONDS}
    return state


def consume_oauth_state(server: ThreadingHTTPServer, state: str, provider: str) -> bool:
    now = now_timestamp()
    with server.oauth_state_lock:
        record = server.oauth_states.pop(state, None)
    return bool(record and record["provider"] == provider and record["expires_at"] > now)


def oauth_state_cookie(handler: "LocalLibraryRequestHandler", state: str | None = None, *, expired: bool = False) -> str:
    value = state or ""
    parts = [f"{OAUTH_STATE_COOKIE_NAME}={value}", "Path=/", "HttpOnly", "SameSite=Lax"]
    parts.append("Max-Age=0" if expired else f"Max-Age={OAUTH_STATE_TTL_SECONDS}")
    if not handler.server.insecure_auth_cookies:
        parts.append("Secure")
    return "; ".join(parts)


def oauth_callback_target(server: ThreadingHTTPServer, provider: str, result: str, message: str = "") -> str:
    config = oauth_config(server, provider)
    if not config:
        return "/"
    callback_path = f"/api/auth/oauth/{provider}/callback"
    parsed = urlsplit(config["redirect_uri"])
    app_path = parsed.path.rsplit(callback_path, 1)[0].rstrip("/") or "/"
    if app_path != "/":
        app_path += "/"
    query = {"auth": result}
    if message:
        query["message"] = message[:120]
    return urlunsplit((parsed.scheme, parsed.netloc, app_path, "", urlencode(query), ""))


def fetch_oauth_response(url: str, *, data: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> str:
    encoded = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, data=encoded, headers=headers or {"Accept": "application/json"}, method="POST" if encoded else "GET")
    try:
        with urlopen(request, timeout=OAUTH_HTTP_TIMEOUT_SECONDS) as response:
            return response.read(MAX_REQUEST_BYTES).decode("utf-8")
    except (HTTPError, URLError, OSError) as error:
        raise ValueError("第三方登录服务暂时不可用，请稍后重试。") from error


def parse_qq_jsonp(value: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        raise ValueError("QQ 登录返回数据无效。")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise ValueError("QQ 登录返回数据无效。") from error
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError("QQ 登录授权失败，请重试。")
    return payload


def oauth_profile(server: ThreadingHTTPServer, provider: str, code: str) -> dict[str, str]:
    config = oauth_config(server, provider)
    if not config:
        raise ValueError(f"{oauth_provider_label(provider)}登录尚未配置。")
    if provider == "qq":
        token_text = fetch_oauth_response("https://graph.qq.com/oauth2.0/token?" + urlencode({
                "grant_type": "authorization_code",
                "client_id": config["app_id"],
                "client_secret": config["app_secret"],
                "code": code,
                "redirect_uri": config["redirect_uri"],
            }), headers={"Accept": "text/plain"})
        token = parse_qs(token_text, keep_blank_values=True).get("access_token", [""])[0]
        if not token:
            raise ValueError("QQ 登录授权失败，请重试。")
        openid_payload = parse_qq_jsonp(fetch_oauth_response(f"https://graph.qq.com/oauth2.0/me?access_token={quote(token)}"))
        subject = str(openid_payload.get("openid", "")).strip()
        if not subject:
            raise ValueError("QQ 登录未返回有效用户标识。")
        user_info_text = fetch_oauth_response(
            "https://graph.qq.com/user/get_user_info?" + urlencode({
                "access_token": token,
                "oauth_consumer_key": config["app_id"],
                "openid": subject,
            })
        )
        user_info = json.loads(user_info_text)
        if not isinstance(user_info, dict) or user_info.get("ret", 0) != 0:
            raise ValueError("QQ 用户信息获取失败，请重试。")
        return {"subject": f"qq:{subject}", "display_name": str(user_info.get("nickname", "")).strip()}

    token_payload = json.loads(fetch_oauth_response("https://api.weixin.qq.com/sns/oauth2/access_token?" + urlencode({
            "appid": config["app_id"],
            "secret": config["app_secret"],
            "code": code,
            "grant_type": "authorization_code",
        })))
    if not isinstance(token_payload, dict) or token_payload.get("errcode") or not token_payload.get("access_token"):
        raise ValueError("微信登录授权失败，请重试。")
    openid = str(token_payload.get("openid", "")).strip()
    unionid = str(token_payload.get("unionid", "")).strip()
    subject = unionid or openid
    if not subject:
        raise ValueError("微信登录未返回有效用户标识。")
    user_info = json.loads(fetch_oauth_response(
        "https://api.weixin.qq.com/sns/userinfo?" + urlencode({
            "access_token": token_payload["access_token"],
            "openid": openid,
            "lang": "zh_CN",
        })
    ))
    if not isinstance(user_info, dict) or user_info.get("errcode"):
        raise ValueError("微信用户信息获取失败，请重试。")
    return {"subject": f"wechat:{subject}", "display_name": str(user_info.get("nickname", "")).strip()}


def oauth_account(server: ThreadingHTTPServer, provider: str, profile: dict[str, str]) -> sqlite3.Row:
    subject = profile["subject"]
    display_name = re.sub(r"[^A-Za-z0-9_]+", "_", profile.get("display_name", "")).strip("_")[:12]
    prefix = "qq" if provider == "qq" else "wx"
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:10]
    with AUTH_LOCK, auth_database() as connection:
        identity = connection.execute(
            "SELECT account_id FROM oauth_identities WHERE provider = ? AND subject = ?",
            (provider, subject),
        ).fetchone()
        if identity:
            account = connection.execute("SELECT id, email, user_id FROM accounts WHERE id = ?", (identity["account_id"],)).fetchone()
            if account:
                return account
        base = f"{prefix}_{display_name}" if display_name else f"{prefix}_{digest}"
        base = base[:24]
        user_id = base
        suffix = 1
        while connection.execute("SELECT 1 FROM user_id_history WHERE user_id = ? COLLATE NOCASE", (user_id,)).fetchone():
            tail = f"_{suffix}"
            user_id = f"{base[:24 - len(tail)]}{tail}"
            suffix += 1
        account_id = str(uuid.uuid4())
        synthetic_email = f"{prefix}_{digest}_{secrets.token_hex(4)}@oauth.invalid"
        now = now_timestamp()
        connection.execute(
            "INSERT INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (account_id, synthetic_email, user_id, now, now),
        )
        connection.execute(
            "INSERT INTO user_id_history(user_id, account_id, reserved_at) VALUES (?, ?, ?)",
            (user_id, account_id, now),
        )
        connection.execute(
            "INSERT INTO oauth_identities(provider, subject, account_id, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (provider, subject, account_id, profile.get("display_name", "")[:120], now),
        )
        return connection.execute("SELECT id, email, user_id FROM accounts WHERE id = ?", (account_id,)).fetchone()


def send_auth_email(server: ThreadingHTTPServer, message: EmailMessage) -> None:
    """Send one verification email without holding an HTTP request thread."""
    if server.smtp_ssl:
        with smtplib.SMTP_SSL(
            server.smtp_host,
            server.smtp_port,
            context=ssl.create_default_context(),
            timeout=AUTH_SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            if server.smtp_username:
                smtp.login(server.smtp_username, server.smtp_password)
            smtp.send_message(message)
        return
    with smtplib.SMTP(server.smtp_host, server.smtp_port, timeout=AUTH_SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.ehlo()
        if server.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if server.smtp_username:
            smtp.login(server.smtp_username, server.smtp_password)
        smtp.send_message(message)


class AuthMailDispatcher:
    """Bound SMTP worker pool so slow mail providers cannot exhaust HTTP threads."""

    def __init__(self, server: ThreadingHTTPServer) -> None:
        self.server = server
        self.jobs: queue.Queue[tuple[str, str, str, EmailMessage]] = queue.Queue(maxsize=AUTH_MAIL_QUEUE_MAXSIZE)
        self.stop_event = threading.Event()
        self.ticket_lock = threading.Lock()
        self.tickets: dict[str, dict[str, Any]] = {}
        self.sequence = 0
        self.workers = [
            threading.Thread(target=self._run, name=f"auth-mail-{index}", daemon=True)
            for index in range(1, AUTH_MAIL_WORKERS + 1)
        ]
        for worker in self.workers:
            worker.start()

    def submit(self, email: str, code_hash: str, message: EmailMessage) -> str:
        """Queue one verification email and return the ticket used to track it."""
        ticket = secrets.token_urlsafe(18)
        now = time.monotonic()
        with self.ticket_lock:
            self._purge_tickets_locked(now)
            self.sequence += 1
            self.tickets[ticket] = {"sequence": self.sequence, "state": "pending", "updated_at": now}
        try:
            self.jobs.put_nowait((ticket, email, code_hash, message))
        except queue.Full as error:
            with self.ticket_lock:
                self.tickets.pop(ticket, None)
            raise ValueError("验证码邮件服务繁忙，请稍后重试。") from error
        return ticket

    def _purge_tickets_locked(self, now: float) -> None:
        expired = [
            ticket for ticket, record in self.tickets.items()
            if now - record["updated_at"] > AUTH_MAIL_TICKET_TTL_SECONDS
        ]
        for ticket in expired:
            self.tickets.pop(ticket, None)
        overflow = len(self.tickets) - AUTH_MAIL_TICKET_LIMIT
        if overflow > 0:
            oldest = sorted(self.tickets, key=lambda item: self.tickets[item]["sequence"])[:overflow]
            for ticket in oldest:
                self.tickets.pop(ticket, None)

    def _set_state(self, ticket: str, state: str) -> None:
        with self.ticket_lock:
            record = self.tickets.get(ticket)
            if record is not None:
                record["state"] = state
                record["updated_at"] = time.monotonic()

    def status(self, ticket: str) -> dict[str, Any] | None:
        """Report one ticket's delivery state from memory only; never touches SQLite."""
        now = time.monotonic()
        with self.ticket_lock:
            self._purge_tickets_locked(now)
            record = self.tickets.get(ticket)
            if record is None:
                return None
            pending = [item for item in self.tickets.values() if item["state"] == "pending"]
            position = 0
            if record["state"] == "pending":
                position = 1 + sum(1 for item in pending if item["sequence"] < record["sequence"])
            return {"state": record["state"], "position": position, "queueDepth": len(pending)}

    def snapshot(self) -> dict[str, Any]:
        """Summarise queue, worker and ticket state for the admin runtime panel."""
        now = time.monotonic()
        with self.ticket_lock:
            self._purge_tickets_locked(now)
            states: Counter[str] = Counter(record["state"] for record in self.tickets.values())
            oldest_pending: float | None = None
            for record in self.tickets.values():
                if record["state"] != "pending":
                    continue
                age = now - record["updated_at"]
                oldest_pending = age if oldest_pending is None else max(oldest_pending, age)
        alive_workers = sum(1 for worker in self.workers if worker.is_alive())
        return {
            "enabled": True,
            "queueDepth": self.jobs.qsize(),
            "queueCapacity": AUTH_MAIL_QUEUE_MAXSIZE,
            "workers": {"total": len(self.workers), "alive": alive_workers, "expected": AUTH_MAIL_WORKERS},
            "tickets": {
                "pending": states["pending"],
                "sending": states["sending"],
                "sent": states["sent"],
                "failed": states["failed"],
                "tracked": len(self.tickets),
                "limit": AUTH_MAIL_TICKET_LIMIT,
            },
            "oldestPendingSeconds": round(oldest_pending, 1) if oldest_pending is not None else None,
            "stopping": self.stop_event.is_set(),
        }

    def _discard_code_if_current(self, email: str, code_hash: str) -> None:
        try:
            with AUTH_LOCK, auth_database() as connection:
                connection.execute(
                    "DELETE FROM email_codes WHERE email = ? AND code_hash = ?",
                    (email, code_hash),
                )
        except sqlite3.Error as error:
            print(f"验证码邮件失败后清理验证码记录失败：{error}", file=sys.stderr, flush=True)

    def _run(self) -> None:
        while not self.stop_event.is_set() or not self.jobs.empty():
            try:
                ticket, email, code_hash, message = self.jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            self._set_state(ticket, "sending")
            try:
                send_auth_email(self.server, message)
            except (OSError, smtplib.SMTPException) as error:
                self._discard_code_if_current(email, code_hash)
                self._set_state(ticket, "failed")
                print(f"验证码邮件发送失败（{email}）：{error}", file=sys.stderr, flush=True)
            else:
                self._set_state(ticket, "sent")
            finally:
                self.jobs.task_done()

    def close(self, timeout: float = 1.0) -> None:
        self.stop_event.set()
        for worker in self.workers:
            worker.join(timeout=timeout)


def request_auth_code(server: ThreadingHTTPServer, email: str, client: str) -> str | None:
    """Store a fresh verification code and queue its email; returns the mail ticket."""
    now = now_timestamp()
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = auth_digest(server, code)
    with AUTH_LOCK, auth_database() as connection:
        connection.execute("DELETE FROM email_codes WHERE expires_at <= ?", (now,))
        connection.execute(
            "INSERT INTO email_codes(email, code_hash, expires_at, attempts) VALUES (?, ?, ?, 0) "
            "ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash, expires_at=excluded.expires_at, attempts=0",
            (email, code_hash, now + AUTH_CODE_TTL_SECONDS),
        )
    if server.auth_code_log_only:
        print(f"[AUTH TEST ONLY] Verification code for {email}: {code}", flush=True)
        return None
    message = EmailMessage()
    message["Subject"] = "三角洲口琴演奏家登录验证码"
    message["From"] = server.smtp_from
    message["To"] = email
    message.set_content(f"你的登录验证码是：{code}\n\n验证码将在 10 分钟后失效。若不是你本人操作，请忽略此邮件。")
    try:
        return server.auth_mail_dispatcher.submit(email, code_hash, message)
    except ValueError:
        with AUTH_LOCK, auth_database() as connection:
            connection.execute(
                "DELETE FROM email_codes WHERE email = ? AND code_hash = ?",
                (email, code_hash),
            )
        raise


def auth_mail_status_payload(server: ThreadingHTTPServer, ticket: str | None) -> dict[str, Any]:
    """Describe one mail ticket for the frontend; reads memory only, never SQLite."""
    dispatcher = server.auth_mail_dispatcher
    if dispatcher is None:
        # --auth-code-log-only 测试模式不投递邮件，直接按已送达展示。
        return {"ticket": None, "state": "sent", "position": 0, "queueDepth": 0}
    status = dispatcher.status(ticket) if ticket else None
    if status is None:
        return {"ticket": None, "state": "expired", "position": 0, "queueDepth": 0}
    return {"ticket": ticket, **status}


def auth_rate_allowed(server: ThreadingHTTPServer, key: str, limit: int) -> bool:
    now = time.monotonic()
    with server.auth_rate_limit_lock:
        entries = [stamp for stamp in server.auth_code_requests.get(key, []) if now - stamp < AUTH_CODE_RATE_WINDOW_SECONDS]
        if len(entries) >= limit:
            server.auth_code_requests[key] = entries
            return False
        entries.append(now)
        server.auth_code_requests[key] = entries
        return True


def authenticate_request(handler: "LocalLibraryRequestHandler") -> sqlite3.Row | None:
    token = handler.cookies().get(AUTH_COOKIE_NAME)
    if not token:
        return None
    token_hash = auth_digest(handler.server, token.value)
    now = now_timestamp()
    with AUTH_LOCK, auth_database() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        return connection.execute(
            "SELECT accounts.id, accounts.email, accounts.user_id FROM sessions "
            "JOIN accounts ON accounts.id = sessions.account_id WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
            (token_hash, now),
        ).fetchone()


def issue_session(server: ThreadingHTTPServer, account_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with AUTH_LOCK, auth_database() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_timestamp(),))
        connection.execute(
            "INSERT INTO sessions(token_hash, account_id, expires_at) VALUES (?, ?, ?)",
            (auth_digest(server, token), account_id, now_timestamp() + AUTH_SESSION_TTL_SECONDS),
        )
    return token


def consume_verification_code(server: ThreadingHTTPServer, email: str, code: Any, requested_user_id: Any, mode: Any = None) -> sqlite3.Row:
    value = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", value):
        raise ValueError("请输入 6 位验证码。")
    now = now_timestamp()
    with AUTH_LOCK, auth_database() as connection:
        record = connection.execute("SELECT code_hash, expires_at, attempts FROM email_codes WHERE email = ?", (email,)).fetchone()
        if not record or record["expires_at"] <= now:
            connection.execute("DELETE FROM email_codes WHERE email = ?", (email,))
            raise ValueError("验证码已失效，请重新获取。")
        if record["attempts"] >= AUTH_CODE_MAX_ATTEMPTS or not hmac.compare_digest(record["code_hash"], auth_digest(server, value)):
            connection.execute("UPDATE email_codes SET attempts = attempts + 1 WHERE email = ?", (email,))
            raise ValueError("验证码不正确，请重试。")
        account = connection.execute("SELECT id, email, user_id FROM accounts WHERE email = ?", (email,)).fetchone()
        if account is None:
            if mode == "login":
                raise ValueError("该邮箱尚未注册，请切换到注册。")
            user_id = validate_user_id(requested_user_id)
            account_id = str(uuid.uuid4())
            try:
                connection.execute(
                    "INSERT INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (account_id, email, user_id, now, now),
                )
                connection.execute("INSERT INTO user_id_history(user_id, account_id, reserved_at) VALUES (?, ?, ?)", (user_id, account_id, now))
            except sqlite3.IntegrityError as error:
                raise ValueError("该用户 ID 已被使用或保留。") from error
            account = connection.execute("SELECT id, email, user_id FROM accounts WHERE id = ?", (account_id,)).fetchone()
        elif mode == "register":
            raise ValueError("该邮箱已注册，请切换到登录。")
        connection.execute("DELETE FROM email_codes WHERE email = ?", (email,))
    backfill_legacy_score_owners(account)
    return account


def bind_score_owner(account_id: str, path: Path) -> None:
    relative = str(path.relative_to(REPOSITORY_ROOT))
    score = next((score for score_path, score in read_scores() if score_path == path), None)
    if not score:
        raise FileNotFoundError("未找到待绑定的曲目。")
    with AUTH_LOCK, auth_database() as connection:
        connection.execute(
            "INSERT INTO score_owners(remix_code, score_path, account_id) VALUES (?, ?, ?) "
            "ON CONFLICT(remix_code) DO UPDATE SET score_path = excluded.score_path, account_id = excluded.account_id",
            (score["remixCode"], relative, account_id),
        )


def backfill_legacy_score_owners(account: sqlite3.Row | None) -> None:
    """Attach legacy Jiko community submissions to the verified owner account."""
    if not account or str(account["email"]).casefold() != LEGACY_OWNER_EMAIL:
        return
    legacy_scores = []
    for path, score in read_scores():
        if not is_canonical_source(path):
            continue
        if str(score.get("sharedBy", "")).strip().casefold() == LEGACY_OWNER_USER_ID:
            legacy_scores.append((score["remixCode"], str(path.relative_to(REPOSITORY_ROOT))))
    if not legacy_scores:
        return
    with AUTH_LOCK, auth_database() as connection:
        connection.executemany(
            "INSERT INTO score_owners(remix_code, score_path, account_id) VALUES (?, ?, ?) "
            "ON CONFLICT(remix_code) DO UPDATE SET score_path = excluded.score_path, account_id = excluded.account_id",
            [(code, path, account["id"]) for code, path in legacy_scores],
        )


def backfill_legacy_score_owners_for_known_account() -> None:
    with AUTH_LOCK, auth_database() as connection:
        account = connection.execute("SELECT id, email, user_id FROM accounts WHERE email = ?", (LEGACY_OWNER_EMAIL,)).fetchone()
    backfill_legacy_score_owners(account)


def scores_owned_by(account_id: str) -> list[dict[str, Any]]:
    # Existing sessions may survive a deployment, so do not rely only on
    # startup or the verification-code flow to attach legacy Jiko submissions.
    # The migration is idempotent and safe to repeat whenever the library is read.
    with AUTH_LOCK, auth_database() as connection:
        account = connection.execute(
            "SELECT id, email, user_id FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    backfill_legacy_score_owners(account)
    with AUTH_LOCK, auth_database() as connection:
        owned_codes = {row["remix_code"] for row in connection.execute("SELECT remix_code FROM score_owners WHERE account_id = ?", (account_id,)).fetchall()}
    if not owned_codes:
        return []
    return [score for path, score in read_scores() if score["remixCode"] in owned_codes]


def delete_owned_score(account_id: str, payload: Any) -> list[dict[str, Any]]:
    with LIBRARY_LOCK:
        path, score = resolve_score_reference(payload)
        if score_owner_account_id(path, score) != account_id:
            raise PermissionError("只能删除自己上传的曲目。")
        path.unlink()
        with AUTH_LOCK, auth_database() as connection:
            connection.execute("DELETE FROM score_owners WHERE remix_code = ?", (score["remixCode"],))
            connection.execute("DELETE FROM recommended_scores WHERE remix_code = ?", (score["remixCode"],))
        songs = [item for _, item in read_scores()]
        write_library(LIBRARY_OUTPUT, songs)
        return songs


def rename_account_user_id(account: sqlite3.Row, user_id: Any) -> list[dict[str, Any]]:
    new_user_id = validate_user_id(user_id)
    if new_user_id.casefold() == account["user_id"].casefold():
        return [item for _, item in read_scores()]
    with LIBRARY_LOCK, AUTH_LOCK, auth_database() as connection:
        reserved = connection.execute("SELECT account_id FROM user_id_history WHERE user_id = ?", (new_user_id,)).fetchone()
        if reserved:
            raise ValueError("该用户 ID 已被使用或保留。")
        rows = connection.execute("SELECT remix_code, score_path FROM score_owners WHERE account_id = ?", (account["id"],)).fetchall()
        for row in rows:
            path = (REPOSITORY_ROOT / row["score_path"]).resolve()
            if not is_canonical_source(path) or not path.exists():
                continue
            package = json.loads(path.read_text(encoding="utf-8"))
            package["sharedBy"] = new_user_id
            package["remixCode"] = row["remix_code"]
            write_json_atomically(path, package)
        now = now_timestamp()
        connection.execute("UPDATE accounts SET user_id = ?, updated_at = ? WHERE id = ?", (new_user_id, now, account["id"]))
        connection.execute("INSERT INTO user_id_history(user_id, account_id, reserved_at) VALUES (?, ?, ?)", (new_user_id, account["id"], now))
        songs = [item for _, item in read_scores()]
        write_library(LIBRARY_OUTPUT, songs)
        return songs


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Keep slow or abandoned clients from creating unbounded request threads."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.request_slots = threading.BoundedSemaphore(MAX_REQUEST_THREADS)
        self.started_at = time.time()
        self.request_stats_lock = threading.Lock()
        self.active_requests = 0
        self.total_requests = 0

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.request_slots.acquire(timeout=1):
            self.shutdown_request(request)
            return
        with self.request_stats_lock:
            self.active_requests += 1
            self.total_requests += 1

        def run_request() -> None:
            try:
                self.process_request_thread(request, client_address)
            finally:
                with self.request_stats_lock:
                    self.active_requests -= 1
                self.request_slots.release()

        thread = threading.Thread(target=run_request, daemon=True)
        thread.start()


def read_system_memory() -> dict[str, float] | None:
    """Read system memory from /proc/meminfo; returns None when unavailable."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            entries: dict[str, float] = {}
            for line in handle:
                key, separator, rest = line.partition(":")
                if not separator:
                    continue
                fields = rest.strip().split()
                if fields:
                    entries[key.strip()] = float(fields[0]) / 1024  # kB → MB
    except (OSError, ValueError):
        return None
    total = entries.get("MemTotal")
    if not total:
        return None
    available = entries.get("MemAvailable")
    if available is None:
        available = entries.get("MemFree", 0.0) + entries.get("Cached", 0.0)
    used = max(0.0, total - available)
    return {
        "totalMb": round(total, 1),
        "availableMb": round(available, 1),
        "usedMb": round(used, 1),
        "usedPercent": round(used / total * 100, 1) if total else 0.0,
    }


def read_process_memory() -> float | None:
    """Read this process' resident set size in MB from /proc/self/status."""
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(float(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None
    return None


def thread_group_name(name: str) -> str:
    """Collapse numbered worker threads such as auth-mail-2 into one group."""
    return re.sub(r"[- ]\d+$", "", name) or name


def build_runtime_report(server: ThreadingHTTPServer) -> dict[str, Any]:
    """Collect process, request, mail queue and thread state for the admin panel."""
    now = time.time()
    started_at = getattr(server, "started_at", now)
    load_average: list[float] | None = None
    if hasattr(os, "getloadavg"):
        try:
            load_average = [round(value, 2) for value in os.getloadavg()]
        except OSError:
            load_average = None

    try:
        usage = shutil.disk_usage(str(REPOSITORY_ROOT))
        disk: dict[str, float] | None = {
            "totalGb": round(usage.total / 1024**3, 1),
            "usedGb": round(usage.used / 1024**3, 1),
            "freeGb": round(usage.free / 1024**3, 1),
            "usedPercent": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
        }
    except OSError:
        disk = None

    uname = os.uname() if hasattr(os, "uname") else None
    threads = threading.enumerate()
    groups = Counter(thread_group_name(thread.name) for thread in threads)

    with server.request_stats_lock:
        active_requests = server.active_requests
        total_requests = server.total_requests

    dispatcher = getattr(server, "auth_mail_dispatcher", None)
    if dispatcher is not None:
        mail = dispatcher.snapshot()
    else:
        mail = {
            "enabled": False,
            "queueDepth": 0,
            "queueCapacity": AUTH_MAIL_QUEUE_MAXSIZE,
            "workers": {"total": 0, "alive": 0, "expected": AUTH_MAIL_WORKERS},
            "tickets": {"pending": 0, "sending": 0, "sent": 0, "failed": 0, "tracked": 0, "limit": AUTH_MAIL_TICKET_LIMIT},
            "oldestPendingSeconds": None,
            "stopping": False,
        }

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "server": {
            "pid": os.getpid(),
            "python": sys.version.split()[0],
            "platform": f"{uname.sysname} {uname.release}" if uname else sys.platform,
            "startedAt": datetime.fromtimestamp(started_at, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "uptimeSeconds": int(max(0.0, now - started_at)),
            "loadAverage": load_average,
            "cpuCount": os.cpu_count() or 0,
            "memory": read_system_memory(),
            "processMemoryMb": read_process_memory(),
            "disk": disk,
        },
        "requests": {
            "active": active_requests,
            "total": total_requests,
            "limit": MAX_REQUEST_THREADS,
            "queueSize": server.request_queue_size,
        },
        "mail": mail,
        "threads": {
            "total": len(threads),
            "daemon": sum(1 for thread in threads if thread.daemon),
            "groups": [{"name": name, "count": count} for name, count in groups.most_common()],
            "list": [
                {"name": thread.name, "daemon": thread.daemon, "alive": thread.is_alive()}
                for thread in threads[:40]
            ],
        },
    }


COMPRESSED_ASSET_LOCK = threading.Lock()
COMPRESSED_ASSET_CACHE: dict[str, tuple[tuple[int, int], bytes]] = {}
COMPRESSED_ASSET_BYTES = 0


def compressed_static_body(path: str) -> bytes | None:
    """Return a gzip copy of a static file, recompressing only when the file changes.

    Compressing per request would trade bandwidth for CPU on a server that is
    already CPU-bound, so results are cached by (mtime, size) and evicted once
    the cache exceeds its byte budget.
    """
    global COMPRESSED_ASSET_BYTES
    try:
        stat = os.stat(path)
    except OSError:
        return None
    stamp = (stat.st_mtime_ns, stat.st_size)
    with COMPRESSED_ASSET_LOCK:
        cached = COMPRESSED_ASSET_CACHE.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    if len(raw) < GZIP_MIN_BYTES:
        return None
    body = gzip.compress(raw, GZIP_LEVEL)
    with COMPRESSED_ASSET_LOCK:
        previous = COMPRESSED_ASSET_CACHE.get(path)
        if previous is not None:
            COMPRESSED_ASSET_BYTES -= len(previous[1])
        COMPRESSED_ASSET_CACHE[path] = (stamp, body)
        COMPRESSED_ASSET_BYTES += len(body)
        while COMPRESSED_ASSET_BYTES > COMPRESSED_ASSET_CACHE_MAX_BYTES:
            oldest = next((key for key in COMPRESSED_ASSET_CACHE if key != path), None)
            if oldest is None:
                break
            COMPRESSED_ASSET_BYTES -= len(COMPRESSED_ASSET_CACHE.pop(oldest)[1])
    return body


class LocalLibraryRequestHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    response_status = 200

    def setup(self) -> None:  # noqa: D401
        super().setup()
        self.connection.settimeout(REQUEST_SOCKET_TIMEOUT_SECONDS)

    def send_response(self, code: int, message: str | None = None) -> None:  # noqa: N802
        self.response_status = code
        super().send_response(code, message)

    def accepts_gzip(self) -> bool:
        """Honor Accept-Encoding, including an explicit ``gzip;q=0`` refusal."""
        header = self.headers.get("Accept-Encoding", "")
        for entry in header.split(","):
            encoding, _, parameters = entry.strip().partition(";")
            if encoding.strip().lower() not in {"gzip", "x-gzip"}:
                continue
            quality = parameters.strip().lower()
            if quality.startswith("q="):
                try:
                    if float(quality[2:]) <= 0:
                        continue
                except ValueError:
                    pass
            return True
        return False

    def static_cache_control(self, path: str) -> str:
        """Versioned asset URLs can be cached for a year; data files keep revalidating."""
        lowered = path.lower()
        if lowered.endswith(".zip"):
            return "public, max-age=31536000, immutable"
        if parse_qs(urlparse(self.path).query).get("v") and not lowered.startswith("/data/"):
            # 本地预览（未开启 --public）即使带版本标记也重新验证，
            # 否则改完 app.js / styles.css 普通刷新看不到效果。
            if not self.server.public_library:
                return "no-cache, must-revalidate"
            return "public, max-age=31536000, immutable"
        if path == "/" or lowered.endswith(".html"):
            return "no-cache, no-store, must-revalidate"
        return "no-cache, must-revalidate"

    def end_headers(self) -> None:  # noqa: N802
        """Make ordinary reloads see newly deployed static files.

        The app is deliberately served without content-hashed filenames, so
        static responses must be revalidated unless the URL carries a ``?v=``
        release token. API responses already set their own ``Cache-Control``
        header and are left unchanged here.
        """
        has_cache_control = any(
            header.lower().startswith(b"cache-control:")
            for header in self._headers_buffer
        )
        if not has_cache_control:
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                cache_control = "no-store"
            elif self.response_status not in (200, 304):
                cache_control = "no-cache, no-store, must-revalidate"
            else:
                cache_control = self.static_cache_control(path)
            self.send_header("Cache-Control", cache_control)
        has_connection_header = any(
            header.lower().startswith(b"connection:")
            for header in self._headers_buffer
        )
        if not has_connection_header:
            self.send_header("Connection", "close")
        self.close_connection = True
        super().end_headers()

    def not_modified_since(self, header: str, mtime: float) -> bool:
        """Mirror the stdlib If-Modified-Since check for responses we build ourselves."""
        try:
            modified_since = parsedate_to_datetime(header)
        except (TypeError, IndexError, OverflowError, ValueError):
            return False
        if modified_since.tzinfo is None:
            modified_since = modified_since.replace(tzinfo=timezone.utc)
        if modified_since.tzinfo is not timezone.utc:
            return False
        last_modified = datetime.fromtimestamp(mtime, timezone.utc).replace(microsecond=0)
        return last_modified <= modified_since

    def send_compressed_static(self, path: str, content_type: str) -> bool:
        """Write a gzipped static file; returns False so the caller can fall back."""
        try:
            stat = os.stat(path)
        except OSError:
            return False
        if stat.st_size < GZIP_MIN_BYTES:
            return False
        conditional = self.headers.get("If-Modified-Since")
        if conditional and "If-None-Match" not in self.headers and self.not_modified_since(conditional, stat.st_mtime):
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.end_headers()
            return True
        body = compressed_static_body(path)
        if body is None:
            return False
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return True

    def send_head(self) -> Any:  # noqa: N802
        """Compress text assets for clients that accept gzip; otherwise use the stdlib path."""
        if not self.accepts_gzip():
            return super().send_head()
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not urlparse(self.path).path.endswith("/"):
                return super().send_head()
            for index in ("index.html", "index.htm"):
                candidate = os.path.join(path, index)
                if os.path.isfile(candidate):
                    path = candidate
                    break
            else:
                return super().send_head()
        content_type = self.guess_type(path)
        if not content_type.startswith(COMPRESSIBLE_CONTENT_TYPES):
            return super().send_head()
        if self.send_compressed_static(path, content_type):
            return None
        return super().send_head()

    def encode_response_body(self, body: bytes) -> tuple[bytes, bool]:
        """Gzip a response body when the client accepts it and the payload is worth it."""
        if len(body) < GZIP_MIN_BYTES or not self.accepts_gzip():
            return body, False
        return gzip.compress(body, GZIP_LEVEL), True

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        body, compressed = self.encode_response_body(encoded)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_download(self, body: bytes, filename: str, content_type: str) -> None:
        """Send a private binary download without compression or caching."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json_with_cookie(self, status: HTTPStatus, payload: dict[str, Any], cookie: str | None = None) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        body, compressed = self.encode_response_body(encoded)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_empty(self, status: HTTPStatus, cookie: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def serve_maintenance_if_active(self, path: str) -> bool:
        """Show a retrying maintenance page while the production container swaps."""
        if path == "/api/public-library/status" or not MAINTENANCE_MARKER.exists():
            return False
        try:
            encoded = MAINTENANCE_PAGE.read_bytes()
        except OSError:
            encoded = "<meta charset='utf-8'><title>正在更新</title><h1>正在更新，请稍候</h1>".encode("utf-8")
        self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(encoded)
        return True

    def send_redirect(self, location: str, cookie: str | list[str] | None = None) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        if isinstance(cookie, list):
            for value in cookie:
                self.send_header("Set-Cookie", value)
        elif cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def cookies(self) -> SimpleCookie:
        parsed = SimpleCookie()
        parsed.load(self.headers.get("Cookie", ""))
        return parsed

    def session_cookie(self, token: str, *, expired: bool = False) -> str:
        parts = [f"{AUTH_COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax"]
        if expired:
            parts.append("Max-Age=0")
        else:
            parts.append(f"Max-Age={AUTH_SESSION_TTL_SECONDS}")
        if not self.server.insecure_auth_cookies:
            parts.append("Secure")
        return "; ".join(parts)

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

    def read_admin_score_payload(self) -> dict[str, Any]:
        """Read JSON metadata or a multipart metadata + .deltamusic upload."""
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            payload = self.read_payload()
            if not isinstance(payload, dict):
                raise ValueError("曲目编辑请求格式无效。")
            return payload
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as error:
            raise ValueError("替换请求缺少有效的内容长度。") from error
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise ValueError("替换请求内容过大或为空。")
        body = self.rfile.read(length)
        envelope = (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8") + body
        message = BytesParser(policy=policy.default).parsebytes(envelope)
        if not message.is_multipart():
            raise ValueError("替换请求格式无效。")
        payload: dict[str, Any] = {}
        for part in message.iter_parts():
            field = part.get_param("name", header="Content-Disposition")
            if not field:
                continue
            if field in {"file", "scoreFile"}:
                payload["_fileName"] = part.get_filename() or ""
                payload["_fileBytes"] = part.get_payload(decode=True) or b""
                continue
            raw_value = part.get_payload(decode=True)
            if isinstance(raw_value, bytes):
                charset = part.get_content_charset() or "utf-8"
                try:
                    value = raw_value.decode(charset)
                except (LookupError, UnicodeDecodeError):
                    # Browser FormData text fields are UTF-8 even when the
                    # multipart part omits a charset or declares us-ascii.
                    value = raw_value.decode("utf-8")
            else:
                value = part.get_content()
            payload[field] = (value if isinstance(value, str) else str(value)).strip()
        if "bpm" in payload:
            try:
                payload["bpm"] = int(str(payload["bpm"]).strip())
            except ValueError as error:
                raise ValueError("BPM 必须是 30 到 300 的整数。") from error
        return payload

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

    def is_admin_console_request(self) -> bool:
        """Use the existing private analytics token for all admin mutations."""
        if not self.server.analytics_enabled:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "管理后台尚未启用。"})
            return False
        if not self.is_analytics_admin():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "管理令牌无效。"})
            return False
        return True

    def allow_public_upload(self) -> bool:
        """Allow up to five public upload attempts per IP in a 30-second window."""
        now = time.monotonic()
        forwarded_for = self.headers.get("X-Forwarded-For", "") if self.server.trust_proxy else ""
        client = forwarded_for.split(",", 1)[0].strip() or self.client_address[0]
        with self.server.upload_rate_limit_lock:
            timestamps = [
                stamp
                for stamp in self.server.public_uploads.get(client, [])
                if now - stamp < PUBLIC_UPLOAD_RATE_WINDOW_SECONDS
            ]
            if len(timestamps) >= PUBLIC_UPLOAD_RATE_LIMIT:
                self.server.public_uploads[client] = timestamps
                return False
            timestamps.append(now)
            self.server.public_uploads[client] = timestamps
        return True

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if self.serve_maintenance_if_active(path):
            return
        oauth_match = re.fullmatch(r"/api/auth/oauth/(qq|wechat)/(start|callback)", path)
        if oauth_match:
            provider, action = oauth_match.groups()
            config = oauth_config(self.server, provider)
            if not config or not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": f"{oauth_provider_label(provider)}登录尚未配置。"})
                return
            if action == "start":
                state = issue_oauth_state(self.server, provider)
                if provider == "qq":
                    location = "https://graph.qq.com/oauth2.0/authorize?" + urlencode({
                        "response_type": "code",
                        "client_id": config["app_id"],
                        "redirect_uri": config["redirect_uri"],
                        "state": state,
                        "scope": "get_user_info",
                    })
                else:
                    location = "https://open.weixin.qq.com/connect/qrconnect?" + urlencode({
                        "appid": config["app_id"],
                        "redirect_uri": config["redirect_uri"],
                        "response_type": "code",
                        "scope": "snsapi_login",
                        "state": state,
                    }) + "#wechat_redirect"
                self.send_redirect(location, oauth_state_cookie(self, state))
                return
            query = parse_qs(urlparse(self.path).query)
            state = query.get("state", [""])[0]
            state_cookie = self.cookies().get(OAUTH_STATE_COOKIE_NAME)
            if not state or not state_cookie or not hmac.compare_digest(state, state_cookie.value) or not consume_oauth_state(self.server, state, provider):
                self.send_redirect(oauth_callback_target(self.server, provider, "error", "登录状态已失效，请重试。"), oauth_state_cookie(self, expired=True))
                return
            if query.get("error"):
                self.send_redirect(oauth_callback_target(self.server, provider, "error", "用户取消了授权。"), oauth_state_cookie(self, expired=True))
                return
            code = query.get("code", [""])[0]
            if not code:
                self.send_redirect(oauth_callback_target(self.server, provider, "error", "未获取到授权码，请重试。"), oauth_state_cookie(self, expired=True))
                return
            try:
                account = oauth_account(self.server, provider, oauth_profile(self.server, provider, code))
                token = issue_session(self.server, account["id"])
            except (ValueError, OSError, sqlite3.Error) as error:
                self.send_redirect(oauth_callback_target(self.server, provider, "error", str(error) or "第三方登录失败，请重试。"), oauth_state_cookie(self, expired=True))
                return
            self.send_redirect(oauth_callback_target(self.server, provider, "success"), [self.session_cookie(token), oauth_state_cookie(self, expired=True)])
            return
        if path == "/api/auth/me":
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "认证尚未启用。"})
                return
            try:
                account = authenticate_request(self)
            except sqlite3.Error:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "账户服务暂时繁忙，请稍后重试。"})
                return
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            self.send_json(HTTPStatus.OK, {"account": account_payload(self.server, account)})
            return
        if path == "/api/auth/mail-status":
            if not self.server.email_auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱验证码登录尚未配置。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            ticket = parse_qs(urlparse(self.path).query).get("ticket", [""])[0]
            if len(ticket) > 64:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "邮件状态查询参数无效。"})
                return
            self.send_json(HTTPStatus.OK, auth_mail_status_payload(self.server, ticket))
            return
        if path == "/api/analytics/summary":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            self.send_json(HTTPStatus.OK, build_public_analytics_summary())
            return
        if path == "/api/analytics/score-exports":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            self.send_json(HTTPStatus.OK, build_public_score_export_summary(self.server.analytics_retention_days))
            return
        if path == "/api/public-rankings":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            self.send_json(HTTPStatus.OK, build_public_rankings(self.server, self.server.auth_enabled, self.server.analytics_retention_days))
            return
        if path == "/api/public-donors":
            self.send_json(HTTPStatus.OK, build_public_donors())
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
        if path == "/api/admin/runtime":
            if not self.is_admin_console_request():
                return
            self.send_json(HTTPStatus.OK, build_runtime_report(self.server))
            return
        if path == "/api/admin/backup":
            if not self.is_admin_console_request():
                return
            try:
                body, filename = build_data_backup()
            except (OSError, sqlite3.Error) as error:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": f"生成数据备份失败：{error}"})
                return
            self.send_download(body, filename, "application/zip")
            return
        if path == "/api/admin/overview":
            if not self.is_admin_console_request():
                return
            try:
                requested_days = int(parse_qs(urlparse(self.path).query).get("days", ["30"])[0])
            except (TypeError, ValueError):
                requested_days = 30
            days = min(self.server.analytics_retention_days, max(1, requested_days))
            library = admin_library_catalog()
            users = admin_user_catalog()
            report = build_analytics_report(days)
            self.send_json(HTTPStatus.OK, {
                "generatedAt": report["generatedAt"],
                "summaryRangeDays": report["rangeDays"],
                "summary": report["summary"],
                "library": {
                    "total": len(library),
                    "recommended": sum(item["recommended"] for item in library),
                    "uploaders": len({item["owner"] for item in library if item["owner"] != "—"}),
                },
                "users": {
                    "total": len(users),
                    "active": sum(item["active"] for item in users),
                },
            })
            return
        if path == "/api/admin/export-methods":
            if not self.is_admin_console_request():
                return
            self.send_json(HTTPStatus.OK, export_methods_payload())
            return
        if path == "/api/admin/library":
            if not self.is_admin_console_request():
                return
            query = parse_qs(urlparse(self.path).query)
            needle = query.get("q", [""])[0].strip().casefold()
            items = admin_library_catalog()
            if needle:
                items = [item for item in items if needle in " ".join(
                    str(item[field]).casefold() for field in ("remixCode", "legacyId", "title", "artist", "sharedBy", "owner")
                )]
            self.send_json(HTTPStatus.OK, {"songs": items, "total": len(items)})
            return
        if path == "/api/admin/users":
            if not self.is_admin_console_request():
                return
            query = parse_qs(urlparse(self.path).query)
            needle = query.get("q", [""])[0].strip().casefold()
            users = admin_user_catalog()
            if needle:
                users = [item for item in users if needle in f"{item['userId']} {item['email']}".casefold()]
            self.send_json(HTTPStatus.OK, {"users": users, "total": len(users)})
            return
        if path == "/api/public-library/export-providers":
            self.send_json(HTTPStatus.OK, export_provider_payload())
            return
        if path == "/api/export-methods":
            self.send_json(HTTPStatus.OK, export_methods_payload())
            return
        if path == "/api/public-library/status":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共上传未启用。"})
                return
            self.send_json(HTTPStatus.OK, {
                "publicLibrary": True,
                "authRequired": True,
                "authAvailable": self.server.auth_enabled,
                "authProviders": sorted(self.server.oauth_providers),
            })
            return
        if path == "/api/public-library/songs":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共上传未启用。"})
                return
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "认证尚未配置。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录后查看我的曲库。"})
                return
            self.send_json(HTTPStatus.OK, {"songs": scores_owned_by(account["id"])})
            return
        if path == "/api/public-library/recommendations":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共曲库尚未启用。"})
                return
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.OK, {"recommendations": []})
                return
            self.send_json(HTTPStatus.OK, {"recommendations": list_recommendations()})
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
        if self.serve_maintenance_if_active(path):
            return
        if path == "/api/admin/donations":
            if not self.is_admin_console_request():
                return
            try:
                result = admin_set_donation(self.read_payload())
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法保存打赏金额。"})
                return
            self.send_json(HTTPStatus.OK, result)
            return
        if path == "/api/admin/library/recommendation":
            if not self.is_admin_console_request():
                return
            try:
                recommendations = add_recommendation(self.read_payload())
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法设置推荐曲目。"})
                return
            self.send_json(HTTPStatus.OK, {"action": "recommended", "recommendations": recommendations})
            return
        if path == "/api/public-library/recommendations":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共曲库尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的推荐请求。"})
                return
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "认证尚未配置。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            if not is_admin_account(account):
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只有管理员可以配置推荐曲库。"})
                return
            try:
                recommendations = add_recommendation(self.read_payload())
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法加入推荐曲库。"})
                return
            self.send_json(HTTPStatus.OK, {"action": "recommended", "recommendations": recommendations})
            return
        if path == "/api/auth/request-code":
            if not self.server.email_auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱验证码登录尚未配置。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            ticket: str | None = None
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("认证请求格式无效。")
                email = normalize_email(payload.get("email"))
                mode = payload.get("mode", "login")
                if mode not in ("login", "register"):
                    raise ValueError("认证模式无效。")
                if mode == "login":
                    with AUTH_LOCK, auth_database() as connection:
                        account_exists = connection.execute(
                            "SELECT 1 FROM accounts WHERE email = ?",
                            (email,),
                        ).fetchone()
                    if account_exists is None:
                        self.send_json(HTTPStatus.BAD_REQUEST, {"error": "该邮箱尚未注册，请切换到注册。"})
                        return
                client = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip() if self.server.trust_proxy else self.client_address[0]
                if not auth_rate_allowed(self.server, f"email:{email}", AUTH_CODE_EMAIL_LIMIT) or not auth_rate_allowed(self.server, f"ip:{client}", AUTH_CODE_IP_LIMIT):
                    self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "验证码发送过于频繁，请稍后再试。"})
                    return
                ticket = request_auth_code(self.server, email, client)
            except sqlite3.Error:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "账户服务暂时繁忙，请稍后重试。"})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法发送验证码。"})
                return
            self.send_json(HTTPStatus.OK, auth_mail_status_payload(self.server, ticket))
            return
        if path == "/api/auth/verify":
            if not self.server.email_auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱验证码登录尚未配置。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("认证请求格式无效。")
                account = consume_verification_code(self.server, normalize_email(payload.get("email")), payload.get("code"), payload.get("userId"), payload.get("mode"))
                token = issue_session(self.server, account["id"])
            except sqlite3.Error:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "账户服务暂时繁忙，请稍后重试。"})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法完成登录。"})
                return
            self.send_json_with_cookie(HTTPStatus.OK, {"account": account_payload(self.server, account)}, self.session_cookie(token))
            return
        if path == "/api/auth/effect":
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "认证尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("请求格式无效。")
                set_account_effect(self.server, account, payload.get("effect"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法保存 ID 特效。"})
                return
            self.send_json(HTTPStatus.OK, {"account": account_payload(self.server, account)})
            return
        if path == "/api/auth/effect-notice":
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "认证尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("请求格式无效。")
                mark_effect_notices(self.server, account, payload.get("effects"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法记录解锁提醒。"})
                return
            self.send_json(HTTPStatus.OK, {"account": account_payload(self.server, account)})
            return
        if path == "/api/auth/logout":
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            token = self.cookies().get(AUTH_COOKIE_NAME)
            if token and self.server.auth_enabled:
                with AUTH_LOCK, auth_database() as connection:
                    connection.execute("DELETE FROM sessions WHERE token_hash = ?", (auth_digest(self.server, token.value),))
            self.send_empty(HTTPStatus.NO_CONTENT, self.session_cookie("", expired=True))
            return
        if path == "/api/analytics/events":
            if not self.server.analytics_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "站内数据分析尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的统计请求。"})
                return
            try:
                session, events = parse_analytics_payload(self.read_analytics_payload())
                account = authenticate_request(self) if self.server.auth_enabled else None
                actor_key = analytics_actor_key(self.server, account["id"]) if account else None
                record_analytics_events(session, events, self.server.analytics_retention_days, actor_key)
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
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "认证尚未配置，暂不能上传。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录后再上传曲谱。"})
                return
            # A user may upload directly from the editor without opening
            # “我的曲库” first. Ensure legacy Jiko submissions are owned by
            # this verified account before duplicate/replace checks run.
            backfill_legacy_score_owners(account)
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("上传内容格式无效。")
                confirm_replace = payload.pop("confirmReplace", False) is True
                replace_existing = payload.pop("replaceExisting", False) is True
                # The overwrite confirmation is the continuation of an
                # already initiated upload and must not consume a rate-limit
                # slot or be blocked by the 30-second upload limit.
                if not confirm_replace and not self.allow_public_upload():
                    self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "30 秒内最多上传 5 次，请稍后再试。"})
                    return
                payload = {**payload, "sharedBy": account["user_id"]}
                action, songs, destination = save_score(
                    payload,
                    allow_replace=confirm_replace,
                    owner_account_id=account["id"],
                    replace_existing=replace_existing,
                )
                bind_score_owner(account["id"], destination)
            except DuplicateScoreError as error:
                self.send_json(HTTPStatus.CONFLICT, {
                    "error": str(error),
                    "code": "owned_duplicate" if error.owned_by_requester else "duplicate_score",
                })
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法上传曲目。"})
                return
            self.send_json(HTTPStatus.CREATED if action == "created" else HTTPStatus.OK, {"action": action, "songs": songs})
            return
        if path != "/api/local-library/songs":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到维护接口。"})
            return
        if not self.request_is_local():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "维护接口只允许本机访问。"})
            return
        try:
            payload = self.read_payload()
            replace_existing = payload.pop("replaceExisting", False) is True if isinstance(payload, dict) else False
            action, songs, _ = save_score(payload, replace_existing=replace_existing)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法写入本地曲库。"})
            return
        self.send_json(HTTPStatus.OK, {"action": action, "songs": songs})

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/admin/library/song":
            if not self.is_admin_console_request():
                return
            try:
                songs = admin_delete_score(self.read_payload())
            except FileNotFoundError as error:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法删除曲目。"})
                return
            self.send_json(HTTPStatus.OK, {"action": "deleted", "songs": songs})
            return
        if path == "/api/admin/library/recommendation":
            if not self.is_admin_console_request():
                return
            try:
                recommendations = remove_recommendation(self.read_payload())
            except FileNotFoundError as error:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法取消推荐。"})
                return
            self.send_json(HTTPStatus.OK, {"action": "unrecommended", "recommendations": recommendations})
            return
        if path == "/api/public-library/recommendations":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共曲库尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的取消推荐请求。"})
                return
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "认证尚未配置。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            if not is_admin_account(account):
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只有管理员可以配置推荐曲库。"})
                return
            try:
                recommendations = remove_recommendation(self.read_payload())
            except FileNotFoundError as error:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法取消推荐。"})
                return
            self.send_json(HTTPStatus.OK, {"action": "unrecommended", "recommendations": recommendations})
            return
        if path != "/api/public-library/songs":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到曲库接口。"})
            return
        if not self.server.public_library:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共上传未启用。"})
            return
        if not self.request_is_same_origin():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的删除请求。"})
            return
        if not self.server.auth_enabled:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "认证尚未配置，暂不能删除。"})
            return
        account = authenticate_request(self)
        if not account:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录后再删除曲目。"})
            return
        try:
            songs = delete_owned_score(account["id"], self.read_payload())
        except PermissionError as error:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
            return
        except FileNotFoundError as error:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
            return
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法删除曲目。"})
            return
        self.send_json(HTTPStatus.OK, {"action": "deleted", "songs": songs})

    def do_PUT(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/admin/export-methods":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到管理接口。"})
            return
        if not self.is_admin_console_request():
            return
        try:
            updated = update_export_methods(self.read_payload())
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError, sqlite3.Error) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法保存导出方式配置。"})
            return
        self.send_json(HTTPStatus.OK, updated)

    def do_PATCH(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/admin/library/song":
            if not self.is_admin_console_request():
                return
            try:
                songs = admin_update_score(self.read_admin_score_payload())
            except DuplicateScoreError as error:
                self.send_json(HTTPStatus.CONFLICT, {"error": str(error), "code": "duplicate_score"})
                return
            except FileNotFoundError as error:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError, sqlite3.Error) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法保存曲目。"})
                return
            self.send_json(HTTPStatus.OK, {"action": "updated", "songs": songs})
            return
        if path == "/api/public-library/songs":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共曲库尚未启用。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的曲库请求。"})
                return
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先配置并登录账号。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            try:
                backfill_legacy_score_owners(account)
                action, songs, _ = update_owned_score(account["id"], account["user_id"], self.read_payload())
            except DuplicateScoreError as error:
                self.send_json(HTTPStatus.CONFLICT, {"error": str(error), "code": "duplicate_score"})
                return
            except PermissionError as error:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                return
            except FileNotFoundError as error:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法保存曲目。"})
                return
            self.send_json(HTTPStatus.OK, {"action": action, "songs": songs})
            return
        if path != "/api/auth/me":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到认证接口。"})
            return
        if not self.server.auth_enabled:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "认证尚未启用。"})
            return
        if not self.request_is_same_origin():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
            return
        account = authenticate_request(self)
        if not account:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
            return
        try:
            payload = self.read_payload()
            if not isinstance(payload, dict):
                raise ValueError("资料请求格式无效。")
            songs = rename_account_user_id(account, payload.get("userId"))
            with AUTH_LOCK, auth_database() as connection:
                updated = connection.execute("SELECT id, email, user_id FROM accounts WHERE id = ?", (account["id"],)).fetchone()
            self.send_json(HTTPStatus.OK, {"account": account_payload(self.server, updated), "songs": songs})
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法更新用户 ID。"})


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 Harmonica Deck 静态站点与曲库服务")
    parser.add_argument("--port", type=int, default=8765, help="本地端口（默认：8765）")
    parser.add_argument("--public", action="store_true", help="监听所有网卡，并启用匿名上传到公共曲库")
    parser.add_argument("--trust-proxy", action="store_true", help="使用反向代理传入的 X-Forwarded-For 做公共上传限流")
    parser.add_argument("--auth-secret", default=os.environ.get("DELTA_AUTH_SECRET", ""), help="认证 HMAC 密钥；也可设 DELTA_AUTH_SECRET")
    parser.add_argument("--smtp-host", default=os.environ.get("DELTA_SMTP_HOST", ""), help="SMTP 主机；也可设 DELTA_SMTP_HOST")
    parser.add_argument("--smtp-port", type=int, default=int(os.environ.get("DELTA_SMTP_PORT", "587")), help="SMTP 端口（默认 587）")
    parser.add_argument("--smtp-username", default=os.environ.get("DELTA_SMTP_USERNAME", ""), help="SMTP 用户名；也可设 DELTA_SMTP_USERNAME")
    parser.add_argument("--smtp-password", default=os.environ.get("DELTA_SMTP_PASSWORD", ""), help="SMTP 密码；也可设 DELTA_SMTP_PASSWORD")
    parser.add_argument("--smtp-from", default=os.environ.get("DELTA_SMTP_FROM", ""), help="验证码发件人；也可设 DELTA_SMTP_FROM")
    parser.add_argument("--smtp-ssl", action="store_true", default=os.environ.get("DELTA_SMTP_SSL", "").lower() in {"1", "true", "yes"}, help="使用 SMTPS（通常为 465 端口）")
    parser.add_argument("--no-smtp-starttls", action="store_true", help="禁用 SMTP STARTTLS（默认启用）")
    parser.add_argument("--qq-app-id", default=os.environ.get("DELTA_QQ_APP_ID", ""), help="QQ 互联应用 App ID；也可设 DELTA_QQ_APP_ID")
    parser.add_argument("--qq-app-key", default=os.environ.get("DELTA_QQ_APP_KEY", ""), help="QQ 互联应用 App Key；也可设 DELTA_QQ_APP_KEY")
    parser.add_argument("--qq-redirect-uri", default=os.environ.get("DELTA_QQ_REDIRECT_URI", ""), help="QQ OAuth 回调地址；也可设 DELTA_QQ_REDIRECT_URI")
    parser.add_argument("--wechat-app-id", default=os.environ.get("DELTA_WECHAT_APP_ID", ""), help="微信开放平台网站应用 AppID；也可设 DELTA_WECHAT_APP_ID")
    parser.add_argument("--wechat-app-secret", default=os.environ.get("DELTA_WECHAT_APP_SECRET", ""), help="微信开放平台网站应用 AppSecret；也可设 DELTA_WECHAT_APP_SECRET")
    parser.add_argument("--wechat-redirect-uri", default=os.environ.get("DELTA_WECHAT_REDIRECT_URI", ""), help="微信 OAuth 回调地址；也可设 DELTA_WECHAT_REDIRECT_URI")
    parser.add_argument("--auth-code-log-only", action="store_true", default=os.environ.get("DELTA_AUTH_CODE_LOG_ONLY", "").lower() in {"1", "true", "yes"}, help="仅本地测试：把验证码写入服务日志，不发送邮件")
    parser.add_argument("--insecure-auth-cookies", action="store_true", help="仅本地测试：允许 HTTP 登录 Cookie；生产环境请勿使用")
    parser.add_argument("--analytics-admin-token", default=os.environ.get("DELTA_ANALYTICS_ADMIN_TOKEN", ""), help="启用内置分析并保护管理接口的令牌；也可设 DELTA_ANALYTICS_ADMIN_TOKEN")
    parser.add_argument("--analytics-retention-days", type=int, default=DEFAULT_ANALYTICS_RETENTION_DAYS, help=f"行为事件保留天数（默认 {DEFAULT_ANALYTICS_RETENTION_DAYS}，最多 365）")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    if not 1 <= args.analytics_retention_days <= 365:
        parser.error("统计保留天数必须在 1 到 365 之间")
    if not 1 <= args.smtp_port <= 65535:
        parser.error("SMTP 端口必须在 1 到 65535 之间")
    email_auth_requested = bool(args.smtp_host or args.smtp_from or args.auth_code_log_only)
    if email_auth_requested and not args.auth_secret:
        parser.error("启用邮箱登录时必须设置 DELTA_AUTH_SECRET 或 --auth-secret")
    if email_auth_requested and not args.auth_code_log_only:
        if not (args.smtp_host and args.smtp_from):
            parser.error("启用 SMTP 登录时必须设置 DELTA_SMTP_HOST 和 DELTA_SMTP_FROM")
        if bool(args.smtp_username) != bool(args.smtp_password):
            parser.error("DELTA_SMTP_USERNAME 与 DELTA_SMTP_PASSWORD 必须同时设置或同时留空")
    oauth_values = {
        "qq": (args.qq_app_id, args.qq_app_key, args.qq_redirect_uri),
        "wechat": (args.wechat_app_id, args.wechat_app_secret, args.wechat_redirect_uri),
    }
    oauth_providers: dict[str, dict[str, str]] = {}
    for provider, values in oauth_values.items():
        if any(values) and not all(values):
            parser.error(f"{oauth_provider_label(provider)}登录必须同时设置 AppID、密钥和回调地址")
        if all(values):
            parsed_redirect = urlparse(values[2])
            if parsed_redirect.scheme != "https" or not parsed_redirect.netloc or not parsed_redirect.path.endswith(f"/api/auth/oauth/{provider}/callback"):
                parser.error(f"{oauth_provider_label(provider)}登录回调地址必须是 HTTPS，并以 /api/auth/oauth/{provider}/callback 结尾")
            oauth_providers[provider] = {"app_id": values[0], "app_secret": values[1], "redirect_uri": values[2]}
    oauth_requested = bool(oauth_providers)
    auth_requested = email_auth_requested or oauth_requested
    if auth_requested and not args.auth_secret:
        parser.error("启用登录时必须设置 DELTA_AUTH_SECRET 或 --auth-secret")
    if args.public and not auth_requested:
        print("警告：公共上传已启用但认证未配置；网页会隐藏直传入口。", file=sys.stderr)

    handler = lambda *args_, **kwargs: LocalLibraryRequestHandler(*args_, directory=str(REPOSITORY_ROOT), **kwargs)
    host = "0.0.0.0" if args.public else "127.0.0.1"
    server = BoundedThreadingHTTPServer((host, args.port), handler)
    server.public_library = args.public
    server.trust_proxy = args.trust_proxy
    server.analytics_admin_token = args.analytics_admin_token
    server.analytics_enabled = bool(args.analytics_admin_token)
    server.analytics_retention_days = args.analytics_retention_days
    server.public_uploads: dict[str, list[float]] = {}
    server.upload_rate_limit_lock = threading.Lock()
    server.auth_enabled = auth_requested
    server.email_auth_enabled = email_auth_requested
    server.auth_secret = args.auth_secret
    server.smtp_host = args.smtp_host
    server.smtp_port = args.smtp_port
    server.smtp_username = args.smtp_username
    server.smtp_password = args.smtp_password
    server.smtp_from = args.smtp_from
    server.smtp_ssl = args.smtp_ssl
    server.smtp_starttls = not args.no_smtp_starttls and not args.smtp_ssl
    server.auth_code_log_only = args.auth_code_log_only
    server.insecure_auth_cookies = args.insecure_auth_cookies
    server.oauth_providers = oauth_providers
    server.oauth_states: dict[str, dict[str, Any]] = {}
    server.oauth_state_lock = threading.Lock()
    server.auth_code_requests: dict[str, list[float]] = {}
    server.auth_rate_limit_lock = threading.Lock()
    server.auth_mail_dispatcher: AuthMailDispatcher | None = None
    server.hot_ranking_stop_event = threading.Event()
    server.hot_ranking_thread: threading.Thread | None = None
    if server.auth_enabled or server.analytics_enabled:
        initialize_auth_database()
        migrate_identity_tables()
    if server.auth_enabled:
        backfill_legacy_score_owners_for_known_account()
    if server.email_auth_enabled and not server.auth_code_log_only:
        server.auth_mail_dispatcher = AuthMailDispatcher(server)
    if server.analytics_enabled:
        initialize_hot_ranking_database()
        try:
            get_daily_hot_ranking(server.analytics_retention_days)
        except (OSError, sqlite3.Error, ValueError) as error:
            print(f"热门曲库每日排行初始化失败：{error}", file=sys.stderr)
        server.hot_ranking_thread = threading.Thread(
            target=hot_ranking_scheduler,
            args=(server.analytics_retention_days, server.hot_ranking_stop_event),
            name="daily-hot-ranking",
            daemon=True,
        )
        server.hot_ranking_thread.start()
    if args.public:
        print(f"公共曲库服务已启动：http://0.0.0.0:{args.port}/")
        print("公共上传已启用；部署时请通过 HTTPS 反向代理，并配置 WAF 或限流。")
    else:
        print(f"本地维护服务已启动：http://127.0.0.1:{args.port}/")
        print("仅监听 127.0.0.1；按 Ctrl+C 停止。")
    if server.analytics_enabled:
        print(f"站内行为分析已启用：/admin/analytics.html（事件保留 {server.analytics_retention_days} 天）")
    if server.auth_enabled:
        if server.email_auth_enabled:
            source = "本地日志（测试模式）" if server.auth_code_log_only else f"SMTP {server.smtp_host}:{server.smtp_port}"
            print(f"邮箱登录已启用：{source}")
        if server.oauth_providers:
            print(f"第三方登录已启用：{', '.join(oauth_provider_label(provider) for provider in sorted(server.oauth_providers))}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地维护服务已停止。")
    finally:
        if server.auth_mail_dispatcher:
            server.auth_mail_dispatcher.close()
        server.hot_ranking_stop_event.set()
        if server.hot_ranking_thread:
            server.hot_ranking_thread.join(timeout=1)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
