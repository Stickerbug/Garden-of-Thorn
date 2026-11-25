import io
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = io.open(os.path.join(ROOT, 'static', 'js', 'game.js'), encoding='utf-8').read()
VERSION = io.open(os.path.join(ROOT, 'static_version.txt'), encoding='utf-8').read().strip()


class SubViewReturnTest(unittest.TestCase):
    def test_return_state_and_helpers_exist(self):
        self.assertIn("let subViewReturn = 'view-login';", SCRIPT)
        self.assertIn('function rememberSubViewReturn() {', SCRIPT)
        self.assertIn("subViewReturn = activeViewId === 'view-lobby' ? 'view-lobby' : 'view-login';", SCRIPT)
        self.assertIn('function returnFromSubView() {', SCRIPT)
        self.assertIn("const target = subViewReturn === 'view-lobby' ? 'view-lobby' : 'view-login';", SCRIPT)

    def test_gallery_remembers_and_restores_the_origin_view(self):
        gallery = SCRIPT[SCRIPT.index('async function showCardGallery('):]
        gallery = gallery[:gallery.index("showView('view-card-gallery');") + 40]
        self.assertIn('if (!galleryReturnToRules) rememberSubViewReturn();', gallery)
        self.assertIn('subViewBackLabel(UI.back_to_home)', gallery)
        self.assertIn('returnFromSubView();', SCRIPT[SCRIPT.index("if ($('btn-gallery-back'))"):][:400])

    def test_skin_editor_remembers_and_restores_the_origin_view(self):
        skin = SCRIPT[SCRIPT.index('function openSkinEditor()'):]
        skin = skin[:skin.index('showView(\'view-skin\');') + 40]
        self.assertIn('rememberSubViewReturn();', skin)
        self.assertIn('subViewBackLabel(UI.back_to_home)', skin)
        self.assertIn(
            "if ($('btn-skin-back')) $('btn-skin-back').addEventListener('click', () => returnFromSubView());",
            SCRIPT,
        )

    def test_back_labels_are_translated(self):
        for label in ('返回大厅', 'Back to Lobby', 'Retour au salon', 'ロビーに戻る'):
            self.assertIn(label, SCRIPT)

    def test_version_bumped(self):
        self.assertIn('-subview-return-1', VERSION)


if __name__ == '__main__':
    unittest.main()
