#!/usr/bin/env python3
"""Validate Harmonica Deck community score packages and optionally build a browser library.

Examples:
  python3 tools/import_community_scores.py submissions --report review.json
  python3 tools/import_community_scores.py approved/*.deltamusic \
    --report review.json --output data/community-songs.js
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


FORMAT = "delta-music"
LEGACY_FORMAT = "harmonica-deck-score"
VERSION = 1
KEY_PATTERN = re.compile(r"^(?:1=)?[A-G](?:[#b♯♭])?$", re.IGNORECASE)
METER_PATTERN = re.compile(r"^(\d{1,2})/(\d{1,2})$")
TOKEN_PATTERN = re.compile(r"^(?:[#b♯♭]?[,]?(?:0|[1-7])['']?_{0,2}\.*-*(?::\d+(?:\.\d+)?)?~?|[-~]+)$")
MAX_DISPLAY_URL_LENGTH = 2048


def compact_text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}必须是文本")
    text = value.strip()
    if not text:
        raise ValueError(f"缺少{field}")
    if len(text) > limit:
        raise ValueError(f"{field}不能超过 {limit} 个字符")
    return text


def validate_jianpu(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("缺少简谱内容")
    found_note = False
    for token in re.findall(r"\|\|:|:\|\||\|+|[^\s|]+", value):
        if token in {"|", "||", "||:", ":||", ":", "(", ")", "[", "]", "{", "}"}:
            continue
        clean = token.strip("()[]{}")
        if not clean:
            continue
        if not TOKEN_PATTERN.fullmatch(clean):
            raise ValueError(f"简谱包含无法识别的符号：{token}")
        if re.search(r"[0-7]", clean):
            found_note = True
    if not found_note:
        raise ValueError("简谱没有可演奏音符")
    return value.strip()


def validate_display_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("展示视频链接必须是文本")
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_DISPLAY_URL_LENGTH:
        raise ValueError(f"展示视频链接不能超过 {MAX_DISPLAY_URL_LENGTH} 个字符")
    if any(character.isspace() for character in text):
        raise ValueError("展示视频链接必须是有效的 HTTPS 地址")
    try:
        parsed = urlparse(text)
        _ = parsed.port
    except ValueError as error:
        raise ValueError("展示视频链接必须是有效的 HTTPS 地址") from error
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("展示视频链接必须是有效的 HTTPS 地址")
    return text


def validate_package(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("JSON 根节点必须是对象")
    if payload.get("format") not in {FORMAT, LEGACY_FORMAT}:
        raise ValueError("不是 Delta Music 谱子文件")
    if payload.get("version") != VERSION:
        raise ValueError(f"不支持的文件版本：{payload.get('version')!r}")
    key = compact_text(payload.get("key"), "调号", 8)
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("调号应为 1=C、C、F♯ 或 A♭")
    meter = compact_text(payload.get("meter"), "拍号", 5)
    match = METER_PATTERN.fullmatch(meter)
    if not match or int(match.group(1)) < 1 or int(match.group(2)) not in {1, 2, 4, 8, 16}:
        raise ValueError("拍号应为例如 4/4 或 6/8")
    bpm = payload.get("bpm")
    if isinstance(bpm, bool) or not isinstance(bpm, int) or not 30 <= bpm <= 300:
        raise ValueError("BPM 必须是 30 到 300 的整数")
    score = {
        "title": compact_text(payload.get("title"), "歌名", 48),
        "artist": compact_text(payload.get("artist"), "歌手/作者", 64),
        "sharedBy": compact_text(payload.get("sharedBy"), "共享人", 48),
        "key": key,
        "meter": meter,
        "bpm": bpm,
        "jianpu": validate_jianpu(payload.get("jianpu")),
        "source": "社区投稿",
    }
    display_url = validate_display_url(payload.get("displayUrl"))
    if display_url:
        score["displayUrl"] = display_url
    return score


def paths_from_inputs(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        if item.is_dir():
            paths.extend(sorted([*item.rglob("*.deltamusic"), *item.rglob("*.harmonica-score.json")]))
        elif item.is_file():
            paths.append(item)
        else:
            print(f"跳过不存在的路径：{item}", file=sys.stderr)
    return paths


def dedupe_key(song: dict[str, Any]) -> str:
    return "|".join(
        str(song[field]).casefold().strip()
        for field in ("title", "artist", "sharedBy")
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_library(path: Path, songs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(songs, ensure_ascii=False, separators=(",", ":"))
    path.write_text(
        "// Reviewed community submissions. Generated with tools/import_community_scores.py.\n"
        f"globalThis.COMMUNITY_SONGS = {payload};\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Harmonica Deck 社区谱子，并生成审核后的曲库文件")
    parser.add_argument("inputs", nargs="+", type=Path, help="投稿文件或包含投稿文件的目录")
    parser.add_argument("--report", type=Path, required=True, help="写入审核报告 JSON")
    parser.add_argument("--output", type=Path, help="确认合格后写入浏览器曲库 JS；省略时只生成报告")
    args = parser.parse_args()

    accepted: list[tuple[Path, dict[str, Any]]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths_from_inputs(args.inputs):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            song = validate_package(payload)
            key = dedupe_key(song)
            if key in seen:
                raise ValueError("与本批次另一首曲目的歌名、歌手/作者和共享人均相同，请人工审核后保留一个版本")
            seen.add(key)
            accepted.append((path, song))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            rejected.append({"file": str(path), "reason": str(error)})

    report = {
        "format": "harmonica-deck-community-review",
        "version": 1,
        "accepted": [{"file": str(path), **song} for path, song in accepted],
        "rejected": rejected,
        "summary": {"accepted": len(accepted), "rejected": len(rejected)},
    }
    write_json(args.report, report)
    if args.output:
        write_library(args.output, [song for _, song in accepted])

    print(f"审核完成：通过 {len(accepted)} 首，拒绝 {len(rejected)} 首。报告：{args.report}")
    if args.output:
        print(f"已写入社区曲库：{args.output}")
    return 0 if not rejected else 1


if __name__ == "__main__":
    raise SystemExit(main())
