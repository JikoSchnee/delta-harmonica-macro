#!/usr/bin/env python3
"""把曲库元数据静态渲染（SSR）进 index.html，供搜索引擎与无脚本环境索引。

背景
----
曲库内容原先完全依赖 JS 运行时 fetch ``data/community-songs.js``（该文件受
服务端 Referer 访问控制保护，且被 robots.txt 屏蔽），因此搜索引擎看到的首页
只有 UI 骨架，没有任何曲目信息，导致"三角洲口琴"这类查询无法命中。

本脚本在构建时把**仅用于索引的元数据**写进静态 HTML，实现方案 A：
既让搜索引擎拿到内容，又不暴露可演奏的宏数据。

输出范围（严格限定）
--------------------
    title     曲名
    artist    作者
    sharedBy  贡献人
    key       调式
    meter     拍号
    bpm       速度

**绝不输出** ``jianpu``（可演奏简谱数据）、``remixCode``（改曲码）等任何可以
还原出宏文件的数据。原始 ``data/community-songs.js`` 继续受访问控制保护。

幂等性
------
注入内容用 ``<!-- SEO:SONG_INDEX:START -->`` / ``<!-- SEO:SONG_INDEX:END -->``
与 ``<!-- SEO:ITEMLIST:START -->`` / ``<!-- SEO:ITEMLIST:END -->`` 包裹，
重复运行只替换标记之间的内容，不会重复堆叠。

用法
----
    python3 tools/build_seo_metadata.py            # 就地更新 index.html
    python3 tools/build_seo_metadata.py --check    # 只检查是否需要更新（CI 用）
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"
SONG_DATA = REPO_ROOT / "data" / "community-songs.js"

SONG_INDEX_START = "<!-- SEO:SONG_INDEX:START -->"
SONG_INDEX_END = "<!-- SEO:SONG_INDEX:END -->"
ITEMLIST_START = "<!-- SEO:ITEMLIST:START -->"
ITEMLIST_END = "<!-- SEO:ITEMLIST:END -->"

SITE_URL = "https://jiko-official.top/delta/"

# songGrid 的空容器形态（首次 SSR 前的原始状态）。
SONG_GRID_EMPTY = '<div class="song-grid library-grid" id="songGrid" aria-label="曲库列表"></div>'
# songGrid 所在行的缩进。
GRID_INDENT = "          "
# head 中的插入锚点：ItemList 结构化数据放在字体预连接之前。
HEAD_ANCHOR = '    <link rel="preconnect" href="https://fonts.googleapis.com" />'


def load_songs(path: Path) -> list[dict]:
    """从 ``globalThis.COMMUNITY_SONGS = [...]`` 里取出曲目数组。"""
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"globalThis\.COMMUNITY_SONGS\s*=\s*(\[.*\])\s*;?\s*$", raw, re.S | re.M)
    if not match:
        raise SystemExit(f"无法在 {path} 中定位 COMMUNITY_SONGS 数组")
    songs = json.loads(match.group(1))
    if not isinstance(songs, list):
        raise SystemExit("COMMUNITY_SONGS 不是数组")
    return songs


def song_fields(song: dict) -> tuple[str, str, str, str, str, str]:
    """只取允许公开索引的六个字段。"""
    title = str(song.get("title") or "").strip()
    artist = str(song.get("artist") or "").strip()
    shared_by = str(song.get("sharedBy") or "").strip()
    key = str(song.get("key") or "").strip()
    meter = str(song.get("meter") or "").strip()
    bpm = str(song.get("bpm") or "").strip()
    return title, artist, shared_by, key, meter, bpm


def render_song_index(songs: list[dict], indent: str) -> str:
    """生成可见的静态曲库索引列表（语义化 HTML，非隐藏内容）。"""
    rows: list[str] = []
    for song in songs:
        title, artist, shared_by, key, meter, bpm = song_fields(song)
        if not title:
            continue
        meta_bits = [
            bit
            for bit in (
                artist,
                key,
                meter,
                f"{bpm} BPM" if bpm else "",
                f"贡献 {shared_by}" if shared_by else "",
            )
            if bit
        ]
        rows.append(
            f"{indent}    <li>"
            f'<span class="seo-song-name">{html.escape(title)}</span>'
            f'<span class="seo-song-meta">{html.escape(" · ".join(meta_bits))}</span>'
            "</li>"
        )

    return "\n".join(
        [
            f"{indent}{SONG_INDEX_START}",
            f'{indent}<section class="seo-song-index" aria-label="曲库索引">',
            f'{indent}  <h3 class="seo-song-index-title">曲库索引 · 共 {len(rows)} 首</h3>',
            f'{indent}  <ul class="seo-song-index-list">',
            *rows,
            f"{indent}  </ul>",
            f'{indent}  <p class="seo-song-index-note">上方为静态曲库索引，便于搜索与无脚本环境查看；'
            "可演奏谱面请在页面内的曲库板块打开。</p>",
            f"{indent}</section>",
            f"{indent}{SONG_INDEX_END}",
        ]
    )


def render_itemlist(songs: list[dict]) -> str:
    """生成 ItemList 结构化数据（只含曲名与作者）。"""
    items: list[dict] = []
    position = 0
    for song in songs:
        title, artist, _shared_by, _key, _meter, _bpm = song_fields(song)
        if not title:
            continue
        position += 1
        item: dict = {"@type": "ListItem", "position": position, "name": title}
        if artist:
            item["item"] = {
                "@type": "MusicComposition",
                "name": title,
                "composer": {"@type": "Person", "name": artist},
            }
        items.append(item)

    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "三角洲口琴曲库",
        "description": "三角洲行动口琴数字简谱曲库索引，含曲名、作者与调式信息。",
        "url": SITE_URL,
        "numberOfItems": len(items),
        "itemListElement": items,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    indented = "\n".join("      " + line for line in body.split("\n"))
    return "\n".join(
        [
            f"    {ITEMLIST_START}",
            '    <script type="application/ld+json">',
            indented,
            "    </script>",
            f"    {ITEMLIST_END}",
        ]
    )


def _block_pattern(start: str, end: str) -> re.Pattern[str]:
    """匹配标记区块，并**连同区块前的行首缩进一起吃掉**。

    若不吃掉前导缩进，替换文本自带的缩进会与原缩进叠加，
    导致脚本每运行一次缩进就加深一层（非幂等）。
    """
    return re.compile(r"[ \t]*" + re.escape(start) + r".*?" + re.escape(end), re.S)


def inject_song_index(source: str, song_index: str) -> str:
    """把曲库索引放进 #songGrid 内部；已存在标记时原地替换。"""
    pattern = _block_pattern(SONG_INDEX_START, SONG_INDEX_END)
    if pattern.search(source):
        return pattern.sub(lambda _m: song_index, source, count=1)

    if source.count(SONG_GRID_EMPTY) != 1:
        raise SystemExit(f"找不到唯一的空 #songGrid 容器（匹配 {source.count(SONG_GRID_EMPTY)} 次）")
    replacement = (
        f'{GRID_INDENT}<div class="song-grid library-grid" id="songGrid" aria-label="曲库列表">\n'
        f"{song_index}\n"
        f"{GRID_INDENT}</div>"
    )
    return source.replace(SONG_GRID_EMPTY, replacement, 1)


