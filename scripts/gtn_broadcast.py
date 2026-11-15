#!/usr/bin/env python3
"""运维工具：给全服发一条系统广播。

实现方式：用服务端的 SECRET_KEY 现场签发一个短期「管理控制台会话」cookie，
再调用既有的 ``POST /api/adminconsole/command`` 执行 ``broadcast <内容>``。
不新增任何公网入口，也不需要把管理台密码写进脚本。

用法（在服务器上用 release 的 venv 运行）::

    /opt/gtn-release/venv/bin/python scripts/gtn_broadcast.py \
        "五分钟后更新，请大家尽快结束对局"

    # 广播成功后等 300 秒再返回，供部署脚本「广播 → 整 5 分钟后切换」
    ... --wait 300

SECRET_KEY 读取顺序：环境变量 → --pid 的 /proc/<pid>/environ → systemd 主进程。
脚本不会打印 SECRET_KEY 本身。
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_NOTICE = '五分钟后更新，请大家尽快结束对局'
DEFAULT_WAIT_SECONDS = 300
DEFAULT_BASE_URL = 'http://127.0.0.1:5000'
SESSION_TTL_SECONDS = 600
_COOKIE_NAME = 'session'
_SERVICE_UNIT = 'gtn-release'


def _read_proc_environ(pid: int) -> dict:
    path = f'/proc/{int(pid)}/environ'
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError as exc:
        raise SystemExit(f'无法读取 {path}: {exc}（需要 root 权限）')
    values = {}
    for chunk in raw.split(b'\x00'):
        if b'=' not in chunk:
            continue
        name, value = chunk.split(b'=', 1)
        values[name.decode('utf-8', 'replace')] = value.decode('utf-8', 'replace')
    return values


def find_main_pid(unit: str = _SERVICE_UNIT) -> int:
    try:
        output = subprocess.run(
            ['systemctl', 'show', '-p', 'MainPID', '--value', unit],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'无法查询 {unit} 的主进程：{exc}')
    try:
        pid = int(output or 0)
    except ValueError:
        pid = 0
    if pid <= 0:
        raise SystemExit(f'{unit} 没有在运行（MainPID={output!r}）')
    return pid


def read_secret_key(pid: int | None = None) -> str:
    secret = (os.environ.get('SECRET_KEY') or '').strip()
    if secret:
        return secret
    pid = find_main_pid() if pid is None else int(pid)
    values = _read_proc_environ(pid)
    secret = (values.get('SECRET_KEY') or '').strip()
    if not secret:
        raise SystemExit(
            f'进程 {pid} 的环境里没有 SECRET_KEY；'
            '若服务用的是进程内临时密钥，重启后任何旧会话都会失效，无法代签。'
        )
    return secret


def build_command_line(message: str) -> str:
    # 管理台命令树里广播挂在 lobby 组下：`lobby broadcast <内容>`。
    return f'lobby broadcast {message}'


def build_session_cookie(
    secret_key: str,
    *,
    now: float | None = None,
    session_id: str | None = None,
    csrf_token: str | None = None,
) -> str:
    """签发一枚「刚登录的管理控制台」会话 cookie。"""
    from flask import Flask
    from flask.sessions import SecureCookieSessionInterface

    stamp = time.time() if now is None else float(now)
    payload = {
        'admin_console_authenticated': True,
        'admin_console_login_time': stamp,
        'admin_console_last_seen': stamp,
        'admin_console_session_id': session_id or secrets.token_urlsafe(18),
        'admin_console_csrf': csrf_token or secrets.token_urlsafe(24),
    }
    app = Flask('gtn-broadcast')
    app.secret_key = secret_key
    serializer = SecureCookieSessionInterface().get_signing_serializer(app)
    return serializer.dumps(payload)


def post_command(
    base_url: str,
    cookie: str,
    csrf_token: str,
    line: str,
    *,
    timeout: float = 15.0,
) -> dict:
    body = json.dumps({
        'line': line,
        'request_id': f'ops-broadcast-{int(time.time() * 1000)}',
    }).encode('utf-8')
    request = urllib.request.Request(
        base_url.rstrip('/') + '/api/adminconsole/command',
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Admin-Console-CSRF': csrf_token,
            'Cookie': f'{_COOKIE_NAME}={cookie}',
            'Origin': base_url.rstrip('/'),
            'Sec-Fetch-Site': 'same-origin',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')
        raise SystemExit(f'广播请求被拒绝（HTTP {exc.code}）：{detail}')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='给 GTN 全服发一条系统广播')
    parser.add_argument('message', nargs='?', default=DEFAULT_NOTICE)
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    parser.add_argument('--pid', type=int, default=None, help='从该进程环境读 SECRET_KEY')
    parser.add_argument('--wait', type=float, default=0.0, help='广播成功后等待的秒数')
    parser.add_argument('--dry-run', action='store_true', help='只打印将要执行的命令')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    message = (args.message or '').strip() or DEFAULT_NOTICE
    line = build_command_line(message)
    if args.dry_run:
        print(line)
        return 0

    secret_key = read_secret_key(args.pid)
    csrf_token = secrets.token_urlsafe(24)
    cookie = build_session_cookie(secret_key, csrf_token=csrf_token)
    result = post_command(args.base_url, cookie, csrf_token, line)
    ok = bool(result.get('success'))
    print(json.dumps({
        'ok': ok,
        'output': result.get('output', ''),
        'broadcast_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, ensure_ascii=False))
    if not ok:
        return 1
    if args.wait > 0:
        print(f'waiting {args.wait:.0f}s before switching the service ...', flush=True)
        time.sleep(args.wait)
        print(json.dumps({
            'switch_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
