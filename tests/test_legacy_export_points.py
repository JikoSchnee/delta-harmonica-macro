import importlib.util
import sqlite3
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_library_server", ROOT / "tools" / "local_library_server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class LegacyExportPointsTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE accounts (id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
            CREATE TABLE point_migrations (migration_key TEXT PRIMARY KEY, applied_at INTEGER NOT NULL);
            CREATE TABLE point_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                reference TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(account_id, reason, reference)
            );
            INSERT INTO accounts VALUES ('acct-jiko', 'Jiko');
            """
        )
        self.original_db = SERVER.auth_database
        self.original_owned = SERVER.public_owned_scores
        self.original_counts = SERVER.cached_score_export_counts
        self.original_lock = SERVER.AUTH_LOCK
        SERVER.auth_database = lambda: self.connection
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): return False
        SERVER.AUTH_LOCK = Lock()

    def tearDown(self):
        SERVER.auth_database = self.original_db
        SERVER.public_owned_scores = self.original_owned
        SERVER.cached_score_export_counts = self.original_counts
        SERVER.AUTH_LOCK = self.original_lock
        self.connection.close()

    def test_historical_exports_are_granted_once_per_owner(self):
        server = types.SimpleNamespace(analytics_enabled=True, analytics_retention_days=90)
        SERVER.public_owned_scores = lambda enabled: [("Jiko", "SCORE-A"), ("Jiko", "SCORE-B")]
        SERVER.cached_score_export_counts = lambda days: {"SCORE-A": 4, "SCORE-B": 0}

        SERVER.apply_legacy_export_points_migration(server)
        SERVER.apply_legacy_export_points_migration(server)

        row = self.connection.execute(
            "SELECT amount, reason, reference FROM point_ledger"
        ).fetchone()
        self.assertEqual(tuple(row), (4, "legacy_export", "legacy-export-points-v1"))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM point_migrations").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()