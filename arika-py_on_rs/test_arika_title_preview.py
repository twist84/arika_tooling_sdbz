"""Offscreen Qt tests for CAppTitleMain within the existing Arika Editor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shiboken6
import unittest
from PySide6 import QtGui as G, QtWidgets as W

from arika_title_preview import (
    c_title_preview, load_title_archive_image, title_diagnostic_canvas,
)
from arika_title_runtime import TITLE_RESOURCE
from test_arika_logo_preview import synthetic_tim2_rgba32, synthetic_fpix


class TitlePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.m_owned = []

    def make_view(self):
        view = c_title_preview()
        self.m_owned.append(view)
        return view

    def tearDown(self):
        for view in self.m_owned:
            if shiboken6.isValid(view):
                view.close()
                shiboken6.delete(view)
        self.m_app.processEvents()

    def test_exact_title_resource_matches_third_startup_logo(self):
        self.assertEqual(TITLE_RESOURCE, 'dis/d03/d03t0202')
        payload = synthetic_tim2_rgba32()
        image, error = load_title_archive_image({
            'DIS\D03\D03T0202.PIX': payload,
            'dis/main_menu.pix': b'ignore',
        })
        self.assertIsNone(error)
        self.assertEqual((image.width(), image.height()), (512, 512))
        self.assertEqual(image.pixelColor(2, 2).red(), 111)

    def test_ambiguous_missing_and_invalid_resources_are_not_guessed(self):
        data = synthetic_tim2_rgba32()
        image, error = load_title_archive_image({})
        self.assertIsNone(image)
        self.assertIn('not found', error)
        image, error = load_title_archive_image({
            'dis/d03/d03t0202': data,
            'dis/d03/d03t0202.pix': data,
        })
        self.assertIsNone(image)
        self.assertIn('ambiguous', error)
        image, error = load_title_archive_image({
            'dis/d03/d03t0202.pix': b'invalid',
        })
        self.assertIsNone(image)
        self.assertIn('unsupported', error)
        image, error = load_title_archive_image({
            'dis/d03/d03t0202.pix':
                synthetic_fpix(synthetic_tim2_rgba32(),
                               synthetic_tim2_rgba32()),
        })
        self.assertIsNone(image)
        self.assertIn('unambiguous', error)
        with self.assertRaises(TypeError):
            load_title_archive_image([])

    def test_qt_canvas_respects_512x448_native_sprite(self):
        texture = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        texture.fill(G.QColor(47, 83, 109))
        native = title_diagnostic_canvas(texture)
        self.assertEqual((native.width(), native.height()), (512, 448))
        pixel = native.pixelColor(256, 224)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()),
                         (47, 83, 109))
        self.assertEqual(title_diagnostic_canvas(None)
                         .pixelColor(256, 224).red(), 0)

    def test_in_editor_manual_four_second_gate_and_exit(self):
        widget = self.make_view()
        widget.m_step.click()  # phase 0 -> 1 on readiness
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 1)
        widget.m_delta.setValue(4.0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 1)
        widget.m_delta.setValue(1.0 / 60.0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        self.assertIn('0x2c08a0', widget.m_status.text())

        widget.m_busy.setChecked(True)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        widget.m_busy.setChecked(False)
        widget.m_step.click()
        self.assertTrue(widget.m_runtime.snapshot()['finished'])
        self.assertFalse(widget.m_play.isEnabled())
        self.assertFalse(widget.m_step.isEnabled())
        self.assertIn('0x3dfb00', widget.m_status.text())
        widget.m_reset.click()
        self.assertTrue(widget.m_play.isEnabled())
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 0)

    def test_play_pause_keeps_phase_and_manual_controls(self):
        widget = self.make_view()
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        self.assertFalse(widget.m_step.isEnabled())
        widget.m_timer.timeout.emit()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 1)
        updates = widget.m_runtime.snapshot()['updates']
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['updates'], updates)
        widget.m_play.click()
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Play')
        self.assertTrue(widget.m_step.isEnabled())
        widget.m_delta.setValue(4.1)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        self.assertEqual(widget.m_last_elapsed_ns, 0)
        widget.m_play.click()

    def test_archive_change_clears_stale_title_art(self):
        widget = self.make_view()
        self.assertEqual(widget.load_archive_assets({
            TITLE_RESOURCE + '.pix': synthetic_tim2_rgba32(),
        }), 1)
        self.assertIsNotNone(widget.m_image)
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        self.assertEqual(widget.load_archive_assets({}), 0)
        self.assertIsNone(widget.m_image)
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 0)
        self.assertFalse(widget.m_timer.isActive())
        self.assertIn('not found', widget.m_status.text())

    def test_editor_tab_switch_pauses_title_animation(self):
        widget = self.make_view()
        tabs = W.QTabWidget()
        tabs.addTab(widget, 'Title Screen')
        tabs.addTab(W.QWidget(), 'Startup / Splash')
        tabs.resize(750, 550)
        tabs.show()
        self.m_app.processEvents()
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        tabs.setCurrentIndex(1)
        self.m_app.processEvents()
        self.assertFalse(widget.m_timer.isActive())
        self.assertTrue(widget.m_step.isEnabled())
        self.assertIn('Paused', widget.m_status.text())
        tabs.close()

    def test_embedded_image_scales_to_four_three(self):
        widget = self.make_view()
        widget.load_archive_assets({
            TITLE_RESOURCE + '.pix': synthetic_tim2_rgba32(),
        })
        tabs = W.QTabWidget()
        tabs.addTab(widget, 'Title Screen')
        tabs.resize(700, 560)
        tabs.show()
        self.m_app.processEvents()
        bitmap = widget.m_canvas.pixmap()
        self.assertIsNotNone(bitmap)
        self.assertLessEqual(bitmap.width(), widget.m_canvas.width())
        self.assertLessEqual(bitmap.height(), widget.m_canvas.height())
        self.assertAlmostEqual(bitmap.width() / bitmap.height(), 4 / 3,
                               delta=0.02)
        tabs.close()


if __name__ == '__main__':
    unittest.main()
