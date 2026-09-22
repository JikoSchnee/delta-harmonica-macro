"""Regression tests for the per-unlock author reward.

The author reward used to be paid in batches of ten valid unlocks (ten points
each), so an author's point history stayed empty until ten different accounts had
unlocked one of their scores, and `/api/points` exposed a "progress toward the
next ten unlocks" counter that the frontend rendered as `X / 10`.

Every valid unlock now credits one point immediately, with the ledger reference
recording the (unlocker, score) pair so a replayed or concurrent request can
never credit the same unlock twice.

These tests drive `/api/points/unlock` and `/api/points` over real HTTP against a
sandboxed score library and a temporary auth database, so the rule cannot
silently drift back to the batched behaviour.
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

REMIX_CODE = "0123456789ABCDEFFEDCB"
SCORE_PAYLOAD = {
    "format": "delta-music",
    "version": 1,
    "title": "作者收益测试曲",
    "artist": "测试作者",
    "sharedBy": "tester",
    "key": "1=C",
    "meter": "4/4",
    "bpm": 120,
    "jianpu": "1 2 3 4 | 5 6 7 1' |",
    "remixCode": REMIX_CODE,
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


class AuthorPointsPerUnlockTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        root = Path(self._temp.name)
        self._originals = {
            "AUTH_DATABASE": SERVER.AUTH_DATABASE,
            "REPOSITORY_ROOT": SERVER.REPOSITORY_ROOT,
            "DATA_DIRECTORY": SERVER.DATA_DIRECTORY,
            "SOURCE_DIRECTORY": SERVER.SOURCE_DIRECTORY,
        }
        SERVER.REPOSITORY_ROOT = root
        SERVER.DATA_DIRECTORY = root / "data"
        SERVER.SOURCE_DIRECTORY = SERVER.DATA_DIRECTORY / "community-scores"
        SERVER.AUTH_DATABASE = SERVER.DATA_DIRECTORY / "auth.sqlite3"
        SERVER.SOURCE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        self.score_path = SERVER.SOURCE_DIRECTORY / "author-points-test.deltamusic"
        self.score_path.write_text(json.dumps(SCORE_PAYLOAD, ensure_ascii=False), encoding="utf-8")

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
        server.auth_secret = "author-points-test-secret"
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
            for account_id in ("author-account", "unlocker-one", "unlocker-two"):
                connection.execute(
                    "INSERT INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (account_id, f"{account_id}@example.invalid", account_id, 1, 1),
                )
            connection.execute(
                "INSERT INTO score_owners(remix_code, score_path, account_id) VALUES (?, ?, ?)",
                (REMIX_CODE, str(self.score_path), "author-account"),
            )
        # issue_session also grants the daily login reward, so balances are read
        # before and after each unlock instead of being hard-coded here.
        self.tokens = {account_id: SERVER.issue_session(server, account_id) for account_id in
                       ("author-account", "unlocker-one", "unlocker-two")}
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        SERVER.reset_auth_schema_guard()
        for name, value in self._originals.items():
            setattr(SERVER, name, value)
        self._temp.cleanup()

    def request(self, path, *, cookie=None, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Cookie": f"{SERVER.AUTH_COOKIE_NAME}={cookie}"} if cookie else {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body, headers=headers,
            method="POST" if body is not None else "GET",
        )
        opener = urllib.request.build_opener(NoRedirect)
        try:
            response = opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return response.status, parsed

    def unlock(self, account_id):
        return self.request("/api/points/unlock", cookie=self.tokens[account_id], payload={"remixCode": REMIX_CODE})

    def points(self, account_id):
        status, payload = self.request("/api/points", cookie=self.tokens[account_id])
        self.assertEqual(status, 200)
        return payload

    def ledger(self, account_id):
        status, payload = self.request("/api/points/ledger", cookie=self.tokens[account_id])
        self.assertEqual(status, 200)
        return payload["entries"]

    def author_entries(self, account_id="author-account"):
        return [entry for entry in self.ledger(account_id) if entry["reason"] == "author"]

    def test_every_valid_unlock_credits_one_point_immediately(self):
        before = self.points("author-account")["balance"]
        self.assertLess(0, before, "author must already hold the signup and upload rewards")

        status, body = self.unlock("unlocker-one")
        self.assertEqual(status, 200)
        self.assertTrue(body["charged"])
        self.assertEqual(self.points("author-account")["balance"], before + 1)
        self.assertEqual(self.points("author-account")["authorUnlocks"], 1)
        entries = self.author_entries()
        self.assertEqual([entry["amount"] for entry in entries], [SERVER.POINT_RULES["author_reward"]])
        self.assertEqual(entries[0]["reference"], f"unlocker-one:{REMIX_CODE}")

        status, body = self.unlock("unlocker-two")
        self.assertEqual(status, 200)
        self.assertTrue(body["charged"])
        self.assertEqual(self.points("author-account")["balance"], before + 2)
        self.assertEqual(self.points("author-account")["authorUnlocks"], 2)
        entries = self.author_entries()
        self.assertEqual([entry["amount"] for entry in entries], [1, 1])
        self.assertEqual(
            {entry["reference"] for entry in entries},
            {f"unlocker-one:{REMIX_CODE}", f"unlocker-two:{REMIX_CODE}"},
        )

    def test_unlocker_is_charged_once_and_a_repeat_never_credits_twice(self):
        self.unlock("unlocker-one")
        author_before = self.points("author-account")["balance"]
        unlocker_before = self.points("unlocker-one")["balance"]

        status, body = self.unlock("unlocker-one")
        self.assertEqual(status, 200)
        self.assertFalse(body["charged"], "the second unlock of the same score must be free")
        self.assertEqual(self.points("author-account")["balance"], author_before)
        self.assertEqual(self.points("unlocker-one")["balance"], unlocker_before)
        self.assertEqual(len(self.author_entries()), 1)

        charges = [entry for entry in self.ledger("unlocker-one") if entry["reason"] == "unlock"]
        self.assertEqual([entry["amount"] for entry in charges], [-SERVER.POINT_RULES["unlock"]])

    def test_own_score_unlock_credits_no_author_points(self):
        status, body = self.unlock("author-account")
        self.assertEqual(status, 200)
        self.assertFalse(body["charged"])
        self.assertEqual(self.author_entries(), [])
        self.assertEqual(self.points("author-account")["authorUnlocks"], 0)

    def test_points_payload_drops_the_batched_progress_counter(self):
        self.unlock("unlocker-one")
        payload = self.points("author-account")
        self.assertIn("authorUnlocks", payload)
        self.assertNotIn("authorProgress", payload)
        self.assertEqual(payload["rules"]["author_reward"], 1)
        self.assertNotIn("author_every", payload["rules"])

    def test_source_no_longer_contains_the_batched_author_rule(self):
        source = (TOOLS / "local_library_server.py").read_text(encoding="utf-8")
        self.assertNotIn("author_every", source)
        self.assertIn('POINT_RULES["author_reward"]', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
