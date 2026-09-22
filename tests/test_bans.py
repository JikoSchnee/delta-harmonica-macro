import importlib.util
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_library_server", ROOT / "tools" / "local_library_server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class BanTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE account_bans (
                account_id TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                banned_at INTEGER NOT NULL,
                expires_at INTEGER
            );
            CREATE TABLE ip_bans (
                ip TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                banned_at INTEGER NOT NULL,
                expires_at INTEGER
            );
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
        """)

    def tearDown(self):
        self.connection.close()

    def test_account_ban_can_be_set_checked_and_cleared(self):
        self.assertFalse(SERVER.is_account_banned(self.connection, "acct", now=100))
        SERVER.set_account_ban(self.connection, "acct", "abuse", now=100)
        self.assertTrue(SERVER.is_account_banned(self.connection, "acct", now=101))
        SERVER.clear_account_ban(self.connection, "acct")
        self.assertFalse(SERVER.is_account_banned(self.connection, "acct", now=102))

    def test_expired_account_and_ip_bans_are_inactive(self):
        SERVER.set_account_ban(self.connection, "acct", "temporary", now=100, expires_at=200)
        SERVER.set_ip_ban(self.connection, "203.0.113.8", "temporary", now=100, expires_at=200)
        self.assertTrue(SERVER.is_account_banned(self.connection, "acct", now=199))
        self.assertFalse(SERVER.is_account_banned(self.connection, "acct", now=200))
        self.assertTrue(SERVER.is_ip_banned(self.connection, "203.0.113.8", now=199))
        self.assertFalse(SERVER.is_ip_banned(self.connection, "203.0.113.8", now=200))

    def test_ip_ban_rejects_invalid_address(self):
        with self.assertRaises(ValueError):
            SERVER.set_ip_ban(self.connection, "not-an-ip", "bad", now=100)


if __name__ == "__main__":
    unittest.main()
