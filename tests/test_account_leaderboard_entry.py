import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = io.open(os.path.join(ROOT, 'templates', 'index.html'), encoding='utf-8').read()
SCRIPT = io.open(os.path.join(ROOT, 'static', 'js', 'game.js'), encoding='utf-8').read()
VERSION = io.open(os.path.join(ROOT, 'static_version.txt'), encoding='utf-8').read().strip()


class AccountLeaderboardEntryTest(unittest.TestCase):
    def test_top_bar_no_longer_hosts_the_leaderboard_button(self):
        self.assertNotIn('btn-leaderboard-top', TEMPLATE)
        self.assertNotIn('btn-leaderboard-top', SCRIPT)

    def test_account_popover_hosts_the_leaderboard_entry(self):
        self.assertIn('<button id="btn-account-leaderboard"', TEMPLATE)
        self.assertLess(TEMPLATE.index('id="account-popover"'), TEMPLATE.index('id="btn-account-leaderboard"'))
        self.assertLess(TEMPLATE.index('id="btn-account-leaderboard"'), TEMPLATE.index('</div>\n  <div id="stats-popover"') if '</div>\n  <div id="stats-popover"' in TEMPLATE else len(TEMPLATE))
        label = TEMPLATE[TEMPLATE.index('id="btn-account-leaderboard"'):]
        self.assertIn('排行榜', label[:120])

    def test_entry_opens_the_leaderboard_popover(self):
        self.assertIn(
            "if ($('btn-account-leaderboard')) $('btn-account-leaderboard').addEventListener('click', () => toggleLeaderboardPopover());",
            SCRIPT,
        )

    def test_entry_label_follows_the_language(self):
        self.assertIn(
            "const accountLeaderboardBtn = $('btn-account-leaderboard');\n    if (accountLeaderboardBtn) accountLeaderboardBtn.textContent = UI.leaderboard || '排行榜';",
            SCRIPT,
        )

    def test_version_bumped(self):
        self.assertIn('-account-leaderboard-entry-1', VERSION)


if __name__ == '__main__':
    unittest.main()
