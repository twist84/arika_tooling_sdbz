"""Qt smoke tests for recovered main-menu navigation in the integrated preview."""
import importlib.util
import os
import struct
from pathlib import Path
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_HAS_QT = importlib.util.find_spec('PySide6') is not None


def synthetic_ffon():
    """Minimal 4-bpp FFON with one mapped ASCII glyph, no proprietary art."""
    data = bytearray(0x160 + 2)
    data[:4] = b'FFON'
    struct.pack_into('<III', data, 0x10, 1, 95, 1)
    data[0x1C:0x20] = bytes((2, 2, 4, 1))
    struct.pack_into('<H', data, 0xA0 + 2 * (ord('J') - 0x20), 1)
    data[0x160:] = bytes((255, 255))
    return bytes(data)


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

    def test_help_panel_atlas_uses_alpha_bounds_and_resets(self):
        from PySide6 import QtCore as C
        editor = self.m_editor
        self.assertIsNone(editor.m_help_panel_uv)
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        # The synthetic atlases are opaque, so the entire 2x2 image is used.
        self.assertEqual(editor.m_help_panel_uv, C.QRectF(0, 0, 2, 2))
        self.assertFalse(editor.load_textures(None))
        self.assertIsNone(editor.m_help_panel_uv)

    def test_reference_pose_match_restores_display_and_ranks_samples(self):
        from PIL import Image
        from arika_menu_frame_match import normalize_reference
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor.fromHsv(index * 17, 190, 220))
            editor.m_textures[index] = pixmap
        editor.m_help_panel = False
        editor.m_time = 70.0
        old_mode = editor.m_presentation
        editor.m_presentation = 'tv_4_3'
        image = G.QImage(512, 384, G.QImage.Format.Format_RGBA8888)
        image.fill(G.QColor('#10151c'))
        painter = G.QPainter(image)
        editor.render(painter, C.QRect(0, 0, 512, 384))
        painter.end()
        reference = normalize_reference(
            Image.frombytes('RGBA', (512, 384), bytes(image.constBits())))
        editor.m_presentation = old_mode
        editor.m_selection_age = 2.0

        editor.match_reference_image(reference)
        self.assertEqual(editor.m_presentation, old_mode)
        self.assertEqual(editor.m_selection_age, 2.0)
        self.assertEqual(len(editor.m_reference_matches), 5)
        self.assertLessEqual(editor.m_reference_matches[0][0], 0.01)
        self.assertIn('Match 1/5:', editor.m_match_status.text())
        self.assertEqual(editor.m_time,
                         float(editor.m_reference_matches[0][1]))
        editor.next_reference_match()
        self.assertEqual(editor.m_reference_match_index, 1)
        self.assertIn('Match 2/5:', editor.m_match_status.text())
        editor.m_timer.stop()

    def test_presentation_mode_changes_display_only(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        self.assertEqual(editor.m_presentation, 'tv_4_3')
        self.assertEqual(editor.presentation_height(), 384)
        logical_bounds = list(editor.m_data['background']['bounds'])
        for mode, expected_height in (
            ('fit', 448), ('raw', 448),
            ('tv_4_3', 384), ('wide_16_9', 288),
            ('native_10_7', 358.4), ('square', 512),
        ):
            idx = editor.m_presentation_combo.findData(mode)
            self.assertGreaterEqual(idx, 0)
            editor.m_presentation_combo.setCurrentIndex(idx)
            self.assertAlmostEqual(editor.presentation_height(), expected_height)
            self.assertEqual(editor.m_data['background']['bounds'],
                             logical_bounds)
        auto = editor.m_presentation_combo.findData('auto')
        editor.m_presentation_combo.setCurrentIndex(auto)
        self.assertTrue(editor.m_scan_combo.isVisibleTo(editor))
        self.assertEqual(editor.presentation_height(), 384)
        progressive = editor.m_scan_combo.findData('progressive')
        editor.m_scan_combo.setCurrentIndex(progressive)
        self.assertAlmostEqual(editor.presentation_height(), 512.0 * 2.0 / 3.0)
        editor.m_scan_combo.setCurrentIndex(
            editor.m_scan_combo.findData('interlaced'))
        self.assertEqual(editor.presentation_height(), 384)
        editor.m_presentation_combo.setCurrentIndex(
            editor.m_presentation_combo.findData('square'))
        self.assertFalse(editor.m_scan_combo.isVisibleTo(editor))
        self.assertEqual(logical_bounds[3], 448)

    def test_logical_448_background_fills_square_presentation(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        editor.m_presentation_combo.setCurrentIndex(editor.m_presentation_combo.findData('square'))
        background = G.QPixmap(512, 512)
        background.fill(G.QColor('#47aabb'))
        editor.m_textures[1] = background
        editor.m_background = True
        editor.m_motion = False
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        image = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        image.fill(G.QColor('#10151c'))
        painter = G.QPainter(image)
        editor.render(painter, C.QRect(0, 0, 512, 512))
        painter.end()
        self.assertEqual(image.pixelColor(256, 500), G.QColor('#47aabb'))
        self.assertEqual(editor.m_data['background']['bounds'][3], 448)

    def test_cloud_tiles_fill_bottom_of_square_menu(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        editor.m_presentation_combo.setCurrentIndex(editor.m_presentation_combo.findData('square'))
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor('#ffffff'))
            editor.m_textures[index] = pixmap
        editor.m_background = False
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_motion = True
        image = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        image.fill(G.QColor('#10151c'))
        painter = G.QPainter(image)
        editor.render(painter, C.QRect(0, 0, 512, 512))
        painter.end()
        self.assertEqual(image.pixelColor(256, 500), G.QColor('#ffffff'))

    def test_menu_uses_square_native_viewport(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        editor.m_presentation_combo.setCurrentIndex(editor.m_presentation_combo.findData('square'))
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor('#3f3f3f'))
            editor.m_textures[index] = pixmap
        editor.m_motion = False
        editor.m_background = False
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = True
        editor.m_help_panel_uv = C.QRectF(0, 0, 512, 512)
        image = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        image.fill(G.QColor('#10151c'))
        painter = G.QPainter(image)
        editor.render(painter, C.QRect(0, 0, 512, 512))
        painter.end()
        self.assertNotEqual(image.pixelColor(100, 480), G.QColor('#10151c'))

    def test_4_3_help_frame_matches_reference_top(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        self.assertEqual(editor.m_presentation, 'tv_4_3')
        editor.m_motion = False
        editor.m_background = False
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = True
        editor.m_help_font = None
        editor.m_help_panel_uv = C.QRectF(0, 0, 2, 2)
        panel = G.QPixmap(2, 2)
        panel.fill(G.QColor('#e04020'))
        editor.m_textures[4] = panel
        image = G.QImage(512, 384, G.QImage.Format.Format_ARGB32)
        image.fill(G.QColor('#10151c'))
        painter = G.QPainter(image)
        editor.render(painter, C.QRect(0, 0, 512, 384))
        painter.end()
        # The image stretches 448 logical Y coordinates to 384 TV pixels.
        top_y = int(272.0 * 384.0 / 448.0)
        self.assertEqual(image.pixelColor(40, top_y + 1),
                         G.QColor('#e04020'))
        self.assertEqual(image.pixelColor(40, top_y - 2),
                         G.QColor('#10151c'))

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
            image = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('black'))
            painter = G.QPainter(image)
            editor.render(painter, C.QRect(0, 0, 512, 512))
            painter.end()
            return bytes(image.constBits())

        original = draw()
        self.assertTrue(editor.navigate(3))
        self.assertNotEqual(original, draw(), 'switching item should change the actual canvas')
 
    def test_selection_pulse_uses_independent_event_clock(self):
        editor = self.m_editor
        editor.m_time = 30.0
        self.assertIsNone(editor.m_selection_age)
        self.assertTrue(editor.navigate(3))
        self.assertEqual(editor.m_selection_age, 0.0)
        self.assertTrue(editor.m_timer.isActive())
        editor.advance()
        self.assertGreater(editor.m_selection_age, 0)
        self.assertEqual(editor.m_time, 30.0, 'selection event must not scrub the global timeline')
        for _ in range(200):
            editor.advance()
        self.assertIsNone(editor.m_selection_age)
        self.assertFalse(editor.m_timer.isActive())
        self.assertEqual(editor.m_time, 30.0)
        editor.m_item_combo.setCurrentIndex(2)
        self.assertEqual(editor.m_selection_age, 0.0)
        editor.m_timer.stop()

    def test_help_panel_and_arrow_layouts_are_bound_to_selection(self):
        from PySide6 import QtCore as C, QtGui as G
        from arika_menu_arrow_preview import arrow_parts
        editor = self.m_editor
        self.assertTrue(editor.m_help_panel)
        self.assertTrue(editor.m_arrow_bob)
        report = editor.m_menu_report

        self.assertEqual(len(arrow_parts(report, 0, -1)), 2)
        self.assertEqual(editor.m_navigation.help_lines()[0],
                         'Just like the arcade version of')
        # From item 2 to item 0, native arrow flag +0x710 changes.
        editor.m_item_combo.setCurrentIndex(2)
        editor.m_item_combo.setCurrentIndex(0)
        actual = arrow_parts(report, editor.m_item, editor.m_navigation.m_previous)
        self.assertEqual(actual, report['arrow_baselines']['items'][0]['variants'][1])

        # Native FFON render path must affect pixels, not just the Qt label.
        self.assertTrue(editor.load_help_font(synthetic_ffon()))
        self.assertIsNotNone(editor.help_line_pixmap('Just like the arcade version of'))
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor('#202020'))
            editor.m_textures[index] = pixmap
        editor.m_time = 70
        def draw():
            image = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('#10151c'))
            painter = G.QPainter(image)
            editor.render(painter, C.QRect(0, 0, 512, 512))
            painter.end()
            return image
        with_panel = draw()
        editor.m_help_panel = False
        without_panel = draw()
        self.assertNotEqual(bytes(with_panel.constBits()),
                            bytes(without_panel.constBits()),
                            'native help artwork or FFON glyphs should change canvas pixels')
        self.assertFalse(editor.load_help_font(None))
        self.assertEqual(editor.m_help_lines_pixmaps, {})

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


    def test_opt_in_native_lifecycle_queues_edges_without_authoring_timing(self):
        editor = self.m_editor
        diagnostic_tick = editor.m_time
        editor.m_lifecycle_combo.setCurrentIndex(1)
        self.assertTrue(editor.m_native_mode)
        self.assertFalse(editor.m_time_slider.isEnabled())
        self.assertFalse(editor.m_item_combo.isEnabled())
        self.assertEqual(editor.m_native_runtime.snapshot()['outer_phase'], 0)

        self.assertTrue(editor.navigate(3))
        self.assertEqual(len(editor.m_native_input_queue), 1)
        # Entry has not completed, so the native input gate drops this edge.
        state = editor.step_native()
        self.assertEqual(state['outer_phase'], 1)
        self.assertEqual(state['selected'], -1)
        self.assertEqual(editor.m_native_input_queue, [])

        for _ in range(100):
            state = editor.step_native()
            if state['outer_phase'] == 2:
                break
        self.assertEqual(state['outer_phase'], 2)
        self.assertEqual(editor.m_item, 0)
        self.assertIn('input=accepting', editor.m_native_status.text())

        self.assertTrue(editor.navigate(3))
        self.assertEqual(editor.m_item, 0, 'native navigation must be queued')
        self.assertEqual(len(editor.m_native_input_queue), 1)
        state = editor.step_native()
        self.assertEqual((state['selected'], state['previous'], state['pending']),
                         (1, 0, 0))
        self.assertEqual(editor.m_item, 1)
        self.assertNotEqual(state['item_ages'][0], state['item_ages'][1])
        self.assertIsNone(editor.m_selection_age,
                          'no authored selection pulse in native state mode')

        editor.inspect_route(False)
        self.assertEqual(editor.m_native_runtime.m_outer_phase, 2)
        state = editor.step_native()
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 30))
        for _ in range(30):
            state = editor.step_native()
        self.assertEqual((state['outer_phase'], state['exit_phase']), (3, 30),
                         'no guessed fade timeout allowed')

        editor.m_lifecycle_combo.setCurrentIndex(0)
        self.assertFalse(editor.m_native_mode)
        self.assertTrue(editor.m_time_slider.isEnabled())
        self.assertTrue(editor.m_item_combo.isEnabled())
        self.assertEqual(editor.m_time, diagnostic_tick)

    def test_native_mode_ignores_qt_keyboard_repeat(self):
        from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
        editor = self.m_editor
        editor.m_lifecycle_combo.setCurrentIndex(1)
        key = C.Qt.Key.Key_Down
        repeated = G.QKeyEvent(
            C.QEvent.Type.KeyPress, key, C.Qt.KeyboardModifier.NoModifier,
            '', True, 2)
        W.QApplication.sendEvent(editor.m_canvas, repeated)
        self.assertTrue(repeated.isAccepted())
        self.assertEqual(editor.m_native_input_queue, [])
        pressed = G.QKeyEvent(
            C.QEvent.Type.KeyPress, key, C.Qt.KeyboardModifier.NoModifier)
        W.QApplication.sendEvent(editor.m_canvas, pressed)
        self.assertEqual(len(editor.m_native_input_queue), 1)




    def test_switching_back_restores_diagnostic_selection_history(self):
        editor = self.m_editor
        editor.m_time_slider.setValue(37)
        editor.m_item_combo.setCurrentIndex(2)
        self.assertEqual((editor.m_item, editor.m_navigation.m_previous),
                         (2, 0))
        previous_age = editor.m_selection_age

        editor.m_lifecycle_combo.setCurrentIndex(1)
        for _ in range(100):
            state = editor.step_native()
            if state['outer_phase'] == 2:
                break
        self.assertEqual(state['selected'], 0)
        editor.navigate(3)
        self.assertEqual(editor.step_native()['selected'], 1)

        editor.m_lifecycle_combo.setCurrentIndex(0)
        self.assertFalse(editor.m_native_mode)
        self.assertEqual(editor.m_item, 2)
        self.assertEqual(editor.m_item_combo.currentIndex(), 2)
        self.assertEqual(
            (editor.m_navigation.m_selected, editor.m_navigation.m_previous),
            (2, 0))
        self.assertEqual(editor.m_time, 37.0)
        self.assertEqual(editor.m_selection_age, previous_age)

    def test_native_render_omits_unselected_and_completed_item_layers(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        editor.m_background = False
        editor.m_motion = False
        editor.m_tint = False
        editor.m_help_panel = False
        editor.m_bounds = False
        editor.m_lifecycle_combo.setCurrentIndex(1)

        def render():
            image = G.QImage(512, 384, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('#10151c'))
            painter = G.QPainter(image)
            editor.render(painter, C.QRect(0, 0, 512, 384))
            painter.end()
            return bytes(image.constBits())

        empty = render()
        self.assertEqual(editor.m_native_runtime.m_selected, -1)
        # No item exists yet in 0x379E60's current/pending draw slots.
        for _ in range(100):
            state = editor.step_native()
            if state['outer_phase'] == 2:
                break
        self.assertEqual(state['selected'], 0)
        self.assertNotEqual(render(), empty)
        editor.m_native_runtime.m_outer_phase = 4
        self.assertEqual(render(), empty)


if __name__ == '__main__':
    unittest.main()
