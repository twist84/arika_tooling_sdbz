#!/usr/bin/env python3
"""Tk stage hierarchy/transform editor with a collision-map preview."""
import math
from pathlib import Path
import struct
import sys
import tempfile
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from arika_stages import parse_stg,parse_hit,export_stage
from arika_models import require,quaternion,local_matrix,multiply,identity,inverse,parse_model
from arika_import import write_output
from arika_stage_view3d import prepare,project,render_image


def snapped_delta(dx,dy,spacing):
    require(all(math.isfinite(v) for v in (dx,dy,spacing)) and spacing>=0,'snap spacing must be finite and nonnegative')
    return (round(dx/spacing)*spacing,round(dy/spacing)*spacing) if spacing else (dx,dy)


def moved_translation(scene,index,dx,dy,plane):
    require(plane in ('XZ','XY','YZ') and all(math.isfinite(v) for v in (dx,dy)),'invalid map movement')
    node=scene['nodes'][index];require('translation' in node,'node has no editable transform')
    chain=[];parent=node['parent']
    while parent>=0:
        chain.append(parent);parent=scene['nodes'][parent]['parent']
    matrix=identity()
    for i in reversed(chain):
        n=scene['nodes'][i]
        if 'translation'in n:matrix=multiply(matrix,local_matrix(dict(translation=n['translation'],rotation=quaternion([math.degrees(v) for v in n['rotation_radians']]),scale=n['scale'])))
    inv=inverse(matrix);delta=[0.,0.,0.];a,b={'XZ':(0,2),'XY':(0,1),'YZ':(1,2)}[plane];delta[a]=dx;delta[b]=dy
    return [node['translation'][i]+sum(inv[i][j]*delta[j] for j in range(3)) for i in range(3)]


class c_stage_document:
    def __init__(self,path):
        self.m_path=Path(path);self.m_original=self.m_path.read_bytes();self.m_data=self.m_original
        self.m_scene=parse_stg(self.m_data);self.m_undo=[];self.m_redo=[]

    def set_transform(self,index,values):
        node=self.m_scene['nodes'][index]
        require(node['kind'] in (1,2,3),'this record has no editable transform')
        require(len(values)==9 and all(math.isfinite(v) for v in values),'expected nine finite values')
        body=struct.pack('<9f',*values);require(all(math.isfinite(v) for v in struct.unpack('<9f',body)),'float32 overflow')
        data=bytearray(self.m_data);data[node['offset']+8:node['offset']+44]=body
        parsed=parse_stg(data)
        if bytes(data)==self.m_data:return
        self.m_undo.append(self.m_data);self.m_undo=self.m_undo[-100:];self.m_redo=[]
        self.m_data=bytes(data);self.m_scene=parsed

    def undo(self):
        if self.m_undo:
            self.m_redo.append(self.m_data);self.m_data=self.m_undo.pop();self.m_scene=parse_stg(self.m_data)

    def redo(self):
        if self.m_redo:
            self.m_undo.append(self.m_data);self.m_data=self.m_redo.pop();self.m_scene=parse_stg(self.m_data)

    def save_as(self,path):
        parse_stg(self.m_data);write_output(path,self.m_data,[self.m_path])

    def export_preview(self,path):
        model=self.m_path.with_suffix('.mdl');hit=self.m_path.with_suffix('.hit');textures=self.m_path.with_suffix('.pix')
        require(all(Path(path).resolve()!=p.resolve() for p in (self.m_path,model,hit,textures)),'export must differ from source assets')
        with tempfile.TemporaryDirectory() as tmp:
            scene=Path(tmp)/'edited.stg';scene.write_bytes(self.m_data)
            return export_stage(scene,path,model_path=model,hit_path=hit if hit.exists() else None,
                texture_path=textures if textures.exists() else None)


