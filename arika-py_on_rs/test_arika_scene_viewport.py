"""Exercise the real Qt/rendercanvas scheduler without requiring a GPU."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                         ('PySide6','rendercanvas','wgpu')), 'Qt/WebGPU dependencies required')
class ViewportLoopTests(unittest.TestCase):
    def test_world_material_redraw_and_error_reporting(self):
        code = r'''
            from PySide6 import QtCore as C, QtWidgets as W
            from types import SimpleNamespace
            import arika_scene_editor as editor

            class Renderer:
                def __init__(self, canvas):
                    self.draws = 0
                    self.uploads = 0
                    self.m_instances = [dict(index=0, collision=False)]
                    self.m_center = [1, 2, 3]
                    self.m_distance = 123
                    self.fail = False
                def set_project(self, project, geometry, fit):
                    self.uploads += 1
                def render(self, *args, **kwargs):
                    self.draws += 1
                    if self.fail:
                        raise RuntimeError('test adapter failure')

            editor.c_webgpu_renderer = Renderer
            app = W.QApplication([])
            window = editor.c_scene_editor()
            window.show()
            project = SimpleNamespace(m_document={})
            window.m_view.set_project(project, fit=True)
            failures = []
            def check():
                try:
                    view = window.m_view
                    assert view.m_renderer is not None, 'World callback never ran'
                    assert view.m_renderer.draws > 0
                    assert view.m_renderer.uploads == 1
                    assert view.m_center == [1, 2, 3] and view.m_distance == 123
                    assert 'WebGPU ready' in window.statusBar().currentMessage()
                    first = view.m_renderer.draws
                    view.request_draw()
                    def redraw_check():
                        try:
                            assert view.m_renderer.draws > first, 'Camera redraw stalled'
                            window.m_views.setCurrentIndex(1)
                            window.m_material_view.set_project(project, fit=True)
                        except Exception as error:
                            failures.append(str(error))
                        C.QTimer.singleShot(200, material_check)
                    C.QTimer.singleShot(200, redraw_check)
                except Exception as error:
                    failures.append(str(error));app.quit()
            def material_check():
                try:
                    view = window.m_material_view
                    assert view.m_renderer is not None, 'Material callback never ran'
                    assert view.m_renderer.draws > 0 and view.m_renderer.uploads == 1
                    view.m_renderer.fail = True
                    view.request_draw()
                    C.QTimer.singleShot(200, error_check)
                except Exception as error:
                    failures.append(str(error));app.quit()
            def error_check():
                try:
                    assert 'test adapter failure' in window.statusBar().currentMessage()
                    assert window.m_material_view.m_error == 'test adapter failure'
                except Exception as error:
                    failures.append(str(error))
                app.quit()
            C.QTimer.singleShot(250, check)
            C.QTimer.singleShot(3000, app.quit)
            app.exec()
            assert not failures, failures
            assert window.m_material_view.m_error == 'test adapter failure'
        '''
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', ARIKA_PRESENT_METHOD='bitmap')
        result = subprocess.run([sys.executable, '-c', textwrap.dedent(code)],
                                cwd=Path(__file__).parent, env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
