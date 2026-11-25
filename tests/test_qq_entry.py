import io
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(rel):
    return io.open(ROOT / rel, encoding='utf-8').read()


class QqEntryLivesInAboutPanel(unittest.TestCase):
    def setUp(self):
        self.index = read('templates/index.html')
        self.game = read('static/js/game.js')
        self.style = read('static/css/style.css')

    def test_top_bar_no_longer_carries_a_qq_button(self):
        self.assertNotIn('id="btn-qq-top"', self.index)
        self.assertNotIn("'btn-qq-top'", self.game)

    def test_credits_page_offers_a_qq_group_button(self):
        self.assertIn('id="btn-qq-group-join"', self.index)
        self.assertIn('>加入群聊</button>', self.index)
        self.assertIn('id="btn-copy-qq-group"', self.index)
        credits_start = self.index.index('id="about-page-credits"')
        credits_end = self.index.index('id="about-panel-close"') if 'id="about-panel-close"' in self.index else len(self.index)
        credits = self.index[credits_start:credits_end]
        self.assertIn('btn-qq-group-join', credits)
        self.assertIn('btn-copy-qq-group', credits)

    def test_group_button_opens_the_invitation_link(self):
        self.assertRegex(
            self.game,
            re.compile(r"\$\('btn-qq-group-join'\)\)\s*\$\('btn-qq-group-join'\)\.addEventListener\('click', \(\) => window\.open\('https://qm\.qq\.com/q/KngslbBBmM'"),
        )
        self.assertNotIn("$('btn-qq-top')", self.game)

    def test_dead_top_button_style_is_gone(self):
        self.assertNotIn('.qq-top-btn', self.style)

    def test_version_bumped(self):
        version = read('static_version.txt').strip()
        self.assertIn('-qq-in-about-1', version)


if __name__ == '__main__':
    unittest.main()
