"""Smoke-test the npm development launcher and stop its complete process tree."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
NPM = shutil.which('npm')
with tempfile.TemporaryDirectory() as temp_dir:
    env = dict(os.environ)
    env.update({
        'GTN_DB_PATH': str(Path(temp_dir) / 'preview.sqlite3'),
        'SECRET_KEY': 'preview-smoke-test-only',
        'GTN_SESSION_COOKIE_SECURE': '0',
    })
    process = subprocess.Popen(
        [NPM, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '7100'],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8',
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError(f'预览服务器提前退出：{process.returncode}')
            try:
                with urlopen('http://127.0.0.1:7100/api/healthz', timeout=1) as response:
                    if response.status == 200:
                        print(response.read().decode('utf-8'))
                        break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.25)
    finally:
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
            process.wait(timeout=8)
        print(f'preview server stopped: {process.poll() is not None}')
