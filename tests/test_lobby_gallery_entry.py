import io
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = io.open(os.path.join(ROOT, 'templates', 'index.html'), encoding='utf-8').read()
SCRIPT = io.open(os.path.join(ROOT, 'static', 'js', 'game.js'), encoding='utf-8').read()
STYLES = io.open(os.path.join(ROOT, 'static', 'css', 'style.css'), encoding='utf-8').read()
VERSION = io.open(os.path.join(ROOT, 'static_version.txt'), encoding='utf-8').read().strip()

BAR_START = TEMPLATE.index('class="top-action-buttons"')
BAR_END = TEMPLATE.index('</div>', TEMPLATE.index('id="btn-friends-top"', BAR_START))
BAR = TEMPLATE[BAR_START:BAR_END]


class LobbyGalleryEntryTest(unittest.TestCase):
    def test_gallery_lives_in_the_top_icon_bar(self):
        self.assertIn('<button id="btn-card-gallery" class="top-icon-btn gallery-top-btn hidden"', BAR)
        self.assertIn('ui-icons/gallery.svg', BAR)
        self.assertLess(BAR.index('id="btn-replays-top"'), BAR.index('id="btn-card-gallery"'))
        self.assertLess(BAR.index('id="btn-card-gallery"'), BAR.index('id="btn-friends-top"'))

    def test_lobby_header_no_longer_hosts_the_gallery_button(self):
        self.assertNotIn('btn-lobby-gallery', TEMPLATE)
        self.assertNotIn('lobby-gallery-btn', TEMPLATE)
        self.assertNotIn('lobby-gallery-btn', STYLES)
        self.assertNotIn('btn-lobby-gallery', SCRIPT)

    def test_button_is_only_visible_in_the_lobby(self):
        self.assertIn(
            "const galleryTop = $('btn-card-gallery');\n"
            "    if (galleryTop) galleryTop.classList.toggle('hidden', viewId !== 'view-lobby');",
            SCRIPT,
        )
        self.assertEqual(SCRIPT.count("bindClickOnce('btn-card-gallery', () => showCardGallery())"), 2)
        self.assertIn(
            "setIconButtonLabel('btn-card-gallery', UI.card_gallery || UI.gallery || '图鉴');", SCRIPT
        )

    def test_icon_rule_exists(self):
        self.assertIn('.gallery-top-btn::before', STYLES)
        self.assertIn('--ui-icon-url: url("/static/assets/ui-icons/gallery.svg");', STYLES)

    def test_version_bumped(self):
        self.assertIn('-lobby-gallery-topbar-1', VERSION)


if __name__ == '__main__':
    unittest.main()
