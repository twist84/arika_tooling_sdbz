"""Offscreen Qt warning-screen tests using synthetic game-free TIM2."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
from PySide6 import QtGui as G, QtWidgets as W

from arika_warning_preview import (
    c_warning_preview, load_warning_archive_image, warning_diagnostic_canvas,
)
from arika_warning_runtime import (
    WARNING_RESOURCE, PHASE_SELECTION, PHASE_TEST_DISPLAY,
    PHASE_TEST_FADE_BACK,
)
from test_arika_logo_preview import synthetic_tim2_rgba32


class WarningPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def test_exact_warning_resource_lookup(self):
        payload = synthetic_tim2_rgba32()
        image, error = load_warning_archive_image({
            r'DIS\D03\D03T0801.PIX': payload,
            'dis/main_menu.pix': b'not the warning',
        })
        self.assertIsNone(error)
        self.assertEqual((image.width(), image.height()), (512, 512))
        self.assertEqual(image.pixelColor(1, 1).red(), 111)

    def test_missing_or_duplicate_archive_resource(self):
        image, error = load_warning_archive_image({})
        self.assertIsNone(image)
        self.assertIn('not found', error)
        image, error = load_warning_archive_image({
            'dis/d03/d03t0801': synthetic_tim2_rgba32(),
            'DIS/d03/d03t0801.PIX': synthetic_tim2_rgba32(),
        })
        self.assertIsNone(image)
        self.assertIn('ambiguous', error)
        with self.assertRaises(TypeError):
            load_warning_archive_image([])

    def test_unsupported_data_is_not_replaced_with_fake_art(self):
        image, error = load_warning_archive_image({
            WARNING_RESOURCE + '.pix': b'not a native asset',
        })
        self.assertIsNone(image)
        self.assertIn('unsupported', error)

    def test_image_renders_only_under_native_flag(self):
        image = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        image.fill(G.QColor(11, 55, 99))
        data = {'phase': 2, 'selection': 0, 'image_visible': True}
        canvas = warning_diagnostic_canvas(data, image)
        self.assertEqual((canvas.width(), canvas.height()), (512, 448))
        pixel = canvas.pixelColor(256, 224)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()),
                         (11, 55, 99))
        data['phase'] = 10
        blank = warning_diagnostic_canvas(data, image)
        self.assertEqual(blank.pixelColor(256, 224).red(), 0)
        data['phase'] = 2
        data['image_visible'] = False
        debug = warning_diagnostic_canvas(data, image)
        self.assertEqual(debug.width(), 512)

    def test_selection_buttons_and_mode_branch(self):
        widget = c_warning_preview()
        self.assertFalse(widget.m_next.isEnabled())
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], PHASE_SELECTION)
        self.assertTrue(widget.m_next.isEnabled())
        widget.m_next.click()
        self.assertEqual(widget.m_runtime.snapshot()['selection'], 1)
        widget.m_confirm.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 10)
        self.assertFalse(widget.m_confirm.isEnabled())
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], PHASE_SELECTION)
        self.assertIn('0x1998a0', widget.m_status.text())
        widget.close()

    def test_manual_test_screen_countdown_and_return(self):
        widget = c_warning_preview()
        widget.load_archive_assets({
            WARNING_RESOURCE + '.pix': synthetic_tim2_rgba32(),
        })
        widget.m_step.click()
        widget.m_next.click()
        widget.m_next.click()
        self.assertEqual(widget.m_runtime.snapshot()['selection'], 2)
        widget.m_confirm.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 20)
        widget.m_step.click()
        widget.m_step.click()
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'],
                         PHASE_TEST_DISPLAY)
        self.assertTrue(widget.m_runtime.snapshot()['image_visible'])
        widget.m_delta.setValue(5.0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'],
                         PHASE_TEST_DISPLAY)
        widget.m_delta.setValue(1.0 / 60.0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'],
                         PHASE_TEST_FADE_BACK)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 1)
        self.assertFalse(widget.m_runtime.snapshot()['image_visible'])
        widget.close()

    def test_play_pause_auto_clock_and_reset(self):
        widget = c_warning_preview()
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Pause')
        self.assertFalse(widget.m_step.isEnabled())
        widget.m_timer.timeout.emit()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], PHASE_SELECTION)
        widget.m_play.click()
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Play')
        self.assertTrue(widget.m_step.isEnabled())
        widget.m_play.click()
        self.assertEqual(widget.m_last_elapsed_ns, 0)
        widget.m_reset.click()
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 0)
        widget.close()

    def test_archive_reload_pauses_and_clears_image(self):
        widget = c_warning_preview()
        self.assertEqual(widget.load_archive_assets({
            WARNING_RESOURCE + '.pix': synthetic_tim2_rgba32(),
        }), 1)
        self.assertIsNotNone(widget.m_image)
        widget.m_play.click()
        self.assertEqual(widget.load_archive_assets({}), 0)
        self.assertFalse(widget.m_timer.isActive())
        self.assertIsNone(widget.m_image)
        self.assertEqual(widget.m_runtime.snapshot()['updates'], 0)
        widget.close()

    def test_to_game_completion_disables_playback(self):
        widget = c_warning_preview()
        widget.m_step.click()
        widget.m_previous.click()
        widget.m_confirm.click()
        widget.m_step.click()
        widget.m_step.click()
        self.assertTrue(widget.m_runtime.snapshot()['finished'])
        self.assertFalse(widget.m_play.isEnabled())
        self.assertFalse(widget.m_step.isEnabled())
        self.assertIn('0x3dfb00', widget.m_status.text())
        widget.m_reset.click()
        self.assertTrue(widget.m_play.isEnabled())
        widget.close()

    def test_switching_editor_tabs_stops_timer(self):
        tabs = W.QTabWidget()
        viewer = c_warning_preview()
        tabs.addTab(viewer, 'Warning / Video Mode')
        tabs.addTab(W.QWidget(), 'Startup / Splash')
        tabs.resize(800, 560)
        tabs.show()
        self.m_app.processEvents()
        viewer.m_play.click()
        tabs.setCurrentIndex(1)
        self.m_app.processEvents()
        self.assertFalse(viewer.m_timer.isActive())
        self.assertTrue(viewer.m_step.isEnabled())
        self.assertIn('Paused', viewer.m_status.text())
        tabs.close()


if __name__ == '__main__':
    unittest.main()
