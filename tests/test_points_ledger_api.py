"""Regression tests for the points-ledger endpoint.

The ledger used to be dead code: `/api/points/ledger` was handled inside a block
guarded by a route set that did not contain it, so the request fell through to
the static-file handler and returned 404. The frontend caught that error and
rendered "暂无积分记录", which made it look like no points were ever granted.

These tests drive the endpoint over real HTTP (in-process server, temporary auth
database) so the route can never silently disappear again.
"""
import importlib.util
import json
import sys
import threading
import unittest
import urllib.error
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


class PointsLedgerApiTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self._original_db = SERVER.AUTH_DATABASE
        SERVER.AUTH_DATABASE = Path(self._temp.name) / "auth.sqlite3"
        SERVER.reset_auth_schema_guard()
        SERVER.initialize_auth_database()
        handler = lambda *a, **k: SERVER.LocalLibraryRequestHandler(*a, directory=str(ROOT), **k)
        self.server = SERVER.BoundedThreadingHTTPServer(("127.0.0.1", 0), handler)
        server = self.server
        server.public_library = True
        server.trust_proxy = False
        server.analytics_admin_token = ""
        server.analytics_enabled = False
        server.analytics_retention_days = 90
        server.public_uploads = {}
        server.upload_rate_limit_lock = threading.Lock()
        server.auth_enabled = True
        server.email_auth_enabled = False
        server.auth_secret = "ledger-test-secret"
        server.smtp_host = server.smtp_from = ""
        server.smtp_port = 587
        server.smtp_username = server.smtp_password = ""
        server.smtp_ssl = False
        server.smtp_starttls = True
        server.auth_code_log_only = True
        server.fixed_test_login_email = ""
        server.fixed_test_login_code = ""
        server.insecure_auth_cookies = True
        server.oauth_providers = {}
        server.github_oauth = None
        server.oauth_states = {}
        server.oauth_state_lock = threading.Lock()
        server.auth_code_requests = {}
        server.auth_rate_limit_lock = threading.Lock()
        server.auth_mail_dispatcher = None
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            connection.execute(
                "INSERT INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("ledger-account", "ledger@example.invalid", "ledger", 1, 1),
            )
        self.token = SERVER.issue_session(server, "ledger-account")
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        SERVER.reset_auth_schema_guard()
        SERVER.AUTH_DATABASE = self._original_db
        self._temp.cleanup()

    def fetch_ledger(self, cookie=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/points/ledger",
            headers={"Cookie": cookie} if cookie else {},
        )
        opener = urllib.request.build_opener(NoRedirect)
        try:
            response = opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        body = response.read().decode("utf-8", "replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        return response.status, payload

    def cookie(self):
        return f"{SERVER.AUTH_COOKIE_NAME}={self.token}"

    def award(self, amount, reason, reference):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            SERVER.award_points(connection, "ledger-account", amount, reason, reference)

    def test_ledger_endpoint_is_reachable_and_lists_awards(self):
        status, payload = self.fetch_ledger(self.cookie())
        self.assertEqual(status, 200, "ledger endpoint must not fall through to the static handler")
        self.assertIsInstance(payload, dict)
        reasons = {entry["reason"] for entry in payload["entries"]}
        # issue_session awards the daily login, ensure_initial_points the signup bonus.
        self.assertIn("daily_login", reasons)
        self.assertIn("register", reasons)

    def test_ledger_shows_gains_and_spends_with_amounts(self):
        self.award(500, "github_star", "4242")
        self.award(-10, "unlock", "SABCDEF01")
        status, payload = self.fetch_ledger(self.cookie())
        self.assertEqual(status, 200)
        amounts = {entry["reason"]: entry["amount"] for entry in payload["entries"]}
        self.assertEqual(amounts["github_star"], 500)
        self.assertEqual(amounts["unlock"], -10)
        self.assertEqual(amounts["daily_login"], SERVER.POINT_RULES["daily_login"])

    def test_ledger_requires_a_session(self):
        status, payload = self.fetch_ledger()
        self.assertEqual(status, 401)
        self.assertIn("error", payload or {})

    def test_ledger_is_newest_first_and_bounded(self):
        for index in range(5):
            self.award(1, "referral", f"ref-{index}")
        status, payload = self.fetch_ledger(self.cookie())
        self.assertEqual(status, 200)
        entries = payload["entries"]
        self.assertLessEqual(len(entries), 100)
        stamps = [entry["created_at"] for entry in entries]
        self.assertEqual(stamps, sorted(stamps, reverse=True), "ledger must be newest first")
        # The signup bonus is granted lazily while reading, so it can legitimately
        # be the newest row; what matters is that the awards are all listed.
        self.assertEqual(sum(1 for entry in entries if entry["reason"] == "referral"), 5)

    def test_route_set_includes_the_ledger_path(self):
        """Guard the exact bug: the handler must match before any fallback runs."""
        source = (TOOLS / "local_library_server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/points/ledger"', source)
        self.assertIn('if path == "/api/points/ledger":', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
