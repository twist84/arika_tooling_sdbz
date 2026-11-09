#!/usr/bin/env python3
"""Arika Editor: general-purpose editor for Arika files with an in-memory archive browser."""
import base64
import copy
import io
import json
import math
import os
import shutil
import tempfile
import hashlib
from pathlib import Path, PurePosixPath
import sys
from PIL import Image
from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
from rendercanvas.qt import QRenderWidget
import arika_backend as backend
import arika_dat as dat
import arika_ffon
import arika_pix
import arika_ani
import arika_pas
import arika_ebz
import arika_cht
import arika_stages
import arika_scripts as arika_spt
from arika_webgpu import c_webgpu_renderer,DEFAULT_BACKGROUND,camera_matrix
from arika_gizmo import (gizmo_geometry,rotate_euler_local_axis,
    quaternion_from_axis_angle,quaternion_from_matrix,quaternion_inverse,
    quaternion_multiply,quaternion_to_euler)
from arika_scene_project import c_scene_project,material_preview_document
from arika_editor_settings import c_editor_settings
from arika_import import c_gltf_reader
from arika_models import identity,local_matrix,multiply,parse_model,build_gltf
from arika_scene_state import node_state,hidden_nodes,selection_nodes,transform_locks

NAVIGATION_HELP='MMB orbit · Shift+MMB pan · Ctrl+MMB zoom · Wheel zoom · Home frame all · Numpad . frame selected · Numpad 1/3/7 views · Numpad 5 perspective/ortho'

SHOW_ROLE=C.Qt.ItemDataRole.UserRole+1   # outliner Show column checked state
LOCK_ROLE=C.Qt.ItemDataRole.UserRole+2   # outliner Lock column checked state

EDITOR_STYLE='''
QWidget { background:#303030; color:#dedede; font-size:12px; }
QMainWindow { background:#202020; }
QMenuBar,QMenu,QToolBar { background:#252525; border:0; }
QMenuBar::item { padding:5px 10px; }
QMenuBar::item:selected,QMenu::item:selected { background:#4779a6; }
QToolBar { spacing:5px; padding:3px; }
QToolButton { border:0; border-radius:3px; padding:5px 8px; }
QToolButton:hover,QPushButton:hover { background:#505050; }
QToolButton:checked { background:#4779a6; }
QLineEdit,QDoubleSpinBox,QComboBox { background:#242424; border:1px solid #404040; border-radius:3px; padding:4px; }
QTreeWidget,QListWidget { background:#282828; border:0; outline:0; }
QTreeWidget::item,QListWidget::item { padding:3px; }
QTreeWidget::item:selected,QListWidget::item:selected { background:#4779a6; color:white; }
QHeaderView::section { background:#353535; border:0; padding:5px; text-align:left; }
QPushButton { padding:6px; background:#454545; border:1px solid #535353; border-radius:3px; }
QDockWidget { border:1px solid #202020; }
QDockWidget::title { background:#252525; padding:5px 8px; }
QMainWindow::separator { background:#202020; width:5px; height:5px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#252525; padding:7px 13px; border:0; }
QTabBar::tab:selected { background:#404040; border-top:2px solid #79a8d0; }
QScrollArea { border:0; }
QStatusBar { background:#202020; font-size:11px; }
QLabel#editor_heading { color:#aaaaaa; padding:4px; }
QTextEdit { background:#282828; border:0; }
'''


class VirtualFileSystem(dict):
    """In-memory name -> bytes mapping used to resolve sibling assets without disk."""
    def __init__(self,files=None):
        super().__init__(files or {})


class VirtualArchive:
    """Wraps an arika_dat.Archive and reads entries into memory."""
    def __init__(self,archive):
        self.archive=archive
        self.files={}
        self.entries=[]
    def load(self):
        self.entries=list(self.archive.entries)
        game=None
        try:
            if getattr(self.archive,'game',None) is not None:
                game=self.archive.game.open('rb')
            for entry in self.entries:
                data=None
                if game is not None and getattr(entry,'offset',None) is not None and entry.offset>=0 and getattr(entry,'size',0)>=0:
                    try:
                        game.seek(entry.offset)
                        data=game.read(entry.size)
                    except Exception:
                        data=None
                if data is None or len(data)<getattr(entry,'size',0):
                    data=self._read_via_extraction(entry)
                self.files[getattr(entry,'name','')]=data
        finally:
            if game is not None:
                game.close()
    def _read_via_extraction(self,entry):
        tmpdir=tempfile.mkdtemp()
        try:
            try:
                self.archive.extract(tmpdir,overwrite=True)
            except Exception:
                pass
            name=getattr(entry,'name','')
            target=Path(tmpdir)/name
            if target.is_file():
                return target.read_bytes()
            # try to find by basename
            for p in Path(tmpdir).rglob(Path(name).name):
                return p.read_bytes()
        finally:
            shutil.rmtree(tmpdir,ignore_errors=True)
        return b''


def detect_format(data, name):
    if data is None:
        data=b''
    if isinstance(name,Path):
        name=str(name)
    lower=(name or '').lower()
    magic=data[:16]
    if lower.endswith('.arika-scene.json'):
        try:
            doc=json.loads(data)
            if isinstance(doc,dict) and doc.get('format')=='ARIKA_SCENE_PROJECT':
                return 'project'
        except Exception:
            pass
        return 'text'
    if magic[:8]==b'\x00\x01\x00\x00STG ':
        return 'stage'
    if magic[:4]==b'FMDL':
        return 'model'
    if magic[:4]==b'FPIX':
        return 'texture'
    if magic[:4]==b'FFON':
        return 'font'
    if data[4:8]==b'CHT ':
        return 'facial'
    if lower.endswith('.cht'):
        return 'facial'
    if magic[:8]==b'\0\0\x02\0HIT ':
        return 'hit'
    if magic[:4]==b'MOT2':
        return 'motion'
    if magic[:6]==b'RFSML3':
        return 'motion'
    if magic[:4]==b'RIFF' and len(data)>=12 and data[8:12]==b'WAVE':
        return 'audio'
    if lower.endswith('.wav'):
        return 'audio'
    if lower.endswith(('.ase','.ams')):
        return 'audio'
    if magic[:8]==b'\x89PNG\r\n\x1a\n':
        return 'image'
    if magic[:2]==b'BM':
        return 'image'
    if magic[:3]==b'\xff\xd8\xff':
        return 'image'
    if lower.endswith(('.gltf',)):
        if data[:4]==b'glTF':
            return 'gltf'
        return 'gltf'
    if lower.endswith('.glb'):
        return 'gltf'
    if lower.endswith('.mdl'):
        return 'model'
    if lower.endswith('.ebz'):
        return 'effect'
    if lower.endswith('.ani'):
        return 'animation'
    if lower.endswith('.pas'):
        return 'pose'
    if lower.endswith('.spt'):
        return 'script'
    if (name or '').upper() in ('INFO.DAT','GAME.DAT'):
        return 'archive'
    if len(magic) >= 7 and magic[1:7] == b'www.ar':
        return 'archive'
    try:
        data.decode('utf-8')
        return 'text'
    except UnicodeDecodeError:
        return 'unknown'


class c_navigation_gizmo(W.QWidget):
    """Clickable 3D axis compass, with drag-to-orbit navigation."""
    def __init__(self,viewport):
        super().__init__(viewport);self.m_viewport=viewport;self.m_drag_last=None;self.m_points=[]
        self.setFixedSize(116,116);self.setMouseTracking(True);self.setToolTip('Click an axis endpoint to align the view; drag empty space to orbit.')
        self.setAttribute(C.Qt.WidgetAttribute.WA_TranslucentBackground,True);self.raise_()

    def paintEvent(self,event):
        painter=G.QPainter(self)
        try:
            painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
            painter.setPen(G.QPen(G.QColor(80,88,100,230),1));painter.setBrush(G.QColor(25,29,35,220));painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),10,10)
            center=C.QPointF(self.width()*.5,self.height()*.5+4);radius=37.0
            painter.setPen(G.QPen(G.QColor(80,86,95,180),1, C.Qt.PenStyle.DashLine));painter.setBrush(C.Qt.BrushStyle.NoBrush);painter.drawEllipse(center,radius,radius)
            view_axes=self.m_viewport.camera_axes();right=view_axes[0];up=view_axes[1]
            world_axes=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.));colors=(G.QColor('#ed5148'),G.QColor('#59c86b'),G.QColor('#568cff'))
            self.m_points=[]
            for axis_index,axis in enumerate(world_axes):
                sx=sum(axis[i]*right[i] for i in range(3));sy=-sum(axis[i]*up[i] for i in range(3));length=math.hypot(sx,sy)
                if length<.12:
                    sx,sy=((0.,-1.) if axis_index==1 else ((1.,0.) if axis_index==0 else (0.,1.)));length=1.0
                sx/=length;sy/=length;screen_length=radius*max(.18,min(1.0,length))
                for sign in (-1,1):
                    point=C.QPointF(center.x()+sx*screen_length*sign,center.y()+sy*screen_length*sign)
                    self.m_points.append((point,axis_index,sign))
                    painter.setPen(G.QPen(colors[axis_index].darker(155) if sign<0 else colors[axis_index],2))
                    painter.drawLine(center,point)
                    painter.setPen(G.QPen(G.QColor(20,22,26,240),1));painter.setBrush(colors[axis_index] if sign>0 else colors[axis_index].darker(145));painter.drawEllipse(point,7,7)
                    painter.setPen(G.QColor(255,255,255,245));font=painter.font();font.setBold(True);font.setPointSize(7);painter.setFont(font)
                    label=('%s%s'%('XYZ'[axis_index],'+' if sign>0 else '−'))
                    painter.drawText(C.QRectF(point.x()-12,point.y()-6,24,12),C.Qt.AlignmentFlag.AlignCenter,label)
        finally:
            if painter.isActive():
                painter.end()
    def align_axis(self,axis,sign):
        view=self.m_viewport
        if axis==0:view.m_yaw=-90 if sign>0 else 90;view.m_pitch=0
        elif axis==1:view.m_yaw=0;view.m_pitch=90 if sign>0 else -90
        else:view.m_yaw=0 if sign>0 else 180;view.m_pitch=0
        view.m_orthographic=True;view.m_axis_view=True;view.request_draw()

    def mousePressEvent(self,event):
        if event.button()!=C.Qt.MouseButton.LeftButton:return super().mousePressEvent(event)
        point=event.position();best=None;distance=14.0
        for endpoint,axis,sign in self.m_points:
            candidate=math.hypot(point.x()-endpoint.x(),point.y()-endpoint.y())
            if candidate<distance:best=(axis,sign);distance=candidate
        if best is not None:self.align_axis(*best);self.m_drag_last=None
        else:self.m_drag_last=(point.x(),point.y())
        event.accept()

    def mouseMoveEvent(self,event):
        if self.m_drag_last is not None and event.buttons()&C.Qt.MouseButton.LeftButton:
            point=event.position();dx=point.x()-self.m_drag_last[0];dy=point.y()-self.m_drag_last[1];self.m_drag_last=(point.x(),point.y())
            self.m_viewport.orbit(dx,dy);event.accept();return
        event.accept()

    def mouseReleaseEvent(self,event):
        self.m_drag_last=None;event.accept()

    def wheelEvent(self,event):
        self.m_viewport.zoom(-(event.angleDelta().y() or event.pixelDelta().y())/1200);event.accept()


