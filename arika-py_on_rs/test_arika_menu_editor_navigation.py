"""Qt smoke tests for recovered main-menu navigation in the integrated preview."""
import importlib.util
import os
import struct
from pathlib import Path
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_HAS_QT = importlib.util.find_spec('PySide6') is not None


def synthetic_menu_pix(count=13):
    """Create tiny unlicensed 2x2 XPIX/TIM2 images for renderer tests."""
    chunks = []
    for index in range(count):
        pixels = bytes((index * 17 % 256, 255 - index * 13, 83, 128)) * 4
        header = struct.pack('<IIIHHBBBBHH', 48 + len(pixels), 0,
                             len(pixels), 48, 0, 0, 1, 0, 3, 2, 2)
        tim2 = b'TIM2' + struct.pack('<BBH', 4, 0, 1) + bytes(8)
        tim2 += header + bytes(48 - len(header)) + pixels
        chunks.append(b'XPIX' + struct.pack('<I', 32 + len(tim2)) +
                      bytes(24) + tim2)
    offsets = []
    pos = 32 + 4 * count
    for chunk in chunks:
        offsets.append(pos)
        pos += len(chunk)
    return (b'FPIX' + struct.pack('<III', pos, count, 1) +
            bytes(16) + struct.pack('<' + 'I' * count, *offsets) +
            b''.join(chunks))



@unittest.skipUnless(_HAS_QT, 'PySide6 required for interactive menu preview tests')
class MenuEditorNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets as W
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        from arika_menu_editor import c_menu_editor
        self.m_editor = c_menu_editor()

    def tearDown(self):
        self.m_editor.close()
        self.m_editor.deleteLater()
        self.m_app.processEvents()

    def test_graph_controls_keep_combo_and_history_in_sync(self):
        editor = self.m_editor
        self.assertEqual((editor.m_item, editor.m_item_combo.currentIndex()), (0, 0))
        self.assertTrue(editor.navigate(3))  # Down: 0 -> 1
        self.assertTrue(editor.navigate(0))  # Right: 1 -> 2
        self.assertTrue(editor.navigate(2))  # Up: 2 -> 0
        self.assertEqual((editor.m_item, editor.m_navigation.m_previous), (0, 2))
        self.assertTrue(editor.navigate(3))  # history-dependent 0 -> 2
        self.assertEqual((editor.m_item, editor.m_navigation.m_previous), (2, 0))
        self.assertEqual(editor.m_item_combo.currentIndex(), 2)
        self.assertTrue(editor.navigate(0))  # history-dependent 2 -> 5
        self.assertEqual(editor.m_item_combo.currentIndex(), 5)
        self.assertFalse(editor.navigate(0))  # 5 has no right neighbour
        self.assertEqual((editor.m_item, editor.m_navigation.m_previous), (5, 2))

    def test_combo_selection_and_destination_preview(self):
        editor = self.m_editor
        editor.m_item_combo.setCurrentIndex(3)
        self.assertEqual((editor.m_navigation.m_selected, editor.m_navigation.m_previous), (3, 0))
        self.assertEqual(editor.inspect_route(False)['next_app_id'], 44)
        self.assertEqual(editor.inspect_route(False)['mode_selector'], 5)
        self.assertEqual(editor.inspect_route(True)['next_app_id'], 3)
        self.assertIsNone(editor.inspect_route(True)['mode_selector'])
        self.assertEqual(editor.m_item, 3)
        self.assertIn('Dragon Summoning', editor.m_navigation_status.text())
        self.assertIn('Shenron', editor.m_navigation_status.toolTip())

    def test_loads_user_supplied_pix_and_clears_on_archive_change(self):
        editor = self.m_editor
        self.assertIsNotNone(editor.m_data, 'asset-free layout should load from repository')
        self.assertEqual(editor.m_textures, {})
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        self.assertEqual(len(editor.m_textures), 13)
        self.assertEqual(editor.m_textures[3].size().width(), 2)
        self.assertEqual(editor.m_textures[3].toImage().pixelColor(0, 0).alpha(), 255)
        self.assertFalse(editor.load_textures(None))
        self.assertFalse(editor.m_textures)
        self.assertIn('open INFO.DAT', editor.m_texture_status.text())
        self.assertFalse(editor.load_textures(b'bad pix'))
        self.assertFalse(editor.m_textures)
        self.assertIn('failed', editor.m_texture_status.text())
        self.assertFalse(editor.load_textures(synthetic_menu_pix(count=12)))
        self.assertFalse(editor.m_textures)

    def test_layout_has_no_embedded_images(self):
        editor = self.m_editor
        self.assertNotIn('textures', editor.m_data)
        self.assertEqual(len(editor.m_data['frames']), 140)
        self.assertFalse((Path(__file__).resolve().parent.parent /
                          'previews' / 'menu_textured.html').exists())

    def test_render_changes_with_selected_item(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        self.assertIsNotNone(editor.m_data, 'animation/geometry layout should load')
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor.fromHsv(index * 25, 255, 255))
            editor.m_textures[index] = pixmap
        editor.m_background = False
        editor.m_motion = False
        editor.m_tint = False

        def draw():
            image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('black'))
            painter = G.QPainter(image)
            editor.render(painter, C.QRect(0, 0, 512, 448))
            painter.end()
            return bytes(image.constBits())

        original = draw()
        self.assertTrue(editor.navigate(3))
        self.assertNotEqual(original, draw(), 'switching item should change the actual canvas')
 
    def test_preview_keyboard_navigation_and_confirm_cancel(self):
        from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
        editor = self.m_editor

        def press(key):
            event = G.QKeyEvent(C.QEvent.Type.KeyPress, key, C.Qt.KeyboardModifier.NoModifier)
            W.QApplication.sendEvent(editor.m_canvas, event)
            self.assertTrue(event.isAccepted())

        press(C.Qt.Key.Key_Down)
        self.assertEqual(editor.m_item, 1)
        press(C.Qt.Key.Key_Return)
        self.assertIn('Confirm', editor.m_navigation_status.text())
        press(C.Qt.Key.Key_Escape)
        self.assertIn('Cancel', editor.m_navigation_status.text())
        self.assertEqual(editor.m_item, 1)


if __name__ == '__main__':
    unittest.main()
