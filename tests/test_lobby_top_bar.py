import io
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = io.open(os.path.join(ROOT, 'static', 'js', 'game.js'), encoding='utf-8').read()
STYLE = io.open(os.path.join(ROOT, 'static', 'css', 'style.css'), encoding='utf-8').read()
VERSION = io.open(os.path.join(ROOT, 'static_version.txt'), encoding='utf-8').read().strip()

START = SCRIPT.index('function updateTopActionButtons(')
END = SCRIPT.index('\nfunction showView(', START)
FUNC = SCRIPT[START:END]

WIDGETS = [
    'settingsTop',
    'accountTop',
    'skinTop',
    'changelogTop',
    'achievementsTop',
    'titleShopTop',
]


class LobbyTopBarWidgetsTest(unittest.TestCase):
    def test_menu_widgets_cover_home_and_lobby(self):
        self.assertIn("const onHome = viewId === 'view-login';", FUNC)
        self.assertIn("const onLobby = viewId === 'view-lobby';", FUNC)
        self.assertIn('const menuWidgets = onHome || onLobby;', FUNC)
        self.assertNotIn('!onHome)', FUNC)

    def test_every_widget_follows_the_shared_flag(self):
        for widget in WIDGETS:
            self.assertIn(
                f"if ({widget}) {widget}.classList.toggle('hidden', !menuWidgets);", FUNC
            )

    def test_friends_still_requires_an_account(self):
        self.assertIn(
            "if (friendsTop) friendsTop.classList.toggle('hidden', !menuWidgets || !currentAccount);", FUNC
        )

    def test_lobby_only_entries_stay_lobby_only(self):
        self.assertIn("if (replaysTop) replaysTop.classList.toggle('hidden', viewId !== 'view-lobby');", FUNC)
        self.assertIn("if (galleryTop) galleryTop.classList.toggle('hidden', viewId !== 'view-lobby');", FUNC)

    def test_pass_hud_is_displayed_in_the_lobby_too(self):
        self.assertIn('body:has(#view-lobby:not(.hidden)) button.pass-top-btn', STYLE)

    def test_version_bumped(self):
        self.assertIn('-lobby-topbar-widgets-1', VERSION)


if __name__ == '__main__':
    unittest.main()
