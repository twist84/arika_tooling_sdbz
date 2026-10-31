import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('PySide6','rendercanvas','wgpu')), 'Qt dependencies required')
class MultiSelectionTests(unittest.TestCase):
    def test_viewport_tree_toggle_clear_and_group_frame(self):
        code=r'''
            from PySide6 import QtCore as C,QtGui as G,QtWidgets as W,QtTest as T
            import numpy as np
            import arika_scene_editor as e
            from arika_scene_project import c_scene_project
            class Renderer:
                def __init__(self,*a):
                    self.m_instances=[];self.m_center=[0,0,0];self.m_distance=100;self.m_bounds={0:([-1,-1,-1],[1,1,1])}
                def set_project(self,*a):pass
                def render(self,*a,**kw):pass
            e.c_webgpu_renderer=Renderer
            app=W.QApplication([]);w=e.c_scene_editor()
            w.m_project=c_scene_project.load('examples/stage_s00.arika-scene.json');w.populate(True);w.show()
            failures=[]
            def check():
                try:
                    ids=[i for i,n in enumerate(w.m_project.m_document['nodes']) if i in w.m_items and 'mesh' in n]
                    a,b=ids[:2];view=w.m_view
                    instances=[]
                    for index,x in ((a,0),(b,100)):
                        matrix=np.eye(4);matrix[0,3]=x
                        instances.append(dict(index=index,mesh=0,matrix=matrix,collision=False))
                    view.m_renderer.m_instances=instances
                    def click(index,mods=C.Qt.KeyboardModifier.NoModifier):
                        view.m_renderer.pick=lambda *args:index
                        point=C.QPointF(10,10)
                        press=G.QMouseEvent(C.QEvent.Type.MouseButtonPress,point,point,C.Qt.MouseButton.LeftButton,C.Qt.MouseButton.LeftButton,mods)
                        release=G.QMouseEvent(C.QEvent.Type.MouseButtonRelease,point,point,C.Qt.MouseButton.LeftButton,C.Qt.MouseButton.NoButton,mods)
                        view.mousePressEvent(press);view.mouseReleaseEvent(release)
                    click(a);assert view.m_selection=={a}
                    click(b,C.Qt.KeyboardModifier.ShiftModifier)
                    assert view.m_selection=={a,b} and w.m_index==b
                    assert len(w.m_tree.selectedItems())==2 and '2 selected' in w.m_label.text()
                    view.frame(True);assert abs(view.m_center[0]-50)<1e-5
                    click(a,C.Qt.KeyboardModifier.ShiftModifier);assert view.m_selection=={b}
                    click(-1,C.Qt.KeyboardModifier.ShiftModifier);assert view.m_selection=={b}
                    click(-1);assert not view.m_selection and w.m_index is None
                    assert not any(f.isEnabled() for f in w.m_fields)
                    # Outliner selection updates the viewport, including active-object fallback.
                    w.select_view(a);w.m_items[b].setSelected(True)
                    assert view.m_selection=={a,b}
                    w.m_items[a].setSelected(False)
                    assert view.m_selection=={b} and w.m_index==b
                    view.keyPressEvent(G.QKeyEvent(C.QEvent.Type.KeyPress,C.Qt.Key.Key_A,C.Qt.KeyboardModifier.NoModifier))
                    assert len(view.m_selection)==len(w.m_items)
                    view.keyPressEvent(G.QKeyEvent(C.QEvent.Type.KeyPress,C.Qt.Key.Key_A,C.Qt.KeyboardModifier.AltModifier))
                    assert not view.m_selection
                    w.select_view(a);w.select_view(b,True);w.populate(False)
                    assert view.m_selection=={a,b}, 'Selection lost on project refresh'
                    view.keyPressEvent(G.QKeyEvent(C.QEvent.Type.KeyPress,C.Qt.Key.Key_Escape,C.Qt.KeyboardModifier.NoModifier))
                    assert not view.m_selection
                    # Native Ctrl-click in the Outliner uses ExtendedSelection.
                    for index in (a,b):
                        ancestor=w.m_items[index].parent()
                        while ancestor:ancestor.setExpanded(True);ancestor=ancestor.parent()
                    w.m_tree.scrollToItem(w.m_items[a]);app.processEvents()
                    T.QTest.mouseClick(w.m_tree.viewport(),C.Qt.MouseButton.LeftButton,C.Qt.KeyboardModifier.NoModifier,w.m_tree.visualItemRect(w.m_items[a]).center())
                    w.m_tree.scrollToItem(w.m_items[b]);app.processEvents()
                    T.QTest.mouseClick(w.m_tree.viewport(),C.Qt.MouseButton.LeftButton,C.Qt.KeyboardModifier.ControlModifier,w.m_tree.visualItemRect(w.m_items[b]).center())
                    assert view.m_selection=={a,b}
                    from arika_scene_state import node_state,hidden_nodes
                    assert node_state(w.m_project.m_document,a)['locked']
                    w.select_view(a)
                    assert all(f.isReadOnly() for f in w.m_fields)
                    before=w.m_project.m_stage.m_data
                    w.m_fields[0].setValue(999);w.apply_transform()
                    assert w.m_project.m_stage.m_data==before, 'Locked transform was applied'
                    w.change_node_state(locked=False)
                    assert not any(f.isReadOnly() for f in w.m_fields)
                    w.m_items[a].setCheckState(2,C.Qt.CheckState.Checked)
                    assert all(f.isReadOnly() for f in w.m_fields)
                    w.m_items[a].setCheckState(1,C.Qt.CheckState.Unchecked)
                    assert a in hidden_nodes(w.m_project.m_document)
                    view.frame(False);assert abs(view.m_center[0]-100)<1e-5
                    click(a);assert not view.m_selection, 'Hidden object was picked from stale ID buffer'
                    w.show_all_objects();assert not hidden_nodes(w.m_project.m_document)
                    click(a);assert view.m_selection=={a}
                    view.toggle_local_view();assert view.m_isolated=={a}
                    view.frame(False);assert abs(view.m_center[0])<1e-5
                    click(b);assert not view.m_selection, 'Object outside Local View was picked'
                    view.toggle_local_view();assert view.m_isolated is None
                except Exception as error:failures.append(repr(error))
                app.quit()
            C.QTimer.singleShot(200,check);C.QTimer.singleShot(3000,app.quit)
            app.exec();assert not failures,failures
        '''
        result=subprocess.run([sys.executable,'-c',textwrap.dedent(code)],cwd=Path(__file__).parent,
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',ARIKA_PRESENT_METHOD='bitmap'),
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
