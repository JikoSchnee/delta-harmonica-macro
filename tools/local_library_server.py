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
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
import uuid
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
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
    validate_package,
    write_library,
)


SOURCE_DIRECTORY = REPOSITORY_ROOT / "data" / "community-scores"
LIBRARY_OUTPUT = REPOSITORY_ROOT / "data" / "community-songs.js"
MAX_REQUEST_BYTES = 1_000_000
MAX_ANALYTICS_REQUEST_BYTES = 25_000
PUBLIC_UPLOAD_RATE_WINDOW_SECONDS = 30
PUBLIC_UPLOAD_RATE_LIMIT = 5
PUBLIC_EXPORT_COUNT_REFRESH_SECONDS = 10 * 60
AUTH_CODE_TTL_SECONDS = 10 * 60
AUTH_CODE_MAX_ATTEMPTS = 5
AUTH_CODE_EMAIL_LIMIT = 5
AUTH_CODE_IP_LIMIT = 12
AUTH_CODE_RATE_WINDOW_SECONDS = 60 * 60
AUTH_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
OAUTH_STATE_TTL_SECONDS = 10 * 60
OAUTH_HTTP_TIMEOUT_SECONDS = 15
AUTH_COOKIE_NAME = "delta_auth_session"
OAUTH_STATE_COOKIE_NAME = "delta_oauth_state"
ADMIN_EMAIL = "274492469@qq.com"
LEGACY_OWNER_EMAIL = "274492469@qq.com"
LEGACY_OWNER_USER_ID = "jiko"
AUTH_DATABASE = REPOSITORY_ROOT / "data" / "auth.sqlite3"
HOT_RANKING_DATABASE = REPOSITORY_ROOT / "data" / "hot-rankings.sqlite3"
# User IDs may contain Unicode letters/numbers (including Chinese characters)
# while retaining the existing underscore support.
USER_ID_PATTERN = re.compile(r"^[\w]{3,24}$", re.UNICODE)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LIBRARY_LOCK = threading.Lock()
ANALYTICS_LOCK = threading.Lock()
AUTH_LOCK = threading.Lock()
HOT_RANKING_LOCK = threading.Lock()
PUBLIC_EXPORT_COUNT_CACHE_LOCK = threading.Lock()
PUBLIC_EXPORT_COUNT_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
ANALYTICS_DIRECTORY = REPOSITORY_ROOT / "data" / "analytics"
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


class DuplicateScoreError(ValueError):
    """Raised when a public upload would replace an existing community score."""

    def __init__(self, message: str, *, owned_by_requester: bool = False) -> None:
        super().__init__(message)
        self.owned_by_requester = owned_by_requester


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
    event_counts = Counter(item["event"] for item in records)
    event_sessions: dict[str, set[str]] = defaultdict(set)
    daily_sessions: dict[str, set[str]] = defaultdict(set)
    daily_views: Counter[str] = Counter()
    daily_exports: Counter[str] = Counter()
    daily_export_keys: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
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
        if day:
            daily_sessions[day].add(item["session"])
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
        "summary": {"sessions": len(sessions), "pageViews": page_views, "events": len(records), "macroDownloads": event_counts["macro_downloaded"]},
        "timeline": timeline,
        "hourlyTimeline": hourly_timeline,
        "sources": [{"name": name, "count": count} for name, count in source_counts.most_common(8)],
        "events": [{"name": name, "count": count, "sessions": len(event_sessions[name])} for name, count in event_counts.most_common()],
        "scoreOperations": score_operations[:100],
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


def score_export_counts_for_period(retention_days: int) -> Counter[str]:
    """Read export totals once for the daily hot-ranking job."""
    safe_days = max(1, retention_days)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=safe_days - 1)
    exports: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    aliases = analytics_score_aliases()
    for offset in range(safe_days):
        path = analytics_event_path(start + timedelta(days=offset))
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if not isinstance(item, dict) or item.get("event") not in SCORE_EXPORT_EVENTS:
                    continue
                properties = item.get("properties")
                score_id = properties.get("score_id") if isinstance(properties, dict) else None
                canonical_id = canonical_analytics_score_id(score_id, aliases)
                if canonical_id:
                    actor = item.get("actor") if isinstance(item.get("actor"), str) and item.get("actor") else item.get("session")
                    if not isinstance(actor, str):
                        continue
                    export_key = (canonical_id, actor)
                    if export_key not in seen:
                        seen.add(export_key)
                        exports[canonical_id] += 1
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return exports


