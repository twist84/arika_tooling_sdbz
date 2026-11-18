"""Offscreen Qt Press Start and application-ID-3 inspector regressions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shiboken6
import unittest
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_press_start_preview import (
    c_press_start_preview, extract_press_start_reference,
    press_start_diagnostic_canvas, PCSX2_REFERENCE_RECT,
)
from arika_press_start_runtime import (
    PHASE_START_TRANSITION, PHASE_START_WAIT, PHASE_ATTRACT_WAIT,
    PHASE_WAIT_FOR_START,
)
from arika_demo_main_preview import c_demo_main_preview


def make_pcsx2_test_capture(color):
    image = G.QImage(1920, 1040, G.QImage.Format.Format_RGB32)
    image.fill(G.QColor(0, 0, 0))
    painter = G.QPainter(image)
    painter.fillRect(C.QRect(*PCSX2_REFERENCE_RECT), G.QColor(*color))
    painter.end()
    return image


class PressStartPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.m_owned = []

    def make_view(self, cls):
        view = cls()
        self.m_owned.append(view)
        return view

    def tearDown(self):
        # Explicit Qt C++ deletion avoids late interpreter shutdown cycles.
        for widget in self.m_owned:
            if shiboken6.isValid(widget):
                widget.close()
                shiboken6.delete(widget)
        self.m_app.processEvents()

    def test_user_capture_rect_is_actual_four_three_viewport(self):
        image = make_pcsx2_test_capture((10, 50, 90))
        cropped = extract_press_start_reference(image)
        self.assertEqual((cropped.width(), cropped.height()), (1206, 903))
        pixel = cropped.pixelColor(520, 390)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()),
                         (10, 50, 90))
        direct = G.QImage(640, 480, G.QImage.Format.Format_RGB32)
        direct.fill(G.QColor(1, 2, 3))
        self.assertEqual((extract_press_start_reference(direct).width(),
                          extract_press_start_reference(direct).height()),
                         (640, 480))
        bad = G.QImage(700, 380, G.QImage.Format.Format_RGB32)
        with self.assertRaisesRegex(ValueError, 'expected a 4:3'):
            extract_press_start_reference(bad)
        with self.assertRaises(ValueError):
            extract_press_start_reference(G.QImage())

    def test_reference_captures_are_optional_and_manual_not_bundled(self):
        viewer = self.make_view(c_press_start_preview)
        self.assertIsNone(viewer.m_reference_hidden)
        self.assertIsNone(viewer.m_reference_visible)
        hidden = make_pcsx2_test_capture((70, 25, 50))
        visible = make_pcsx2_test_capture((5, 155, 220))
        viewer.load_reference_capture(hidden, False)
        viewer.load_reference_capture(visible, True)
        self.assertIn('reference captures 2/2', viewer.m_status.text())
        self.assertTrue(viewer.m_prompt_visible.isChecked())
        self.assertEqual(viewer.m_reference_visible.pixelColor(5, 5).green(),
                         155)
        viewer.m_prompt_visible.setChecked(False)
        self.assertEqual(viewer.m_reference_hidden.pixelColor(5, 5).red(),
                         70)
        self.assertIn('phase 0', viewer.m_status.text())
        with self.assertRaises(ValueError):
            viewer.load_reference_capture(hidden, 1)
        viewer.clear_reference_captures()
        self.assertIn('reference captures 0/2', viewer.m_status.text())

    def test_fallback_is_labeled_diagnostic_with_optional_prompt(self):
        with_prompt = press_start_diagnostic_canvas(True)
        without = press_start_diagnostic_canvas(False)
        self.assertEqual((with_prompt.width(), with_prompt.height()),
                         (640, 480))
        self.assertNotEqual(with_prompt.pixelColor(320, 387),
                            without.pixelColor(320, 387))
        viewer = self.make_view(c_press_start_preview)
        self.assertIn('NOT recreated native GS', viewer.m_notice.text())

    def test_native_controller_zero_and_complete_return_to_id_42(self):
        viewer = self.make_view(c_press_start_preview)
        received = []
        viewer.transition_requested.connect(received.append)
        self.assertFalse(viewer.m_inspect.isEnabled())
        viewer.m_start_0.click()
        self.assertEqual(viewer.m_runtime.snapshot()['phase'],
                         PHASE_START_TRANSITION)
        self.assertIn('0x3eb040', viewer.m_calls.text())
        self.assertFalse(viewer.m_start_0.isEnabled())
        viewer.m_step.click()
        self.assertEqual(viewer.m_runtime.snapshot()['phase'],
                         PHASE_START_WAIT)
        viewer.m_transition_busy.setChecked(True)
        viewer.m_step.click()
        self.assertFalse(viewer.m_runtime.snapshot()['finished'])
        viewer.m_transition_busy.setChecked(False)
        viewer.m_step.click()
        self.assertTrue(viewer.m_runtime.snapshot()['finished'])
        self.assertEqual(viewer.m_runtime.snapshot()['destination_id'], 42)
        self.assertFalse(viewer.m_play.isEnabled())
        self.assertFalse(viewer.m_step.isEnabled())
        self.assertTrue(viewer.m_inspect.isEnabled())
        viewer.m_inspect.click()
        self.assertEqual(received, [42])
        viewer.m_reset.click()
        self.assertFalse(viewer.m_inspect.isEnabled())
        self.assertEqual(viewer.m_runtime.snapshot()['phase'],
                         PHASE_WAIT_FOR_START)

    def test_controller_one_eligibility_gate(self):
        viewer = self.make_view(c_press_start_preview)
        viewer.m_controller1_ready.setChecked(False)
        viewer.m_start_1.click()
        self.assertEqual(viewer.m_runtime.snapshot()['phase'], 0)
        viewer.m_controller1_ready.setChecked(True)
        viewer.m_start_1.click()
        self.assertEqual(viewer.m_runtime.snapshot()['phase'],
                         PHASE_START_TRANSITION)
        self.assertIn('0x3eb040', viewer.m_calls.text())

    def test_idle_twenty_seconds_and_demo_handoff(self):
        viewer = self.make_view(c_press_start_preview)
        requested = []
        viewer.transition_requested.connect(requested.append)
        viewer.m_delta.setValue(20.0)
        viewer.m_step.click()
        self.assertEqual(viewer.m_runtime.snapshot()['phase'],
                         PHASE_ATTRACT_WAIT)
        self.assertIn('0x2c08a0', viewer.m_calls.text())
        viewer.m_transition_busy.setChecked(True)
        viewer.m_step.click()
        self.assertFalse(viewer.m_runtime.snapshot()['finished'])
        viewer.m_transition_busy.setChecked(False)
        viewer.m_step.click()
        self.assertTrue(viewer.m_runtime.snapshot()['finished'])
        self.assertEqual(viewer.m_runtime.snapshot()['destination_id'], 6)
        viewer.m_inspect.click()
        self.assertEqual(requested, [6])

    def test_idle_helper_prevents_timeout(self):
        viewer = self.make_view(c_press_start_preview)
        viewer.m_delta.setValue(20)
        viewer.m_idle_reset.setChecked(True)
        viewer.m_step.click()
        self.assertEqual(viewer.m_runtime.snapshot()['phase'], 0)
        self.assertEqual(viewer.m_runtime.snapshot()['elapsed_seconds'], 0)
        viewer.m_idle_reset.setChecked(False)
        viewer.m_delta.setValue(1)
        viewer.m_step.click()
        self.assertEqual(viewer.m_runtime.snapshot()['elapsed_seconds'], 1)

    def test_pause_resume_hide_and_archive_replace(self):
        viewer = self.make_view(c_press_start_preview)
        tabs = self.make_view(W.QTabWidget)
        tabs.addTab(viewer, 'Press Start')
        tabs.addTab(W.QWidget(), 'Demo Main')
        tabs.resize(900, 700)
        tabs.show()
        self.m_app.processEvents()
        viewer.m_play.click()
        self.assertTrue(viewer.m_timer.isActive())
        self.assertFalse(viewer.m_step.isEnabled())
        viewer.m_timer.timeout.emit()
        self.assertEqual(viewer.m_runtime.snapshot()['updates'], 1)
        viewer.m_play.click()
        self.assertFalse(viewer.m_timer.isActive())
        self.assertTrue(viewer.m_step.isEnabled())
        viewer.m_play.click()
        tabs.setCurrentIndex(1)
        self.m_app.processEvents()
        self.assertFalse(viewer.m_timer.isActive())
        self.assertIn('Paused', viewer.m_status.text())
        viewer.load_reference_capture(make_pcsx2_test_capture((5, 6, 7)),
                                      False)
        viewer.load_archive_assets({})
        self.assertIsNone(viewer.m_reference_hidden)
        self.assertEqual(viewer.m_runtime.snapshot()['updates'], 0)
        self.assertFalse(viewer.m_timer.isActive())
        tabs.close()

    def test_demo_parent_id_three_routes_by_explicit_signal(self):
        demo = self.make_view(c_demo_main_preview)
        press = self.make_view(c_press_start_preview)
        tabs = self.make_view(W.QTabWidget)
        tabs.addTab(demo, 'Demo Main')
        tabs.addTab(press, 'Press Start')
        targets = []

        def inspect_parent(app_id):
            targets.append(app_id)
            if app_id == 3:
                press.reset()
                tabs.setCurrentWidget(press)

        demo.parent_requested.connect(inspect_parent)
        tabs.resize(850, 600)
        tabs.show()
        self.m_app.processEvents()
        self.assertFalse(demo.m_inspect_parent.isEnabled())
        demo.m_next_choice.setCurrentIndex(1)
        demo.m_set_choice.click()
        demo.m_child_pending.setChecked(False)
        demo.m_update_step.click()
        self.assertTrue(demo.m_bootstrap.m_update.snapshot()['finished'])
        self.assertTrue(demo.m_inspect_parent.isEnabled())
        demo.m_inspect_parent.click()
        self.assertEqual(targets, [3])
        self.assertIs(tabs.currentWidget(), press)
        self.assertFalse(press.m_runtime.snapshot()['finished'])
        self.assertEqual(press.m_runtime.snapshot()['phase'], 0)
        tabs.close()


if __name__ == '__main__':
    unittest.main()
