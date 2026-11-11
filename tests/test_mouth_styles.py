# -*- coding: utf-8 -*-
"""嘴型款式商店、永久库存、装备与前端资源契约。"""

import gc
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import app
import db
import mouth_styles


ROOT = Path(__file__).resolve().parents[1]


class MouthStyleShopTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'mouth-styles.sqlite3')
        db.init_db()
        self.user, error = db.create_user('MouthStyleOwner', 'Passw0rd!xyz')
        assert self.user, error
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET thorn_dew_free = 100000 WHERE id = ?', (self.user['id'],))
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def shop(self):
        shop, error = mouth_styles.get_mouth_style_shop(self.user['id'])
        self.assertIsNone(error)
        return shop

    def test_catalog_and_daily_offers(self):
        self.assertEqual(mouth_styles.BASE_MOUTH_SHAPES, {'original'})
        self.assertEqual(mouth_styles.MOUTH_STYLE_BY_ID['original']['price'], 0)
        for mouth_shape in ('cat', 'smirk', 'open', 'angry'):
            self.assertEqual(mouth_styles.MOUTH_STYLE_BY_ID[mouth_shape]['price'], 5000)
            self.assertEqual(mouth_styles.MOUTH_STYLE_BY_ID[mouth_shape]['weight'], 5)
            self.assertIn(mouth_shape, db.SKIN_MOUTH_SHAPES)
        shop = self.shop()
        self.assertEqual(len(shop['offers']), 3)
        offer_ids = {item['mouth_shape'] for item in shop['offers']}
        self.assertEqual(len(offer_ids), 3)
        self.assertTrue(offer_ids.issubset({'cat', 'smirk', 'open', 'angry'}))
        self.assertEqual(shop['refresh_cost'], 700)
        self.assertEqual(set(shop['owned_mouth_shapes']), mouth_styles.BASE_MOUTH_SHAPES)
        self.assertTrue(shop['set_id'].startswith('mouth:'))
        self.assertEqual(self.shop()['set_id'], shop['set_id'])

    def test_purchase_equip_preserves_player_skin_and_rejects_duplicates(self):
        shop = self.shop()
        target = shop['offers'][0]
        # 模拟调价前已生成的商品，购买时仍必须按新价格 5000 扣款。
        with db.get_db_connection() as conn:
            conn.execute('UPDATE mouth_shop_offers SET price = 10000 WHERE set_id = ?', (shop['set_id'],))
            conn.commit()
        before = db.get_user_thorn_dew(self.user['id'])['total']
        purchased, error = mouth_styles.purchase_mouth_style_offer(
            self.user['id'], shop['set_id'], target['slot'],
        )
        self.assertIsNone(error)
        self.assertIn(target['mouth_shape'], purchased['owned_mouth_shapes'])
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - target['price'])
        with db.get_db_connection() as conn:
            transaction = conn.execute(
                "SELECT reason, source_type, source_id, free_delta FROM user_currency_transactions WHERE user_id = ? AND source_type = 'mouth_style_purchase'",
                (self.user['id'],),
            ).fetchone()
        self.assertEqual(transaction['reason'], '购买嘴型：' + target['name'])
        self.assertEqual(transaction['source_type'], 'mouth_style_purchase')
        self.assertEqual(transaction['source_id'], f"{shop['set_id']}:{target['slot']}")
        self.assertEqual(transaction['free_delta'], -target['price'])
        _, error = mouth_styles.purchase_mouth_style_offer(
            self.user['id'], shop['set_id'], target['slot'],
        )
        self.assertEqual(error, '本轮已购买该商品')
        with db.get_db_connection() as conn:
            self.assertIsNone(mouth_styles.equip_mouth_style(conn, self.user['id'], target['mouth_shape']))
            conn.commit()
        updated, error = db.update_user_skin(self.user['id'], {
            'skin_id': 'classic', 'primary_color': '#abcdef', 'mouth_shape': target['mouth_shape'],
        })
        self.assertIsNone(error)
        self.assertEqual(updated['skin']['skin_id'], 'classic')
        self.assertEqual(updated['skin']['primary_color'], '#ABCDEF')
        self.assertEqual(updated['skin']['mouth_shape'], target['mouth_shape'])
        unowned = next(value for value in ('cat', 'smirk', 'open', 'angry') if value != target['mouth_shape'])
        _, error = db.update_user_skin(self.user['id'], {'mouth_shape': unowned})
        self.assertEqual(error, '尚未拥有这款嘴型')

    def test_insufficient_balance_and_refreshed_set_do_not_unlock(self):
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?', (self.user['id'],))
            conn.commit()
        shop = self.shop()
        target = shop['offers'][0]
        _, error = mouth_styles.purchase_mouth_style_offer(self.user['id'], shop['set_id'], target['slot'])
        self.assertEqual(error, '荆露不足')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        _, error = mouth_styles.purchase_mouth_style_offer(self.user['id'], shop['set_id'], 99)
        self.assertEqual(error, '商品不存在或已下架')

    def test_refresh_cost_increments_and_resets_next_day(self):
        shop = self.shop()
        before = db.get_user_thorn_dew(self.user['id'])['total']
        refreshed, error = mouth_styles.refresh_mouth_style_shop(self.user['id'])
        self.assertIsNone(error)
        self.assertNotEqual(refreshed['set_id'], shop['set_id'])
        self.assertEqual(refreshed['refresh_cost'], 1000)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 700)
        refreshed, error = mouth_styles.refresh_mouth_style_shop(self.user['id'])
        self.assertIsNone(error)
        self.assertEqual(refreshed['refresh_cost'], 1300)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 1700)
        _, error = mouth_styles.purchase_mouth_style_offer(self.user['id'], shop['set_id'], 1)
        self.assertEqual(error, '商店内容已刷新，请按当前商品操作')
        with db.get_db_connection() as conn:
            conn.execute(
                "UPDATE mouth_shop_user_state SET refresh_date = '2000-01-01', refresh_count = 4 WHERE user_id = ?",
                (self.user['id'],),
            )
            conn.commit()
        self.assertEqual(self.shop()['refresh_cost'], 700)

    def test_mouth_style_api_returns_shop_and_owned_shapes(self):
        app.app.config.update(TESTING=True)
        client = app.app.test_client()
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            response = client.get('/api/mouth-styles')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['shop']['offers']), 3)
        self.assertEqual(set(payload['shop']['owned_mouth_shapes']), mouth_styles.BASE_MOUTH_SHAPES)


