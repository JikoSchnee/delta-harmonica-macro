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
AUTH_CODE_TTL_SECONDS = 10 * 60
AUTH_CODE_MAX_ATTEMPTS = 5
AUTH_CODE_EMAIL_LIMIT = 5
AUTH_CODE_IP_LIMIT = 12
AUTH_CODE_RATE_WINDOW_SECONDS = 60 * 60
AUTH_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
AUTH_COOKIE_NAME = "delta_auth_session"
LEGACY_OWNER_EMAIL = "274492469@qq.com"
LEGACY_OWNER_USER_ID = "jiko"
AUTH_DATABASE = REPOSITORY_ROOT / "data" / "auth.sqlite3"
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,24}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LIBRARY_LOCK = threading.Lock()
ANALYTICS_LOCK = threading.Lock()
AUTH_LOCK = threading.Lock()
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


def score_owner_account_id(path: Path) -> str | None:
    relative = str(path.relative_to(REPOSITORY_ROOT))
    with AUTH_LOCK, auth_database() as connection:
        row = connection.execute("SELECT account_id FROM score_owners WHERE score_path = ?", (relative,)).fetchone()
    return row["account_id"] if row else None


def save_score(payload: Any, *, allow_replace: bool = True, owner_account_id: str | None = None) -> tuple[str, list[dict[str, Any]], Path]:
    """Validate, store, and expose one score while serialising concurrent uploads."""
    score = validate_package(payload)
    with LIBRARY_LOCK:
        existing_scores = read_scores()
        matches = [(path, item) for path, item in existing_scores if dedupe_key(item) == dedupe_key(score)]
        if len(matches) > 1:
            raise ValueError("曲库中存在多个相同身份的曲目，请先手动整理源文件。")
        if matches and not allow_replace:
            owned_by_requester = owner_account_id and len(matches) == 1 and score_owner_account_id(matches[0][0]) == owner_account_id
            if owned_by_requester:
                allow_replace = True
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
        return ("updated" if matches else "created"), rebuilt_scores, destination


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
            CREATE TABLE IF NOT EXISTS score_owners (
                score_path TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id)
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
        """)


def now_timestamp() -> int:
    return int(time.time())


def normalize_email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("请输入有效的邮箱地址。")
    return email


def validate_user_id(value: Any) -> str:
    user_id = str(value or "").strip()
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise ValueError("用户 ID 应为 3–24 个字母、数字或下划线。")
    return user_id


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        visible = local[:1] + "*"
    else:
        visible = local[:2] + "***"
    return f"{visible}@{domain}"


def account_payload(account: sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    return {"userId": account["user_id"], "email": mask_email(account["email"])}


def auth_digest(server: ThreadingHTTPServer, value: str) -> str:
    return hmac.new(server.auth_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


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
    with AUTH_LOCK, auth_database() as connection:
        connection.execute(
            "INSERT INTO score_owners(score_path, account_id) VALUES (?, ?) "
            "ON CONFLICT(score_path) DO UPDATE SET account_id = excluded.account_id",
            (relative, account_id),
        )


def backfill_legacy_score_owners(account: sqlite3.Row | None) -> None:
    """Attach legacy Jiko community submissions to the verified owner account.

    PDMX songs are not stored in the community score directory, but the explicit
    source check keeps this migration safe if another import path ever exposes
    them through read_scores().
    """
    if not account or str(account["email"]).casefold() != LEGACY_OWNER_EMAIL:
        return
    legacy_paths = []
    for path, score in read_scores():
        if not is_canonical_source(path):
            continue
        if score.get("source") == "PDMX":
            continue
        if str(score.get("sharedBy", "")).strip().casefold() == LEGACY_OWNER_USER_ID:
            legacy_paths.append(str(path.relative_to(REPOSITORY_ROOT)))
    if not legacy_paths:
        return
    with AUTH_LOCK, auth_database() as connection:
        connection.executemany(
            "INSERT INTO score_owners(score_path, account_id) VALUES (?, ?) "
            "ON CONFLICT(score_path) DO UPDATE SET account_id = excluded.account_id",
            [(path, account["id"]) for path in legacy_paths],
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
        owned_paths = {row["score_path"] for row in connection.execute("SELECT score_path FROM score_owners WHERE account_id = ?", (account_id,)).fetchall()}
    if not owned_paths:
        return []
    return [score for path, score in read_scores() if str(path.relative_to(REPOSITORY_ROOT)) in owned_paths]


def delete_owned_score(account_id: str, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("删除请求格式无效。")
    identity = {}
    for field, limit in (("title", 48), ("artist", 64), ("sharedBy", 48)):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError("删除请求中的曲目信息无效。")
        identity[field] = value.strip()

    with LIBRARY_LOCK:
        matches = [
            (path, score)
            for path, score in read_scores()
            if is_canonical_source(path)
            and all(score.get(field) == value for field, value in identity.items())
        ]
        if not matches:
            raise FileNotFoundError("未找到该曲目。")
        for path, _ in matches:
            if score_owner_account_id(path) != account_id:
                raise PermissionError("只能删除自己上传的曲目。")
        relative_paths = [str(path.relative_to(REPOSITORY_ROOT)) for path, _ in matches]
        for path, _ in matches:
            path.unlink()
        with AUTH_LOCK, auth_database() as connection:
            connection.executemany("DELETE FROM score_owners WHERE score_path = ?", [(path,) for path in relative_paths])
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
        rows = connection.execute("SELECT score_path FROM score_owners WHERE account_id = ?", (account["id"],)).fetchall()
        for row in rows:
            path = (REPOSITORY_ROOT / row["score_path"]).resolve()
            if not is_canonical_source(path) or not path.exists():
                continue
            package = json.loads(path.read_text(encoding="utf-8"))
            package["sharedBy"] = new_user_id
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
        self.send_header("Cache-Control", "no-store")
        if cookie:
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
        if path == "/api/auth/me":
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "邮箱登录尚未启用。"})
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
            self.send_json(HTTPStatus.OK, {"publicLibrary": True, "authRequired": True, "authAvailable": self.server.auth_enabled})
            return
        if path == "/api/public-library/songs":
            if not self.server.public_library:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "公共上传未启用。"})
                return
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱登录尚未配置。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录后查看我的曲库。"})
                return
            self.send_json(HTTPStatus.OK, {"songs": scores_owned_by(account["id"])})
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
        if path == "/api/auth/request-code":
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱登录尚未配置。"})
                return
            if not self.request_is_same_origin():
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "只接受本站页面发起的认证请求。"})
                return
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("认证请求格式无效。")
                email = normalize_email(payload.get("email"))
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
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱登录尚未配置。"})
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
            if not self.server.auth_enabled:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱登录尚未配置，暂不能上传。"})
                return
            account = authenticate_request(self)
            if not account:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录后再上传曲谱。"})
                return
            if not self.allow_public_upload():
                self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "上传过于频繁，请 30 秒后再试。"})
                return
            try:
                payload = self.read_payload()
                if not isinstance(payload, dict):
                    raise ValueError("上传内容格式无效。")
                payload = {**payload, "sharedBy": account["user_id"]}
                action, songs, destination = save_score(payload, allow_replace=False, owner_account_id=account["id"])
                bind_score_owner(account["id"], destination)
            except DuplicateScoreError as error:
                self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
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
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "邮箱登录尚未配置，暂不能删除。"})
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
        if path != "/api/auth/me":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到认证接口。"})
            return
        if not self.server.auth_enabled:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "邮箱登录尚未启用。"})
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
    parser.add_argument("--auth-code-log-only", action="store_true", default=os.environ.get("DELTA_AUTH_CODE_LOG_ONLY", "").lower() in {"1", "true", "yes"}, help="仅本地测试：把验证码写入服务日志，不发送邮件")
    parser.add_argument("--insecure-auth-cookies", action="store_true", help="仅本地测试：允许 HTTP 登录 Cookie；生产环境请勿使用")
    parser.add_argument("--analytics-admin-token", default=os.environ.get("DELTA_ANALYTICS_ADMIN_TOKEN", ""), help="启用内置分析并保护管理接口的令牌；也可设 DELTA_ANALYTICS_ADMIN_TOKEN")
    parser.add_argument("--analytics-retention-days", type=int, default=DEFAULT_ANALYTICS_RETENTION_DAYS, help=f"匿名事件保留天数（默认 {DEFAULT_ANALYTICS_RETENTION_DAYS}，最多 365）")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    if not 1 <= args.analytics_retention_days <= 365:
        parser.error("统计保留天数必须在 1 到 365 之间")
    if not 1 <= args.smtp_port <= 65535:
        parser.error("SMTP 端口必须在 1 到 65535 之间")
    auth_requested = bool(args.smtp_host or args.smtp_from or args.auth_code_log_only)
    if auth_requested and not args.auth_secret:
        parser.error("启用邮箱登录时必须设置 DELTA_AUTH_SECRET 或 --auth-secret")
    if auth_requested and not args.auth_code_log_only:
        if not (args.smtp_host and args.smtp_from):
            parser.error("启用 SMTP 登录时必须设置 DELTA_SMTP_HOST 和 DELTA_SMTP_FROM")
        if bool(args.smtp_username) != bool(args.smtp_password):
            parser.error("DELTA_SMTP_USERNAME 与 DELTA_SMTP_PASSWORD 必须同时设置或同时留空")
    if args.public and not auth_requested:
        print("警告：公共上传已启用但邮箱登录未配置；网页会隐藏直传入口。", file=sys.stderr)

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
    server.auth_enabled = auth_requested
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
    server.auth_code_requests: dict[str, list[float]] = {}
    server.auth_rate_limit_lock = threading.Lock()
    if server.auth_enabled:
        initialize_auth_database()
        backfill_legacy_score_owners_for_known_account()
    if args.public:
        print(f"公共曲库服务已启动：http://0.0.0.0:{args.port}/")
        print("公共上传已启用；部署时请通过 HTTPS 反向代理，并配置 WAF 或限流。")
    else:
        print(f"本地维护服务已启动：http://127.0.0.1:{args.port}/")
        print("仅监听 127.0.0.1；按 Ctrl+C 停止。")
    if server.analytics_enabled:
        print(f"站内匿名分析已启用：/admin/analytics.html（事件保留 {server.analytics_retention_days} 天）")
    if server.auth_enabled:
        source = "本地日志（测试模式）" if server.auth_code_log_only else f"SMTP {server.smtp_host}:{server.smtp_port}"
        print(f"邮箱登录已启用：{source}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地维护服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