class c_stage_editor:
    def __init__(self,root,path=None):
        self.m_root=root;self.m_document=None;self.m_hit=None;self.m_selected=None;self.m_points=[];self.m_lines=[]
        self.m_scale=1.;self.m_offset=[0.,0.];self.m_pan=None;self.m_saved=None;self.m_drag=None;self.m_model=None;self.m_view3d=None;self.m_yaw=.6;self.m_pitch=.55;self.m_orbit=None
        root.title('Arika stage editor');root.geometry('1250x800');root.minsize(900,600)
        root.protocol('WM_DELETE_WINDOW',self.close)
        bar=ttk.Frame(root,padding=6);bar.pack(fill='x')
        for label,command in [('Open STG',self.open_dialog),('Save As',self.save_as),('Export glTF',self.export_preview),('Undo',self.undo),('Redo',self.redo),('Fit view',self.fit)]:
            ttk.Button(bar,text=label,command=command).pack(side='left',padx=3)
        self.m_plane=tk.StringVar(value='3D')
        combo=ttk.Combobox(bar,textvariable=self.m_plane,values=['3D','XZ','XY','YZ'],width=4,state='readonly');combo.pack(side='left',padx=12)
        combo.bind('<<ComboboxSelected>>',lambda e:self.rebuild(True))
        self.m_templates=tk.BooleanVar(value=False)
        ttk.Checkbutton(bar,text='Include templates / effects',variable=self.m_templates,command=lambda:self.rebuild(True)).pack(side='left')
        panes=ttk.Panedwindow(root,orient='horizontal');panes.pack(fill='both',expand=True)
        left=ttk.Frame(panes);panes.add(left,weight=1)
        ttk.Label(left,text='Authored hierarchy',padding=6).pack(anchor='w')
        search=ttk.Frame(left);search.pack(fill='x');self.m_search=tk.StringVar()
        entry=ttk.Entry(search,textvariable=self.m_search);entry.pack(side='left',fill='x',expand=True);entry.bind('<Return>',lambda e:self.find_next())
        ttk.Button(search,text='Find next',command=self.find_next).pack(side='right')
        self.m_tree=ttk.Treeview(left,columns=('kind',),selectmode='browse');self.m_tree.heading('#0',text='Node');self.m_tree.heading('kind',text='Kind')
        self.m_tree.column('#0',width=230);self.m_tree.column('kind',width=45,stretch=False)
        scroll=ttk.Scrollbar(left,command=self.m_tree.yview);self.m_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.m_tree.pack(fill='both',expand=True);self.m_tree.bind('<<TreeviewSelect>>',self.select)
        center=ttk.Frame(panes);panes.add(center,weight=4)
        self.m_canvas=tk.Canvas(center,background='#111c26',highlightthickness=0);self.m_canvas.pack(fill='both',expand=True)
        self.m_canvas.bind('<Configure>',lambda e:self.draw());self.m_canvas.bind('<MouseWheel>',self.zoom)
        self.m_canvas.bind('<Button-4>',lambda e:self.zoom(e,1.2));self.m_canvas.bind('<Button-5>',lambda e:self.zoom(e,1/1.2))
        self.m_canvas.bind('<ButtonPress-3>',lambda e:setattr(self,'m_pan',(e.x,e.y)))
        self.m_canvas.bind('<B3-Motion>',self.pan);self.m_canvas.bind('<Button-1>',self.begin_drag)
        self.m_canvas.bind('<B1-Motion>',self.drag_preview);self.m_canvas.bind('<ButtonRelease-1>',self.end_drag)
        right=ttk.Frame(panes,padding=10);panes.add(right,weight=1)
        self.m_name=ttk.Label(right,text='Select a node',wraplength=250);self.m_name.pack(anchor='w',pady=5)
        ttk.Label(right,text='Rotation: radians. Scale: native units.').pack(anchor='w')
        fields=ttk.Frame(right);fields.pack(fill='x',pady=10);self.m_fields=[]
        for row,label in enumerate(('Position X','Position Y','Position Z','Rotation X','Rotation Y','Rotation Z','Scale X','Scale Y','Scale Z')):
            ttk.Label(fields,text=label).grid(row=row,column=0,sticky='w',pady=3)
            value=tk.StringVar();entry=ttk.Entry(fields,textvariable=value,width=16);entry.grid(row=row,column=1,pady=3);self.m_fields.append((value,entry))
        self.m_collision=tk.BooleanVar(value=False)
        ttk.Checkbutton(right,text='3D collision overlay',variable=self.m_collision,command=self.draw).pack(anchor='w',pady=5)
        self.m_apply=ttk.Button(right,text='Apply transform',command=self.apply);self.m_apply.pack(fill='x')
        snap=ttk.Frame(right);snap.pack(fill='x',pady=8);ttk.Label(snap,text='Drag step (0 = off)').pack(side='left')
        self.m_snap=tk.StringVar(value='0');ttk.Entry(snap,textvariable=self.m_snap,width=8).pack(side='right')
        self.m_details=tk.Text(right,width=32,height=19,wrap='word');self.m_details.pack(fill='both',expand=True,pady=10)
        self.m_status=tk.StringVar(value='Open an extracted .stg. Green: collision; blue: mesh origins. Wheel: zoom; right drag: pan.')
        ttk.Label(root,textvariable=self.m_status,padding=6).pack(fill='x')
        for key,command in [('<Control-o>',self.open_dialog),('<Control-s>',self.save_as),('<Control-z>',self.undo),('<Control-y>',self.redo)]:root.bind(key,lambda e,c=command:c())
        if path:self.load(path)

    def discard(self):
        return not self.m_document or self.m_document.m_data==self.m_saved or messagebox.askyesno('Unsaved changes','Discard unsaved changes?',parent=self.m_root)

    def open_dialog(self):
        if not self.discard():return
        path=filedialog.askopenfilename(filetypes=[('Stage scene','*.stg'),('All files','*')])
        if path:self.load(path)

    def load(self,path):
        try:
            document=c_stage_document(path);hit_path=Path(path).with_suffix('.hit')
            hit=parse_hit(hit_path.read_bytes()) if hit_path.exists() else None
            self.m_document=document;self.m_hit=hit;model_path=Path(path).with_suffix('.mdl');self.m_model=parse_model(model_path.read_bytes()) if model_path.exists() else None;self.m_saved=document.m_data;self.m_selected=None
            self.m_tree.delete(*self.m_tree.get_children())
            for node in document.m_scene['nodes']:
                self.m_tree.insert('' if node['parent']<0 else str(node['parent']),'end',iid=str(node['index']),text=node['name'],values=(node['kind'],),open=node['parent']<0)
            self.rebuild(True);self.update_title()
        except (OSError,ValueError,struct.error) as e:messagebox.showerror('Open failed',str(e))

    def update_title(self):
        if self.m_document:self.m_root.title((' * ' if self.m_document.m_data!=self.m_saved else '')+self.m_document.m_path.name+' — Arika stage editor')

    def select(self,event=None):
        if not self.m_document or not self.m_tree.selection():return
        self.m_selected=int(self.m_tree.selection()[0]);node=self.m_document.m_scene['nodes'][self.m_selected]
        self.m_name.configure(text=node['name']+'\nKind %d • offset 0x%X'%(node['kind'],node['offset']))
        editable='translation'in node;values=node.get('translation',[])+node.get('rotation_radians',[])+node.get('scale',[])
        for i,(variable,entry) in enumerate(self.m_fields):
            variable.set(format(values[i],'.9g') if editable else '');entry.configure(state='normal' if editable else 'disabled')
        self.m_apply.configure(state='normal' if editable else 'disabled')
        import json
        details={k:node[k] for k in ('flags','links','references','state_control','opaque_words') if k in node}
        self.m_details.configure(state='normal');self.m_details.delete('1.0','end');self.m_details.insert('end',json.dumps(details,indent=2));self.m_details.configure(state='disabled');self.draw()

    def apply(self):
        if self.m_selected is None:return
        try:
            self.m_document.set_transform(self.m_selected,[float(v.get()) for v,e in self.m_fields]);self.rebuild();self.update_title()
        except (ValueError,OverflowError,struct.error) as e:messagebox.showerror('Invalid transform',str(e))

    def undo(self):
        if self.m_document:self.m_document.undo();self.rebuild();self.select();self.update_title()

    def redo(self):
        if self.m_document:self.m_document.redo();self.rebuild();self.select();self.update_title()

    def save_as(self):
        if not self.m_document:return
        path=filedialog.asksaveasfilename(defaultextension='.stg',initialfile=self.m_document.m_path.stem+'_edited.stg',filetypes=[('Stage scene','*.stg')])
        if not path:return
        try:
            self.m_document.save_as(path);self.m_saved=self.m_document.m_data;self.update_title();self.m_status.set('Saved '+path+' — source file preserved. Pending field text requires Apply before saving.')
        except (OSError,ValueError) as e:messagebox.showerror('Save failed',str(e))

    def export_preview(self):
        if not self.m_document:return
        path=filedialog.asksaveasfilename(defaultextension='.gltf',initialfile=self.m_document.m_path.stem+'_edited.gltf',filetypes=[('glTF scene','*.gltf')])
        if not path:return
        try:
            self.m_root.configure(cursor='watch');self.m_root.update_idletasks()
            report=self.m_document.export_preview(path)
            self.m_status.set('Exported committed scene: %d mesh instances. Pending field text requires Apply.'%report['mesh_instances'])
        except (OSError,ValueError,struct.error) as error:messagebox.showerror('Export failed',str(error))
        finally:self.m_root.configure(cursor='')

    def rebuild(self,fit=False):
        if not self.m_document:return
        scene=self.m_document.m_scene;world=[];axes={'XZ':(0,2),'XY':(0,1),'YZ':(1,2)}.get(self.m_plane.get(),(0,2))
        self.m_points=[];self.m_lines=[];by_hit={o['name']:o for o in self.m_hit['objects']} if self.m_hit else {}
        allowed=set();todo=scene['roots'][:] if self.m_templates.get() else [scene['stage_root']]
        while todo:
            i=todo.pop();allowed.add(i);todo.extend(scene['nodes'][i]['children'])
        for n in scene['nodes']:
            local=identity() if 'translation'not in n else local_matrix(dict(translation=n['translation'],rotation=quaternion([math.degrees(v) for v in n['rotation_radians']]),scale=n['scale']))
            matrix=local if n['parent']<0 else multiply(world[n['parent']],local);world.append(matrix)
            if n['index']not in allowed:continue
            def project(v):return tuple(sum(matrix[a][j]*v[j] for j in range(3))+matrix[a][3] for a in axes)
            self.m_points.append((n['index'],project((0,0,0)),n['kind']))
            for ref in n['references']:
                obj=by_hit.get(ref['name'])
                if obj is None:continue
                for polygon in self.m_hit['polygons'][obj['first_polygon']:obj['first_polygon']+obj['polygon_count']]:
                    if len(self.m_lines)>=5000:break
                    first=polygon['first_vertex'];vertices=self.m_hit['vertices'][first:first+polygon['vertex_count']]
                    points=[project(v[:3]) for v in vertices];self.m_lines.append(points+[points[0]])
        self.m_status.set('%d nodes • %d collision polygons shown (limit 5000). Map preview; runtime controls/visibility not simulated.'%(len(self.m_points),len(self.m_lines)))
        self.m_view3d=prepare(scene,self.m_model,self.m_hit,self.m_templates.get()) if self.m_plane.get()=='3D' else None
        if self.m_view3d:self.m_status.set('3D: left drag orbits; right drag pans; wheel zooms. %d/%d triangles. Untextured diagnostic view.'%(len(self.m_view3d['triangles']),self.m_view3d['total_triangles']))
        if fit:self.fit()
        else:self.draw()

    def screen(self,p):return (p[0]*self.m_scale+self.m_offset[0],-p[1]*self.m_scale+self.m_offset[1])

    def fit(self):
        points=[p for line in self.m_lines for p in line]+[p for i,p,k in self.m_points]
        if self.m_view3d:points=[project(p,self.m_yaw,self.m_pitch)[:2] for i,triangle in self.m_view3d['triangles'] for p in triangle]+[project(p,self.m_yaw,self.m_pitch)[:2] for i,p,k in self.m_view3d['points']]
        if not points:return
        lo=[min(p[a] for p in points) for a in range(2)];hi=[max(p[a] for p in points) for a in range(2)]
        w=max(400,self.m_canvas.winfo_width());h=max(400,self.m_canvas.winfo_height())
        self.m_scale=min((w-50)/max(1,hi[0]-lo[0]),(h-50)/max(1,hi[1]-lo[1]))
        self.m_offset=[w/2-(lo[0]+hi[0])/2*self.m_scale,h/2+(lo[1]+hi[1])/2*self.m_scale];self.draw()

    def draw(self):
        if getattr(self,'m_render_job',None) is None:self.m_render_job=self.m_root.after(25,self.draw_now)

    def draw_now(self):
        self.m_render_job=None
        c=self.m_canvas;c.delete('all')
        if self.m_view3d:
            self.draw_3d();return
        for line in self.m_lines:c.create_line(*[v for p in line for v in self.screen(p)],fill='#47896e')
        for index,p,kind in self.m_points:
            if kind!=2 and index!=self.m_selected:continue
            x,y=self.screen(p);r=5 if index==self.m_selected else 2
            c.create_oval(x-r,y-r,x+r,y+r,fill='#ffcf66' if index==self.m_selected else '#65aee8',outline='')
            if index==self.m_selected:c.create_text(x+9,y-10,text=self.m_document.m_scene['nodes'][index]['name'],anchor='w',fill='#ffcf66')

    def draw_3d(self):
        c=self.m_canvas;data=self.m_view3d
        try:
            from PIL import ImageTk
            image=render_image(data,c.winfo_width(),c.winfo_height(),self.m_yaw,self.m_pitch,self.m_scale,self.m_offset,self.m_selected,self.m_collision.get())
            self.m_frame_photo=ImageTk.PhotoImage(image,master=c)
            c.create_image(0,0,anchor='nw',image=self.m_frame_photo)
        except ImportError:
            c.create_text(20,30,anchor='nw',fill='white',text='3D viewport needs Pillow. Run: python -m pip install Pillow')
            return
        self.m_points=[(i,project(p,self.m_yaw,self.m_pitch)[:2],k) for i,p,k in data['points']]
        for i,p,k in self.m_points:
            if i==self.m_selected:
                x,y=self.screen(p);c.create_oval(x-5,y-5,x+5,y+5,outline='#ffcf66',width=2)
                c.create_text(x+8,y-10,text=self.m_document.m_scene['nodes'][i]['name'],anchor='w',fill='#ffcf66')

    def zoom(self,event,factor=None):
        factor=factor or (1.2 if event.delta>0 else 1/1.2)
        if not 1e-6<self.m_scale*factor<1e6:return
        self.m_offset=[event.x+(self.m_offset[0]-event.x)*factor,event.y+(self.m_offset[1]-event.y)*factor];self.m_scale*=factor;self.draw()

    def pan(self,event):
        if self.m_pan:
            self.m_offset[0]+=event.x-self.m_pan[0];self.m_offset[1]+=event.y-self.m_pan[1];self.m_pan=(event.x,event.y);self.draw()

    def pick(self,event):
        options=[((self.screen(p)[0]-event.x)**2+(self.screen(p)[1]-event.y)**2,i) for i,p,k in self.m_points if k==2]
        if options:
            distance,index=min(options)
            if distance<144:self.m_tree.selection_set(str(index));self.m_tree.see(str(index))

    def find_next(self):
        if not self.m_document:return
        query=self.m_search.get().strip().casefold()
        if not query:return
        matches=[n['index'] for n in self.m_document.m_scene['nodes'] if query in n['name'].casefold()]
        if not matches:self.m_status.set('No matching node');return
        index=next((i for i in matches if self.m_selected is None or i>self.m_selected),matches[0])
        self.m_tree.selection_set(str(index));self.m_tree.see(str(index));self.select()
        self.m_status.set('%d matches — Find next cycles through them'%len(matches))

    def begin_drag(self,event):
        if self.m_view3d:
            self.m_orbit=(event.x,event.y);self.pick(event);return
        options=[((self.screen(p)[0]-event.x)**2+(self.screen(p)[1]-event.y)**2,i) for i,p,k in self.m_points if k==2 or i==self.m_selected]
        self.m_drag=None
        if not options:return
        distance,index=min(options)
        if distance>=144:return
        self.m_tree.selection_set(str(index));self.m_tree.see(str(index));self.select()
        if 'translation'in self.m_document.m_scene['nodes'][index]:self.m_drag=(event.x,event.y,index)

    def drag_preview(self,event):
        if self.m_orbit:
            x,y=self.m_orbit;self.m_yaw+=(event.x-x)*.008;self.m_pitch=max(-1.5,min(1.5,self.m_pitch+(event.y-y)*.008));self.m_orbit=(event.x,event.y);self.draw();return
        if self.m_drag:
            x,y,index=self.m_drag;self.m_canvas.delete('drag')
            self.m_canvas.create_line(x,y,event.x,event.y,fill='#ffcf66',dash=(4,3),tags='drag')
            self.m_status.set('Move delta: %.3f, %.3f native units — release to apply'%((event.x-x)/self.m_scale,-(event.y-y)/self.m_scale))

    def end_drag(self,event):
        if self.m_orbit:self.m_orbit=None;return
        if not self.m_drag:return
        x,y,index=self.m_drag;self.m_drag=None;self.m_canvas.delete('drag')
        if (event.x-x)**2+(event.y-y)**2<9:return
        try:
            scene=self.m_document.m_scene;node=scene['nodes'][index]
            dx,dy=snapped_delta((event.x-x)/self.m_scale,-(event.y-y)/self.m_scale,float(self.m_snap.get()))
            position=moved_translation(scene,index,dx,dy,self.m_plane.get())
            self.m_document.set_transform(index,position+node['rotation_radians']+node['scale'])
            self.rebuild();self.select();self.update_title()
        except (ValueError,OverflowError,struct.error) as error:messagebox.showerror('Move failed',str(error))

    def close(self):
        if self.discard():self.m_root.destroy()


if __name__=='__main__':
    if '--legacy' not in sys.argv:
        try:
            from arika_scene_editor import main
            sys.exit(main())
        except ModuleNotFoundError as error:
            print('Scene editor dependency missing: '+str(error)+'\nInstall: python -m pip install -r requirements_scene_editor.txt',file=sys.stderr)
            sys.exit(1)
    sys.argv.remove('--legacy')
    root=tk.Tk();c_stage_editor(root,sys.argv[1] if len(sys.argv)>1 else None);root.mainloop()
