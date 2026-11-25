import io
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = io.open(os.path.join(ROOT, 'templates', 'index.html'), encoding='utf-8').read()
SCRIPT = io.open(os.path.join(ROOT, 'static', 'js', 'game.js'), encoding='utf-8').read()
STYLES = io.open(os.path.join(ROOT, 'static', 'css', 'style.css'), encoding='utf-8').read()
VERSION = io.open(os.path.join(ROOT, 'static_version.txt'), encoding='utf-8').read().strip()

TABS_START = TEMPLATE.index('id="account-panel-tabs"')
TABS_END = TEMPLATE.index('</div>', TABS_START)
TABS = TEMPLATE[TABS_START:TABS_END]
ACTIONS_START = TEMPLATE.index('class="account-popover-actions"')
ACTIONS = TEMPLATE[ACTIONS_START:]


class AccountLeaderboardEntryTest(unittest.TestCase):
    def test_top_bar_no_longer_hosts_the_leaderboard_button(self):
        self.assertNotIn('btn-leaderboard-top', TEMPLATE)
        self.assertNotIn('btn-leaderboard-top', SCRIPT)

    def test_entry_sits_in_the_account_panel_tab_row(self):
        self.assertIn(
            '<button id="btn-account-leaderboard" class="account-mode-tab" type="button">排行榜</button>',
            TABS,
        )
        # 跟在「注销账户」之后，与账号信息等在同一排
        self.assertLess(TABS.index('data-account-panel-tab="delete"'), TABS.index('id="btn-account-leaderboard"'))
        self.assertNotIn('btn-account-leaderboard', ACTIONS)

    def test_entry_is_hidden_until_logged_in(self):
        # 账号面板的 tab 行本身只在登录后显示，排行榜放在其中即继承该可见性
        self.assertIn("const accountTabs = $('account-panel-tabs');", SCRIPT)
        self.assertIn("if (accountTabs) accountTabs.classList.toggle('hidden', !currentAccount);", SCRIPT)

    def test_entry_opens_the_leaderboard_popover(self):
        self.assertIn(
            "if ($('btn-account-leaderboard')) $('btn-account-leaderboard').addEventListener('click', () => toggleLeaderboardPopover());",
            SCRIPT,
        )

    def test_entry_label_follows_the_language(self):
        self.assertIn(
            "const accountLeaderboardBtn = $('btn-account-leaderboard');\n"
            "    if (accountLeaderboardBtn) accountLeaderboardBtn.textContent = UI.leaderboard || '排行榜';",
            SCRIPT,
        )

    def test_entry_uses_the_tab_styling(self):
        self.assertIn('class="account-mode-tab"', TABS)
        self.assertIn('.account-panel-tabs {\n  grid-template-columns: repeat(3, minmax(0, 1fr));\n}', STYLES)

    def test_version_bumped(self):
        self.assertIn('-account-leaderboard-tab-1', VERSION)


if __name__ == '__main__':
    unittest.main()