def yesterday_export_ranking() -> list[dict[str, Any]]:
    """Return unique-actor score exports for the previous local calendar day."""
    target_date = datetime.now().astimezone().date() - timedelta(days=1)
    exports: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    aliases = analytics_score_aliases()
    if not ANALYTICS_DIRECTORY.exists():
        return []
    for path in ANALYTICS_DIRECTORY.glob("events-*.ndjson"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
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
    ordered = sorted(exports.items(), key=lambda item: (-item[1], item[0]))[:10]
    return [{"rank": rank, "scoreId": score_id, "exports": count} for rank, (score_id, count) in enumerate(ordered, start=1)]


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
    exports_by_score = score_export_counts_for_period(retention_days)
    counts: Counter[str] = Counter()
    for user_id, score_id in public_owned_scores(auth_enabled):
        counts[user_id] += exports_by_score.get(score_id, 0)
    ordered = sorted(
        ((user_id, count) for user_id, count in counts.items() if count > 0),
        key=lambda item: (-item[1], item[0].casefold(), item[0]),
    )
    return [{"rank": rank, "userId": user_id, "exports": count} for rank, (user_id, count) in enumerate(ordered, start=1)]


def build_public_rankings(auth_enabled: bool, retention_days: int) -> dict[str, Any]:
    """Build the privacy-safe rankings consumed by the public homepage."""
    yesterday = datetime.now().astimezone().date() - timedelta(days=1)
    return {
        "rankingDate": yesterday.isoformat(),
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "uploads": upload_ranking(auth_enabled),
        "contributions": contribution_ranking(auth_enabled, retention_days),
        "yesterdayExports": yesterday_export_ranking(),
    }


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


def build_public_score_export_summary(retention_days: int) -> dict[str, Any]:
    """Return export totals from a short-lived cache, independent of the daily hot ranking."""
    safe_days = max(1, retention_days)
    now = time.monotonic()
    with PUBLIC_EXPORT_COUNT_CACHE_LOCK:
        cached = PUBLIC_EXPORT_COUNT_CACHE.get(safe_days)
        if cached and now - cached[0] < PUBLIC_EXPORT_COUNT_REFRESH_SECONDS:
            return cached[1]

    counts = score_export_counts_for_period(safe_days)
    summary = {
        "rankingDate": datetime.now().astimezone().date().isoformat(),
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scores": [
            {"scoreId": score_id, "exports": count, "rank": rank}
            for rank, (score_id, count) in enumerate(sorted(counts.items(), key=lambda item: (-item[1], item[0])), start=1)
        ],
    }
    with PUBLIC_EXPORT_COUNT_CACHE_LOCK:
        PUBLIC_EXPORT_COUNT_CACHE[safe_days] = (time.monotonic(), summary)
    return summary


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


