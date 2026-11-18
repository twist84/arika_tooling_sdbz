"""Offscreen Qt app-manager handoff tests with no game artwork."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shiboken6
import unittest

from PySide6 import QtWidgets as W
from arika_demo_main_preview import c_demo_main_preview
from arika_title_preview import c_title_preview
from arika_title_runtime import c_title_runtime


def completed_title():
    native = c_title_runtime()
    native.step(0, False)
    native.step(4.1, False)
    return native.step(0, False)


class DemoMainPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.m_windows = []

    def make_window(self, cls):
        window = cls()
        self.m_windows.append(window)
        return window

    def tearDown(self):
        for window in self.m_windows:
            if shiboken6.isValid(window):
                window.close()
                shiboken6.delete(window)
        self.m_app.processEvents()

    def test_loader_inspector_waits_for_explicit_external_readiness(self):
        inspector = self.make_window(c_demo_main_preview)
        self.assertIn('No title handoff', inspector.m_route.text())
        self.assertIn('Loader phase 0', inspector.m_status.text())
        inspector.m_step.click()
        self.assertEqual(inspector.m_bootstrap.snapshot()['load_phase'], 1)
        self.assertEqual(inspector.m_bootstrap.snapshot()['load_updates'], 1)
        inspector.m_step.click()
        self.assertEqual(inspector.m_bootstrap.snapshot()['load_phase'], 1)
        self.assertFalse(inspector.m_bootstrap.snapshot()['ready'])
        inspector.m_ready.setChecked(True)
        inspector.m_step.click()
        self.assertTrue(inspector.m_bootstrap.snapshot()['ready'])
        self.assertIn('ready', inspector.m_status.text())
        self.assertFalse(inspector.m_step.isEnabled())
        inspector.m_reset.click()
        self.assertTrue(inspector.m_step.isEnabled())
        self.assertFalse(inspector.m_ready.isChecked())

    def test_title_handoff_is_explicit_not_automatic_execution(self):
        title = self.make_window(c_title_preview)
        inspector = self.make_window(c_demo_main_preview)
        events = []
        title.handoff_requested.connect(events.append)
        title.handoff_requested.connect(inspector.accept_title_result)
        self.assertFalse(title.m_destination.isEnabled())
        title.m_step.click()
        title.m_delta.setValue(4.1)
        title.m_step.click()
        self.assertFalse(title.m_destination.isEnabled())
        title.m_step.click()
        self.assertTrue(title.m_destination.isEnabled())
        self.assertIn('CAppDemoMain', title.m_status.text())
        self.assertFalse(inspector.m_bootstrap.snapshot()['handoff_requested'])

        title.m_destination.click()
        self.assertEqual(len(events), 1)
        self.assertTrue(inspector.m_bootstrap.snapshot()['handoff_requested'])
        self.assertFalse(inspector.m_bootstrap.snapshot()['constructor_executed'])
        self.assertIn('CAppDemoMain', inspector.m_route.text())
        self.assertIn('ID 6', inspector.m_route.text())

        title.m_reset.click()
        self.assertFalse(title.m_destination.isEnabled())
        self.assertEqual(title.m_runtime.snapshot()['phase'], 0)
        title.load_archive_assets({})
        self.assertFalse(title.m_destination.isEnabled())

    def test_fifth_tab_can_receive_title_signal_without_host_execution(self):
        tab = self.make_window(W.QTabWidget)
        title = self.make_window(c_title_preview)
        inspector = self.make_window(c_demo_main_preview)
        tab.addTab(title, 'Title Screen')
        tab.addTab(inspector, 'Demo Main')
        def inspect_target(result):
            if inspector.accept_title_result(result):
                tab.setCurrentWidget(inspector)
        title.handoff_requested.connect(inspect_target)
        tab.show()
        self.m_app.processEvents()
        title.m_step.click()
        title.m_delta.setValue(5.0)
        title.m_step.click()
        title.m_step.click()
        title.m_destination.click()
        self.assertIs(tab.currentWidget(), inspector)
        self.assertIn('CAppDemoMain', inspector.m_route.text())
        self.assertEqual(inspector.m_bootstrap.snapshot()['destination_id'], 6)

    def test_inspect_native_child_paths_are_not_movie_playback(self):
        inspector = self.make_window(c_demo_main_preview)
        observed = []
        for index, child_id in enumerate((4, 7, 8, 9)):
            inspector.m_child_combo.setCurrentIndex(index)
            inspector.m_child_button.click()
            self.assertIsNotNone(inspector.m_last_child)
            self.assertEqual(inspector.m_last_child['requested_child_id'],
                             child_id)
            self.assertFalse(inspector.m_last_child['executed'])
            observed.append(inspector.m_last_child['request_site'])
        self.assertEqual(len(set(observed)), 4)
        self.assertIn('unresolved', inspector.m_child_info.text().lower())
        self.assertFalse(inspector.m_bootstrap.snapshot()['handoff_requested'])

    def test_archive_change_clears_title_handoff_and_loader_state(self):
        inspector = self.make_window(c_demo_main_preview)
        self.assertTrue(inspector.accept_title_result(completed_title()))
        inspector.m_step.click()
        self.assertEqual(inspector.m_bootstrap.snapshot()['load_phase'], 1)
        inspector.load_archive_assets({'dis/d03/d03t0202.pix': b'irrelevant'})
        self.assertFalse(inspector.m_bootstrap.snapshot()['handoff_requested'])
        self.assertEqual(inspector.m_bootstrap.snapshot()['load_phase'], 0)
        self.assertIsNone(inspector.m_last_child)
        self.assertIn('No title handoff', inspector.m_route.text())


if __name__ == '__main__':
    unittest.main()
