# -*- coding: utf-8 -*-
"""货币流水异常检测：供 /handling「风险」页签展示荆露 / 金露的可疑流水。

阈值（2026-11-12 定稿）：
- 荆露：5 分钟内两笔相同金额且金额 > 1000；单笔 > 5000；同一玩家当日流水合计 > 20000。
- 金露：5 分钟内两笔相同金额且金额 > 5；同一玩家当日流水合计 > 100。

「流水」按绝对值累加（扣减也算量），同一玩家同一币种分开统计；日期按北京时间切分。
检测只产出线索供人工判断，不做任何处罚。
"""

from datetime import datetime, timedelta, timezone

CURRENCY_THORN = 'thorn_dew'
CURRENCY_GOLD = 'golden_dew'

_BEIJING = timezone(timedelta(hours=8))

RULES = {
    CURRENCY_THORN: {
        'label': '荆露',
        'duplicate_amount': 1000,
        'duplicate_window_seconds': 300,
        'single_amount': 5000,
        'daily_total': 20000,
    },
    CURRENCY_GOLD: {
        'label': '金露',
        'duplicate_amount': 5,
        'duplicate_window_seconds': 300,
        'single_amount': None,
        'daily_total': 100,
    },
}

KIND_LABELS = {
    'duplicate': '5 分钟内重复同额',
    'single': '单笔超额',
    'daily': '日流水超额',
}


def beijing_today(now=None):
    moment = now or datetime.now(timezone.utc)
    if isinstance(moment, (int, float)):
        moment = datetime.fromtimestamp(float(moment), timezone.utc)
    return moment.astimezone(_BEIJING).strftime('%Y-%m-%d')


def day_bounds(day_key):
    """把北京时间日期换成 UTC 起止（左闭右开），用于 created_at 字符串比较。"""
    start = datetime.strptime(str(day_key), '%Y-%m-%d').replace(tzinfo=_BEIJING)
    end = start + timedelta(days=1)
    fmt = lambda value: value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return fmt(start), fmt(end)


def _parse_ts(value):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None


def _amount(row):
    return abs(int(row.get('free_delta') or 0)) + abs(int(row.get('paid_delta') or 0))


def _sort_key(row):
    parsed = _parse_ts(row.get('created_at'))
    return (parsed or datetime.min.replace(tzinfo=timezone.utc), int(row.get('id') or 0))


def detect(transactions):
    """纯函数：输入流水行（含 user_id/currency/free_delta/paid_delta/created_at 等），输出风险条目。"""
    by_bucket = {}
    for row in transactions:
        currency = str(row.get('currency') or '')
        if currency not in RULES:
            continue
        key = (int(row.get('user_id') or 0), currency)
        by_bucket.setdefault(key, []).append(row)

    items = []
    for (user_id, currency), rows in by_bucket.items():
        rule = RULES[currency]
        rows = sorted(rows, key=_sort_key)
        total = sum(_amount(row) for row in rows)
        if total > int(rule['daily_total']):
            items.append({
                'risk_id': f"daily:{user_id}:{currency}",
                'kind': 'daily',
                'kind_label': KIND_LABELS['daily'],
                'user_id': user_id,
                'username': str(rows[0].get('username') or ''),
                'currency': currency,
                'currency_label': rule['label'],
                'amount': total,
                'threshold': int(rule['daily_total']),
                'count': len(rows),
                'first_at': str(rows[0].get('created_at') or ''),
                'last_at': str(rows[-1].get('created_at') or ''),
                'reason': '',
                'source_type': '',
                'transaction_ids': [int(row.get('id') or 0) for row in rows][:20],
            })
        single_cap = rule.get('single_amount')
        if single_cap:
            for row in rows:
                amount = _amount(row)
                if amount > int(single_cap):
                    items.append({
                        'risk_id': f"single:{row.get('id')}",
                        'kind': 'single',
                        'kind_label': KIND_LABELS['single'],
                        'user_id': user_id,
                        'username': str(row.get('username') or ''),
                        'currency': currency,
                        'currency_label': rule['label'],
                        'amount': amount,
                        'threshold': int(single_cap),
                        'count': 1,
                        'first_at': str(row.get('created_at') or ''),
                        'last_at': str(row.get('created_at') or ''),
                        'reason': str(row.get('reason') or ''),
                        'source_type': str(row.get('source_type') or ''),
                        'transaction_ids': [int(row.get('id') or 0)],
                    })
        dup_floor = int(rule['duplicate_amount'])
        window = int(rule['duplicate_window_seconds'])
        for left in range(len(rows)):
            for right in range(left + 1, len(rows)):
                first, second = rows[left], rows[right]
                amount = _amount(first)
                if amount != _amount(second) or amount <= dup_floor:
                    continue
                t1, t2 = _parse_ts(first.get('created_at')), _parse_ts(second.get('created_at'))
                if not t1 or not t2 or abs((t2 - t1).total_seconds()) > window:
                    continue
                items.append({
                    'risk_id': f"duplicate:{first.get('id')}:{second.get('id')}",
                    'kind': 'duplicate',
                    'kind_label': KIND_LABELS['duplicate'],
                    'user_id': user_id,
                    'username': str(first.get('username') or ''),
                    'currency': currency,
                    'currency_label': rule['label'],
                    'amount': amount,
                    'threshold': dup_floor,
                    'count': 2,
                    'first_at': str(first.get('created_at') or ''),
                    'last_at': str(second.get('created_at') or ''),
                    'reason': str(second.get('reason') or ''),
                    'source_type': str(second.get('source_type') or ''),
                    'transaction_ids': [int(first.get('id') or 0), int(second.get('id') or 0)],
                })
    items.sort(key=lambda item: (_parse_ts(item.get('last_at')) or datetime.min.replace(tzinfo=timezone.utc), str(item.get('risk_id') or '')), reverse=True)
    return items


def scan(conn, day=None, limit=50):
    """读取指定北京时间日期的流水并返回风险条目。"""
    day_key = str(day or beijing_today())
    start, end = day_bounds(day_key)
    rows = conn.execute(
        '''SELECT t.id, t.user_id, t.currency, t.free_delta, t.paid_delta, t.reason,
                  t.source_type, t.source_id, t.created_at, u.username
           FROM user_currency_transactions t
           LEFT JOIN users u ON u.id = t.user_id
           WHERE datetime(t.created_at) >= datetime(?) AND datetime(t.created_at) < datetime(?)
           ORDER BY datetime(t.created_at) ASC, t.id ASC''',
        (start, end),
    ).fetchall()
    transactions = [dict(row) for row in rows]
    items = detect(transactions)
    counts = {}
    for item in items:
        counts[item['kind']] = counts.get(item['kind'], 0) + 1
    try:
        safe_limit = max(1, min(int(limit or 50), 200))
    except (TypeError, ValueError):
        safe_limit = 50
    return {
        'day': day_key,
        'scanned': len(transactions),
        'total': len(items),
        'counts': counts,
        'items': items[:safe_limit],
        'rules': {
            currency: {
                'label': rule['label'],
                'duplicate_amount': rule['duplicate_amount'],
                'duplicate_window_seconds': rule['duplicate_window_seconds'],
                'single_amount': rule['single_amount'],
                'daily_total': rule['daily_total'],
            }
            for currency, rule in RULES.items()
        },
    }
