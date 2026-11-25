import io
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(rel):
    return io.open(ROOT / rel, encoding='utf-8').read()


class LobbyReplayEntry(unittest.TestCase):
    def setUp(self):
        self.index = read('templates/index.html')
        self.game = read('static/js/game.js')
        self.style = read('static/css/style.css')

    def _lobby_block(self):
        start = self.index.index('id="view-lobby"')
        end = self.index.index('id="view-draft"')
        return self.index[start:end]

    def test_top_bar_no_longer_carries_a_replay_button(self):
        top_bar = self.index[self.index.index('class="top-action-buttons"') : self.index.index('id="changelog-popover"')]
        self.assertNotIn('btn-replays-top', top_bar)
        self.assertNotIn("$/('btn-replays-top')", self.game)
        self.assertNotIn("$('btn-replays-top')", self.game)

    def test_replay_button_sits_in_the_lobby_header(self):
        block = self._lobby_block()
        self.assertIn('id="btn-lobby-replays"', block)
        self.assertIn('id="lobby-replay-label"', block)
        header_start = block.index('class="lobby-header')
        header_end = block.index('id="lobby-rank-cards"') if 'id="lobby-rank-cards"' in block else len(block)
        header = block[header_start:header_end]
        self.assertIn('id="btn-lobby-replays"', header)
        # 按钮在模式页签之前，才能靠 margin-left:auto 落到标题行右端
        self.assertLess(header.index('id="btn-lobby-replays"'), header.index('id="lobby-mode-tabs"'))

    def test_replay_button_styles_are_scoped_and_aligned_right(self):
        self.assertIn('.lobby-replay-btn {', self.style)
        rule_start = self.style.index('.lobby-replay-btn {')
        rule_end = self.style.index('}', rule_start)
        self.assertIn('margin-left: auto', self.style[rule_start:rule_end])
        self.assertNotIn('.replay-top-btn', self.style)

    def test_popover_anchors_under_the_lobby_button(self):
        self.assertIn('function positionStatsPopover(anchor)', self.game)
        self.assertIn("$('btn-lobby-replays')", self.game)
        self.assertRegex(self.game, re.compile(r"toggleStatsPopover\(undefined, \$\('btn-lobby-replays'\)\)"))

    def test_version_bumped(self):
        self.assertIn('-lobby-replay-entry-1', read('static_version.txt'))


if __name__ == '__main__':
    unittest.main()