def save_score(payload: Any, *, allow_replace: bool = True, owner_account_id: str | None = None) -> tuple[str, list[dict[str, Any]], Path]:
    """Validate, store, and expose one score while serialising concurrent uploads."""
    incoming_code = normalize_remix_code(payload.get("remixCode")) if isinstance(payload, dict) else None
    score = validate_package(payload)
    with LIBRARY_LOCK:
        existing_scores = read_scores()
        matches = [(path, item) for path, item in existing_scores if item["remixCode"] == score["remixCode"]]
        if not matches and owner_account_id and not incoming_code:
            owned_title_artist_matches = [
                (path, item)
                for path, item in existing_scores
                if item["title"].casefold() == score["title"].casefold()
                and item["artist"].casefold() == score["artist"].casefold()
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
            score["analyticsId"] = existing_score.get("analyticsId") or legacy_analytics_score_id(existing_score)
            score["legacyAnalyticsIds"] = existing_score.get("legacyAnalyticsIds") or []
            score["legacyAdminIds"] = existing_score.get("legacyAdminIds") or [legacy_admin_id(existing_score)]
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
        candidate["analyticsId"] = existing_score.get("analyticsId") or legacy_analytics_score_id(existing_score)
        candidate["legacyAnalyticsIds"] = existing_score.get("legacyAnalyticsIds") or []
        candidate["legacyAdminIds"] = existing_score.get("legacyAdminIds") or [legacy_admin_id(existing_score)]
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
    connection = sqlite3.connect(AUTH_DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
        """)


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


def account_payload(account: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    email = str(account["email"])
    if email.endswith("@oauth.invalid"):
        provider = "QQ" if email.startswith("qq_") else "微信"
        credential = f"{provider} 登录账号"
    else:
        credential = mask_email(email)
    return {"userId": account["user_id"], "email": credential, "isAdmin": is_admin_account(account)}


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
            "key": score["key"],
            "meter": score["meter"],
            "bpm": score["bpm"],
            "displayUrl": score.get("displayUrl", ""),
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
        "key": payload.get("key", source_score["key"]),
        "meter": payload.get("meter", source_score["meter"]),
        "bpm": payload.get("bpm", source_score["bpm"]),
        "jianpu": source_score["jianpu"],
        "displayUrl": payload.get("displayUrl", source_score.get("displayUrl")),
        "createdAt": existing_score.get("createdAt"),
        "remixCode": existing_score.get("remixCode"),
        "analyticsId": existing_score.get("analyticsId") or analytics_score_id(existing_score),
        "legacyAnalyticsIds": existing_score.get("legacyAnalyticsIds") or [],
        "legacyAdminIds": existing_score.get("legacyAdminIds") or [legacy_admin_id(existing_score)],
    }
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
            "COUNT(DISTINCT score_owners.remix_code) AS uploads, "
            "COUNT(DISTINCT CASE WHEN sessions.expires_at > ? THEN sessions.token_hash END) AS active_sessions "
            "FROM accounts "
            "LEFT JOIN score_owners ON score_owners.account_id = accounts.id "
            "LEFT JOIN sessions ON sessions.account_id = accounts.id "
            "GROUP BY accounts.id ORDER BY accounts.created_at DESC",
            (now,),
        ).fetchall()
    return [{
        "id": row["id"],
        "userId": row["user_id"],
        "email": mask_email(str(row["email"])),
        "role": "管理员" if is_admin_account(row) else "用户",
        "uploads": row["uploads"],
        "active": bool(row["active_sessions"]),
        "registeredAt": datetime.fromtimestamp(row["created_at"], timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "updatedAt": datetime.fromtimestamp(row["updated_at"], timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    } for row in rows]


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


def request_auth_code(server: ThreadingHTTPServer, email: str, client: str) -> None:
    now = now_timestamp()
    with AUTH_LOCK, auth_database() as connection:
        connection.execute("DELETE FROM email_codes WHERE expires_at <= ?", (now,))
        code = f"{secrets.randbelow(1_000_000):06d}"
        connection.execute(
            "INSERT INTO email_codes(email, code_hash, expires_at, attempts) VALUES (?, ?, ?, 0) "
            "ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash, expires_at=excluded.expires_at, attempts=0",
            (email, auth_digest(server, code), now + AUTH_CODE_TTL_SECONDS),
        )
    if server.auth_code_log_only:
        print(f"[AUTH TEST ONLY] Verification code for {email}: {code}", flush=True)
        return
    message = EmailMessage()
    message["Subject"] = "三角洲口琴演奏家登录验证码"
    message["From"] = server.smtp_from
    message["To"] = email
    message.set_content(f"你的登录验证码是：{code}\n\n验证码将在 10 分钟后失效。若不是你本人操作，请忽略此邮件。")
    try:
        if server.smtp_ssl:
            with smtplib.SMTP_SSL(server.smtp_host, server.smtp_port, context=ssl.create_default_context(), timeout=15) as smtp:
                if server.smtp_username:
                    smtp.login(server.smtp_username, server.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(server.smtp_host, server.smtp_port, timeout=15) as smtp:
                smtp.ehlo()
                if server.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if server.smtp_username:
                    smtp.login(server.smtp_username, server.smtp_password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        with AUTH_LOCK, auth_database() as connection:
            connection.execute("DELETE FROM email_codes WHERE email = ?", (email,))
        raise ValueError("验证码邮件发送失败，请稍后重试。") from error


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


class LocalLibraryRequestHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self) -> None:  # noqa: N802
        """Make ordinary reloads see newly deployed static files.

        The app is deliberately served without content-hashed filenames, so
        static responses must be revalidated. API responses already set their
        own ``Cache-Control`` header and are left unchanged here.
        """
        has_cache_control = any(
            header.lower().startswith(b"cache-control:")
            for header in self._headers_buffer
        )
        if not has_cache_control:
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                cache_control = "no-store"
            elif path == "/" or path.endswith(".html"):
                cache_control = "no-cache, no-store, must-revalidate"
            else:
                cache_control = "no-cache, must-revalidate"
            self.send_header("Cache-Control", cache_control)
        super().end_headers()

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_json_with_cookie(self, status: HTTPStatus, payload: dict[str, Any], cookie: str | None = None) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(encoded)

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
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录。"})
                return
            self.send_json(HTTPStatus.OK, {"account": account_payload(account)})
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
            self.send_json(HTTPStatus.OK, build_public_rankings(self.server.auth_enabled, self.server.analytics_retention_days))
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
                request_auth_code(self.server, email, client)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法发送验证码。"})
                return
            self.send_empty(HTTPStatus.NO_CONTENT)
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
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error) or "无法完成登录。"})
                return
            self.send_json_with_cookie(HTTPStatus.OK, {"account": account_payload(account)}, self.session_cookie(token))
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
                # The overwrite confirmation is the continuation of an
                # already initiated upload and must not consume a rate-limit
                # slot or be blocked by the 30-second upload limit.
                if not confirm_replace and not self.allow_public_upload():
                    self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "30 秒内最多上传 5 次，请稍后再试。"})
                    return
                payload = {**payload, "sharedBy": account["user_id"]}
                action, songs, destination = save_score(payload, allow_replace=confirm_replace, owner_account_id=account["id"])
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
            action, songs, _ = save_score(self.read_payload())
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
            self.send_json(HTTPStatus.OK, {"account": account_payload(updated), "songs": songs})
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
    server = ThreadingHTTPServer((host, args.port), handler)
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
    server.hot_ranking_stop_event = threading.Event()
    server.hot_ranking_thread: threading.Thread | None = None
    if server.auth_enabled or server.analytics_enabled:
        initialize_auth_database()
        migrate_identity_tables()
    if server.auth_enabled:
        backfill_legacy_score_owners_for_known_account()
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
        server.hot_ranking_stop_event.set()
        if server.hot_ranking_thread:
            server.hot_ranking_thread.join(timeout=1)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
