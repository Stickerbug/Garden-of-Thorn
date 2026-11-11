# -*- coding: utf-8 -*-
"""爱发电赞助兑换：签名向量（官方文档示例）、绑定码、幂等入账、补结、webhook 路由。"""

from __future__ import annotations

import gc
import os
import tempfile
import unittest
from unittest import mock

import afdian_service
import db


def _app_available():
    try:
        import app as gtn
        return gtn, ''
    except Exception as exc:  # pragma: no cover
        return None, str(exc)


class AfdianServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'afdian.sqlite3')
        db.init_db()
        self.user, error = db.create_user('AfdianTester', 'Aa1!aaaa')
        self.assertIsNone(error)

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        gc.collect()          # sqlite 连接靠 GC 关闭，先收再删临时库（Windows 文件锁）
        self.temp_dir.cleanup()

    def _order(self, **kwargs):
        payload = {
            'out_trade_no': 'AFD20260924NO1',
            'user_id': 'afd-user-1',
            'user_private_id': 'union-1',
            'plan_id': 'plan_small',
            'month': 1,
            'total_amount': '10.00',
            'show_amount': '10.00',
            'status': 2,
            'remark': '',
        }
        payload.update(kwargs)
        return payload

    def test_api_sign_official_vector(self):
        # 官方文档示例：token=123、params={"a":333}、ts=1624339905、user_id=abc
        sign = afdian_service.api_sign('{"a":333}', 1624339905, 'abc', '123')
        self.assertEqual(sign, 'a4acc28b81598b7e5d84ebdc3e91710c')

    def test_bind_code_get_reset(self):
        code = afdian_service.bind_code_for(self.user['id'])
        self.assertRegex(code, r'^[A-Z2-9]{8}$')
        self.assertEqual(afdian_service.bind_code_for(self.user['id']), code)
        new_code = afdian_service.reset_bind_code(self.user['id'])
        self.assertNotEqual(new_code, code)
        self.assertEqual(afdian_service.bind_code_for(self.user['id']), new_code)

    def test_extract_bind_code_tolerates_messy_remarks(self):
        """留言识别：大小写/空格/前后缀标点与中文/全角字符都不影响；9 位串不误切。"""
        f = afdian_service.extract_bind_code
        self.assertEqual(f('ABCD2345'), 'ABCD2345')
        self.assertEqual(f('abcd2345'), 'ABCD2345')                      # 小写
        self.assertEqual(f('  ABCD2345  '), 'ABCD2345')                  # 空格
        self.assertEqual(f('赞助！ABCD2345，谢谢'), 'ABCD2345')          # 全角标点
        self.assertEqual(f('绑定码ABCD2345'), 'ABCD2345')                # 紧贴中文无空格
        self.assertEqual(f('ABCD2345谢谢投喂'), 'ABCD2345')              # 尾贴中文
        self.assertEqual(f('ＡＢＣＤ２３４５'), 'ABCD2345')              # 全角字母数字
        self.assertEqual(f('我的码是 abcd2345 感谢'), 'ABCD2345')        # 混合随意书写
        self.assertEqual(f('ABCD23456'), '')                             # 9 位串不误切
        self.assertEqual(f('XABCD2345'), '')                             # 前面多一位同理
        self.assertEqual(f(''), '')
        self.assertEqual(f('没有码'), '')

    def test_ingest_grants_titles_without_golden_dew_and_is_idempotent(self):
        code = afdian_service.bind_code_for(self.user['id'])
        db.adjust_user_golden_dew(self.user['id'], 7, reason='既有余额', source_type='test')
        result = afdian_service.ingest_order(self._order(remark=f'赞助！绑定码 {code}'))
        self.assertEqual(result['status'], 'credited')
        self.assertEqual(result['total_amount'], '10.00')
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 7)
        with db.get_db_connection() as conn:
            tx = conn.execute(
                "SELECT * FROM user_currency_transactions WHERE source_type='afdian' "
                'AND source_id=?', ('AFD20260924NO1',)).fetchone()
        self.assertIsNone(tx)
        titles = {item['id']: item for item in db.get_user_title_center(self.user['id'])['items']}
        self.assertIn('afdian:sponsor', titles)
        self.assertIn('afdian:major-sponsor', titles)
        self.assertEqual(titles['afdian:major-sponsor']['style']['segments'][0]['paint']['kind'], 'rainbow')
        again = afdian_service.ingest_order(self._order(remark=f'绑定码 {code}'))
        self.assertEqual(again['status'], 'duplicate')
        progress = afdian_service.sponsor_progress(self.user['id'])
        self.assertEqual(progress['total_fen'], 1000)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 7)
        titles = {item['id']: item for item in db.get_user_title_center(self.user['id'])['items']}
        self.assertEqual(titles['afdian:sponsor']['quantity'], 1)
        self.assertEqual(titles['afdian:major-sponsor']['quantity'], 1)

    def test_month_count_does_not_multiply_actual_order_amount(self):
        code = afdian_service.bind_code_for(self.user['id'])
        result = afdian_service.ingest_order(
            self._order(out_trade_no='AFD-M3', remark=code, month=3))
        self.assertEqual(result['status'], 'credited')
        self.assertEqual(result['amount_fen'], 1000)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 1000)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)

    def test_unmatched_order_does_not_count_until_a_valid_code_arrives(self):
        result = afdian_service.ingest_order(self._order(remark='没有码'))
        self.assertEqual(result['status'], 'unmatched')
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 0)
        code = afdian_service.bind_code_for(self.user['id'])
        result = afdian_service.ingest_order(
            self._order(out_trade_no='AFD-VALID', remark=f'码 {code}'))
        self.assertEqual(result['status'], 'credited')
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 1000)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)
        again = afdian_service.ingest_order(self._order(out_trade_no='AFD-VALID', remark=code))
        self.assertEqual(again['status'], 'duplicate')
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 1000)

    def test_non_success_order_is_ignored(self):
        result = afdian_service.ingest_order(self._order(status=1))
        self.assertEqual(result['status'], 'ignored')

    def test_renewal_without_remark_follows_afdian_user(self):
        """按月方案的自动续费单不带留言：同一爱发电账号此前到账过则自动认领入同一账号。"""
        code = afdian_service.bind_code_for(self.user['id'])
        with mock.patch.object(afdian_service, 'requery_recent', lambda **kw: {'ok': False}):
            afdian_service.admin_set_plan('plan_monthly', 500, '月档')
        first = afdian_service.ingest_order(
            self._order(out_trade_no='AFD-M1', remark=f'码 {code}',
                        plan_id='plan_monthly', user_id='afd-sub-1'))
        self.assertEqual(first['status'], 'credited')
        renewal = afdian_service.ingest_order(
            self._order(out_trade_no='AFD-M2', remark='',
                        plan_id='plan_monthly', user_id='afd-sub-1'))
        self.assertEqual(renewal['status'], 'credited')
        self.assertEqual(renewal['amount_fen'], 1000)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 2000)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)
        # 陌生爱发电账号的无留言单仍是 unmatched
        stranger = afdian_service.ingest_order(
            self._order(out_trade_no='AFD-M3', remark='',
                        plan_id='plan_monthly', user_id='afd-stranger'))
        self.assertEqual(stranger['status'], 'unmatched')

    def test_sale_orders_use_actual_amounts_even_with_legacy_skus(self):
        code = afdian_service.bind_code_for(self.user['id'])
        result = afdian_service.ingest_order({
            'out_trade_no': 'AFD-SKU1', 'plan_id': 'plan_shop', 'month': 1, 'status': 2,
            'remark': f'码 {code}', 'total_amount': '3.00',
            'sku_detail': [{'sku_id': 'sku-aaa', 'name': 'Y3 档', 'count': 2}],
        })
        self.assertEqual(result['status'], 'credited')
        self.assertEqual(result['amount_fen'], 300)
        combo = afdian_service.ingest_order({
            'out_trade_no': 'AFD-SKU2', 'plan_id': 'plan_shop', 'month': 1, 'status': 2,
            'remark': f'码 {code}', 'total_amount': '7.00',
            'sku_detail': [
                {'sku_id': 'sku-aaa', 'name': 'Y3 档', 'count': 1},
                {'sku_id': 'sku-bbb', 'name': 'Y1 档', 'count': 3},
            ],
        })
        self.assertEqual(combo['status'], 'credited')
        self.assertEqual(combo['amount_fen'], 700)
        renamed = afdian_service.ingest_order({
            'out_trade_no': 'AFD-SKU3', 'plan_id': 'plan_shop', 'month': 1, 'status': 2,
            'remark': f'码 {code}', 'total_amount': '3.00',
            'sku_detail': [{'sku_id': 'sku-aaa', 'name': '新名字了', 'count': 1}],
        })
        self.assertEqual(renamed['status'], 'credited')
        unknown = afdian_service.ingest_order({
            'out_trade_no': 'AFD-SKU4', 'plan_id': 'plan_shop', 'month': 1, 'status': 2,
            'remark': f'码 {code}', 'total_amount': '68.00',
            'sku_detail': [{'sku_id': 'sku-zzz', 'name': 'Y68 档', 'count': 1}],
        })
        self.assertEqual(unknown['status'], 'credited')
        self.assertEqual(unknown['amount_fen'], 6800)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 8100)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)

    def test_custom_amount_does_not_require_sku_mapping(self):
        code = afdian_service.bind_code_for(self.user['id'])
        result = afdian_service.ingest_order({
            'out_trade_no': 'AFD-CUSTOM', 'plan_id': 'custom', 'month': 1,
            'status': 2, 'remark': code, 'total_amount': '204.00',
            'sku_detail': [{'sku_id': 'sku-custom', 'name': '自定义赞助', 'count': 1}],
        })
        self.assertEqual(result['status'], 'credited')
        self.assertEqual(result['amount_fen'], 20400)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 20400)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)

    def test_tombstoned_order_cannot_be_recreated(self):
        with db.get_db_connection() as conn:
            afdian_service.ensure_schema(conn)
            conn.execute(
                "INSERT INTO afdian_order_tombstones(out_trade_no, reason, created_at) "
                "VALUES (?, ?, ?)",
                ('AFD-TOMBSTONE', 'manual compensation', '2026-10-27T12:00:00Z'),
            )
            conn.commit()
        result = afdian_service.ingest_order({
            'out_trade_no': 'AFD-TOMBSTONE', 'plan_id': 'plan_shop',
            'status': 2, 'remark': '', 'total_amount': '68.00',
        })
        self.assertEqual(result['status'], 'ignored')
        with db.get_db_connection() as conn:
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM afdian_orders WHERE out_trade_no=?",
                ('AFD-TOMBSTONE',),
            ).fetchone())

    def test_history_backfill_thresholds_styles_and_idempotence(self):
        def add_order(order_id, amount, status='credited'):
            with db.get_db_connection() as conn:
                afdian_service.ensure_schema(conn)
                conn.execute(
                    "INSERT INTO afdian_orders (out_trade_no, game_user_id, total_amount, status, received_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (order_id, self.user['id'], amount, status, '2026-10-01T00:00:00Z'),
                )
                conn.commit()

        add_order('HISTORY-099', '0.99')
        first = afdian_service.sync_all_sponsor_titles()
        self.assertEqual(first['granted_titles'], 0)
        self.assertEqual(db.get_user_title_center(self.user['id'])['items'], [])

        add_order('HISTORY-001', '0.01', status='manual')
        second = afdian_service.sync_all_sponsor_titles()
        self.assertEqual(second['granted_titles'], 1)
        titles = {item['id']: item for item in db.get_user_title_center(self.user['id'])['items']}
        self.assertIn('afdian:sponsor', titles)
        self.assertNotIn('afdian:major-sponsor', titles)
        self.assertEqual(titles['afdian:sponsor']['style']['segments'][0]['paint']['color'], '#808080')

        add_order('HISTORY-900', '9.00')
        third = afdian_service.sync_all_sponsor_titles()
        self.assertEqual(third['granted_titles'], 1)
        self.assertEqual(afdian_service.sync_all_sponsor_titles()['granted_titles'], 0)
        titles = {item['id']: item for item in db.get_user_title_center(self.user['id'])['items']}
        self.assertEqual(titles['afdian:sponsor']['quantity'], 1)
        self.assertEqual(titles['afdian:major-sponsor']['quantity'], 1)
        self.assertEqual(titles['afdian:major-sponsor']['style']['segments'][0]['paint']['kind'], 'rainbow')
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_amount'], '10.00')
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)

    def test_public_plans_lists_new_sponsor_tiers(self):
        plans = afdian_service.public_plans()
        self.assertEqual(
            [(p['name'], p['price'], p['kind']) for p in plans],
            [
                ('请开发组打两把舞萌', '3.00', 'sku'),
                ('为开发组购买喵斯快跑', '18.00', 'sku'),
                ('请开发组吃一顿疯狂星期四', '50.00', 'sku'),
                ('自定义', '', 'custom'),
            ],
        )
        self.assertTrue(all('dew_amount' not in plan for plan in plans))

    def test_no_sku_order_uses_actual_amount_for_fixed_and_custom_prices(self):
        code = afdian_service.bind_code_for(self.user['id'])
        result = afdian_service.ingest_order(self._order(
            out_trade_no='AFD-NOSKU', remark=f'码 {code}',
            total_amount='3.00', plan_id='plan_shop'))
        self.assertEqual(result['status'], 'credited')
        self.assertEqual(result['amount_fen'], 300)
        other = afdian_service.ingest_order(self._order(
            out_trade_no='AFD-NOSKU2', remark=f'码 {code}',
            total_amount='68.00', plan_id='custom'))
        self.assertEqual(other['status'], 'credited')
        self.assertEqual(other['amount_fen'], 6800)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 7100)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)

    def test_plan_set_zero_disables_mapping(self):
        with mock.patch.object(afdian_service, 'requery_recent', lambda **kw: {'ok': False}):
            r1 = afdian_service.admin_set_plan('plan_x', 500, '测试')
            self.assertEqual(r1.get('active'), 1)
            r2 = afdian_service.admin_set_plan('plan_x', 0)
            self.assertEqual(r2.get('active'), 0)
        plans = [p for p in afdian_service.public_plans() if p['kind'] == 'plan']
        self.assertFalse(any(p['plan_id'] == 'plan_x' for p in plans))

    def test_page_url_setting_roundtrip(self):
        """爱发电主页链接：设置/读取/清除；非 afdian.com 域名拒绝。"""
        self.assertEqual(afdian_service.get_page_url(), '')
        r = afdian_service.admin_set_page_url('afdian.com/a/stickerbug/')
        self.assertTrue(r.get('ok'), r)
        self.assertEqual(r['page_url'], 'https://afdian.com/a/stickerbug')
        self.assertEqual(afdian_service.get_page_url(), 'https://afdian.com/a/stickerbug')
        bad = afdian_service.admin_set_page_url('https://evil.example/x')
        self.assertFalse(bad.get('ok'))
        r2 = afdian_service.admin_set_page_url('')
        self.assertTrue(r2.get('ok'))
        self.assertEqual(afdian_service.get_page_url(), '')

    def test_admin_credit_manual(self):
        afdian_service.ingest_order(self._order(out_trade_no='AFD-BAD', remark='忘了写码'))
        result = afdian_service.admin_credit('AFD-BAD', self.user['id'])
        self.assertTrue(result.get('ok'))
        self.assertEqual(result['total_amount'], '10.00')
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 1000)
        with db.get_db_connection() as conn:
            row = conn.execute(
                "SELECT status FROM afdian_orders WHERE out_trade_no='AFD-BAD'").fetchone()
        self.assertEqual(row['status'], 'manual')


