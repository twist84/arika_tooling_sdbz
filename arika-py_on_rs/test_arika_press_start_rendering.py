"""Offscreen rendering and existing-tab regression tests for Press Start M1."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shiboken6
import unittest

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_press_start_preview import c_press_start_preview
from arika_press_start_rendering import (
    decode_press_start_texture, load_press_start_archive_images,
    render_press_start_image, press_start_comparison_image,
)
from arika_press_start_resources import PRESS_START_RESOURCE_KEYS
from test_arika_logo_preview import synthetic_tim2_rgba32, synthetic_fpix


class PressStartRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.m_views = []

    def tearDown(self):
        for view in self.m_views:
            if shiboken6.isValid(view):
                view.close()
                shiboken6.delete(view)
        self.m_app.processEvents()

    @staticmethod
    def texture(color, width=512, height=512):
        image = G.QImage(width, height, G.QImage.Format.Format_RGBA8888)
        image.fill(G.QColor(*color))
        return image

    def test_decode_only_unambiguous_original_tim2(self):
        tim2 = synthetic_tim2_rgba32()
        image = decode_press_start_texture(tim2)
        self.assertEqual((image.width(), image.height()), (512, 512))
        self.assertEqual(image.pixelColor(0, 0).red(), 111)
        self.assertEqual(decode_press_start_texture(synthetic_fpix(tim2))
                         .pixelColor(2, 3).blue(), 191)
        with self.assertRaisesRegex(ValueError, 'unambiguous'):
            decode_press_start_texture(synthetic_fpix(tim2, tim2))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            decode_press_start_texture(b'PNG')
        with self.assertRaises(TypeError):
            decode_press_start_texture('not bytes')

    def test_exact_resource_matching_rejects_ambiguous_and_short(self):
        pix = synthetic_tim2_rgba32()
        images, errors = load_press_start_archive_images({
            'DIS\\D03\\D03T0101.PIX': pix,
            '/dis/d03/d03t0103': synthetic_fpix(pix),
            'DIS/D05/D05T0101.PIX': pix,
            'dis/main_menu.pix': b'ignored',
        })
        self.assertTrue(all(image is not None for image in images))
        self.assertEqual(errors, [None, None, None])
        images, errors = load_press_start_archive_images({
            'dis/d03/d03t0101': pix,
            'dis/d03/d03t0101.pix': pix,
            'dis/d03/d03t0103': synthetic_tim2_rgba32(16, 16),
        })
        self.assertIsNone(images[0])
        self.assertIn('ambiguous', errors[0])
        self.assertIsNone(images[1])
        self.assertIn('smaller', errors[1])
        self.assertIsNone(images[2])
        self.assertIn('not found', errors[2])
        with self.assertRaises(TypeError):
            load_press_start_archive_images([])

    def test_background_then_foreground_native_geometry(self):
        foreground = self.texture((0, 250, 0, 255), 300, 320)
        background = self.texture((200, 0, 0, 255))
        third = self.texture((0, 0, 250, 255))
        image = render_press_start_image((foreground, background, third))
        self.assertEqual((image.width(), image.height()), (512, 448))
        outer = image.pixelColor(0, 0)
        self.assertGreaterEqual(outer.red(), 118)
        self.assertLessEqual(outer.red(), 122)
        self.assertEqual(outer.green(), 0)
        self.assertEqual(image.pixelColor(128, 28).green(), 250)
        self.assertEqual(image.pixelColor(384, 333).green(), 250)
        self.assertGreaterEqual(image.pixelColor(385, 333).red(), 118)
        # The unverified dynamic third sprite must NOT be drawn arbitrarily.
        self.assertEqual(image.pixelColor(450, 400).blue(), 0)
        self.assertIsNone(render_press_start_image((None, None, third)))
        with self.assertRaises(ValueError):
            render_press_start_image((foreground, background))

    def test_compare_keeps_reference_separate_from_reconstruction(self):
        reconstruction = self.texture((6, 30, 80, 255), 512, 448)
        reference = self.texture((90, 20, 8, 255), 640, 480)
        combined = press_start_comparison_image(reconstruction, reference)
        self.assertEqual((combined.width(), combined.height()), (1280, 480))
        self.assertEqual(combined.pixelColor(10, 10).blue(), 80)
        self.assertEqual(combined.pixelColor(900, 10).red(), 90)
        self.assertEqual(reconstruction.pixelColor(10, 10).red(), 6)
        with self.assertRaises(ValueError):
            press_start_comparison_image(None, reference)

    def test_existing_tab_uses_real_resources_and_resets_on_archive(self):
        viewer = c_press_start_preview()
        self.m_views.append(viewer)
        pix = synthetic_tim2_rgba32()
        mapping = {key + '.pix': pix for key in PRESS_START_RESOURCE_KEYS}
        self.assertEqual(viewer.load_archive_assets(mapping), 3)
        self.assertIsNotNone(viewer.current_reconstruction())
        self.assertIn('decoded resources 3/3', viewer.m_status.text())
        self.assertEqual(viewer.m_view_mode.currentIndex(), 0)
        visible = self.texture((4, 90, 170, 255), 640, 480)
        hidden = self.texture((7, 40, 20, 255), 640, 480)
        viewer.load_reference_capture(visible, True)
        viewer.load_reference_capture(hidden, False)
        viewer.m_view_mode.setCurrentIndex(1)
        self.assertEqual(viewer.m_canvas.pixmap().isNull(), False)
        original = viewer.current_reconstruction().pixelColor(0, 0)
        viewer.m_prompt_visible.setChecked(False)
        self.assertEqual(viewer.current_reconstruction().pixelColor(0, 0),
                         original)
        viewer.m_play.click()
        self.assertTrue(viewer.m_timer.isActive())
        self.assertEqual(viewer.load_archive_assets({}), 0)
        self.assertFalse(viewer.m_timer.isActive())
        self.assertIsNone(viewer.current_reconstruction())
        self.assertIsNone(viewer.m_reference_visible)
        self.assertEqual(viewer.m_runtime.snapshot()['updates'], 0)
        self.assertEqual(viewer.m_view_mode.currentIndex(), 0)
        self.assertIn('decoded resources 0/3', viewer.m_status.text())


if __name__ == '__main__':
    unittest.main()