def inject_itemlist(source: str, itemlist: str) -> str:
    """把 ItemList 结构化数据放进 head；已存在标记时原地替换。"""
    pattern = _block_pattern(ITEMLIST_START, ITEMLIST_END)
    if pattern.search(source):
        return pattern.sub(lambda _m: itemlist, source, count=1)

    if source.count(HEAD_ANCHOR) != 1:
        raise SystemExit(f"head 插入锚点不唯一（{source.count(HEAD_ANCHOR)} 次）")
    return source.replace(HEAD_ANCHOR, itemlist + "\n" + HEAD_ANCHOR, 1)


def build(index_path: Path = INDEX_HTML, data_path: Path = SONG_DATA) -> str:
    songs = load_songs(data_path)
    source = index_path.read_text(encoding="utf-8")
    source = inject_song_index(source, render_song_index(songs, GRID_INDENT + "  "))
    source = inject_itemlist(source, render_itemlist(songs))
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description="把曲库元数据 SSR 进 index.html")
    parser.add_argument("--check", action="store_true", help="只检查是否需要更新，不写入")
    parser.add_argument("--index", type=Path, default=INDEX_HTML)
    parser.add_argument("--data", type=Path, default=SONG_DATA)
    args = parser.parse_args()

    updated = build(args.index, args.data)
    current = args.index.read_text(encoding="utf-8")

    if updated == current:
        print("SEO 元数据已是最新，无需更新。")
        return 0

    songs = load_songs(args.data)
    if args.check:
        print(f"SEO 元数据需要更新（曲库 {len(songs)} 首）。请运行：python3 tools/build_seo_metadata.py")
        return 1

    args.index.write_text(updated, encoding="utf-8")
    print(f"已把 {len(songs)} 首曲目的元数据 SSR 进 {args.index.relative_to(REPO_ROOT)}")
    print("输出字段：曲名 / 作者 / 贡献人 / 调式 / 拍号 / BPM（不含 jianpu 与 remixCode）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
