"""Qt smoke tests for recovered main-menu navigation in the integrated preview."""
import importlib.util
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_HAS_QT = importlib.util.find_spec('PySide6') is not None


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
