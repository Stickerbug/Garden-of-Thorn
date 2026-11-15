#!/usr/bin/env bash
# GTN 更新发布脚本（2026-11-15 起强制流程）：
#   解包到暂存目录 → 全服广播「五分钟后更新，请大家尽快结束对局」→ 等 5 分钟整 → 切换服务。
#
# 用法（在服务器上，root）：
#   bash gtn_update.sh /tmp/gtn-deploy.tgz <git-sha>
#
# 可调环境变量（仅演练时才改时长）：
#   GTN_NOTICE_MESSAGE   广播文案
#   GTN_NOTICE_WAIT_SECONDS  广播后等待秒数（默认 300）
#   GTN_NOTICE_BANNER_SECONDS 顶部公告持续秒数（默认 WAIT+120，覆盖重启窗口）
#   GTN_PORT             应用端口（默认 5000）
set -euo pipefail

ARCHIVE=${1:?用法: bash gtn_update.sh <archive.tar.gz> <git-sha>}
SHA=${2:?用法: bash gtn_update.sh <archive.tar.gz> <git-sha>}
NOTICE=${GTN_NOTICE_MESSAGE:-五分钟后更新，请大家尽快结束对局}
WAIT=${GTN_NOTICE_WAIT_SECONDS:-300}
BANNER_SECONDS=${GTN_NOTICE_BANNER_SECONDS:-$((WAIT + 120))}
PORT=${GTN_PORT:-5000}

RELEASE=/opt/gtn-release
STAGE=/opt/gtn-stage
RECYCLE=/opt/gtn-release.old
RELEASE_ENV=/etc/gtn/release.env

BROADCAST_SCRIPT=""
for candidate in \
    "$RELEASE/scripts/gtn_broadcast.py" \
    "/usr/local/sbin/gtn-broadcast" \
    "$(dirname "$0")/gtn_broadcast.py"; do
    if [ -f "$candidate" ]; then BROADCAST_SCRIPT=$candidate; break; fi
done

echo "[1/6] 解包 $ARCHIVE -> $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"
tar -xzf "$ARCHIVE" -C "$STAGE" --strip-components=1
if [ ! -f "$STAGE/app.py" ]; then
    echo "解包后找不到 app.py，中止（发布包前缀应为 gtn/）" >&2
    exit 1
fi
# 优先用发布包里的广播工具：它和即将上线的服务端命令格式一致，
# 线上旧版的 gtn_broadcast.py 可能还不认识 --seconds。
if [ -f "$STAGE/scripts/gtn_broadcast.py" ]; then
    BROADCAST_SCRIPT=$STAGE/scripts/gtn_broadcast.py
fi
if [ ! -f "$BROADCAST_SCRIPT" ]; then
    echo "找不到 gtn_broadcast.py，无法按要求广播，中止" >&2
    exit 1
fi
"$RELEASE/venv/bin/python" -m py_compile "$STAGE/app.py"
echo "[2/6] 暂存目录编译校验通过"

echo "[3/6] 全服广播 + 顶部公告（${BANNER_SECONDS} 秒）：$NOTICE"
"$RELEASE/venv/bin/python" "$BROADCAST_SCRIPT" --base-url "http://127.0.0.1:${PORT}" --seconds "$BANNER_SECONDS" "$NOTICE"

echo "[4/6] 等待 ${WAIT} 秒后切换服务（请勿中断本脚本）"
sleep "$WAIT"

echo "[5/6] 停服并切换目录"
systemctl stop gtn-release
mv "$RELEASE/venv" "$STAGE/venv"
rm -rf "$RECYCLE"
mv "$RELEASE" "$RECYCLE"
mv "$STAGE" "$RELEASE"
if grep -q '^GTN_VERSION=' "$RELEASE_ENV"; then
    sed -i "s/^GTN_VERSION=.*/GTN_VERSION=${SHA}/" "$RELEASE_ENV"
else
    printf 'GTN_VERSION=%s\n' "$SHA" >> "$RELEASE_ENV"
fi
if grep -q '^GTN_GIT_SHA=' "$RELEASE_ENV"; then
    sed -i "s/^GTN_GIT_SHA=.*/GTN_GIT_SHA=${SHA}/" "$RELEASE_ENV"
fi
if grep -q '^GTN_STATIC_VERSION=' "$RELEASE_ENV"; then
    sed -i "s/^GTN_STATIC_VERSION=.*/GTN_STATIC_VERSION=${SHA}/" "$RELEASE_ENV"
fi
systemctl daemon-reload
systemctl start gtn-release

echo "[6/6] 等待新版本就绪"
for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/api/version" | grep -q "${SHA}"; then
        echo "VERSION_OK ${SHA}"
        systemctl is-active gtn-release
        exit 0
    fi
    sleep 1
done
echo "新版本 ${SHA} 在 30 秒内未就绪，请检查 journalctl -u gtn-release" >&2
exit 1
