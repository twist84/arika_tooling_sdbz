"""Verify editor placement and workspace routing through Qt's event loop."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('PySide6','rendercanvas','wgpu')), 'Qt dependencies required')
class SceneLayoutTests(unittest.TestCase):
    def test_blender_layout_and_workspaces(self):
        code=r'''
            from PySide6 import QtCore as C,QtWidgets as W,QtTest as T,QtGui as G
            from unittest.mock import patch
            import arika_scene_editor as e
            from arika_scene_project import c_scene_project
            class Renderer:
                def __init__(self,*a):
                    self.m_instances=[];self.m_center=[0,0,0];self.m_distance=100
                def set_project(self,*a):pass
                def render(self,*a,**kw):pass
            e.c_webgpu_renderer=Renderer
            app=W.QApplication([]);w=e.c_scene_editor()
            w.m_project=c_scene_project.load('examples/stage_s00.arika-scene.json')
            w.populate(True);w.show();failures=[]
            def check():
                try:
                    assert w.dockWidgetArea(w.m_outliner_dock)==C.Qt.DockWidgetArea.RightDockWidgetArea
                    assert w.dockWidgetArea(w.m_properties_dock)==C.Qt.DockWidgetArea.RightDockWidgetArea
                    assert w.m_outliner_dock.y()<w.m_properties_dock.y()
                    assert w.m_view.width()>w.m_outliner_dock.width()*2
                    assert w.m_assets_dock.y()>w.centralWidget().y()
                    assert len(w.m_fields)==9
                    assert len(w.m_axis_lock_checks)==9
                    assert w.m_gizmo_buttons['move'].isChecked()
                    w.set_gizmo_mode('transform');assert w.m_view.m_gizmo_mode=='transform' and w.m_gizmo_buttons['transform'].isChecked()
                    w.set_gizmo_mode('rotate');assert w.m_view.m_gizmo_mode=='rotate' and w.m_object_view.m_gizmo_mode=='rotate'
                    assert w.m_gizmo_buttons['rotate'].isChecked() and not w.m_gizmo_buttons['move'].isChecked()
                    w.set_gizmo_mode('scale');assert w.m_gizmo_buttons['scale'].isChecked()
                    w.m_orientation_combo.setCurrentText('Global');assert w.m_view.m_transform_orientation=='global'
                    w.m_orientation_combo.setCurrentText('Local');assert w.m_view.m_transform_orientation=='local'
                    w.m_pivot_combo.setCurrentText('3D Cursor');assert w.m_view.m_pivot_mode=='cursor'
                    w.m_pivot_combo.setCurrentText('Median Point');assert w.m_view.m_pivot_mode=='median'
                    w.set_snap_step('move',.5);assert w.m_view.m_snap_steps['move']==.5
                    w.set_snap_step('move',1.0)
                    w.m_view.keyPressEvent(G.QKeyEvent(C.QEvent.Type.KeyPress,C.Qt.Key.Key_G,C.Qt.KeyboardModifier.NoModifier))
                    assert w.m_view.m_gizmo_mode=='move' and w.m_gizmo_buttons['move'].isChecked()
                    assert w.m_texture_browser.count()>0
                    w.m_workspaces.setCurrentIndex(1)
                    assert w.m_views.currentIndex()==1 and w.m_properties_tabs.currentIndex()==1
                    assert w.m_material_view.m_project is not None
                    w.m_workspaces.setCurrentIndex(2)
                    assert w.m_views.currentIndex()==2
                    assert w.m_texture_view.m_pixmap is not None
                    w.m_view_mode.setCurrentIndex(0)
                    assert w.m_workspaces.currentIndex()==0 and w.m_views.currentIndex()==0
                    w.select_view(next(iter(w.m_items)))
                    assert w.m_index is not None
                    editable=next(i for i,n in enumerate(w.m_project.m_document['nodes'])
                        if i in w.m_items and any(s['offset']==n.get('extras',{}).get('stg_offset') and 'translation' in s
                               for s in w.m_project.m_stage.m_scene['nodes']))
                    w.select_view(editable)
                    selected=set(w.m_view.m_selection)
                    w.m_workspaces.setCurrentIndex(3)
                    assert w.active_view() is w.m_object_view
                    assert w.m_object_view.m_isolated==selected
                    assert w.m_object_view.m_project is w.m_project
                    w.mode('Wireframe');assert w.m_object_view.m_mode=='Wireframe'
                    assert w.m_view.m_mode=='Textured', 'Object shading changed world shading'
                    w.viewport_option('grid',False);assert not w.m_object_view.m_options['grid']
                    assert w.m_view.m_options['grid']
                    w.projection(True);assert w.m_object_view.m_orthographic
                    w.align_view(0,90);assert w.m_object_view.m_pitch==90
                    background=w.m_object_view.m_options['background']
                    with patch.object(W.QColorDialog,'getColor',return_value=G.QColor()):
                        w.background_color()
                    assert w.m_object_view.m_options['background']==background, 'Cancel changed background'
                    with patch.object(W.QColorDialog,'getColor',return_value=G.QColor('#336699')):
                        w.background_color()
                    assert w.m_object_view.m_options['background']==G.QColor('#336699').getRgbF()
                    assert w.m_view.m_options['background']!=w.m_object_view.m_options['background']
                    with patch.object(W.QColorDialog,'getColor',return_value=G.QColor('#ff8000')):
                        w.choose_color()
                    assert w.m_color==list(G.QColor('#ff8000').getRgbF())
                    w.m_view_mode.setCurrentIndex(0);assert w.m_views.currentIndex()==0
                    w.m_view.toggle_local_view();assert w.m_view.m_isolated==selected
                    w.m_view.toggle_local_view();assert w.m_view.m_isolated is None
                    assert all(f.isEnabled() for f in w.m_fields)
                    for f in w.m_fields:
                        assert f.lineEdit().width()>80, 'Transform text area collapsed'
                        assert f.lineEdit().height()>10
                        assert f.lineEdit().text()==f.text()
                    assert all(f.isReadOnly() for f in w.m_fields), 'Objects must start locked'
                    assert not w.m_apply_transform.isEnabled()
                    w.change_node_state(locked=False)
                    field=w.m_fields[0];field.setFocus();field.selectAll()
                    T.QTest.keyClicks(field,'123.5');field.interpretText()
                    assert field.value()==123.5, 'Transform field cannot be edited'
                    count=len(w.m_project.m_document['nodes'])
                    w.add_example_character()
                    assert len(w.m_project.m_document['nodes'])>count
                    assert w.m_views.currentIndex()==3
                    actor=w.m_index
                    assert w.m_project.m_document['nodes'][actor]['name']=='Goku'
                    assert all(f.isReadOnly() for f in w.m_fields)
                    w.change_node_state(locked=False)
                    w.m_fields[0].setValue(42);w.apply_transform()
                    assert w.m_project.m_document['nodes'][actor]['translation'][0]==42
                    assert w.m_object_view.m_isolated=={actor}
                    count=len(w.m_project.m_document['nodes'])
                    w.m_fields[0].setFocus();T.QTest.keyClick(w.m_fields[0],C.Qt.Key.Key_Delete)
                    assert len(w.m_project.m_document['nodes'])==count, 'Typing Delete removed objects'
                    w.change_node_state(locked=True)
                    w.m_object_view.setFocus();T.QTest.keyClick(w.m_object_view,C.Qt.Key.Key_Delete)
                    assert len(w.m_project.m_document['nodes'])==count, 'Locked character was deleted'
                    w.change_node_state(locked=False)
                    T.QTest.keyClick(w.m_object_view,C.Qt.Key.Key_Delete,C.Qt.KeyboardModifier.KeypadModifier)
                    assert len(w.m_project.m_document['nodes'])==count, 'Numpad frame-selected deleted objects'
                    T.QTest.keyClick(w.m_object_view,C.Qt.Key.Key_Delete)
                    assert len(w.m_project.m_document['nodes'])<count
                    assert not w.m_view.m_selection and w.m_index is None
                    w.history(False);assert len(w.m_project.m_document['nodes'])==count
                    w.history(True);assert len(w.m_project.m_document['nodes'])<count
                    w.m_assets_dock.hide();assert w.m_assets_dock.isHidden()
                    w.reset_layout();assert not w.m_assets_dock.isHidden()
                    labels=[a.text() for a in w.menuBar().actions()]
                    assert labels==['File','Edit','Window','Help']
                    w.resize(1000,700)
                except Exception as error:
                    import traceback
                    failures.append(traceback.format_exc())
                C.QTimer.singleShot(150,finish)
            def finish():
                try:
                    assert w.m_properties_dock.width()>=300
                    assert w.m_view.width()>=400
                    assert all(f.lineEdit().width()>80 for f in w.m_fields)
                except Exception as error:
                    import traceback
                    failures.append(traceback.format_exc())
                app.quit()
            C.QTimer.singleShot(200,check);C.QTimer.singleShot(3000,app.quit)
            app.exec();assert not failures,failures
        '''
        result=subprocess.run([sys.executable,'-c',textwrap.dedent(code)],cwd=Path(__file__).parent,
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',ARIKA_PRESENT_METHOD='bitmap'),
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
