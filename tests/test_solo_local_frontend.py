# -*- coding: utf-8 -*-
"""普通训练场本地 Worker 路径的前端与接口契约。"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SoloLocalFrontendTests(unittest.TestCase):
    def test_worker_and_bridge_are_loaded_before_game(self):
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertLess(index.index('/static/js/solo-local.js'), index.index('/static/js/game.js'))
        worker = (ROOT / 'static/js/solo-local-worker.js').read_text(encoding='utf-8')
        self.assertIn("from '/static/vendor/pyodide/pyodide.esm.js'", worker)
        self.assertIn("type: 'module'", (ROOT / 'static/js/solo-local.js').read_text(encoding='utf-8'))
        self.assertIn("zipfile.ZipFile('/tmp/gtn-solo-local.zip').extractall", worker)
        loader = (ROOT / 'static/vendor/pyodide/pyodide.esm.js').read_text(encoding='utf-8')
        self.assertIn('WebAssembly.instantiate(await t,s)', loader)
        self.assertNotIn('instantiateStreaming', loader)

    def test_all_training_actions_use_local_dispatcher_when_active(self):
        source = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        for marker in (
            "window.GTNSoloLocal.dispatch(eventName, payload)",
            "window.GTNSoloLocal.dispatch('request_game_state'",
            "window.GTNSoloLocal.dispatch('predict_hand'",
            "window.GTNSoloLocal?.register(eventName, handler)",
        ):
            self.assertIn(marker, source)
        start = source.index('function emitSoloEvent(')
        end = source.index('function emitModeEvent(', start)
        self.assertIn('localStart', source[start:end])
        self.assertIn('localActive', source[start:end])
        self.assertLess(source.index('localStart'), source.index('socket.emit(eventName, payload)', start))

    def test_runtime_endpoints_do_not_run_game_actions(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        for route in ('/api/solo-local-runtime', '/api/solo-local-community', '/api/solo-local-achievement'):
            self.assertIn(route, source)
        runtime = source[source.index("def api_solo_local_runtime("):source.index("@app.route('/api/solo-local-community'")]
        self.assertIn('solo_local_bundle.runtime_bundle', runtime)
        self.assertNotIn('create_solo_engine', runtime)
        self.assertNotIn('play_card(', runtime)
        self.assertNotIn('end_turn(', runtime)

    def test_official_pyodide_files_are_local(self):
        for name in ('pyodide.esm.js', 'pyodide.asm.esm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json'):
            path = ROOT / 'static/vendor/pyodide' / name
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 0, name)


if __name__ == '__main__':
    unittest.main()
