# -*- coding: utf-8 -*-
"""训练场本地引擎下载与辅助接口。"""

import io
import time
import unittest
import zipfile

import app


class SoloLocalApiTests(unittest.TestCase):
    def test_runtime_route_returns_complete_zip_promptly(self):
        client = app.app.test_client()
        started = time.monotonic()
        response = client.get('/api/solo-local-runtime')
        elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 200, response.data[:500])
        self.assertLess(elapsed, 20, elapsed)
        self.assertEqual(response.mimetype, 'application/zip')
        self.assertTrue(response.headers.get('ETag'))
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('game_engine.py', archive.namelist())
            self.assertIn('solo_local_runner.py', archive.namelist())

    def test_official_community_payload_is_empty(self):
        client = app.app.test_client()
        response = client.post('/api/solo-local-community', json={'mod_source': 'official'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'success': True, 'mods': []})

    def test_achievement_requires_login(self):
        client = app.app.test_client()
        response = client.post('/api/solo-local-achievement', json={
            'flag': 'flag_solo_status_25', 'status_type_count': 30,
        })
        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
