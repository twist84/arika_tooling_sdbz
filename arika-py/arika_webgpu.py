"""WebGPU stage renderer. Uses D3D12/Vulkan/Metal; no OpenGL fallback."""
import os
import sys
os.environ.setdefault('WGPU_BACKEND_TYPE','D3D12' if sys.platform=='win32' else 'Metal' if sys.platform=='darwin' else 'Vulkan')
if os.environ['WGPU_BACKEND_TYPE'].lower() not in ('d3d12','vulkan','metal'):
    raise RuntimeError('Use the D3D12, Vulkan or Metal WebGPU backend')
import base64
import io
import json
import math
from pathlib import Path
import tempfile
import numpy as np
from PIL import Image
try:
    import wgpu
except ImportError:  # Pure camera/color helpers and unit tests do not need a GPU runtime.
    wgpu = None
from arika_import import c_gltf_reader
from arika_models import identity,local_matrix,multiply
from arika_scene_state import selection_nodes,hidden_nodes
from arika_gizmo import gizmo_geometry


def srgb_to_linear(value):
    return value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4


def linear_to_srgb(value):
    return value*12.92 if value<=.0031308 else 1.055*value**(1/2.4)-.055


# Store picker colors as sRGB. Preserve the prior default on sRGB surfaces.
DEFAULT_BACKGROUND=tuple(linear_to_srgb(v) for v in (.035,.045,.06))+(1,)


def background_clear_color(color,texture_format):
    # sRGB render attachments encode linear clear values in hardware. Qt's
    # picker supplies display-encoded RGB, so decode once before that write.
    if str(texture_format).endswith('-srgb'):
        return tuple(srgb_to_linear(v) for v in color[:3])+(color[3],)
    return tuple(color)


SHADER='''
struct Camera { matrix: mat4x4<f32> };
struct Object { matrix: mat4x4<f32>, color: vec4<f32>, params: vec4<f32> };
@group(0) @binding(0) var<uniform> camera: Camera;
@group(1) @binding(0) var<uniform> object: Object;
@group(1) @binding(1) var tex_sampler: sampler;
@group(1) @binding(2) var tex: texture_2d<f32>;
struct VOut { @builtin(position) position: vec4<f32>, @location(0) uv: vec2<f32> };
@vertex fn vs(@location(0) position: vec3<f32>, @location(1) uv: vec2<f32>) -> VOut {
 var out: VOut; out.position=camera.matrix*object.matrix*vec4(position,1.0); out.uv=uv; return out;
}
struct FOut { @location(0) color: vec4<f32>, @location(1) id: vec4<f32> };
@fragment fn fs(input: VOut) -> FOut {
 var color=object.color;
 if object.params.x>0.5 {color=color*textureSample(tex,tex_sampler,input.uv);}
 if object.params.y>=0.0 && color.a<object.params.y {discard;}
 if object.params.z>0.5 {color=vec4(mix(color.rgb,vec3(1.0,0.5,0.05),0.3),color.a);}
 let id=u32(object.params.w);
 var out:FOut;out.color=color;out.id=vec4(f32(id&255u),f32((id>>8u)&255u),f32((id>>16u)&255u),255.0)/255.0;return out;
}
'''


def camera_matrix(center,distance,yaw,pitch,aspect,orthographic=False):
    y=math.radians(yaw);p=math.radians(pitch);cy,sy=math.cos(y),math.sin(y);cp,sp=math.cos(p),math.sin(p)
    ry=np.array([[cy,0,sy,0],[0,1,0,0],[-sy,0,cy,0],[0,0,0,1]],dtype='f4')
    rx=np.array([[1,0,0,0],[0,cp,-sp,0],[0,sp,cp,0],[0,0,0,1]],dtype='f4')
    translation=np.eye(4,dtype='f4');translation[:3,3]=-np.asarray(center)
    view=rx@ry@translation;view[2,3]-=distance
    # Keep the far plane from collapsing as the user zooms toward the scene.
    # A distance-relative far plane alone clips distant stage geometry when
    # the camera gets close to its pivot. Keep a generous world-space floor,
    # while scaling farther out for large scenes and long camera distances.
    far=max(10000.0,distance*20.0)
    near=max(.01,min(distance/1000.0,far/1000000.0))
    f=1/math.tan(math.radians(45)/2)
    projection=np.zeros((4,4),dtype='f4');projection[0,0]=f/aspect;projection[1,1]=f
    if orthographic:
        projection[0,0]/=distance;projection[1,1]/=distance
        projection[2,2]=1/(near-far);projection[2,3]=near/(near-far);projection[3,3]=1
    else:
        projection[2,2]=far/(near-far);projection[2,3]=far*near/(near-far);projection[3,2]=-1
    return projection@view


