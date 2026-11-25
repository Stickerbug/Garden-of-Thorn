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

    def _top_bar(self):
        start = self.index.index('class="top-action-buttons"')
        end = self.index.index('id="changelog-popover"')
        return self.index[start:end]

    def _lobby_block(self):
        start = self.index.index('id="view-lobby"')
        end = self.index.index('id="view-draft"')
        return self.index[start:end]

    def test_replay_button_lives_in_the_main_menu_icon_bar(self):
        top_bar = self._top_bar()
        self.assertIn('id="btn-replays-top"', top_bar)
        self.assertIn('class="top-icon-btn replay-top-btn hidden"', top_bar)
        self.assertIn('class="top-icon-label">回放<', top_bar)
        self.assertNotIn('btn-lobby-replays', self.index)

    def test_replay_button_only_shows_in_the_lobby(self):
        self.assertIn("const replaysTop = $('btn-replays-top');", self.game)
        self.assertIn("if (replaysTop) replaysTop.classList.toggle('hidden', viewId !== 'view-lobby');", self.game)
        self.assertNotIn('btn-lobby-replays', self.game)

    def test_icon_button_style_is_restored(self):
        self.assertIn('.replay-top-btn::before', self.style)
        self.assertIn('url("/static/assets/ui-icons/replay.svg")', self.style)
        self.assertNotIn('.lobby-replay-btn', self.style)

    def test_popover_anchors_under_the_replay_button(self):
        self.assertIn('function positionStatsPopover(anchor)', self.game)
        self.assertRegex(self.game, re.compile(r"toggleStatsPopover\(undefined, \$\('btn-replays-top'\)\)"))

    def test_version_bumped(self):
        self.assertIn('-lobby-replay-entry-2', read('static_version.txt'))


if __name__ == '__main__':
    unittest.main()
