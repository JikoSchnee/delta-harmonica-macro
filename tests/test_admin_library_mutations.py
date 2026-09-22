import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_library_server", ROOT / "tools" / "local_library_server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class AdminLibraryMutationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.source = root / "data" / "community-scores"
        self.source.mkdir(parents=True)
        self.library = root / "data" / "community-songs.js"
        self.database = root / "data" / "auth.sqlite3"
        self.original = {
            "root": SERVER.REPOSITORY_ROOT,
            "source": SERVER.SOURCE_DIRECTORY,
            "library": SERVER.LIBRARY_OUTPUT,
            "database": SERVER.AUTH_DATABASE,
        }
        SERVER.REPOSITORY_ROOT = root
        SERVER.SOURCE_DIRECTORY = self.source
        SERVER.LIBRARY_OUTPUT = self.library
        SERVER.AUTH_DATABASE = self.database
        self.code = "0123456789ABCDEFFEDCB"
        self.path = self.source / "song.deltamusic"
        self.path.write_text(json.dumps({
            "format": SERVER.FORMAT,
            "version": SERVER.VERSION,
            "title": "测试曲目",
            "artist": "测试作者",
            "sharedBy": "tester",
            "key": "1=C",
            "meter": "4/4",
            "bpm": 120,
            "jianpu": "1 2 3",
            "remixCode": self.code,
            "declaration": "原声明",
        }), encoding="utf-8")

    def tearDown(self):
        SERVER.REPOSITORY_ROOT = self.original["root"]
        SERVER.SOURCE_DIRECTORY = self.original["source"]
        SERVER.LIBRARY_OUTPUT = self.original["library"]
        SERVER.AUTH_DATABASE = self.original["database"]
        self.tempdir.cleanup()

    def test_admin_can_update_declaration(self):
        SERVER.admin_update_score({"remixCode": self.code, "declaration": "修改后的声明"})
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["declaration"], "修改后的声明")

    def test_admin_delete_removes_file_and_related_metadata(self):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            connection.executescript("""
                CREATE TABLE score_owners (
                    remix_code TEXT PRIMARY KEY,
                    score_path TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL
                );
                CREATE TABLE recommended_scores (
                    remix_code TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    shared_by TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE score_unlocks (
                    account_id TEXT NOT NULL,
                    remix_code TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(account_id, remix_code)
                );
                CREATE TABLE author_unlocks (
                    owner_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    remix_code TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(account_id, remix_code)
                );
                INSERT INTO score_owners VALUES ('0123456789ABCDEFFEDCB', 'data/community-scores/song.deltamusic', 'owner');
                INSERT INTO recommended_scores VALUES ('0123456789ABCDEFFEDCB', '测试曲目', '测试作者', 'tester', 1);
                INSERT INTO score_unlocks VALUES ('viewer', '0123456789ABCDEFFEDCB', 1);
                INSERT INTO author_unlocks VALUES ('owner', 'viewer', '0123456789ABCDEFFEDCB', 1);
            """)

        SERVER.admin_delete_score({"remixCode": self.code})
        self.assertFalse(self.path.exists())
        self.assertNotIn(self.code, self.library.read_text(encoding="utf-8"))
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            for table in ("score_owners", "recommended_scores", "score_unlocks", "author_unlocks"):
                self.assertIsNone(connection.execute(f"SELECT 1 FROM {table} WHERE remix_code = ?", (self.code,)).fetchone())


if __name__ == "__main__":
    unittest.main()
