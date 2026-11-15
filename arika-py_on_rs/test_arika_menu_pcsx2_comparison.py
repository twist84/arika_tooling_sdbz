"""Screenshot-grounded PCSX2 settings and opt-in Qt approximation tests."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from arika_menu_pcsx2_comparison import (
    PREVIEW_APPROXIMATE, PREVIEW_REFERENCE_ONLY,
    s_pcsx2_comparison_settings,
)

_HAS_QT = importlib.util.find_spec('PySide6') is not None


class Pcsx2ComparisonSettingsTests(unittest.TestCase):
    def test_screenshot_preset_matches_exact_resolved_values(self):
        settings = s_pcsx2_comparison_settings()
        self.assertEqual(settings.graphics_api, 'Direct3D 12')
        self.assertEqual(settings.adapter, 'NVIDIA GeForce GTX 1660 SUPER')
        self.assertEqual(settings.internal_resolution, 4)
        self.assertEqual(settings.texture_filtering, 'bilinear_ps2')
        self.assertEqual(settings.trilinear_filtering, 'automatic')
        self.assertEqual(settings.anisotropic_filtering, 0)
        self.assertEqual(settings.dithering, 'unscaled')
        self.assertEqual(settings.blending_accuracy, 'basic')
        self.assertTrue(settings.mipmapping)
        self.assertTrue(settings.aa1)
        self.assertTrue(settings.manual_hardware_fixes)
        self.assertFalse(settings.accurate_alpha_test)
        self.assertFalse(settings.rasterizer_ordered_view)

    def test_logical_supersampling_and_aspect_ratio(self):
        settings = s_pcsx2_comparison_settings()
        self.assertEqual(settings.internal_canvas_size(), (2048, 1536))
        self.assertEqual(settings.internal_canvas_size(448.0), (2048, 1792))
        self.assertEqual(
            settings.with_changes(internal_resolution=1).internal_canvas_size(),
            (512, 384))
        self.assertEqual(
            settings.with_changes(internal_resolution=6).internal_canvas_size(288),
            (3072, 1728))
        with self.assertRaises(ValueError):
            settings.internal_canvas_size(0)

    def test_texture_filtering_and_unimplemented_settings_stay_distinct(self):
        settings = s_pcsx2_comparison_settings()
        self.assertTrue(settings.approximate_linear_filter())
        self.assertFalse(settings.with_changes(
            texture_filtering='nearest').approximate_linear_filter())
        self.assertTrue(settings.with_changes(
            texture_filtering='bilinear_forced').approximate_linear_filter())
        metadata = settings.to_metadata()
        self.assertEqual(set(metadata['preview_applied_approximately']),
                         PREVIEW_APPROXIMATE)
        self.assertEqual(set(metadata['pcsx2_reference_only']),
                         PREVIEW_REFERENCE_ONLY)
        self.assertIn('not PCSX2/GS emulation', metadata['warning'])

    def test_invalid_profile_is_rejected_and_immutable(self):
        original = s_pcsx2_comparison_settings()
        for overrides in (
            {'internal_resolution': 0},
            {'texture_filtering': 'invalid'},
            {'trilinear_filtering': 'invalid'},
            {'anisotropic_filtering': 3},
            {'dithering': 'invalid'},
            {'blending_accuracy': 'invalid'},
            {'aa1': 1},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                original.with_changes(**overrides)
        self.assertEqual(original.internal_resolution, 4)
        self.assertTrue(original.aa1)


@unittest.skipUnless(_HAS_QT, 'PySide6 required for Qt PCSX2 comparison tests')
class Pcsx2ComparisonQtTests(unittest.TestCase):
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

    def test_pcsx2_dialog_restores_screenshot_preset(self):
        from arika_menu_pcsx2_dialog import c_pcsx2_comparison_dialog
        settings = s_pcsx2_comparison_settings().with_changes(
            internal_resolution=2, texture_filtering='nearest',
            dithering='off', aa1=False)
        dialog = c_pcsx2_comparison_dialog(settings, False, self.m_editor)
        self.assertFalse(dialog.m_enabled.isChecked())
        self.assertEqual(dialog.m_choices['internal_resolution'].currentData(), 2)
        self.assertEqual(dialog.m_choices['texture_filtering'].currentData(),
                         'nearest')
        self.assertEqual(dialog.selected_settings(), settings)
        dialog.restore_screenshot_preset()
        self.assertTrue(dialog.m_enabled.isChecked())
        self.assertEqual(dialog.selected_settings(),
                         s_pcsx2_comparison_settings())
        self.assertEqual(dialog.m_api.text(), 'Direct3D 12')
        self.assertTrue(dialog.m_api.isReadOnly())
        dialog.close()

    def test_opt_in_keeps_original_renderer_and_changes_offscreen_raster(self):
        from PySide6 import QtCore as C, QtGui as G
        editor = self.m_editor
        self.assertFalse(editor.m_pcsx2_enabled)
        self.assertFalse(editor.m_pcsx2_capture_button.isEnabled())

        frame = G.QImage(512, 384, G.QImage.Format.Format_ARGB32)
        frame.fill(G.QColor('#10151c'))
        painter = G.QPainter(frame)
        try:
            with patch.object(editor, 'render') as render:
                editor.render_canvas(painter, C.QRect(0, 0, 512, 384))
                render.assert_called_once()
        finally:
            painter.end()

        settings = s_pcsx2_comparison_settings().with_changes(
            internal_resolution=2, texture_filtering='nearest')
        editor.apply_pcsx2_comparison(settings, enabled=True)
        self.assertTrue(editor.m_pcsx2_capture_button.isEnabled())
        self.assertIn('Qt raster 1024x768', editor.m_pcsx2_status.text())
        image = editor.render_comparison_image()
        self.assertEqual((image.width(), image.height()), (1024, 768))

        editor.m_presentation_combo.setCurrentIndex(
            editor.m_presentation_combo.findData('raw'))
        self.assertIn('Qt raster 1024x896', editor.m_pcsx2_status.text())
        editor.apply_pcsx2_comparison(settings, enabled=False)
        self.assertFalse(editor.m_pcsx2_capture_button.isEnabled())
        self.assertFalse(editor.m_pcsx2_enabled)
        self.assertTrue(editor.m_smooth, 'existing diagnostics unchanged')

    def test_lossless_png_with_reference_only_settings_sidecar(self):
        editor = self.m_editor
        settings = s_pcsx2_comparison_settings().with_changes(
            internal_resolution=1)
        editor.apply_pcsx2_comparison(settings)
        with tempfile.TemporaryDirectory() as root:
            png = Path(root) / 'comparison.png'
            with patch('arika_menu_editor.W.QFileDialog.getSaveFileName',
                       return_value=(str(png), 'PNG images (*.png)')):
                editor.capture_pcsx2_comparison()
            metadata_path = png.with_suffix('.pcsx2-settings.json')
            self.assertTrue(png.is_file())
            self.assertTrue(metadata_path.is_file())
            self.assertEqual(png.read_bytes()[:8], b'\\x89PNG\\r\\n\\x1a\\n')
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            self.assertEqual(metadata['image_size'], [512, 384])
            self.assertEqual(metadata['internal_resolution'], 1)
            self.assertFalse(metadata['native_lifecycle'])
            self.assertIsNone(metadata['native_tick'])
            self.assertEqual(metadata['presentation'], 'tv_4_3')
            self.assertIn('NOT a PCSX2/GS capture', metadata['source'])


if __name__ == '__main__':
    unittest.main()