class MouthStyleFrontendContractTests(unittest.TestCase):
    def test_shop_inventory_form_and_api_routes_exist(self):
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        for marker in ('data-shop-tab="mouth-styles"', 'id="mouth-style-shop-panel"', 'id="mouth-style-shop-grid"'):
            self.assertIn(marker, index)
        self.assertLess(index.index('id="skin-eye-shape"'), index.index('id="skin-mouth-shape"'))
        for mouth_shape in ('original', 'cat', 'smirk', 'open', 'angry'):
            self.assertIn(f'value="{mouth_shape}"', index)
        for mouth_shape in ('cat', 'smirk', 'open', 'angry'):
            self.assertIn(f"/static/assets/mouth-styles/{mouth_shape}.svg", (ROOT / 'static/js/mouth-styles.js').read_text(encoding='utf-8'))
        for route in ('/api/mouth-styles', '/api/mouth-styles/refresh', '/api/mouth-styles/purchase', '/api/mouth-styles/equip'):
            self.assertIn(route, source)
            self.assertIn(route, game)
        for marker in ('loadMouthStyleOwnership', 'updateSkinMouthShapeOptions', 'activePlayerShopKind', 'mouthStyleShopActive', 'mouthStyleOwnershipUserId'):
            self.assertIn(marker, game)
        self.assertIn('尚未拥有这款嘴型', game)

    def test_player_shop_route_helper_accepts_both_action_forms(self):
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        start = game.index('const PLAYER_SHOP_ROUTES')
        end = game.index('let rankCardsShopActive', start)
        segment = game[start:end]
        self.assertIn("const route = String(action || 'list').replace(/^\\/+/, '') || 'list';", segment)
        for kind in ('mouth', 'player'):
            base = '/api/mouth-styles' if kind == 'mouth' else '/api/player-skins'
            cases = {'': '', 'list': '', '/refresh': '/refresh', 'refresh': '/refresh', '/purchase': '/purchase', 'purchase': '/purchase', '/equip': '/equip', 'equip': '/equip'}
            for action, suffix in cases.items():
                route = action.lstrip('/') or 'list'
                self.assertIn(f"{route}: '{base + suffix}'", segment)

    def test_shared_mouth_art_assets_and_renderers(self):
        for mouth_shape in ('cat', 'smirk', 'open', 'angry'):
            asset = ROOT / 'static/assets/mouth-styles' / f'{mouth_shape}.svg'
            self.assertTrue(asset.is_file())
            root = ET.parse(asset).getroot()
            self.assertEqual(root.attrib.get('viewBox'), '0 0 100 56')
        for template, renderer in (
            ('templates/index.html', 'game.js'),
            ('templates/story.html', 'story.js'),
            ('templates/minigame_suika.html', 'minigame_suika.js'),
        ):
            page = (ROOT / template).read_text(encoding='utf-8')
            self.assertIn('/static/css/mouth-styles.css', page)
            self.assertLess(page.index('/static/js/mouth-styles.js'), page.index(renderer))
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        story = (ROOT / 'static/js/story.js').read_text(encoding='utf-8')
        suika = (ROOT / 'static/js/minigame_suika.js').read_text(encoding='utf-8')
        self.assertIn('window.GTNMouthStyles?.render(mouthShape)', game)
        self.assertIn('window.GTNMouthStyles?.render(skin.mouthShape)', story)
        self.assertIn("insertAdjacentHTML('beforebegin', window.GTNMouthStyles?.render(seatSkin.mouthShape)", story)
        self.assertIn('window.GTNMouthStyles?.render(mouthShape)', suika)
        self.assertIn('playerMouthArt', suika)
        self.assertIn('target.drawImage(playerMouthArt,', suika)
        self.assertIn('${mouthArt}\n                <svg class="skin-mouth"', game)
        self.assertIn('${mouthArt}\n                <svg class="skin-mouth"', story)
        mouth_catalog = (ROOT / 'static/js/mouth-styles.js').read_text(encoding='utf-8')
        for mouth_shape in ('cat', 'smirk', 'open', 'angry'):
            self.assertIn(f"id: '{mouth_shape}', asset:", mouth_catalog)
        self.assertIn("return byId.has(id) ? id : 'original'", mouth_catalog)
        css = (ROOT / 'static/css/mouth-styles.css').read_text(encoding='utf-8')
        self.assertIn('skin-mouth-art', css)
        self.assertIn(':not(.is-defeated) .skin-mouth', css)
        for marker in ('.skin-avatar.skin-mouth-hurt .skin-mouth-art', '.skin-avatar.is-defeated .skin-mouth-art', '.skin-avatar.skin-hide-mouth .skin-mouth-art', '.skin-avatar.phelren-avatar .skin-mouth-art'):
            self.assertIn(marker, css)



if __name__ == '__main__':
    unittest.main()