def viewport_guides(center,distance,grid=True,axes=True):
    """Y-up world guides, with grid spacing adapted to the camera distance."""
    spacing=10**math.floor(math.log10(max(.01,distance*.1)))
    extent=spacing*10;cx=round(center[0]/spacing)*spacing;cz=round(center[2]/spacing)*spacing
    groups=[]
    if grid:
        lines=[]
        for i in range(-10,11):
            lines.extend(((cx+i*spacing,0,cz-extent),(cx+i*spacing,0,cz+extent),(cx-extent,0,cz+i*spacing),(cx+extent,0,cz+i*spacing)))
        groups.append((lines,(.18,.20,.23,1)))
    if axes:
        for axis,color in ((0,(.8,.12,.1,1)),(1,(.15,.7,.2,1)),(2,(.15,.35,.9,1))):
            a=[0,0,0];b=[0,0,0];a[axis]=-extent;b[axis]=extent;groups.append(([a,b],color))
    return groups


class c_webgpu_renderer:
    def __init__(self,canvas=None,format='rgba8unorm'):
        if wgpu is None:
            raise RuntimeError('WebGPU rendering requires the optional wgpu package; install requirements_scene_editor.txt')
        self.m_adapter=wgpu.gpu.request_adapter_sync(power_preference='high-performance',canvas=canvas)
        self.m_device=self.m_adapter.request_device_sync();self.m_context=canvas.get_wgpu_context() if canvas else None
        self.m_format=self.m_context.get_preferred_format(self.m_adapter) if canvas else format
        if self.m_context:self.m_context.configure(device=self.m_device,format=self.m_format)
        d=self.m_device;visibility=wgpu.ShaderStage.VERTEX|wgpu.ShaderStage.FRAGMENT
        self.m_camera_layout=d.create_bind_group_layout(entries=[dict(binding=0,visibility=visibility,buffer=dict(type='uniform'))])
        self.m_object_layout=d.create_bind_group_layout(entries=[dict(binding=0,visibility=visibility,buffer=dict(type='uniform')),dict(binding=1,visibility=wgpu.ShaderStage.FRAGMENT,sampler=dict(type='filtering')),dict(binding=2,visibility=wgpu.ShaderStage.FRAGMENT,texture=dict(sample_type='float',view_dimension='2d',multisampled=False))])
        self.m_layout=d.create_pipeline_layout(bind_group_layouts=[self.m_camera_layout,self.m_object_layout]);self.m_shader=d.create_shader_module(code=SHADER)
        self.m_camera=d.create_buffer(size=64,usage=wgpu.BufferUsage.UNIFORM|wgpu.BufferUsage.COPY_DST)
        self.m_camera_group=d.create_bind_group(layout=self.m_camera_layout,entries=[dict(binding=0,resource=dict(buffer=self.m_camera))])
        self.m_sampler=d.create_sampler(address_mode_u='repeat',address_mode_v='repeat',mag_filter='linear',min_filter='linear',mipmap_filter='linear')
        self.m_pipelines={};self.m_size=None;self.m_project=None;self.m_meshes={};self.m_textures=[];self.m_instances=[];self.m_depth=None;self.m_pick=None
        self.m_hidden=set();self.m_selection_cache={}
        self.m_white=self.texture(Image.new('RGBA',(1,1),'white'));self.m_center=[0,0,0];self.m_distance=1000

    def texture(self,image):
        image=image.convert('RGBA');w,h=image.size;levels=int(math.log2(max(w,h)))+1
        texture=self.m_device.create_texture(size=(w,h,1),format='rgba8unorm-srgb',mip_level_count=levels,usage=wgpu.TextureUsage.TEXTURE_BINDING|wgpu.TextureUsage.COPY_DST)
        for level in range(levels):
            mip=image.resize((max(1,w>>level),max(1,h>>level)),Image.Resampling.BILINEAR)
            self.m_device.queue.write_texture(dict(texture=texture,mip_level=level),mip.tobytes(),dict(bytes_per_row=mip.width*4,rows_per_image=mip.height),(mip.width,mip.height,1))
        return texture

    def pipeline(self,topology,blend,cull,overlay=False):
        key=(topology,blend,cull,overlay)
        if key not in self.m_pipelines:
            target=dict(format=self.m_format)
            if blend:target['blend']=dict(color=dict(src_factor='src-alpha',dst_factor='one-minus-src-alpha',operation='add'),alpha=dict(src_factor='one',dst_factor='one-minus-src-alpha',operation='add'))
            self.m_pipelines[key]=self.m_device.create_render_pipeline(layout=self.m_layout,vertex=dict(module=self.m_shader,entry_point='vs',buffers=[dict(array_stride=20,step_mode='vertex',attributes=[dict(shader_location=0,offset=0,format='float32x3'),dict(shader_location=1,offset=12,format='float32x2')])]),primitive=dict(topology=topology,cull_mode='back' if cull else 'none',front_face='ccw'),depth_stencil=dict(format='depth24plus',depth_write_enabled=not blend and not overlay,depth_compare='always' if overlay else 'less-equal'),fragment=dict(module=self.m_shader,entry_point='fs',targets=[target,dict(format='rgba8unorm')]))
        return self.m_pipelines[key]

    @staticmethod
    def _destroy_resource(resource):
        destroy=getattr(resource,'destroy',None)
        if callable(destroy):
            try:destroy()
            except Exception:pass

    def _destroy_instance_resources(self,instances):
        destroyed=set()
        for instance in instances:
            resources=[instance.get('uniform')]
            resources.extend(binding[0] for binding in instance.get('bindings',{}).values())
            for resource in resources:
                if resource is not None and id(resource) not in destroyed:
                    destroyed.add(id(resource));self._destroy_resource(resource)

    def _destroy_geometry_resources(self):
        destroyed=set()
        for parts in self.m_meshes.values():
            for part in parts:
                for name in ('vbo','ibo','edge'):
                    resource=part.get(name)
                    if resource is not None and id(resource) not in destroyed:
                        destroyed.add(id(resource));self._destroy_resource(resource)
        for texture in self.m_textures:
            if texture is not None and id(texture) not in destroyed:
                destroyed.add(id(texture));self._destroy_resource(texture)

    def selection_nodes_cached(self,selected):
        # Keep the helper usable on lightweight renderer instances used by tests/tools.
        cache=getattr(self,'m_selection_cache',None)
        if cache is None:
            cache={}
            self.m_selection_cache=cache
        if isinstance(selected,int):key=('index',selected)
        else:key=('indices',tuple(sorted(selected)))
        if key not in cache:
            if len(cache)>=32:cache.pop(next(iter(cache)))
            document=self.m_project.m_document if self.m_project else {}
            cache[key]=selection_nodes(document,selected)
        return cache[key]

    def set_project(self,project,geometry=True,fit=False):
        same_project=self.m_project is project
        rebuild_geometry=bool(geometry or not self.m_meshes or not same_project)
        previous_instances={}
        if rebuild_geometry:
            self._destroy_instance_resources(self.m_instances)
            self._destroy_geometry_resources()
            self.m_instances=[];self.m_meshes={};self.m_textures=[];self.m_bounds={}
        else:
            previous_instances={(item['index'],item['mesh'],item['collision']):item for item in self.m_instances}
            self.m_instances=[]
        self.m_project=project;doc=project.m_document;d=self.m_device
        self.m_hidden=hidden_nodes(doc);self.m_selection_cache.clear()
        if rebuild_geometry:
            for entry in doc.get('textures',[]):
                raw=base64.b64decode(doc['images'][entry['source']]['uri'].split(',',1)[1])
                with Image.open(io.BytesIO(raw)) as image:self.m_textures.append(self.texture(image))
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'scene.gltf';path.write_text(json.dumps(doc));reader=c_gltf_reader(path);accessors={};vbos={}
                def values(i):
                    if i not in accessors:accessors[i]=np.asarray(reader.accessor(i))
                    return accessors[i]
                for mi,mesh in enumerate(doc['meshes']):
                    parts=[];bounds=[]
                    for part in mesh['primitives']:
                        pos=part['attributes']['POSITION'];uv=part['attributes'].get('TEXCOORD_0');key=(pos,uv);positions=values(pos)
                        if key not in vbos:
                            data=np.hstack((positions,values(uv) if uv is not None else np.zeros((len(positions),2)))).astype('f4')
                            vbos[key]=d.create_buffer_with_data(data=data,usage=wgpu.BufferUsage.VERTEX)
                        ids=values(part['indices']).astype('u4').reshape(-1);mode=part.get('mode',4)
                        edges=ids if mode==1 else ids.reshape(-1,3)[:,[0,1,1,2,2,0]].reshape(-1)
                        ibo=d.create_buffer_with_data(data=ids,usage=wgpu.BufferUsage.INDEX);edge=d.create_buffer_with_data(data=edges,usage=wgpu.BufferUsage.INDEX)
                        parts.append(dict(vbo=vbos[key],ibo=ibo,count=len(ids),edge=edge,edge_count=len(edges),mode=mode,material=part.get('material',-1)))
                        bounds.extend((positions.min(axis=0),positions.max(axis=0)))
                    self.m_meshes[mi]=parts;self.m_bounds[mi]=(np.min(bounds,axis=0),np.max(bounds,axis=0))
        world_bounds=[]
        def walk(index,parent,collision=False):
            node=doc['nodes'][index];local=local_matrix(dict(translation=node.get('translation',[0,0,0]),rotation=node.get('rotation',[0,0,0,1]),scale=node.get('scale',[1,1,1])));matrix=multiply(parent,local)
            if 'mesh'in node:
                mesh=node['mesh'];key=(index,mesh,collision);instance=previous_instances.pop(key,None)
                if instance is None:
                    # Per-material uniforms are allocated lazily in render(); a separate
                    # per-instance uniform was never bound and only consumed GPU memory.
                    instance=dict(index=index,mesh=mesh,matrix=matrix,collision=collision,bindings={})
                else:
                    instance['matrix']=matrix
                self.m_instances.append(instance)
                if not collision and index not in self.m_hidden:
                    lo,hi=self.m_bounds[mesh]
                    for x in (lo[0],hi[0]):
                        for y in (lo[1],hi[1]):
                            for z in (lo[2],hi[2]):world_bounds.append((np.asarray(matrix)@np.array([x,y,z,1]))[:3])
            for child in node.get('children',[]):walk(child,matrix,collision)
        for root in doc['scenes'][doc.get('scene',0)]['nodes']:walk(root,identity())
        for scene in doc['scenes']:
            if scene.get('name')=='Collision':
                for root in scene['nodes']:walk(root,identity(),True)
        if previous_instances:self._destroy_instance_resources(previous_instances.values())
        if fit and world_bounds:
            lo=np.min(world_bounds,axis=0);hi=np.max(world_bounds,axis=0);self.m_center=((lo+hi)/2).tolist();self.m_distance=max(1,float(np.linalg.norm(hi-lo))*1.05)
        self.m_dirty=True

    def draw_guides(self,render,center,distance,options):
        guides=viewport_guides(center,distance,options.get('grid',False),options.get('axes',False))
        key=repr(guides)
        if getattr(self,'m_guides_key',None)!=key:
            for buffer,uniform,_,_ in getattr(self,'m_guides',[]):buffer.destroy();uniform.destroy()
            self.m_guides=[];d=self.m_device
            for positions,color in guides:
                vertices=np.hstack((np.asarray(positions),np.zeros((len(positions),2)))).astype('f4')
                buffer=d.create_buffer_with_data(data=vertices,usage=wgpu.BufferUsage.VERTEX)
                body=np.concatenate((np.eye(4,dtype='f4').reshape(-1),color,[0,-1,0,0])).astype('f4')
                uniform=d.create_buffer_with_data(data=body,usage=wgpu.BufferUsage.UNIFORM)
                group=d.create_bind_group(layout=self.m_object_layout,entries=[dict(binding=0,resource=dict(buffer=uniform)),dict(binding=1,resource=self.m_sampler),dict(binding=2,resource=self.m_white.create_view())])
                self.m_guides.append((buffer,uniform,group,len(positions)))
            self.m_guides_key=key
        if self.m_guides:
            render.set_pipeline(self.pipeline('line-list',False,False))
            for buffer,_,group,count in self.m_guides:
                render.set_bind_group(1,group);render.set_vertex_buffer(0,buffer);render.draw(count)

    def draw_gizmo(self,render,gizmo):
        if not gizmo:return
        d=self.m_device
        key=(gizmo['mode'],tuple(gizmo['position']),tuple(tuple(axis) for axis in gizmo['axes']),
             tuple(tuple(axis) for axis in gizmo.get('view_axes',[])),gizmo.get('orientation'),gizmo.get('pivot'),gizmo.get('hover_handle'),gizmo['size'],gizmo['enabled'])
        if getattr(self,'m_gizmo_key',None)!=key:
            geometry=gizmo_geometry(gizmo['position'],gizmo['axes'],gizmo['size'],gizmo['mode'],include_extra=True,view_axes=gizmo.get('view_axes'))
            for buffer,uniform,_,_ in getattr(self,'m_gizmo_lines',[]):buffer.destroy();uniform.destroy()
            self.m_gizmo_lines=[]
            colors={0:(.92,.18,.16,1),1:(.2,.88,.32,1),2:(.22,.48,1,1),
                'plane_xy':(.88,.25,.58,1),'plane_xz':(.9,.58,.18,1),'plane_yz':(.18,.75,.82,1),
                'plane_view':(.95,.95,.95,1),'uniform':(.98,.98,.98,1),'view':(.96,.96,.96,1),
                'trackball':(.68,.72,.78,1)}
            for operation in ('move','rotate','scale'):
                for axis,name in enumerate(('x','y','z')):colors[operation+'_'+name]=colors[axis]
                for name in ('plane_xy','plane_xz','plane_yz','plane_view','uniform','view','trackball'):
                    colors[operation+'_'+name]=colors[name]
            if not gizmo['enabled']:colors={axis:(.42,.42,.42,1) for axis in colors}
            elif gizmo.get('hover_handle') in colors:
                hovered=gizmo['hover_handle'];color=colors[hovered]
                colors[hovered]=tuple(min(1.0,v*1.28+.08) for v in color[:3])+(1.0,)
            for axis,segments in geometry.items():
                vertices=[]
                for a,b in segments:vertices.extend(((*a,0,0),(*b,0,0)))
                if not vertices:continue
                buffer=d.create_buffer_with_data(data=np.asarray(vertices,dtype='f4'),usage=wgpu.BufferUsage.VERTEX)
                body=np.concatenate((np.eye(4,dtype='f4').reshape(-1),np.asarray(colors.get(axis,(.9,.9,.9,1)),dtype='f4'),[0,-1,0,0])).astype('f4')
                uniform=d.create_buffer_with_data(data=body,usage=wgpu.BufferUsage.UNIFORM)
                group=d.create_bind_group(layout=self.m_object_layout,entries=[dict(binding=0,resource=dict(buffer=uniform)),dict(binding=1,resource=self.m_sampler),dict(binding=2,resource=self.m_white.create_view())])
                self.m_gizmo_lines.append((buffer,uniform,group,len(vertices)))
            self.m_gizmo_key=key
        if self.m_gizmo_lines:
            render.set_pipeline(self.pipeline('line-list',False,False,overlay=True))
            for buffer,_,group,count in self.m_gizmo_lines:
                render.set_bind_group(1,group);render.set_vertex_buffer(0,buffer);render.draw(count)

    def render(self,width,height,yaw,pitch,center,distance,mode='Textured',selected=-1,collision=False,target=None,orthographic=False,isolated=None,options=None,gizmo=None):
        options=options or {}
        selection=self.selection_nodes_cached(selected)
        if not options.get('highlight',True):selection=set()
        hidden=self.m_hidden
        scope=self.selection_nodes_cached(isolated) if isolated is not None else None
        d=self.m_device;width=max(1,width);height=max(1,height)
        if self.m_size!=(width,height):
            if self.m_depth:self.m_depth.destroy();self.m_pick.destroy()
            self.m_depth=d.create_texture(size=(width,height,1),format='depth24plus',usage=wgpu.TextureUsage.RENDER_ATTACHMENT)
            self.m_pick=d.create_texture(size=(width,height,1),format='rgba8unorm',usage=wgpu.TextureUsage.RENDER_ATTACHMENT|wgpu.TextureUsage.COPY_SRC);self.m_size=(width,height)
        target=target or self.m_context.get_current_texture()
        d.queue.write_buffer(self.m_camera,0,camera_matrix(center,distance,yaw,pitch,width/height,orthographic).T.astype('f4').tobytes())
        background=background_clear_color(options.get('background',DEFAULT_BACKGROUND),self.m_format)
        encoder=d.create_command_encoder();render=encoder.begin_render_pass(color_attachments=[dict(view=target.create_view(),resolve_target=None,clear_value=background,load_op='clear',store_op='store'),dict(view=self.m_pick.create_view(),resolve_target=None,clear_value=(0,0,0,0),load_op='clear',store_op='store')],depth_stencil_attachment=dict(view=self.m_depth.create_view(),depth_clear_value=1,depth_load_op='clear',depth_store_op='store'))
        render.set_bind_group(0,self.m_camera_group)
        if self.m_project:
            doc=self.m_project.m_document
            for instance in self.m_instances:
                if instance['index'] in hidden:continue
                if scope is not None and instance['index'] not in scope:continue
                if instance['collision'] and not collision:continue
                for part in self.m_meshes[instance['mesh']]:
                    mi=part['material'];material=doc['materials'][mi] if mi>=0 else {};pbr=material.get('pbrMetallicRoughness',{});textured=mode=='Textured' and not instance['collision'];ti=pbr.get('baseColorTexture',{}).get('index',-1)
                    texture=self.m_textures[ti] if textured and 0<=ti<len(self.m_textures) else self.m_white
                    color=pbr.get('baseColorFactor',[1,1,1,1]) if mode=='Textured' else [.55,.65,.75,1]
                    if instance['collision']:color=[.1,.9,.25,1]
                    params=[float(textured and ti>=0),material.get('alphaCutoff',.5) if material.get('alphaMode')=='MASK' else -1,float(instance['index'] in selection),float(instance['index']+1) if not instance['collision'] else 0]
                    body=np.concatenate((np.asarray(instance['matrix'],dtype='f4').T.reshape(-1),color,params)).astype('f4').tobytes()
                    # One uniform per material part: queue writes execute before the pass.
                    key=(mi,ti,textured,mode)
                    if key not in instance['bindings']:
                        # A material's texture can change while editing. Retire its old binding instead
                        # of accumulating a new GPU uniform for every previous texture assignment.
                        stale=[old_key for old_key in instance['bindings'] if old_key[0]==mi and old_key[2]==textured and old_key[3]==mode and old_key!=key]
                        for old_key in stale:
                            old_uniform,_,_=instance['bindings'].pop(old_key);self._destroy_resource(old_uniform)
                        uniform=d.create_buffer(size=96,usage=wgpu.BufferUsage.UNIFORM|wgpu.BufferUsage.COPY_DST)
                        group=d.create_bind_group(layout=self.m_object_layout,entries=[dict(binding=0,resource=dict(buffer=uniform)),dict(binding=1,resource=self.m_sampler),dict(binding=2,resource=texture.create_view())])
                        instance['bindings'][key]=(uniform,group,None)
                    uniform,group,old=instance['bindings'][key]
                    if body!=old:d.queue.write_buffer(uniform,0,body);instance['bindings'][key]=(uniform,group,body)
                    wire=mode=='Wireframe' or part['mode']==1;topology='line-list' if wire else 'triangle-list'
                    render.set_pipeline(self.pipeline(topology,material.get('alphaMode')=='BLEND',options.get('cull',False) or not material.get('doubleSided',True)))
                    render.set_bind_group(1,group);render.set_vertex_buffer(0,part['vbo']);render.set_index_buffer(part['edge'] if wire else part['ibo'],'uint32');render.draw_indexed(part['edge_count'] if wire else part['count'])
        self.draw_guides(render,center,distance,options)
        self.draw_gizmo(render,gizmo)
        render.end();d.queue.submit([encoder.finish()])

    def pick(self,x,y):
        if not self.m_pick:return -1
        width,height=self.m_size;x=max(0,min(width-1,x));y=max(0,min(height-1,y))
        data=bytes(self.m_device.queue.read_texture(dict(texture=self.m_pick,origin=(x,y,0)),dict(bytes_per_row=4,rows_per_image=1),(1,1,1)))
        return data[0]+(data[1]<<8)+(data[2]<<16)-1
