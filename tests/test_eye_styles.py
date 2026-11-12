# -*- coding: utf-8 -*-
"""眼睛款式商店、永久库存、装备与前端资源契约。"""

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
import eye_styles


ROOT = Path(__file__).resolve().parents[1]


class EyeStyleShopTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'eye-styles.sqlite3')
        db.init_db()
        self.user, error = db.create_user('EyeStyleOwner', 'Passw0rd!xyz')
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
        shop, error = eye_styles.get_eye_style_shop(self.user['id'])
        self.assertIsNone(error)
        return shop

    def test_catalog_and_daily_offers(self):
        self.assertEqual(eye_styles.BASE_EYE_SHAPES, {'oval', 'rectangle', 'diamond', 'hexagon'})
        for eye_shape in ('angry', 'coin', 'dizzy'):
            self.assertEqual(eye_styles.EYE_STYLE_BY_ID[eye_shape]['price'], 10000)
            self.assertEqual(eye_styles.EYE_STYLE_BY_ID[eye_shape]['weight'], 5)
            self.assertIn(eye_shape, db.SKIN_EYE_SHAPES)
        shop = self.shop()
        self.assertEqual(len(shop['offers']), 3)
        self.assertEqual({item['eye_shape'] for item in shop['offers']}, {'angry', 'coin', 'dizzy'})
        self.assertEqual(shop['refresh_cost'], 700)
        self.assertEqual(set(shop['owned_eye_shapes']), eye_styles.BASE_EYE_SHAPES)
        self.assertTrue(shop['set_id'].startswith('eye:'))
        self.assertEqual(self.shop()['set_id'], shop['set_id'])

    def test_purchase_equip_preserves_player_skin_and_rejects_duplicates(self):
        shop = self.shop()
        target = shop['offers'][0]
        before = db.get_user_thorn_dew(self.user['id'])['total']
        purchased, error = eye_styles.purchase_eye_style_offer(
            self.user['id'], shop['set_id'], target['slot'],
        )
        self.assertIsNone(error)
        self.assertIn(target['eye_shape'], purchased['owned_eye_shapes'])
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - target['price'])
        with db.get_db_connection() as conn:
            transaction = conn.execute(
                "SELECT reason, source_type, source_id, free_delta FROM user_currency_transactions WHERE user_id = ? AND source_type = 'eye_style_purchase'",
                (self.user['id'],),
            ).fetchone()
        self.assertEqual(transaction['reason'], '购买眼睛：' + target['name'])
        self.assertEqual(transaction['source_type'], 'eye_style_purchase')
        self.assertEqual(transaction['source_id'], f"{shop['set_id']}:{target['slot']}")
        self.assertEqual(transaction['free_delta'], -target['price'])
        _, error = eye_styles.purchase_eye_style_offer(
            self.user['id'], shop['set_id'], target['slot'],
        )
        self.assertEqual(error, '本轮已购买该商品')
        with db.get_db_connection() as conn:
            self.assertIsNone(eye_styles.equip_eye_style(conn, self.user['id'], target['eye_shape']))
            conn.commit()
        updated, error = db.update_user_skin(self.user['id'], {
            'skin_id': 'classic', 'primary_color': '#abcdef', 'eye_shape': target['eye_shape'],
        })
        self.assertIsNone(error)
        self.assertEqual(updated['skin']['skin_id'], 'classic')
        self.assertEqual(updated['skin']['primary_color'], '#ABCDEF')
        self.assertEqual(updated['skin']['eye_shape'], target['eye_shape'])
        unowned = next(value for value in ('angry', 'coin', 'dizzy') if value != target['eye_shape'])
        _, error = db.update_user_skin(self.user['id'], {'eye_shape': unowned})
        self.assertEqual(error, '尚未拥有这款眼睛')

    def test_insufficient_balance_and_refreshed_set_do_not_unlock(self):
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?', (self.user['id'],))
            conn.commit()
        shop = self.shop()
        target = shop['offers'][0]
        _, error = eye_styles.purchase_eye_style_offer(self.user['id'], shop['set_id'], target['slot'])
        self.assertEqual(error, '荆露不足')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        _, error = eye_styles.purchase_eye_style_offer(self.user['id'], shop['set_id'], 99)
        self.assertEqual(error, '商品不存在或已下架')

    def test_refresh_cost_increments_and_resets_next_day(self):
        shop = self.shop()
        before = db.get_user_thorn_dew(self.user['id'])['total']
        refreshed, error = eye_styles.refresh_eye_style_shop(self.user['id'])
        self.assertIsNone(error)
        self.assertNotEqual(refreshed['set_id'], shop['set_id'])
        self.assertEqual(refreshed['refresh_cost'], 1000)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 700)
        refreshed, error = eye_styles.refresh_eye_style_shop(self.user['id'])
        self.assertIsNone(error)
        self.assertEqual(refreshed['refresh_cost'], 1300)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], before - 1700)
        _, error = eye_styles.purchase_eye_style_offer(self.user['id'], shop['set_id'], 1)
        self.assertEqual(error, '商店内容已刷新，请按当前商品操作')
        with db.get_db_connection() as conn:
            conn.execute(
                "UPDATE eye_shop_user_state SET refresh_date = '2000-01-01', refresh_count = 4 WHERE user_id = ?",
                (self.user['id'],),
            )
            conn.commit()
        self.assertEqual(self.shop()['refresh_cost'], 700)

    def test_eye_style_api_returns_shop_and_owned_shapes(self):
        app.app.config.update(TESTING=True)
        client = app.app.test_client()
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            response = client.get('/api/eye-styles')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['shop']['offers']), 3)
        self.assertEqual(set(payload['shop']['owned_eye_shapes']), eye_styles.BASE_EYE_SHAPES)


