import copy
import json
from pathlib import Path
import tempfile
import unittest
import arika_faces as faces
import arika_models as models
from arika_face_player import c_face_player, sample_program, f32
from arika_face_bake import resolve_faces,bake_gltf
from test_arika_import import model_fixture


def event(time,expression=0,behavior=0,end=False):
    return dict(time=time,expression=expression,behavior=behavior,flags=0x1000 if end else 0)


class FacePlayerTests(unittest.TestCase):
    def test_original_random_generator(self):
        player=c_face_player(seed=0)
        self.assertEqual(player.m_seed,1)
        self.assertEqual(player.random(),1481765933)
        self.assertEqual(player.m_seed,6364136223846793006)

    def test_timed_expression_and_end(self):
        player=c_face_player([event(0,0,4),event(.5,end=True)],seed=1,blink=False)
        samples=[player.tick() for _ in range(50)]
        self.assertEqual(samples[0]['pair'],'AC')
        self.assertAlmostEqual(samples[0]['blend'],f32(1/6),places=6)
        self.assertEqual(samples[6]['blend'],1)
        self.assertEqual(samples[-1]['pair'],'AB')
        self.assertEqual(samples[-1]['blend'],0)
        self.assertFalse(samples[-1]['flags']&0x20)

    def test_randomized_pulses_are_reproducible(self):
        records=[event(0,0,6),event(1,end=True)]
        a=sample_program(records,1,seed=7,blink=False)
        self.assertEqual(a,sample_program(records,1,seed=7,blink=False))
        self.assertNotEqual(a['samples'],sample_program(records,1,seed=8,blink=False)['samples'])
        self.assertTrue(all(0<=s['blend']<=1 for s in a['samples']))

    def test_delayed_first_event_and_texture_threshold(self):
        player=c_face_player([event(1,1,4),event(1.5,end=True)],blink=False)
        # The native float32 clock reaches 0.9999997 after 60 increments.
        for _ in range(61):self.assertEqual(player.tick()['blend'],0)
        sample=player.tick()
        self.assertEqual(sample['pair'],'BC')
        self.assertEqual(sample['blend'],1)
        self.assertEqual(sample['texture_endpoint'],1)

    def test_idle_blink_and_super_form(self):
        normal=sample_program([],1,seed=0)
        self.assertTrue(any(s['blend']>=.5 and s['pair']=='AB' for s in normal['samples']))
        self.assertTrue(all(s['blend']==0 for s in sample_program([],1,seed=0,blink=False)['samples']))
        super_samples=sample_program([],1,seed=0,super_form=True)['samples']
        self.assertTrue(all(s['blend']==0 and s['pair']=='SAD' for s in super_samples))

    def test_texture_switch_and_visibility_channels(self):
        model=models.parse_model(model_fixture())
        original=model['meshes'][0]
        model['meshes']=[]
        for name in ['MeshBody','ShapeHeadAB','ShapeHeadAC','HeadTexAB','HeadTexBA','HeadTexAC','HeadTexCA']:
            mesh=copy.deepcopy(original);mesh['name']=name;mesh['index']=len(model['meshes'])
            if name.startswith('ShapeHead'):
                mesh['morph']=True
                for v in mesh['vertices']:
                    v['morph_position']=list(v['position']);v['morph_normal']=list(v['normal'])
            model['meshes'].append(mesh)
        resolved=resolve_faces(model)
        self.assertEqual(resolved[2]['mesh']['name'],'ShapeHeadAC') # native carry-forward fallback
        playback=sample_program([],1,seed=0)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'facial.gltf';result=bake_gltf(model,playback,path)
            data=json.loads(path.read_text())
            self.assertEqual(result['face_instances'],2)
            clip=data['animations'][0]
            self.assertTrue(any(c['target']['path']=='weights' for c in clip['channels']))
            scales=[s for s in clip['samplers'] if s['interpolation']=='STEP']
            self.assertEqual(len(scales),2)
            self.assertTrue(data['extras']['baked_facial_playback'])

    def test_bad_duration_rate_and_program(self):
        with self.assertRaises(ValueError):sample_program([],0)
        with self.assertRaises(ValueError):sample_program([],1,rate=59)
        with self.assertRaises(ValueError):c_face_player([event(0)])


if __name__=='__main__':unittest.main()
