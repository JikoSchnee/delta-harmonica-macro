"""Regression tests for GitHub account binding and GitHub sign-in.

GitHub sign-in must never mint a new account: a GitHub identity that is not
already bound to a site account is rejected, and binding only happens from an
authenticated session (or from verifying the Star reward). These tests run
offline against faked GitHub HTTP.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

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


class GithubLoginBindingTests(unittest.TestCase):
    def setUp(self):
        self._temp = TemporaryDirectory()
        self._original_db = SERVER.AUTH_DATABASE
        self._original_fetch = SERVER.fetch_oauth_response
        self._original_urlopen = SERVER.urlopen
        SERVER.AUTH_DATABASE = Path(self._temp.name) / "auth.sqlite3"
        SERVER.reset_auth_schema_guard()
        SERVER.initialize_auth_database()
        self.server = SimpleNamespace(
            auth_enabled=True,
            analytics_enabled=False,
            github_oauth={
                "client_id": "cid",
                "client_secret": "secret",
                "redirect_uri": "https://example.test/delta/api/points/github/callback",
                "repo": "JikoSchnee/delta-harmonica-macro",
            },
        )
        for name in ("account-a", "account-b"):
            self.add_account(name)

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

    def account_count(self):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            return connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    def bind(self, account_id, github_id="4242", login="octocat"):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            SERVER.bind_github_identity(connection, account_id, github_id, login)

    def bound(self, account_id):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            return SERVER.bound_github_identity(connection, account_id)

    def fake_github(self, *, github_id=4242, login="octocat", star_status=204, token="token-abc"):
        def fake_fetch(url, *, data=None, headers=None, timeout=None):
            if url.startswith("https://github.com/login/oauth/access_token"):
                return json.dumps({"access_token": token} if token else {"error": "bad_verification_code"})
            if url == "https://api.github.com/user":
                return json.dumps({"id": github_id, "login": login})
            raise AssertionError(f"unexpected fetch: {url}")

        def fake_urlopen(request, timeout=None):
            if "/user/starred/" not in request.full_url:
                raise AssertionError(f"unexpected urlopen: {request.full_url}")
            return FakeResponse(star_status)

        SERVER.fetch_oauth_response = fake_fetch
        SERVER.urlopen = fake_urlopen

    def test_sign_in_is_rejected_when_github_is_not_bound(self):
        self.fake_github()
        before = self.account_count()
        with self.assertRaises(SERVER.GithubLoginError) as ctx:
            SERVER.github_login_account(self.server, "code-1")
        self.assertEqual(ctx.exception.reason, "unbound")
        self.assertEqual(ctx.exception.login, "octocat")
        # The whole point: signing in with GitHub must not create an account.
        self.assertEqual(self.account_count(), before)

    def test_bound_github_account_signs_into_its_site_account(self):
        self.bind("account-a")
        self.fake_github()
        account, login = SERVER.github_login_account(self.server, "code-2")
        self.assertEqual(str(account["id"]), "account-a")
        self.assertEqual(login, "octocat")

    def test_binding_from_a_session_links_the_github_account(self):
        self.fake_github(github_id=777, login="binder")
        account, login = SERVER.github_login_account(self.server, "code-3", "account-b")
        self.assertEqual(str(account["id"]), "account-b")
        self.assertEqual(login, "binder")
        row = self.bound("account-b")
        self.assertIsNotNone(row)
        self.assertEqual(row["subject"], "777")
        self.assertEqual(row["display_name"], "binder")
        # A following GitHub sign-in now resolves to the same site account.
        account, _ = SERVER.github_login_account(self.server, "code-4")
        self.assertEqual(str(account["id"]), "account-b")

    def test_a_site_account_holds_one_github_account(self):
        self.bind("account-a", "111", "first")
        with self.assertRaises(SERVER.GithubLoginError) as ctx:
            self.bind("account-a", "222", "second")
        self.assertEqual(ctx.exception.reason, "taken")
        self.assertEqual(self.bound("account-a")["subject"], "111")

    def test_a_github_account_belongs_to_one_site_account(self):
        self.bind("account-a", "333", "shared")
        with self.assertRaises(SERVER.GithubLoginError) as ctx:
            self.bind("account-b", "333", "shared")
        self.assertEqual(ctx.exception.reason, "taken")
        self.assertIsNone(self.bound("account-b"))

    def test_rebinding_the_same_github_account_refreshes_the_login(self):
        self.bind("account-a", "444", "old-name")
        self.bind("account-a", "444", "new-name")
        self.assertEqual(self.bound("account-a")["display_name"], "new-name")

    def test_banned_account_cannot_sign_in_with_github(self):
        self.bind("account-a")
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            SERVER.set_account_ban(connection, "account-a", "abuse")
        self.fake_github()
        with self.assertRaises(SERVER.GithubLoginError) as ctx:
            SERVER.github_login_account(self.server, "code-5")
        self.assertEqual(ctx.exception.reason, "banned")

    def test_star_verification_binds_the_github_account(self):
        self.fake_github(github_id=555, login="star-giver")
        self.assertEqual(SERVER.claim_github_star(self.server, "account-a", "code-6"), "star-giver")
        row = self.bound("account-a")
        self.assertIsNotNone(row)
        self.assertEqual(row["subject"], "555")

    def test_account_payload_exposes_the_bound_github_login(self):
        with SERVER.AUTH_LOCK, SERVER.auth_database() as connection:
            account = connection.execute("SELECT id, email, user_id FROM accounts WHERE id = ?",
                                        ("account-a",)).fetchone()
        payload = SERVER.account_payload(self.server, account)
        self.assertIsNone(payload["github"])
        self.bind("account-a", "666", "shown-user")
        payload = SERVER.account_payload(self.server, account)
        self.assertEqual(payload["github"]["login"], "shown-user")
        self.assertEqual(payload["github"]["githubId"], "666")

    def test_return_url_carries_the_reason_and_login(self):
        url = SERVER.github_login_return_url(self.server, "error", "unbound", "octocat")
        self.assertIn("github-login=error", url)
        self.assertIn("reason=unbound", url)
        self.assertIn("login=octocat", url)
        self.assertIn("/delta/", url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