class EyeStyleFrontendContractTests(unittest.TestCase):
    def test_shop_inventory_form_and_api_routes_exist(self):
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        for marker in ('data-shop-tab="eye-styles"', 'id="eye-style-shop-panel"', 'id="eye-style-shop-grid"'):
            self.assertIn(marker, index)
        for eye_shape in ('angry', 'coin', 'dizzy'):
            self.assertIn(f'value="{eye_shape}"', index)
            self.assertIn(f"/static/assets/eye-styles/{eye_shape}.svg", (ROOT / 'static/js/eye-styles.js').read_text(encoding='utf-8'))
        for route in ('/api/eye-styles', '/api/eye-styles/refresh', '/api/eye-styles/purchase', '/api/eye-styles/equip'):
            self.assertIn(route, source)
            self.assertIn(route, game)
        for marker in ('loadEyeStyleOwnership', 'updateSkinEyeShapeOptions', 'activePlayerShopKind', 'eyeStyleShopActive', 'eyeStyleOwnershipUserId'):
            self.assertIn(marker, game)
        self.assertIn('尚未拥有这款眼睛', game)

    def test_shop_buttons_are_rendered_after_the_busy_flag_clears(self):
        # 曾经的 bug：loadPlayerSkinShop 在 busy=true 时渲染，按钮全部带 disabled，点不动。
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        start = game.index('async function loadPlayerSkinShop(')
        end = game.index('function renderPlayerSkinShop()', start)
        segment = game[start:end]
        segment = segment[segment.index('playerSkinShopBusy = true;'):]
        self.assertEqual(segment.count('renderPlayerSkinShop();'), 1)
        self.assertLess(
            segment.index('playerSkinShopBusy = false;'),
            segment.index('renderPlayerSkinShop();'),
        )
    def test_player_shop_route_helper_accepts_both_action_forms(self):
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        start = game.index('const PLAYER_SHOP_ROUTES')
        end = game.index('let rankCardsShopActive', start)
        segment = game[start:end]
        self.assertIn("const route = String(action || 'list').replace(/^\\/+/, '') || 'list';", segment)
        for kind in ('eye', 'player'):
            base = '/api/eye-styles' if kind == 'eye' else '/api/player-skins'
            cases = {'': '', 'list': '', '/refresh': '/refresh', 'refresh': '/refresh', '/purchase': '/purchase', 'purchase': '/purchase', '/equip': '/equip', 'equip': '/equip'}
            for action, suffix in cases.items():
                route = action.lstrip('/') or 'list'
                self.assertIn(f"{route}: '{base + suffix}'", segment)

    def test_shared_eye_art_assets_and_renderers(self):
        for eye_shape in ('angry', 'coin', 'dizzy'):
            asset = ROOT / 'static/assets/eye-styles' / f'{eye_shape}.svg'
            self.assertTrue(asset.is_file())
            root = ET.parse(asset).getroot()
            self.assertTrue(root.attrib.get('viewBox'))
        for part in ('angry-socket', 'angry-white'):
            asset = ROOT / 'static/assets/eye-styles' / f'{part}.svg'
            self.assertTrue(asset.is_file())
            self.assertTrue(ET.parse(asset).getroot().attrib.get('viewBox'))
        for template, renderer in (
            ('templates/index.html', 'game.js'),
            ('templates/story.html', 'story.js'),
            ('templates/minigame_suika.html', 'minigame_suika.js'),
        ):
            page = (ROOT / template).read_text(encoding='utf-8')
            self.assertIn('/static/css/eye-styles.css', page)
            self.assertLess(page.index('/static/js/eye-styles.js'), page.index(renderer))
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        story = (ROOT / 'static/js/story.js').read_text(encoding='utf-8')
        suika = (ROOT / 'static/js/minigame_suika.js').read_text(encoding='utf-8')
        self.assertIn('window.GTNEyeStyles?.render(eyeShape)', game)
        self.assertIn('window.GTNEyeStyles?.render(skin.eyeShape)', story)
        self.assertIn("insertAdjacentHTML('afterbegin', window.GTNEyeStyles?.render(seatSkin.eyeShape)", story)
        self.assertIn('window.GTNEyeStyles?.render(shape)', suika)
        self.assertIn('playerEyeArt', suika)
        self.assertIn('playerEyeSocketArt', suika)
        self.assertIn('playerEyeWhiteArt', suika)
        self.assertIn('target.clip(playerEyeClipPath)', suika)
        self.assertIn('const artBaseY = y - radius + (eyeY - y)', suika)
        self.assertIn('<div class="skin-face">\n                ${eyeArt}', game)
        self.assertIn('<div class="skin-face">\n                ${eyeArt}', story)
        eye_catalog = (ROOT / 'static/js/eye-styles.js').read_text(encoding='utf-8')
        self.assertIn("id: 'coin', asset:", eye_catalog)
        self.assertIn("id: 'dizzy', asset:", eye_catalog)
        self.assertEqual(eye_catalog.count('socketless: true'), 2)
        self.assertIn('skin-eye-art-socket', eye_catalog)
        self.assertIn('skin-eye-art-white', eye_catalog)
        self.assertIn('x: 3.192, y: 6.048', eye_catalog)
        css = (ROOT / 'static/css/eye-styles.css').read_text(encoding='utf-8')
        self.assertIn('skin-eye-art', css)
        self.assertIn(':not(.is-defeated) .skin-eye', css)
        self.assertIn('calc(var(--skin-eye-art-y, 0%) - 8%)', css)
        self.assertIn('mask-image: var(--skin-eye-socket-image)', css)



if __name__ == '__main__':
    unittest.main()
