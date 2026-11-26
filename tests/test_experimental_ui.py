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
        self.assertIn('-experimental-ui-1', VERSION.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
