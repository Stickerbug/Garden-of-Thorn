# -*- coding: utf-8 -*-
"""主题／战斗背景目录、每日刷新、购买库存与装备偏好。"""

import gc
import os
from pathlib import Path
import tempfile
import unittest

import backgrounds
import db


ROOT = Path(__file__).resolve().parents[1]


class BackgroundInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'backgrounds.sqlite3')
        db.init_db()
        self.user, error = db.create_user('BackgroundOwner1', 'Passw0rd!xyz')
        assert self.user, error
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET thorn_dew_free = 100000 WHERE id = ?', (self.user['id'],))
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def payload(self):
        with db.get_db_connection() as conn:
            return backgrounds.get_background_payload(conn, self.user['id'])

    def test_catalog_offers_and_guest_defaults(self):
        payload = self.payload()
        self.assertEqual(payload['preferences'], {'theme': 'classic', 'battle': 'classic'})
        for kind in backgrounds.BACKGROUND_KINDS:
            shop = payload['shops'][kind]
            self.assertEqual(len(shop['items']), 7)
            ids = {item['background_id'] for item in shop['items']}
            self.assertEqual('tower_curse_dark_harbor' in ids, kind == 'battle')
            self.assertEqual(shop['owned_background_ids'], ['classic'])
            self.assertEqual(shop['equipped'], 'classic')
            self.assertEqual(shop['refresh_cost'], 700)
            self.assertEqual(shop['offer_count'], 3)
            self.assertEqual(len(shop['offers']), 3)
            self.assertEqual(len({offer['background_id'] for offer in shop['offers']}), 3)
            self.assertNotIn('classic', {offer['background_id'] for offer in shop['offers']})
            for offer in shop['offers']:
                self.assertEqual(offer['price'], 10000)
                self.assertEqual(offer['weight'], 5)
            classic = next(item for item in shop['items'] if item['background_id'] == 'classic')
            self.assertTrue(classic['owned'])
            self.assertTrue(classic['equipped'])
            self.assertEqual(classic['price'], 0)
        self.assertNotIn('olive_nocturne', backgrounds.BACKGROUND_BY_KEY)
        self.assertNotIn('desert_mist', backgrounds.BACKGROUND_BY_KEY)
        self.assertNotIn('parchment_grove', backgrounds.BACKGROUND_BY_KEY)
        guest = backgrounds.get_background_payload(None, None)
        self.assertEqual(guest['preferences'], payload['preferences'])
        self.assertEqual(guest['shops']['theme']['offers'], [])

    def test_purchase_and_equipment_are_independent_and_persistent(self):
        before = db.get_user_thorn_dew(self.user['id'])['total']
        shop = self.payload()['shops']['theme']
        offer = shop['offers'][0]
        payload, error = backgrounds.purchase_background(self.user['id'], 'theme', shop['set_id'], offer['slot'])
        self.assertIsNone(error)
        background_id = offer['background_id']
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 10000)
        self.assertIn(background_id, payload['shops']['theme']['owned_background_ids'])
        self.assertEqual(payload['shops']['theme']['equipped'], 'classic')
        with db.get_db_connection() as conn:
            transaction = conn.execute(
                "SELECT reason, source_type, source_id, free_delta FROM user_currency_transactions WHERE user_id = ? AND source_type = 'background_purchase'",
                (self.user['id'],),
            ).fetchone()
            self.assertEqual(transaction['reason'], '购买背景：' + offer['name'])
            self.assertEqual(transaction['source_id'], f"{shop['set_id']}:{offer['slot']}")
            self.assertEqual(transaction['free_delta'], -10000)
            self.assertIsNone(backgrounds.equip_background(conn, self.user['id'], 'theme', background_id))
            conn.commit()
        equipped = self.payload()
        self.assertEqual(equipped['preferences']['theme'], background_id)
        self.assertEqual(equipped['preferences']['battle'], 'classic')
        battle_shop = self.payload()['shops']['battle']
        battle_offer = battle_shop['offers'][0]
        _, error = backgrounds.purchase_background(self.user['id'], 'battle', battle_shop['set_id'], battle_offer['slot'])
        self.assertIsNone(error)
        with db.get_db_connection() as conn:
            self.assertIsNone(backgrounds.equip_background(conn, self.user['id'], 'battle', battle_offer['background_id']))
            conn.commit()
        equipped = self.payload()
        self.assertEqual(equipped['preferences'], {'theme': background_id, 'battle': battle_offer['background_id']})
        _, error = backgrounds.purchase_background(self.user['id'], 'theme', shop['set_id'], offer['slot'])
        self.assertEqual(error, '本轮已购买该商品')

    def test_refresh_costs_old_set_rejection_and_daily_reset(self):
        shop = self.payload()['shops']['theme']
        old_set = shop['set_id']
        before = db.get_user_thorn_dew(self.user['id'])['total']
        refreshed, error = backgrounds.refresh_background_shop(self.user['id'], 'theme')
        self.assertIsNone(error)
        self.assertNotEqual(refreshed['shops']['theme']['set_id'], old_set)
        self.assertEqual(refreshed['shops']['theme']['refresh_cost'], 1000)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 700)
        battle_before = db.get_user_thorn_dew(self.user['id'])['total']
        battle_refreshed, error = backgrounds.refresh_background_shop(self.user['id'], 'battle')
        self.assertIsNone(error)
        self.assertEqual(battle_refreshed['shops']['battle']['refresh_cost'], 1000)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], battle_before - 700)
        self.assertEqual(battle_refreshed['shops']['theme']['refresh_cost'], 1000)
        _, error = backgrounds.purchase_background(self.user['id'], 'theme', old_set, 1)
        self.assertEqual(error, '商店内容已刷新，请按当前商品操作')
        with db.get_db_connection() as conn:
            conn.execute(
                "UPDATE background_shop_user_state SET refresh_date = '2000-01-01', refresh_count = 4 WHERE user_id = ? AND kind = 'theme'",
                (self.user['id'],),
            )
            conn.commit()
        self.assertEqual(self.payload()['shops']['theme']['refresh_cost'], 700)

    def test_unowned_invalid_and_unaffordable_requests_are_rejected(self):
        with db.get_db_connection() as conn:
            self.assertEqual(backgrounds.equip_background(conn, self.user['id'], 'battle', 'factory'), '尚未拥有该背景')
            self.assertEqual(backgrounds.equip_background(conn, self.user['id'], 'other', 'classic'), '背景不存在')
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?', (self.user['id'],))
            conn.commit()
        shop = self.payload()['shops']['battle']
        offer = shop['offers'][0]
        _, error = backgrounds.purchase_background(self.user['id'], 'battle', shop['set_id'], offer['slot'])
        self.assertEqual(error, '荆露不足')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        theme_shop = self.payload()['shops']['theme']
        _, error = backgrounds.purchase_background(self.user['id'], 'theme', theme_shop['set_id'], 99)
        self.assertEqual(error, '商品不存在或已下架')


class BackgroundFrontendContractTests(unittest.TestCase):
    def test_api_routes_exist(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        for route in ('/api/backgrounds', '/api/backgrounds/purchase', '/api/backgrounds/refresh', '/api/backgrounds/equip'):
            self.assertIn(route, source)


if __name__ == '__main__':
    unittest.main()