@unittest.skipIf(not _app_available()[0], f'无法导入 app（{_app_available()[1]}）')
class AfdianWebhookRouteTests(unittest.TestCase):
    def setUp(self):
        self._app, _ = _app_available()
        self.client = self._app.app.test_client()
        self.old_db_path = db.DB_PATH
        self.old_available = self._app.DB_AVAILABLE
        self.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.temp_dir.name, 'afdian-route.sqlite3')
        db.init_db()
        self._app.DB_AVAILABLE = True
        self.user, error = db.create_user('AfdianRoute', 'Bb2!bbbb')
        self.assertIsNone(error)

    def tearDown(self):
        self._app.DB_AVAILABLE = self.old_available
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_webhook_secret_and_ingest(self):
        code = afdian_service.bind_code_for(self.user['id'])
        with mock.patch.object(afdian_service, 'requery_recent', lambda **kw: {'ok': False}):
            afdian_service.admin_set_plan('plan_small', 1000, '¥10 档')
        with mock.patch.dict(os.environ, {'GTN_AFDIAN_WEBHOOK_SECRET': 's3cret'}):
            wrong = self.client.post('/api/afdian/webhook/nope', json={})
            self.assertEqual(wrong.status_code, 403)
            payload = {'ec': 200, 'em': 'ok', 'data': {'type': 'order', 'order': {
                'out_trade_no': 'AFD-WH1', 'plan_id': 'plan_small', 'month': 1,
                'status': 2, 'remark': f'绑定码 {code}', 'total_amount': '10.00'}}}
            ok = self.client.post('/api/afdian/webhook/s3cret', json=payload)
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.get_json()['ec'], 200)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)
        self.assertEqual(afdian_service.sponsor_progress(self.user['id'])['total_fen'], 1000)



    def test_entry_open_to_all_accounts(self):
        """赞助入口对全员开放（2026-09-24）：任意登录账号页面 200、API 可用、主页渲染赞助 tab。"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user['id']
            sess['username'] = 'AfdianRoute'
        with mock.patch.object(self._app, 'feedback_is_staff', lambda uid: False):
            page = self.client.get('/afdian')
            self.assertEqual(page.status_code, 200)
            api = self.client.get('/api/afdian/status')
            self.assertEqual(api.status_code, 200)
            self.assertIn('bind_code', api.get_json())
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        home_html = home.get_data(as_text=True)
        # 入口在商店头部「赞助」按钮（tab 已撤），面板与前往爱发电链接常驻
        self.assertIn('btn-title-shop-afdian', home_html)
        self.assertIn('title-shop-afdian-panel', home_html)
        self.assertIn('title-shop-afdian-go', home_html)
        self.assertNotIn('title-shop-tab-afdian', home_html)

if __name__ == '__main__':
    unittest.main()
