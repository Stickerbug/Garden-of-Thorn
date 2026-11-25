import io
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(rel):
    return io.open(ROOT / rel, encoding='utf-8').read()


class LobbyGalleryEntry(unittest.TestCase):
    def setUp(self):
        self.index = read('templates/index.html')
        self.game = read('static/js/game.js')
        self.style = read('static/css/style.css')
        self.version = read('static_version.txt')

    def _top_bar(self):
        start = self.index.index('class="top-action-buttons"')
        end = self.index.index('id="changelog-popover"')
        return self.index[start:end]

    def _lobby_block(self):
        start = self.index.index('id="view-lobby"')
        end = self.index.index('id="view-draft"')
        return self.index[start:end]

    def test_gallery_button_left_the_main_menu_icon_bar(self):
        top_bar = self._top_bar()
        self.assertNotIn('id="btn-card-gallery"', top_bar)
        self.assertNotIn('gallery-top-btn', top_bar)

    def test_gallery_button_sits_in_the_lobby_header(self):
        lobby = self._lobby_block()
        self.assertIn('id="btn-lobby-gallery"', lobby)
        self.assertIn('class="btn btn-secondary btn-small lobby-gallery-btn"', lobby)
        self.assertIn('id="btn-lobby-gallery-label">图鉴<', lobby)
        self.assertIn('ui-icons/gallery.svg', lobby)
        header = lobby.index('lobby-header lobby-header-with-tabs')
        button = lobby.index('id="btn-lobby-gallery"')
        tabs = lobby.index('id="lobby-mode-tabs"')
        self.assertLess(header, button)
        self.assertLess(button, tabs)

    def test_button_opens_the_card_gallery(self):
        self.assertIn("bindClickOnce('btn-lobby-gallery', () => showCardGallery());", self.game)
        self.assertNotIn("bindClickOnce('btn-card-gallery'", self.game)
        self.assertIn("const lobbyGalleryLabel = document.getElementById('btn-lobby-gallery-label');", self.game)
        self.assertIn("const btnLobbyGallery = $('btn-lobby-gallery-label');", self.game)

    def test_gallery_button_has_no_home_only_visibility_toggle(self):
        self.assertNotIn("const galleryTop = $('btn-card-gallery');", self.game)
        self.assertIn("if (replaysTop) replaysTop.classList.toggle('hidden', viewId !== 'view-lobby');", self.game)

    def test_lobby_gallery_button_is_positioned_top_right(self):
        self.assertIn('.lobby-gallery-btn {', self.style)
        block_start = self.style.index('.lobby-gallery-btn {')
        block_end = self.style.index('}', block_start)
        block = self.style[block_start:block_end]
        self.assertIn('position: absolute;', block)
        self.assertIn('right: 0;', block)
        self.assertIn('.lobby-gallery-icon {', self.style)

    def test_version_bumped(self):
        self.assertIn('-lobby-gallery-entry-1', self.version)


if __name__ == '__main__':
    unittest.main()
