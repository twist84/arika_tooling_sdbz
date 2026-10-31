#!/usr/bin/env python3
"""Lightweight Qt/WebGPU stage editor with textured material previews."""
import base64
import copy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
from PIL import Image
from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
from rendercanvas.qt import QRenderWidget
from arika_webgpu import c_webgpu_renderer,DEFAULT_BACKGROUND,camera_matrix
from arika_gizmo import (gizmo_geometry,rotate_euler_local_axis,
    quaternion_from_axis_angle,quaternion_from_matrix,quaternion_inverse,
    quaternion_multiply,quaternion_to_euler)
from arika_scene_project import c_scene_project,material_preview_document
from arika_editor_settings import c_editor_settings
from arika_import import c_gltf_reader
from arika_models import identity,local_matrix,multiply
from arika_scene_state import node_state,hidden_nodes,selection_nodes,transform_locks

NAVIGATION_HELP='MMB orbit · Shift+MMB pan · Ctrl+MMB zoom · Wheel zoom · Home frame all · Numpad . frame selected · Numpad 1/3/7 views · Numpad 5 perspective/ortho'

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
'''


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
        self.setMinimumSize(400,350)
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
            print('WebGPU error:',error,file=sys.stderr)

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


class c_outliner_tree(W.QTreeWidget):
    def __init__(self,editor):
        super().__init__();self.m_editor=editor
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
        super().__init__();self.m_settings=c_editor_settings();self.m_project=None;self.m_project_path=None;self.m_index=None;self.m_material=-1;self.m_items={};self.m_color=[1,1,1,1]
        self.m_transform_orientation='local';self.m_pivot_mode='median';self.m_cursor_location=[0.0,0.0,0.0];self.m_cursor_axes=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]];self.m_custom_orientation_axes=None;self.m_snap_steps={'move':1.0,'rotate':15.0,'scale':0.1}
        self.setWindowTitle('Arika WebGPU scene editor');self.resize(1400,900);self.m_view=c_viewport();self.m_view.selection_requested.connect(self.select_view);self.m_view.selection_all.connect(self.select_all);self.m_view.delete_requested.connect(self.delete_selected);self.m_view.transform_changed.connect(self.sync_selection);self.m_view.gizmo_mode_requested.connect(self.set_gizmo_mode)
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
        for view in (self.m_view,self.m_object_view):
            view.m_transform_orientation=self.m_transform_orientation;view.m_pivot_mode=self.m_pivot_mode;view.m_cursor_location=list(self.m_cursor_location);view.m_cursor_axes=[list(a) for a in self.m_cursor_axes];view.m_custom_orientation_axes=self.m_custom_orientation_axes;view.m_snap_steps=dict(self.m_snap_steps)
        self.setStyleSheet(EDITOR_STYLE)
        bar=W.QToolBar('Viewport');bar.setObjectName('viewport_header');bar.setMovable(False)
        self.m_editor_heading=W.QLabel('3D Viewport');self.m_editor_heading.setObjectName('editor_heading');bar.addWidget(self.m_editor_heading)
        view_mode=W.QComboBox();view_mode.addItems(['World','Material Preview','Texture Browser','Object View','Menu Editor']);view_mode.currentIndexChanged.connect(self.change_view);bar.addWidget(view_mode);self.m_view_mode=view_mode
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
        self.m_tree=c_outliner_tree(self);self.m_tree.setHeaderLabels(['Scene / object','Show','Lock']);self.m_tree.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.m_tree.setDragEnabled(True);self.m_tree.setAcceptDrops(True);self.m_tree.setDragDropMode(W.QAbstractItemView.DragDropMode.InternalMove);self.m_tree.setDefaultDropAction(C.Qt.DropAction.MoveAction)
        self.m_tree.header().setSectionResizeMode(0,W.QHeaderView.ResizeMode.Stretch)
        for column in (1,2):self.m_tree.header().setSectionResizeMode(column,W.QHeaderView.ResizeMode.Fixed);self.m_tree.setColumnWidth(column,45)
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
        outliner=W.QWidget();layout=W.QVBoxLayout(outliner);layout.setContentsMargins(5,5,5,5);layout.addWidget(filter_row);layout.addWidget(self.m_tree)
        dock=W.QDockWidget('Scene Collection — Outliner',self);dock.setObjectName('scene_outliner');dock.setWidget(outliner);dock.setMinimumWidth(300);self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,dock);self.m_outliner_dock=dock
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
        note=W.QLabel('Material and image edits save to projects / glTF.\nNative MDL/PIX are unchanged.');note.setWordWrap(True);mf.addWidget(note);mf.addStretch();material_scroll=W.QScrollArea();material_scroll.setWidgetResizable(True);material_scroll.setWidget(materials);tabs.addTab(material_scroll,'Materials');self.m_properties_tabs=tabs
        self.m_texture_browser=W.QListWidget();self.m_texture_browser.setViewMode(W.QListView.ViewMode.IconMode);self.m_texture_browser.setIconSize(C.QSize(64,64));self.m_texture_browser.setGridSize(C.QSize(110,100));self.m_texture_browser.setResizeMode(W.QListView.ResizeMode.Adjust);self.m_texture_browser.currentRowChanged.connect(self.browse_texture)
        dock=W.QDockWidget('Properties',self);dock.setObjectName('scene_properties');dock.setWidget(tabs);self.addDockWidget(C.Qt.DockWidgetArea.RightDockWidgetArea,dock);self.m_properties_dock=dock
        self.splitDockWidget(self.m_outliner_dock,dock,C.Qt.Orientation.Vertical)
        self.m_assets_dock=W.QDockWidget('Asset Browser — Textures',self);self.m_assets_dock.setObjectName('scene_assets');self.m_assets_dock.setWidget(self.m_texture_browser);self.addDockWidget(C.Qt.DockWidgetArea.BottomDockWidgetArea,self.m_assets_dock)
        self.setCorner(C.Qt.Corner.BottomRightCorner,C.Qt.DockWidgetArea.RightDockWidgetArea)
        self.build_menus()
        workspaces=self.addToolBar('Workspaces');workspaces.setObjectName('workspace_header');workspaces.setMovable(False)
        brand=W.QLabel('  ARIKA  ');brand.setObjectName('editor_heading');workspaces.addWidget(brand)
        self.m_workspaces=W.QTabBar();self.m_workspaces.setExpanding(False)
        for name in ('Layout','Shading','Textures','Object','Menu'):self.m_workspaces.addTab(name)
        self.m_workspaces.currentChanged.connect(self.workspace);workspaces.addWidget(self.m_workspaces)
        self.statusBar().setSizeGripEnabled(True);self.statusBar().showMessage('MMB orbit  |  Shift+MMB pan  |  Wheel zoom  |  Home frame all  |  Numpad . frame selected')
        self.m_selection_status=W.QLabel('0 selected');self.statusBar().addPermanentWidget(self.m_selection_status)
        self.m_scene_status=W.QLabel('No scene');self.m_scene_status.setMaximumWidth(320);self.statusBar().addPermanentWidget(self.m_scene_status)
        self.reset_layout()
        self.m_settings.restore_window(self)
        self.refresh_recent_menu()

    def build_menus(self):
        file_menu=self.menuBar().addMenu('File')
        file_menu.addAction('Add character…').triggered.connect(self.add_character)
        file_menu.addAction('Add example Goku').triggered.connect(self.add_example_character)
        file_menu.addSeparator()
        for title,shortcut,callback in [('Open stage…','Ctrl+O',self.open_stage),('Open project…','Ctrl+Shift+O',self.open_project)]:
            action=file_menu.addAction(title);action.triggered.connect(callback)
            if shortcut:action.setShortcut(shortcut)
        self.m_recent_menu=file_menu.addMenu('Open Recent')
        self.m_recent_stages=self.m_recent_menu.addMenu('Stages')
        self.m_recent_projects=self.m_recent_menu.addMenu('Projects')
        self.m_recent_menu.addSeparator()
        self.m_clear_recent_action=self.m_recent_menu.addAction('Clear Recent Files')
        self.m_clear_recent_action.triggered.connect(self.clear_recent_files)
        self.m_recent_menu.aboutToShow.connect(self.refresh_recent_menu)
        file_menu.addSeparator()
        for title,shortcut,callback in [('Save project…','Ctrl+S',self.save_project),('Save STG copy…','',self.save_stage),('Export glTF…','Ctrl+E',self.export),('Exit','Alt+F4',self.close)]:
            action=file_menu.addAction(title);action.triggered.connect(callback)
            if shortcut:action.setShortcut(shortcut)
        edit=self.menuBar().addMenu('Edit')
        edit.addAction('Delete selected objects').triggered.connect(self.delete_selected)
        duplicate_action=edit.addAction('Duplicate selected (Ctrl+D)');duplicate_action.setShortcut('Ctrl+D');duplicate_action.triggered.connect(self.duplicate_selected)
        for title,shortcut,callback in [('Undo','Ctrl+Z',lambda:self.history(False)),('Redo','Ctrl+Shift+Z',lambda:self.history(True))]:
            action=edit.addAction(title);action.setShortcut(shortcut);action.triggered.connect(callback)
        window=self.menuBar().addMenu('Window')
        for dock in (self.m_outliner_dock,self.m_properties_dock,self.m_assets_dock):window.addAction(dock.toggleViewAction())
        window.addSeparator();window.addAction('Reset layout').triggered.connect(self.reset_layout)
        help_menu=self.menuBar().addMenu('Help');help_menu.addAction('Viewport controls').triggered.connect(lambda:W.QMessageBox.information(self,'Viewport controls',self.m_view.toolTip().replace(' · ','\n')))

    def add_character(self):
        if not self.m_project:
            self.statusBar().showMessage('Open a stage or editor project, then add a character.');return
        path,_=W.QFileDialog.getOpenFileName(self,'Add character model','','Character models (*.mdl *.gltf *.glb)')
        if not path:return
        texture=None
        if Path(path).suffix.lower()=='.mdl' and not Path(path).with_suffix('.pix').exists():
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
            from arika_scene_characters import load_character
            W.QApplication.setOverrideCursor(C.Qt.CursorShape.WaitCursor)
            try:character=load_character(path,texture)
            finally:W.QApplication.restoreOverrideCursor()
            meshes=character['meshes'];selected=list(range(len(meshes)))
            if choose:
                dialog=W.QDialog(self);dialog.setWindowTitle('Character mesh variants');dialog.resize(440,480);layout=W.QVBoxLayout(dialog)
                note=W.QLabel('Choose meshes to include. Alternate hands, hair or costumes may overlap. Static authored pose; no animation playback.');note.setWordWrap(True);layout.addWidget(note)
                items=W.QListWidget();layout.addWidget(items)
                for mesh in meshes:
                    item=W.QListWidgetItem(mesh.get('name','Character mesh'));item.setCheckState(C.Qt.CheckState.Checked);items.addItem(item)
                buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok|W.QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
                if dialog.exec()!=W.QDialog.DialogCode.Accepted:return
                selected=[i for i in range(items.count()) if items.item(i).checkState()==C.Qt.CheckState.Checked]
            else:selected=[i for i,m in enumerate(meshes) if m.get('name') not in ('MeshLHandD','MeshRHandD')]
            center=self.m_view.m_center
            index=self.m_project.add_character(character,name or Path(path).stem,selected,[center[0],0,center[2]])
            self.populate();self.select_view(index);self.m_workspaces.setCurrentIndex(3)
            self.statusBar().showMessage('Character added in authored pose. Unlock its root to place it. Save project retains it; STG does not include character instances.')
        except Exception as error:self.fail(error)

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
        for menu,kind in ((self.m_recent_stages,'stage'),(self.m_recent_projects,'project')):
            menu.clear()
            entries=self.m_settings.recent_files(kind)
            if not entries:
                action=menu.addAction('No recent %s files'%('stage' if kind=='stage' else 'projects'))
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
        self.load_scene_file(path,kind)

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
            self.m_project=project;self.m_project_path=project_path
            self.populate(True)
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
    def populate(self,fit=False):
        previous=set(self.m_view.m_selection) if not fit else set();active=self.m_index
        self.m_tree.blockSignals(True);self.m_tree.clear();self.m_items={};doc=self.m_project.m_document
        self.m_scene_status.setText('%d objects | %d materials | %d textures'%(len(doc.get('nodes',[])),len(doc.get('materials',[])),len(doc.get('textures',[]))))
        def item(index,parent):
            node=doc['nodes'][index];out=W.QTreeWidgetItem(parent,[node.get('name','Node %d'%index)]);out.setData(0,C.Qt.ItemDataRole.UserRole,index);self.m_items[index]=out
            state=node_state(doc,index);out.setCheckState(1,C.Qt.CheckState.Unchecked if state['hidden'] else C.Qt.CheckState.Checked);out.setCheckState(2,C.Qt.CheckState.Checked if state['locked'] else C.Qt.CheckState.Unchecked)
            out.setToolTip(1,'Checked: visible. Toggle a group to affect its descendants.');out.setToolTip(2,'Checked: transform locked. Uncheck to edit. Groups affect descendants.')
            for child in node.get('children',[]):item(child,out)
        for root in doc['scenes'][doc.get('scene',0)]['nodes']:item(root,self.m_tree)
        self.m_tree.clearSelection();self.m_tree.setCurrentItem(None)
        for index in previous:
            if index in self.m_items:self.m_items[index].setSelected(True)
        if active in previous and active in self.m_items:self.m_tree.setCurrentItem(self.m_items[active],0,C.QItemSelectionModel.SelectionFlag.NoUpdate)
        self.m_tree.blockSignals(False);self.m_tree.expandToDepth(1);self.m_tree_expanded=False
        if hasattr(self,'m_tree_toggle_button'):self.m_tree_toggle_button.setText('+')
        self.m_materials.blockSignals(True);self.m_materials.clear()
        for i,m in enumerate(doc['materials']):self.m_materials.addItem('%d — %s'%(i,m.get('name','Material')))
        self.m_materials.blockSignals(False);self.m_view.set_project(self.m_project,fit);self.m_object_view.set_project(self.m_project,True);self.m_index=None;self.m_material=-1;self.refresh_texture_browser()
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
        value=item.checkState(column)==C.Qt.CheckState.Checked
        self.change_node_state(indices={index},**({'hidden':not value} if column==1 else {'locked':value}))

    def change_node_state(self,indices=None,**state):
        if not self.m_project:return
        targets=self.m_view.m_selection if indices is None else indices
        if not targets:return
        self.m_project.set_node_state(targets,**state)
        self.m_tree.blockSignals(True)
        for index,item in self.m_items.items():
            flags=node_state(self.m_project.m_document,index)
            item.setCheckState(1,C.Qt.CheckState.Unchecked if flags['hidden'] else C.Qt.CheckState.Checked)
            item.setCheckState(2,C.Qt.CheckState.Checked if flags['locked'] else C.Qt.CheckState.Unchecked)
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
        if not self.m_project:return
        path,_=W.QFileDialog.getOpenFileName(self,'Import texture','','Images (*.png *.bmp *.jpg *.tga *.tif)')
        if path:
            try:index=self.m_project.import_texture(path);self.m_view.set_project(self.m_project);self.m_object_view.set_project(self.m_project);self.textures();self.m_texture.setCurrentIndex(index+1);self.show_texture();self.refresh_texture_browser()
            except Exception as e:self.fail(e)
    def save_project(self):
        if not self.m_project:return
        path,_=W.QFileDialog.getSaveFileName(self,'Save project',self.m_project_path or 'scene.arika-scene.json','Arika project (*.arika-scene.json)')
        if path:
            if not path.lower().endswith('.arika-scene.json'):path += '.arika-scene.json'
            try:
                self.m_project.save(path);self.m_project_path=str(Path(path).resolve());self.remember_file(self.m_project_path,'project');self.statusBar().showMessage('Saved project '+self.m_project_path)
            except Exception as e:self.fail(e)
    def save_stage(self):
        if not self.m_project:return
        path,_=W.QFileDialog.getSaveFileName(self,'Save STG copy','edited.stg','Stage (*.stg)')
        if path:
            if not path.lower().endswith('.stg'):path += '.stg'
            try:
                self.m_project.m_stage.save_as(path);self.remember_file(path,'stage');self.statusBar().showMessage('Saved native STG transforms only. Object deletions, characters and materials require project/glTF saving.')
            except Exception as e:self.fail(e)
    def export(self):
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
            item=W.QListWidgetItem(G.QIcon(pix),'%d: %s\n%d × %d'%(i,image.get('name','PIX'),pix.width(),pix.height()));self.m_texture_browser.addItem(item)
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
        self.m_editor_heading.setText(('3D Viewport','Material Preview','Image Editor','Object View','Menu Editor')[index])
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
        kind='project' if Path(path).name.lower().endswith('.arika-scene.json') else 'stage'
        window.load_scene_file(path,kind)
    return app.exec()


if __name__=='__main__':sys.exit(main())
