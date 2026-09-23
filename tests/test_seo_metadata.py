"""Regression tests for the SEO surface of the single-page site.

The site is one hash-routed URL whose library is fetched at runtime from a
``robots.txt``-disallowed, referer-guarded ``data/community-songs.js``. That
combination used to leave the *served* HTML with no ``<title>`` and no song
content at all, so search engines indexed a bare UI shell.

These tests pin the fix, so it cannot silently regress:

* the served document carries exactly one ``<title>``,
* ``tools/build_seo_metadata.py`` renders song metadata (title / artist /
  sharedBy / key / meter / bpm) into the static HTML, is idempotent, and never
  leaks the playable ``jianpu`` payload or the ``remixCode``,
* ``tools/update_sitemap_lastmod.py`` tracks content changes and is idempotent,
* ``robots.txt`` keeps pages indexable while keeping ``/data/`` closed,
* ``deploy.sh`` runs both builders before packaging and fails fast when the
  library is missing.

Every builder invocation runs against a throwaway copy, so the suite never
mutates the working tree.
"""
import hashlib
import html
import http.server
import json
import re
import socketserver
import subprocess
import sys
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SONG_DATA = ROOT / "data" / "community-songs.js"

SONG_INDEX = re.compile(r"<!-- SEO:SONG_INDEX:START -->(.*?)<!-- SEO:SONG_INDEX:END -->", re.S)
ITEMLIST = re.compile(r"<!-- SEO:ITEMLIST:START -->(.*?)<!-- SEO:ITEMLIST:END -->", re.S)
JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
BANNED = ("jianpu", "remixCode", "analyticsId", "legacyAdminIds")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Silence per-request logging so the test output stays readable."""

    def log_message(self, format, *args):  # noqa: A002 - base class signature
        pass


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block(pattern: re.Pattern, text: str, label: str) -> str:
    """Return the body of a marker-delimited block, failing loudly if absent."""
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"{label} missing from the served document")
    return match.group(1)


def source_songs() -> list:
    match = re.search(r"globalThis\.COMMUNITY_SONGS\s*=\s*(\[.*\])\s*;?\s*$", read(SONG_DATA), re.S)
    if match is None:
        raise AssertionError("data/community-songs.js is not parseable")
    return json.loads(match.group(1))


def run_tool(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class ServedHtmlTests(unittest.TestCase):
    """The bytes a crawl of the static document actually receives."""

    @classmethod
    def setUpClass(cls):
        cls.index = read(ROOT / "index.html")
        cls.songs = source_songs()
        cls.song_index = block(SONG_INDEX, cls.index, "SSR song index")
        cls.itemlist = block(ITEMLIST, cls.index, "ItemList")

    def test_title_is_present_and_unique(self):
        titles = re.findall(r"<title>(.*?)</title>", self.index, re.S)
        self.assertEqual(len(titles), 1, f"expected exactly one <title>, got {len(titles)}")
        self.assertIn("三角洲口琴演奏家", titles[0])
        self.assertIn("三角洲口琴宏", titles[0])
        self.assertLess(self.index.index("<title>"), self.index.index("</head>"))

    def test_favicon_is_declared_and_shipped(self):
        self.assertIn('rel="icon" type="image/svg+xml" href="./assets/favicon.svg"', self.index)
        favicon = read(ROOT / "assets" / "favicon.svg")
        self.assertTrue(favicon.strip().startswith("<svg"))
        # an explicit colour is required: currentColor renders black in a tab bar
        self.assertIn('fill="#008080"', favicon)

    def test_brand_logo_is_inline_svg(self):
        self.assertIn('<span class="brand-mark" aria-hidden="true"><svg', self.index)
        self.assertNotIn("<i></i><i></i>", self.index)

    def test_static_library_index_covers_every_song(self):
        names = re.findall(r'class="seo-song-name">(.*?)</span>', self.song_index, re.S)
        expected = [
            html.escape(str(song.get("title") or "").strip())
            for song in self.songs
            if str(song.get("title") or "").strip()
        ]
        self.assertEqual(names, expected, "static index drifted from the library")

    def test_static_index_is_visible_not_hidden(self):
        # hiding served text to farm keywords is cloaking; it must stay visible
        self.assertNotIn("display:none", self.song_index)
        self.assertNotIn("hidden", self.song_index)

    def test_playable_payload_never_leaks(self):
        for label, body in (("song index", self.song_index), ("item list", self.itemlist)):
            for banned in BANNED:
                self.assertNotIn(banned, body, f"{banned} leaked into the {label}")
        self.assertFalse(
            re.search(r",\d+:\d+\.\d+", self.song_index),
            "jiao-pu note data leaked into the static index",
        )

    def test_itemlist_structured_data_is_valid(self):
        script = JSONLD.search(self.itemlist)
        self.assertIsNotNone(script, "ItemList is not a JSON-LD script")
        payload = json.loads(script.group(1))
        self.assertEqual(payload["@type"], "ItemList")
        self.assertEqual(payload["numberOfItems"], len(self.songs))
        self.assertEqual(len(payload["itemListElement"]), len(self.songs))
        self.assertEqual(payload["itemListElement"][0]["item"]["@type"], "MusicComposition")

    def test_existing_structured_data_survives(self):
        self.assertIn('"@graph"', self.index)
        self.assertIn('"@type": "SoftwareApplication"', self.index)

    def test_document_over_http_carries_the_index(self):
        """Caddy serves index.html verbatim, so assert on the wire bytes too."""
        handler = lambda *a, **kw: QuietHandler(*a, directory=str(ROOT), **kw)
        with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/",
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                self.assertEqual(response.status, 200)
                served = response.read().decode("utf-8", "replace")
            server.shutdown()
        self.assertIn("<title>三角洲口琴演奏家", served)
        self.assertEqual(len(re.findall(r'class="seo-song-name"', served)), len(self.songs))
        self.assertIn("SEO:ITEMLIST:START", served)


class SeoBuilderTests(unittest.TestCase):
    """Both builders must be idempotent and must not touch the working tree."""

    def test_index_builder_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "index.html"
            target.write_bytes((ROOT / "index.html").read_bytes())
            first = run_tool("build_seo_metadata.py", "--index", str(target))
            self.assertEqual(first.returncode, 0, first.stderr)
            once = target.read_bytes()
            second = run_tool("build_seo_metadata.py", "--index", str(target))
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_bytes(), once, "builder is not idempotent")

    def test_index_builder_reports_in_sync(self):
        """--check exits 0 only when the committed HTML already matches the library."""
        self.assertEqual(run_tool("build_seo_metadata.py", "--check").returncode, 0)

    def test_sitemap_builder_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "sitemap.xml"
            target.write_bytes((ROOT / "sitemap.xml").read_bytes())
            self.assertEqual(run_tool("update_sitemap_lastmod.py", "--sitemap", str(target)).returncode, 0)
            once = target.read_bytes()
            self.assertEqual(run_tool("update_sitemap_lastmod.py", "--sitemap", str(target)).returncode, 0)
            self.assertEqual(target.read_bytes(), once, "lastmod writer is not idempotent")

    def test_sitemap_builder_reports_in_sync(self):
        self.assertEqual(run_tool("update_sitemap_lastmod.py", "--check").returncode, 0)

    def test_builders_leave_the_repository_untouched(self):
        watched = [ROOT / "index.html", ROOT / "sitemap.xml"]
        before = [digest(path) for path in watched]
        run_tool("build_seo_metadata.py")
        run_tool("update_sitemap_lastmod.py")
        self.assertEqual([digest(path) for path in watched], before)


class CrawlPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.robots = read(ROOT / "robots.txt")
        cls.sitemap = read(ROOT / "sitemap.xml")

    def test_pages_are_indexable_for_major_engines(self):
        self.assertIn("User-agent: *", self.robots)
        for bot in ("Googlebot", "Bingbot", "Baiduspider"):
            self.assertIn(f"User-agent: {bot}", self.robots)

    def test_raw_library_stays_closed(self):
        self.assertGreaterEqual(self.robots.count("Disallow: /data/"), 4)

    def test_scraper_and_ai_directives_survive(self):
        for bot in ("harmonica-autoplay", "GPTBot", "ClaudeBot", "Google-Extended"):
            self.assertIn(f"User-agent: {bot}", self.robots)

    def test_robots_has_no_stray_lines(self):
        allowed = re.compile(r"^(#|User-agent:|Allow:|Disallow:|Sitemap:)")
        stray = [line for line in self.robots.splitlines() if line.strip() and not allowed.match(line.strip())]
        self.assertEqual(stray, [], f"robots.txt has malformed lines: {stray}")

    def test_sitemap_is_well_formed(self):
        root = ET.fromstring(self.sitemap)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        self.assertEqual([e.text for e in root.findall(".//s:loc", ns)], ["https://jiko-official.top/delta/"])
        lastmods = root.findall(".//s:lastmod", ns)
        self.assertEqual(len(lastmods), 1, "sitemap must declare exactly one <lastmod>")
        lastmod = lastmods[0].text or ""
        self.assertRegex(lastmod, r"^\d{4}-\d{2}-\d{2}$")
        self.assertNotEqual(lastmod, "2026-09-15", "stale lastmod kept from before the fix")

    def test_robots_points_at_the_sitemap(self):
        self.assertIn("Sitemap: https://jiko-official.top/delta/sitemap.xml", self.robots)


class DeployWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deploy = read(ROOT / "deploy.sh")

    def test_script_parses(self):
        result = subprocess.run(["bash", "-n", str(ROOT / "deploy.sh")], capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_builders_run_before_packaging(self):
        pack = self.deploy.index("[2/5] 正在打包项目")
        for script in ("build_seo_metadata.py", "update_sitemap_lastmod.py"):
            self.assertIn(script, self.deploy)
            self.assertLess(self.deploy.index(script), pack, f"{script} runs after the tarball is built")

    def test_missing_library_aborts_the_deploy(self):
        self.assertIn("无法生成 SEO 曲库索引，已停止部署", self.deploy)

    def test_steps_are_numbered_consistently(self):
        for index in range(6):
            self.assertIn(f"[{index}/5]", self.deploy)


if __name__ == "__main__":
    unittest.main()
