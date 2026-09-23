#!/usr/bin/env python3
"""同步 sitemap.xml 的 <lastmod>，让它反映内容的真实最后修改时间。

设计取舍
--------
``lastmod`` 取的是**内容最后变化的时间**，而不是部署时间：

* 优先使用受监控文件的最后一次 git 提交日期；
* 文件存在未提交改动时，视为"今天改过"；
* 不在 git 仓库中时回退到文件 mtime。

这样反复部署而内容未变时 ``lastmod`` 保持不变 —— Google 官方明确说明，
不可信的 ``lastmod`` 会被整体忽略，所以绝不能简单写入当前时间。

用法
----
    python3 tools/update_sitemap_lastmod.py            # 就地更新 sitemap.xml
    python3 tools/update_sitemap_lastmod.py --check    # 只检查（CI / 发布前校验用）
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITEMAP = REPO_ROOT / "sitemap.xml"

# 任何一项变化都意味着页面内容变化，需要刷新 lastmod。
WATCHED_PATHS = ("index.html", "data/community-songs.js", "app.js", "styles.css")

LASTMOD_PATTERN = re.compile(r"<lastmod>[^<]*</lastmod>")


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _has_uncommitted_changes(rel_path: str) -> bool:
    status = _git("status", "--porcelain", "--", rel_path)
    if status is None:
        return False
    return bool(status)


def _last_commit_date(rel_path: str) -> dt.date | None:
    raw = _git("log", "-1", "--format=%cs", "--", rel_path)
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw.splitlines()[0].strip())
    except ValueError:
        return None


def content_last_modified(paths: tuple[str, ...] = WATCHED_PATHS) -> dt.date:
    """取所有受监控路径中最新的一次内容变化日期。"""
    candidates: list[dt.date] = []
    for rel_path in paths:
        absolute = REPO_ROOT / rel_path
        if _has_uncommitted_changes(rel_path):
            candidates.append(dt.date.today())
            continue
        commit_date = _last_commit_date(rel_path)
        if commit_date is not None:
            candidates.append(commit_date)
            continue
        if absolute.exists():
            candidates.append(dt.date.fromtimestamp(absolute.stat().st_mtime))

    if not candidates:
        raise SystemExit("无法确定任何受监控文件的内容修改时间")
    return max(candidates)


def render(sitemap_text: str, last_modified: dt.date) -> str:
    if not LASTMOD_PATTERN.search(sitemap_text):
        raise SystemExit("sitemap.xml 中没有找到 <lastmod> 节点")
    return LASTMOD_PATTERN.sub(f"<lastmod>{last_modified.isoformat()}</lastmod>", sitemap_text, count=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 sitemap.xml 的 lastmod")
    parser.add_argument("--check", action="store_true", help="只检查是否需要更新，不写入")
    parser.add_argument("--sitemap", type=Path, default=SITEMAP)
    args = parser.parse_args()

    current = args.sitemap.read_text(encoding="utf-8")
    last_modified = content_last_modified()
    updated = render(current, last_modified)

    if updated == current:
        print(f"sitemap lastmod 已是最新：{last_modified.isoformat()}")
        return 0

    if args.check:
        print(f"sitemap lastmod 需要更新为 {last_modified.isoformat()}。请运行：python3 tools/update_sitemap_lastmod.py")
        return 1

    args.sitemap.write_text(updated, encoding="utf-8")
    print(f"已把 sitemap.xml lastmod 更新为 {last_modified.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
