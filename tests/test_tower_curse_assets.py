# -*- coding: utf-8 -*-
"""赛季「塔之诅咒」素材：已入库、非商店、供赛季/活动系统另行发放。"""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import backgrounds
import card_skins
import db
import player_skins


ROOT = Path(__file__).resolve().parents[1]

CHARACTERS = (
    ('tower_curse_ironclad', 'ironclad'),
    ('tower_curse_silent', 'silent'),
    ('tower_curse_defect', 'defect'),
    ('tower_curse_necrobinder', 'necrobinder'),
    ('tower_curse_regent', 'regent'),
)
BACKGROUNDS = (
    ('tower_curse_deepwood', 'theme-tower-curse-deepwood.svg'),
    ('tower_curse_dark_harbor', 'theme-tower-curse-dark-harbor.svg'),
)


class TowerCurseAssetTests(unittest.TestCase):
    def test_art_revision_is_scoped_to_the_five_skins(self):
        """美术修订号只对这五款生效：其余皮肤（含卡背、默认卡背）URL 不变。"""
        self.assertEqual(card_skins.CARD_SKIN_ART_REVISION, 8)
        self.assertEqual(card_skins.TOWER_CURSE_SKIN_ART_REVISION, 12)
        for skin_id, _slug in CHARACTERS:
            self.assertEqual(card_skins.skin_art_revision(skin_id), 12)
        for other in ('区', '叶框', '金叶框', '绷带', '标靶', '蠕虫', '阴阳', '阴阳玉', '初始', ''):
            self.assertEqual(card_skins.skin_art_revision(other), 8, other)

        # 客户端同一套口径：旧版本号 11 保留，塔之诅咒单独 12
        script = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn('const CARD_SKIN_ART_REVISION = 11;', script)
        self.assertIn('const TOWER_CURSE_SKIN_ART_REVISION = 12;', script)
        self.assertIn("startsWith('tower_curse_')", script)
        self.assertIn('skinArtRevision(id)', script)

    def test_card_skins_are_registered_but_not_sold(self):
        by_id = {item['skin_id']: item for item in card_skins.CARD_SKIN_CATALOG}
        for skin_id, asset_id in CHARACTERS:
            item = by_id[skin_id]
            self.assertEqual(item['price'], 0)
            self.assertEqual(item['weight'], 0)
            for layer in ('front', 'back'):
                path = ROOT / 'static/assets/card-skins' / layer / f'{skin_id}.svg'
                self.assertTrue(path.is_file(), path)
                ET.parse(path)

    def test_player_skins_are_registered_but_not_sold(self):
        for skin_id, asset_id in CHARACTERS:
            item = player_skins.PLAYER_SKIN_BY_ID[skin_id]
            self.assertEqual(item['price'], 0)
            self.assertEqual(item['weight'], 0)
            self.assertIn(skin_id, db.SKIN_IDS)
            path = ROOT / 'static/assets/player-avatars' / f'tower-curse-{asset_id}.svg'
            self.assertTrue(path.is_file(), path)
            ET.parse(path)

    def test_theme_backgrounds_are_registered_but_not_sold(self):
        for background_id, filename in BACKGROUNDS:
            item = backgrounds.BACKGROUND_BY_KEY[('theme', background_id)]
            self.assertEqual(item['price'], 0)
            self.assertEqual(item['weight'], 0)
            self.assertEqual(
                item['asset_url'],
                f'/static/assets/backgrounds/{filename}',
            )
            path = ROOT / 'static/assets/backgrounds' / filename
            self.assertTrue(path.is_file(), path)
            ET.parse(path)

    def test_client_definitions_cover_all_new_assets(self):
        player_script = (ROOT / 'static/js/player-skins.js').read_text(encoding='utf-8')
        background_script = (ROOT / 'static/js/backgrounds.js').read_text(encoding='utf-8')
        for skin_id, asset_id in CHARACTERS:
            self.assertIn(f"id: '{skin_id}'", player_script)
            self.assertIn(f'tower-curse-{asset_id}.svg', player_script)
        for background_id, filename in BACKGROUNDS:
            self.assertIn(f"id: '{background_id}'", background_script)
            self.assertIn(filename, background_script)

    def test_skins_are_split_into_normal_and_special(self):
        """一般皮肤用默认布局，这五款是特殊皮肤（自带特殊绑定）。"""
        normal_ids = ('区', '叶框', '金叶框', '绷带', '标靶', '蠕虫', '阴阳', '阴阳玉')
        special_ids = tuple(skin_id for skin_id, _ in CHARACTERS)

        for item in card_skins.CARD_SKIN_CATALOG:
            self.assertIn('layout', item, item['skin_id'])
        for skin_id in normal_ids:
            self.assertEqual(card_skins.skin_layout(skin_id), card_skins.SKIN_LAYOUT_DEFAULT, skin_id)
            self.assertEqual(card_skins.skin_category(skin_id), card_skins.SKIN_CATEGORY_NORMAL, skin_id)
        for skin_id in special_ids:
            self.assertEqual(card_skins.skin_layout(skin_id), card_skins.SKIN_LAYOUT_MANA_ON_STAR, skin_id)
            self.assertEqual(card_skins.skin_category(skin_id), card_skins.SKIN_CATEGORY_SPECIAL, skin_id)
        # 未知/空皮肤按一般皮肤处理，不会误加特殊绑定
        self.assertEqual(card_skins.skin_layout(''), card_skins.SKIN_LAYOUT_DEFAULT)
        self.assertEqual(card_skins.skin_category('tower_curse_unknown'), card_skins.SKIN_CATEGORY_NORMAL)

    def test_payload_carries_category_and_layout(self):
        """客户端靠下发的 category/layout 决定绑定，不再按 id 前缀猜。"""
        conn = db.get_db_connection()
        try:
            user = conn.execute('SELECT id FROM users LIMIT 1').fetchone()
            payload = card_skins.card_skin_payload(conn, user['id'] if user else 0)
        finally:
            conn.close()
        by_id = {item['skin_id']: item for item in payload['items']}
        for skin_id, _ in CHARACTERS:
            self.assertEqual(by_id[skin_id]['category'], 'special')
            self.assertEqual(by_id[skin_id]['layout'], 'mana_on_star')
        self.assertEqual(by_id['区']['category'], 'normal')
        self.assertEqual(by_id['区']['layout'], 'default')

    def test_client_binds_by_layout_not_by_prefix(self):
        """特殊绑定由目录的 layout 决定；game.js 里不再出现 tower_curse_ 前缀判断。"""
        script = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn("function cardSkinLayout(skinId)", script)
        self.assertIn("if (cardSkinLayout(ownerSkin) === 'mana_on_star') el.classList.add('card-mana-on-star');", script)
        create_card = script.split('function createCardElement', 1)[1].split('function ', 1)[0]
        self.assertNotIn("startsWith('tower_curse_')", create_card)

    def test_mana_cost_anchor_matches_every_front_star(self):
        """五款卡面共用同一枚蓝色辉星：魔力消耗锚点靠它定位，换图必须同步。"""
        for skin_id, _ in CHARACTERS:
            text = (ROOT / 'static/assets/card-skins/front' / f'{skin_id}.svg').read_text(encoding='utf-8')
            self.assertIn('fill: #3abee8', text, skin_id)
            self.assertIn('M343.1,285.1', text, skin_id)

    def test_costs_sit_in_the_middle_of_their_emblems(self):
        """能量/魔力数字分别在六边形、辉星的正中间（坐标由卡面图换算）。"""
        script = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn("classList.add('card-mana-on-star')", script)
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')

        shared = css.split(
            '.card.card-mana-on-star .card-costs .cost-e,\n'
            '.card.card-mana-on-star .card-costs .cost-m {', 1,
        )[1].split('}', 1)[0]
        self.assertIn('position: absolute', shared)
        self.assertIn('translate(-50%, -50%)', shared)

        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-costs .cost-m {')
        magic = tail.split('}', 1)[0]
        self.assertIn('left: 0.59%', magic)
        self.assertIn('top: 17.61%', magic)

        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-costs .cost-e {')
        elixir = tail.split('}', 1)[0]
        self.assertIn('left: 10.8%', elixir)
        self.assertIn('top: 7.53%', elixir)

    def test_description_starts_below_the_yellow_frame(self):
        """黄框内沿底边在卡高约 48.2%，底部中央的金色小标签再低到约 53.4%；
        红边左右各占 6~7% 卡宽。描述要整体落在标签下方、红边右侧。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')
        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-effect {')
        rule = tail.split('}', 1)[0]
        self.assertIn('padding-top: calc(var(--card-effect-padding-y) + 8cqi)', rule)
        self.assertIn('padding-left: calc(var(--card-effect-padding-x) + 4.5cqi)', rule)
        self.assertIn('padding-right: calc(var(--card-effect-padding-x) + 4.5cqi)', rule)
        self.assertIn('color: #fff', rule)

        # 皮肤墨色自适应会给描述挂逐像素贴图，白字要连贴图一起压掉
        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-effect .skin-ink {')
        ink = tail.split('}', 1)[0]
        self.assertIn('background-image: none !important', ink)
        self.assertIn('color: #fff !important', ink)

    def test_mana_digit_uses_resource_blue(self):
        """魔力数字用 var(--magic)，不被皮肤墨色贴图改写成深蓝。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')
        _head, _sep, tail = css.rpartition(
            '.card.card-mana-on-star .card-costs .cost-m,\n'
            '.card.card-mana-on-star .card-costs .cost-m .skin-ink {'
        )
        rule = tail.split('}', 1)[0]
        self.assertIn('color: var(--magic) !important', rule)

        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-costs .cost-m .skin-ink {')
        ink = tail.split('}', 1)[0]
        self.assertIn('background-image: none !important', ink)

    def test_card_name_is_white_and_inside_the_yellow_band(self):
        """卡名白字 + 深红描边，并整体落在黄条内（黄条 = 卡高 3.03%~10.33%）。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')
        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-costs .card-name {')
        rule = tail.split('}', 1)[0]
        self.assertIn('color: #fff !important', rule)
        self.assertIn('font-size: calc(var(--card-name-font-scale) * 0.9)', rule)
        self.assertIn('text-shadow', rule)
        self.assertIn('#8f2a16', rule)
        self.assertIn('transform: translateY(-1.6cqi)', rule)

    def test_english_translation_line_is_hidden(self):
        """这五款卡面不显示卡名的英文翻译行；占位保留，避免卡图压到黄边。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')
        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-english-name {')
        rule = tail.split('}', 1)[0]
        self.assertIn('visibility: hidden', rule)
        self.assertNotIn('display: none', rule)

    def test_card_art_fills_the_skin_window(self):
        """卡图对到黄框内开口上（SVG x 307.7~826.2、y 217.2~551.3），
        方图不再被 25cqi 的小盒子卡住，插画高度翻倍。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')

        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-art {')
        rule = tail.split('}', 1)[0]
        self.assertIn('position: absolute', rule)
        self.assertIn('left: 8.32%', rule)
        self.assertIn('top: 9.72%', rule)
        self.assertIn('width: 83.37%', rule)
        self.assertIn('height: 38.46%', rule)
        self.assertIn('border-radius: 0', rule)

        # 卡图脱离流后要补回原来占的高度，否则描述和类型标签会整体上移
        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-art ~ .card-type-label-wrap {')
        comp = tail.split('}', 1)[0]
        self.assertIn('margin-top: 25.1cqi', comp)

    def test_type_label_sits_on_the_gold_tab(self):
        """类型标签挪到卡面底部中央的金色小标签里：
        SVG rect(488, 535.2, 157.9 × 61.4) → 卡面中心 (50%, 49.88%)。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')

        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-type-label-wrap {')
        wrap = tail.split('}', 1)[0]
        # 保留原占位高度，否则 .card-effect 上移会把描述压回金色小标签上
        self.assertIn('height: 9.67cqi', wrap)
        self.assertIn('position: static', wrap)

        _head, _sep, tail = css.rpartition('.card.card-mana-on-star .card-type-label {')
        label = tail.split('}', 1)[0]
        self.assertIn('position: absolute', label)
        self.assertIn('left: 50%', label)
        self.assertIn('top: 49.88%', label)
        self.assertIn('transform: translate(-50%, -50%)', label)
        # 金色标签上用深棕字；模板内联的类型色必须 !important 才盖得住
        self.assertIn('color: #4a2b06 !important', label)
        self.assertIn('background: transparent', label)
        self.assertIn('font-size: 6.2cqi', label)

    def test_cost_badges_keep_only_the_number(self):
        """这五款卡面去掉能量/魔力的圆形外框与底色，只留数字压在卡面徽记上。"""
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8').replace('\r\n', '\n')
        shared = css.split(
            '.card.card-mana-on-star .card-costs .cost-e,\n'
            '.card.card-mana-on-star .card-costs .cost-m {', 1,
        )[1].split('}', 1)[0]
        self.assertIn('border-color: transparent', shared)
        self.assertIn('background: transparent', shared)
        self.assertNotIn('box-shadow', shared)
        self.assertIn('text-shadow: none', shared)
        # 颜色沿用资源色：能量黄、魔力蓝
        self.assertIn('color: var(--elixir);', css)
        self.assertIn('color: var(--magic);', css)


if __name__ == '__main__':
    unittest.main()
