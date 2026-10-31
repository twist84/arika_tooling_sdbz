"""Embedded scene projects for the lightweight Qt stage editor."""
import base64
import copy
import json
from pathlib import Path, PurePosixPath
from arika_stage_editor import c_stage_document
from arika_stages import parse_stg,build_stage_gltf
from arika_models import euler_radians,quaternion,require,local_matrix,multiply,identity
from arika_import import write_output
from arika_scene_characters import merge_character


def material_preview_document(document,index):
    import math
    from arika_models import c_gltf
    require(0<=index<len(document['materials']),'invalid preview material')
    g=c_gltf();doc=g.m_document;positions=[];uvs=[];indices=[];rows=24;columns=32
    for row in range(rows+1):
        theta=math.pi*row/rows
        for column in range(columns+1):
            phi=2*math.pi*column/columns
            positions.append([math.sin(theta)*math.cos(phi),math.cos(theta),math.sin(theta)*math.sin(phi)])
            uvs.append([column/columns,row/rows])
    for row in range(rows):
        for column in range(columns):
            a=row*(columns+1)+column;b=a+columns+1;c=b+1;d=a+1
            indices.extend((a,c,b,a,d,c))
    material=copy.deepcopy(document['materials'][index]);pbr=material.get('pbrMetallicRoughness',{})
    if 'baseColorTexture'in pbr:
        texture=copy.deepcopy(document['textures'][pbr['baseColorTexture']['index']]);image=copy.deepcopy(document['images'][texture['source']])
        texture['source']=0;texture.pop('sampler',None);pbr['baseColorTexture']['index']=0;doc['textures']=[texture];doc['images']=[image]
    doc['materials']=[material];doc['meshes']=[dict(name='Material sphere',primitives=[dict(attributes=dict(POSITION=g.array(positions,'VEC3',bounds=True),TEXCOORD_0=g.array(uvs,'VEC2')),indices=g.array(indices,'SCALAR',5125),material=0,mode=4)])]
    doc['nodes']=[dict(name='Material sphere',mesh=0)];doc['scenes']=[dict(name='Material',nodes=[0])]
    doc['buffers']=[dict(byteLength=len(g.m_blob),uri='data:application/octet-stream;base64,'+base64.b64encode(g.m_blob).decode())]
    return doc


