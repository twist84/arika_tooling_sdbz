"""Bake controller-driven facial geometry and texture switches to standard glTF."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import arika_models as models
from arika_models import require
from arika_import import sample_track, write_output
from arika_faces import PAIRS


def resolve_faces(model, super_form=False):
    by_name={m['name']:m for m in model['meshes']}
    last=by_name.get('MeshHead',by_name.get('ShapeHeadAB'))
    require(last is not None, 'model has no facial mesh (MeshHead/ShapeHeadAB)')
    default_material=last['primitives'][0]['material']
    materials=[default_material,default_material]
    result=[]
    for pair in PAIRS:
        geometry_name='ShapeHeadSAD' if super_form else 'ShapeHead'+pair
        last=by_name.get(geometry_name,last)
        controls=['HeadTexSAD','HeadTexSDA'] if super_form else ['HeadTex'+pair,'HeadTex'+pair[::-1]]
        for i,name in enumerate(controls):
            control=by_name.get(name)
            if control:
                materials[i]=control['primitives'][0]['material']
        result.append(dict(pair=pair,mesh=last,materials=list(materials)))
    return result


def bake_gltf(model, playback, output, texture_path=None, motion=None, loop_motion=False,
              left_hand='A',right_hand='A',name='facial_playback',auto_hands=False):
    require(not auto_hands or motion is not None, 'automatic hands require a body motion')
    from arika_actions import resolve_hands, sample_hands
    by_name={m['name']:m for m in model['meshes']}
    faces=resolve_faces(model,playback['super_form'])
    work=copy.deepcopy(model)
    work['meshes']=[]
    for wanted in ['MeshBody','MeshHairS' if playback['super_form'] else 'MeshHair']:
        if wanted not in by_name and wanted=='MeshHairS': wanted='MeshHair'
        if wanted in by_name:
            work['meshes'].append(copy.deepcopy(by_name[wanted]))
    hand_states=[]
    hand_meshes={}
    if auto_hands:
        hand_states=sample_hands(motion,[s['time'] for s in playback['samples']],loop_motion)
        choices=resolve_hands(model)
        for side,key in [('L','left'),('R','right')]:
            names=[]
            for state in hand_states:
                hand=choices[side][state[key]]
                require(hand is not None, 'model has no fallback for %s hand index %d'%(side,state[key]))
                names.append(hand['name'])
                if hand['name'] not in hand_meshes:
                    hand_meshes[hand['name']]=hand
                    work['meshes'].append(copy.deepcopy(hand))
            for state,mesh_name in zip(hand_states,names):
                state[key+'_mesh']=mesh_name
    else:
        for prefix,variant in [('MeshLHand',left_hand),('MeshRHand',right_hand)]:
            hand=by_name.get(prefix+variant,by_name.get(prefix))
            if hand is None:
                hand=next((m for m in model['meshes'] if m['name'].startswith(prefix)),None)
            if hand:
                work['meshes'].append(copy.deepcopy(hand))
    keys=sorted({(s['pair_index'],min(1,max(0,s['texture_endpoint']))) for s in playback['samples']})
    clone_names={}
    fallbacks=[]
    for pair,endpoint in keys:
        definition=faces[pair]
        mesh=copy.deepcopy(definition['mesh'])
        mesh['name']='face_%s_texture_%d'%(PAIRS[pair],endpoint)
        for part in mesh['primitives']:
            part['material']=definition['materials'][endpoint]
        work['meshes'].append(mesh)
        clone_names[(pair,endpoint)]=mesh['name']
        expected='ShapeHeadSAD' if playback['super_form'] else 'ShapeHead'+PAIRS[pair]
        if definition['mesh']['name']!=expected:
            fallbacks.append(dict(pair=PAIRS[pair],geometry=definition['mesh']['name']))
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'base.gltf'
        models.export_gltf(work,path,texture_path=texture_path)
        document=json.loads(path.read_text(encoding='utf-8'))
    writer=models.c_gltf()
    writer.m_document=document
    writer.m_blob=bytearray(base64.b64decode(document['buffers'][0]['uri'].split(',')[1]))
    nodes_by_name={n['name']:i for i,n in enumerate(document['nodes'])}
    samples=playback['samples']
    times=[s['time'] for s in samples]
    input_accessor=writer.array(times,'SCALAR',bounds=True)
    clip=dict(name=name,channels=[],samplers=[],extras=dict(
        controller_sample_rate=playback['sample_rate'],rng_seed_hex=hex(playback['seed']),
        idle_blink=playback['idle_blink'],super_form=playback['super_form'],
        original_ani_group=playback.get('group'),original_ani_program=playback.get('program'),
        face_start_requested=playback.get('face_start_requested',0),
        face_start_sampled=playback.get('face_start_sampled',0),
        facial_program_events=playback.get('program_events',[]),
        source_motion_binding=playback.get('motion_binding'),
        action_sequence=playback.get('action_sequence'),
        native_pose=playback.get('native_pose'),
        loop_body_motion=loop_motion,automatic_hands=auto_hands))
    def channel(target,path,values,kind,interpolation='LINEAR'):
        sampler=len(clip['samplers'])
        clip['samplers'].append(dict(input=input_accessor,output=writer.array(values,kind),interpolation=interpolation))
        clip['channels'].append(dict(sampler=sampler,target=dict(node=target,path=path)))
    if motion:
        duration=motion['duration']
        for source in motion['nodes']:
            target=nodes_by_name.get(source.get('name'))
            if target is None:
                continue
            for path,track in source['tracks'].items():
                values=[]
                for time in times:
                    time=time%duration if loop_motion else min(time,motion['last_frame_time'])
                    value=sample_track(track['times'],track['values'],time,path,'LINEAR')
                    values.append(models.normalized(value) if path=='rotation' else value)
                if path=='rotation':
                    for i in range(1,len(values)):
                        if sum(a*b for a,b in zip(values[i-1],values[i]))<0:
                            values[i]=[-v for v in values[i]]
                channel(target,path,values,'VEC4' if path=='rotation' else 'VEC3')
        clip['extras']['body_motion']=motion['name']
    body_channels=list(clip['channels'])
    def visibility_target(target):
        # glTF ignores mesh-node TRS for a skinned mesh. Give switched skins
        # independent joint trees and scale their common parent instead.
        node=document['nodes'][target]
        if 'skin' not in node:
            return target
        skin=copy.deepcopy(document['skins'][node['skin']])
        parents={child:i for i,n in enumerate(document['nodes']) for child in n.get('children',[])}
        needed=set(skin['joints'])
        if 'skeleton' in skin: needed.add(skin['skeleton'])
        for joint in list(needed):
            while joint in parents:
                joint=parents[joint];needed.add(joint)
        mapping={old:len(document['nodes'])+i for i,old in enumerate(sorted(needed))}
        for old in sorted(needed):
            clone=copy.deepcopy(document['nodes'][old])
            require('mesh' not in clone,'unexpected mesh inside visibility skeleton')
            clone['name']=node['name']+'__'+clone.get('name',str(old))
            clone['children']=[mapping[c] for c in clone.get('children',[]) if c in mapping]
            if not clone['children']: clone.pop('children')
            document['nodes'].append(clone)
        wrapper=len(document['nodes'])
        document['nodes'].append(dict(name=node['name']+'_visibility',children=[mapping[j] for j in sorted(needed) if parents.get(j) not in needed]))
        document['scenes'][document.get('scene',0)]['nodes'].append(wrapper)
        skin['joints']=[mapping[j] for j in skin['joints']]
        if 'skeleton' in skin: skin['skeleton']=mapping[skin['skeleton']]
        skin['name']=node['name']+'_skin'
        node['skin']=len(document['skins']);document['skins'].append(skin)
        for source in body_channels:
            if source['target']['node'] in mapping:
                clone=copy.deepcopy(source)
                clone['target']['node']=mapping[source['target']['node']]
                clip['channels'].append(clone)
        return wrapper
    for mesh_name in hand_meshes:
        target=visibility_target(nodes_by_name[mesh_name+'_geometry'])
        visible=[[1,1,1] if mesh_name in (s['left_mesh'],s['right_mesh']) else [0,0,0] for s in hand_states]
        document['nodes'][target]['scale']=visible[0]
        channel(target,'scale',visible,'VEC3','STEP')
    for key,mesh_name in clone_names.items():
        target=nodes_by_name[mesh_name+'_geometry']
        visible_target=visibility_target(target)
        visible=[[1,1,1] if (s['pair_index'],min(1,max(0,s['texture_endpoint'])))==key else [0,0,0] for s in samples]
        document['nodes'][visible_target]['scale']=visible[0]
        channel(visible_target,'scale',visible,'VEC3','STEP')
        mesh=document['meshes'][document['nodes'][target]['mesh']]
        if mesh.get('weights') is not None:
            weights=[max(0,min(1,s['blend'])) for s in samples]
            mesh['weights']=[weights[0]]
            channel(target,'weights',weights,'SCALAR')
    document['animations']=[clip]
    document['extras']['baked_facial_playback']=True
    document['extras']['face_geometry_fallbacks']=fallbacks
    document['extras']['note']='Sampled native facial controller; STEP scale switches select geometry/texture instances, LINEAR weights deform the active face. Re-export an unbaked model for importing edits.'
    document['buffers']=[dict(byteLength=len(writer.m_blob),uri='data:application/octet-stream;base64,'+base64.b64encode(writer.m_blob).decode())]
    write_output(output,json.dumps(document,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'),[texture_path] if texture_path else [])
    return dict(face_instances=len(keys),fallbacks=fallbacks,sample_count=len(samples),
                duration=playback['duration'],body_motion=motion['name'] if motion else None,
                automatic_hands=auto_hands,hand_instances=len(hand_meshes))
