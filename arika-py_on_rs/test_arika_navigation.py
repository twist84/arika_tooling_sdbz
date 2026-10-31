"""Qt input routing and camera behavior; no adapter required."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


@unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('PySide6','rendercanvas','wgpu')), 'Qt dependencies required')
class NavigationTests(unittest.TestCase):
    def test_blender_navigation(self):
        code=r'''
            from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
            from types import SimpleNamespace
            import numpy as np
            from arika_scene_editor import c_viewport
            app=W.QApplication([])
            v=c_viewport();v.resize(800,600)
            left=C.Qt.MouseButton.LeftButton;middle=C.Qt.MouseButton.MiddleButton
            none=C.Qt.KeyboardModifier.NoModifier
            shift=C.Qt.KeyboardModifier.ShiftModifier
            ctrl=C.Qt.KeyboardModifier.ControlModifier
            alt=C.Qt.KeyboardModifier.AltModifier
            def mouse(kind,point,button,buttons,mods=none):
                event=G.QMouseEvent(kind,C.QPointF(*point),C.QPointF(*point),button,buttons,mods)
                {C.QEvent.Type.MouseButtonPress:v.mousePressEvent,C.QEvent.Type.MouseMove:v.mouseMoveEvent,C.QEvent.Type.MouseButtonRelease:v.mouseReleaseEvent}[kind](event)
            def drag(button,mods=none):
                mouse(C.QEvent.Type.MouseButtonPress,(100,100),button,button,mods)
                mouse(C.QEvent.Type.MouseMove,(140,120),C.Qt.MouseButton.NoButton,button,mods)
                mouse(C.QEvent.Type.MouseButtonRelease,(140,120),button,C.Qt.MouseButton.NoButton,mods)
            start=(v.m_yaw,v.m_pitch)
            drag(left);assert (v.m_yaw,v.m_pitch)==start
            drag(middle);assert (v.m_yaw,v.m_pitch)!=start
            angle=(v.m_yaw,v.m_pitch);center=list(v.m_center)
            drag(middle,shift);assert v.m_center!=center and (v.m_yaw,v.m_pitch)==angle
            distance=v.m_distance;drag(middle,ctrl);assert v.m_distance>distance
            angle=(v.m_yaw,v.m_pitch);drag(left,alt);assert (v.m_yaw,v.m_pitch)!=angle
            def key(k,mods=none):
                v.keyPressEvent(G.QKeyEvent(C.QEvent.Type.KeyPress,k,mods))
            pad=C.Qt.KeyboardModifier.KeypadModifier
            key(C.Qt.Key.Key_7,pad);assert v.m_pitch==90 and v.m_orthographic
            center=list(v.m_center);v.pan(0,50)
            assert abs(v.m_center[2]-center[2])>1 and abs(v.m_center[1]-center[1])<1e-5
            key(C.Qt.Key.Key_5,pad);assert not v.m_orthographic
            key(C.Qt.Key.Key_1,pad|ctrl);assert v.m_yaw==180 and v.m_orthographic
            key(C.Qt.Key.Key_3,pad);assert v.m_yaw==90
            key(C.Qt.Key.Key_6,pad);assert v.m_yaw==105 and not v.m_orthographic
            angle=v.m_yaw;key(C.Qt.Key.Key_1);assert v.m_yaw==angle
            v.m_project=SimpleNamespace(m_document={'nodes':[{'children':[1]},{'mesh':0}]})
            v.m_renderer=SimpleNamespace(m_instances=[dict(index=1,mesh=0,matrix=np.eye(4),collision=False)],m_bounds={0:([-1,-2,-3],[1,2,3])})
            v.m_selected=0;key(C.Qt.Key.Key_Period,pad)
            assert v.m_center==[0,0,0] and v.m_distance>3
            v.m_selection={0};key(C.Qt.Key.Key_Slash,pad);assert v.m_isolated=={0}
            key(C.Qt.Key.Key_Slash,pad);assert v.m_isolated is None
            v.m_center=[99,99,99];key(C.Qt.Key.Key_Home);assert v.m_center==[0,0,0]
            # Origin clicks must select too; Alt navigation must not select.
            v.m_renderer.pick=lambda x,y:1
            selected=[];v.selected.connect(selected.append)
            mouse(C.QEvent.Type.MouseButtonPress,(0,0),left,left)
            mouse(C.QEvent.Type.MouseButtonRelease,(0,0),left,C.Qt.MouseButton.NoButton)
            assert selected==[1]
            drag(left,alt);assert selected==[1]
        '''
        result=subprocess.run([sys.executable,'-c',textwrap.dedent(code)],cwd=Path(__file__).parent,
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',ARIKA_PRESENT_METHOD='bitmap'),
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
