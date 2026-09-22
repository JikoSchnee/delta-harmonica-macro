"""Regression tests for the account↔IP observations behind the console's 高级模式.

The admin console can only ban "the IP of this user" if the server actually
records which IPs an account uses; before this the IP was read for the ban
check and then thrown away. These tests pin both halves: the throttled write
path and the advanced user catalog (full email + IP list, opt-in only).
"""
import importlib.util
import sqlite3
import sys
import threading
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location("local_library_server", TOOLS / "local_library_server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class AccountIpObservationTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE account_ips (
                account_id TEXT NOT NULL,
                ip TEXT NOT NULL,
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                hits INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account_id, ip)
            );
        """)
        SERVER.reset_account_ip_throttle()

    def tearDown(self):
        self.connection.close()
        SERVER.reset_account_ip_throttle()

    def rows(self):
        return [dict(row) for row in self.connection.execute(
            "SELECT account_id, ip, first_seen_at, last_seen_at, hits FROM account_ips ORDER BY ip"
        ).fetchall()]

    def test_first_observation_is_persisted_and_repeat_is_throttled(self):
        self.assertTrue(SERVER.record_account_ip(self.connection, "acct", "203.0.113.7", now=1_000))
        # Same pair inside the write window: skipped, so hits stays at 1.
        self.assertFalse(SERVER.record_account_ip(self.connection, "acct", "203.0.113.7", now=1_000 + SERVER.ACCOUNT_IP_WRITE_INTERVAL_SECONDS - 1))
        self.assertEqual(self.rows(), [{
            "account_id": "acct", "ip": "203.0.113.7", "first_seen_at": 1_000, "last_seen_at": 1_000, "hits": 1,
        }])

    def test_same_pair_after_the_window_bumps_last_seen_and_hits(self):
        SERVER.record_account_ip(self.connection, "acct", "203.0.113.7", now=1_000)
        later = 1_000 + SERVER.ACCOUNT_IP_WRITE_INTERVAL_SECONDS
        self.assertTrue(SERVER.record_account_ip(self.connection, "acct", "203.0.113.7", now=later))
        row = self.rows()[0]
        self.assertEqual((row["first_seen_at"], row["last_seen_at"], row["hits"]), (1_000, later, 2))

    def test_distinct_ips_are_tracked_separately_and_ipv6_is_normalized(self):
        SERVER.record_account_ip(self.connection, "acct", "203.0.113.7", now=1_000)
        SERVER.record_account_ip(self.connection, "acct", "2001:0db8::1", now=1_000)
        SERVER.record_account_ip(self.connection, "other", "203.0.113.7", now=1_000)
        self.assertEqual(
            [(row["account_id"], row["ip"]) for row in self.rows()],
            [("acct", "2001:db8::1"), ("acct", "203.0.113.7"), ("other", "203.0.113.7")],
        )

    def test_invalid_address_is_ignored(self):
        self.assertFalse(SERVER.record_account_ip(self.connection, "acct", "not-an-ip", now=1_000))
        self.assertEqual(self.rows(), [])

    def test_expired_observations_are_pruned(self):
        SERVER.record_account_ip(self.connection, "acct", "203.0.113.7", now=1_000)
        stale = 1_000 + SERVER.ACCOUNT_IP_RETENTION_SECONDS + SERVER.ACCOUNT_IP_PRUNE_INTERVAL_SECONDS
        SERVER.record_account_ip(self.connection, "acct", "198.51.100.9", now=stale)
        self.assertEqual([row["ip"] for row in self.rows()], ["198.51.100.9"])


class AdminAdvancedCatalogTests(unittest.TestCase):
    """Drive the real endpoint over HTTP so `advanced=1` stays opt-in."""

    def setUp(self):
        self._temp = TemporaryDirectory()
        self._original_database = SERVER.AUTH_DATABASE
        SERVER.AUTH_DATABASE = Path(self._temp.name) / "auth.sqlite3"
        SERVER.reset_auth_schema_guard()
        SERVER.reset_account_ip_throttle()
        SERVER.initialize_auth_database()
        handler = lambda *a, **k: SERVER.LocalLibraryRequestHandler(*a, directory=str(ROOT), **k)
        self.server = SERVER.BoundedThreadingHTTPServer(("127.0.0.1", 0), handler)
        server = self.server
        server.public_library = False
        server.trust_proxy = True
        server.analytics_admin_token = "advanced-mode-test-token"
        server.analytics_enabled = True
        server.analytics_retention_days = 90
        server.public_uploads = {}
        server.upload_rate_limit_lock = threading.Lock()
        server.auth_enabled = True
        server.auth_secret = "advanced-mode-test-secret"
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            connection.execute(
                "INSERT INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("acct-1", "someone@example.com", "tester", SERVER.now_timestamp(), SERVER.now_timestamp()),
            )
            connection.execute(
                "INSERT INTO account_ips(account_id, ip, first_seen_at, last_seen_at, hits) VALUES (?, ?, ?, ?, ?)",
                ("acct-1", "203.0.113.7", SERVER.now_timestamp() - 60, SERVER.now_timestamp(), 3),
            )
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        SERVER.reset_auth_schema_guard()
        SERVER.reset_account_ip_throttle()
        SERVER.AUTH_DATABASE = self._original_database
        self._temp.cleanup()

    def fetch(self, query):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}/api/admin/users?{query}",
            headers={"Authorization": "Bearer advanced-mode-test-token", "X-Forwarded-For": "198.51.100.23"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return SERVER.json.loads(response.read().decode("utf-8"))

    def test_default_catalog_stays_masked_and_ip_free(self):
        body = self.fetch("q=")
        self.assertFalse(body["advanced"])
        user = body["users"][0]
        self.assertEqual(user["email"], "so***@example.com")
        self.assertNotIn("emailFull", user)
        self.assertNotIn("ips", user)

    def test_advanced_catalog_returns_full_email_and_ip_history(self):
        body = self.fetch("advanced=1")
        self.assertTrue(body["advanced"])
        user = body["users"][0]
        self.assertEqual(user["email"], "so***@example.com")
        self.assertEqual(user["emailFull"], "someone@example.com")
        self.assertEqual([(entry["ip"], entry["hits"], entry["banned"]) for entry in user["ips"]], [("203.0.113.7", 3, False)])

    def test_advanced_catalog_can_be_searched_by_ip(self):
        body = self.fetch("advanced=1&q=203.0.113.7")
        self.assertEqual([user["userId"] for user in body["users"]], ["tester"])
        self.assertEqual(self.fetch("advanced=1&q=198.51.100.99")["users"], [])


if __name__ == "__main__":
    unittest.main()
