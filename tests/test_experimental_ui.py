import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'static' / 'css' / 'experimental-ui.css'
JS = ROOT / 'static' / 'js' / 'experimental-ui.js'
GAME_JS = ROOT / 'static' / 'js' / 'game.js'
INDEX = ROOT / 'templates' / 'index.html'
VERSION = ROOT / 'static_version.txt'


class ExperimentalCssTest(unittest.TestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding='utf-8')

    def test_every_rule_is_scoped_to_the_experimental_shell(self):
        body = re.sub(r'/\*.*?\*/', '', self.css, flags=re.S)
        selectors = []
        for block in re.findall(r'([^{}]+)\{[^{}]*\}', body):
            for part in block.split(','):
                part = part.strip()
                if not part or part.startswith('@'):
                    continue
                selectors.append(part)
        self.assertGreater(len(selectors), 60)
        unscoped = [s for s in selectors if 'data-ui-shell="experimental"' not in s]
        self.assertEqual(unscoped, [], f'实验性 UI 的规则必须全部限定在实验外壳下：{unscoped[:5]}')

    def test_tokens_follow_the_design_document(self):
        for token, value in [
            ('--xui-ink', '#172d2a'),
            ('--xui-panel', '#fff6df'),
            ('--xui-ink-soft', '#243c34'),
            ('--xui-primary', '#4d7551'),
            ('--xui-select', '#e4e9d6'),
            ('--xui-accent', '#c58b38'),
            ('--xui-danger', '#b9434c'),
        ]:
            self.assertIn(f'{token}: {value};', self.css)

    def test_four_pages_have_layout_rules(self):
        for selector in [
            '#view-login .login-container',
            '#view-lobby .lobby-body',
            '#changelog-popover',
            '#title-shop-popover',
        ]:
            self.assertIn(selector, self.css)
        self.assertIn('grid-template-columns: minmax(240px, 280px) minmax(0, 1fr) minmax(260px, 320px);', self.css)
        self.assertIn('grid-template-columns: 150px minmax(0, 1fr);', self.css)

    def test_mobile_breakpoint_collapses_to_one_column(self):
        mobile = self.css.split('@media (max-width: 720px)', 1)[1]
        self.assertIn('#view-login .login-form', mobile)
        self.assertIn('grid-template-columns: minmax(0, 1fr);', mobile)
        self.assertIn('#changelog-popover .ann-item[open] .ann-body', mobile)
        self.assertIn('position: static;', mobile)

    def test_panel_style_matches_the_furniture_rules(self):
        self.assertIn('border: 2px solid var(--xui-line);', self.css)
        self.assertIn('border-radius: var(--xui-radius);', self.css)
        self.assertIn('--xui-radius: 12px;', self.css)
        self.assertIn('--xui-shadow: 4px 4px 0 rgba(23, 45, 42, .45);', self.css)


class ExperimentalJsTest(unittest.TestCase):
    def setUp(self):
        self.js = JS.read_text(encoding='utf-8')

    def test_storage_and_roles(self):
        self.assertIn("var SHELL_KEY = 'gtn_ui_shell';", self.js)
        self.assertIn("var SHELL_EXPERIMENTAL = 'experimental';", self.js)
        self.assertIn("var SHELL_STANDARD = 'standard';", self.js)
        self.assertIn("var ROLE_ALLOWED = { admin: true, staff: true, tester: true };", self.js)
        self.assertIn('function isSignedIn(account)', self.js)
        self.assertIn('function isAvailable(account)', self.js)

    def test_cookie_first_storage_matches_the_boot_script(self):
        self.assertIn('function readCookie(key)', self.js)
        self.assertIn('function writeCookie(key, value)', self.js)
        self.assertIn('document.cookie', self.js)
        self.assertIn('localStorage.setItem(key, value)', self.js)

    def test_applies_shell_attribute_and_reloads_on_toggle(self):
        self.assertIn("root.setAttribute('data-ui-shell'", self.js)
        self.assertIn('window.location.reload()', self.js)
        self.assertIn('window.GtnExperimentalUi = {', self.js)
        for api in ['isEnabled', 'isAvailable', 'setEnabled', 'syncAccount', 'apply']:
            self.assertIn(api, self.js)

    def test_reverts_only_for_signed_in_accounts_without_permission(self):
        self.assertIn('if (isSignedIn(account) && !available && isEnabled())', self.js)

    def test_settings_row_is_hidden_by_default(self):
        self.assertIn("var ROW_ID = 'settings-experimental-ui-row';", self.js)
        self.assertIn("var INPUT_ID = 'settings-experimental-ui';", self.js)
        self.assertIn("row.classList.toggle('hidden', !available)", self.js)


class ExperimentalWiringTest(unittest.TestCase):
    def setUp(self):
        self.index = INDEX.read_text(encoding='utf-8')
        self.game = GAME_JS.read_text(encoding='utf-8')

    def test_stylesheet_and_script_are_loaded_before_the_boot_script(self):
        css_at = self.index.index('/static/css/experimental-ui.css')
        js_at = self.index.index('/static/js/experimental-ui.js')
        boot_at = self.index.index('window.__GTN_BETA_MODE__')
        self.assertLess(css_at, boot_at)
        self.assertLess(js_at, boot_at)

    def test_settings_row_exists_in_the_appearance_page(self):
        self.assertIn('id="settings-experimental-ui-row"', self.index)
        self.assertIn('id="settings-experimental-ui"', self.index)
        self.assertIn('实验性UI（管理员／测试员）', self.index)

    def test_game_js_allows_the_key_and_syncs_the_account(self):
        self.assertGreaterEqual(self.game.count("'gtn_ui_shell',"), 2)
        self.assertIn('window.GtnExperimentalUi.syncAccount(currentAccount)', self.game)

    def test_version_bumped(self):
        self.assertIn('-experimental-ui-', VERSION.read_text(encoding='utf-8'))


