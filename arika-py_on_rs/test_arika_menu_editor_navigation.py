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

    def test_native_help_panel_draws_uncropped_elf_sprite_and_ffon_rows(self):
        from unittest.mock import patch
        from PySide6 import QtCore as C, QtGui as G

        editor = self.m_editor
        editor.m_native_mode = True
        editor.m_item = 0
        editor.m_native_runtime.m_help_state.update(
            phase=2, age=0.0, x=24.0, y=272.0)
        editor.m_help_font = object()  # Synthetic line bitmap below.
        editor.m_help_panel_uv = C.QRectF(100, 100, 1, 1)
        panel = G.QPixmap(512, 512)
        panel.fill(G.QColor('#c83214'))
        editor.m_textures[4] = panel
        glyphs = G.QPixmap(8, 8)
        glyphs.fill(G.QColor('#32fa32'))

        def draw_help():
            canvas = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            canvas.fill(G.QColor('#10151c'))
            painter = G.QPainter(canvas)
            try:
                with patch.object(editor, 'help_line_pixmap',
                                  return_value=glyphs):
                    editor.draw_help_panel(painter)
            finally:
                painter.end()
            return canvas

        image = draw_help()
        # State 2 uses native component (24,272) and full 464x176 UV,
        # NOT the visible alpha-bounds crop at (30,272).
        self.assertEqual(image.pixelColor(23, 280),
                         G.QColor('#10151c'))
        self.assertEqual(image.pixelColor(24, 280),
                         G.QColor('#c83214'))
        self.assertEqual(image.pixelColor(487, 440),
                         G.QColor('#c83214'))
        # Text starts at (24+64,272+52) and scales an 8x8 source
        # by the native 0.75, making each synthetic row 6x6.
        for y in (324, 349, 374, 399):
            self.assertEqual(image.pixelColor(88, y),
                             G.QColor('#32fa32'))
            self.assertEqual(image.pixelColor(94, y),
                             G.QColor('#c83214'))

        editor.m_item = 2
        editor.m_navigation.select(2)
        versus = draw_help()
        self.assertEqual(versus.pixelColor(88, 374),
                         G.QColor('#32fa32'))
        self.assertEqual(versus.pixelColor(88, 399),
                         G.QColor('#c83214'))

    def test_native_help_entry_exit_phases_reposition_frame_and_gate_text(self):
        from unittest.mock import patch
        from PySide6 import QtCore as C, QtGui as G
        from arika_menu_help_lifecycle import start_help, exit_help, step_help

        editor = self.m_editor
        editor.m_native_mode = True
        editor.m_help_panel = True
        editor.m_item = 0
        editor.m_help_font = object()
        panel = G.QPixmap(512, 512)
        panel.fill(G.QColor('#c83214'))
        editor.m_textures[4] = panel
        glyphs = G.QPixmap(8, 8)
        glyphs.fill(G.QColor('#32fa32'))
        state = editor.m_native_runtime.m_help_state
        start_help(state)
        self.assertEqual(state['y'], -448.0)

        def render_help():
            canvas = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            canvas.fill(G.QColor('#10151c'))
            painter = G.QPainter(canvas)
            try:
                with patch.object(editor, 'help_line_pixmap',
                                  return_value=glyphs):
                    editor.draw_help_panel(painter)
            finally:
                painter.end()
            return canvas

        # The panel starts well above the visible viewport; its text is
        # gated until the vtable +0x34 entry callback returns complete.
        self.assertEqual(render_help().pixelColor(88, 324),
                         G.QColor('#10151c'))
        for _ in range(15):
            step_help(state)
        entry = render_help()
        self.assertEqual((state['phase'], state['y']), (1, 272.0))
        self.assertEqual(entry.pixelColor(88, 324),
                         G.QColor('#c83214'))
        for _ in range(12):
            step_help(state)
        settled = render_help()
        self.assertEqual((state['phase'], state['y']), (2, 272.0))
        self.assertEqual(settled.pixelColor(88, 324),
                         G.QColor('#32fa32'))

        exit_help(state)
        self.assertEqual(render_help().pixelColor(88, 324),
                         G.QColor('#c83214'))
        step_help(state)
        self.assertAlmostEqual(state['y'], 316.8, places=3)
        self.assertEqual(render_help().pixelColor(88, 324),
                         G.QColor('#10151c'))

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


    def test_native_first_layer_and_strip_run_independently_of_diagnostic_time(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor.fromHsv(index * 21, 200, 255))
            editor.m_textures[index] = pixmap
        editor.m_background = False
        editor.m_motion = False
        editor.m_tint = False
        editor.m_first = True
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_time = 70.0
        editor.m_lifecycle_combo.setCurrentIndex(1)
        for _ in range(100):
            state = editor.step_native()
            if state['outer_phase'] == 2:
                break
        self.assertEqual(state['first_phases'][0], 1)
        self.assertEqual(state['first_offsets'][0], (-128.0, -128.0))
        self.assertEqual(state['first_strip_phases'][0], 0.0)

        def render_bytes():
            canvas = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            canvas.fill(G.QColor('#10151c'))
            painter = G.QPainter(canvas)
            try:
                editor.render(painter, C.QRect(0, 0, 512, 448))
            finally:
                painter.end()
            return bytes(canvas.constBits())

        first = render_bytes()
        for _ in range(6):
            state = editor.step_native()
        self.assertNotEqual(first, render_bytes(),
                            'recovered first-layer translation must reach Qt')
        self.assertEqual(state['first_strip_phases'][0], 0.0)
        for _ in range(11):
            state = editor.step_native()
        self.assertEqual((state['first_phases'][0],
                          state['first_strip_phases'][0]), (2, 0.0))
        editor.step_native()
        self.assertEqual(editor.m_native_runtime.snapshot()['first_strip_phases'][0],
                         1.0)
        self.assertTrue(editor.m_native_runtime.first_strip_geometry(0))
        self.assertEqual(editor.m_time, 70.0)

        editor.navigate(3)
        state = editor.step_native()
        self.assertEqual((state['selected'], state['pending']), (1, 0))
        self.assertEqual(state['first_offsets'][0], (0.0, 0.0))
        for _ in range(5):
            state = editor.step_native()
        self.assertNotEqual(state['first_offsets'][0], (0.0, 0.0))
        self.assertEqual(editor.m_time, 70.0)
        editor.m_timer.stop()

    def test_native_character_pose_changes_without_scrubbing_diagnostic_time(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor.fromHsv(index * 19, 255, 240))
            editor.m_textures[index] = pixmap

        editor.m_background = False
        editor.m_motion = False
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = True
        editor.m_character_motion = True
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_selection_effect = False
        editor.m_time = 70.0
        editor.m_lifecycle_combo.setCurrentIndex(1)
        for _ in range(100):
            state = editor.step_native()
            if state['outer_phase'] == 2:
                break
        self.assertEqual(state['outer_phase'], 2)

        def draw():
            canvas = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            canvas.fill(G.QColor('#10151c'))
            painter = G.QPainter(canvas)
            try:
                editor.render(painter, C.QRect(0, 0, 512, 448))
            finally:
                painter.end()
            return bytes(canvas.constBits())

        start_pose = editor.m_native_runtime.character_geometry(0)
        before = draw()
        for _ in range(8):
            editor.step_native()
        after = draw()
        self.assertNotEqual(
            editor.m_native_runtime.character_geometry(0), start_pose)
        self.assertNotEqual(before, after,
                            'native character movement must reach Qt pixels')
        self.assertEqual(editor.m_time, 70.0,
                         'native child updates must not scrub diagnostic time')
        # Check phase-two per-part offsets reach actual Qt pixels as well.
        for _ in range(22):
            editor.step_native()
        idle_before = draw()
        self.assertEqual(
            editor.m_native_runtime.snapshot()['character_phases'][0], 2)
        for _ in range(26):
            editor.step_native()
        idle_after = draw()
        self.assertNotEqual(idle_before, idle_after,
                            'phase-two per-part idle must animate the canvas')
        self.assertTrue(
            editor.m_native_runtime.snapshot()['character_part_offsets'][0])
        self.assertEqual(editor.m_time, 70.0)
        editor.m_timer.stop()

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
        # The atlas must contain the native UV region. A 2x2-only dummy
        # texture has no texels at most recovered sprite coordinates.
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor.fromHsv(index * 19, 200, 255))
            editor.m_textures[index] = pixmap
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
        # The first layer starts at native -128,-128. Our synthetic TIM2
        # occupies only 2x2 pixels, so its atlas sample is initially
        # offscreen; completion of the verified 17-update entry makes
        # it visible. Full 512px textures animate throughout entry.
        for _ in range(17):
            state = editor.step_native()
        self.assertEqual(state['first_phases'][0], 2)
        self.assertNotEqual(render(), empty)
        editor.m_native_runtime.m_outer_phase = 4
        self.assertEqual(render(), empty)


    def test_match_pose_is_diagnostic_only(self):
        editor = self.m_editor
        self.assertTrue(editor.m_match_button.isEnabled())
        self.assertTrue(editor.m_next_match_button.isEnabled())
        editor.m_lifecycle_combo.setCurrentIndex(1)
        self.assertFalse(editor.m_match_button.isEnabled())
        self.assertFalse(editor.m_next_match_button.isEnabled())
        with self.assertRaisesRegex(ValueError, 'Diagnostic timeline'):
            editor.match_reference_image(None)
        editor.m_lifecycle_combo.setCurrentIndex(0)
        self.assertTrue(editor.m_match_button.isEnabled())
        self.assertTrue(editor.m_next_match_button.isEnabled())


    def test_native_dragon_particles_render_pixels_without_repaint_update(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        for index in range(13):
            pixmap = G.QPixmap(512, 512)
            pixmap.fill(G.QColor.fromHsv(index * 19, 200, 255))
            editor.m_textures[index] = pixmap
        editor.m_background = False
        editor.m_motion = False
        editor.m_tint = False
        editor.m_help_panel = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_lifecycle_combo.setCurrentIndex(1)
        runtime = editor.m_native_runtime
        self.assertIsNotNone(runtime.m_particle_pool)
        self.assertEqual(runtime.snapshot()['particles']['total_random_draws'], 15)

        # Isolate the six recovered sprites from the item's other opaque
        # first-layer sprites, so their contribution to Qt pixels is clear.
        source_parts = editor.m_data['items'][3]['first']
        editor.m_data['items'][3]['first'] = []
        editor.m_item = 3
        runtime.m_selected = 3
        runtime.m_item_phases[3] = 2
        runtime.m_first_states[3].update(phase=2, offset=[0.0, 0.0],
                                         depth=15.0)
        literal = runtime.first_geometry(
            3, source_parts[0]['geometry'], component_index=0)
        decoration = runtime.first_geometry(
            3, source_parts[2]['geometry'], component_index=2)
        particle = runtime.particle_geometry(3)[0]['geometry']
        self.assertLess(literal['depth'], particle['depth'])
        self.assertLess(particle['depth'], decoration['depth'])

        def render():
            image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('#10151c'))
            painter = G.QPainter(image)
            editor.render(painter, C.QRect(0, 0, 512, 448))
            painter.end()
            return bytes(image.constBits())

        initial_state = runtime.snapshot()
        first_pixels = render()
        self.assertEqual(first_pixels, render())
        self.assertEqual(initial_state, runtime.snapshot(),
                         'paint must not change the RNG or particle state')
        self.assertTrue(runtime.particle_geometry(3))
        for slot in runtime.m_particle_pool.m_slots:
            slot['x'] = 500.0
        after_pixels = render()
        self.assertNotEqual(after_pixels, first_pixels,
                            'native particle position must affect Qt pixels')
        self.assertEqual(render(), after_pixels)
        self.assertEqual(runtime.snapshot()['particles']['rng_state'],
                         initial_state['particles']['rng_state'])
        # Diagnostic mode has no access to the native simulation.
        editor.m_lifecycle_combo.setCurrentIndex(0)
        self.assertFalse(editor.m_native_mode)
        self.assertEqual(runtime.snapshot()['particles']['rng_state'],
                         initial_state['particles']['rng_state'])


    def test_native_companions_affect_qt_pixels_without_repaint_rng(self):
        """The ten-slot effect is drawn only in native preview mode."""
        from PySide6 import QtCore as C, QtGui as G
        from arika_menu_companions import spawn_slot

        editor = self.m_editor
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        tex = G.QPixmap(512, 512)
        tex.fill(G.QColor('#cb32f2'))
        editor.m_textures[2] = tex
        editor.m_background = False
        editor.m_motion = True
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_lifecycle_combo.setCurrentIndex(1)
        self.assertTrue(editor.m_native_mode)
        runtime = editor.m_native_runtime

        # The diagnostic tiles/banner/small sprites remain independent
        # source frames. Remove those synthetic samples in this fixture
        # to isolate the newly recovered companion-only draw path.
        frame = editor.m_data['frames'][int(editor.m_time)]
        frame['banner'] = None
        frame['tiles'] = []
        frame['small'] = []

        def render():
            image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('#10151c'))
            painter = G.QPainter(image)
            try:
                editor.render(painter, C.QRect(0, 0, 512, 448))
            finally:
                painter.end()
            return bytes(image.constBits())

        blank = render()
        slot = spawn_slot(runtime.m_companion_spec['templates'][0], 0, 0)
        slot.update(x=275.0, y=290.0)
        runtime.m_companion_state['slots'][0] = slot
        state = runtime.snapshot()
        visible = render()
        self.assertNotEqual(visible, blank)
        self.assertEqual(visible, render())
        self.assertEqual(runtime.snapshot(), state,
                         'repaint must neither update owner nor consume RNG')
        slot['x'] = 440.0
        moved = render()
        self.assertNotEqual(visible, moved)
        self.assertEqual(runtime.snapshot()['context_rng_state'],
                         state['context_rng_state'])
        editor.m_lifecycle_combo.setCurrentIndex(0)
        # Native preview now draws independently clocked banner/tiles,
        # so its baseline is not the old diagnostic frame. Instead
        # verify changing the live companion slot cannot change any
        # diagnostic pixels.
        diagnostic_pixels = render()
        slot['x'] = 275.0
        self.assertEqual(render(), diagnostic_pixels,
                         'diagnostic timeline cannot draw live companions')


    def test_native_shared_tiles_banner_and_small_reach_qt_pixels(self):
        """Use synthetic unlicensed atlases; sample frames cannot drive native."""
        from PySide6 import QtCore as C, QtGui as G

        editor = self.m_editor
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        patterned = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        for x in range(512):
            color = G.QColor.fromHsv((x * 7) % 360, 220, 240)
            for y in range(512):
                patterned.setPixelColor(x, y, color)
        editor.m_textures[2] = G.QPixmap.fromImage(patterned)
        small_texture = G.QPixmap(512, 512)
        small_texture.fill(G.QColor('#43e68c'))
        editor.m_textures[3] = small_texture

        editor.m_background = False
        editor.m_motion = True
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_lifecycle_combo.setCurrentIndex(1)
        runtime = editor.m_native_runtime
        self.assertTrue(editor.m_native_mode)
        self.assertIsNotNone(runtime.m_companion_state)

        def render():
            image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('#10151c'))
            painter = G.QPainter(image)
            try:
                editor.render(painter, C.QRect(0, 0, 512, 448))
            finally:
                painter.end()
            return bytes(image.constBits())

        initial = render()
        state = runtime.snapshot()
        self.assertEqual(initial, render())
        # Deliberately corrupt the authored diagnostic frame. Native
        # drawing must use banner/tile/small state and ignore this frame.
        frame = editor.m_data['frames'][int(editor.m_time)]
        frame['banner'] = None
        frame['tiles'] = []
        frame['small'] = []
        self.assertEqual(render(), initial)
        self.assertEqual(runtime.snapshot(), state)

        runtime.m_banner_state['offset'][0] = 0.0
        banner_pixels = render()
        self.assertNotEqual(banner_pixels, initial,
                            'shared banner native offset must reach Qt')
        runtime.m_companion_state['phase'] = 1024.0
        tile_pixels = render()
        self.assertNotEqual(tile_pixels, banner_pixels,
                            'native owner tile phase must reach Qt pixels')
        component = runtime.m_small_states[0]
        component.update(phase=2, offset=[0.0, 0.0])
        small_pixels = render()
        self.assertNotEqual(small_pixels, tile_pixels,
                            'active small native child must reach Qt pixels')
        after = runtime.snapshot()
        self.assertEqual(small_pixels, render())
        self.assertEqual(runtime.snapshot(), after,
                         'paint cannot advance native child clocks or RNG')
        editor.m_lifecycle_combo.setCurrentIndex(0)
        # The diagnostic frame was deliberately cleared and remains the
        # independent source when we switch back.
        self.assertFalse(editor.m_native_mode)
        self.assertNotEqual(render(), small_pixels)

    def test_native_overlay_uses_shared_visibility_and_alpha(self):
        from PySide6 import QtCore as C, QtGui as G

        editor = self.m_editor
        self.assertTrue(editor.load_textures(synthetic_menu_pix()))
        for i in range(13):
            atlas = G.QPixmap(512, 512)
            atlas.fill(G.QColor('#913ed0'))
            editor.m_textures[i] = atlas
        editor.m_background = False
        editor.m_motion = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_tint = True
        editor.m_lifecycle_combo.setCurrentIndex(1)

        def render():
            image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
            image.fill(G.QColor('#10151c'))
            painter = G.QPainter(image)
            try:
                editor.render(painter, C.QRect(0, 0, 512, 448))
            finally:
                painter.end()
            return bytes(image.constBits())

        runtime = editor.m_native_runtime
        hidden_pixels = render()
        runtime.m_shared['overlay_hidden'] = False
        runtime.m_shared['overlay_alpha'] = 0.5
        visible_pixels = render()
        self.assertNotEqual(hidden_pixels, visible_pixels)
        snapshot = runtime.snapshot()
        self.assertEqual(visible_pixels, render())
        self.assertEqual(snapshot, runtime.snapshot())
        runtime.m_shared['overlay_hidden'] = True
        self.assertEqual(render(), hidden_pixels)


    def test_native_submission_order_and_depth_aware_painter_order(self):
        """Source command order is preserved, while Qt approximates Z layers."""
        from PySide6 import QtCore as C, QtGui as G
        from unittest.mock import patch
        from arika_menu_compositor import software_painter_order

        editor = self.m_editor
        editor.m_textures[1] = G.QPixmap(2, 2)
        editor.m_lifecycle_combo.setCurrentIndex(1)
        runtime = editor.m_native_runtime
        runtime.m_outer_phase = 2
        runtime.m_pending = 0
        runtime.m_selected = 1
        runtime.m_item_phases[0] = 4
        runtime.m_item_phases[1] = 2
        runtime.m_first_states[0]['phase'] = 4
        runtime.m_first_states[1]['phase'] = 2
        runtime.m_small_states[0]['phase'] = 2
        runtime.m_shared['overlay_hidden'] = False
        runtime.m_shared['overlay_alpha'] = .5
        editor.m_item = 1
        editor.m_background = True
        editor.m_motion = True
        editor.m_tint = True
        editor.m_first = True
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False

        # These source geometry tags are deliberately unique; the first
        # item draw must follow the shared overlay and precede current.
        old_item = editor.m_data['items'][0]['first']
        new_item = editor.m_data['items'][1]['first']
        editor.m_data['items'][0]['first'] = [
            {'texture_entry': 100, 'geometry': old_item[0]['geometry']}]
        editor.m_data['items'][1]['first'] = [
            {'texture_entry': 101, 'geometry': new_item[0]['geometry']}]
        # Remove the independently tested dynamic strip geometry, leaving
        # this test focused on native parent and shared draw ordering.
        runtime.first_strip_geometry = lambda item: []
        runtime.particle_geometry = lambda item: []
        commands = []
        submissions = []

        def capture_native_submission(queue):
            submissions.extend(queue)
            return software_painter_order(queue)

        editor.draw_sprite = lambda painter, entry, geometry, alpha: (
            commands.append((entry, geometry.get('depth', None))))
        image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
        painter = G.QPainter(image)
        try:
            with patch('arika_menu_editor.software_painter_order',
                       side_effect=capture_native_submission):
                editor.render(painter, C.QRect(0, 0, 512, 448))
        finally:
            painter.end()
        self.assertEqual([q['entry'] for q in submissions],
                         [1, 2, 2, 2, 3, 8, 100, 101],
                         'native commands preserve shared/pending/current')
        self.assertEqual([entry for entry, _ in commands],
                         [q['entry'] for q in sorted(
                             submissions, key=lambda q: q['depth'])],
                         'Qt must compose by depth without changing commands')
        self.assertGreater(submissions[1]['depth'], submissions[4]['depth'],
                           'banner Z is above small sprite Z')
        self.assertLess(commands.index((3, 5)), commands.index((2, 99)),
                        'small sprite must paint behind the title')

        # The diagnostic timeline retains the original depth sort.
        editor.m_lifecycle_combo.setCurrentIndex(0)
        diagnostic = []
        editor.draw_sprite = lambda painter, entry, geometry, alpha: (
            diagnostic.append((entry, geometry.get('depth', 0))))
        painter = G.QPainter(image)
        try:
            editor.render(painter, C.QRect(0, 0, 512, 448))
        finally:
            painter.end()
        self.assertEqual(diagnostic[0][0], 1)
        self.assertEqual(diagnostic[-1][0], 2,
                         'diagnostic depth sorting places banner last')
        self.assertNotEqual([e for e, _ in diagnostic],
                            [e for e, _ in commands],
                            'native and authored diagnostic draw orders differ')

    def test_native_item3_draws_decorations_before_particle_pass(self):
        """0x37A910 draws two literals, then six decorations, then pool."""
        from PySide6 import QtCore as C, QtGui as G

        editor = self.m_editor
        editor.m_textures[1] = G.QPixmap(2, 2)
        editor.m_lifecycle_combo.setCurrentIndex(1)
        runtime = editor.m_native_runtime
        runtime.m_outer_phase = 2
        runtime.m_selected = 3
        runtime.m_pending = -1
        runtime.m_item_phases[3] = 2
        runtime.m_first_states[3]['phase'] = 2
        editor.m_item = 3
        editor.m_background = False
        editor.m_motion = False
        editor.m_tint = False
        editor.m_first = True
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        runtime.first_strip_geometry = lambda item: []
        parts = editor.m_data['items'][3]['first']
        self.assertEqual(len(parts), 8)
        # Eight first-layer sprite entries are followed by six-slot pool
        # quads. Their Z values differ but do not authorize reordering.
        editor.m_data['items'][3]['first'] = [
            {'texture_entry': i + 100,
             'geometry': original['geometry']}
            for i, original in enumerate(parts)]
        from unittest.mock import patch
        from arika_menu_compositor import software_painter_order

        commands = []
        submissions = []

        def capture_native_submission(queue):
            submissions.extend(queue)
            return software_painter_order(queue)

        editor.draw_sprite = lambda painter, entry, geometry, alpha: (
            commands.append(entry))
        painter_image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
        painter = G.QPainter(painter_image)
        try:
            with patch('arika_menu_editor.software_painter_order',
                       side_effect=capture_native_submission):
                editor.render(painter, C.QRect(0, 0, 512, 448))
        finally:
            painter.end()
        self.assertEqual([q['entry'] for q in submissions[:8]],
                         list(range(100, 108)))
        expected_particle_quads = len(runtime.particle_geometry(3))
        self.assertGreater(expected_particle_quads, 0)
        self.assertEqual([q['entry'] for q in submissions[8:]],
                         [11] * expected_particle_quads)
        self.assertEqual(commands, [q['entry'] for q in sorted(
            submissions, key=lambda q: q['depth'])])


    def test_title_depth_overlap_matches_reference_capture(self):
        """EE submits banner before small #2, but the title is visible.

        PCSX2 reference: banner [0,16]-[264,64] Z99 survives small #2
        [0,0]-[320,152] Z5, which is submitted afterward.
        Synthetic solid atlases test the overlap without game assets.
        """
        from PySide6 import QtCore as C, QtGui as G

        editor = self.m_editor
        banner_atlas = G.QPixmap(512, 512)
        banner_atlas.fill(G.QColor('#0838ff'))
        small_atlas = G.QPixmap(512, 512)
        small_atlas.fill(G.QColor('#ff3300'))
        editor.m_textures[2] = banner_atlas
        editor.m_textures[3] = small_atlas

        editor.m_background = False
        editor.m_motion = True
        editor.m_tint = False
        editor.m_first = False
        editor.m_middle = False
        editor.m_overlay = False
        editor.m_arrows = False
        editor.m_help_panel = False
        editor.m_presentation = 'raw'
        editor.m_lifecycle_combo.setCurrentIndex(1)

        runtime = editor.m_native_runtime
        runtime.m_outer_phase = 2
        runtime.m_banner_state.update(
            phase=2, age=0.0, offset=[0.0, 0.0])
        for state in runtime.m_small_states:
            state.update(phase=0, offset=[0.0, 0.0])
        runtime.m_small_states[2]['phase'] = 2

        image = G.QImage(512, 448, G.QImage.Format.Format_ARGB32)
        image.fill(G.QColor('#10151c'))
        painter = G.QPainter(image)
        before = runtime.snapshot()
        try:
            editor.render(painter, C.QRect(0, 0, 512, 448))
        finally:
            painter.end()

        self.assertEqual(image.pixelColor(100, 40), G.QColor('#0838ff'),
                         'banner is above small sprite at the overlap')
        self.assertEqual(image.pixelColor(100, 10), G.QColor('#ff3300'),
                         'small sprite remains visible outside title')
        self.assertEqual(before, runtime.snapshot(),
                         'software composition cannot advance native state')



if __name__ == '__main__':
    unittest.main()
