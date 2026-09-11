#!/usr/bin/env python3
"""Import popular, usable PDMX scores into Harmonica Deck.

The generated file is a small, browser-ready JavaScript data file.  PDMX is
distributed as bulk archives, so this script intentionally keeps downloading
and conversion outside the static web page.

Typical workflow:

    python3 tools/import_pdmx.py \
      --csv /path/to/PDMX.csv \
      --mxl-dir /path/to/PDMX \
      --output data/pdmx-top-1000.js

For the Hugging Face mirror, which bundles the older MusicRender JSON form:

    python3 tools/import_pdmx.py \
      --pdmx-archive /path/to/PDMX.tar.gz \
      --output data/pdmx-top-1000.js

The directory passed to --mxl-dir can be the extracted PDMX directory or the
extracted mxl directory.  The script only selects entries with a usable score,
no license conflict when that PDMX column is available, and a best unique
arrangement.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import io
import json
import math
import re
import sys
import tarfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


PDMX_RECORD = "https://zenodo.org/records/15571083"
CSV_URL = f"{PDMX_RECORD}/files/PDMX.csv?download=1"
MXL_URL = f"{PDMX_RECORD}/files/mxl.tar.gz?download=1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / ".pdmx-cache" / "PDMX.csv"
DEFAULT_MXL_ARCHIVE = ROOT / ".pdmx-cache" / "mxl.tar.gz"
DEFAULT_OUTPUT = ROOT / "data" / "pdmx-top-1000.js"


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def first_text(row: dict[str, str], *fields: str) -> str:
    for field in fields:
        value = clean_text(row.get(field))
        if value:
            return value
    return ""


def normalise_key(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def popularity_score(row: dict[str, str]) -> float:
    """Rank using PDMX engagement metadata, with a long-tail-safe score."""

    views = math.log1p(max(0.0, number(row.get("n_views"))))
    favorites = math.log1p(max(0.0, number(row.get("n_favorites"))))
    ratings = math.log1p(max(0.0, number(row.get("n_ratings"))))
    rating = min(5.0, max(0.0, number(row.get("rating")))) / 5.0
    return views + favorites * 0.8 + ratings * 0.5 + rating * 0.25


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "HarmonicaDeck-PDMX-Importer/1.0"})
    print(f"Downloading {url}", file=sys.stderr)
    with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if total and downloaded % (16 * 1024 * 1024) < len(chunk):
                print(f"  {downloaded / total:.0%}", file=sys.stderr)
    temporary.replace(destination)


def row_is_usable(row: dict[str, str]) -> bool:
    source = clean_text(row.get("mxl") or row.get("path"))
    if not source or source.upper() in {"N/A", "NA", "NONE", "NULL"}:
        return False
    if "subset:no_license_conflict" in row and not truthy(row["subset:no_license_conflict"]):
        return False
    if "is_best_unique_arrangement" in row and not truthy(row["is_best_unique_arrangement"]):
        return False
    return number(row.get("n_notes"), 0) >= 8


def select_candidates(csv_path: Path, limit: int) -> list[dict[str, str]]:
    # Keep a generous ranked pool because some high-ranking arrangements may
    # be polyphonic or outside the playable harmonica range.
    pool_size = max(limit * 10, 10_000)
    heap: list[tuple[float, int, dict[str, str]]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for index, row in enumerate(reader):
            if not row_is_usable(row):
                continue
            candidate = {
                key: row.get(key, "")
                for key in (
                    "path", "mxl", "title", "song_name", "subtitle", "artist_name", "composer_name",
                    "license", "license_url", "n_views", "n_favorites", "n_ratings", "rating",
                    "n_notes", "n_tracks", "subset:no_license_conflict", "subset:all_valid",
                    "is_best_unique_arrangement",
                )
            }
            score = popularity_score(row)
            item = (score, index, candidate)
            if len(heap) < pool_size:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)
    return [item[2] for item in sorted(heap, key=lambda item: (-item[0], item[1]))]


def normalise_member_path(value: str) -> str:
    value = value.replace("\\", "/").lstrip("./")
    return value.removeprefix("PDMX/")


def extract_archive_member(archive: Path, names: set[str], destination: Path) -> None:
    wanted = {normalise_member_path(name) for name in names}
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not member.isfile() or normalise_member_path(member.name) not in wanted:
                continue
            extracted = bundle.extractfile(member)
            if extracted is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(extracted.read())
            return
    raise FileNotFoundError(f"归档中没有找到 {', '.join(sorted(names))}")


def locate_mxl(root: Path, relative: str) -> Path | None:
    relative = normalise_member_path(relative)
    candidates = [root / relative]
    if relative.startswith("mxl/"):
        candidates.append(root / relative.removeprefix("mxl/"))
    else:
        candidates.append(root / "mxl" / relative)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def xml_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def child(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in list(element) if xml_name(item) == name), None)


def child_text(element: ET.Element, name: str, default: str = "") -> str:
    item = child(element, name)
    return (item.text or "").strip() if item is not None and item.text else default


def descendant(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (item for item in element.iter() if xml_name(item) == name)


def parse_float(value: str | None, default: float = 0.0) -> float:
    try:
        parsed = float(value or "")
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) else default


def load_xml_payload(payload: bytes) -> ET.Element:
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            xml_name_in_zip = None
            try:
                container = ET.fromstring(archive.read("META-INF/container.xml"))
                root_file = next(descendant(container, "rootfile"), None)
                xml_name_in_zip = root_file.attrib.get("full-path") if root_file is not None else None
            except (KeyError, ET.ParseError):
                pass
            if not xml_name_in_zip:
                xml_name_in_zip = next(
                    (name for name in archive.namelist() if name.lower().endswith(".xml") and not name.startswith("META-INF/")),
                    None,
                )
            if not xml_name_in_zip:
                raise ValueError("MXL 中没有找到 MusicXML 文件")
            return ET.fromstring(archive.read(xml_name_in_zip))
    return ET.fromstring(payload)


def parse_tempo(root: ET.Element) -> int:
    for sound in descendant(root, "sound"):
        tempo = parse_float(sound.attrib.get("tempo"), 0)
        if tempo > 0:
            return max(30, min(300, round(tempo)))
    for direction in descendant(root, "direction"):
        for per_minute in descendant(direction, "per-minute"):
            tempo = parse_float(per_minute.text, 0)
            if tempo > 0:
                return max(30, min(300, round(tempo)))
    return 120


def key_name(fifths: int, mode: str) -> str:
    major = {-7: "C♭", -6: "G♭", -5: "D♭", -4: "A♭", -3: "E♭", -2: "B♭", -1: "F", 0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F♯", 7: "C♯"}
    minor = {-7: "A♭m", -6: "E♭m", -5: "B♭m", -4: "Fm", -3: "Cm", -2: "Gm", -1: "Dm", 0: "Am", 1: "Em", 2: "Bm", 3: "F♯m", 4: "C♯m", 5: "G♯m", 6: "D♯m", 7: "A♯m"}
    bounded = max(-7, min(7, fifths))
    return (minor if mode.lower() == "minor" else major)[bounded]


def parse_score_payload(payload: bytes) -> dict[str, Any]:
    root = load_xml_payload(payload)
    tempo = parse_tempo(root)
    first_fifths = 0
    first_mode = "major"
    first_meter = "4/4"
    for attributes in descendant(root, "attributes"):
        key = child(attributes, "key")
        if key is not None:
            try:
                first_fifths = int(child_text(key, "fifths", "0"))
            except ValueError:
                first_fifths = 0
            first_mode = child_text(key, "mode", "major")
        time = child(attributes, "time")
        if time is not None:
            first_meter = f"{child_text(time, 'beats', '4')}/{child_text(time, 'beat-type', '4')}"
        if key is not None or time is not None:
            break

    part_names: dict[str, str] = {}
    part_list = next(descendant(root, "part-list"), None)
    if part_list is not None:
        for score_part in (item for item in list(part_list) if xml_name(item) == "score-part"):
            part_names[score_part.attrib.get("id", "")] = child_text(score_part, "part-name", "")

    candidates: list[tuple[float, int, str, list[dict[str, Any]]]] = []
    for part in descendant(root, "part"):
        events_by_voice: dict[str, list[dict[str, Any]]] = defaultdict(list)
        absolute_measure_start = 0.0
        divisions = 1.0
        measures = [item for item in list(part) if xml_name(item) == "measure"]
        for measure_index, measure in enumerate(measures):
            cursor = 0.0
            max_end = 0.0
            last_start: dict[str, float] = {}
            for element in list(measure):
                tag = xml_name(element)
                if tag == "attributes":
                    parsed_divisions = child_text(element, "divisions", "")
                    if parsed_divisions:
                        divisions = max(1.0, parse_float(parsed_divisions, divisions))
                    continue
                if tag in {"backup", "forward"}:
                    duration = parse_float(child_text(element, "duration", "0")) / max(divisions, 1.0)
                    cursor = max(0.0, cursor - duration) if tag == "backup" else cursor + duration
                    max_end = max(max_end, cursor)
                    continue
                if tag != "note":
                    continue
                duration = parse_float(child_text(element, "duration", "0")) / max(divisions, 1.0)
                if duration <= 0:
                    continue
                voice = child_text(element, "voice", "1") or "1"
                is_chord = child(element, "chord") is not None
                start = last_start.get(voice, cursor) if is_chord else cursor
                pitch_element = child(element, "pitch")
                rest_element = child(element, "rest")
                event: dict[str, Any] | None = None
                if pitch_element is not None:
                    step = child_text(pitch_element, "step", "C").upper()
                    octave = int(parse_float(child_text(pitch_element, "octave", "4"), 4))
                    alter = parse_float(child_text(pitch_element, "alter", "0"), 0)
                    pitch_class = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}.get(step, 0)
                    event = {"kind": "note", "midi": round((octave + 1) * 12 + pitch_class + alter), "duration": duration}
                elif rest_element is not None:
                    event = {"kind": "rest", "duration": duration}
                if event is not None:
                    event.update({"start": absolute_measure_start + start, "bar": measure_index})
                    events_by_voice[voice].append(event)
                if not is_chord:
                    last_start[voice] = start
                    cursor += duration
                max_end = max(max_end, start + duration)
            absolute_measure_start += max_end

        for voice, events in events_by_voice.items():
            pitched = [event for event in events if event["kind"] == "note"]
            if pitched:
                duration_sum = sum(event["duration"] for event in pitched)
                candidates.append((duration_sum, len(pitched), part_names.get(part.attrib.get("id", ""), ""), events))

    if not candidates:
        raise ValueError("没有找到可演奏的有声音符")
    _, _, part_name, events = max(candidates, key=lambda item: (item[0], item[1]))
    events.sort(key=lambda event: (event["start"], 0 if event["kind"] == "note" else 1, -event.get("midi", -1)))

    grouped: list[list[dict[str, Any]]] = []
    for event in events:
        if grouped and abs(grouped[-1][0]["start"] - event["start"]) < 1e-6:
            grouped[-1].append(event)
        else:
            grouped.append([event])

    melody: list[dict[str, Any]] = []
    cursor = 0.0
    for group in grouped:
        start = group[0]["start"]
        if start > cursor + 1e-6:
            melody.append({"kind": "rest", "duration": start - cursor, "bar": group[0]["bar"]})
        notes = [event for event in group if event["kind"] == "note"]
        chosen = max(notes, key=lambda event: event["midi"]) if notes else group[0]
        melody.append({"kind": chosen["kind"], "midi": chosen.get("midi"), "duration": max(event["duration"] for event in group), "bar": chosen["bar"]})
        cursor = max(cursor, start + melody[-1]["duration"])

    pitches = [event["midi"] for event in melody if event["kind"] == "note"]
    if len(pitches) < 8:
        raise ValueError("主旋律音符太少")
    shift = choose_octave_shift(pitches)
    if shift is None:
        raise ValueError("音域超过口琴可播放范围")
    for event in melody:
        if event["kind"] == "note":
            event["midi"] += shift
    return {
        "events": melody,
        "bpm": tempo,
        "meter": first_meter,
        "key": key_name(first_fifths, first_mode),
        "shift": shift,
        "part": clean_text(part_name),
    }


def parse_musicrender_payload(payload: bytes) -> dict[str, Any]:
    data = json.loads(payload)
    resolution = max(1.0, number(data.get("resolution"), 480))
    tempo = 120
    if data.get("tempos"):
        tempo = max(30, min(300, round(number(data["tempos"][0].get("qpm"), 120))))
    key_data = (data.get("key_signatures") or [{}])[0]
    meter_data = (data.get("time_signatures") or [{}])[0]
    fifths = int(number(key_data.get("fifths"), 0))
    mode = clean_text(key_data.get("mode")) or "major"
    meter = f"{int(number(meter_data.get('numerator'), 4))}/{int(number(meter_data.get('denominator'), 4))}"

    candidates: list[tuple[float, int, str, list[dict[str, Any]]]] = []
    for track in data.get("tracks") or []:
        if truthy(track.get("is_drum")):
            continue
        notes: list[dict[str, Any]] = []
        for note in track.get("notes") or []:
            pitch = number(note.get("pitch"), -1)
            duration = number(note.get("duration"), 0) / resolution
            if pitch < 0 or duration <= 0:
                continue
            notes.append({
                "kind": "note",
                "midi": round(pitch),
                "duration": duration,
                "start": number(note.get("time"), 0) / resolution,
                "bar": int(number(note.get("measure"), 0)),
            })
        if notes:
            candidates.append((sum(note["duration"] for note in notes), len(notes), clean_text(track.get("name")), notes))
    if not candidates:
        raise ValueError("JSON 中没有找到可演奏音符")
    _, _, track_name, events = max(candidates, key=lambda item: (item[0], item[1]))
    events.sort(key=lambda event: (event["start"], -event["midi"]))

    grouped: list[list[dict[str, Any]]] = []
    for event in events:
        if grouped and abs(grouped[-1][0]["start"] - event["start"]) < 1e-6:
            grouped[-1].append(event)
        else:
            grouped.append([event])
    melody: list[dict[str, Any]] = []
    cursor = 0.0
    for group in grouped:
        start = group[0]["start"]
        if start > cursor + 1e-6:
            melody.append({"kind": "rest", "duration": start - cursor, "bar": group[0]["bar"]})
        chosen = max(group, key=lambda event: event["midi"])
        melody.append({"kind": "note", "midi": chosen["midi"], "duration": max(event["duration"] for event in group), "bar": chosen["bar"]})
        cursor = max(cursor, start + melody[-1]["duration"])

    pitches = [event["midi"] for event in melody if event["kind"] == "note"]
    if len(pitches) < 8:
        raise ValueError("主旋律音符太少")
    shift = choose_octave_shift(pitches)
    if shift is None:
        raise ValueError("音域超过口琴可播放范围")
    for event in melody:
        if event["kind"] == "note":
            event["midi"] += shift
    return {
        "events": melody,
        "bpm": tempo,
        "meter": meter,
        "key": key_name(fifths, mode),
        "shift": shift,
        "part": track_name,
    }


def parse_score_payload_auto(payload: bytes) -> dict[str, Any]:
    stripped = payload.lstrip()
    if stripped.startswith(b"{"):
        return parse_musicrender_payload(payload)
    return parse_score_payload(payload)


def choose_octave_shift(pitches: list[int]) -> int | None:
    low, high = min(pitches), max(pitches)
    choices = range(-60, 61, 12)
    ranked = sorted(
        choices,
        key=lambda shift: (
            max(0, 48 - (low + shift)) + max(0, (high + shift) - 83),
            abs(((low + shift) + (high + shift)) / 2 - 65.5),
            abs(shift),
        ),
    )
    best = ranked[0]
    return best if 48 <= low + best and high + best <= 83 else None


PITCH_TO_JIANPU = {
    0: ("", "1"), 1: ("#", "1"), 2: ("", "2"), 3: ("#", "2"),
    4: ("", "3"), 5: ("", "4"), 6: ("#", "4"), 7: ("", "5"),
    8: ("#", "5"), 9: ("", "6"), 10: ("#", "6"), 11: ("", "7"),
}


def midi_to_jianpu(midi: int) -> str:
    if not 48 <= midi <= 83:
        raise ValueError(f"音高 {midi} 超出范围")
    accidental, digit = PITCH_TO_JIANPU[midi % 12]
    octave_mark = "," if midi < 60 else ""
    high_mark = "'" if midi >= 72 else ""
    return f"{accidental}{octave_mark}{digit}{high_mark}"


def beat_text(value: float) -> str:
    value = round(value, 4)
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def events_to_jianpu(events: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    current: list[str] = []
    current_bar: int | None = None
    for event in events:
        bar = int(event.get("bar", 0))
        if current_bar is not None and bar != current_bar and current:
            current.append("|")
            lines.append(" ".join(current))
            current = []
        current_bar = bar
        token = "0" if event["kind"] == "rest" else midi_to_jianpu(int(event["midi"]))
        current.append(f"{token}:{beat_text(float(event['duration']))}")
    if current:
        lines.append(" ".join(current) + " |")
    return "\n".join(lines)


def read_payloads(candidates: list[dict[str, str]], mxl_dir: Path | None, archive: Path | None) -> dict[str, bytes]:
    if mxl_dir:
        return {}
    if archive is None:
        return {}
    wanted = {
        normalise_member_path(row.get("mxl") or row.get("path")): (row.get("mxl") or row.get("path"))
        for row in candidates
    }
    payloads: dict[str, bytes] = {}
    print(f"Reading selected MXL files from {archive}", file=sys.stderr)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not member.isfile():
                continue
            name = normalise_member_path(member.name)
            if name not in wanted:
                continue
            extracted = bundle.extractfile(member)
            if extracted is not None:
                payloads[wanted[name]] = extracted.read()
    return payloads


def build_song(row: dict[str, str], payload: bytes, rank: int, score: float) -> dict[str, Any]:
    parsed = parse_score_payload_auto(payload)
    title = first_text(row, "song_name", "title", "subtitle") or f"PDMX 曲目 {rank:04d}"
    composer = first_text(row, "composer_name", "artist_name")
    detail = ["PDMX 热门导入", f"热度 #{rank}", f"{parsed['key']} · {parsed['meter']} · {parsed['bpm']} BPM"]
    if composer:
        detail.append(composer)
    if parsed["shift"]:
        detail.append(f"自动移调 {parsed['shift']:+d}")
    return {
        "title": title,
        "artist": composer or "未署名",
        "sharedBy": "Jiko",
        "key": parsed["key"],
        "meter": parsed["meter"],
        "detail": " · ".join(detail),
        "bpm": parsed["bpm"],
        "jianpu": events_to_jianpu(parsed["events"]),
        "source": "PDMX",
        "pdmxRank": rank,
        "pdmxPopularity": round(score, 4),
        "pdmxLicense": first_text(row, "license"),
        "pdmxLicenseUrl": first_text(row, "license_url"),
        "pdmxPart": parsed["part"],
    }


def write_output(output: Path, songs: list[dict[str, Any]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(songs, ensure_ascii=False, separators=(",", ":"))
    output.write_text(
        "// Generated by tools/import_pdmx.py.\n"
        "globalThis.PDMX_SONGS = " + payload + ";\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 PDMX 热门 MusicXML 曲目导入 Harmonica Deck 简谱曲库")
    parser.add_argument("--csv", type=Path, help="已下载的 PDMX.csv")
    parser.add_argument("--mxl-dir", type=Path, help="已解压的 PDMX 目录或 mxl 目录")
    parser.add_argument("--mxl-archive", type=Path, help="PDMX 的 mxl.tar.gz；脚本只从中读取候选文件")
    parser.add_argument("--pdmx-archive", type=Path, help="包含 PDMX.csv 和 mxl/ 的单一 PDMX.tar.gz 镜像")
    parser.add_argument("--download-csv", action="store_true", help=f"下载 PDMX.csv 到 {DEFAULT_CSV}")
    parser.add_argument("--download-mxl", action="store_true", help=f"下载约 1.9 GB 的 MXL 压缩包到 {DEFAULT_MXL_ARCHIVE}")
    parser.add_argument("--limit", type=int, default=1000, help="导入数量，默认 1000")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"输出 JS 文件，默认 {DEFAULT_OUTPUT}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit 必须大于 0")
    csv_path = args.csv or DEFAULT_CSV
    archive = args.mxl_archive
    if args.pdmx_archive:
        archive = args.pdmx_archive if archive is None else archive
        if not csv_path.exists():
            extract_archive_member(args.pdmx_archive, {"PDMX/PDMX.csv", "PDMX.csv"}, csv_path)
    if args.download_csv and not csv_path.exists():
        download_file(CSV_URL, csv_path)
    if args.download_mxl and archive is None:
        archive = DEFAULT_MXL_ARCHIVE
    if args.download_mxl and not archive.exists():
        download_file(MXL_URL, archive)
    if not csv_path.is_file():
        raise SystemExit(f"找不到 PDMX.csv：{csv_path}\n先下载后运行，或传入 --csv /path/to/PDMX.csv")
    if args.mxl_dir is None and archive is None:
        raise SystemExit("需要 --mxl-dir、--mxl-archive 或 --pdmx-archive 才能读取乐谱内容；仅有 PDMX.csv 只能做元数据筛选。")
    if archive is not None and not archive.is_file():
        raise SystemExit(f"找不到 MXL 压缩包：{archive}")

    candidates = select_candidates(csv_path, args.limit)
    payloads = read_payloads(candidates, args.mxl_dir, archive)
    songs: list[dict[str, Any]] = []
    seen: set[str] = set()
    failures = 0
    failure_samples: list[str] = []
    for candidate in candidates:
        if len(songs) >= args.limit:
            break
        key = normalise_key(first_text(candidate, "song_name", "title", "subtitle"))
        composer = normalise_key(first_text(candidate, "composer_name", "artist_name"))
        dedupe_key = f"{key}|{composer}"
        if dedupe_key in seen:
            continue
        try:
            source = candidate.get("mxl") or candidate.get("path")
            if args.mxl_dir:
                path = locate_mxl(args.mxl_dir, source)
                if path is None:
                    raise FileNotFoundError(source)
                payload = path.read_bytes()
            else:
                payload = payloads.get(source, b"")
                if not payload:
                    raise FileNotFoundError(source)
            score = popularity_score(candidate)
            songs.append(build_song(candidate, payload, len(songs) + 1, score))
            seen.add(dedupe_key)
        except (ET.ParseError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            failures += 1
            if len(failure_samples) < 20:
                failure_samples.append(f"skip {candidate.get('title') or candidate.get('song_name') or source}: {error}")

    if len(songs) < args.limit:
        print(f"警告：只成功转换 {len(songs)} / {args.limit} 首，跳过 {failures} 首。", file=sys.stderr)
    for sample in failure_samples:
        print(sample, file=sys.stderr)
    if failures > len(failure_samples):
        print(f"其余 {failures - len(failure_samples)} 条跳过信息已省略。", file=sys.stderr)
    write_output(args.output, songs)
    print(f"已写入 {len(songs)} 首曲目：{args.output}")
    return 0 if songs else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("已取消")