class ExperimentalBatchTwoTest(unittest.TestCase):
    """第二批：顶栏单色图标、商店购买、公告筛选/搜索/逐条已读、大厅空态、其余子页。"""

    def setUp(self):
        self.css = CSS.read_text(encoding='utf-8')
        self.js = JS.read_text(encoding='utf-8')

    def test_top_icons_are_single_tone(self):
        self.assertIn('html[data-ui-shell="experimental"] .top-icon-btn::before {', self.css)
        self.assertIn('filter: grayscale(1) brightness(.38) contrast(1.05);', self.css)

    def test_shop_cards_and_buy_buttons_are_styled(self):
        for selector in [
            '#title-shop-popover .title-shop-item',
            '#title-shop-popover .title-shop-buy-btn',
            '#title-shop-popover .title-shop-buy-btn:disabled',
            '#title-shop-popover .title-shop-item.is-purchased .title-shop-buy-btn',
        ]:
            self.assertIn(selector, self.css)

    def test_shop_purchase_asks_for_confirmation(self):
        self.assertIn("var CONFIRM_SELECTOR = '[data-title-shop-buy]", self.js)
        self.assertIn('function confirmPurchase(event)', self.js)
        self.assertIn('confirmFn(', self.js)
        self.assertIn('button.dataset.xuiConfirmed', self.js)

    def test_announcement_toolbar_filter_search_and_per_item_read(self):
        self.assertIn("var READ_KEY = 'gtn_ui_ann_read_v1';", self.js)
        self.assertIn('function buildTools()', self.js)
        self.assertIn("btn.dataset.annFilter = pair[0];", self.js)
        self.assertIn('function applyFilter()', self.js)
        self.assertIn('xui-ann-dot', self.js)
        self.assertIn('function decorate()', self.js)
        self.assertIn("item.addEventListener('toggle'", self.js)
        for selector in ['.xui-ann-tools', '.xui-ann-tab', '.xui-ann-search', '.xui-ann-dot', '.ann-item.is-read']:
            self.assertIn(selector, self.css)

    def test_lobby_empty_states_and_chat_surface(self):
        self.assertIn('#view-lobby .lobby-chat-log:empty::before', self.css)
        self.assertIn('还没有人说话，打个招呼吧。', self.css)
        self.assertIn('#view-lobby .player-list:empty::before', self.css)
        self.assertIn('#view-lobby .game-list:empty::before', self.css)

    def test_gallery_and_other_views_get_the_shell(self):
        for selector in [
            '#view-card-gallery .gallery-container',
            '#view-card-gallery .gallery-tab',
            '#view-card-gallery .gallery-tab.active',
        ]:
            self.assertIn(selector, self.css)

    def test_background_covers_the_whole_screen(self):
        """背景要铺满整屏：根节点与 body 都上色，并用整屏背景图而不是纯色。"""
        self.assertIn('html[data-ui-shell="experimental"] {\n    background-color: #24443a;', self.css)
        self.assertIn("url('/static/assets/backgrounds/theme-olive-nocturne.svg')", self.css)
        self.assertIn('background-size: cover, cover;', self.css)
        self.assertIn('background-attachment: fixed, fixed;', self.css)
        self.assertIn('background-repeat: no-repeat, no-repeat;', self.css)

    def test_panels_fill_the_whole_screen(self):
        """奶油面板铺满全屏：去掉悬浮卡片的外边距、圆角、边框与投影。"""
        block = self.css[self.css.index('奶油面板铺满全屏'):]
        self.assertIn('#view-login .login-container,', block)
        self.assertIn('#view-lobby .lobby-container,', block)
        self.assertIn('#view-card-gallery .gallery-container {', block)
        self.assertIn('width: 100%;', block)
        self.assertIn('height: 100%;', block)
        self.assertIn('margin: 0;', block)
        self.assertIn('border-radius: 0;', block)
        self.assertIn('border: 0;', block)
        self.assertIn('box-shadow: none;', block)
        self.assertIn('background: var(--xui-panel);', block)

    def test_pass_entry_keeps_its_original_artwork(self):
        """通行证入口不在顶栏方块那一排：宽度/描边/阴影都要回到游戏原样。"""
        block = self.css[self.css.index('通行证入口恢复原样'):]
        self.assertIn('.pass-top-btn {', block)
        self.assertIn('width: 170px !important;', block)
        self.assertIn('width: 232px !important;', block)
        self.assertIn('aspect-ratio: 360 / 158;', block)
        self.assertIn('background: none !important;', block)
        self.assertIn('border: 0 !important;', block)
        self.assertIn('box-shadow: none !important;', block)
        self.assertIn('background: var(--ui-icon-url) center / contain no-repeat !important;', block)

    def test_home_center_is_scaled_up(self):
        """菜单中心区放大一档：标题 52px、模式牌 84px 高、表单 820px。"""
        self.assertIn('max-width: 820px;', self.css)
        self.assertIn('font-size: 52px;', self.css)
        self.assertIn('min-height: 84px;', self.css)
        self.assertIn('font-size: 20px;', self.css)
        self.assertIn('white-space: nowrap;', self.css)

    def test_version_bumped_to_batch_two(self):
        self.assertIn('-experimental-ui-2', VERSION.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
