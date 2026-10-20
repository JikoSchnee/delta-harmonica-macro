"""Smoke the admin → KOOK/activity redemption → ledger flow over HTTP."""
import json
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_points_ledger_api as ledger_fixture

SERVER = ledger_fixture.SERVER


class RewardCodesSmokeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ledger_fixture.PointsLedgerApiTests()
        self.fixture.setUp()
        self.fixture.server.analytics_enabled = True
        self.fixture.server.analytics_admin_token = "reward-smoke-admin"

    def tearDown(self):
        self.fixture.tearDown()

    def request(self, path, payload=None, *, admin=False, logged_in=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if logged_in:
            headers["Cookie"] = self.fixture.cookie()
        if admin:
            headers["Authorization"] = "Bearer reward-smoke-admin"
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.fixture.port}/api/{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_activity_and_permanent_kook_flow(self):
        self.assertEqual(self.request("admin/reward-codes")[0], 401)
        status, listing = self.request("admin/reward-codes", admin=True)
        self.assertEqual(status, 200)
        kook = next(item for item in listing["items"] if item["kind"] == "kook")
        self.assertEqual((kook["points"], kook["expiresAt"]), (20, None))
        SERVER.reset_auth_schema_guard()
        SERVER.initialize_auth_database()
        self.assertEqual(SERVER.reward_codes_admin_payload()["items"], listing["items"])
        self.assertEqual(self.request("points/redeem", {"code": kook["code"]}, logged_in=False)[0], 401)
        self.assertEqual(self.request("points/redeem", {"code": kook["code"]}, origin="https://other.invalid")[0], 403)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.request("points/redeem", {"code": kook["code"].lower()}), range(2)))
        self.assertEqual(sorted(status for status, _ in replies), [200, 400])
        self.assertEqual(next(body for status, body in replies if status == 200)["awarded"], 20)
        now = SERVER.now_timestamp()
        create = {"action": "create", "title": "KOOK 100 人里程碑", "points": 75, "startsAt": now, "expiresAt": now + 3600}
        status, listing = self.request("admin/reward-codes", create, admin=True)
        self.assertEqual(status, 200)
        activity = next(item for item in listing["items"] if item["kind"] == "limited")
        for points in (0, True, 1.5, 10001):
            self.assertEqual(self.request("admin/reward-codes", {**create, "points": points}, admin=True)[0], 400)
        with patch.object(SERVER, "now_timestamp", return_value=now - 1):
            self.assertEqual(self.request("points/redeem", {"code": activity["code"]})[0], 400)
        with patch.object(SERVER, "now_timestamp", return_value=now + 3600):
            self.assertEqual(self.request("points/redeem", {"code": activity["code"]})[0], 400)
        toggle = {"action": "toggle", "id": activity["id"], "active": False}
        self.assertEqual(self.request("admin/reward-codes", toggle, admin=True)[0], 200)
        self.assertEqual(self.request("points/redeem", {"code": activity["code"]})[0], 400)
        self.request("admin/reward-codes", {**toggle, "active": True}, admin=True)
        status, result = self.request("points/redeem", {"code": activity["code"]})
        self.assertEqual((status, result["awarded"]), (200, 75))
        self.assertEqual(self.request("points/redeem", {"code": activity["code"]})[0], 400)
        _, ledger = self.request("points/ledger")
        entries = [entry for entry in ledger["entries"] if entry["reason"] == "reward_code"]
        self.assertEqual(sum(entry["amount"] for entry in entries), 95)
        self.assertEqual({entry["reward_title"] for entry in entries}, {"KOOK 入群奖励", create["title"]})
        self.assertTrue(all(item["redeemed"] == 1 for item in SERVER.reward_codes_admin_payload()["items"]))
        with SERVER.auth_database() as connection:
            connection.execute("INSERT INTO accounts(id,email,user_id,created_at,updated_at) VALUES ('second','second@example.invalid','second',1,1)")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM streamer_redemptions").fetchone()[0], 0)
        self.assertEqual(SERVER.redeem_reward_code("second", {"code": kook["code"]})["awarded"], 20)


if __name__ == "__main__":
    unittest.main()
