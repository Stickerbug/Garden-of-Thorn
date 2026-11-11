"""Start an isolated GTN server, verify browser-local solo play, then stop everything."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
PORT = 5127
BASE = f'http://127.0.0.1:{PORT}'

with tempfile.TemporaryDirectory() as temp_dir:
    env = dict(os.environ)
    env.update({
        'GTN_DB_PATH': str(Path(temp_dir) / 'solo-browser.sqlite3'),
        'SECRET_KEY': 'local-solo-browser-test-only',
        'GTN_SESSION_COOKIE_SECURE': '0',
        'GTN_PUBLIC_VERSION': 'solo-local-browser-test',
        'GTN_PORT': str(PORT),
        'GTN_BIND_HOST': '127.0.0.1',
        'PYTHONUNBUFFERED': '1',
    })
    server = subprocess.Popen(
        [str(ROOT / '.venv/Scripts/python.exe'), 'app.py'],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8',
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            if server.poll() is not None:
                raise RuntimeError(f'本地测试服务器提前退出：{server.returncode}')
            try:
                with urlopen(f'{BASE}/api/healthz', timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.25)
        completed = subprocess.run(
            [NODE, str(ROOT / 'tests/local_solo_browser_check.js'), BASE],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=270,
        )
        print(completed.stdout, end='')
        if completed.stderr:
            print(completed.stderr, end='')
        if completed.returncode != 0:
            raise RuntimeError(f'浏览器本地训练场验证失败，退出码 {completed.returncode}')
    finally:
        if server.poll() is None:
            subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], capture_output=True, check=False)
            server.wait(timeout=8)
        print(f'isolated app server stopped: {server.poll() is not None}')
