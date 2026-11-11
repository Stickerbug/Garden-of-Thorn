# -*- coding: utf-8 -*-
"""浏览器本地引擎包的完整性与隔离运行测试。"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import solo_local_bundle


class SoloLocalBundleTests(unittest.TestCase):
    def test_bundle_is_self_contained_and_runs_without_app(self):
        payload, digest = solo_local_bundle.runtime_bundle({'BlockedCard'}, {'Blocked Mod.gtnmod'})
        self.assertEqual(len(digest), 64)
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / 'runtime.zip'
            archive_path.write_bytes(payload)
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertNotIn('app.py', archive.namelist())
                self.assertIn('game_engine.py', archive.namelist())
                self.assertIn('solo_local_runner.py', archive.namelist())
                self.assertIn('mods/Vanilla Cards.gtnmod', archive.namelist())
                manifest = json.loads(archive.read('solo_local_manifest.json'))
                self.assertEqual(manifest['disabled_card_ids'], ['BlockedCard'])
                self.assertEqual(manifest['disabled_mod_files'], ['Blocked Mod.gtnmod'])
                archive.extractall(temp_dir)
            env = dict(os.environ)
            env['PYTHONPATH'] = temp_dir
            completed = subprocess.run(
                [
                    sys.executable,
                    '-c',
                    "import json; import solo_local_runner as r; "
                    "assert json.loads(r.initialize('{}'))['success']; "
                    "result=json.loads(r.dispatch('solo_start', {'deck0':['Basic']*15,'deck1':['Basic']*15})); "
                    "assert any(name == 'solo_state' for name, _ in result['events']); "
                    "print('LOCAL_BUNDLE_OK')",
                ],
                cwd=temp_dir, env=env, capture_output=True, text=True,
                encoding='utf-8', timeout=45,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertIn('LOCAL_BUNDLE_OK', completed.stdout)


if __name__ == '__main__':
    unittest.main()
