import importlib.util
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path

SERVER_PATH = Path(__file__).resolve().parents[1] / "tools" / "local_library_server.py"
_SPEC = importlib.util.spec_from_file_location("local_library_server", SERVER_PATH)
_SERVER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SERVER)
award_daily_login_points = _SERVER.award_daily_login_points



class DailyLoginPointsTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.executescript(
            """
            CREATE TABLE account_notices (
                account_id TEXT NOT NULL,
                notice_key TEXT NOT NULL,
                acknowledged_at INTEGER NOT NULL,
                PRIMARY KEY(account_id, notice_key)
            );
            CREATE TABLE point_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                reference TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(account_id, reason, reference)
            );
            CREATE TABLE score_owners (account_id TEXT NOT NULL);
            CREATE TABLE point_migrations (migration_key TEXT PRIMARY KEY, applied_at INTEGER NOT NULL);
            CREATE TABLE accounts (id TEXT PRIMARY KEY);
            INSERT INTO accounts VALUES ('account-legacy');
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_awards_twenty_points_once_per_utc_day(self):
        first = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
        second = datetime(2026, 9, 22, 23, 0, tzinfo=timezone.utc)
        third = datetime(2026, 9, 23, 0, 1, tzinfo=timezone.utc)

        self.assertTrue(award_daily_login_points(self.connection, "account-1", first))
        self.assertFalse(award_daily_login_points(self.connection, "account-1", second))
        self.assertTrue(award_daily_login_points(self.connection, "account-1", third))

        rows = self.connection.execute(
            "SELECT amount, reason, reference FROM point_ledger ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, [
            (20, "daily_login", "2026-09-22"),
            (20, "daily_login", "2026-09-23"),
        ])


    def test_accounts_are_isolated(self):
        today = datetime(2026, 9, 22, tzinfo=timezone.utc)
        self.assertTrue(award_daily_login_points(self.connection, "account-1", today))
        self.assertTrue(award_daily_login_points(self.connection, "account-2", today))


if __name__ == "__main__":
    unittest.main()

