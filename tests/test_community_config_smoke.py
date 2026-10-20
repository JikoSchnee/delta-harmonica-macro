"""Smoke the persistent admin KOOK QR/link configuration over HTTP."""
import json
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import test_points_ledger_api as ledger_fixture

SERVER = ledger_fixture.SERVER
ROOT = Path(__file__).resolve().parents[1]


class CommunityConfigSmokeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ledger_fixture.PointsLedgerApiTests()
        self.fixture.setUp()
        self.fixture.server.analytics_enabled = True
        self.fixture.server.analytics_admin_token = 'community-smoke-admin'
        self.data_patch = patch.object(SERVER, 'DATA_DIRECTORY', Path(self.fixture._temp.name) / 'data')
        self.data_patch.start()
        self.fixture.server.RequestHandlerClass = lambda *a, **k: SERVER.LocalLibraryRequestHandler(
            *a, directory=self.fixture._temp.name, **k)

    def tearDown(self):
        self.data_patch.stop()
        self.fixture.tearDown()

    def request(self, path, payload=None, *, method=None, admin=False, declared_length=None):
        headers = {'Content-Type': 'application/json'}
        if admin:
            headers['Authorization'] = 'Bearer community-smoke-admin'
        if isinstance(payload, bytes):
            body = payload
            headers['Content-Type'] = 'image/png'
        else:
            body = json.dumps(payload).encode() if payload is not None else None
        if declared_length is not None:
            headers['Content-Length'] = str(declared_length)
        req = urllib.request.Request(f'http://127.0.0.1:{self.fixture.port}/{path}',
                                     data=body, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            data = json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw
            return response.status, data

    def test_upload_save_public_read_and_persistence(self):
        status, original = self.request('api/community')
        self.assertEqual(status, 200)
        self.assertEqual(original['kookUrl'], 'https://kook.vip/jcJIDN')
        self.assertEqual(self.request('api/admin/community')[0], 401)
        self.assertEqual(self.request('api/admin/community', original, method='PUT')[0], 401)
        png = (ROOT / 'assets/kook-channel-qr.png').read_bytes()
        self.assertEqual(self.request('api/admin/community/qr', png)[0], 401)
        self.assertEqual(self.request('api/admin/community/qr', b'not an image', admin=True)[0], 400)
        self.assertEqual(self.request('api/admin/community/qr', b'x', admin=True, declared_length=5 * 1024 * 1024 + 1)[0], 400)
        status, upload = self.request('api/admin/community/qr', png, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(self.request(upload['url'][2:]), (200, png))
        self.assertEqual(self.request('api/community')[1], original, 'upload alone must not publish the image')
        updated = {'kookUrl': 'https://kook.vip/Smoke123', 'kookQrUrl': upload['url']}
        for invalid_url in ('javascript:alert(1)', 'https://kook.vip.evil.invalid/x', 'https://kook.vip@evil.invalid/x', 'http://kook.vip/abc'):
            self.assertEqual(self.request('api/admin/community', {**updated, 'kookUrl': invalid_url}, method='PUT', admin=True)[0], 400)
        self.assertEqual(self.request('api/admin/community', {**updated, 'kookQrUrl': './data/community/' + '0' * 32 + '.png'}, method='PUT', admin=True)[0], 400)
        self.assertEqual(self.request('api/admin/community', {**updated, 'kookQrUrl': '../auth.sqlite3'}, method='PUT', admin=True)[0], 400)
        status, saved = self.request('api/admin/community', updated, method='PUT', admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(saved['kookUrl'], updated['kookUrl'])
        self.assertEqual(saved['kookQrUrl'], upload['url'])
        self.assertEqual(self.request('api/community')[1], saved)
        SERVER.reset_auth_schema_guard()
        SERVER.initialize_auth_database()
        self.assertEqual(self.request('api/admin/community', admin=True)[1], saved)
        shell = (ROOT / 'index.html').read_text()
        self.assertEqual(shell.count('data-kook-link href='), 4)
        self.assertEqual(shell.count('data-kook-qr src='), 3)


if __name__ == '__main__':
    unittest.main()