class c_scene_project:
    def delete_nodes(self,indices):
        from arika_scene_state import selection_nodes,node_state
        indices=set(indices);nodes=self.m_document['nodes']
        require(all(type(i)is int and 0<=i<len(nodes) for i in indices),'invalid object index')
        removed=selection_nodes(self.m_document,indices)
        if not removed:return dict(count=0,remap={i:i for i in range(len(nodes))})
        require(not any(node_state(self.m_document,i)['locked'] for i in removed),'Unlock selected objects and their children before deleting.')
        mapping={old:new for new,old in enumerate(i for i in range(len(nodes)) if i not in removed)}
        document=copy.deepcopy(self.m_document)
        document['nodes']=[node for i,node in enumerate(document['nodes']) if i in mapping]
        for node in document['nodes']:
            if 'children' in node:node['children']=[mapping[i] for i in node['children'] if i in mapping]
        for scene in document['scenes']:scene['nodes']=[mapping[i] for i in scene['nodes'] if i in mapping]
        # Keep optional skin/animation references valid in project glTF too.
        used_skins=sorted({node['skin'] for node in document['nodes'] if 'skin' in node})
        skin_mapping={old:new for new,old in enumerate(used_skins)}
        skins=[]
        for i in used_skins:
            skin=document['skins'][i]
            require(all(j in mapping for j in skin['joints']),'Cannot delete joints used by a remaining skinned mesh.')
            skin['joints']=[mapping[j] for j in skin['joints']]
            if 'skeleton' in skin:
                if skin['skeleton'] in mapping:skin['skeleton']=mapping[skin['skeleton']]
                else:skin.pop('skeleton')
            skins.append(skin)
        if skins:document['skins']=skins
        else:document.pop('skins',None)
        for node in document['nodes']:
            if 'skin' in node:node['skin']=skin_mapping[node['skin']]
        for animation in document.get('animations',[]):
            channels=[]
            for channel in animation['channels']:
                target=channel['target']
                if 'node' not in target or target['node'] in mapping:
                    if 'node' in target:target['node']=mapping[target['node']]
                    channels.append(channel)
            animation['channels']=channels
        if 'animations' in document:
            document['animations']=[a for a in document['animations'] if a['channels']]
            if not document['animations']:document.pop('animations')
        self.checkpoint();self.m_document=document
        return dict(count=len(removed),remap=mapping)

    def _gltf_parents(self):
        nodes=self.m_document.get('nodes',[])
        parents={}
        for parent,node in enumerate(nodes):
            for child in node.get('children',[]):
                parents[child]=parent
        return parents

    def _gltf_worlds(self):
        nodes=self.m_document.get('nodes',[])
        parents=self._gltf_parents()
        worlds=[None]*len(nodes)
        visiting=set()
        def local_matrix_for(index):
            node=nodes[index]
            if 'matrix' in node:
                values=node['matrix']
                return [[values[c*4+r] for c in range(4)] for r in range(4)]
            return local_matrix(dict(translation=node.get('translation',[0,0,0]),rotation=node.get('rotation',[0,0,0,1]),scale=node.get('scale',[1,1,1])))
        def resolve(index):
            if worlds[index] is not None:return worlds[index]
            require(index not in visiting,'node parent cycle')
            visiting.add(index)
            parent=parents.get(index)
            parent_matrix=identity() if parent is None else resolve(parent)
            worlds[index]=multiply(parent_matrix,local_matrix_for(index))
            visiting.remove(index)
            return worlds[index]
        for index in range(len(nodes)):resolve(index)
        return parents,worlds

    def duplicate_nodes(self,indices):
        nodes=self.m_document.get('nodes',[])
        if isinstance(indices,int):indices=[indices]
        indices=list(indices)
        require(all(type(i) is int and 0<=i<len(nodes) for i in indices),'invalid object index')
        parents=self._gltf_parents()
        def ancestors(index):
            result=[];cur=parents.get(index)
            while cur is not None:
                result.append(cur);cur=parents.get(cur)
            return result
        selected=set(indices)
        roots=[i for i in sorted(selected) if not (selected & set(ancestors(i)))]
        if not roots:return dict(count=0,mapping={},new_indices=[],indices=[],new=[])
        def collect(root):
            result=[root]
            for child in nodes[root].get('children',[]):result.extend(collect(child))
            return result
        ordered=[]
        for root in roots:
            for old in collect(root):
                if old not in ordered:ordered.append(old)
        mapping={old:len(nodes)+k for k,old in enumerate(ordered)}
        # validate subtree indices
        new_nodes=[]
        for old in ordered:
            new_node=copy.deepcopy(nodes[old])
            if old in roots:
                new_node['name']=str(nodes[old].get('name','Node %d'%old))+' (copy)'
            if 'children' in new_node:
                new_node['children']=[mapping[c] for c in nodes[old].get('children',[]) if c in mapping]
            new_nodes.append(new_node)
        # checkpoint once
        self.checkpoint()
        nodes.extend(new_nodes)
        # attach roots
        scene_list=self.m_document.setdefault('scenes',[])
        for root in roots:
            new_root=mapping[root]
            parent=parents.get(root)
            if parent is None:
                for scene in scene_list:
                    if root in scene.get('nodes',[]) and new_root not in scene.get('nodes',[]):
                        scene.setdefault('nodes',[]).append(new_root)
                if not any(root in scene.get('nodes',[]) for scene in scene_list):
                    if scene_list:scene_list[0].setdefault('nodes',[]).append(new_root)
            else:
                self.m_document['nodes'][parent].setdefault('children',[]).append(new_root)
        new_indices=[mapping[root] for root in roots]
        return dict(count=len(roots),mapping=mapping,new_indices=new_indices,indices=new_indices,new=new_indices)

    def set_node_parent(self,index,parent):
        return self.reparent_nodes(index,parent)

    def reparent_nodes(self,indices,parent):
        nodes=self.m_document.get('nodes',[])
        if isinstance(indices,int):indices=[indices]
        indices=list(indices)
        require(all(type(i) is int and 0<=i<len(nodes) for i in indices),'invalid object index')
        # normalize parent
        if parent is None or parent==-1:
            parent=None
        else:
            require(type(parent) is int and 0<=parent<len(nodes),'invalid parent index')
        parents=self._gltf_parents()
        def ancestors(index):
            result=[];cur=parents.get(index)
            while cur is not None:
                result.append(cur);cur=parents.get(cur)
            return result
        selected=set(indices)
        roots=[i for i in sorted(selected) if not (selected & set(ancestors(i)))]
        # filter valid roots
        # lock check: moved roots and descendants unlocked
        from arika_scene_state import selection_nodes,node_state
        moved_nodes=set()
        for root in roots:moved_nodes |= selection_nodes(self.m_document,{root})
        require(not any(node_state(self.m_document,i)['locked'] for i in moved_nodes),'Unlock selected objects and their children before moving.')
        # cycle checks
        for root in roots:
            if parent==root:raise ValueError('Cannot move an object into itself.')
            if parent is not None and parent in selection_nodes(self.m_document,{root}):raise ValueError('Cannot move an object into its descendant.')
        # if parent is one of roots? reject
        if parent is not None and parent in roots:raise ValueError('Cannot move an object into its descendant.')
        # compute old worlds before mutation
        old_parents,old_worlds=self._gltf_worlds()
        new_parent_matrix=identity() if parent is None else old_worlds[parent]
        try:
            new_parent_inverse=__import__('numpy').linalg.inv(__import__('numpy').asarray(new_parent_matrix,dtype=float)) if False else None
        except Exception:
            new_parent_inverse=None
        import numpy as np
        try:new_parent_inverse=np.linalg.inv(np.asarray(new_parent_matrix,dtype=float))
        except np.linalg.LinAlgError:new_parent_inverse=np.eye(4)
        # determine changed
        changed=False
        for root in roots:
            if old_parents.get(root)!=parent:changed=True
        if any('stg_offset' in nodes[i].get('extras',{}) for i in moved_nodes):changed=True
        if not changed:return dict(count=0)
        # checkpoint once
        self.checkpoint()
        original_root_scenes={root:[scene for scene in self.m_document.get('scenes',[]) if root in scene.get('nodes',[])] for root in roots if old_parents.get(root) is None}
        for root in roots:
            old_parent=old_parents.get(root)
            old_world=old_worlds[root]
            new_local=np.asarray(new_parent_inverse,dtype=float)@np.asarray(old_world,dtype=float)
            new_local=new_local.tolist()
            node=nodes[root]
            # apply transform
            if 'matrix' in node:
                # column-major flat
                flat=[new_local[r][c] for c in range(4) for r in range(4)]
                node['matrix']=flat
            else:
                # decompose
                tx=new_local[0][3];ty=new_local[1][3];tz=new_local[2][3]
                col0=[new_local[0][0],new_local[1][0],new_local[2][0]]
                col1=[new_local[0][1],new_local[1][1],new_local[2][1]]
                col2=[new_local[0][2],new_local[1][2],new_local[2][2]]
                import math
                sx=math.sqrt(sum(v*v for v in col0));sy=math.sqrt(sum(v*v for v in col1));sz=math.sqrt(sum(v*v for v in col2))
                if sx<=1e-12:sx=1.0
                if sy<=1e-12:sy=1.0
                if sz<=1e-12:sz=1.0
                R=[[new_local[r][c]/( [sx,sy,sz][c] ) for c in range(3)] for r in range(3)]
                from arika_models import quaternion_from_matrix
                q=quaternion_from_matrix(R)
                node['translation']=[tx,ty,tz]
                node['rotation']=q
                node['scale']=[sx,sy,sz]
            # detach stg for the moved root and all moved descendants
            for moved_index in moved_nodes:
                moved_extras=nodes[moved_index].get('extras')
                if isinstance(moved_extras,dict) and 'stg_offset' in moved_extras:
                    moved_extras.pop('stg_offset',None)
            # update hierarchy
            # remove from old parent/scene roots
            if old_parent is None:
                for scene in self.m_document.get('scenes',[]):
                    if root in scene.get('nodes',[]):scene['nodes']=[i for i in scene['nodes'] if i!=root]
            else:
                oldp_nodes=nodes[old_parent].get('children',[])
                if root in oldp_nodes:oldp_nodes.remove(root)
                nodes[old_parent]['children']=oldp_nodes
            if parent is None:
                targets=original_root_scenes.get(root) or []
                if not targets and self.m_document.get('scenes'):
                    targets=[self.m_document['scenes'][0]]
                for scene in targets:
                    if root not in scene.setdefault('nodes',[]):scene['nodes'].append(root)
            else:
                nodes[parent].setdefault('children',[]).append(root)
        return dict(count=len(roots))

    def duplicate(self,indices):return self.duplicate_nodes(indices)
    def copy_nodes(self,indices):return self.duplicate_nodes(indices)
    def reparent(self,indices,parent):return self.reparent_nodes(indices,parent)
    def move_nodes(self,indices,parent):return self.reparent_nodes(indices,parent)
    def set_parent(self,indices,parent):return self.reparent_nodes(indices,parent)
    def assign_parent(self,indices,parent):return self.reparent_nodes(indices,parent)

    def add_character(self,character,name,mesh_indices=None,translation=(0,0,0),hidden_indices=None,skinned=False):
        document,index=merge_character(self.m_document,character,name,mesh_indices,translation,hidden_indices,skinned)
        self.checkpoint();self.m_document=document
        return index

    def node_transform_values(self,index):
        require(type(index)is int and 0<=index<len(self.m_document.get('nodes',[])),'invalid node index')
        node=self.m_document['nodes'][index]
        if 'matrix' in node:return None
        extras=node.get('extras',{})
        actor=extras.get('character_preview')
        if actor is not None:
            return list(node.get('translation',[0,0,0]))+list(actor['rotation_radians'])+list(node.get('scale',[1,1,1]))
        offset=extras.get('stg_offset')
        if offset is not None:
            original=next((n for n in self.m_stage.m_scene['nodes'] if n['offset']==offset),None)
            if original is None or 'translation' not in original:return None
            return list(original['translation'])+list(original['rotation_radians'])+list(original['scale'])
        rotation=euler_radians(node.get('rotation',[0,0,0,1]))
        return list(node.get('translation',[0,0,0]))+rotation+list(node.get('scale',[1,1,1]))

    def actor_transform(self,index,values,checkpoint=True):
        from arika_import import floats
        from arika_scene_state import node_state
        floats(values,9)
        node=self.m_document['nodes'][index]
        require('character_preview' in node.get('extras',{}),'not a character instance')
        require(not node_state(self.m_document,index)['locked'],'character is locked')
        current=self.node_transform_values(index)
        if list(values)==current:return
        if checkpoint:self.checkpoint()
        else:self.m_changed=True
        node.update(translation=list(values[:3]),rotation=quaternion([v*180/3.141592653589793 for v in values[3:6]]),scale=list(values[6:9]))
        node['extras']['character_preview']['rotation_radians']=list(values[3:6])

    def node_transform(self,index,values,checkpoint=True):
        from arika_import import floats
        floats(values,9)
        current=self.node_transform_values(index)
        require(current is not None,'matrix-authored nodes do not have editable TRS fields')
        node=self.m_document['nodes'][index]
        if list(values)==current:return
        if checkpoint:self.checkpoint()
        else:self.m_changed=True
        node.update(translation=list(values[:3]),rotation=quaternion([v*180/3.141592653589793 for v in values[3:6]]),scale=list(values[6:9]))

    def transform_node(self,index,values,checkpoint=True):
        """Transform a scene node, routing native STG roots through the patcher."""
        require(type(index)is int and 0<=index<len(self.m_document.get('nodes',[])),'invalid node index')
        node=self.m_document['nodes'][index]
        if 'character_preview' in node.get('extras',{}):
            return self.actor_transform(index,values,checkpoint)
        offset=node.get('extras',{}).get('stg_offset')
        if offset is not None:
            original=next((n for n in self.m_stage.m_scene['nodes'] if n['offset']==offset),None)
            if original is not None and 'translation' in original:
                return self.transform(original['index'],values,checkpoint=checkpoint)
        return self.node_transform(index,values,checkpoint)

    def set_node_state(self,indices,hidden=None,locked=None):
        from arika_scene_state import selection_nodes,node_state
        indices=list(indices);nodes=self.m_document.get('nodes',[])
        require(all(type(i)is int and 0<=i<len(nodes) for i in indices),'invalid object index')
        require(hidden is None or type(hidden)is bool,'invalid hidden state')
        require(locked is None or type(locked)is bool,'invalid lock state')
        updates={key:value for key,value in (('hidden',hidden),('locked',locked)) if value is not None}
        targets=selection_nodes(self.m_document,indices)
        if not any(any(node_state(self.m_document,i)[key]!=value for key,value in updates.items()) for i in targets):return
        self.checkpoint()
        for index in targets:nodes[index].setdefault('extras',{}).setdefault('arika_editor',{}).update(updates)

    def set_transform_lock(self,index,component,axis,locked):
        from arika_scene_state import transform_locks
        require(type(index)is int and 0<=index<len(self.m_document.get('nodes',[])),'invalid object index')
        require(component in ('location','rotation','scale'),'invalid transform component')
        require(type(axis)is int and 0<=axis<3,'invalid transform axis')
        require(type(locked)is bool,'invalid transform lock state')
        current=transform_locks(self.m_document,index)
        if current[component][axis]==locked:return
        self.checkpoint()
        state=self.m_document['nodes'][index].setdefault('extras',{}).setdefault('arika_editor',{})
        locks=state.setdefault('transform_locks',dict(location=[False]*3,rotation=[False]*3,scale=[False]*3))
        locks.setdefault(component,[False]*3)[axis]=locked

    def __init__(self,path):
        self.m_stage=c_stage_document(path)
        gltf,_report=build_stage_gltf(self.m_stage.m_path,scene=self.m_stage.m_scene)
        self.m_document=gltf.to_document()
        self.m_history=[];self.m_future=[];self.m_changed=False
        self.m_virtual=False
        self._import_sibling_audio()

    def _import_sibling_audio(self):
        if getattr(self,'m_virtual',False):return
        base=self.m_stage.m_path.parent
        for suffix in ('.ase','.ams'):
            for path in sorted(base.glob('*'+suffix)):
                try:self.import_audio(path)
                except Exception:pass

    @classmethod
    def _build(cls,stage,document,virtual=False):
        obj=cls.__new__(cls);obj.m_stage=stage;obj.m_document=document
        obj.m_history=[];obj.m_future=[];obj.m_changed=False
        obj.m_virtual=virtual
        return obj

    @classmethod
    def from_bytes(cls,stg_data,name=None,virtual_files=None,model_data=None,hit_data=None,texture_data=None):
        stage=c_stage_document(data=stg_data,name=name,virtual_files=virtual_files)
        stage.m_virtual=True
        gltf,_report=build_stage_gltf(stage.m_path,scene=stage.m_scene,
            model_data=model_data,hit_data=hit_data,texture_data=texture_data)
        return cls._build(stage,gltf.to_document(),virtual=True)

    @classmethod
    def from_virtual(cls,stg_path,virtual_files):
        data=virtual_files[stg_path]
        p=PurePosixPath(stg_path);directory=str(p.parent);stem=p.stem
        def sibling(suffix):
            return '%s/%s%s'%(directory,stem,suffix) if directory else '%s%s'%(stem,suffix)
        return cls.from_bytes(data,stg_path,virtual_files,
            model_data=virtual_files.get(sibling('.mdl')),
            hit_data=virtual_files.get(sibling('.hit')),
            texture_data=virtual_files.get(sibling('.pix')))

    @classmethod
    def load_bytes(cls,data,name=None):
        document=data if isinstance(data,dict) else json.loads(data)
        require(document.get('format')=='ARIKA_SCENE_PROJECT' and document.get('version')==1,'unsupported editor project')
        stage=c_stage_document.__new__(c_stage_document);stage.m_path=Path(document['source_stage'])
        stage.m_original=base64.b64decode(document['original_stage'],validate=True);parse_stg(stage.m_original)
        stage.m_data=base64.b64decode(document['edited_stage'],validate=True);stage.m_scene=parse_stg(stage.m_data);stage.m_undo=[];stage.m_redo=[]
        stage.m_virtual_files={};stage.m_virtual=bool(name)
        doc=document['gltf'];require(doc.get('asset',{}).get('version')=='2.0','invalid project glTF')
        for item in doc.get('buffers',[])+doc.get('images',[]):require(item.get('uri','').startswith('data:'),'project assets must be embedded')
        return cls._build(stage,doc,virtual=bool(name))

    def snapshot(self):return (self.m_stage.m_data if self.m_stage else b'',copy.deepcopy(self.m_document))

    def checkpoint(self):
        self.m_history.append(self.snapshot());self.m_history=self.m_history[-20:];self.m_future=[];self.m_changed=True

    def restore(self,state):
        self.m_stage.m_data,self.m_document=state;self.m_stage.m_scene=parse_stg(self.m_stage.m_data);self.m_changed=True

    def undo(self):
        if self.m_history:self.m_future.append(self.snapshot());self.restore(self.m_history.pop())

    def redo(self):
        if self.m_future:self.m_history.append(self.snapshot());self.restore(self.m_future.pop())

    def transform(self,index,values,checkpoint=True):
        # Validate without adding project history until the STG patch succeeds.
        before_data=self.m_stage.m_data;before=self.snapshot() if checkpoint else None
        self.m_stage.set_transform(index,values)
        if before_data==self.m_stage.m_data:return
        if checkpoint:
            self.m_history.append(before);self.m_history=self.m_history[-20:];self.m_future=[]
        self.m_changed=True
        self.m_stage.m_undo=[];self.m_stage.m_redo=[]
        for node in self.m_document['nodes']:
            if node.get('extras',{}).get('stg_offset')==self.m_stage.m_scene['nodes'][index]['offset']:
                node.update(translation=values[:3],rotation=quaternion([v*180/3.141592653589793 for v in values[3:6]]),scale=values[6:9])

    def material(self,index,texture,color,alpha_mode,double_sided):
        require(type(index)is int and 0<=index<len(self.m_document['materials']),'invalid material')
        require(type(texture)is int and -1<=texture<len(self.m_document.get('textures',[])),'invalid texture')
        require(len(color)==4 and all(isinstance(v,(int,float)) and 0<=v<=1 for v in color),'invalid material color')
        require(alpha_mode in ('OPAQUE','MASK','BLEND'),'invalid alpha mode')
        self.checkpoint();mat=self.m_document['materials'][index];pbr=mat.setdefault('pbrMetallicRoughness',{})
        pbr['baseColorFactor']=list(color)
        if texture<0:pbr.pop('baseColorTexture',None)
        else:pbr['baseColorTexture']=dict(index=texture)
        mat.update(alphaMode=alpha_mode,alphaCutoff=.5,doubleSided=bool(double_sided))

    def import_texture(self,path):
        from PIL import Image
        import io
        import arika_dat as dat
        path=Path(path)
        data=None
        try:
            data=path.read_bytes()
        except Exception:
            pass
        # Check if it's FPIX
        if data and len(data)>=4 and data[:4]==b'FPIX':
            try:
                metadata=dat.container(data)
                self.checkpoint()
                images=self.m_document.setdefault('images',[])
                textures=self.m_document.setdefault('textures',[])
                added=0
                for chunk in metadata['chunks']:
                    if chunk['magic']!='XPIX':continue
                    try:
                        png=dat.tim2_png_bytes(data[chunk['offset']:chunk['offset']+chunk['size']])
                        images.append(dict(name='%s_%04d.png'%(path.stem,chunk['index']),uri='data:image/png;base64,'+base64.b64encode(png).decode()))
                        textures.append(dict(source=len(images)-1))
                        added+=1
                    except Exception:
                        continue
                if added==0:raise ValueError('FPIX contains no extractable textures')
                return len(textures)-1
            except Exception as e:
                raise
        try:
            with Image.open(path) as image:
                require(image.width<=16384 and image.height<=16384,'texture dimensions exceed 16384')
                buffer=io.BytesIO();image.convert('RGBA').save(buffer,format='PNG')
        except Exception:
            if data is None:
                data=path.read_bytes()
            buffer=io.BytesIO();buffer.write(data)
        self.checkpoint();images=self.m_document.setdefault('images',[]);textures=self.m_document.setdefault('textures',[])
        images.append(dict(name=path.name,uri='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()))
        textures.append(dict(source=len(images)-1));return len(textures)-1

    def import_audio(self,path):
        import arika_backend as backend
        import base64
        path=Path(path);suffix=path.suffix.lower();data=path.read_bytes()
        entries=[]  # (name, sample_rate, channels[list of int lists])
        if suffix=='.wav':
            info=backend.read_wav(data);rate=info['sample_rate'];channels=info['channels']
            if not channels or not channels[0]:
                raise ValueError('WAV contains no audio frames')
            entries.append((path.name,rate,channels))
        elif suffix=='.ase':
            samples=backend.ase_samples(data)
            for s in samples:
                rate=s['sample_rate'];payload=base64.b64decode(s['payload'])
                pcm=backend.decode_adpcm(payload)['pcm']
                entries.append((s.get('name') or ('%s_%03d'%(path.stem,s['index'])),rate,[pcm]))
        elif suffix=='.ams':
            info=backend.ams_channels(data);rate=info['sample_rate']
            left=backend.decode_adpcm(base64.b64decode(info['left']))['pcm']
            right=backend.decode_adpcm(base64.b64decode(info['right']))['pcm']
            entries.append((path.stem,rate,[left,right]))
        else:
            raise ValueError('expected .wav, .ase or .ams audio file')
        self.checkpoint();audios=self.m_document.setdefault('audios',[])
        first_index=len(audios);added=0
        for name,rate,channels in entries:
            if not channels or not channels[0]:continue
            wav=backend.write_wav(channels,rate)
            audios.append(dict(name=name,uri='data:audio/wav;base64,'+base64.b64encode(wav).decode(),
                sampleRate=rate,channels=len(channels),frames=len(channels[0])))
            added+=1
        if added==0:raise ValueError('audio file contains no decodable audio')
        return first_index

    def save(self,path):
        payload=dict(format='ARIKA_SCENE_PROJECT',version=1,source_stage=str(self.m_stage.m_path),
            original_stage=base64.b64encode(self.m_stage.m_original).decode(),edited_stage=base64.b64encode(self.m_stage.m_data).decode(),gltf=self.m_document)
        write_output(path,json.dumps(payload,separators=(',',':'),allow_nan=False).encode(),self.source_inputs());self.m_changed=False

    def source_inputs(self):
        sources=[self.m_stage.m_path.with_suffix(s) for s in ('.stg','.mdl','.hit','.pix')]
        for node in self.m_document['nodes']:sources.extend(node.get('extras',{}).get('character_preview',{}).get('source_paths',[]))
        return sources

    def export(self,path):write_output(path,json.dumps(self.m_document,separators=(',',':'),allow_nan=False).encode(),self.source_inputs())

    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text());require(data.get('format')=='ARIKA_SCENE_PROJECT' and data.get('version')==1,'unsupported editor project')
        stage=c_stage_document.__new__(c_stage_document);stage.m_path=Path(data['source_stage'])
        stage.m_original=base64.b64decode(data['original_stage'],validate=True);parse_stg(stage.m_original)
        stage.m_data=base64.b64decode(data['edited_stage'],validate=True);stage.m_scene=parse_stg(stage.m_data);stage.m_undo=[];stage.m_redo=[]
        doc=data['gltf'];require(doc.get('asset',{}).get('version')=='2.0','invalid project glTF')
        for item in doc.get('buffers',[])+doc.get('images',[]):require(item.get('uri','').startswith('data:'),'project assets must be embedded')
        obj=cls.__new__(cls);obj.m_stage=stage;obj.m_document=doc;obj.m_history=[];obj.m_future=[];obj.m_changed=False;return obj
