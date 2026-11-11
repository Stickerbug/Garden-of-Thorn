# -*- coding: utf-8 -*-
"""天梯开放窗口（北京时间）：工作日 20-22，周末 8-12、14-20。"""
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc


def _beijing(now=None):
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BEIJING_TZ).replace(microsecond=0)


def _utc_iso(value):
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _windows_for_day(day):
    if day.weekday() < 5:
        return [(20, 22)]
    return [(8, 12), (14, 20)]


def ranked_status(now=None):
    local = _beijing(now)
    today = local.date()
    for start_hour, end_hour in _windows_for_day(today):
        start = local.replace(hour=start_hour, minute=0, second=0)
        end = local.replace(hour=end_hour, minute=0, second=0)
        if start <= local < end:
            return {
                'open': True,
                'seconds_to_open': 0,
                'seconds_to_close': max(0, int((end - local).total_seconds())),
                'next_change_at': _utc_iso(end),
                'server_time': _utc_iso(local),
            }
    for offset in range(0, 9):
        day = today + timedelta(days=offset)
        for start_hour, _ in _windows_for_day(day):
            start = local.replace(
                year=day.year, month=day.month, day=day.day,
                hour=start_hour, minute=0, second=0,
            )
            if start > local:
                return {
                    'open': False,
                    'seconds_to_open': max(0, int((start - local).total_seconds())),
                    'seconds_to_close': 0,
                    'next_change_at': _utc_iso(start),
                    'server_time': _utc_iso(local),
                }
    raise RuntimeError('无法计算下一次天梯开放时间')


def ranked_is_open(now=None):
    return bool(ranked_status(now)['open'])
