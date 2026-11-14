"""Qt lifecycle regressions for the full editor, without initialising a GPU."""
import importlib.util
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(
    all(importlib.util.find_spec(name) is not None for name in
        ('PySide6', 'shiboken6', 'rendercanvas', 'wgpu')),
    'Qt editor dependencies required'
)
class EditorShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets as W
        cls.m_app=W.QApplication.instance() or W.QApplication([])

    def test_font_panel_attaches_toolbar_layout_once(self):
        from PySide6 import QtCore as C
        from arika_editor import c_font_panel
        warnings=[]
        def handler(message_type,context,message):
            if message_type==C.QtMsgType.QtWarningMsg:
                warnings.append(message)
        previous=C.qInstallMessageHandler(handler)
        try:
            panel=c_font_panel(SimpleNamespace(m_font_font=None,m_font_data=None))
            self.assertEqual(panel.layout().count(),5)
            panel.close()
            panel.deleteLater()
            self.m_app.processEvents()
        finally:
            C.qInstallMessageHandler(previous)
        self.assertFalse(any('QLayout::addChildLayout' in warning for warning in warnings), warnings)

    def test_filter_handles_deleted_tree_wrapper_during_shutdown(self):
        from PySide6 import QtCore as C,QtWidgets as W
        import shiboken6
        from arika_editor import c_outliner_pinned_columns,c_outliner_tree

        tree=c_outliner_tree(SimpleNamespace(sync_outliner_scrollbar=lambda:None))
        tree.setHeaderLabels(['Scene / object','Show','Lock'])
        tree.set_pinned_columns()
        tree.resize(300,180)
        tree.show()
        self.m_app.processEvents()
        shiboken6.delete(tree)
        self.m_app.processEvents()
        self.assertFalse(shiboken6.isValid(tree))

        # The Qt event dispatcher can invoke the installed Python event
        # filter after its tree wrapper's C++ instance is destroyed.
        # Calling the override with a surrogate tests that exact guard.
        filter_state=SimpleNamespace(m_tree=tree)
        event=C.QEvent(C.QEvent.Type.Paint)
        self.assertFalse(c_outliner_pinned_columns.eventFilter(filter_state,None,event))


if __name__=='__main__':
    unittest.main()
