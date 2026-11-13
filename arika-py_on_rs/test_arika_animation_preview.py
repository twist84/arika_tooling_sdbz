"""Animation preview and character clip remapping regression tests."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from arika_models import c_gltf
from arika_animation_preview import c_animation_preview
from arika_scene_characters import load_skinned_character, merge_character


def fixture():
    gltf=c_gltf()
    doc=gltf.m_document
    positions=gltf.array([[0,0,0],[1,0,0],[0,1,0]],'VEC3')
    indices=gltf.array([0,1,2],'SCALAR',5125)
    times=gltf.array([0.0,1.0],'SCALAR')
    positions_keys=gltf.array([[0,0,0],[2,4,6]],'VEC3')
    rotation_keys=gltf.array([[0,0,0,1],[0,0,1,0]],'VEC4')
    doc['nodes']=[dict(name='bone',translation=[1,0,0],rotation=[0,0,0,1],scale=[1,1,1]),
                  dict(name='mesh',mesh=0)]
    doc['scenes'][0]['nodes']=[0,1]
    doc['meshes']=[dict(primitives=[dict(attributes=dict(POSITION=positions),indices=indices)])]
    doc['animations']=[dict(name='Rotate and move',samplers=[
        dict(input=times,output=positions_keys,interpolation='LINEAR'),
        dict(input=times,output=rotation_keys,interpolation='LINEAR'),
    ],channels=[
        dict(sampler=0,target=dict(node=0,path='translation')),
        dict(sampler=1,target=dict(node=0,path='rotation')),
    ])]
    return gltf.to_document()


class AnimationPreviewTests(unittest.TestCase):
    def test_scrub_and_restore_without_modifying_original(self):
        doc=fixture()
        original=copy.deepcopy(doc)
        preview=c_animation_preview(doc,0)
        self.assertEqual(preview.name,'Rotate and move')
        self.assertAlmostEqual(preview.m_duration,1.0)
        preview.seek(0.5)
        posed=preview.m_document['nodes'][0]
        self.assertEqual(posed['translation'],[1.0,2.0,3.0])
        self.assertAlmostEqual(posed['rotation'][2],math.sqrt(.5),places=6)
        self.assertAlmostEqual(posed['rotation'][3],math.sqrt(.5),places=6)
        self.assertEqual(doc,original)
        preview.seek(10)
        self.assertEqual(posed['translation'],[2.0,4.0,6.0])
        preview.seek(-10)
        self.assertEqual(posed['translation'],[0.0,0.0,0.0])
        self.assertEqual(doc,original)

    def test_character_animation_remaps_targets_and_accessors(self):
        character=fixture()
        base=fixture()
        base.pop('animations')
        base['nodes'][0]['name']='existing'
        document,actor=merge_character(base,character,'Animated actor',skinned=True)
        self.assertEqual(len(document['animations']),1)
        clip=document['animations'][0]
        target=clip['channels'][0]['target']['node']
        self.assertNotEqual(target,0)
        self.assertIn(target,document['nodes'][actor]['children'])
        self.assertEqual(document['nodes'][target]['name'],'bone')
        self.assertGreater(clip['samplers'][0]['input'],character['animations'][0]['samplers'][0]['input'])
        preview=c_animation_preview(document,0)
        preview.seek(.5)
        self.assertEqual(preview.m_document['nodes'][target]['translation'],[1.0,2.0,3.0])
        self.assertEqual(document['nodes'][target]['translation'],[1,0,0])

    def test_loader_embeds_external_gltf_buffer(self):
        document=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            uri=document['buffers'][0]['uri']
            import base64
            blob=base64.b64decode(uri.split(',',1)[1])
            (directory/'geometry.bin').write_bytes(blob)
            document['buffers'][0]['uri']='geometry.bin'
            path=directory/'character.gltf'
            path.write_text(json.dumps(document),encoding='utf-8')
            loaded=load_skinned_character(path)
            self.assertTrue(loaded['buffers'][0]['uri'].startswith('data:'))
            self.assertEqual(len(loaded['animations']),1)
            preview=c_animation_preview(loaded,0)
            preview.seek(.5)
            self.assertEqual(preview.m_document['nodes'][0]['translation'],[1.0,2.0,3.0])

    def test_rejects_unsupported_interpolation(self):
        document=fixture()
        document['animations'][0]['samplers'][0]['interpolation']='STEP'
        with self.assertRaises(ValueError):
            c_animation_preview(document,0)


if __name__=='__main__':
    unittest.main()
