# -*- coding: utf-8 -*-
"""玩家皮肤商店：目录、扣款、库存、装备与前端契约。"""

import gc
import os
from pathlib import Path
import tempfile
import unittest

import db
import player_skins


ROOT = Path(__file__).resolve().parents[1]


class PlayerSkinShopTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'player-skins.sqlite3')
        db.init_db()
        self.user, error = db.create_user('PlayerSkinOwner1', 'Passw0rd!xyz')
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
            return player_skins.player_skin_payload(conn, self.user['id'])

    def shop(self):
        shop, error = player_skins.get_player_skin_shop(self.user['id'])
        self.assertIsNone(error)
        return shop

    def test_catalog_matches_requested_prices_and_weights(self):
        expected = {
            'classic', 'faceless', 'ghost', 'brain_damage', 'corrupted', 'mark', 'nazar', 'right_angle',
            'centipede_head', 'desert_centipede_head', 'evil_centipede_head',
            'tower_curse_ironclad', 'tower_curse_silent', 'tower_curse_defect',
            'tower_curse_necrobinder', 'tower_curse_regent',
        }
        self.assertEqual(set(player_skins.PLAYER_SKIN_BY_ID), expected)
        self.assertEqual(set(player_skins.PLAYER_SKIN_BY_ID), db.SKIN_IDS)
        self.assertNotIn('sprout', expected)
        self.assertNotIn('thorn', expected)
        expected_shop = {
            'faceless': (20000, 2), 'ghost': (20000, 2),
            'brain_damage': (50000, 1), 'mark': (20000, 2), 'nazar': (20000, 2),
            'right_angle': (10000, 5),
            'centipede_head': (20000, 5), 'desert_centipede_head': (20000, 5),
            'evil_centipede_head': (20000, 5),
        }
        self.assertEqual(player_skins.PLAYER_SKIN_BY_ID['classic']['price'], 0)
        self.assertEqual(player_skins.PLAYER_SKIN_BY_ID['classic']['weight'], 0)
        self.assertEqual(player_skins.PLAYER_SKIN_BY_ID['corrupted']['price'], 10000)
        self.assertEqual(player_skins.PLAYER_SKIN_BY_ID['corrupted']['weight'], 0)
        for skin_id, (price, weight) in expected_shop.items():
            self.assertEqual(player_skins.PLAYER_SKIN_BY_ID[skin_id]['price'], price)
            self.assertEqual(player_skins.PLAYER_SKIN_BY_ID[skin_id]['weight'], weight)

    def test_daily_shop_has_three_unique_weighted_offers(self):
        shop = self.shop()
        self.assertEqual(len(shop['offers']), 3)
        self.assertEqual(len({offer['skin_id'] for offer in shop['offers']}), 3)
        offer_ids = {offer['skin_id'] for offer in shop['offers']}
        self.assertNotIn('classic', offer_ids)
        self.assertNotIn('corrupted', offer_ids)
        self.assertEqual(shop['refresh_cost'], 700)
        self.assertEqual(shop['owned_skin_ids'], ['classic'])
        self.assertTrue(shop['set_id'].startswith('daily:'))
        for offer in shop['offers']:
            definition = player_skins.PLAYER_SKIN_BY_ID[offer['skin_id']]
            self.assertGreater(definition['weight'], 0)
            self.assertEqual(offer['price'], definition['price'])
        self.assertEqual(self.shop()['set_id'], shop['set_id'])

    def test_delisted_corrupted_set_is_replaced_but_owned_skin_still_works(self):
        old_set = self.shop()['set_id']
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE player_skin_shop_offers SET skin_id = ?, price = ? WHERE set_id = ? AND slot = 1',
                ('corrupted', 10000, old_set),
            )
            conn.execute(
                "INSERT INTO user_player_skins (user_id, skin_id, acquired_source, acquired_ref, acquired_at) VALUES (?, 'corrupted', 'legacy', NULL, ?)",
                (self.user['id'], db.utc_now()),
            )
            conn.commit()
        before = db.get_user_thorn_dew(self.user['id'])['total']
        replaced = self.shop()
        self.assertNotEqual(replaced['set_id'], old_set)
        self.assertEqual(len(replaced['offers']), 3)
        self.assertNotIn('corrupted', {offer['skin_id'] for offer in replaced['offers']})
        self.assertEqual(self.shop()['set_id'], replaced['set_id'])
        _, error = player_skins.purchase_player_skin_offer(self.user['id'], old_set, 1)
        self.assertEqual(error, '商店内容已刷新，请按当前商品操作')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before)
        corrupted = next(item for item in self.payload()['items'] if item['skin_id'] == 'corrupted')
        self.assertTrue(corrupted['owned'])
        with db.get_db_connection() as conn:
            self.assertIsNone(player_skins.equip_player_skin(conn, self.user['id'], 'corrupted'))
            conn.commit()
        self.assertEqual(self.payload()['equipped'], 'corrupted')

    def test_purchase_is_atomic_and_equip_preserves_face_config(self):
        initial = self.payload()
        classic = next(item for item in initial['items'] if item['skin_id'] == 'classic')
        self.assertTrue(classic['owned'])
        self.assertTrue(classic['equipped'])
        shop = self.shop()
        target = shop['offers'][0]
        before = db.get_user_thorn_dew(self.user['id'])['total']
        purchased, error = player_skins.purchase_player_skin_offer(
            self.user['id'], shop['set_id'], target['slot'],
        )
        self.assertIsNone(error)
        bought = next(item for item in purchased['offers'] if item['skin_id'] == target['skin_id'])
        self.assertTrue(bought['owned'])
        self.assertIn(target['skin_id'], purchased['owned_skin_ids'])
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - target['price'])
        with db.get_db_connection() as conn:
            transaction = conn.execute(
                "SELECT reason, source_type, source_id, free_delta FROM user_currency_transactions WHERE user_id = ? AND source_type = 'player_skin_purchase'",
                (self.user['id'],),
            ).fetchone()
        self.assertEqual(transaction['reason'], '购买玩家皮肤：' + target['name'])
        self.assertEqual(transaction['source_id'], f"{shop['set_id']}:{target['slot']}")
        self.assertEqual(transaction['free_delta'], -target['price'])

        _, error = player_skins.purchase_player_skin_offer(self.user['id'], shop['set_id'], target['slot'])
        self.assertEqual(error, '本轮已购买该商品')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - target['price'])

        with db.get_db_connection() as conn:
            self.assertIsNone(player_skins.equip_player_skin(conn, self.user['id'], target['skin_id']))
            conn.commit()
        updated, error = db.update_user_skin(self.user['id'], {
            'skin_id': target['skin_id'], 'primary_color': '#abcdef', 'eye_shape': 'diamond',
        })
        self.assertIsNone(error)
        self.assertEqual(updated['skin']['skin_id'], target['skin_id'])
        self.assertEqual(updated['skin']['primary_color'], '#ABCDEF')
        self.assertEqual(updated['skin']['eye_shape'], 'diamond')
        unowned = next(skin_id for skin_id in player_skins.PLAYER_SKIN_BY_ID if skin_id not in ('classic', target['skin_id']))
        _, error = db.update_user_skin(self.user['id'], {'skin_id': unowned})
        self.assertEqual(error, '尚未拥有该玩家皮肤')
        self.assertEqual(self.payload()['equipped'], target['skin_id'])

    def test_insufficient_balance_and_invalid_slot_do_not_unlock(self):
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?', (self.user['id'],))
            conn.commit()
        shop = self.shop()
        target = shop['offers'][0]
        _, error = player_skins.purchase_player_skin_offer(self.user['id'], shop['set_id'], target['slot'])
        self.assertEqual(error, '荆露不足')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        _, error = player_skins.purchase_player_skin_offer(self.user['id'], shop['set_id'], 99)
        self.assertEqual(error, '商品不存在或已下架')

    def test_refresh_cost_increments_and_resets_next_day(self):
        shop = self.shop()
        old_set = shop['set_id']
        before = db.get_user_thorn_dew(self.user['id'])['total']
        refreshed, error = player_skins.refresh_player_skin_shop(self.user['id'])
        self.assertIsNone(error)
        self.assertNotEqual(refreshed['set_id'], old_set)
        self.assertEqual(refreshed['refresh_cost'], 1000)
        self.assertEqual(len({offer['skin_id'] for offer in refreshed['offers']}), 3)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 700)
        refreshed, error = player_skins.refresh_player_skin_shop(self.user['id'])
        self.assertIsNone(error)
        self.assertEqual(refreshed['refresh_cost'], 1300)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 1700)
        _, error = player_skins.purchase_player_skin_offer(self.user['id'], old_set, 1)
        self.assertEqual(error, '商店内容已刷新，请按当前商品操作')
        with db.get_db_connection() as conn:
            conn.execute(
                "UPDATE player_skin_shop_user_state SET refresh_date = '2000-01-01', refresh_count = 4 WHERE user_id = ?",
                (self.user['id'],),
            )
            conn.commit()
        self.assertEqual(self.shop()['refresh_cost'], 700)


class PlayerSkinShopFrontendContractTests(unittest.TestCase):
    def test_shop_tab_panel_routes_and_actions_exist(self):
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        css = (ROOT / 'static/css/player-skins.css').read_text(encoding='utf-8')
        self.assertIn('data-shop-tab="player-skins"', index)
        self.assertIn('id="player-skin-shop-panel"', index)
        self.assertIn('id="player-skin-shop-grid"', index)
        for route in ('/api/player-skins', '/api/player-skins/refresh', '/api/player-skins/purchase', '/api/player-skins/equip'):
            self.assertIn(route, app)
            self.assertIn(route, game)
        for marker in ('loadPlayerSkinShop', 'refreshPlayerSkinShop', 'purchasePlayerSkinFromShop', 'equipPlayerSkinFromShop'):
            self.assertIn(marker, game)
        self.assertIn('loadPlayerSkinOwnership', game)
        self.assertIn('availableDefinitions', game)
        self.assertIn('owned_skin_ids', game)
        self.assertIn('owned_skin_ids', (ROOT / 'player_skins.py').read_text(encoding='utf-8'))
        self.assertIn('.player-skin-shop-item', css)
        self.assertIn("skin_id !== 'classic'", game)


if __name__ == '__main__':
    unittest.main()
