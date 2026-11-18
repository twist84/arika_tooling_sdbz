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
    press_start_comparison_metrics,
    raster_press_start_copyright, load_press_start_archive_font,
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

    def test_source_atlas_extents_are_required_for_all_original_draws(self):
        images, errors = load_press_start_archive_images({
            'dis/d03/d03t0101.pix': synthetic_tim2_rgba32(257, 306),
            'dis/d03/d03t0103.pix': synthetic_tim2_rgba32(512, 448),
            'dis/d05/d05t0101.pix': synthetic_tim2_rgba32(32, 110),
        })
        self.assertIsNone(images[0])
        self.assertIn('smaller than native sprite source', errors[0])
        self.assertIsNotNone(images[1])
        self.assertIsNone(images[2])
        self.assertIn('smaller than native sprite source', errors[2])

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


    def test_native_copyright_symbols_use_third_original_texture(self):
        background = self.texture((100, 10, 20, 255))
        symbols = self.texture((0, 0, 0, 0))
        painter = G.QPainter(symbols)
        painter.fillRect(C.QRect(15, 97, 17, 17),
                         G.QColor(20, 255, 80, 255))
        painter.end()
        native = render_press_start_image((None, background, symbols))
        self.assertEqual(native.pixelColor(68, 382).green(), 255)
        self.assertEqual(native.pixelColor(68, 399).green(), 255)
        self.assertEqual(native.pixelColor(68, 381).green(), 6)
        self.assertEqual(native.pixelColor(450, 420).green(), 6)

    def test_atlas_prompt_visibility_uses_three_elf_case_one_rectangles(self):
        foreground = self.texture((0, 0, 0, 0))
        painter = G.QPainter(foreground)
        painter.fillRect(C.QRect(0, 357, 99, 30),
                         G.QColor(0, 255, 0, 255))
        painter.fillRect(C.QRect(204, 357, 74, 30),
                         G.QColor(0, 0, 255, 255))
        painter.fillRect(C.QRect(99, 357, 105, 30),
                         G.QColor(255, 255, 0, 255))
        painter.end()
        background = self.texture((100, 20, 0, 255))
        hidden = render_press_start_image(
            (foreground, background, None), prompt_visible=False)
        visible = render_press_start_image(
            (foreground, background, None), prompt_visible=True)
        self.assertEqual(hidden.pixelColor(118, 345).green(), 12)
        self.assertEqual(visible.pixelColor(118, 345).green(), 255)
        self.assertEqual(visible.pixelColor(219, 345).blue(), 255)
        self.assertEqual(visible.pixelColor(295, 345).red(), 255)
        self.assertEqual(hidden.pixelColor(399, 345).red(), 60)
        with self.assertRaises(ValueError):
            render_press_start_image(
                (foreground, background, None), prompt_visible=1)

    def test_original_ffon_uses_shared_native_raster(self):
        from test_arika_menu_ffon_native import synthetic_font
        font, data = synthetic_font()
        images = raster_press_start_copyright(font, data)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].height(), 24)
        self.assertEqual(images[0].width(),
                         12 * len('1989 BIRD STUDIO/SHUEISHA, TOEI ANIMATION'))
        self.assertTrue(any(images[0].pixelColor(x, 0).alpha() != 0
                            for x in range(images[0].width())))
        blank, data, error = load_press_start_archive_font({})
        self.assertIsNone(blank)
        self.assertIsNone(data)
        self.assertIn('not found', error)

    def test_native_prompt_clock_steps_without_replacing_reference_toggle(self):
        viewer = c_press_start_preview()
        self.m_views.append(viewer)
        pix = synthetic_tim2_rgba32()
        mapping = {key + '.pix': pix for key in PRESS_START_RESOURCE_KEYS}
        viewer.load_archive_assets(mapping)
        self.assertFalse(viewer.m_prompt_clock.visible)
        viewer.m_delta.setValue(1.25)
        viewer.m_step.click()
        self.assertTrue(viewer.m_prompt_clock.visible)
        self.assertIn('native prompt 1.2500 s (visible)',
                      viewer.m_status.text())
        viewer.m_clock_enabled.setChecked(False)
        viewer.m_delta.setValue(1.0)
        viewer.m_step.click()
        self.assertEqual(viewer.m_prompt_clock.phase, 1.25)
        viewer.m_prompt_visible.setChecked(False)
        self.assertTrue(viewer.m_prompt_clock.visible)
        viewer.m_clock_enabled.setChecked(True)
        viewer.m_delta.setValue(2.0)
        viewer.m_step.click()
        self.assertFalse(viewer.m_prompt_clock.visible)
        self.assertEqual(viewer.m_prompt_clock.phase, 0.0)
        viewer.reset()
        self.assertEqual(viewer.m_prompt_clock.phase, 0.0)
        viewer.load_archive_assets({})
        self.assertIsNone(viewer.m_copyright_images)


    def test_all_prompt_cases_render_from_original_atlas(self):
        foreground = self.texture((0, 0, 0, 0))
        painter = G.QPainter(foreground)
        try:
            painter.fillRect(C.QRect(278, 357, 92, 30),
                             G.QColor(255, 40, 80, 255))
            painter.fillRect(C.QRect(0, 357, 99, 30),
                             G.QColor(20, 255, 50, 255))
        finally:
            painter.end()
        background = self.texture((100, 0, 0, 255))
        for case, initial_x in ((0, 154), (1, 116), (2, 88),
                                (3, 86), (4, 118)):
            with self.subTest(case=case):
                rendered = render_press_start_image(
                    (foreground, background, None),
                    prompt_visible=True, prompt_case=case)
                pixel = rendered.pixelColor(initial_x, 344)
                if case < 2:
                    self.assertGreater(pixel.green(), 240)
                else:
                    self.assertEqual(pixel.red(), 255)
                self.assertEqual(pixel.alpha(), 255)
        with self.assertRaisesRegex(ValueError, 'unsupported native prompt'):
            render_press_start_image(
                (foreground, background, None),
                prompt_visible=True, prompt_case=5)

    def test_native_prompt_case_selector_is_diagnostic(self):
        viewer = c_press_start_preview()
        self.m_views.append(viewer)
        pix = synthetic_tim2_rgba32()
        viewer.load_archive_assets({
            key + '.pix': pix for key in PRESS_START_RESOURCE_KEYS
        })
        self.assertEqual(viewer.m_prompt_case.currentData(), 1)
        self.assertIn('diagnostic', viewer.m_prompt_case.toolTip().lower())
        viewer.m_prompt_case.setCurrentIndex(3)
        self.assertEqual(viewer.m_prompt_case.currentData(), 3)
        self.assertIn('prompt case 3', viewer.m_status.text())
        viewer.m_delta.setValue(1.25)
        viewer.m_step.click()
        self.assertTrue(viewer.m_prompt_clock.visible)
        self.assertEqual(viewer.m_prompt_case.currentData(), 3)
        viewer.reset()
        self.assertEqual(viewer.m_prompt_case.currentData(), 3)
        self.assertEqual(viewer.load_archive_assets({}), 0)
        self.assertEqual(viewer.m_prompt_case.currentData(), 1)



    def test_both_pcsx2_states_have_explicit_pixel_error_metrics(self):
        foreground = self.texture((0, 0, 0, 0))
        background = self.texture((100, 40, 20, 255))
        hidden = render_press_start_image((foreground, background, None),
                                          prompt_visible=False)
        visible = render_press_start_image((foreground, background, None),
                                           prompt_visible=True)
        result = press_start_comparison_metrics(
            (foreground, background, None), hidden, visible)
        self.assertEqual(result['prompt_case'], 1)
        for state in ('hidden', 'visible'):
            data = result['reference_states'][state]
            self.assertEqual(data['all_pixels']['mean_absolute_error'], 0)
            self.assertEqual(data['all_pixels']['root_mean_square_error'], 0)
            self.assertEqual(data['registration'], 'none')
        shifted = self.texture((0, 0, 0, 255), 512, 448)
        errors = press_start_comparison_metrics(
            (foreground, background, None), hidden, shifted)
        self.assertEqual(
            errors['reference_states']['hidden']['all_pixels']
            ['mean_absolute_error'], 0)
        self.assertGreater(
            errors['reference_states']['visible']['all_pixels']
            ['mean_absolute_error'], 0)
        with self.assertRaisesRegex(ValueError, 'both original'):
            press_start_comparison_metrics(
                (foreground, background, None), hidden, None)

    def test_editor_measurement_is_explicit_and_invalidated_by_case_change(self):
        viewer = c_press_start_preview()
        self.m_views.append(viewer)
        pix = synthetic_tim2_rgba32()
        viewer.load_archive_assets({
            key + '.pix': pix for key in PRESS_START_RESOURCE_KEYS
        })
        self.assertFalse(viewer.m_measure.isEnabled())
        reconstruction = viewer.current_reconstruction()
        viewer.load_reference_capture(reconstruction, False)
        viewer.load_reference_capture(reconstruction, True)
        self.assertTrue(viewer.m_measure.isEnabled())
        viewer.m_measure.click()
        self.assertIn('hidden MAE 0.000', viewer.m_comparison_stats.text())
        self.assertIn('visible MAE', viewer.m_comparison_stats.text())
        self.assertIn('NOT GS parity', viewer.m_comparison_stats.text())
        viewer.m_prompt_case.setCurrentIndex(4)
        self.assertIn('not measured', viewer.m_comparison_stats.text())
        viewer.load_archive_assets({})
        self.assertFalse(viewer.m_measure.isEnabled())



if __name__ == '__main__':
    unittest.main()