class c_viewport(QRenderWidget):
    selected=C.Signal(int)
    selection_requested=C.Signal(int,bool)
    selection_all=C.Signal(bool)
    delete_requested=C.Signal()
    transform_changed=C.Signal()
    gizmo_mode_requested=C.Signal(str)
    def __init__(self,parent=None):
        import os
        super().__init__(parent,present_method=os.environ.get('ARIKA_PRESENT_METHOD','screen' if sys.platform=='win32' else 'bitmap'),update_mode='ondemand')
        self.m_project=None;self.m_renderer=None;self.m_upload=False;self.m_geometry=True;self.m_fit=False;self.m_world_cache=None
        self.m_center=[0,0,0];self.m_distance=1000.;self.m_yaw=35.;self.m_pitch=30.;self.m_selected=-1
        self.m_selection=set()
        self.m_isolated=None
        self.m_options=dict(grid=True,axes=True,highlight=True,cull=False,background=DEFAULT_BACKGROUND)
        self.m_mode='Textured';self.m_collision=False;self.m_last=None;self.m_press=None;self.m_error=''
        self.m_orthographic=False;self.m_axis_view=False;self.m_dragged=False
        self.m_navigation_start=None;self.m_gizmo_mode='move';self.m_show_gizmo=True;self.m_gizmo_drag=None;self.m_gizmo_hover=None
        self.m_transform_orientation='local';self.m_pivot_mode='median';self.m_cursor_location=[0.0,0.0,0.0];self.m_cursor_axes=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]];self.m_custom_orientation_axes=None
        self.m_snap_steps={'move':1.0,'rotate':15.0,'scale':0.1}
        self.setToolTip(NAVIGATION_HELP+' · T combined transform / G move / R rotate / S scale · drag gizmo handles · X/Y/Z axis constraint · numeric entry · Shift precision · Ctrl snap · Esc/right-click cancel')
        self.setMouseTracking(True)
        self.setMinimumSize(0, 0)
        # rendercanvas skips callbacks until a context exists. Creating it in
        # draw_frame would leave both world and material views blank forever.
        self.get_wgpu_context()
        self.m_nav_gizmo=c_navigation_gizmo(self);self.m_nav_gizmo.move(max(4,self.width()-self.m_nav_gizmo.width()-12),12);self.m_nav_gizmo.show()
        self.request_draw(self.draw_frame)

    def request_draw(self,*args,**kwargs):
        result=super().request_draw(*args,**kwargs)
        nav=getattr(self,'m_nav_gizmo',None)
        if nav is not None:nav.update()
        return result

    def resizeEvent(self,event):
        super().resizeEvent(event)
        nav=getattr(self,'m_nav_gizmo',None)
        if nav is not None:nav.move(max(4,self.width()-nav.width()-12),12);nav.raise_()

    def set_project(self,project,fit=False,geometry=True):
        self.m_project=project;self.m_world_cache=None;self.m_upload=True;self.m_geometry=geometry;self.m_fit=fit or self.m_fit;self.request_draw()

    def draw_frame(self):
        if not self.isVisible():return
        try:
            if self.m_renderer is None:self.m_renderer=c_webgpu_renderer(self)
            if self.m_upload and self.m_project:
                self.m_renderer.set_project(self.m_project,self.m_geometry,self.m_fit)
                if self.m_fit:self.m_center=self.m_renderer.m_center;self.m_distance=self.m_renderer.m_distance
                if self.m_fit and self.m_isolated is not None:self.frame()
                self.m_upload=False;self.m_fit=False;self.m_geometry=False
                if hasattr(self.window(),'statusBar'):
                    count=len(self.m_renderer.m_instances)
                    self.window().statusBar().showMessage('WebGPU ready: %d mesh instances. MMB orbit | Shift+MMB pan | Wheel zoom'%count)
            width,height=self.get_physical_size()
            self.m_renderer.render(width,height,self.m_yaw,self.m_pitch,self.m_center,self.m_distance,self.m_mode,self.m_selection or self.m_selected,self.m_collision,orthographic=self.m_orthographic,isolated=self.m_isolated,options=self.m_options,gizmo=self.gizmo_state())
            self.m_error=''
        except Exception as error:
            self.m_error=str(error)
            if hasattr(self.window(),'statusBar'):self.window().statusBar().showMessage('WebGPU error: '+self.m_error)
            try:
                import traceback
                with open('C:/Dev/arika/.kilo/webgpu_traceback.txt','w') as f:
                    traceback.print_exc(file=f)
            except Exception:pass

    def showEvent(self,event):
        super().showEvent(event);self.request_draw()

    def zoom(self,amount):
        self.m_distance=max(.1,min(1e8,self.m_distance*math.exp(max(-20,min(20,amount)))))
        self.request_draw()

    def pan(self,dx,dy):
        # Use the full camera basis, including pitch, so top views pan correctly.
        y=math.radians(self.m_yaw);p=math.radians(self.m_pitch)
        right=[math.cos(y),0,math.sin(y)]
        up=[math.sin(p)*math.sin(y),math.cos(p),-math.sin(p)*math.cos(y)]
        amount=2*self.m_distance*math.tan(math.radians(22.5))/max(1,self.height())
        self.m_center=[v+amount*(-dx*r+dy*u) for v,r,u in zip(self.m_center,right,up)]
        self.request_draw()

    def orbit(self,dx,dy):
        self.m_yaw=(self.m_yaw+dx*.4)%360
        self.m_pitch=max(-90,min(90,self.m_pitch+dy*.4))
        if self.m_axis_view:self.m_orthographic=False;self.m_axis_view=False
        self.request_draw()

    def frame(self,selected=False):
        if not self.m_project or not self.m_renderer:return
        import numpy as np
        nodes=self.m_project.m_document.get('nodes',[])
        allowed=set()
        def collect(index):
            if index in allowed:return
            allowed.add(index)
            for child in nodes[index].get('children',[]):collect(child)
        if selected:
            for index in self.m_selection or {self.m_selected}:
                if 0<=index<len(nodes):collect(index)
            if not allowed:return
        points=[]
        hidden=getattr(self.m_renderer,'m_hidden',None)
        if hidden is None:hidden=hidden_nodes(self.m_project.m_document)
        scope=None
        if self.m_isolated is not None:
            if self.m_renderer is not None and hasattr(self.m_renderer,'selection_nodes_cached'):
                scope=self.m_renderer.selection_nodes_cached(self.m_isolated)
            else:
                scope=selection_nodes(self.m_project.m_document,self.m_isolated)
        for instance in self.m_renderer.m_instances:
            if instance['mesh'] not in self.m_renderer.m_bounds:continue
            if instance['index'] in hidden:continue
            if scope is not None and instance['index'] not in scope:continue
            if instance['collision'] or (selected and instance['index'] not in allowed):continue
            lo,hi=self.m_renderer.m_bounds[instance['mesh']]
            for x in (lo[0],hi[0]):
                for y in (lo[1],hi[1]):
                    for z in (lo[2],hi[2]):points.append((np.asarray(instance['matrix'])@np.array([x,y,z,1]))[:3])
        if points:
            lo=np.min(points,axis=0);hi=np.max(points,axis=0)
            self.m_center=((lo+hi)/2).tolist()
            aspect=max(.01,self.width()/max(1,self.height()))
            self.m_distance=max(1,float(np.linalg.norm(hi-lo))*.5/math.sin(math.atan(math.tan(math.radians(22.5))*min(1,aspect)))*1.1)
            self.request_draw()

    def world_transforms(self):
        import numpy as np
        if not self.m_project:return {},{}
        if self.m_world_cache is not None:return self.m_world_cache
        nodes=self.m_project.m_document.get('nodes',[]);parents={}
        for parent,node in enumerate(nodes):
            for child in node.get('children',[]):parents[child]=parent
        worlds={}
        def resolve(index):
            if index in worlds:return worlds[index]
            node=nodes[index]
            local=local_matrix(dict(translation=node.get('translation',[0,0,0]),rotation=node.get('rotation',[0,0,0,1]),scale=node.get('scale',[1,1,1])))
            parent=parents.get(index)
            matrix=np.asarray(multiply(resolve(parent),local) if parent is not None else local,dtype=float)
            worlds[index]=matrix
            return matrix
        for index in range(len(nodes)):resolve(index)
        self.m_world_cache=(worlds,parents)
        return self.m_world_cache

    @staticmethod
    def orthogonal_axes(matrix):
        import numpy as np
        x=np.asarray(matrix[:3,0],dtype=float);nx=float(np.linalg.norm(x))
        x=x/max(nx,1e-12) if nx>1e-8 else np.asarray([1.,0.,0.])
        y=np.asarray(matrix[:3,1],dtype=float);y-=x*float(np.dot(x,y));ny=float(np.linalg.norm(y))
        if ny<=1e-8:
            fallback=np.asarray([0.,1.,0.]) if abs(float(x[1]))<.9 else np.asarray([0.,0.,1.])
            y=fallback-x*float(np.dot(x,fallback));ny=float(np.linalg.norm(y))
        y/=max(1e-12,ny);z=np.cross(x,y);z/=max(1e-12,float(np.linalg.norm(z)))
        if float(np.dot(z,matrix[:3,2]))<0:z=-z
        return [x,y,z]

    def camera_axes(self):
        y=math.radians(self.m_yaw);p=math.radians(self.m_pitch)
        cy,sy,cp,sp=math.cos(y),math.sin(y),math.cos(p),math.sin(p)
        return [[cy,0.0,sy],[sp*sy,cp,-sp*cy],[-cp*sy,sp,cp*cy]]

    def selection_roots(self):
        if not self.m_project:return []
        selected=set(self.m_selection or ({self.m_selected} if self.m_selected>=0 else set()))
        nodes=self.m_project.m_document.get('nodes',[]);_,parents=self.world_transforms()
        roots=[]
        for index in sorted(selected):
            if not 0<=index<len(nodes):continue
            parent=parents.get(index);nested=False
            while parent is not None:
                if parent in selected:nested=True;break
                parent=parents.get(parent)
            if not nested:roots.append(index)
        return roots

    def gizmo_state(self):
        import numpy as np
        if not self.m_show_gizmo or not self.m_project or self.m_selected<0 or not hasattr(self.m_project,'node_transform_values'):return None
        values=self.m_project.node_transform_values(self.m_selected)
        if values is None:return None
        try:
            from arika_scene_state import node_state
            enabled=not node_state(self.m_project.m_document,self.m_selected)['locked']
            worlds,parents=self.world_transforms();matrix=worlds[self.m_selected]
            local_axes=self.orthogonal_axes(matrix);view_axes=self.camera_axes()
            orientation=self.m_transform_orientation
            if orientation=='global':axes=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
            elif orientation=='view':axes=view_axes
            elif orientation=='cursor':axes=self.m_cursor_axes
            elif orientation=='custom':axes=self.m_custom_orientation_axes or local_axes
            elif orientation=='gimbal':
                parent=parents.get(self.m_selected);parent_matrix=worlds[parent] if parent is not None else np.eye(4)
                parent_axes=self.orthogonal_axes(parent_matrix);x,y,z=values[3:6]
                local_gimbal=[[1.,0.,0.],[0.,math.cos(x),math.sin(x)],[math.sin(y),-math.sin(x)*math.cos(y),math.cos(x)*math.cos(y)]]
                axes=[[sum(parent_axes[k][j]*local_gimbal[i][k] for k in range(3)) for j in range(3)] for i in range(3)]
            else:axes=local_axes
            selected=self.m_selection or {self.m_selected};positions=[worlds[i][:3,3] for i in selected if i in worlds]
            active_position=matrix[:3,3]
            if self.m_pivot_mode=='cursor':position=np.asarray(self.m_cursor_location,dtype=float)
            elif self.m_pivot_mode=='active' or self.m_pivot_mode=='individual' or not positions:position=active_position
            else:position=np.mean(np.asarray(positions,dtype=float),axis=0)
            return dict(mode=self.m_gizmo_mode,position=position.tolist(),axes=[np.asarray(a,dtype=float).tolist() for a in axes],
                view_axes=[np.asarray(a,dtype=float).tolist() for a in view_axes],size=max(.01,self.m_distance*.12),enabled=enabled,
                orientation=orientation,pivot=self.m_pivot_mode,hover_handle=self.m_gizmo_hover)
        except (IndexError,ValueError,ZeroDivisionError):
            return None

    def project_world(self,point):
        import numpy as np
        matrix=camera_matrix(self.m_center,self.m_distance,self.m_yaw,self.m_pitch,max(.01,self.width()/max(1,self.height())),self.m_orthographic)
        clip=matrix@np.asarray([point[0],point[1],point[2],1.0],dtype=float)
        if clip[3]<=1e-8:return None
        ndc=clip[:3]/clip[3]
        return ((float(ndc[0])+1)*.5*self.width(),(1-float(ndc[1]))*.5*self.height())

    def ray_plane_point(self,point,pivot,normal):
        import numpy as np
        camera=camera_matrix(self.m_center,self.m_distance,self.m_yaw,self.m_pitch,max(.01,self.width()/max(1,self.height())),self.m_orthographic)
        try:inverse=np.linalg.inv(camera)
        except np.linalg.LinAlgError:return None
        x=2.0*point.x()/max(1,self.width())-1.0;y=1.0-2.0*point.y()/max(1,self.height())
        near=inverse@np.asarray([x,y,0.,1.]);far=inverse@np.asarray([x,y,1.,1.])
        if abs(float(near[3]))<=1e-10 or abs(float(far[3]))<=1e-10:return None
        near=near[:3]/near[3];far=far[:3]/far[3];direction=far-near
        length=float(np.linalg.norm(direction))
        if length<=1e-10:return None
        direction/=length;normal=np.asarray(normal,dtype=float);denom=float(np.dot(direction,normal))
        if abs(denom)<=1e-8:return None
        return near+direction*(float(np.dot(np.asarray(pivot,dtype=float)-near,normal))/denom)

    def ray_plane_vector(self,point,pivot,normal):
        import numpy as np
        hit=self.ray_plane_point(point,pivot,normal)
        if hit is None:return None
        vector=hit-np.asarray(pivot,dtype=float);length=float(np.linalg.norm(vector))
        return vector/length if length>1e-8 else None

    @staticmethod
    def segment_distance(point,a,b):
        dx=b[0]-a[0];dy=b[1]-a[1];length=dx*dx+dy*dy
        if length<=1e-12:return math.hypot(point[0]-a[0],point[1]-a[1])
        t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length))
        return math.hypot(point[0]-(a[0]+t*dx),point[1]-(a[1]+t*dy))

    def hit_test_gizmo(self,point):
        state=self.gizmo_state()
        if state is None:return None
        best=None;best_distance=11.0
        geometry=gizmo_geometry(state['position'],state['axes'],state['size'],state['mode'],include_extra=True,view_axes=state['view_axes'])
        for handle,segments in geometry.items():
            for a,b in segments:
                screen_a=self.project_world(a);screen_b=self.project_world(b)
                if screen_a is None or screen_b is None:continue
                distance=self.segment_distance((point.x(),point.y()),screen_a,screen_b)
                if distance<best_distance:best_distance=distance;best=handle
        return best

    @staticmethod
    def plane_handle_axes(handle,axes,view_axes):
        if handle=='plane_xy':return axes[0],axes[1]
        if handle=='plane_xz':return axes[0],axes[2]
        if handle=='plane_yz':return axes[1],axes[2]
        if handle=='plane_view':return view_axes[0],view_axes[1]
        return None

    def begin_gizmo_drag(self,handle,point):
        import numpy as np
        state=self.gizmo_state()
        if state is None or not state['enabled'] or not self.m_project:return None
        display_handle=handle;mode=state['mode']
        if mode=='transform':
            if not isinstance(handle,str) or '_' not in handle:return None
            mode,handle=handle.split('_',1)
            if handle in ('x','y','z'):handle=('x','y','z').index(handle)
        roots=self.selection_roots()
        targets=[]
        for index in roots:
            from arika_scene_state import node_state
            if node_state(self.m_project.m_document,index)['locked']:continue
            if self.m_project.node_transform_values(index) is not None:targets.append(index)
        if not targets:return None
        values={i:list(self.m_project.node_transform_values(i)) for i in targets}
        worlds,parents=self.world_transforms();parent_inverses={};parent_quaternions={};world_quaternions={}
        for index in targets:
            parent=parents.get(index);parent_matrix=worlds[parent] if parent is not None else np.eye(4)
            try:parent_inverses[index]=np.linalg.inv(parent_matrix)
            except np.linalg.LinAlgError:parent_inverses[index]=np.eye(4)
            parent_axes=self.orthogonal_axes(parent_matrix)
            parent_quaternions[index]=quaternion_from_matrix(np.column_stack(parent_axes))
            world_quaternions[index]=quaternion_from_matrix(np.column_stack(self.orthogonal_axes(worlds[index])))
        pivot=np.asarray(state['position'],dtype=float);axes=[np.asarray(a,dtype=float) for a in state['axes']]
        view_axes=[np.asarray(a,dtype=float) for a in state['view_axes']]
        basis=self.plane_handle_axes(handle,axes,view_axes)
        axis_world=None;plane_normal=None;start_vector=None;start_plane_point=None
        if isinstance(handle,int):axis_world=axes[handle]
        elif handle=='view':axis_world=view_axes[2]
        elif handle=='trackball':axis_world=view_axes[2]
        if handle in ('plane_xy','plane_xz','plane_yz','plane_view'):
            plane_normal=np.cross(basis[0],basis[1]);plane_normal/=max(1e-12,float(np.linalg.norm(plane_normal)))
            start_plane_point=self.ray_plane_point(point,pivot,plane_normal)
        if mode=='rotate' and handle!='trackball':
            if axis_world is None:return None
            start_vector=self.ray_plane_vector(point,pivot,axis_world)
            if start_vector is None:return None
        pivot_screen=self.project_world(pivot)
        if pivot_screen is None:return None
        screen_axes=[]
        for axis in (basis if basis else ([axis_world] if axis_world is not None else [])):
            endpoint=self.project_world(pivot+axis*state['size'])
            screen_axes.append((endpoint[0]-pivot_screen[0],endpoint[1]-pivot_screen[1]) if endpoint else (0.,0.))
        return dict(handle=handle,display_handle=display_handle,axis=handle if isinstance(handle,int) else None,mode=mode,start=(point.x(),point.y()),
            last_point=(point.x(),point.y()),start_values=values,targets=targets,pivot=pivot.tolist(),axes=[a.tolist() for a in axes],
            view_axes=[a.tolist() for a in view_axes],orientation=state['orientation'],pivot_mode=state['pivot'],size=state['size'],
            axis_world=axis_world.tolist() if axis_world is not None else None,basis=[a.tolist() for a in basis] if basis else None,
            plane_normal=plane_normal.tolist() if plane_normal is not None else None,start_vector=start_vector,
            start_plane_point=start_plane_point.tolist() if start_plane_point is not None else None,screen_axes=screen_axes,
            parent_inverses=parent_inverses,parent_quaternions=parent_quaternions,world_quaternions=world_quaternions,
            start_worlds={i:np.asarray(worlds[i],dtype=float).copy() for i in targets},checkpointed=False,
            snapshot=self.m_project.snapshot(),was_changed=self.m_project.m_changed,numeric_buffer='',axis_lock=None)

    @staticmethod
    def solve_screen_basis(dx,dy,screen_axes):
        if len(screen_axes)==1:
            sx,sy=screen_axes[0];denom=sx*sx+sy*sy
            if denom<=1e-8:return [0.0]
            return [(dx*sx+dy*sy)/denom]
        if len(screen_axes)<2:return []
        (sx1,sy1),(sx2,sy2)=screen_axes[:2];det=sx1*sy2-sx2*sy1
        if abs(det)<=1e-8:
            denom=sx1*sx1+sy1*sy1
            return [(dx*sx1+dy*sy1)/denom,0.0] if denom>1e-8 else [0.0,0.0]
        return [(dx*sy2-dy*sx2)/det,(dy*sx1-dx*sy1)/det]

    @staticmethod
    def rotate_vector(vector,quaternion):
        import numpy as np
        q=np.asarray(quaternion,dtype=float);v=np.asarray(vector,dtype=float);xyz=q[:3]
        return v+2.0*np.cross(xyz,np.cross(xyz,v)+q[3]*v)

    def apply_gizmo_operation(self,drag,world_delta=None,angle=0.0,axis_world=None,scale_factors=None):
        import numpy as np
        from arika_scene_state import transform_locks
        if not drag or not self.m_project:return
        mode=drag['mode'];pivot=np.asarray(drag['pivot'],dtype=float)
        delta_q=quaternion_from_axis_angle(axis_world,angle) if mode=='rotate' and axis_world is not None else None
        basis=[np.asarray(a,dtype=float) for a in (drag['basis'] or drag['axes'])]
        factors=list(scale_factors or (1.0,1.0,1.0))
        if mode=='scale':factors=[max(.001,float(v)) for v in factors]
        changed=False
        for index in drag['targets']:
            values=list(drag['start_values'][index]);world=np.asarray(drag['start_worlds'][index],dtype=float)
            parent_inverse=drag['parent_inverses'][index];locks=transform_locks(self.m_project.m_document,index)
            if mode=='move' and world_delta is not None:
                local_delta=parent_inverse@np.asarray([*world_delta,0.0])
                values[:3]=[values[i] if locks['location'][i] else values[i]+float(local_delta[i]) for i in range(3)]
            elif mode=='rotate' and delta_q is not None:
                if drag['pivot_mode']!='individual':
                    position=world[:3,3];rotated=pivot+self.rotate_vector(position-pivot,delta_q)
                    local_position=parent_inverse@np.asarray([*rotated,1.0]);values[:3]=[values[i] if locks['location'][i] else float(local_position[i]) for i in range(3)]
                world_q=quaternion_multiply(delta_q,drag['world_quaternions'][index])
                local_q=quaternion_multiply(quaternion_inverse(drag['parent_quaternions'][index]),world_q)
                rotated_euler=quaternion_to_euler(local_q);values[3:6]=[values[3+i] if locks['rotation'][i] else rotated_euler[i] for i in range(3)]
            elif mode=='scale':
                if drag['pivot_mode']!='individual':
                    position=world[:3,3];offset=position-pivot;scaled=np.zeros(3,dtype=float)
                    for i,axis in enumerate(basis[:3]):scaled+=axis*float(np.dot(offset,axis))* (factors[i]-1.0)
                    local_position=parent_inverse@np.asarray([*(position+scaled),1.0]);values[:3]=[values[i] if locks['location'][i] else float(local_position[i]) for i in range(3)]
                target_axes=self.orthogonal_axes(world)
                for local_axis in range(3):
                    if locks['scale'][local_axis]:continue
                    factor=1.0
                    for i,axis in enumerate(basis[:3]):
                        alignment=max(0.0,min(1.0,float(np.dot(target_axes[local_axis],axis))**2))
                        factor*=factors[i]**alignment
                    values[6+local_axis]*=factor
            if any(abs(float(a)-float(b))>1e-12 for a,b in zip(values,drag['start_values'][index])):
                changed=True
                try:self.m_project.transform_node(index,values,checkpoint=False)
                except Exception as error:
                    window=self.window()
                    if hasattr(window,'statusBar'):window.statusBar().showMessage('Gizmo transform failed: '+str(error))
                    return
        if changed and not drag['checkpointed']:
            # Insert the original snapshot once, regardless of selection size.
            self.m_project.m_history.append(drag['snapshot']);self.m_project.m_history=self.m_project.m_history[-20:]
            self.m_project.m_future=[];self.m_project.m_changed=True;drag['checkpointed']=True
        if changed:
            window=self.window()
            for view in (getattr(window,'m_view',None),getattr(window,'m_object_view',None)):
                if view is not None:view.set_project(self.m_project,geometry=False)
            self.transform_changed.emit()
        self.request_draw()

    def update_gizmo_drag(self,point,modifiers):
        import numpy as np
        drag=self.m_gizmo_drag
        if not drag or not self.m_project:return
        drag['last_point']=(point.x(),point.y())
        dx=point.x()-drag['start'][0];dy=point.y()-drag['start'][1]
        mode=drag['mode'];handle=drag['handle'];basis=[np.asarray(a,dtype=float) for a in (drag['basis'] or drag['axes'])]
        number=None
        if drag['numeric_buffer']:
            try:number=float(drag['numeric_buffer'].rstrip('%'))/(100.0 if drag['numeric_buffer'].endswith('%') else 1.0)
            except ValueError:number=None
        shift=bool(modifiers&C.Qt.KeyboardModifier.ShiftModifier)
        snap=bool(modifiers&C.Qt.KeyboardModifier.ControlModifier)
        world_delta=None;angle=0.0;axis_world=np.asarray(drag['axis_world'],dtype=float) if drag['axis_world'] is not None else None
        factors=[1.0,1.0,1.0]
        if mode=='move':
            if drag['numeric_buffer'] and isinstance(handle,int) and number is not None:components=[number]
            elif drag['numeric_buffer'] and drag['basis']:
                parts=drag['numeric_buffer'].split(',');components=[]
                for part in parts[:len(basis)]:
                    try:components.append(float(part))
                    except ValueError:components.append(0.0)
                components+=( [0.0] * (len(basis)-len(components)) )
            elif isinstance(handle,int):
                components=self.solve_screen_basis(dx,dy,drag['screen_axes'])
                components=[components[0]*drag['size'] if components else 0.0]
            elif drag['basis']:
                components=self.solve_screen_basis(dx,dy,drag['screen_axes'])
            else:return
            if shift:components=[v*.1 for v in components]
            if snap:components=[round(v/self.m_snap_steps['move'])*self.m_snap_steps['move'] for v in components]
            world_delta=np.zeros(3,dtype=float)
            if isinstance(handle,int):world_delta=np.asarray(drag['axis_world'],dtype=float)*components[0]
            else:
                if not drag['numeric_buffer']:components=[v*drag['size'] for v in components]
                for i,component in enumerate(components):world_delta+=basis[i]*component
        elif mode=='rotate':
            if number is not None:angle=math.radians(number);axis_world=np.asarray(drag['axis_world'] or drag['view_axes'][2],dtype=float)
            elif handle=='trackball':
                view=[np.asarray(a,dtype=float) for a in drag['view_axes']]
                length=math.hypot(dx,dy);angle=length/max(1.0,min(self.width(),self.height())*.45)*math.pi
                axis_world=view[1]*dx-view[0]*dy
                norm=float(np.linalg.norm(axis_world));axis_world=axis_world/max(norm,1e-12)
            else:
                current=self.ray_plane_vector(point,drag['pivot'],drag['axis_world'])
                if current is None:return
                start=np.asarray(drag['start_vector'],dtype=float);current=np.asarray(current,dtype=float);axis_world=np.asarray(drag['axis_world'],dtype=float)
                angle=math.atan2(float(np.dot(axis_world,np.cross(start,current))),float(np.dot(start,current)))
            if shift:angle*=.1
            if snap:
                step=math.radians(self.m_snap_steps['rotate']);angle=round(angle/step)*step
        elif mode=='scale':
            if drag['numeric_buffer'] and number is not None and ',' not in drag['numeric_buffer']:
                factor=number
                if isinstance(handle,int):factors[handle]=factor
                elif handle=='uniform':factors=[factor,factor,factor]
                elif drag['basis']:
                    parts=drag['numeric_buffer'].split(',')
                    for i,part in enumerate(parts[:len(basis)]):
                        try:factors[i]=float(part.rstrip('%'))/(100.0 if part.endswith('%') else 1.0)
                        except ValueError:pass
            elif handle=='uniform':
                factor=max(.001,1.0-dy/max(1,self.height())*2.0)
                if shift:factor=1.0+(factor-1.0)*.1
                if snap:factor=round((factor-1.0)/self.m_snap_steps['scale'])*self.m_snap_steps['scale']+1.0
                factors=[factor,factor,factor]
            elif isinstance(handle,int):
                components=self.solve_screen_basis(dx,dy,drag['screen_axes'])
                delta=(components[0] if components else 0.0)*drag['size']
                if shift:delta*=.1
                factor=max(.001,1.0+delta/max(drag['size'],1e-8))
                if snap:factor=max(.001,round((factor-1.0)/self.m_snap_steps['scale'])*self.m_snap_steps['scale']+1.0)
                factors[handle]=factor
            elif drag['numeric_buffer'] and drag['basis']:
                parts=drag['numeric_buffer'].split(',')
                for i,part in enumerate(parts[:len(basis)]):
                    try:factors[i]=float(part.rstrip('%'))/(100.0 if part.endswith('%') else 1.0)
                    except ValueError:pass
            elif drag['basis']:
                components=self.solve_screen_basis(dx,dy,drag['screen_axes'])
                for i,component in enumerate(components[:len(basis)]):
                    delta=component*drag['size']
                    if shift:delta*=.1
                    factor=max(.001,1.0+delta/max(drag['size'],1e-8))
                    if snap:factor=max(.001,round((factor-1.0)/self.m_snap_steps['scale'])*self.m_snap_steps['scale']+1.0)
                    factors[i]=factor
        self.apply_gizmo_operation(drag,world_delta=world_delta,angle=angle,axis_world=axis_world,scale_factors=factors)
        window=self.window()
        if hasattr(window,'statusBar'):
            if drag['numeric_buffer']:value=drag['numeric_buffer']
            elif mode=='rotate':value='%+.2f°'%math.degrees(angle)
            elif mode=='scale':value=' × '.join('%.3f'%v for v in factors)
            else:value='Δ '+', '.join('%+.3f'%v for v in (world_delta if world_delta is not None else (0,0,0)))
            window.statusBar().showMessage('%s · %s · %s · %s'%({'move':'Move','rotate':'Rotate','scale':'Scale'}[mode],handle, value, 'Snapping' if snap else ('Precision' if shift else '')))

    def cancel_gizmo_drag(self):
        drag=self.m_gizmo_drag
        if drag is None:return
        if drag['checkpointed'] and self.m_project:
            self.m_project.restore(drag['snapshot'])
            if self.m_project.m_history:self.m_project.m_history.pop()
            self.m_project.m_future=[];self.m_project.m_changed=drag['was_changed']
            window=self.window()
            for view in (getattr(window,'m_view',None),getattr(window,'m_object_view',None)):
                if view is not None:view.set_project(self.m_project,geometry=False)
            self.transform_changed.emit()
        self.m_gizmo_drag=None;self.unsetCursor();self.m_last=None;self.m_press=None;self.m_navigation_start=None;self.request_draw()

    def rebase_gizmo_drag(self,handle,point):
        old=self.m_gizmo_drag
        if old is None:return
        if self.m_gizmo_mode=='transform' and isinstance(handle,int):handle=old['mode']+'_'+('x','y','z')[handle]
        fresh=self.begin_gizmo_drag(handle,point)
        if fresh is None:return
        fresh['checkpointed']=old['checkpointed'];fresh['snapshot']=old['snapshot'];fresh['was_changed']=old['was_changed']
        self.m_gizmo_drag=fresh

    def mousePressEvent(self,e):
        self.setFocus(C.Qt.FocusReason.MouseFocusReason)
        if e.button()==C.Qt.MouseButton.RightButton and self.m_gizmo_drag is not None:
            self.cancel_gizmo_drag();return
        if e.button()==C.Qt.MouseButton.RightButton and self.m_navigation_start:
            self.m_center,self.m_distance,self.m_yaw,self.m_pitch,self.m_orthographic,self.m_axis_view=self.m_navigation_start
            self.m_navigation_start=None;self.m_last=None;self.m_press=None;self.request_draw();return
        if e.button()==C.Qt.MouseButton.RightButton and e.modifiers()&C.Qt.KeyboardModifier.ShiftModifier:
            cursor_point=self.ray_plane_point(e.position(),(0.0,0.0,0.0),(0.0,1.0,0.0))
            if cursor_point is not None and hasattr(self.window(),'set_cursor_location'):self.window().set_cursor_location(cursor_point.tolist())
            return
        self.m_last=e.position();self.m_press=e.position();self.m_dragged=False
        if e.button()==C.Qt.MouseButton.LeftButton and not (e.modifiers()&C.Qt.KeyboardModifier.AltModifier):
            axis=self.hit_test_gizmo(e.position())
            if axis is not None:
                state=self.gizmo_state()
                if state is not None and not state['enabled']:
                    if hasattr(self.window(),'statusBar'):self.window().statusBar().showMessage('Object is locked. Uncheck Lock in the Outliner to move it.')
                    self.m_last=None;self.m_press=None;return
                self.m_gizmo_drag=self.begin_gizmo_drag(axis,e.position())
                if self.m_gizmo_drag is not None:
                    self.setCursor(C.Qt.CursorShape.ClosedHandCursor);return
        if e.button()==C.Qt.MouseButton.MiddleButton or (e.button()==C.Qt.MouseButton.LeftButton and e.modifiers()&C.Qt.KeyboardModifier.AltModifier):
            self.m_navigation_start=(list(self.m_center),self.m_distance,self.m_yaw,self.m_pitch,self.m_orthographic,self.m_axis_view)
    def mouseMoveEvent(self,e):
        if self.m_gizmo_drag is not None:
            self.update_gizmo_drag(e.position(),e.modifiers());return
        if not self.m_navigation_start and e.buttons()==C.Qt.MouseButton.NoButton:
            hovered=self.hit_test_gizmo(e.position())
            if hovered!=self.m_gizmo_hover:
                self.m_gizmo_hover=hovered;self.setCursor(C.Qt.CursorShape.OpenHandCursor if hovered is not None else C.Qt.CursorShape.ArrowCursor);self.request_draw()
        if self.m_last is None:return
        delta=e.position()-self.m_last;self.m_last=e.position()
        if self.m_press is not None and (e.position()-self.m_press).manhattanLength()>=4:self.m_dragged=True
        if self.m_navigation_start:
            if e.modifiers()&C.Qt.KeyboardModifier.ShiftModifier:self.pan(delta.x(),delta.y())
            elif e.modifiers()&C.Qt.KeyboardModifier.ControlModifier:self.zoom(delta.y()*.01)
            else:self.orbit(delta.x(),delta.y())
    def mouseReleaseEvent(self,e):
        if e.button()==C.Qt.MouseButton.LeftButton and self.m_gizmo_drag is not None:
            self.m_gizmo_drag=None;self.unsetCursor();self.m_last=None;self.m_press=None;self.m_navigation_start=None;self.request_draw();return
        if e.button()==C.Qt.MouseButton.LeftButton and self.m_press is not None and not self.m_dragged and not self.m_navigation_start and self.m_renderer:
            width,height=self.get_physical_size();index=self.m_renderer.pick(int(e.position().x()*width/max(1,self.width())),int(e.position().y()*height/max(1,self.height())))
            hidden=getattr(self.m_renderer,'m_hidden',None) if self.m_renderer is not None else None
            if hidden is None:hidden=hidden_nodes(self.m_project.m_document) if self.m_project else set()
            if self.m_isolated is not None and self.m_project:
                scope=(self.m_renderer.selection_nodes_cached(self.m_isolated)
                    if self.m_renderer is not None and hasattr(self.m_renderer,'selection_nodes_cached')
                    else selection_nodes(self.m_project.m_document,self.m_isolated))
                if index not in scope:index=-1
            if index not in hidden and any(i['index']==index and not i['collision'] for i in self.m_renderer.m_instances):self.selected.emit(index)
            else:index=-1
            additive=bool(e.modifiers()&(C.Qt.KeyboardModifier.ShiftModifier|C.Qt.KeyboardModifier.ControlModifier))
            self.selection_requested.emit(index,additive)
            self.request_draw()
        self.m_last=None;self.m_press=None;self.m_navigation_start=None
    def leaveEvent(self,e):
        self.m_gizmo_hover=None;self.setCursor(C.Qt.CursorShape.ArrowCursor);self.request_draw();super().leaveEvent(e)
    def wheelEvent(self,e):self.zoom(-(e.angleDelta().y() or e.pixelDelta().y())/1200);e.accept()
    def keyPressEvent(self,e):
        key=e.key();mods=e.modifiers();pad=bool(mods&C.Qt.KeyboardModifier.KeypadModifier)
        if self.m_gizmo_drag is not None:
            drag=self.m_gizmo_drag
            if key==C.Qt.Key.Key_Escape:
                self.cancel_gizmo_drag();e.accept();return
            if key in (C.Qt.Key.Key_Return,C.Qt.Key.Key_Enter):
                self.m_gizmo_drag=None;self.m_press=None;self.m_last=None;self.unsetCursor();self.request_draw();e.accept();return
            if key==C.Qt.Key.Key_Backspace:
                drag['numeric_buffer']=drag['numeric_buffer'][:-1];self.update_gizmo_drag(C.QPointF(*drag['last_point']),mods);e.accept();return
            if key in (C.Qt.Key.Key_X,C.Qt.Key.Key_Y,C.Qt.Key.Key_Z) and not mods:
                axis={C.Qt.Key.Key_X:0,C.Qt.Key.Key_Y:1,C.Qt.Key.Key_Z:2}[key]
                handle=axis
                if drag.get('axis_lock')==axis:
                    handle=axis;world_axis=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]][axis]
                    # A repeated axis key toggles the corresponding global axis.
                    old_orientation=self.m_transform_orientation;self.m_transform_orientation='global'
                    self.rebase_gizmo_drag(handle,C.QPointF(*drag['last_point']))
                    self.m_transform_orientation=old_orientation
                    if self.m_gizmo_drag is not None:self.m_gizmo_drag['axis_world']=world_axis
                else:
                    self.rebase_gizmo_drag(handle,C.QPointF(*drag['last_point']))
                if self.m_gizmo_drag is not None:self.m_gizmo_drag['axis_lock']=axis
                e.accept();return
            text=e.text()
            if text and (text.isdigit() or text in ('.','-',',','%')):
                drag['numeric_buffer']+=text
                self.update_gizmo_drag(C.QPointF(*drag['last_point']),mods);e.accept();return
            if key in (C.Qt.Key.Key_Plus,C.Qt.Key.Key_Minus):
                drag['numeric_buffer']+=('+' if key==C.Qt.Key.Key_Plus else '-')
                self.update_gizmo_drag(C.QPointF(*drag['last_point']),mods);e.accept();return
        if key in (C.Qt.Key.Key_T,C.Qt.Key.Key_G,C.Qt.Key.Key_R,C.Qt.Key.Key_S) and not mods:
            self.gizmo_mode_requested.emit({C.Qt.Key.Key_T:'transform',C.Qt.Key.Key_G:'move',C.Qt.Key.Key_R:'rotate',C.Qt.Key.Key_S:'scale'}[key]);e.accept();return
        if pad and key==C.Qt.Key.Key_Slash:self.toggle_local_view()
        elif (key==C.Qt.Key.Key_Delete and not pad) or (key==C.Qt.Key.Key_X and mods==C.Qt.KeyboardModifier.NoModifier):self.delete_requested.emit()
        elif key==C.Qt.Key.Key_A and not mods&C.Qt.KeyboardModifier.ControlModifier:self.selection_all.emit(not bool(mods&C.Qt.KeyboardModifier.AltModifier))
        elif key==C.Qt.Key.Key_Escape:self.selection_all.emit(False)
        elif key==C.Qt.Key.Key_Home:self.frame()
        elif pad and key in (C.Qt.Key.Key_Period,C.Qt.Key.Key_Comma,C.Qt.Key.Key_Delete):self.frame(True)
        elif pad and key==C.Qt.Key.Key_5:self.m_orthographic=not self.m_orthographic;self.m_axis_view=False
        elif pad and key in (C.Qt.Key.Key_1,C.Qt.Key.Key_3,C.Qt.Key.Key_7):
            self.m_yaw,self.m_pitch={C.Qt.Key.Key_1:(0,0),C.Qt.Key.Key_3:(90,0),C.Qt.Key.Key_7:(0,90)}[key]
            if mods&C.Qt.KeyboardModifier.ControlModifier:
                if key==C.Qt.Key.Key_7:self.m_pitch=-90
                else:self.m_yaw+=180
            self.m_orthographic=True;self.m_axis_view=True
        elif pad and key in (C.Qt.Key.Key_2,C.Qt.Key.Key_4,C.Qt.Key.Key_6,C.Qt.Key.Key_8):
            dx,dy={C.Qt.Key.Key_2:(0,-37.5),C.Qt.Key.Key_4:(-37.5,0),C.Qt.Key.Key_6:(37.5,0),C.Qt.Key.Key_8:(0,37.5)}[key]
            if mods&C.Qt.KeyboardModifier.ControlModifier:self.pan(dx,dy)
            else:self.orbit(dx,dy)
        elif pad and key==C.Qt.Key.Key_9:self.m_yaw=(self.m_yaw+180)%360;self.m_pitch=-self.m_pitch
        elif pad and key in (C.Qt.Key.Key_Plus,C.Qt.Key.Key_Minus):self.zoom(-.1 if key==C.Qt.Key.Key_Plus else .1)
        else:super().keyPressEvent(e);return
        self.request_draw();e.accept()

    def toggle_local_view(self):
        if self.m_isolated is not None:self.m_isolated=None
        elif self.m_selection:self.m_isolated=set(self.m_selection)
        else:return
        self.frame();self.request_draw()


