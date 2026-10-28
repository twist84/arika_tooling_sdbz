import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from arika_actions import c_elf_reader, common_tables, parse_table, resolve_hands, sample_hands
from arika_face_bake import bake_gltf
from arika_face_player import sample_program
import arika_models as models
from test_arika_import import model_fixture


def motion_fixture():
    return dict(name='test',duration=1,last_frame_time=1,nodes=[dict(name='HandAni',tracks=dict(
        translation=dict(times=[0,.5,1],values=[[0,0,1],[4,0,2],[-1,0,0]])))])


class ActionTests(unittest.TestCase):
    def test_hand_step_keys_and_native_tolerance(self):
        states=sample_hands(motion_fixture(),[0,.25,.49998,.499995,.5,.75,1])
        self.assertEqual([(s['left'],s['right']) for s in states],
                         [(0,1),(0,1),(0,1),(4,2),(4,2),(4,2),(4,0)])

    def test_missing_track_resets_to_zero(self):
        motion=motion_fixture();motion['nodes']=[]
        self.assertEqual(sample_hands(motion,[0],initial=(3,4))[0]['left'],0)

    def test_loop_and_invalid_hand_index(self):
        states=sample_hands(motion_fixture(),[.75,1.25],loop=True)
        self.assertEqual([s['left'] for s in states],[4,0])
        self.assertEqual(states[1]['time'],1.25)
        self.assertEqual(states[1]['motion_time'],.25)
        motion=motion_fixture();motion['nodes'][0]['tracks']['translation']['values'][0][0]=10
        with self.assertRaises(ValueError):sample_hands(motion,[0])

    def test_hand_meshes_carry_forward(self):
        model=dict(meshes=[dict(name=n) for n in ['MeshLHand','MeshLHandC','MeshRHandA','MeshRHandE']])
        hands=resolve_hands(model)
        self.assertEqual([h['name'] for h in hands['L'][:4]],['MeshLHand','MeshLHand','MeshLHandC','MeshLHandC'])
        self.assertEqual(hands['R'][9]['name'],'MeshRHandE')

    def test_elf_and_action_record_bounds(self):
        data=bytearray(0x114);data[:7]=b'\x7fELF\x01\x01\x01'
        struct.pack_into('<I',data,28,52);struct.pack_into('<HH',data,42,32,1)
        struct.pack_into('<5I',data,52,1,0x100,0x100000,0x100000,20)
        struct.pack_into('<HHfffI',data,0x100,210,0,1,0,-1,0x10000)
        reader=c_elf_reader(data);record=parse_table(reader,0x100000,1)[0]
        self.assertEqual(record['motion_id'],210);self.assertEqual(record['flags'],0x10000)
        with self.assertRaises(ValueError):parse_table(reader,0x100000,2)
        with self.assertRaises(ValueError):common_tables(data)
        with self.assertRaises(ValueError):c_elf_reader(b'bad')

    def test_automatic_hands_bake_step_visibility(self):
        model=models.parse_model(model_fixture());mesh=model['meshes'][0]
        model['meshes']=[]
        for i,name in enumerate(['MeshBody','ShapeHeadAB','MeshLHandA','MeshLHandE','MeshRHandA','MeshRHandB','MeshRHandC']):
            item=copy.deepcopy(mesh);item['name']=name;item['index']=i;model['meshes'].append(item)
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'hands.gltf'
            result=bake_gltf(model,sample_program([],1,blink=False),output,
                             motion=motion_fixture(),auto_hands=True)
            doc=json.loads(output.read_text());clip=doc['animations'][0]
            self.assertEqual(result['hand_instances'],5)
            self.assertTrue(clip['extras']['automatic_hands'])
            hand_channels=[c for c in clip['channels'] if doc['nodes'][c['target']['node']]['name'].startswith(('MeshLHand','MeshRHand'))]
            self.assertEqual(len(hand_channels),5)
            self.assertTrue(all(c['target']['path']=='scale' and clip['samplers'][c['sampler']]['interpolation']=='STEP' for c in hand_channels))
            self.assertTrue(all('skin' not in doc['nodes'][c['target']['node']] for c in hand_channels))
        with self.assertRaises(ValueError):bake_gltf(model,sample_program([],1),output,auto_hands=True)

    def test_skinned_visibility_clones_animated_joints(self):
        model=models.parse_model(model_fixture());original=model['meshes'][0]
        model['nodes']=[dict(name='root',index=0,parent=-1,translation=[0,0,0],rotation=[0,0,0,1],scale=[1,1,1])]
        model['meshes']=[]
        for i,name in enumerate(['ShapeHeadAB','MeshLHandA','MeshRHandA']):
            mesh=copy.deepcopy(original);mesh.update(name=name,index=i,skinned=name!='ShapeHeadAB')
            for vertex in mesh['vertices']:
                vertex.update(joints=[0,0,0,0],weights=[1,0,0,0])
            model['meshes'].append(mesh)
        motion=dict(name='skin_test',duration=1,last_frame_time=1,nodes=[dict(name='root',tracks=dict(
            translation=dict(times=[0,1],values=[[0,0,0],[1,0,0]])))])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'skin.gltf'
            bake_gltf(model,sample_program([],1,blink=False),path,motion=motion,auto_hands=True)
            doc=json.loads(path.read_text());clip=doc['animations'][0]
            self.assertEqual(len(doc['skins']),3)
            translations=[c for c in clip['channels'] if c['target']['path']=='translation']
            self.assertEqual(len(translations),3)
            self.assertEqual(len({c['sampler'] for c in translations}),1)
            visibility=[c for c in clip['channels'] if c['target']['path']=='scale']
            self.assertTrue(all('skin' not in doc['nodes'][c['target']['node']] for c in visibility))
            for skin in doc['skins'][1:]:
                self.assertTrue(all(j not in doc['skins'][0]['joints'] for j in skin['joints']))


if __name__=='__main__':unittest.main()
