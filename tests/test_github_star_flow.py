"""Regression tests for the GitHub Star verification flow.

These run entirely offline: the GitHub HTTP calls are replaced with fakes so the
decision logic (retry, 404 vs rate limit, duplicate claims, reason codes and the
state-cookie handling) is pinned without touching the network.
"""
import importlib.util
import io
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location("local_library_server", TOOLS / "local_library_server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class GithubStarFlowTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self._original_db = SERVER.AUTH_DATABASE
        self._original_fetch = SERVER.fetch_oauth_response
        self._original_urlopen = SERVER.urlopen
        SERVER.AUTH_DATABASE = Path(self._temp.name) / "auth.sqlite3"
        SERVER.reset_auth_schema_guard()
        SERVER.initialize_auth_database()
        self.server = SimpleNamespace(
            github_oauth={
                "client_id": "cid",
                "client_secret": "secret",
                "redirect_uri": "https://example.test/delta/api/points/github/callback",
                "repo": "JikoSchnee/delta-harmonica-macro",
            }
        )
        self.accounts = {}
        for name in ("account-a", "account-b"):
            self.accounts[name] = self.add_account(name)

    def tearDown(self):
        SERVER.fetch_oauth_response = self._original_fetch
        SERVER.urlopen = self._original_urlopen
        SERVER.reset_auth_schema_guard()
        SERVER.AUTH_DATABASE = self._original_db
        self._temp.cleanup()

    def add_account(self, name):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            connection.execute(
                "INSERT INTO accounts(id, email, user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, f"{name}@example.invalid", name, 1, 1),
            )
        return name

    def fake_github(self, *, star_status, profile=None, token="token-abc", star_failures=0):
        """Install offline fakes for GitHub.

        ``star_status`` is the HTTP status of the starred check (or an exception
        to raise); ``star_failures`` injects that many transient network errors
        into the starred check before its real answer.
        """
        state = {"star_failures": star_failures}
        calls = []

        def fake_fetch(url, *, data=None, headers=None, timeout=None):
            calls.append(url)
            if url.startswith("https://github.com/login/oauth/access_token"):
                return json.dumps({"access_token": token} if token else {"error": "bad_verification_code"})
            if url == "https://api.github.com/user":
                return json.dumps(profile or {"id": 4242, "login": "octocat"})
            raise AssertionError(f"unexpected fetch: {url}")

        def fake_urlopen(request, timeout=None):
            calls.append(request.full_url)
            if "/user/starred/" not in request.full_url:
                raise AssertionError(f"unexpected urlopen: {request.full_url}")
            if state["star_failures"] > 0:
                state["star_failures"] -= 1
                raise URLError("simulated network failure")
            if isinstance(star_status, Exception):
                raise star_status
            return FakeResponse(star_status)

        SERVER.fetch_oauth_response = fake_fetch
        SERVER.urlopen = fake_urlopen
        self.last_calls = calls
        return calls

    def balance(self, account_id):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            return SERVER.point_balance(connection, account_id)

    def test_starred_repo_grants_the_configured_reward(self):
        self.fake_github(star_status=204)
        login = SERVER.claim_github_star(self.server, "account-a", "code-1")
        self.assertEqual(login, "octocat")
        self.assertEqual(self.balance("account-a"), SERVER.POINT_RULES["github_star"])
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            row = connection.execute("SELECT github_id, account_id FROM github_stars").fetchone()
        self.assertEqual(tuple(row), ("4242", "account-a"))

    def test_not_starred_reports_the_verified_account(self):
        self.fake_github(star_status=HTTPError("url", 404, "Not Found", None, None))
        with self.assertRaises(SERVER.GithubStarError) as ctx:
            SERVER.claim_github_star(self.server, "account-a", "code-2")
        self.assertEqual(ctx.exception.reason, "not_starred")
        self.assertEqual(ctx.exception.login, "octocat")
        self.assertEqual(self.balance("account-a"), 0)

    def test_rate_limit_is_unavailable_not_not_starred(self):
        self.fake_github(star_status=HTTPError("url", 403, "Forbidden", None, None))
        with self.assertRaises(SERVER.GithubStarError) as ctx:
            SERVER.claim_github_star(self.server, "account-a", "code-3")
        self.assertEqual(ctx.exception.reason, "unavailable")

    def test_one_transient_failure_is_retried(self):
        # First starred-check call fails, the retry succeeds.
        self.fake_github(star_status=204, star_failures=1)
        login = SERVER.claim_github_star(self.server, "account-a", "code-4")
        self.assertEqual(login, "octocat")
        self.assertEqual(self.balance("account-a"), SERVER.POINT_RULES["github_star"])

    def test_invalid_token_is_reported_as_authorize_failure(self):
        self.fake_github(star_status=204, token="")
        with self.assertRaises(SERVER.GithubStarError) as ctx:
            SERVER.claim_github_star(self.server, "account-a", "code-5")
        self.assertEqual(ctx.exception.reason, "authorize_failed")

    def test_second_account_cannot_reuse_the_same_github_id(self):
        self.fake_github(star_status=204)
        SERVER.claim_github_star(self.server, "account-a", "code-6")
        with self.assertRaises(SERVER.GithubStarError) as ctx:
            SERVER.claim_github_star(self.server, "account-b", "code-7")
        # The GitHub account is already bound to another site account, which is
        # a clearer reason than the older "already claimed the reward" message.
        self.assertIn(ctx.exception.reason, {"already_claimed", "taken"})
        self.assertEqual(self.balance("account-b"), 0)

    def test_same_account_reclaim_does_not_double_grant(self):
        self.fake_github(star_status=204)
        SERVER.claim_github_star(self.server, "account-a", "code-8")
        SERVER.claim_github_star(self.server, "account-a", "code-9")
        self.assertEqual(self.balance("account-a"), SERVER.POINT_RULES["github_star"])

    def test_attempt_budget_is_honoured(self):
        # attempts=1 (what the flow uses once its time budget is spent) must not
        # retry, while attempts=2 must try twice.
        self.fake_github(star_status=URLError("boom"))
        with self.assertRaises(SERVER.GithubStarError):
            SERVER.github_star_status("owner/repo", {}, attempts=1)
        self.assertEqual(len([c for c in self.last_calls if "/user/starred/" in c]), 1)

        self.fake_github(star_status=URLError("boom"))
        with self.assertRaises(SERVER.GithubStarError):
            SERVER.github_star_status("owner/repo", {}, attempts=2)
        self.assertEqual(len([c for c in self.last_calls if "/user/starred/" in c]), 2)

    def test_return_url_carries_reason_and_login(self):
        url = SERVER.github_star_return_url(self.server, "error", "not_starred", "octocat")
        self.assertTrue(url.startswith("https://example.test/delta/?"))
        self.assertIn("github-star=error", url)
        self.assertIn("reason=not_starred", url)
        self.assertIn("login=octocat", url)
        success = SERVER.github_star_return_url(self.server, "success")
        self.assertEqual(success, "https://example.test/delta/?github-star=success")

    def test_state_binding_replaces_the_optional_cookie(self):
        """The callback must trust the in-memory state bound to the account.

        The state cookie cannot be required: browsers drop a cookie set on the
        redirect out to github.com, which used to fail every attempt.
        """
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            connection.execute("SELECT 1")
        self.assertEqual(SERVER.OAUTH_STATE_COOKIE_NAME, "delta_oauth_state")
        source = (TOOLS / "local_library_server.py").read_text(encoding="utf-8")
        self.assertIn("state cookie 缺失，改用绑定校验", source)
        self.assertIn("pending.get(\"account_id\") not in (None, account[\"id\"])", source)


if __name__ == "__main__":
    unittest.main()