class c_texture_view(W.QGraphicsView):
    def __init__(self):
        super().__init__();self.m_scene=W.QGraphicsScene(self);self.setScene(self.m_scene);self.m_pixmap=None
        checker=G.QPixmap(24,24);checker.fill(G.QColor('#454545'));painter=G.QPainter(checker);painter.fillRect(0,0,12,12,G.QColor('#626262'));painter.fillRect(12,12,12,12,G.QColor('#626262'));painter.end()
        self.setBackgroundBrush(G.QBrush(checker));self.setDragMode(W.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(W.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    def set_image(self,pixmap):
        self.m_scene.clear();self.m_pixmap=pixmap;self.resetTransform()
        if not pixmap.isNull():self.m_scene.addPixmap(pixmap);self.m_scene.setSceneRect(0,0,pixmap.width(),pixmap.height());self.fit()
    def fit(self):
        if self.m_pixmap and not self.m_pixmap.isNull():self.fitInView(self.m_scene.sceneRect(),C.Qt.AspectRatioMode.KeepAspectRatio)
    def wheelEvent(self,event):self.scale(1.2 if event.angleDelta().y()>0 else 1/1.2,1.2 if event.angleDelta().y()>0 else 1/1.2)


class c_font_panel(W.QWidget):
    """Text input + glyph output for a loaded FFON font."""
    def __init__(self,editor):
        super().__init__();self.m_editor=editor
        self.m_img=None
        layout=W.QVBoxLayout(self);layout.setContentsMargins(8,8,8,8);layout.setSpacing(6)
        layout.addWidget(W.QLabel('Text (ASCII 0x20-0x7E rendered as glyphs):'))
        self.m_input=W.QTextEdit();self.m_input.setPlaceholderText('Type text to render as glyphs…')
        self.m_input.setMaximumHeight(100);self.m_input.textChanged.connect(self._render)
        layout.addWidget(self.m_input)
        bar=W.QHBoxLayout();bar.setContentsMargins(0,4,0,0);bar.setSpacing(4)
        self.m_export_btn=W.QPushButton('Export PNG…');self.m_export_btn.clicked.connect(self.export_png);self.m_export_btn.setEnabled(False);bar.addWidget(self.m_export_btn)
        bar.addWidget(W.QLabel('Margin L:'));self.m_margin_l=W.QSpinBox();self.m_margin_l.setRange(0,512);self.m_margin_l.setValue(16);self.m_margin_l.setToolTip('Left');self.m_margin_l.valueChanged.connect(lambda *_:self._render());bar.addWidget(self.m_margin_l)
        bar.addWidget(W.QLabel('R:'));self.m_margin_r=W.QSpinBox();self.m_margin_r.setRange(0,512);self.m_margin_r.setValue(16);self.m_margin_r.setToolTip('Right');self.m_margin_r.valueChanged.connect(lambda *_:self._render());bar.addWidget(self.m_margin_r)
        bar.addWidget(W.QLabel('T:'));self.m_margin_t=W.QSpinBox();self.m_margin_t.setRange(0,512);self.m_margin_t.setValue(16);self.m_margin_t.setToolTip('Top');self.m_margin_t.valueChanged.connect(lambda *_:self._render());bar.addWidget(self.m_margin_t)
        bar.addWidget(W.QLabel('B:'));self.m_margin_b=W.QSpinBox();self.m_margin_b.setRange(0,512);self.m_margin_b.setValue(16);self.m_margin_b.setToolTip('Bottom');self.m_margin_b.valueChanged.connect(lambda *_:self._render());bar.addWidget(self.m_margin_b)
        bar.addStretch(1);layout.addLayout(bar)
        bar.addStretch(1);layout.addLayout(bar)
        self.m_output=W.QLabel('No font loaded.');self.m_output.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_output.setStyleSheet('QLabel { background:#282828; color:#dedede; }')
        self.m_output.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Expanding)
        self.m_scroll=W.QScrollArea();self.m_scroll.setWidgetResizable(True);self.m_scroll.setWidget(self.m_output)
        self.m_scroll.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Expanding)
        layout.addWidget(W.QLabel('Glyph output:'))
        layout.addWidget(self.m_scroll,1)
        self._render()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._render()

    def _output_width(self):
        try:
            return max(1,self.m_scroll.viewport().width()-8)
        except Exception:
            return None

    def _render(self):
        text=self.m_input.toPlainText()
        font=getattr(self.m_editor,'m_font_font',None);data=getattr(self.m_editor,'m_font_data',None)
        if font is None or data is None:
            self.m_output.setPixmap(G.QPixmap());self.m_output.setText('No font loaded.');self.m_img=None;self.m_export_btn.setEnabled(False);return
        try:
            margin_l=self.m_margin_l.value();margin_r=self.m_margin_r.value()
            margin_t=self.m_margin_t.value();margin_b=self.m_margin_b.value()
            panel_w=self.m_scroll.viewport().width()
            max_width=panel_w-margin_l-margin_r
            img=arika_ffon.render_text(font,data,text,max_width=max_width)
        except Exception as error:
            self.m_output.setPixmap(G.QPixmap());self.m_output.setText('Render error: '+str(error));self.m_img=None;self.m_export_btn.setEnabled(False);return
        # Position the rendered glyph block inside the margin rect; the rest is
        # transparent panel background (no padding around the glyphs themselves).
        canvas_w=max(panel_w,margin_l+img.width+margin_r)
        canvas=Image.new('RGBA',(canvas_w,img.height+margin_t+margin_b),(0,0,0,0))
        canvas.paste(img,(margin_l,margin_t))
        self.m_img=canvas
        pix=arika_ffon.image_to_qpixmap(img)
        self.m_output.setPixmap(pix);self.m_output.setText('')
        self.m_export_btn.setEnabled(True)

    def export_png(self):
        if self.m_img is None:return
        path,_=W.QFileDialog.getSaveFileName(self,'Export glyph output as PNG','','PNG (*.png)')
        if not path:return
        try:
            self.m_img.save(path,'PNG')
            self.m_editor.statusBar().showMessage('Exported glyph output to %s'%path,0)
        except Exception as error:
            self.m_editor.fail(error)

class c_outliner_pinned_columns(W.QWidget):
    """Fixed Show/Lock controls painted over the right side of the tree."""
    COLUMN_WIDTH=44
    CHECK_SIZE=17
    TOTAL_WIDTH=COLUMN_WIDTH*2

    def __init__(self,tree):
        super().__init__(tree)
        self.m_tree=tree
        self.setMouseTracking(True)
        self.setToolTip('Show: checked means visible. Lock: checked means transforms are locked.')
        tree.viewport().installEventFilter(self)
        tree.header().installEventFilter(self)
        tree.verticalScrollBar().valueChanged.connect(lambda *_:self.update())
        tree.itemExpanded.connect(lambda *_:self.update())
        tree.itemCollapsed.connect(lambda *_:self.update())
        tree.itemChanged.connect(lambda *_:self.update())

    def eventFilter(self,watched,event):
        if watched in (self.m_tree.viewport(),self.m_tree.header()):
            if event.type()==C.QEvent.Type.Resize:
                C.QTimer.singleShot(0,self.m_tree.update_outliner_layout)
            elif event.type()==C.QEvent.Type.Paint:
                self.update()
        return super().eventFilter(watched,event)

    def paintEvent(self,event):
        tree=self.m_tree
        painter=G.QPainter(self)
        try:
            header_height=tree.header().height()
            viewport=tree.viewport()
            panel_rect=self.rect()
            painter.fillRect(panel_rect,G.QColor('#282828'))
            painter.fillRect(C.QRect(0,0,self.width(),header_height),G.QColor('#353535'))

            painter.setPen(G.QColor('#dedede'))
            for column,label in enumerate(('Show','Lock')):
                left=column*self.COLUMN_WIDTH
                header_rect=C.QRect(left,0,self.COLUMN_WIDTH,header_height)
                painter.drawText(header_rect.adjusted(0,0,-5,0),
                    C.Qt.AlignmentFlag.AlignRight|C.Qt.AlignmentFlag.AlignVCenter,label)

            painter.setPen(G.QPen(G.QColor('#202020'),1))
            painter.drawLine(0,0,0,self.height())
            painter.drawLine(self.COLUMN_WIDTH,0,self.COLUMN_WIDTH,self.height())

            # The overlay is positioned at y=0 in tree coordinates, while
            # visualItemRect() reports row positions relative to the viewport.
            # Add the viewport's tree-relative y offset explicitly. Avoid
            # QWidget.mapTo() here: the overlay and viewport are sibling widgets,
            # and mapping/clip coordinates can otherwise exclude every row.
            viewport_y=viewport.geometry().y()
            viewport_rect=C.QRect(0,viewport_y,self.width(),viewport.height())

            def paint_items(parent):
                for row in range(parent.childCount()):
                    item=parent.child(row)
                    if item.isHidden():
                        continue
                    item_rect=tree.visualItemRect(item)
                    if item_rect.isValid() and item_rect.height()>0:
                        top=viewport_y+item_rect.top()
                        row_rect=C.QRect(0,top,self.width(),item_rect.height())
                        if row_rect.intersects(viewport_rect):
                            if item.isSelected():
                                painter.fillRect(row_rect,G.QColor('#4779a6'))
                            values=(bool(item.data(1,SHOW_ROLE)),bool(item.data(2,LOCK_ROLE)))
                            for column,checked in enumerate(values):
                                x=column*self.COLUMN_WIDTH+self.COLUMN_WIDTH-self.CHECK_SIZE-4
                                y=top+max(0,(item_rect.height()-self.CHECK_SIZE)//2)
                                option=W.QStyleOptionButton()
                                option.rect=C.QRect(x,y,self.CHECK_SIZE,self.CHECK_SIZE)
                                option.state=W.QStyle.StateFlag.State_Enabled
                                option.state|=(W.QStyle.StateFlag.State_On if checked
                                    else W.QStyle.StateFlag.State_Off)
                                self.style().drawPrimitive(
                                    W.QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                                    option,painter)
                    if item.isExpanded():
                        paint_items(item)

            painter.save()
            painter.setClipRect(viewport_rect,C.Qt.ClipOperation.IntersectClip)
            paint_items(tree.invisibleRootItem())
            painter.restore()
        finally:
            painter.end()

    def mousePressEvent(self,event):
        position=event.position().toPoint() if hasattr(event,'position') else event.pos()
        tree=self.m_tree
        viewport=tree.viewport()
        # Overlay coordinates start at the top of the tree; tree.itemAt() uses
        # viewport coordinates, whose origin is below the header.
        view_y=position.y()-viewport.geometry().y()
        if event.button()==C.Qt.MouseButton.RightButton and 0<=view_y<viewport.height():
            view_position=C.QPoint(max(0,viewport.width()-1),view_y)
            editor=tree.m_editor
            if hasattr(editor,'object_menu'):
                editor.object_menu(view_position)
            event.accept()
            return
        if event.button()!=C.Qt.MouseButton.LeftButton or not 0<=view_y<viewport.height():
            event.accept()
            return

        item=tree.itemAt(C.QPoint(max(0,viewport.width()-1),view_y))
        if item is None:
            event.accept()
            return
        column=1 if position.x()<self.COLUMN_WIDTH else 2
        role=SHOW_ROLE if column==1 else LOCK_ROLE
        item.setData(column,role,not bool(item.data(column,role)))
        tree.itemChanged.emit(item,column)
        self.update()
        event.accept()


class c_outliner_tree(W.QTreeWidget):
    def __init__(self,editor):
        super().__init__();self.m_editor=editor;self.m_pinned_columns=None
        self.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(W.QFrame.Shape.NoFrame)
        self.itemExpanded.connect(self.schedule_outliner_layout)
        self.itemCollapsed.connect(self.schedule_outliner_layout)

    def set_pinned_columns(self):
        if self.m_pinned_columns is None:
            self.m_pinned_columns=c_outliner_pinned_columns(self)
            self.m_pinned_columns.raise_()
        self.update_outliner_layout()

    def schedule_outliner_layout(self,*args):
        C.QTimer.singleShot(0,self.update_outliner_layout)

    def update_outliner_layout(self):
        if self.m_pinned_columns is None:
            return
        viewport_rect=self.viewport().geometry()
        overlay_x=viewport_rect.x()+viewport_rect.width()-self.m_pinned_columns.TOTAL_WIDTH
        overlay_height=viewport_rect.bottom()+1
        self.m_pinned_columns.setGeometry(
            overlay_x,0,self.m_pinned_columns.TOTAL_WIDTH,max(0,overlay_height))
        self.m_pinned_columns.raise_()

        viewport_width=max(1,viewport_rect.width())
        content_width=max(0,self.sizeHintForColumn(0))
        column_width=max(viewport_width,
            content_width+self.m_pinned_columns.TOTAL_WIDTH)
        if self.columnWidth(0)!=column_width:
            self.setColumnWidth(0,column_width)
        self.m_pinned_columns.update()
        if hasattr(self.m_editor,'sync_outliner_scrollbar'):
            self.m_editor.sync_outliner_scrollbar()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.schedule_outliner_layout()

    def showEvent(self,event):
        super().showEvent(event)
        self.schedule_outliner_layout()

    def mousePressEvent(self,event):
        super().mousePressEvent(event)

    def dropEvent(self,event):
        editor=self.m_editor
        if not editor.m_project:
            event.accept();return
        indices=[item.data(0,C.Qt.ItemDataRole.UserRole) for item in self.selectedItems()]
        if not indices:
            event.accept();return
        editor.m_view.m_selection=set(indices)
        pos=event.position().toPoint() if hasattr(event,'position') else event.pos()
        item=self.itemAt(pos)
        parent=item.data(0,C.Qt.ItemDataRole.UserRole) if item is not None else None
        try:
            editor.reparent_selected(parent)
        except Exception as error:
            editor.statusBar().showMessage(str(error))
        event.accept()

class c_scene_editor(W.QMainWindow):
    def __init__(self):
        super().__init__();self.m_settings=c_editor_settings();self.m_project=None;self.m_project_path=None;self.m_index=None;self.m_material=-1;self.m_items={};self.m_color=[1,1,1,1];self.m_audio=-1
        self.m_transform_orientation='local';self.m_pivot_mode='median';self.m_cursor_location=[0.0,0.0,0.0];self.m_cursor_axes=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]];self.m_custom_orientation_axes=None;self.m_snap_steps={'move':1.0,'rotate':15.0,'scale':0.1}
        self.m_audio_buffer=None;self.m_audio_playing=False;self.m_audio_timer=None;self.m_audio_duration_ms=0
        self.m_motion=None;self.m_motion_nodes=[];self.m_motion_node_map={};self.m_bind_pose={}
        self.m_motion_time=0.0;self.m_motion_duration=0.0;self.m_motion_playing=False;self.m_motion_timer=None
        self.m_virtual=False;self.m_virtual_files={};self.m_modified_files=set();self.m_loaded_models=set()
        self.m_font_font=None;self.m_font_data=None
        self.setWindowTitle('Arika Editor');self.resize(1400,900);self.m_view=c_viewport();self.m_view.selection_requested.connect(self.select_view);self.m_view.selection_all.connect(self.select_all);self.m_view.delete_requested.connect(self.delete_selected);self.m_view.transform_changed.connect(self.sync_selection);self.m_view.gizmo_mode_requested.connect(self.set_gizmo_mode)
        self.m_views=W.QStackedWidget();self.m_views.addWidget(self.m_view);self.m_material_view=c_viewport();self.m_material_view.m_show_gizmo=False;self.m_material_view.m_options.update(grid=False,axes=False);self.m_views.addWidget(self.m_material_view)
        texture_panel=W.QWidget();texture_layout=W.QVBoxLayout(texture_panel);self.m_texture_info=W.QLabel('Choose a texture');texture_layout.addWidget(self.m_texture_info);self.m_texture_view=c_texture_view();texture_layout.addWidget(self.m_texture_view);self.m_views.addWidget(texture_panel)
        menu_panel=W.QWidget();menu_layout=W.QVBoxLayout(menu_panel);menu_layout.setContentsMargins(0,0,0,0);self.m_menu_info=W.QLabel('Menu editor');menu_layout.addWidget(self.m_menu_info)
        try:
            from arika_menu_editor import c_menu_editor
            self.m_menu_view=c_menu_editor()
            self.m_menu_view.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Expanding)
            menu_layout.addWidget(self.m_menu_view,1)
        except Exception:
            self.m_menu_view=W.QLabel('Menu editor unavailable.')
            menu_layout.addWidget(self.m_menu_view,1)
        self.m_object_view=c_viewport();self.m_object_view.m_isolated=set();self.m_object_view.selection_requested.connect(self.select_view);self.m_object_view.selection_all.connect(self.select_all);self.m_object_view.delete_requested.connect(self.delete_selected);self.m_object_view.transform_changed.connect(self.sync_selection);self.m_object_view.gizmo_mode_requested.connect(self.set_gizmo_mode);self.m_views.addWidget(self.m_object_view)
        self.m_views.addWidget(menu_panel)
        audio_panel=W.QWidget();al=W.QVBoxLayout(audio_panel);al.setContentsMargins(8,8,8,8);al.setSpacing(6)
        self.m_audio_name=W.QLabel('No audio selected');self.m_audio_name.setObjectName('editor_heading');al.addWidget(self.m_audio_name)
        self.m_audio_info=W.QLabel('');al.addWidget(self.m_audio_info)
        ctrl=W.QWidget();cl=W.QHBoxLayout(ctrl);cl.setContentsMargins(0,0,0,0);cl.setSpacing(4)
        self.m_audio_play_btn=W.QPushButton('▶ Play');self.m_audio_play_btn.clicked.connect(self.play_audio);self.m_audio_play_btn.setEnabled(False);cl.addWidget(self.m_audio_play_btn)
        self.m_audio_stop_btn=W.QPushButton('■ Stop');self.m_audio_stop_btn.clicked.connect(self.stop_audio);self.m_audio_stop_btn.setEnabled(False);cl.addWidget(self.m_audio_stop_btn)
        cl.addStretch()
        cl.addWidget(W.QLabel('Volume:'));self.m_audio_vol=W.QSlider(C.Qt.Orientation.Horizontal);self.m_audio_vol.setRange(0,100);self.m_audio_vol.setValue(80);self.m_audio_vol.setFixedWidth(120);self.m_audio_vol.valueChanged.connect(self.set_audio_volume);cl.addWidget(self.m_audio_vol)
        al.addWidget(ctrl)
        bar2=W.QWidget();bl=W.QHBoxLayout(bar2);bl.setContentsMargins(0,0,0,0);bl.setSpacing(4)
        self.m_audio_pos=W.QLabel('0:00');bl.addWidget(self.m_audio_pos);self.m_audio_slider=W.QSlider(C.Qt.Orientation.Horizontal);self.m_audio_slider.setRange(0,1000);self.m_audio_slider.setValue(0);self.m_audio_slider.setEnabled(False);self.m_audio_slider.sliderReleased.connect(self.seek_audio);bl.addWidget(self.m_audio_slider);self.m_audio_dur=W.QLabel('0:00');bl.addWidget(self.m_audio_dur);al.addWidget(bar2)
        note=W.QLabel('Audio plays from embedded project WAV; no temp files written.');note.setWordWrap(True);note.setStyleSheet('color:#888888;');al.addWidget(note);al.addStretch()
        self.m_views.addWidget(audio_panel)
        self.m_font_panel=c_font_panel(self);self.m_views.addWidget(self.m_font_panel)
        for view in (self.m_view,self.m_object_view):
            view.m_transform_orientation=self.m_transform_orientation;view.m_pivot_mode=self.m_pivot_mode;view.m_cursor_location=list(self.m_cursor_location);view.m_cursor_axes=[list(a) for a in self.m_cursor_axes];view.m_custom_orientation_axes=self.m_custom_orientation_axes;view.m_snap_steps=dict(self.m_snap_steps)
        self.setStyleSheet(EDITOR_STYLE)
        bar=W.QToolBar('Viewport');bar.setObjectName('viewport_header');bar.setMovable(False)
        self.m_editor_heading=W.QLabel('3D Viewport');self.m_editor_heading.setObjectName('editor_heading');bar.addWidget(self.m_editor_heading)
        view_mode=W.QComboBox();view_mode.addItems(['World','Material Preview','Texture Browser','Object View','Menu Editor','Audio','Fonts']);view_mode.currentIndexChanged.connect(self.change_view);bar.addWidget(view_mode);self.m_view_mode=view_mode
        view_menu=W.QMenu('View',self)
        for title,callback in [('Frame all',self.fit),('Frame selected',lambda:self.active_view().frame(True)),('Toggle Local View (Numpad /)',lambda:self.active_view().toggle_local_view()),('Set 3D Cursor to Active',self.set_cursor_to_active),('Align 3D Cursor Orientation to Active',self.align_cursor_to_active),('Create Custom Orientation from Active',self.create_custom_orientation_from_active),('Clear Custom Orientation',self.clear_custom_orientation),('Reset 3D Cursor',self.reset_cursor)]:view_menu.addAction(title).triggered.connect(callback)
        view_menu.addSeparator()
        for title,yaw,pitch in [('Front',0,0),('Back',180,0),('Right',90,0),('Left',270,0),('Top',0,90),('Bottom',0,-90)]:
            view_menu.addAction(title).triggered.connect(lambda _=False,yaw=yaw,pitch=pitch:self.align_view(yaw,pitch))
        view_button=W.QToolButton();view_button.setText('View');view_button.setMenu(view_menu);view_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup);bar.addWidget(view_button)
        bar.addSeparator();self.m_gizmo_buttons={};self.m_gizmo_group=W.QButtonGroup(self);self.m_gizmo_group.setExclusive(True)
        for label,gizmo_mode,shortcut in [('Transform','transform','T'),('Move','move','G'),('Rotate','rotate','R'),('Scale','scale','S')]:
            gizmo_button=W.QToolButton();gizmo_button.setText(label);gizmo_button.setCheckable(True);gizmo_button.setToolTip('%s gizmo (%s)'%(label,shortcut));self.m_gizmo_group.addButton(gizmo_button);bar.addWidget(gizmo_button)
            gizmo_button.clicked.connect(lambda checked=False,mode=gizmo_mode:self.set_gizmo_mode(mode));self.m_gizmo_buttons[gizmo_mode]=gizmo_button
        self.m_gizmo_buttons['move'].setChecked(True)
        orientation=W.QComboBox();orientation.addItems(['Global','Local','Normal','Gimbal','View','Cursor','Custom']);orientation.setCurrentText('Local');orientation.setToolTip('Transform orientation: Global, Local, Normal, Gimbal, View, Cursor or Custom');orientation.currentTextChanged.connect(self.set_transform_orientation);bar.addWidget(orientation);self.m_orientation_combo=orientation
        pivot=W.QComboBox();pivot.addItems(['Median Point','Active Element','Individual Origins','3D Cursor']);pivot.setCurrentText('Median Point');pivot.setToolTip('Pivot for rotation and scaling');pivot.currentTextChanged.connect(self.set_pivot_mode);bar.addWidget(pivot);self.m_pivot_combo=pivot
        snap_button=W.QToolButton();snap_button.setText('Snap');snap_menu=W.QMenu(snap_button)
        for label,transform_mode,values in [('Move increment','move',[.1,.25,.5,1.0,5.0,10.0]),('Rotation increment','rotate',[1.0,5.0,10.0,15.0,30.0,45.0,90.0]),('Scale increment','scale',[.01,.05,.1,.25,.5])]:
            submenu=snap_menu.addMenu(label);group=G.QActionGroup(submenu);group.setExclusive(True)
            for value in values:
                suffix='°' if transform_mode=='rotate' else ('%' if transform_mode=='scale' else ' units')
                display=('%g'%(value*100) if transform_mode=='scale' else '%g'%value)+suffix
                action=submenu.addAction(display);action.setCheckable(True);action.setChecked(abs(self.m_snap_steps[transform_mode]-value)<1e-9);group.addAction(action)
                action.triggered.connect(lambda checked=False,mode=transform_mode,value=value:self.set_snap_step(mode,value))
        snap_button.setMenu(snap_menu);snap_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup);snap_button.setToolTip('Ctrl during a transform uses these snap increments');bar.addWidget(snap_button);self.m_snap_button=snap_button
        spacer=W.QWidget();spacer.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Preferred);bar.addWidget(spacer)
        mode=W.QComboBox();mode.addItems(['Textured','Solid','Wireframe']);mode.currentTextChanged.connect(self.mode);bar.addWidget(mode);self.m_shading_mode=mode
        collision=W.QCheckBox('Collision');collision.toggled.connect(self.collision);bar.addWidget(collision);self.m_collision_toggle=collision
        options=W.QMenu('Viewport options',self);self.m_option_actions={}
        for label,key in [('Floor grid','grid'),('World axes','axes'),('Selection highlight','highlight'),('Backface culling','cull')]:
            action=options.addAction(label);action.setCheckable(True);action.toggled.connect(lambda checked,key=key:self.viewport_option(key,checked));self.m_option_actions[key]=action
        options.addSeparator();self.m_projection_action=options.addAction('Orthographic projection');self.m_projection_action.setCheckable(True);self.m_projection_action.toggled.connect(self.projection)
        options.addAction('Background color…').triggered.connect(self.background_color)
        options.aboutToShow.connect(self.sync_view_controls)
        button=W.QToolButton();button.setText('Viewport');button.setMenu(options);button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup);bar.addWidget(button)
        center=W.QWidget();center_layout=W.QVBoxLayout(center);center_layout.setContentsMargins(0,0,0,0);center_layout.setSpacing(1);center_layout.addWidget(bar);center_layout.addWidget(self.m_views,1);self.setCentralWidget(center)
        self.m_viewport_header=bar
        self.m_tree=c_outliner_tree(self);self.m_tree.setHeaderLabels(['Scene / object','Show','Lock']);self.m_tree.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection);self.m_tree.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectItems)
        self.m_tree.setDragEnabled(True);self.m_tree.setAcceptDrops(True);self.m_tree.setDragDropMode(W.QAbstractItemView.DragDropMode.InternalMove);self.m_tree.setDefaultDropAction(C.Qt.DropAction.MoveAction)
        self.m_tree.header().setSectionResizeMode(0,W.QHeaderView.ResizeMode.Fixed)
        for column in (1,2):
            self.m_tree.header().setSectionResizeMode(column,W.QHeaderView.ResizeMode.Fixed)
            self.m_tree.setColumnWidth(column,44)
            self.m_tree.setColumnHidden(column,True)
        self.m_tree.setColumnWidth(0,max(1,self.m_tree.viewport().width()))
        self.m_tree.set_pinned_columns()
        self.m_tree.itemChanged.connect(self.node_state_changed)
        self.m_tree.setContextMenuPolicy(C.Qt.ContextMenuPolicy.CustomContextMenu);self.m_tree.customContextMenuRequested.connect(self.object_menu)
        self.m_tree.itemSelectionChanged.connect(self.sync_selection);self.m_tree.currentItemChanged.connect(lambda *_:self.sync_selection())
        for sequence,select in [('A',True),('Alt+A',False),('Escape',False)]:
            shortcut=G.QShortcut(G.QKeySequence(sequence),self.m_tree);shortcut.setContext(C.Qt.ShortcutContext.WidgetShortcut);shortcut.activated.connect(lambda select=select:self.select_all(select))
        for widget in (self.m_tree,self.m_view,self.m_object_view):
            for sequence,callback in [('H',lambda:self.change_node_state(hidden=True)),('Alt+H',self.show_all_objects)]:
                shortcut=G.QShortcut(G.QKeySequence(sequence),widget);shortcut.setContext(C.Qt.ShortcutContext.WidgetShortcut);shortcut.activated.connect(callback)
        for sequence in ('Delete','X'):
            shortcut=G.QShortcut(G.QKeySequence(sequence),self.m_tree);shortcut.setContext(C.Qt.ShortcutContext.WidgetShortcut);shortcut.activated.connect(self.delete_selected)
        for sequence in ('Ctrl+D',):
            shortcut=G.QShortcut(G.QKeySequence(sequence),self.m_tree);shortcut.setContext(C.Qt.ShortcutContext.WidgetShortcut);shortcut.activated.connect(self.duplicate_selected)
        for widget in (self.m_view,self.m_object_view):
            shortcut=G.QShortcut(G.QKeySequence('Ctrl+D'),widget);shortcut.setContext(C.Qt.ShortcutContext.WidgetShortcut);shortcut.activated.connect(self.duplicate_selected)
        search=W.QLineEdit();search.setPlaceholderText('Filter objects…');search.textChanged.connect(self.filter_tree)
        self.m_tree_toggle_button=W.QPushButton('+');self.m_tree_toggle_button.setToolTip('Expand or collapse all objects');self.m_tree_toggle_button.clicked.connect(self.toggle_tree_expand)
        filter_row=W.QWidget();filter_layout=W.QHBoxLayout(filter_row);filter_layout.setContentsMargins(0,0,0,0);filter_layout.addWidget(search,1);filter_layout.addWidget(self.m_tree_toggle_button)
        self.m_tree_hscroll=W.QScrollBar(C.Qt.Orientation.Horizontal)
        self.m_tree_hscroll.setFixedHeight(max(14,self.m_tree.horizontalScrollBar().sizeHint().height()))
        tree_panel=W.QWidget();tree_panel_layout=W.QVBoxLayout(tree_panel)
        tree_panel_layout.setContentsMargins(0,0,0,0);tree_panel_layout.setSpacing(0)
        tree_panel_layout.addWidget(self.m_tree,1)
        tree_scroll_row=W.QWidget();tree_scroll_layout=W.QHBoxLayout(tree_scroll_row)
        tree_scroll_layout.setContentsMargins(0,0,0,0);tree_scroll_layout.setSpacing(0)
        tree_scroll_layout.addWidget(self.m_tree_hscroll,0);tree_scroll_layout.addStretch(1)
        tree_panel_layout.addWidget(tree_scroll_row)
        native_hscroll=self.m_tree.horizontalScrollBar()
        native_hscroll.valueChanged.connect(self.m_tree_hscroll.setValue)
        native_hscroll.rangeChanged.connect(lambda *_:self.sync_outliner_scrollbar())
        self.m_tree_hscroll.valueChanged.connect(native_hscroll.setValue)
        outliner=W.QWidget();layout=W.QVBoxLayout(outliner);layout.setContentsMargins(5,5,5,5);layout.addWidget(filter_row);layout.addWidget(tree_panel)
        dock=W.QDockWidget('Scene Collection — Outliner',self);dock.setObjectName('scene_outliner');dock.setWidget(outliner);self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,dock);self.m_outliner_dock=dock
        tabs=W.QTabWidget();self.m_object=W.QWidget();object_layout=W.QVBoxLayout(self.m_object);self.m_label=W.QLabel('Select an object');object_layout.addWidget(self.m_label);self.m_fields=[]
        transform=W.QGroupBox('Transform');form=W.QFormLayout(transform);form.setContentsMargins(8,12,8,8);form.setHorizontalSpacing(5);form.setLabelAlignment(C.Qt.AlignmentFlag.AlignTop);object_layout.addWidget(transform)
        self.m_axis_lock_checks={}
        for component_index,label in enumerate(('Location','Rotation','Scale')):
            row=W.QWidget();row_layout=W.QVBoxLayout(row);row_layout.setContentsMargins(0,0,0,0);row_layout.setSpacing(2)
            for axis_index,axis in enumerate(('X','Y','Z')):
                axis_row=W.QWidget();axis_layout=W.QHBoxLayout(axis_row);axis_layout.setContentsMargins(0,0,0,0);axis_layout.setSpacing(3)
                field=W.QDoubleSpinBox();field.setDecimals(6);field.setRange(-1e8,1e8);field.setMinimumWidth(0)
                # Qt's stylesheet geometry with NoButtons can collapse the
                # embedded line edit to one pixel. Keep native steppers.
                field.setButtonSymbols(W.QAbstractSpinBox.ButtonSymbols.UpDownArrows)
                field.setToolTip(label+' '+axis+(' (radians)' if label=='Rotation' else ''));field.setPrefix(axis+' ');axis_layout.addWidget(field,1);self.m_fields.append(field)
                lock=W.QCheckBox('🔒');lock.setToolTip('Lock '+label+' '+axis);lock.setMaximumWidth(34);lock.toggled.connect(lambda checked,component=component_index,axis=axis_index:self.set_axis_transform_lock(component,axis,checked));axis_layout.addWidget(lock);self.m_axis_lock_checks[component_index*3+axis_index]=lock
                row_layout.addWidget(axis_row)
            form.addRow(label,row)
        apply=W.QPushButton('Apply active transform');apply.clicked.connect(self.apply_transform);form.addRow(apply);self.m_apply_transform=apply;apply.setEnabled(False)
        self.m_object_materials=W.QComboBox();self.m_object_materials.currentIndexChanged.connect(self.select_object_material);form.addRow('Material slots',self.m_object_materials)
        object_layout.addStretch()
        object_scroll=W.QScrollArea();object_scroll.setWidgetResizable(True);object_scroll.setWidget(self.m_object);tabs.addTab(object_scroll,'Object')
        materials=W.QWidget();mf=W.QVBoxLayout(materials);self.m_materials=W.QListWidget();self.m_materials.currentRowChanged.connect(self.select_material);mf.addWidget(self.m_materials)
        self.m_materials.setMaximumHeight(140)
        self.m_texture=W.QComboBox();mf.addWidget(self.m_texture);self.m_thumbnail=W.QLabel();self.m_thumbnail.setFixedSize(250,140);self.m_thumbnail.setAlignment(C.Qt.AlignmentFlag.AlignCenter);mf.addWidget(self.m_thumbnail)
        self.m_texture.currentIndexChanged.connect(self.show_texture)
        load=W.QPushButton('Import image (project / glTF)');load.clicked.connect(self.import_texture);mf.addWidget(load)
        color=W.QPushButton('Base color / tint');color.clicked.connect(self.choose_color);mf.addWidget(color)
        self.m_alpha=W.QComboBox();self.m_alpha.addItems(['OPAQUE','MASK','BLEND']);mf.addWidget(self.m_alpha)
        self.m_double=W.QCheckBox('Double sided');mf.addWidget(self.m_double)
        apply_mat=W.QPushButton('Apply material');apply_mat.clicked.connect(self.apply_material);mf.addWidget(apply_mat)
        note=W.QLabel('Material and image edits save to projects / glTF.\nNative MDL/PIX are unchanged.');note.setWordWrap(True);mf.addWidget(note);mf.addStretch();material_scroll=W.QScrollArea();material_scroll.setWidgetResizable(True);material_scroll.setWidget(materials);tabs.addTab(material_scroll,'Materials')
        motion_panel=W.QWidget();mpl=W.QVBoxLayout(motion_panel);mpl.setContentsMargins(8,8,8,8);mpl.setSpacing(6)
        self.m_motion_name=W.QLabel('No motion loaded');self.m_motion_name.setObjectName('editor_heading');mpl.addWidget(self.m_motion_name)
        self.m_motion_info=W.QLabel('');mpl.addWidget(self.m_motion_info)
        mpl.addWidget(W.QLabel('Motion:'));self.m_motion_list=W.QComboBox();self.m_motion_list.currentIndexChanged.connect(self.motion_list_changed);mpl.addWidget(self.m_motion_list)
        mctrl=W.QWidget();mcl=W.QHBoxLayout(mctrl);mcl.setContentsMargins(0,0,0,0);mcl.setSpacing(4)
        self.m_motion_play_btn=W.QPushButton('▶ Play');self.m_motion_play_btn.clicked.connect(self.play_motion);self.m_motion_play_btn.setEnabled(False);mcl.addWidget(self.m_motion_play_btn)
        self.m_motion_pause_btn=W.QPushButton('|| Pause');self.m_motion_pause_btn.clicked.connect(self.pause_motion);self.m_motion_pause_btn.setEnabled(False);mcl.addWidget(self.m_motion_pause_btn)
        self.m_motion_stop_btn=W.QPushButton('■ Stop');self.m_motion_stop_btn.clicked.connect(self.stop_motion);self.m_motion_stop_btn.setEnabled(False);mcl.addWidget(self.m_motion_stop_btn)
        mcl.addStretch()
        mcl.addWidget(W.QLabel('Time:'));self.m_motion_pos=W.QLabel('0:00');mcl.addWidget(self.m_motion_pos)
        self.m_motion_slider=W.QSlider(C.Qt.Orientation.Horizontal);self.m_motion_slider.setRange(0,1000);self.m_motion_slider.setValue(0);self.m_motion_slider.setEnabled(False);self.m_motion_slider.sliderPressed.connect(self.motion_slider_pressed);self.m_motion_slider.sliderReleased.connect(self.seek_motion);mcl.addWidget(self.m_motion_slider)
        self.m_motion_dur=W.QLabel('0:00');mcl.addWidget(self.m_motion_dur)
        mpl.addWidget(mctrl);mpl.addStretch()
        tabs.addTab(motion_panel,'Motion');self.m_properties_tabs=tabs
        self.m_texture_browser=W.QListWidget();self.m_texture_browser.setViewMode(W.QListView.ViewMode.IconMode);self.m_texture_browser.setIconSize(C.QSize(64,64));self.m_texture_browser.setGridSize(C.QSize(110,100));self.m_texture_browser.setResizeMode(W.QListView.ResizeMode.Adjust);self.m_texture_browser.currentRowChanged.connect(self.browse_texture)
        dock=W.QDockWidget('Properties',self);dock.setObjectName('scene_properties');dock.setWidget(tabs);self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,dock);self.m_properties_dock=dock
        self.splitDockWidget(self.m_outliner_dock,dock,C.Qt.Orientation.Vertical)
        self.m_assets_dock=W.QDockWidget('Asset Browser — Textures',self);self.m_assets_dock.setObjectName('scene_assets');self.m_assets_dock.setWidget(self.m_texture_browser);self.addDockWidget(C.Qt.DockWidgetArea.BottomDockWidgetArea,self.m_assets_dock)
        self.m_audio_browser=W.QListWidget();self.m_audio_browser.setViewMode(W.QListView.ViewMode.IconMode);self.m_audio_browser.setIconSize(C.QSize(48,48));self.m_audio_browser.setGridSize(C.QSize(150,70));self.m_audio_browser.setResizeMode(W.QListView.ResizeMode.Adjust);self.m_audio_browser.currentRowChanged.connect(self.select_audio)
        self.m_audio_browser_info=W.QLabel('No audio');self.m_audio_browser_info.setWordWrap(True)
        self.m_audio_play=W.QPushButton('Play');self.m_audio_play.clicked.connect(self.play_audio);self.m_audio_play.setEnabled(False)
        audio_panel=W.QWidget();ap=W.QVBoxLayout(audio_panel);ap.setContentsMargins(0,0,0,0);ap.addWidget(self.m_audio_browser);ap.addWidget(self.m_audio_browser_info);ap.addWidget(self.m_audio_play)
        self.m_audio_dock=W.QDockWidget('Asset Browser — Audio',self);self.m_audio_dock.setObjectName('scene_audio');self.m_audio_dock.setWidget(audio_panel);self.addDockWidget(C.Qt.DockWidgetArea.BottomDockWidgetArea,self.m_audio_dock)
        self.setCorner(C.Qt.Corner.BottomRightCorner,C.Qt.DockWidgetArea.RightDockWidgetArea)
        self.m_file_tree=W.QTreeWidget();self.m_file_tree.setHeaderLabels(['Archive entry','Size','Format']);self.m_file_tree.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.m_file_tree.itemActivated.connect(lambda item,*_a:self.open_virtual(item.data(0,C.Qt.ItemDataRole.UserRole)))
        self.m_file_tree.header().setSectionResizeMode(0,W.QHeaderView.ResizeMode.Stretch);self.m_file_tree.header().setSectionResizeMode(1,W.QHeaderView.ResizeMode.Fixed);self.m_file_tree.header().setSectionResizeMode(2,W.QHeaderView.ResizeMode.Fixed);self.m_file_tree.setColumnWidth(1,90);self.m_file_tree.setColumnWidth(2,80)
        dock=W.QDockWidget('Archive Browser',self);dock.setObjectName('archive_browser');dock.setWidget(self.m_file_tree);self.addDockWidget(C.Qt.DockWidgetArea.LeftDockWidgetArea,dock);self.m_files_dock=dock;self.m_archive_dock=dock
        self.m_preview=W.QTextEdit();self.m_preview.setReadOnly(True);self.m_preview.setLineWrapMode(W.QTextEdit.LineWrapMode.NoWrap);self.m_preview.setFont(G.QFont('Consolas',10))
        self.m_preview_image=W.QLabel('No preview');self.m_preview_image.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_preview_stack=W.QStackedWidget();self.m_preview_stack.addWidget(self.m_preview);self.m_preview_stack.addWidget(self.m_preview_image)
        dockp=W.QDockWidget('Preview',self);dockp.setObjectName('preview_dock');dockp.setWidget(self.m_preview_stack);self.addDockWidget(C.Qt.DockWidgetArea.BottomDockWidgetArea,dockp);self.m_preview_dock=dockp
        # --- Script Viewer dock ---
        self.m_script_list=W.QListWidget();self.m_script_list.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.m_script_list.currentItemChanged.connect(self._script_selected)
        self.m_script_text=W.QTextEdit();self.m_script_text.setReadOnly(True);self.m_script_text.setLineWrapMode(W.QTextEdit.LineWrapMode.NoWrap);self.m_script_text.setFont(G.QFont('Consolas',10))
        self.m_script_decompile_cb=W.QCheckBox('Pseudocode');self.m_script_decompile_cb.setChecked(False);self.m_script_decompile_cb.stateChanged.connect(self._script_selected)
        self.m_script_edit_btn=W.QPushButton('Edit selected token');self.m_script_edit_btn.setEnabled(False);self.m_script_edit_btn.clicked.connect(self._edit_selected_token)
        self.m_script_save_btn=W.QPushButton('Save changes');self.m_script_save_btn.setEnabled(False);self.m_script_save_btn.clicked.connect(self._save_script_changes)
        script_panel=W.QWidget();sp=W.QVBoxLayout(script_panel);sp.setContentsMargins(4,4,4,4);sp.setSpacing(4)
        sp.addWidget(W.QLabel('Scripts:'));sp.addWidget(self.m_script_list,1)
        btnrow=W.QWidget();br=W.QHBoxLayout(btnrow);br.setContentsMargins(0,0,0,0);br.setSpacing(4)
        br.addWidget(self.m_script_edit_btn);br.addWidget(self.m_script_save_btn);br.addWidget(self.m_script_decompile_cb);br.addStretch()
        sp.addWidget(btnrow)
        sp.addWidget(W.QLabel('Tokens:'));sp.addWidget(self.m_script_text,2)
        docks=W.QDockWidget('Script Viewer',self);docks.setObjectName('script_viewer');docks.setWidget(script_panel);self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,docks);self.m_script_dock=docks
        # split with properties dock
        self.splitDockWidget(self.m_properties_dock,docks,C.Qt.Orientation.Vertical)
        # script state
        self.m_scripts={}   # name -> parsed SPT document
        self.m_script_text_data={}  # name -> raw text representation
        self.m_current_script=None
        self.m_current_token_path=None  # (program_idx, token_idx)
        self.build_menus()
        workspaces=self.addToolBar('Workspaces');workspaces.setObjectName('workspace_header');workspaces.setMovable(False)
        brand=W.QLabel('  ARIKA  ');brand.setObjectName('editor_heading');workspaces.addWidget(brand)
        self.m_workspaces=W.QTabBar();self.m_workspaces.setExpanding(False)
        for name in ('Layout','Shading','Textures','Object','Menu','Audio'):self.m_workspaces.addTab(name)
        self.m_workspaces.currentChanged.connect(self.workspace);workspaces.addWidget(self.m_workspaces)
        self.statusBar().setSizeGripEnabled(True);self.statusBar().showMessage('MMB orbit  |  Shift+MMB pan  |  Wheel zoom  |  Home frame all  |  Numpad . frame selected')
        self.m_selection_status=W.QLabel('0 selected');self.statusBar().addPermanentWidget(self.m_selection_status)
        self.m_scene_status=W.QLabel('No scene');self.m_scene_status.setMaximumWidth(320);self.statusBar().addPermanentWidget(self.m_scene_status)
        self.reset_layout()
        self.m_settings.restore_window(self)
        self.refresh_recent_menu()
        self.setMinimumSize(0, 0)

    def build_menus(self):
        file_menu=self.menuBar().addMenu('File')
        file_menu.addAction('Add character…').triggered.connect(self.add_character)
        file_menu.addAction('Add example Goku').triggered.connect(self.add_example_character)
        file_menu.addSeparator()
        for title,shortcut,callback in [('Open…','Ctrl+O',self.open_file),('Open archive…','',self.open_archive),('Open stage…','',self.open_stage),('Open project…','',self.open_project)]:
            action=file_menu.addAction(title);action.triggered.connect(callback)
            if shortcut:action.setShortcut(shortcut)
        self.m_recent_menu=file_menu.addMenu('Open Recent')
        self.m_recent_stages=self.m_recent_menu.addMenu('Stages')
        self.m_recent_projects=self.m_recent_menu.addMenu('Projects')
        self.m_recent_models=self.m_recent_menu.addMenu('Models')
        self.m_recent_archives=self.m_recent_menu.addMenu('Archives')
        self.m_recent_textures=self.m_recent_menu.addMenu('Textures')
        self.m_recent_sounds=self.m_recent_menu.addMenu('Sounds')
        self.m_recent_motions=self.m_recent_menu.addMenu('Motions')
        self.m_recent_menu.addSeparator()
        self.m_clear_recent_action=self.m_recent_menu.addAction('Clear Recent Files')
        self.m_clear_recent_action.triggered.connect(self.clear_recent_files)
        self.m_recent_menu.aboutToShow.connect(self.refresh_recent_menu)
        file_menu.addSeparator()
        file_menu.addAction('Import audio…').triggered.connect(self.import_audio)
        for title,shortcut,callback in [('Save project…','Ctrl+S',self.save_project),('Save STG copy…','',self.save_stage),('Export glTF…','Ctrl+E',self.export),('Exit','Alt+F4',self.close)]:
            action=file_menu.addAction(title);action.triggered.connect(callback)
            if shortcut:action.setShortcut(shortcut)
        edit=self.menuBar().addMenu('Edit')
        edit.addAction('Delete selected objects').triggered.connect(self.delete_selected)
        duplicate_action=edit.addAction('Duplicate selected (Ctrl+D)');duplicate_action.setShortcut('Ctrl+D');duplicate_action.triggered.connect(self.duplicate_selected)
        for title,shortcut,callback in [('Undo','Ctrl+Z',lambda:self.history(False)),('Redo','Ctrl+Shift+Z',lambda:self.history(True))]:
            action=edit.addAction(title);action.setShortcut(shortcut);action.triggered.connect(callback)
        window=self.menuBar().addMenu('Window')
        for dock in (self.m_outliner_dock,self.m_properties_dock,self.m_assets_dock,self.m_script_dock):window.addAction(dock.toggleViewAction())
        window.addSeparator();window.addAction('Reset layout').triggered.connect(self.reset_layout)
        help_menu=self.menuBar().addMenu('Help');help_menu.addAction('Viewport controls').triggered.connect(lambda:W.QMessageBox.information(self,'Viewport controls',self.m_view.toolTip().replace(' · ','\n')));help_menu.addAction('Format interaction map').triggered.connect(self._show_format_map)

    def add_character(self):
        if not self.m_project:
            self.statusBar().showMessage('Open a stage or editor project, then add a character.');return
        path,_=W.QFileDialog.getOpenFileName(self,'Add character model','','Character models (*.mdl *.mdt *.gltf *.glb)')
        if not path:return
        texture=None
        pix=Path(path).with_suffix('.pix')
        if Path(path).suffix.lower()=='.mdl':
            if pix.exists():texture=str(pix)
            else:
                texture,_=W.QFileDialog.getOpenFileName(self,'Optional character textures (Cancel for untextured)','','Character textures (*.pix)')
                texture=texture or None
        self.import_character(path,texture)

    def add_example_character(self):
        if not self.m_project:
            self.m_project=c_scene_project.__new__(c_scene_project)
            self.m_project.m_document={
                'asset':{'version':'2.0','generator':'Arika Editor'},
                'buffers':[],'bufferViews':[],'accessors':[],
                'images':[],'textures':[],'samplers':[],
                'materials':[],'meshes':[],'nodes':[],
                'scenes':[{'nodes':[]}],'scene':0,
            }
            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
            self.m_project.m_stage=None
        path=Path(__file__).parent/'examples/goku_action_232_native_poses.gltf'
        self.import_character(path,name='Goku',choose=False)

    def import_character(self,path,texture=None,name=None,choose=True):
        try:
            from arika_scene_characters import load_character,load_skinned_character
            W.QApplication.setOverrideCursor(C.Qt.CursorShape.WaitCursor)
            try:
                skinned=False
                try:
                    candidate=load_skinned_character(path,texture)
                    if candidate.get('skins'):
                        character=candidate;skinned=True
                    else:
                        character=load_character(path,texture)
                except Exception:
                    character=load_character(path,texture)
            finally:W.QApplication.restoreOverrideCursor()
            meshes=character['meshes'];selected=list(range(len(meshes)))
            if choose and not skinned:
                dialog=W.QDialog(self);dialog.setWindowTitle('Character mesh variants');dialog.resize(440,480);layout=W.QVBoxLayout(dialog)
                note=W.QLabel('Choose meshes to include. Alternate hands, hair or costumes may overlap. Static authored pose; no animation playback.');note.setWordWrap(True);layout.addWidget(note)
                items=W.QListWidget();layout.addWidget(items)
                for mesh in meshes:
                    item=W.QListWidgetItem(mesh.get('name','Character mesh'));item.setCheckState(C.Qt.CheckState.Checked);items.addItem(item)
                buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok|W.QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
                if dialog.exec()!=W.QDialog.DialogCode.Accepted:return
                selected=[i for i in range(items.count()) if items.item(i).checkState()==C.Qt.CheckState.Checked]
            else:
                selected=[i for i,m in enumerate(meshes) if m.get('name') not in ('MeshLHandD','MeshRHandD')]
            center=self.m_view.m_center
            index=self.m_project.add_character(character,name or Path(path).stem,selected,[center[0],0,center[2]],skinned=skinned)
            self.populate();self.select_view(index);self.m_workspaces.setCurrentIndex(3)
            if Path(path).suffix.lower()=='.mdl':self.remember_file(path,'model')
            self.clear_motion()
            # Auto-load associated motion files (same directory / stem).
            loaded=False
            try:loaded=self._auto_load_motions(path)
            except Exception:pass
            if loaded:
                self.statusBar().showMessage('Character added with motion. Unlock its root to place it.')
            elif skinned:
                self.statusBar().showMessage('Skinned character loaded with skeleton. Select the root or a bone to pose; load a motion to animate.')
            else:
                self.statusBar().showMessage('Character added in authored pose (no motion found nearby). Unlock its root to place it. Save project retains it; STG does not include character instances.')
        except Exception as error:self.fail(error)

    def _auto_load_motions(self,path):
        p=Path(path)
        candidates=[]
        # Virtual archive: search m_virtual_files for motion files.
        if getattr(self,'m_virtual_files',None):
            for name,data in self.m_virtual_files.items():
                lower=name.lower()
                if lower.endswith(('.mot2','.rfsm','.pmt')):
                    candidates.append((name,data))
            # Prefer files whose stem matches the character stem.
            stem=p.stem.lower()
            matching=[c for c in candidates if Path(c[0]).stem.lower()==stem or stem in Path(c[0]).stem.lower()]
            if matching:candidates=matching
            if candidates:
                name,data=candidates[0]
                self._open_motion(name,data,remember=False)
                return True
            return False
        # Filesystem: search same directory.
        directory=p.parent
        if directory.is_dir():
            for suffix in ('.mot2','.rfsm','.pmt'):
                for mp in sorted(directory.glob('*'+suffix)):
                    if mp.stem.lower()==p.stem.lower() or p.stem.lower() in mp.stem.lower():
                        try:
                            data=mp.read_bytes()
                            self._open_motion(str(mp),data,remember=True)
                            return True
                        except Exception:pass
            # Fallback: any motion file in the same directory.
            for suffix in ('.mot2','.rfsm','.pmt'):
                for mp in sorted(directory.glob('*'+suffix)):
                    try:
                        data=mp.read_bytes()
                        self._open_motion(str(mp),data,remember=True)
                        return True
                    except Exception:pass
            return False
    def reset_layout(self):
        for dock in (self.m_outliner_dock,self.m_properties_dock,self.m_assets_dock):dock.setFloating(False);dock.show()
        self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,self.m_outliner_dock)
        self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,self.m_properties_dock)
        self.splitDockWidget(self.m_outliner_dock,self.m_properties_dock,C.Qt.Orientation.Vertical)
        self.addDockWidget(C.Qt.DockWidgetArea.BottomDockWidgetArea,self.m_assets_dock)
        self.resizeDocks([self.m_outliner_dock,self.m_properties_dock],[330,330],C.Qt.Orientation.Horizontal)
        self.resizeDocks([self.m_outliner_dock,self.m_properties_dock],[230,570],C.Qt.Orientation.Vertical)
        self.resizeDocks([self.m_assets_dock],[145],C.Qt.Orientation.Vertical)

    def workspace(self,index):
        self.m_view_mode.setCurrentIndex(index)
        self.m_properties_tabs.setCurrentIndex(1 if index==1 else 0)
        if index==2:self.m_assets_dock.show()

    def fail(self,error):W.QMessageBox.critical(self,'Editor error',str(error))
    def discard(self):return not self.m_project or not self.m_project.m_changed or W.QMessageBox.question(self,'Unsaved project','Discard unsaved changes?')==W.QMessageBox.StandardButton.Yes

    def refresh_recent_menu(self):
        if not hasattr(self,'m_recent_stages'):return
        for menu,kind in ((self.m_recent_stages,'stage'),(self.m_recent_projects,'project'),(self.m_recent_models,'model'),(self.m_recent_archives,'archive'),(self.m_recent_textures,'texture'),(self.m_recent_sounds,'sound'),(self.m_recent_motions,'motion')):
            menu.clear()
            entries=self.m_settings.recent_files(kind)
            if not entries:
                action=menu.addAction('No recent %s files'%{'stage':'stages','project':'projects','model':'models','archive':'archives','texture':'textures','sound':'sounds','motion':'motions'}[kind])
                action.setEnabled(False)
                continue
            for entry in entries:
                path=Path(entry['path'])
                label='%s — %s'%(path.name or str(path),path.parent)
                action=menu.addAction(label)
                action.setToolTip(str(path))
                action.setStatusTip(str(path))
                action.setEnabled(path.is_file())
                if not path.is_file():action.setText(label+' (missing)')
                action.triggered.connect(lambda checked=False,path=str(path),kind=kind:self.open_recent(path,kind))
        self.m_clear_recent_action.setEnabled(bool(self.m_settings.recent_files()))

    def remember_file(self,path,kind):
        self.m_settings.add_recent_file(path,kind)
        self.m_settings.set_last_directory(kind,path)
        try:self.m_settings.save()
        except OSError as error:self.statusBar().showMessage('Could not save editor settings: '+str(error),8000)
        self.refresh_recent_menu()

    def clear_recent_files(self):
        self.m_settings.m_data['recent_files']=[]
        try:self.m_settings.save()
        except OSError as error:self.statusBar().showMessage('Could not save editor settings: '+str(error),8000)
        self.refresh_recent_menu()

    def open_recent(self,path,kind):
        if not self.discard():return
        if not Path(path).is_file():
            self.statusBar().showMessage('Recent file no longer exists: '+path,8000)
            self.refresh_recent_menu()
            return
        if kind=='model':
            self.open_recent_model(path);return
        if kind=='archive':
            self.open_recent_archive(path);return
        if kind=='texture':
            self.open_recent_texture(path);return
        if kind=='sound':
            self.open_recent_sound(path);return
        if kind=='motion':
            self.open_recent_motion(path);return
        self.load_scene_file(path,kind)

    def open_recent_model(self,path):
        from arika_scene_characters import load_character, load_skinned_character
        path=str(path)
        pix=str(Path(path).with_suffix('.pix'))
        texture=None
        if Path(path).suffix.lower()=='.mdl' and Path(pix).exists():texture=pix
        try:
            skinned=False
            try:
                candidate=load_skinned_character(path,texture)
                if candidate.get('skins'):
                    character=candidate;skinned=True
                else:
                    character=load_character(path,texture)
            except Exception:
                character=load_character(path,texture)
        except Exception as error:self.fail(error);return
        meshes=character['meshes'];selected=list(range(len(meshes)))
        center=self.m_view.m_center
        if self.m_project is None:
            self.m_project=c_scene_project.__new__(c_scene_project)
            self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
            self.m_project.m_stage=None;self.m_project.m_virtual=True;self.m_project_path=None;self.m_virtual=True
        index=self.m_project.add_character(character,Path(path).stem,selected,[center[0],0,center[2]],skinned=skinned)
        self.populate();self.select_view(index)
        try:self.m_workspaces.setCurrentIndex(3)
        except Exception:pass
        self.m_view.set_project(self.m_project,fit=True);self.m_view.frame(False)
        self.remember_file(path,'model')
        self.clear_motion()
        self.statusBar().showMessage('Opened recent model %s'%path)

    def open_recent_archive(self,path):
        path=str(path)
        self.load_archive(path)

    def open_recent_texture(self,path):
        path=str(path)
        try:self.import_texture_file(path)
        except Exception as e:self.fail(e)

    def open_recent_sound(self,path):
        path=str(path)
        try:self.import_audio_file(path)
        except Exception as e:self.fail(e)

    def open_recent_motion(self,path):
        path=str(path)
        try:data=Path(path).read_bytes()
        except Exception as error:self.fail(error);return
        self._open_motion(path,data,remember=True)

    def import_texture_file(self,path):
        if not self.m_project:
            self.m_project=c_scene_project.__new__(c_scene_project)
            self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
            self.m_project.m_stage=None;self.m_project.m_virtual=True;self.m_project_path=None;self.m_virtual=True
        index=self.m_project.import_texture(path)
        try:self.m_view.set_project(self.m_project)
        except Exception:pass
        try:self.m_object_view.set_project(self.m_project)
        except Exception:pass
        try:self.textures();self.m_texture.setCurrentIndex(index+1);self.show_texture()
        except Exception:pass
        self.refresh_texture_browser()
        try:self.m_texture_browser.setCurrentRow(index)
        except Exception:pass
        self.remember_file(path,'texture')
        self.statusBar().showMessage('Imported texture %s'%Path(path).name)

    def import_audio_file(self,path):
        if not self.m_project:
            self.m_project=c_scene_project.__new__(c_scene_project)
            self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
            self.m_project.m_stage=None;self.m_project_path=None
        index=self.m_project.import_audio(path);self.refresh_audio_browser();self.m_audio_browser.setCurrentRow(index)
        self.remember_file(path,'sound')
        self.statusBar().showMessage('Imported audio %s'%Path(path).name)

    def open_file(self):
        if not self.discard():return
        path,_=W.QFileDialog.getOpenFileName(self,'Open',self.m_settings.last_directory('stage'),'All files (*)')
        if path:self.load_file(path)

    def open_archive(self):
        if not self.discard():return
        path,_=W.QFileDialog.getOpenFileName(self,'Open archive',self.m_settings.last_directory('stage'),'Archives (INFO.DAT GAME.DAT);;All files (*)')
        if path:self.load_archive(path)
    def load_file(self,path):
        path=Path(path)
        if path.is_dir():
            info=path/'INFO.DAT';game=path/'GAME.DAT'
            if info.is_file() or game.is_file():
                return self.load_archive(info if info.is_file() else game, game if game.is_file() else None)
            self.statusBar().showMessage('No INFO.DAT/GAME.DAT in '+str(path));return
        try:
            data=path.read_bytes()
        except Exception as error:
            self.fail(error);return
        kind=detect_format(data,path.name)
        if kind=='archive':
            return self.load_archive(path)
        if kind=='project':
            return self.load_scene_file(str(path),'project')
        if kind=='stage':
            return self.load_scene_file(str(path),'stage')
        if kind=='font':
            return self.preview_font(str(path),data)
        if kind=='motion':
            return self._open_motion(str(path),data,remember=True)
        self.preview_virtual(str(path),data,kind)

    def load_archive(self,info_path,game_path=None):
        if not self.discard():return
        info_path=Path(info_path)
        if game_path is None:
            candidate=info_path.with_name('GAME.DAT' if info_path.name.upper()=='INFO.DAT' else 'INFO.DAT')
            if candidate.is_file():game_path=candidate
            else:game_path=None
        if game_path is None and info_path.name.upper()=='GAME.DAT':
            candidate=info_path.with_name('INFO.DAT')
            if candidate.is_file():game_path=info_path;info_path=candidate
        self.m_virtual_files={}
        self.m_virtual=True
        self.m_project=None
        try:
            self.m_tree.clear();self.m_items={}
        except Exception:pass
        try:
            archive = dat.Archive(str(info_path), str(game_path) if game_path else None)
            va = VirtualArchive(archive)
            va.load()
            self.m_virtual_files = va.files or {}
        except Exception as error:
            self.fail(error); return
        try:
            self.m_file_tree.blockSignals(True);self.m_file_tree.clear()
            for name in sorted(self.m_virtual_files):
                data=self.m_virtual_files[name]
                kind=detect_format(data,name)
                item=W.QTreeWidgetItem([name,'%d'%len(data),kind]);item.setData(0,C.Qt.ItemDataRole.UserRole,name)
                self.m_file_tree.addTopLevelItem(item)
            self.m_file_tree.blockSignals(False)
        except Exception:pass
        self.statusBar().showMessage('Loaded archive %s — %d entries'%(info_path.name,len(self.m_virtual_files)))
        self.m_scene_status.setText('Archive: %d entries'%len(self.m_virtual_files))
        self.remember_file(str(info_path),'archive')
        self.clear_motion()
        try:
            self._populate_scripts()
        except Exception:
            pass

    def open_virtual(self,path):
        if not self.m_virtual_files:return
        data=self.m_virtual_files.get(path)
        if data is None:
            self.statusBar().showMessage('Virtual entry not found: '+str(path));return
        kind=detect_format(data,path)
        if kind=='stage':
            try:
                project=c_scene_project.from_virtual(path,self.m_virtual_files)
            except Exception as error:
                self.fail(error);return
            self.m_project=project;self.m_project_path=None;self.m_virtual=True
            try:
                self._import_virtual_audio(path)
            except Exception:
                pass
            self.populate(True)
            self.clear_motion()
            self.statusBar().showMessage('Opened virtual stage %s'%path)
            try:
                self._show_stage_xrefs(path,data)
            except Exception:
                pass
            return
        if kind=='project':
            try:
                project=c_scene_project.load_bytes(data,path)
            except Exception as error:
                self.fail(error);return
            self.m_project=project;self.m_project_path=None;self.m_virtual=True
            self.populate(True)
            self.clear_motion()
            self.statusBar().showMessage('Opened virtual project %s'%path)
            return
        if kind=='motion':
            self._open_motion(path,data,remember=False)
            return
        if kind=='effect':
            self._preview_effect(path,data)
            return
        if kind=='animation':
            self._preview_animation(path,data)
            return
        if kind=='pose':
            self._preview_pose(path,data)
            return
        if kind=='facial':
            self._preview_facial(path,data)
            return
        if kind=='script':
            self._preview_script(path,data)
            return
        if kind=='hit':
            try:
                from arika_stages import parse_hit
                hit=parse_hit(data)
            except Exception as error:
                self.fail(error);return
            self.statusBar().showMessage('HIT: %d objects, %d polygons, %d vertices'%(len(hit['objects']),len(hit['polygons']),len(hit['vertices'])))
            self.preview_virtual(path,data,kind)
            return
        if kind=='model':
            if Path(path).name in self.m_loaded_models:
                self.statusBar().showMessage('Model already loaded: %s'%path);return
            tmp_mdl=None;tmp_pix=None
            try:
                from arika_scene_characters import load_character, load_skinned_character
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False,suffix='.mdl') as tf:
                    tf.write(data);tf.close();tmp_mdl=tf.name
                tex_data=None
                pix=str(Path(path).with_suffix('.pix'))
                pix_data=self.m_virtual_files.get(pix)
                if pix_data is None:
                    stem=Path(path).stem+'.pix'
                    for k,v in self.m_virtual_files.items():
                        if Path(k).name==stem and v is not None:pix_data=v;break
                if pix_data is not None:
                    with tempfile.NamedTemporaryFile(delete=False,suffix='.pix') as tf:
                        tf.write(pix_data);tf.close();tmp_pix=tf.name
                skinned=False
                try:
                    candidate=load_skinned_character(tmp_mdl,tmp_pix)
                    if candidate.get('skins'):
                        character=candidate;skinned=True
                    else:
                        character=load_character(tmp_mdl,tmp_pix)
                except Exception:
                    character=load_character(tmp_mdl,tmp_pix)
                meshes=character['meshes']
                dlg=W.QDialog(self);dlg.setWindowTitle('Model permutations');dlg.resize(460,400);lay=W.QVBoxLayout(dlg)
                lay.addWidget(W.QLabel('Select mesh variants (permutations) to load (unchecked stay hidden):'))
                items=W.QListWidget();items.setSelectionMode(W.QAbstractItemView.SelectionMode.NoSelection)
                for m in meshes:
                    it=W.QListWidgetItem(m.get('name') or 'mesh %d'%(items.count()+1));it.setFlags(C.Qt.ItemFlag.ItemIsEnabled|C.Qt.ItemFlag.ItemIsUserCheckable);it.setCheckState(C.Qt.CheckState.Checked);items.addItem(it)
                lay.addWidget(items)
                bb=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok|W.QDialogButtonBox.StandardButton.Cancel);bb.accepted.connect(dlg.accept);bb.rejected.connect(dlg.reject);lay.addWidget(bb)
                if dlg.exec()!=W.QDialog.DialogCode.Accepted:return
                selected=set(i for i in range(items.count()) if items.item(i).checkState()==C.Qt.CheckState.Checked)
                unchecked=set(i for i in range(items.count()) if items.item(i).checkState()!=C.Qt.CheckState.Checked)
                all_indices=list(range(len(meshes)))
                center=self.m_view.m_center
                if self.m_project is None:
                    self.m_project=c_scene_project.__new__(c_scene_project)
                    self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
                    self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                    self.m_project.m_stage=None;self.m_project.m_virtual=True;self.m_project_path=None;self.m_virtual=True
                index=self.m_project.add_character(character,Path(path).stem,all_indices,[center[0],0,center[2]],unchecked,skinned=skinned)
                self.populate();self.select_view(index)
                try:self.m_workspaces.setCurrentIndex(3)
                except Exception:pass
                self.m_view.set_project(self.m_project,fit=True);self.m_view.frame(False)
                self.m_loaded_models.add(Path(path).name)
                self.clear_motion()
                self.statusBar().showMessage('Loaded model %s (%d/%d meshes; %d hidden)'%(path,len(selected),len(meshes),len(unchecked)))
            except Exception as error:
                self.fail(error);return
            finally:
                for p in (tmp_mdl,tmp_pix):
                    if p:
                        try:os.unlink(p)
                        except Exception:pass
            return
        if kind in ('texture','image'):
            try:
                # Check if it's actually FPIX
                if data and len(data)>=4 and data[:4]==b'FPIX':
                    self.preview_virtual(path,data,'texture')
                    if self.m_project is None:
                        self.m_project=c_scene_project.__new__(c_scene_project)
                        self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
                        self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                        self.m_project.m_stage=None;self.m_project.m_virtual=True
                        self.m_project_path=None;self.m_virtual=True
                        try:self.populate(True)
                        except Exception:pass
                    try:
                        # Check if already imported
                        images=self.m_project.m_document.get('images',[])
                        if any(Path((img.get('name') or '')).name.startswith(Path(path).stem) for img in images):
                            self.refresh_texture_browser()
                            if hasattr(self,'m_view_mode'):self.m_view_mode.setCurrentIndex(2)
                            self.m_views.setCurrentIndex(2)
                            return
                    except Exception:pass
                    with tempfile.NamedTemporaryFile(delete=False,suffix='.pix') as tf:
                        tf.write(data);tf.close()
                        tpath=tf.name
                    try:
                        origname=Path(tpath).with_name(Path(path).name)
                        try:
                            os.rename(tpath, origname)
                            tpath=str(origname)
                        except Exception:pass
                        idx=self.m_project.import_texture(tpath)
                        self.refresh_texture_browser()
                        try:
                            if hasattr(self,'m_texture_browser'):self.m_texture_browser.setCurrentRow(idx)
                        except Exception:pass
                        if hasattr(self,'m_view_mode'):self.m_view_mode.setCurrentIndex(2)
                        self.m_views.setCurrentIndex(2)
                        self.statusBar().showMessage('Imported virtual texture %s'%path)
                        return
                    finally:
                        try:os.unlink(tpath)
                        except Exception:pass
                self.preview_virtual(path,data,kind)
                pix=G.QPixmap()
                if pix.loadFromData(data):
                    self.m_texture_info.setText('Virtual: %s — %d × %d'%(path,pix.width(),pix.height()))
                    self.m_texture_view.set_image(pix)
                    if hasattr(self,'m_view_mode'):
                        self.m_view_mode.setCurrentIndex(2)
                    self.m_views.setCurrentIndex(2)
                    try:
                        if self.m_project is None:
                            self.m_project=c_scene_project.__new__(c_scene_project)
                            self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
                            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                            self.m_project.m_stage=None;self.m_project.m_virtual=True
                            self.m_project_path=None;self.m_virtual=True
                            try:self.populate(True)
                            except Exception:pass
                        # Avoid reloading if already present
                        try:
                            images=self.m_project.m_document.get('images',[])
                            if any(Path((img.get('name') or '')).name==Path(path).name for img in images):
                                self.refresh_texture_browser()
                                try:
                                    if hasattr(self,'m_texture_browser'):
                                        for i in range(self.m_texture_browser.count()):
                                            item=self.m_texture_browser.item(i)
                                            if item and Path(str(item.data(C.Qt.ItemDataRole.UserRole) or '')).name==Path(path).name:
                                                self.m_texture_browser.setCurrentRow(i);break
                                except Exception:pass
                                return
                        except Exception:pass
                        with tempfile.NamedTemporaryFile(delete=False,suffix=Path(path).suffix) as tf:
                            tf.write(data);tf.close()
                            tpath=tf.name
                        try:
                            origname=Path(tpath).with_name(Path(path).name)
                            try:
                                os.rename(tpath, origname)
                                tpath=str(origname)
                            except Exception:
                                pass
                            idx=self.m_project.import_texture(tpath)
                            self.refresh_texture_browser()
                            try:
                                if hasattr(self,'m_texture_browser'):
                                    self.m_texture_browser.setCurrentRow(idx)
                            except Exception:pass
                        finally:
                            try:os.unlink(tpath)
                            except Exception:pass
                    except Exception:
                        pass
                    self.statusBar().showMessage('Showing virtual texture %s'%path)
                    return
                else:
                    # Even if can't load with QPixmap, try to import anyway
                    try:
                        if self.m_project is None:
                            self.m_project=c_scene_project.__new__(c_scene_project)
                            self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
                            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                            self.m_project.m_stage=None;self.m_project.m_virtual=True
                            self.m_project_path=None;self.m_virtual=True
                            try:self.populate(True)
                            except Exception:pass
                        try:
                            images=self.m_project.m_document.get('images',[])
                            if any(Path((img.get('name') or '')).name==Path(path).name for img in images):
                                self.refresh_texture_browser()
                                try:
                                    if hasattr(self,'m_texture_browser'):
                                        for i in range(self.m_texture_browser.count()):
                                            item=self.m_texture_browser.item(i)
                                            if item and Path(str(item.data(C.Qt.ItemDataRole.UserRole) or '')).name==Path(path).name:
                                                self.m_texture_browser.setCurrentRow(i);break
                                except Exception:pass
                                if hasattr(self,'m_view_mode'):self.m_view_mode.setCurrentIndex(2)
                                self.m_views.setCurrentIndex(2)
                                return
                        except Exception:pass
                        with tempfile.NamedTemporaryFile(delete=False,suffix=Path(path).suffix) as tf:
                            tf.write(data);tf.close()
                            tpath=tf.name
                        try:
                            origname=Path(tpath).with_name(Path(path).name)
                            try:
                                os.rename(tpath, origname)
                                tpath=str(origname)
                            except Exception:
                                pass
                            idx=self.m_project.import_texture(tpath)
                            self.refresh_texture_browser()
                            try:
                                if hasattr(self,'m_texture_browser'):
                                    self.m_texture_browser.setCurrentRow(idx)
                            except Exception:pass
                        finally:
                            try:os.unlink(tpath)
                            except Exception:pass
                        if hasattr(self,'m_view_mode'):self.m_view_mode.setCurrentIndex(2)
                        self.m_views.setCurrentIndex(2)
                        self.statusBar().showMessage('Showing virtual texture %s'%path)
                        return
                    except Exception:pass
            except Exception:
                pass
            self.preview_virtual(path,data,kind)
            return
        if kind=='audio':
            try:
                self.preview_virtual(path,data,kind)
                self.statusBar().showMessage('Virtual audio %s (%d bytes)'%(path,len(data)))
                if hasattr(self,'m_views'):
                    self.m_views.setCurrentIndex(5)
                if hasattr(self,'m_view_mode'):
                    self.m_view_mode.setCurrentIndex(5)
                try:
                    if self.m_project is None:
                        self.m_project=c_scene_project.__new__(c_scene_project)
                        self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
                        self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                        self.m_project.m_stage=None;self.m_project.m_virtual=True
                        self.m_project_path=None;self.m_virtual=True
                        try:self.populate(True)
                        except Exception:pass
                    try:
                        audios=self.m_project.m_document.get('audios',[])
                        if any(Path((a.get('name') or '')).name==Path(path).name for a in audios):
                            self.refresh_audio_browser()
                            return
                    except Exception:pass
                    with tempfile.NamedTemporaryFile(delete=False,suffix=Path(path).suffix) as tf:
                        tf.write(data);tf.close()
                        tpath=tf.name
                    try:
                        origname=Path(tpath).with_name(Path(path).name)
                        try:
                            os.rename(tpath, origname)
                            tpath=str(origname)
                        except Exception:
                            pass
                        idx=self.m_project.import_audio(tpath)
                        self.refresh_audio_browser()
                        try:self.m_audio_browser.setCurrentRow(idx)
                        except Exception:pass
                    finally:
                        try:os.unlink(tpath)
                        except Exception:pass
                except Exception:
                    pass
                return
            except Exception:
                pass
            self.preview_virtual(path,data,kind)
            return
        if kind=='gltf':
            try:
                if self.m_project is None:
                    self.m_project=c_scene_project.__new__(c_scene_project)
                    self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
                    self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                    self.m_project.m_stage=None
                    self.m_project_path=None
                    self.m_virtual=True
                with tempfile.NamedTemporaryFile(delete=False,suffix=Path(path).suffix) as tf:
                    tf.write(data);tpath=tf.name
                try:
                    self.import_character(tpath)
                    self.statusBar().showMessage('Imported virtual glTF %s'%path)
                    self.preview_virtual(path,data,kind)
                    return
                finally:
                    try:os.unlink(tpath)
                    except Exception:pass
            except Exception:
                pass
            self.preview_virtual(path,data,kind)
            return
        if kind=='font':
            self.preview_font(path,data)
            return
        self.preview_virtual(path,data,kind)

    def _import_virtual_audio(self,stage_path):
        try:
            if not self.m_project or not self.m_virtual_files:return
            p=PurePosixPath(stage_path)
            directory=str(p.parent)
            seen=set()
            imported=0
            # Try to import all audio in same directory
            for name,data in self.m_virtual_files.items():
                np=PurePosixPath(name)
                if str(np.parent)!=directory:continue
                lower=name.lower()
                if lower.endswith(('.wav','.ase','.ams')):
                    try:
                        key=name.lower()  # use full name
                        if key in seen:continue
                        seen.add(key)
                        with tempfile.NamedTemporaryFile(delete=False,suffix=Path(name).suffix) as tf:
                            tf.write(data);tf.close()
                            tpath=tf.name
                        try:
                            # For ASE/AMS, pass original name context by writing with original stem? import_audio uses path.stem/name
                            # write to temp with original name
                            origname=Path(tpath).with_name(Path(name).name)
                            try:
                                os.rename(tpath, origname)
                                tpath=str(origname)
                            except Exception:
                                pass
                            self.m_project.import_audio(tpath)
                            imported+=1
                        finally:
                            try:os.unlink(tpath)
                            except Exception:pass
                    except Exception:
                        pass
            # Also scan all directories for audio if none found
            if imported==0:
                for name,data in self.m_virtual_files.items():
                    lower=name.lower()
                    if lower.endswith(('.wav','.ase','.ams')):
                        try:
                            key=name.lower()
                            if key in seen:continue
                            seen.add(key)
                            with tempfile.NamedTemporaryFile(delete=False,suffix=Path(name).suffix) as tf:
                                tf.write(data);tf.close()
                                tpath=tf.name
                            try:
                                origname=Path(tpath).with_name(Path(name).name)
                                try:
                                    os.rename(tpath, origname)
                                    tpath=str(origname)
                                except Exception:
                                    pass
                                self.m_project.import_audio(tpath)
                                imported+=1
                            finally:
                                try:os.unlink(tpath)
                                except Exception:pass
                        except Exception:
                            pass
            try:
                self.refresh_audio_browser()
            except Exception:
                pass
        except Exception:
            pass

    def load_virtual(self,path):
        self.open_virtual(path)

    def preview_virtual(self,path,data,kind):
        try:
            self.m_preview_stack.setCurrentIndex(0)
            self.m_preview.clear()
            lines=['Entry: %s'%path,'Kind: %s'%kind,'Size: %d bytes'%len(data)]
            if kind in ('image','texture') and data:
                try:
                    pix=G.QPixmap()
                    pix.loadFromData(data)
                    if not pix.isNull():
                        self.m_preview_image.setPixmap(pix.scaled(512,512,C.Qt.AspectRatioMode.KeepAspectRatio,C.Qt.TransformationMode.SmoothTransformation))
                        self.m_preview_stack.setCurrentIndex(1)
                    else:
                        self.m_preview.setPlainText('\n'.join(lines)+'\n\n(hex preview)\n'+data[:256].hex())
                except Exception:
                    self.m_preview.setPlainText('\n'.join(lines))
            elif kind in ('text','project'):
                try:
                    text=data[:8192].decode('utf-8',errors='replace')
                    self.m_preview.setPlainText('\n'.join(lines)+'\n\n'+text)
                except Exception:
                    self.m_preview.setPlainText('\n'.join(lines)+'\n\n'+data[:256].hex())
            elif kind=='facial':
                self._preview_facial(path,data)
            elif kind=='effect':
                self._preview_effect(path,data)
            elif kind=='animation':
                self._preview_animation(path,data)
            elif kind=='pose':
                self._preview_pose(path,data)
            elif kind=='script':
                self._preview_script(path,data)
            else:
                # show hex + metadata
                try:
                    head=data[:512]
                    hexstr=' '.join('%02X'%b for b in head)
                    self.m_preview.setPlainText('\n'.join(lines)+'\n\nHex:\n'+hexstr)
                except Exception:
                    self.m_preview.setPlainText('\n'.join(lines))
            if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        except Exception as error:
            self.statusBar().showMessage(str(error))

    def preview_font(self,path,data):
        try:
            font=arika_ffon.parse_ffon(data)
        except Exception as error:
            self.fail(error);return
        self.m_font_font=font;self.m_font_data=data
        try:
            self.m_font_panel._render()
        except Exception:pass
        try:
            idx=self.m_views.indexOf(self.m_font_panel)
            if idx>=0:self.m_views.setCurrentIndex(idx)
            if hasattr(self,'m_view_mode'):self.m_view_mode.setCurrentIndex(idx)
        except Exception:pass
        info=arika_ffon.font_info_text(path,font,len(data))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('FFON font: %d glyphs, %dx%d @%dbpp, %d pages x %d cols, %d mapped'%(
            font.glyph_count,font.width,font.height,font.bits_per_pixel,
            font.page_count,font.columns_per_page,
            len(font.mapped_cells())),0)

    def _preview_effect(self,path,data):
        try:
            doc=arika_ebz.parse_ebz(data)
        except Exception as error:
            self.fail(error);return
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['Entry: %s'%path,'Kind: effect','Size: %d bytes'%len(data)]
        h=doc['header']
        lines.append('Magic: %s  Version: %d  Type: %d'%(h['magic'],h['version'],h['type']))
        lines.append('Param0: %.4f  Size field: 0x%08X'%(h['param0'],h['size_field']))
        lines.append('Count: %d'%h['count'])
        lines.append('')
        lines.append('Ref table (%d entries):'%len(doc['refs']))
        for r in doc['refs'][:32]:
            lines.append('  [%d] %s = 0x%016X'%(r['index'],r['name'],r['value']))
        if len(doc['refs'])>32:lines.append('  ... and %d more'%(len(doc['refs'])-32))
        lines.append('')
        lines.append('Entries (%d):'%len(doc['entries']))
        for e in doc['entries'][:16]:
            nz=[(i,f) for i,f in enumerate(e['fields']) if f!=0]
            if nz:
                lines.append('  Entry %d (%d nonzero):'%(e['index'],len(nz)))
                for i,f in nz[:8]:
                    fl=e['floats'][i]
                    lines.append('    f[%d]=%d (0x%08X)%s'%(i,f,f,' (%.4f)'%fl if fl is not None else ' (NaN)'))
                if len(nz)>8:lines.append('    ... and %d more'%(len(nz)-8))
        if len(doc['entries'])>16:lines.append('  ... and %d more entries'%(len(doc['entries'])-16))
        lines.append('')
        lines.append('Entries end at 0x%08X, %d trailing bytes'%(doc['entries_end'],doc['remaining']))
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('EBZ effect: %d refs, %d entries'%(len(doc['refs']),len(doc['entries'])),0)

    def _preview_animation(self,path,data):
        try:
            doc=arika_ani.parse_ani(data)
        except Exception as error:
            self.fail(error);return
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['Entry: %s'%path,'Kind: animation','Size: %d bytes'%doc['byte_size']]
        lines.append('Tracks: %d'%doc['track_count'])
        total=sum(len(t['frames']) for t in doc['tracks'])
        lines.append('Total frames: %d'%total)
        lines.append('')
        for t in doc['tracks']:
            bones=sorted(set(f['bone_index'] for f in t['frames'] if 'bone_index' in f))
            chans=sorted(set(f['channel_count'] for f in t['frames'] if 'channel_count' in f))
            lines.append('Track %d: %d frames, offset=0x%06X, bones=%s, chans=%s'%(
                t['index'],t['frame_count'],t['offset'],bones,chans))
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('ANI animation: %d tracks, %d frames'%(doc['track_count'],total),0)

    def _preview_pose(self,path,data):
        try:
            doc=arika_pas.parse_pas(data)
        except Exception as error:
            self.fail(error);return
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['Entry: %s'%path,'Kind: pose','Size: %d bytes'%doc['byte_size']]
        lines.append('Entries: %d'%doc['entry_count'])
        total_refs=sum(len(e['references']) for e in doc['entries'])
        lines.append('Total cross-refs: %d'%total_refs)
        lines.append('')
        for e in doc['entries'][:32]:
            if e['size']==0:
                lines.append('Entry %d: null'%e['index'])
            else:
                refs=[r['target_index'] for r in e['references']]
                lines.append('Entry %d: offset=0x%04X size=%d refs=%s'%(e['index'],e['file_offset'],e['size'],refs[:16]))
        if len(doc['entries'])>32:lines.append('... and %d more entries'%(len(doc['entries'])-32))
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('PAS pose: %d entries, %d refs'%(doc['entry_count'],total_refs),0)

    def _preview_script(self,path,data):
        try:
            doc=arika_spt.parse(data)
        except Exception as error:
            self.fail(error);return
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['Entry: %s'%path,'Kind: script','Size: %d bytes'%len(data)]
        lines.append('Programs: %d'%len(doc['programs']))
        lines.append('')
        for p in doc['programs'][:16]:
            lines.append('Program %d: size=%d vars=%d entry_points=%s tokens=%d'%(
                p['index'],p['size'],p['variable_count'],p['entry_points'],len(p['tokens'])))
            for tok in p['tokens'][:6]:
                if tok['type']==0:desc='float 0x%08X'%tok['payload']
                elif tok['type']==1:desc='string '+repr(tok.get('text',''))
                elif tok['type']==2:desc='cmd 0x%04X'%(tok.get('command_id',0))
                elif tok['type']==3:desc='var idx=%d type=%d'%(tok.get('variable_index',0),tok.get('variable_type',0))
                elif tok['type']==4:desc='sym %r'%tok.get('symbol',None)
                else:desc='type %d'%tok['type']
                lines.append('  [0x%04X] type=%d %s'%(tok['offset'],tok['type'],desc))
            if len(p['tokens'])>6:lines.append('    ... and %d more tokens'%(len(p['tokens'])-6))
        if len(doc['programs'])>16:lines.append('... and %d more programs'%(len(doc['programs'])-16))
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('SPT script: %d programs'%len(doc['programs']),0)

    def _preview_facial(self,path,data):
        try:
            doc=arika_cht.parse_cht(data)
        except Exception as error:
            self.fail(error);return
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['Entry: %s'%path,'Kind: facial','Size: %d bytes'%doc['byte_size']]
        if 'entries' in doc:
            lines.append('Entries: %d'%len(doc['entries']))
            total_frames=sum(len(e.get('frames',[])) for e in doc['entries'])
            lines.append('Total frames: %d'%total_frames)
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('CHT facial: %d bytes'%(doc['byte_size']),0)

    def _show_stage_xrefs(self,path,data):
        """Show which other format files a STG stage references."""
        try:
            doc=arika_stages.parse_stg(data)
        except Exception as error:
            self.fail(error);return
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['Entry: %s'%path,'Kind: stage','Size: %d bytes'%len(data)]
        lines.append('Nodes: %d  Roots: %d'%(len(doc['nodes']),len(doc['roots'])))
        lines.append('Effect root node index: %d  Stage root node index: %d'%(doc['effect_root'],doc['stage_root']))
        lines.append('')
        # Find effect nodes under EFFECT root
        effect_nodes=[n for n in doc['nodes'] if n['name'].startswith('ef') and n['kind']==1]
        if effect_nodes:
            lines.append('Effect placement nodes (%d):'%len(effect_nodes))
            for n in effect_nodes:
                lines.append('  %s  TRS=(%.1f,%.1f,%.1f)  links=0x%02X'%(
                    n['name'],n['translation'][0],n['translation'][1],n['translation'][2],n['links']))
            lines.append('')
        # Find HIT references (kind=3 nodes with references)
        hit_refs=[n for n in doc['nodes'] if n.get('references')]
        if hit_refs:
            lines.append('HIT collision references (%d nodes):'%len(hit_refs))
            for n in hit_refs:
                ref_names=[r['name'] for r in n['references']]
                lines.append('  %s -> %s'%(n['name'],ref_names))
            lines.append('')
        # Find state control nodes (kind=6) - reference other named nodes
        state_nodes=[n for n in doc['nodes'] if 'state_control' in n]
        if state_nodes:
            lines.append('State control nodes (%d):'%len(state_nodes))
            for n in state_nodes:
                sc=n['state_control']
                lines.append('  %s -> primary=%s secondary=%s handler=%d'%(
                    n['name'],sc['primary_name'],sc['secondary_name'],sc['handler_index']))
            lines.append('')
        lines.append('Format interaction map:')
        lines.append('  STG -> .ebz (effects under EFFECT root)')
        lines.append('  STG -> .hit (collision via kind=3 nodes)')
        lines.append('  STG -> .mdl (stage geometry under STAGE root)')
        lines.append('  STG -> .spt (stage scripts via state_control handlers)')
        lines.append('  STG -> .ams (stage music/audio)')
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('STG stage: %d nodes, %d effect nodes'%(len(doc['nodes']),len(effect_nodes)),0)

    def _show_format_map(self):
        """Show how all file formats interact with each other."""
        self.m_preview_stack.setCurrentIndex(0)
        self.m_preview.clear()
        lines=['=== SUPER DRAGON BALL Z — Format Interaction Map ===']
        lines.append('')
        lines.append('ARCHIVE CONTAINERS:')
        lines.append('  GAME.DAT — main game data (FPIX container)')
        lines.append('  INFO.DAT — metadata/index archive')
        lines.append('')
        lines.append('STAGE (STG):')
        lines.append('  .stg — scene graph with EFFECT and STAGE roots')
        lines.append('    -> .ebz  effect instances (efXX nodes under EFFECT root)')
        lines.append('    -> .hit  collision geometry (kind=3 node references)')
        lines.append('    -> .mdl  stage geometry (under STAGE root)')
        lines.append('    -> .spt  stage scripts (state_control handlers)')
        lines.append('    -> .ams  stage music/audio')
        lines.append('')
        lines.append('MODEL (MDL/FMDL):')
        lines.append('  .mdl — vertex buffers, indices, materials, skeletons')
        lines.append('    -> .pix  textures (via material slots)')
        lines.append('    -> .pmt  material definitions (RFSML3 motion archives)')
        lines.append('    -> .ani  skeletal animation tracks')
        lines.append('    -> .cht  facial animation data')
        lines.append('    -> .ase  character voice/sound banks')
        lines.append('    -> .pas  pose data')
        lines.append('')
        lines.append('EFFECT (EBZ):')
        lines.append('  .ebz — effect/trajectory archives')
        lines.append('    Ref table: named effect entries (e00006p0, se00028b, etc.)')
        lines.append('    Entries: per-instance transform data (TRS, scale, angles)')
        lines.append('    Referenced by: STG effect nodes (efXX)')
        lines.append('')
        lines.append('TEXTURE (PIX/FPIX):')
        lines.append('  .pix — FPIX container with XPIX/TIM2 texture chunks')
        lines.append('    Referenced by: MDL materials, stage geometry')
        lines.append('')
        lines.append('AUDIO:')
        lines.append('  .ase — ADPCM sound banks (character voices, effects)')
        lines.append('  .ams — sound sequence/music tracks')
        lines.append('    Referenced by: MDL characters (.ase), STG stages (.ams)')
        lines.append('')
        lines.append('SCRIPT (SPT):')
        lines.append('  .spt — tokenized bytecode programs')
        lines.append('    Referenced by: STG stage scripts (state_control handlers)')
        lines.append('')
        lines.append('POSE (PAS):')
        lines.append('  .pas — pose data with cross-references')
        lines.append('    Referenced by: MDL characters, STG stages')
        lines.append('')
        lines.append('FACIAL (CHT):')
        lines.append('  .cht — facial animation/track data')
        lines.append('    Referenced by: MDL characters')
        lines.append('')
        lines.append('FONT (FFON):')
        lines.append('  .fon — glyph atlas, character maps, font metrics')
        lines.append('')
        self.m_preview.setPlainText('\n'.join(lines))
        if hasattr(self,'m_preview_dock') and self.m_preview_dock.isHidden():self.m_preview_dock.show()
        self.statusBar().showMessage('Format interaction map shown',0)

    # ----- Script Viewer methods -----
    def _populate_scripts(self):
        """Fill the script list from the archive or project."""
        self.m_script_list.clear()
        self.m_scripts={}
        if self.m_virtual_files:
            for name in sorted(self.m_virtual_files):
                if name.lower().endswith('.spt'):
                    data=self.m_virtual_files[name]
                    try:
                        doc=arika_spt.parse(data)
                        self.m_scripts[name]=doc
                        item=W.QListWidgetItem(name)
                        item.setData(C.Qt.ItemDataRole.UserRole,name)
                        self.m_script_list.addItem(item)
                    except Exception:
                        pass
        elif self.m_project:
            # scripts embedded in project are not separately tracked; skip
            pass
        if self.m_script_list.count()>0:
            self.m_script_list.setCurrentRow(0)

    def _script_selected(self,current=None,previous=None):
        """Show token details for the selected script."""
        self.m_script_text.clear()
        self.m_script_edit_btn.setEnabled(False)
        self.m_script_save_btn.setEnabled(False)
        self.m_current_script=None
        self.m_current_token_path=None
        if not isinstance(current, W.QListWidgetItem):
            current=self.m_script_list.currentItem()
        if not current:
            return
        name=current.data(C.Qt.ItemDataRole.UserRole)
        doc=self.m_scripts.get(name)
        if not doc:
            return
        self.m_current_script=name
        self.m_script_edit_btn.setEnabled(True)
        if self.m_script_decompile_cb.isChecked():
            # Show decompiled pseudocode
            try:
                pseudo=arika_spt.decompile(Path(name).read_bytes() if Path(name).is_file() else self.m_virtual_files.get(name,b''))
            except Exception:
                # Try reading from virtual files
                data=self.m_virtual_files.get(name,b'') if self.m_virtual_files else b''
                try:
                    pseudo=arika_spt.decompile(data)
                except Exception as e2:
                    self.m_script_text.setPlainText('Decompile error: %s'%e2)
                    return
            lines=['Script: %s'%name,'Pseudocode decompilation']
            lines.append('')
            for p in pseudo.get('programs',[]):
                lines.append('// Program %d (vars=%d, entries=%s)'%(
                    p['index'],p['variable_count'],p['entry_points']))
                for line in p['lines']:
                    lines.append(line)
                lines.append('')
            self.m_script_text.setPlainText('\n'.join(lines))
        else:
            # Show raw tokens
            lines=['Script: %s'%name,'Format: %s'%doc.get('format','ARIKA_SPT'),'Programs: %d'%len(doc.get('programs',[]))]
            lines.append('')
            for p in doc.get('programs',[]):
                lines.append('Program %d:'%p['index'])
                lines.append('  size=%d  reserved=%d  vars=%d  bytecode_size=%d  entry_points=%s'%(
                    p['size'],p['reserved'],p['variable_count'],p['bytecode_size'],p['entry_points']))
                lines.append('  Tokens (%d):'%len(p.get('tokens',[])))
                for ti,tok in enumerate(p.get('tokens',[])):
                    desc=self._token_desc(tok)
                    lines.append('    [%d] off=0x%04X type=%d %s'%(ti,tok['offset'],tok['type'],desc))
                lines.append('')
            self.m_script_text.setPlainText('\n'.join(lines))

    def _token_desc(self,tok):
        t=tok['type']
        if t==0: return 'float 0x%08X'%tok['payload']
        if t==1: return 'string %r'%tok.get('text','')
        if t==2: return 'cmd 0x%04X extra=%s'%(tok.get('command_id',0),tok.get('extra_hex',''))
        if t==3: return 'var idx=%d type=%d'%(tok.get('variable_index',0),tok.get('variable_type',0))
        if t==4: return 'sym %r'%tok.get('symbol',None)
        return 'type %d payload 0x%08X'%(t,tok['payload'])

    def _edit_selected_token(self):
        """Placeholder for token editing - opens a dialog to modify a token value."""
        W.QMessageBox.information(self,'Script Editor','Token editing is not yet implemented.\nUse the SPT rebuild tool (arika_scripts.py import-json) to modify scripts externally.')

    def _save_script_changes(self):
        """Placeholder for saving modified script."""
        W.QMessageBox.information(self,'Script Editor','Save is not yet implemented.\nUse the SPT rebuild tool (arika_scripts.py import-json) to modify scripts externally.')

    def load_scene_file(self,path,kind,remember=True):
        try:
            absolute=str(Path(path).expanduser().resolve())
            if kind=='project':
                project=c_scene_project.load(absolute)
                project_path=absolute
            elif kind=='stage':
                project=c_scene_project(absolute)
                project_path=None
            else:
                raise ValueError('Unknown scene file type: '+str(kind))
            self.m_project=project;self.m_project_path=project_path;self.m_virtual=False
            self.populate(True)
            self.clear_motion()
            if remember:self.remember_file(absolute,kind)
            self.statusBar().showMessage('Opened '+absolute)
            if kind=='stage':
                try:
                    self._show_stage_xrefs(str(path),data)
                except Exception:
                    pass
        except Exception as error:
            self.fail(error)
        try:
            absolute=str(Path(path).expanduser().resolve())
            if kind=='project':
                project=c_scene_project.load(absolute)
                project_path=absolute
            elif kind=='stage':
                project=c_scene_project(absolute)
                project_path=None
            else:
                raise ValueError('Unknown scene file type: '+str(kind))
            self.m_project=project;self.m_project_path=project_path;self.m_virtual=False
            self.populate(True)
            self.clear_motion()
            if remember:self.remember_file(absolute,kind)
            self.statusBar().showMessage('Opened '+absolute)
        except Exception as error:
            self.fail(error)

    def open_stage(self):
        if not self.discard():return
        path,_=W.QFileDialog.getOpenFileName(self,'Open stage',self.m_settings.last_directory('stage'),'Stage (*.stg)')
        if path:self.load_scene_file(path,'stage')

    def open_project(self):
        if not self.discard():return
        path,_=W.QFileDialog.getOpenFileName(self,'Open project',self.m_settings.last_directory('project'),'Arika project (*.arika-scene.json)')
        if path:self.load_scene_file(path,'project')
    def sync_outliner_scrollbar(self):
        if not hasattr(self,'m_tree_hscroll') or not hasattr(self,'m_tree'):
            return
        native=self.m_tree.horizontalScrollBar()
        visible_width=max(1,self.m_tree.viewport().width()-c_outliner_pinned_columns.TOTAL_WIDTH)
        self.m_tree_hscroll.setRange(native.minimum(),native.maximum())
        self.m_tree_hscroll.setPageStep(visible_width)
        self.m_tree_hscroll.setSingleStep(max(1,native.singleStep()))
        self.m_tree_hscroll.setValue(native.value())
        if self.m_tree_hscroll.width()!=visible_width:
            self.m_tree_hscroll.setFixedWidth(visible_width)

    def populate(self,fit=False):
        previous=set(self.m_view.m_selection) if not fit else set();active=self.m_index
        self.m_tree.blockSignals(True);self.m_tree.clear();self.m_items={};doc=self.m_project.m_document
        self.m_scene_status.setText('%d objects | %d materials | %d textures | %d audio'%(len(doc.get('nodes',[])),len(doc.get('materials',[])),len(doc.get('textures',[])),len(doc.get('audios',[]))))
        def item(index,parent):
            node=doc['nodes'][index];out=W.QTreeWidgetItem(parent,[node.get('name','Node %d'%index)]);out.setData(0,C.Qt.ItemDataRole.UserRole,index);self.m_items[index]=out
            state=node_state(doc,index);out.setData(1,SHOW_ROLE,not state['hidden']);out.setData(2,LOCK_ROLE,state['locked'])
            out.setTextAlignment(1,C.Qt.AlignmentFlag.AlignRight|C.Qt.AlignmentFlag.AlignVCenter);out.setTextAlignment(2,C.Qt.AlignmentFlag.AlignRight|C.Qt.AlignmentFlag.AlignVCenter)
            out.setToolTip(1,'Checked: visible. Toggle a group to affect its descendants.');out.setToolTip(2,'Checked: transform locked. Uncheck to edit. Groups affect descendants.')
            for child in node.get('children',[]):item(child,out)
        for root in doc['scenes'][doc.get('scene',0)]['nodes']:item(root,self.m_tree)
        self.m_tree.clearSelection();self.m_tree.setCurrentItem(None)
        for index in previous:
            if index in self.m_items:self.m_items[index].setSelected(True)
        if active in previous and active in self.m_items:self.m_tree.setCurrentItem(self.m_items[active],0,C.QItemSelectionModel.SelectionFlag.NoUpdate)
        self.m_tree.blockSignals(False);self.m_tree.expandToDepth(1);self.m_tree_expanded=False
        self.m_tree.schedule_outliner_layout()
        if hasattr(self,'m_tree_toggle_button'):self.m_tree_toggle_button.setText('+')
        self.m_materials.blockSignals(True);self.m_materials.clear()
        for i,m in enumerate(doc['materials']):self.m_materials.addItem('%d — %s'%(i,m.get('name','Material')))
        self.m_materials.blockSignals(False);self.m_view.set_project(self.m_project,fit);self.m_object_view.set_project(self.m_project,True);self.m_index=None;self.m_material=-1;self.m_audio=-1;self.refresh_texture_browser();self.refresh_audio_browser()
        if fit:self.m_view.m_isolated=None
        if doc['materials']:self.m_materials.setCurrentRow(0)
        self.sync_selection()
    def select_view(self,index,additive=False):
        self.m_tree.blockSignals(True)
        if not additive:self.m_tree.clearSelection()
        if index in self.m_items:
            item=self.m_items[index];item.setSelected(not item.isSelected() if additive else True)
            self.m_tree.setCurrentItem(item,0,C.QItemSelectionModel.SelectionFlag.NoUpdate);self.m_tree.scrollToItem(item)
        self.m_tree.blockSignals(False);self.sync_selection()

    def select_all(self,select=True):
        view=self.active_view();scope=selection_nodes(self.m_project.m_document,view.m_isolated) if self.m_project and view.m_isolated is not None else None
        self.m_tree.blockSignals(True)
        for index,item in self.m_items.items():item.setSelected(select and (scope is None or index in scope))
        self.m_tree.blockSignals(False);self.sync_selection()

    def sync_selection(self):
        selected=self.m_tree.selectedItems();current=self.m_tree.currentItem()
        if current not in selected:current=selected[-1] if selected else None
        self.m_view.m_selection={item.data(0,C.Qt.ItemDataRole.UserRole) for item in selected}
        self.m_view.m_selected=current.data(0,C.Qt.ItemDataRole.UserRole) if current else -1
        changed=self.m_object_view.m_isolated!=self.m_view.m_selection
        self.m_object_view.m_selection=set(self.m_view.m_selection);self.m_object_view.m_selected=self.m_view.m_selected;self.m_object_view.m_isolated=set(self.m_view.m_selection)
        if changed:self.m_object_view.frame()
        self.m_object_view.request_draw()
        self.m_selection_status.setText('%d selected'%len(selected));self.m_view.request_draw()
        self.select_tree(current,None)

    def select_tree(self,current,previous):
        if not current or not self.m_project:
            self.m_index=None;self.m_label.setText('Select an object');self.m_object_materials.clear()
            for field in self.m_fields:field.setEnabled(False)
            self.m_apply_transform.setEnabled(False)
            return
        index=current.data(0,C.Qt.ItemDataRole.UserRole);self.m_index=index
        node=self.m_project.m_document['nodes'][index];count=len(self.m_view.m_selection);name=node.get('name','Object')
        locked=node_state(self.m_project.m_document,index)['locked'];values=self.m_project.node_transform_values(index);editable=values is not None
        self.m_label.setText(('%d selected — Active: '%count if count>1 else '')+name+(' [Locked]' if locked else ''))
        self.m_label.setWordWrap(True);self.m_label.setToolTip('Transform fields and the viewport gizmo edit the active object. Numpad . frames the entire selection.')
        axis_locks=transform_locks(self.m_project.m_document,index)
        for field_index,(field,value) in enumerate(zip(self.m_fields,values if editable else [0]*9)):
            field.setValue(value);component=field_index//3;axis=field_index%3;component_name=('location','rotation','scale')[component]
            field.setEnabled(editable and not axis_locks[component_name][axis]);field.setReadOnly(locked or axis_locks[component_name][axis])
        for field_index,check in self.m_axis_lock_checks.items():
            component=field_index//3;axis=field_index%3;component_name=('location','rotation','scale')[component]
            check.blockSignals(True);check.setChecked(axis_locks[component_name][axis]);check.setEnabled(editable and not locked);check.blockSignals(False)
        self.m_apply_transform.setEnabled(editable and not locked)
        self.m_object_materials.blockSignals(True);self.m_object_materials.clear()
        if 'mesh'in node:
            for part in self.m_project.m_document['meshes'][node['mesh']]['primitives']:
                i=part.get('material',-1)
                if i>=0:self.m_object_materials.addItem('Material %d'%i,i)
        self.m_object_materials.blockSignals(False);self.select_object_material(0)
    def select_object_material(self,index):
        material=self.m_object_materials.itemData(index)
        if material is not None:self.m_materials.setCurrentRow(material)
    def filter_tree(self,text):
        query=text.casefold()
        def walk(item):
            child_matches=[walk(item.child(i)) for i in range(item.childCount())];matched=query in item.text(0).casefold() or any(child_matches)
            item.setHidden(not matched)
            if query and any(child_matches):item.setExpanded(True)
            return matched
        for i in range(self.m_tree.topLevelItemCount()):walk(self.m_tree.topLevelItem(i))
        self.m_tree.schedule_outliner_layout()
    def apply_transform(self):
        if self.m_index is None:return
        if node_state(self.m_project.m_document,self.m_index)['locked']:
            self.statusBar().showMessage('Object is locked. Uncheck Lock in the Outliner to edit transforms.');return
        try:
            from arika_scene_state import transform_locks
            current=self.m_project.node_transform_values(self.m_index);locks=transform_locks(self.m_project.m_document,self.m_index)
            values=[current[i] if locks[('location','rotation','scale')[i//3]][i%3] else f.value() for i,f in enumerate(self.m_fields)]
            self.m_project.transform_node(self.m_index,values)
            self.m_view.set_project(self.m_project,geometry=False);self.m_object_view.set_project(self.m_project,geometry=False);self.sync_selection()
        except Exception as e:self.fail(e)

    def set_axis_transform_lock(self,component,axis,locked):
        if not self.m_project or self.m_index is None:return
        if node_state(self.m_project.m_document,self.m_index)['locked']:return
        try:
            self.m_project.set_transform_lock(self.m_index,('location','rotation','scale')[component],axis,bool(locked))
            self.sync_selection()
        except Exception as error:self.fail(error)

    def node_state_changed(self,item,column):
        if column not in (1,2) or not self.m_project:return
        index=item.data(0,C.Qt.ItemDataRole.UserRole)
        role=SHOW_ROLE if column==1 else LOCK_ROLE
        value=bool(item.data(column,role))
        self.change_node_state(indices={index},**({'hidden':not value} if column==1 else {'locked':value}))

    def change_node_state(self,indices=None,**state):
        if not self.m_project:return
        targets=self.m_view.m_selection if indices is None else indices
        if not targets:return
        self.m_project.set_node_state(targets,**state)
        for view in (self.m_view,self.m_material_view,self.m_object_view):
            r=getattr(view,'m_renderer',None)
            if r is not None:r.m_hidden=hidden_nodes(self.m_project.m_document)
        self.m_tree.blockSignals(True)
        for index,item in self.m_items.items():
            flags=node_state(self.m_project.m_document,index)
            item.setData(1,SHOW_ROLE,not flags['hidden']);item.setData(2,LOCK_ROLE,flags['locked'])
        self.m_tree.blockSignals(False);self.sync_selection();self.m_object_view.request_draw()

    def show_all_objects(self):self.change_node_state(indices=set(self.m_items),hidden=False)

    def toggle_tree_expand(self):
        if getattr(self,'m_tree_expanded',False):
            self.m_tree.collapseAll();self.m_tree_expanded=False
            if hasattr(self,'m_tree_toggle_button'):self.m_tree_toggle_button.setText('+')
        else:
            self.m_tree.expandAll();self.m_tree_expanded=True
            if hasattr(self,'m_tree_toggle_button'):self.m_tree_toggle_button.setText('-')
    def duplicate_selected(self):
        if not self.m_project or not self.m_view.m_selection:return
        try:result=self.m_project.duplicate_nodes(self.m_view.m_selection)
        except ValueError as error:
            self.statusBar().showMessage(str(error));return
        new_indices=list(result.get('new_indices') or result.get('new') or result.get('indices') or [])
        self.m_view.m_selection=set(new_indices)
        self.m_view.m_selected=new_indices[-1] if new_indices else -1
        self.m_index=None
        self.populate()
        self.statusBar().showMessage('Duplicated %d objects.'%result.get('count',len(new_indices)))

    def reparent_selected(self,parent):
        if not self.m_project or not self.m_view.m_selection:return
        try:result=self.m_project.reparent_nodes(self.m_view.m_selection,parent)
        except ValueError as error:
            self.statusBar().showMessage(str(error));return
        self.populate()
        self.statusBar().showMessage('Reparented %d objects.'%result.get('count',0))

    def delete_selected(self):
        if not self.m_project or not self.m_view.m_selection:return
        try:result=self.m_project.delete_nodes(self.m_view.m_selection)
        except ValueError as error:
            self.statusBar().showMessage(str(error));return
        self.m_view.m_selection=set();self.m_view.m_selected=-1;self.m_index=None
        if self.m_view.m_isolated is not None:self.m_view.m_isolated={result['remap'][i] for i in self.m_view.m_isolated if i in result['remap']}
        self.populate()
        self.statusBar().showMessage('Deleted %d objects from editor scene. Ctrl+Z undoes. Save project/glTF retains deletions; native STG is unchanged.'%result['count'])

    def object_menu(self,point):
        item=self.m_tree.itemAt(point)
        if item and not item.isSelected():self.select_view(item.data(0,C.Qt.ItemDataRole.UserRole))
        menu=W.QMenu(self)
        for title,state in [('Hide selected',dict(hidden=True)),('Show selected',dict(hidden=False)),('Lock selected',dict(locked=True)),('Unlock selected',dict(locked=False))]:
            action=menu.addAction(title);action.setEnabled(bool(self.m_view.m_selection));action.triggered.connect(lambda _=False,state=state:self.change_node_state(**state))
        action=menu.addAction('Delete selected (Delete / X)');action.setEnabled(bool(self.m_view.m_selection));action.triggered.connect(self.delete_selected)
        action=menu.addAction('Duplicate selected (Ctrl+D)');action.setEnabled(bool(self.m_view.m_selection));action.triggered.connect(self.duplicate_selected)
        menu.addSeparator();menu.addAction('Show all objects').triggered.connect(self.show_all_objects)
        menu.addAction('Lock all objects').triggered.connect(lambda:self.change_node_state(indices=set(self.m_items),locked=True))
        menu.exec(self.m_tree.viewport().mapToGlobal(point))
    def textures(self):
        self.m_texture.blockSignals(True);self.m_texture.clear();self.m_texture.addItem('No texture',-1)
        for i,t in enumerate(self.m_project.m_document.get('textures',[])):
            image=self.m_project.m_document['images'][t['source']];self.m_texture.addItem('%d — %s'%(i,image.get('name','PIX texture')),i)
        self.m_texture.blockSignals(False)
    def select_material(self,index):
        if not self.m_project or index<0:return
        self.m_material=index;mat=self.m_project.m_document['materials'][index];pbr=mat.get('pbrMetallicRoughness',{});self.m_color=list(pbr.get('baseColorFactor',[1,1,1,1]))
        self.textures();self.m_texture.setCurrentIndex(pbr.get('baseColorTexture',{}).get('index',-1)+1)
        self.m_alpha.setCurrentText(mat.get('alphaMode','OPAQUE'));self.m_double.setChecked(mat.get('doubleSided',True));self.show_texture()
        if self.m_views.currentIndex()==1:self.refresh_material_preview()
    def show_texture(self,*args):
        if not self.m_project:return
        i=self.m_texture.currentData()
        if i is None or i<0:self.m_thumbnail.setText('No texture');return
        image=self.m_project.m_document['images'][self.m_project.m_document['textures'][i]['source']];pix=G.QPixmap();pix.loadFromData(base64.b64decode(image['uri'].split(',',1)[1]))
        self.m_thumbnail.setPixmap(pix.scaled(250,140,C.Qt.AspectRatioMode.KeepAspectRatio,C.Qt.TransformationMode.SmoothTransformation))
    def choose_color(self):
        color=W.QColorDialog.getColor(G.QColor.fromRgbF(*self.m_color),self,'Base color',W.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():self.m_color=[color.redF(),color.greenF(),color.blueF(),color.alphaF()]
    def apply_material(self):
        if self.m_material<0:return
        try:
            self.m_project.material(self.m_material,self.m_texture.currentData(),self.m_color,self.m_alpha.currentText(),self.m_double.isChecked());self.m_view.set_project(self.m_project,geometry=False);self.m_object_view.set_project(self.m_project,geometry=False)
            if self.m_views.currentIndex()==1:self.refresh_material_preview()
        except Exception as e:self.fail(e)
    def import_texture(self):
        if not self.m_project:
            self.m_project=c_scene_project.__new__(c_scene_project)
            self.m_project.m_document={'asset':{'version':'2.0','generator':'Arika Editor'},'buffers':[],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[],'materials':[],'meshes':[],'nodes':[],'scenes':[{'nodes':[]}],'scene':0}
            self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
            self.m_project.m_stage=None;self.m_project.m_virtual=True
            self.m_project_path=None;self.m_virtual=True
        path,_=W.QFileDialog.getOpenFileName(self,'Import texture','','Images (*.png *.bmp *.jpg *.tga *.tif *.pix *.FPIX)')
        if path:
            try:
                if getattr(self,'m_virtual_files',None):
                    name=Path(path).name
                    if name in self.m_virtual_files:
                        data=self.m_virtual_files[name]
                        p=Path(path)
                        with tempfile.NamedTemporaryFile(delete=False,suffix=p.suffix) as tf:
                            tf.write(data);tf.close()
                            tpath=tf.name
                        try:
                            origname=Path(tpath).with_name(p.name)
                            try:
                                os.rename(tpath, origname)
                                tpath=str(origname)
                            except Exception:pass
                            index=self.m_project.import_texture(tpath)
                            try:self.m_view.set_project(self.m_project)
                            except Exception:pass
                            try:self.m_object_view.set_project(self.m_project)
                            except Exception:pass
                            try:self.textures();self.m_texture.setCurrentIndex(index+1);self.show_texture()
                            except Exception:pass
                            self.refresh_texture_browser()
                            try:self.m_texture_browser.setCurrentRow(index)
                            except Exception:pass
                            self.statusBar().showMessage('Imported texture %s'%p.name)
                            self.remember_file(str(path),'texture')
                            return
                        finally:
                            try:os.unlink(tpath)
                            except Exception:pass
                index=self.m_project.import_texture(path)
                try:self.m_view.set_project(self.m_project)
                except Exception:pass
                try:self.m_object_view.set_project(self.m_project)
                except Exception:pass
                try:self.textures();self.m_texture.setCurrentIndex(index+1);self.show_texture()
                except Exception:pass
                self.refresh_texture_browser()
                try:self.m_texture_browser.setCurrentRow(index)
                except Exception:pass
                self.statusBar().showMessage('Imported texture %s'%Path(path).name)
                self.remember_file(path,'texture')
            except Exception as e:self.fail(e)
    def import_audio(self):
        path,_=W.QFileDialog.getOpenFileName(self,'Import audio','','Audio (*.wav *.ase *.ams)')
        if not path:return
        try:
            if not self.m_project:
                self.m_project=c_scene_project.__new__(c_scene_project)
                self.m_project.m_document={
                    'asset':{'version':'2.0','generator':'Arika Editor'},
                    'buffers':[],'bufferViews':[],'accessors':[],
                    'images':[],'textures':[],'samplers':[],
                    'materials':[],'meshes':[],'nodes':[],
                    'scenes':[{'nodes':[]}],'scene':0,
                }
                self.m_project.m_history=[];self.m_project.m_future=[];self.m_project.m_changed=False
                self.m_project.m_stage=None
                self.m_project_path=None
            index=self.m_project.import_audio(path);self.refresh_audio_browser();self.m_audio_browser.setCurrentRow(index)
            self.statusBar().showMessage('Imported audio %s'%Path(path).name)
            self.remember_file(path,'sound')
        except Exception as e:self.fail(e)
    def refresh_audio_browser(self):
        self.m_audio_browser.blockSignals(True);self.m_audio_browser.clear()
        for i,a in enumerate(self.m_project.m_document.get('audios',[])):
            item=W.QListWidgetItem('%s\n%d Hz · %dch · %d frames'%(a.get('name','Audio'),a.get('sampleRate',0),a.get('channels',0),a.get('frames',0)));item.setData(C.Qt.ItemDataRole.UserRole,i);self.m_audio_browser.addItem(item)
        self.m_audio_browser.blockSignals(False)
    def select_audio(self,index):
        item=self.m_audio_browser.item(index) if index>=0 else None
        self.m_audio=item.data(C.Qt.ItemDataRole.UserRole) if item is not None else -1
        if not self.m_project or self.m_audio<0:
            self.m_audio_browser_info.setText('No audio');self.m_audio_play.setEnabled(False);return
        a=self.m_project.m_document['audios'][self.m_audio]
        self.m_audio_browser_info.setText('%s\n%d Hz · %d channel(s) · %d frames (%.2f s)'%(a.get('name','Audio'),a.get('sampleRate',0),a.get('channels',0),a.get('frames',0),a.get('frames',0)/max(1,a.get('sampleRate',1))))
        self.m_audio_play.setEnabled(True)
    def play_audio(self):
        if self.m_audio<0 or not self.m_project:return
        a=self.m_project.m_document['audios'][self.m_audio]
        import base64
        from PySide6 import QtCore,QtMultimedia
        data=base64.b64decode(a['uri'].split(',',1)[1])
        self.stop_audio()
        buffer=QtCore.QBuffer();buffer.setData(data);buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
        self.m_audio_buffer=buffer
        player=QtMultimedia.QMediaPlayer();self.m_audio_player=player
        audio_output=QtMultimedia.QAudioOutput();self.m_audio_output=audio_output
        player.setAudioOutput(audio_output)
        player.setSourceDevice(buffer,'audio/wav')
        player.play()
        self.m_audio_playing=True;self.m_audio_duration_ms=int(a.get('frames',0)/max(1,a.get('sampleRate',1))*1000)
        self.m_audio_play_btn.setText('|| Pause')
        try:self.m_audio_play_btn.clicked.disconnect()
        except RuntimeError:pass
        self.m_audio_play_btn.clicked.connect(self.pause_audio)
        self.m_audio_stop_btn.setEnabled(True);self.m_audio_slider.setEnabled(True)
        self.m_audio_dur.setText('%d:%02d'%(self.m_audio_duration_ms//60000,(self.m_audio_duration_ms%60000)//1000))
        self.m_audio_timer=QtCore.QTimer();self.m_audio_timer.timeout.connect(self._audio_tick);self.m_audio_timer.start(200)
        self.statusBar().showMessage('Playing %s'%a.get('name','Audio'))
    def pause_audio(self):
        player=getattr(self,'m_audio_player',None)
        if player is not None:
            try:player.pause()
            except Exception:pass
        self.m_audio_playing=False
        self.m_audio_play_btn.setText(chr(9654)+' Play')
        try:self.m_audio_play_btn.clicked.disconnect()
        except RuntimeError:pass
        self.m_audio_play_btn.clicked.connect(self.resume_audio)
        if self.m_audio_timer:self.m_audio_timer.stop()
    def resume_audio(self):
        player=getattr(self,'m_audio_player',None)
        if player is not None:
            try:player.play()
            except Exception:pass
        self.m_audio_playing=True
        self.m_audio_play_btn.setText('|| Pause')
        try:self.m_audio_play_btn.clicked.disconnect()
        except RuntimeError:pass
        self.m_audio_play_btn.clicked.connect(self.pause_audio)
        if self.m_audio_timer:self.m_audio_timer.start(200)
    def stop_audio(self):
        player=getattr(self,'m_audio_player',None)
        if player is not None:
            try:player.stop()
            except Exception:pass
        self.m_audio_player=None;self.m_audio_output=None;self.m_audio_buffer=None;self.m_audio_playing=False
        if self.m_audio_timer:self.m_audio_timer.stop();self.m_audio_timer=None
        self.m_audio_play_btn.setText(chr(9654)+' Play')
        try:self.m_audio_play_btn.clicked.disconnect()
        except RuntimeError:pass
        self.m_audio_play_btn.clicked.connect(self.play_audio)
        self.m_audio_stop_btn.setEnabled(False);self.m_audio_slider.setEnabled(False);self.m_audio_slider.setValue(0)
        self.m_audio_pos.setText('0:00')
    def _audio_tick(self):
        if not self.m_audio_playing:return
        player=getattr(self,'m_audio_player',None)
        if player is None:return
        ms=player.position()
        self.m_audio_slider.setValue(int(ms/max(1,self.m_audio_duration_ms)*1000) if self.m_audio_duration_ms>0 else 0)
        self.m_audio_pos.setText('%d:%02d'%(ms//60000,(ms%60000)//1000))
        if ms>=self.m_audio_duration_ms:self.stop_audio()
    def set_audio_volume(self,value):
        output=getattr(self,'m_audio_output',None)
        if output is not None:
            try:output.setVolume(value/100.0)
            except Exception:pass
    def seek_audio(self):
        value=self.m_audio_slider.value()
        if self.m_audio<0 or not self.m_project or self.m_audio_duration_ms<=0:return
        ms=int(value/1000.0*self.m_audio_duration_ms)
        self.m_audio_pos.setText('%d:%02d'%(ms//60000,(ms%60000)//1000))
        player=getattr(self,'m_audio_player',None)
        if player is not None:
            try:player.setPosition(ms)
            except Exception:pass

    def _open_motion(self,path,data,remember):
        try:
            from arika_models import parse_motion, parse_motions
            if data[:4]==b'MOT2':
                motion=parse_motion(data);motions=[motion]
            else:
                parsed=parse_motions(data);motions=list(parsed.get('motions',[]))
        except Exception as error:
            self.fail(error);return
        if not motions:
            self.statusBar().showMessage('No motions found in %s'%path);return
        self.m_motions=list(motions)
        self.m_motion_list.blockSignals(True);self.m_motion_list.clear()
        for m in motions:self.m_motion_list.addItem(m.get('name') or 'Motion %d'%(motions.index(m)+1))
        self.m_motion_list.blockSignals(False)
        self.m_motion_list.setEnabled(len(motions)>1)
        self.m_motion_path=path;self.m_motion_remember=remember
        self.motion_list_changed(0)

    def motion_list_changed(self,index):
        if not hasattr(self,'m_motions') or index<0 or index>=len(self.m_motions):return
        motion=self.m_motions[index]
        self._start_motion(motion,getattr(self,'m_motion_path',None),False)

    def _start_motion(self,motion,path,remember):
        if not self.m_project or not self.m_project.m_document.get('nodes'):
            self.statusBar().showMessage('Load a model/character before playing a motion.');return
        self.clear_motion()
        self.m_motion=motion
        self.m_motion_nodes=list(motion.get('nodes',[]))
        self.m_motion_node_map=self._build_motion_node_map(motion)
        self.m_motion_duration=float(motion.get('duration',0.0))
        nodes=self.m_project.m_document['nodes']
        self.m_bind_pose={}
        for index in self.m_motion_node_map.values():
            node=nodes[index]
            self.m_bind_pose[index]=(list(node.get('translation',[0,0,0])),list(node.get('rotation',[0,0,0,1])),list(node.get('scale',[1,1,1])))
        name=motion.get('name') or Path(path).stem
        self.m_motion_name.setText(name)
        matched=len(self.m_motion_node_map);total=len(self.m_motion_nodes)
        self.m_motion_info.setText('%d/%d bone tracks matched to model'%(matched,total))
        self.m_motion_dur.setText('%d:%02d'%(int(self.m_motion_duration)//60,int(self.m_motion_duration)%60))
        self.m_motion_time=0.0
        self.m_motion_play_btn.setEnabled(True);self.m_motion_pause_btn.setEnabled(False)
        self.m_motion_stop_btn.setEnabled(False);self.m_motion_slider.setEnabled(True)
        self.m_motion_slider.setValue(0);self._update_motion_ui()
        self.apply_motion_frame(0.0)
        self.statusBar().showMessage('Motion loaded: %s'%name)
        if remember:self.remember_file(path,'motion')

    def _build_motion_node_map(self,motion):
        nodes=self.m_project.m_document.get('nodes',[])
        name_to_index={}
        for i,node in enumerate(nodes):
            name=node.get('name')
            if name:name_to_index[name]=i
        skinned=any(node.get('extras',{}).get('skinned_preview') or 'skin' in node for node in nodes)
        node_map={};count=len(nodes)
        motion_nodes=list(motion.get('nodes',[]))
        has_names=any(mnode.get('name') for mnode in motion_nodes)
        if has_names:
            # RFSM: bone names assigned via reverse binding -> name match. Skinned
            # characters carry named bone nodes, so name-based matching applies.
            for mnode in motion_nodes:
                mindex=mnode.get('index',0);name=mnode.get('name')
                if name and name in name_to_index:node_map[mindex]=name_to_index[name]
        # Best-effort fallback for baked characters: no bone nodes exist, so
        # animate the character root actor. Skipped for skinned characters.
        if not node_map and not skinned:
            root=None
            for i,node in enumerate(nodes):
                if node.get('extras',{}).get('character_preview'):root=i;break
            if root is not None and motion_nodes:
                rev=motion.get('reverse_node_bindings') or motion.get('rev')
                root_motion_node=0
                if rev and len(rev)>0 and rev[0] is not None and rev[0]>=0:
                    root_motion_node=rev[0]
                if root_motion_node < len(motion_nodes):
                    node_map[root_motion_node]=root
        return node_map

    def clear_motion(self):
        self.stop_motion()
        self.m_motion=None;self.m_motion_nodes=[];self.m_motion_node_map={}
        self.m_bind_pose={};self.m_motion_time=0.0;self.m_motion_duration=0.0
        self.m_motion_name.setText('No motion loaded');self.m_motion_info.setText('')
        self.m_motion_play_btn.setEnabled(False);self.m_motion_pause_btn.setEnabled(False)
        self.m_motion_stop_btn.setEnabled(False);self.m_motion_slider.setEnabled(False)
        self.m_motion_slider.setValue(0);self.m_motion_pos.setText('0:00');self.m_motion_dur.setText('0:00')

    def _sample_track(self,track,t,quaternion=False):
        times=track.get('times',[]);values=track.get('values',[])
        if not times:return [0,0,0] if not quaternion else [0,0,0,1]
        if t<=times[0]:return values[0]
        if t>=times[-1]:return values[-1]
        i=0
        while i+1<len(times) and times[i+1]<=t:i+=1
        t0,t1=times[i],times[i+1];f=(t-t0)/max(1e-9,(t1-t0))
        v0,v1=values[i],values[i+1]
        out=[v0[k]+f*(v1[k]-v0[k]) for k in range(len(v0))]
        if quaternion:
            n=math.sqrt(sum(x*x for x in out))
            if n>1e-12:out=[x/n for x in out]
        return out

    def apply_motion_frame(self,t):
        if not self.m_motion or not self.m_project:return
        nodes=self.m_project.m_document.get('nodes',[])
        for mindex,index in self.m_motion_node_map.items():
            mnode=self.m_motion_nodes[mindex]
            tr=self._sample_track(mnode['tracks']['translation'],t)
            ro=self._sample_track(mnode['tracks']['rotation'],t,quaternion=True)
            sc=self._sample_track(mnode['tracks']['scale'],t)
            node=nodes[index]
            node['translation']=list(tr);node['rotation']=list(ro);node['scale']=list(sc)
        self.m_view.set_project(self.m_project, geometry=False);self.m_object_view.set_project(self.m_project, geometry=False)

    def restore_bind_pose(self):
        if not self.m_project:return
        nodes=self.m_project.m_document.get('nodes',[])
        for index,(tr,ro,sc) in self.m_bind_pose.items():
            node=nodes[index]
            node['translation']=list(tr);node['rotation']=list(ro);node['scale']=list(sc)
        self.m_view.set_project(self.m_project, geometry=False);self.m_object_view.set_project(self.m_project, geometry=False)

    def play_motion(self):
        if not self.m_motion or not self.m_project:return
        if self.m_motion_timer is None:
            self.m_motion_timer=C.QTimer();self.m_motion_timer.timeout.connect(self._motion_tick)
        self.m_motion_timer.start(33)
        self.m_motion_playing=True
        self.m_motion_play_btn.setEnabled(False);self.m_motion_pause_btn.setEnabled(True)
        self.m_motion_stop_btn.setEnabled(True);self.m_motion_slider.setEnabled(True)
        self.statusBar().showMessage('Playing motion')

    def pause_motion(self):
        self.m_motion_playing=False
        if self.m_motion_timer:self.m_motion_timer.stop()
        self.m_motion_play_btn.setEnabled(True);self.m_motion_pause_btn.setEnabled(False)
        self.statusBar().showMessage('Motion paused')

    def stop_motion(self):
        self.m_motion_playing=False
        if self.m_motion_timer:self.m_motion_timer.stop()
        self.m_motion_time=0.0
        self.restore_bind_pose()
        self._update_motion_ui()
        self.m_motion_play_btn.setEnabled(bool(self.m_motion is not None));self.m_motion_pause_btn.setEnabled(False)
        self.m_motion_stop_btn.setEnabled(False);self.m_motion_slider.setEnabled(False)
        self.m_motion_slider.setValue(0)
        self.statusBar().showMessage('Motion stopped (bind pose restored)')

    def motion_slider_pressed(self):
        self._motion_was_playing=getattr(self,'_motion_was_playing',False) or self.m_motion_playing
        if self.m_motion_playing:self.pause_motion()

    def seek_motion(self):
        if not self.m_motion or self.m_motion_duration<=0:return
        self.m_motion_time=self.m_motion_slider.value()/1000.0*self.m_motion_duration
        self.apply_motion_frame(self.m_motion_time)
        self._update_motion_ui()
        if getattr(self,'_motion_was_playing',False):
            self._motion_was_playing=False;self.play_motion()

    def _motion_tick(self):
        if not self.m_motion_playing or not self.m_motion:return
        self.m_motion_time+=0.033
        if self.m_motion_time>=self.m_motion_duration:self.m_motion_time=0.0
        self.apply_motion_frame(self.m_motion_time)
        self._update_motion_ui()

    def _update_motion_ui(self):
        dur=self.m_motion_duration;t=self.m_motion_time
        self.m_motion_slider.blockSignals(True)
        self.m_motion_slider.setValue(int(t/max(1e-6,dur)*1000) if dur>0 else 0)
        self.m_motion_slider.blockSignals(False)
        self.m_motion_pos.setText('%d:%02d'%(int(t)//60,int(t)%60))
        self.m_motion_dur.setText('%d:%02d'%(int(dur)//60,int(dur)%60))

    def select_audio_view(self):
        if not self.m_project:self.m_audio_name.setText('No project');return
        audios=self.m_project.m_document.get('audios',[])
        if not audios:self.m_audio_name.setText('No audio imported');return
        if self.m_audio<0 or self.m_audio>=len(audios):self.m_audio=0
        a=audios[self.m_audio]
        self.m_audio_name.setText(a.get('name','Audio'))
        self.m_audio_info.setText('%d Hz · %d channel(s) · %d frames (%.2f s)'%(a.get('sampleRate',0),a.get('channels',0),a.get('frames',0),a.get('frames',0)/max(1,a.get('sampleRate',1))))
        self.m_audio_dur.setText('%d:%02d'%(int(a.get('frames',0)/max(1,a.get('sampleRate',1))*1000)//60000,(int(a.get('frames',0)/max(1,a.get('sampleRate',1))*1000)%60000)//1000))
        self.m_audio_duration_ms=int(a.get('frames',0)/max(1,a.get('sampleRate',1))*1000)
        self.m_audio_play_btn.setEnabled(True);self.m_audio_stop_btn.setEnabled(False);self.m_audio_slider.setEnabled(False);self.m_audio_slider.setValue(0);self.m_audio_pos.setText('0:00')
        try:self.m_audio_play_btn.clicked.disconnect()
        except RuntimeError:pass;self.m_audio_play_btn.clicked.connect(self.play_audio)
    def save_project(self):
        if not self.m_project:return
        path,_=W.QFileDialog.getSaveFileName(self,'Save project',self.m_project_path or 'scene.arika-scene.json','Arika project (*.arika-scene.json)')
        if path:
            if not path.lower().endswith('.arika-scene.json'):path += '.arika-scene.json'
            try:
                self.m_project.save(path);self.m_project_path=str(Path(path).resolve());self.remember_file(self.m_project_path,'project');self.statusBar().showMessage('Saved project '+self.m_project_path)
            except Exception as e:self.fail(e)
    def save_stage(self):
        if getattr(self,'m_virtual',False):
            self.statusBar().showMessage('Save STG copy is disabled for virtual archives.');return
        if not self.m_project:return
        path,_=W.QFileDialog.getSaveFileName(self,'Save STG copy','edited.stg','Stage (*.stg)')
        if path:
            if not path.lower().endswith('.stg'):path += '.stg'
            try:
                self.m_project.m_stage.save_as(path);self.remember_file(path,'stage');self.statusBar().showMessage('Saved native STG transforms only. Object deletions, characters and materials require project/glTF saving.')
            except Exception as e:self.fail(e)
    def export(self):
        if getattr(self,'m_virtual',False):
            self.statusBar().showMessage('Export glTF is disabled for virtual archives.');return
        if not self.m_project:return
        path,_=W.QFileDialog.getSaveFileName(self,'Export glTF','scene.gltf','glTF (*.gltf)')
        if path:
            try:self.m_project.export(path);self.statusBar().showMessage('Exported scene with material/image edits')
            except Exception as e:self.fail(e)
    def history(self,redo):
        if self.m_project:
            self.m_project.redo() if redo else self.m_project.undo();self.populate()
    def refresh_texture_browser(self):
        self.m_texture_browser.blockSignals(True);self.m_texture_browser.clear()
        for i,texture in enumerate(self.m_project.m_document.get('textures',[])):
            image=self.m_project.m_document['images'][texture['source']];pix=G.QPixmap();pix.loadFromData(base64.b64decode(image['uri'].split(',',1)[1]))
            item=W.QListWidgetItem(G.QIcon(pix),'%d: %s\n%d x %d'%(i,image.get('name','PIX'),pix.width(),pix.height()));item.setData(C.Qt.ItemDataRole.UserRole,i);self.m_texture_browser.addItem(item)
        self.m_texture_browser.blockSignals(False)
    def browse_texture(self,index):
        if not self.m_project or index<0:return
        image=self.m_project.m_document['images'][self.m_project.m_document['textures'][index]['source']];pix=G.QPixmap();pix.loadFromData(base64.b64decode(image['uri'].split(',',1)[1]))
        self.m_texture_info.setText('Texture %d — %s — %d × %d — wheel zoom / drag pan'%(index,image.get('name','PIX texture'),pix.width(),pix.height()));self.m_texture_view.set_image(pix)
        if self.m_view_mode.currentIndex()!=2:self.m_view_mode.setCurrentIndex(2)
    def refresh_material_preview(self):
        if not self.m_project or self.m_material<0:return
        from types import SimpleNamespace
        self.m_material_view.set_project(SimpleNamespace(m_document=material_preview_document(self.m_project.m_document,self.m_material)),fit=True)
    def change_view(self,index):
        self.m_views.setCurrentIndex(index)
        self.m_workspaces.blockSignals(True);self.m_workspaces.setCurrentIndex(index);self.m_workspaces.blockSignals(False)
        self.m_editor_heading.setText(('3D Viewport','Material Preview','Image Editor','Object View','Menu Editor','Audio','Fonts')[index])
        if index==1:self.m_properties_tabs.setCurrentIndex(1)
        if index==1:self.refresh_material_preview()
        elif index==2 and self.m_project and self.m_texture_browser.count():
            row=self.m_texture_browser.currentRow();self.browse_texture(max(0,row))
        elif index==3:
            self.m_object_view.m_isolated=set(self.m_view.m_selection)
            if self.m_object_view.m_renderer and not self.m_object_view.m_upload:self.m_object_view.frame()
            else:self.m_object_view.m_fit=True
            self.m_object_view.request_draw()
            if not self.m_view.m_selection:self.statusBar().showMessage('Object View: select an object or group in the Outliner.')
        elif index==4:
            self.statusBar().showMessage('Menu editor: recovered 2D menu preview.')
        elif index==5:
            self.select_audio_view()
        self.sync_view_controls()

    def active_view(self):
        return {0:self.m_view,1:self.m_material_view,3:self.m_object_view}.get(self.m_views.currentIndex(),self.m_view)

    def set_gizmo_mode(self,mode):
        if mode not in ('transform','move','rotate','scale'):return
        for view in (self.m_view,self.m_object_view):view.m_gizmo_mode=mode;view.request_draw()
        for name,button in self.m_gizmo_buttons.items():button.blockSignals(True);button.setChecked(name==mode);button.blockSignals(False)
        self.statusBar().showMessage('Transform gizmo: %s (%s) · X/Y/Z constrain axes · Shift precision · Ctrl snapping · type a value while dragging'%({'transform':'Transform','move':'Move','rotate':'Rotate','scale':'Scale'}[mode],{'transform':'T','move':'G','rotate':'R','scale':'S'}[mode]))

    def set_transform_orientation(self,text):
        self.m_transform_orientation={'Global':'global','Local':'local','Normal':'normal','Gimbal':'gimbal','View':'view','Cursor':'cursor','Custom':'custom'}.get(text,'local')
        for view in (self.m_view,self.m_object_view):view.m_transform_orientation=self.m_transform_orientation;view.m_custom_orientation_axes=self.m_custom_orientation_axes;view.request_draw()

    def set_pivot_mode(self,text):
        self.m_pivot_mode={'Median Point':'median','Active Element':'active','Individual Origins':'individual','3D Cursor':'cursor'}.get(text,'median')
        for view in (self.m_view,self.m_object_view):view.m_pivot_mode=self.m_pivot_mode;view.request_draw()

    def set_snap_step(self,mode,value):
        if mode in self.m_snap_steps and isinstance(value,(int,float)) and value>0:
            self.m_snap_steps[mode]=float(value)
            for view in (self.m_view,self.m_object_view):view.m_snap_steps[mode]=float(value)
            self.statusBar().showMessage('Snap increment: %s'%({'move':'%g units'%value,'rotate':'%g°'%value,'scale':'%g%%'%(value*100)}[mode]))

    def set_cursor_to_active(self):
        if not self.m_project or self.m_view.m_selected<0:return
        worlds,_=self.m_view.world_transforms()
        self.set_cursor_location(worlds[self.m_view.m_selected][:3,3].tolist())
        self.statusBar().showMessage('3D Cursor moved to active object origin.')

    def set_cursor_location(self,location):
        self.m_cursor_location=[float(v) for v in location[:3]]
        for view in (self.m_view,self.m_object_view):view.m_cursor_location=list(self.m_cursor_location);view.request_draw()

    def align_cursor_to_active(self):
        if not self.m_project or self.m_view.m_selected<0:return
        worlds,_=self.m_view.world_transforms()
        self.m_cursor_axes=[a.tolist() for a in self.m_view.orthogonal_axes(worlds[self.m_view.m_selected])]
        for view in (self.m_view,self.m_object_view):view.m_cursor_axes=[list(a) for a in self.m_cursor_axes];view.request_draw()
        self.statusBar().showMessage('3D Cursor orientation aligned to active object.')

    def create_custom_orientation_from_active(self):
        if not self.m_project or self.m_view.m_selected<0:return
        worlds,_=self.m_view.world_transforms()
        self.m_custom_orientation_axes=[a.tolist() for a in self.m_view.orthogonal_axes(worlds[self.m_view.m_selected])]
        for view in (self.m_view,self.m_object_view):view.m_custom_orientation_axes=[list(a) for a in self.m_custom_orientation_axes];view.request_draw()
        self.m_orientation_combo.setCurrentText('Custom')
        self.statusBar().showMessage('Custom transform orientation created from active object.')

    def clear_custom_orientation(self):
        self.m_custom_orientation_axes=None
        for view in (self.m_view,self.m_object_view):view.m_custom_orientation_axes=None;view.request_draw()
        if self.m_transform_orientation=='custom':self.m_orientation_combo.setCurrentText('Local')
        self.statusBar().showMessage('Custom transform orientation cleared.')

    def reset_cursor(self):
        self.m_cursor_location=[0.0,0.0,0.0]
        self.m_cursor_axes=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
        for view in (self.m_view,self.m_object_view):view.m_cursor_location=list(self.m_cursor_location);view.m_cursor_axes=[list(a) for a in self.m_cursor_axes];view.request_draw()

    def sync_view_controls(self):
        view=self.active_view()
        self.m_shading_mode.blockSignals(True);self.m_shading_mode.setCurrentText(view.m_mode);self.m_shading_mode.blockSignals(False)
        self.m_collision_toggle.blockSignals(True);self.m_collision_toggle.setChecked(view.m_collision);self.m_collision_toggle.blockSignals(False)
        for key,action in self.m_option_actions.items():
            action.blockSignals(True);action.setChecked(view.m_options[key]);action.blockSignals(False)
        self.m_projection_action.blockSignals(True);self.m_projection_action.setChecked(view.m_orthographic);self.m_projection_action.blockSignals(False)

    def viewport_option(self,key,value):
        view=self.active_view();view.m_options[key]=value;view.request_draw()

    def projection(self,orthographic):
        view=self.active_view();view.m_orthographic=orthographic;view.m_axis_view=False;view.request_draw()

    def align_view(self,yaw,pitch):
        view=self.active_view();view.m_yaw=yaw;view.m_pitch=pitch;view.m_orthographic=True;view.m_axis_view=True;view.request_draw()

    def background_color(self):
        view=self.active_view();color=W.QColorDialog.getColor(G.QColor.fromRgbF(*view.m_options['background']),self,'Viewport background')
        if color.isValid():view.m_options['background']=color.getRgbF();view.request_draw()

    def fit(self):
        if self.m_views.currentIndex()==2:self.m_texture_view.fit();return
        view=self.active_view()
        if view.m_renderer and not view.m_upload:view.frame()
        else:view.m_fit=True;view.m_upload=True;view.update()
    def mode(self,text):view=self.active_view();view.m_mode=text.replace(' World','');view.request_draw()
    def collision(self,value):view=self.active_view();view.m_collision=value;view.request_draw()
    def closeEvent(self,event):
        if not self.discard():
            event.ignore();return
        if self.m_motion_timer:self.m_motion_timer.stop()
        try:
            self.m_settings.set_window_bytes(self.saveGeometry(),self.saveState())
            self.m_settings.save()
        except OSError as error:
            self.statusBar().showMessage('Could not save editor settings: '+str(error),8000)
        event.accept()


def main():
    app=W.QApplication(sys.argv);app.setStyle('Fusion')
    window=c_scene_editor();window.show()
    if len(sys.argv)>1:
        path=sys.argv[1]
        try:
            window.load_file(path)
        except Exception:
            try:
                p=Path(path)
                kind='project' if p.name.lower().endswith('.arika-scene.json') else 'stage'
                window.load_scene_file(str(p),kind)
            except Exception:
                pass
    return app.exec()


c_arika_editor=c_scene_editor
c_editor=c_scene_editor


if __name__=='__main__':sys.exit(main())
