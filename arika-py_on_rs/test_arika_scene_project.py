import base64
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from arika_scene_project import c_scene_project,material_preview_document
from arika_models import c_gltf
from arika_stage_editor import c_stage_document
from test_arika_stages import stg_fixture


class SceneProjectTests(unittest.TestCase):
    def test_stage_constructor_builds_document_in_memory(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.stg';path.write_bytes(stg_fixture())
            gltf=c_gltf()
            with patch('arika_scene_project.build_stage_gltf',return_value=(gltf,{})) as builder, \
                 patch.object(c_stage_document,'export_preview',side_effect=AssertionError('must not round-trip through a temporary glTF')):
                project=c_scene_project(path)
            builder.assert_called_once()
            self.assertEqual(project.m_document['buffers'][0]['byteLength'],0)
            self.assertTrue(project.m_document['buffers'][0]['uri'].startswith('data:application/octet-stream;base64,'))

    def test_transform_axis_locks_persist_and_undo(self):
        from arika_scene_state import transform_locks
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp));before=project.m_stage.m_data
            self.assertEqual(transform_locks(project.m_document,0),dict(location=[False]*3,rotation=[False]*3,scale=[False]*3))
            project.set_transform_lock(0,'location',0,True)
            self.assertTrue(transform_locks(project.m_document,0)['location'][0])
            self.assertEqual(project.m_stage.m_data,before)
            path=Path(tmp)/'locks.arika-scene.json';project.save(path)
            loaded=c_scene_project.load(path)
            self.assertTrue(transform_locks(loaded.m_document,0)['location'][0])
            project.undo()
            self.assertFalse(transform_locks(project.m_document,0)['location'][0])

    def test_visibility_locks_persist_undo_and_preserve_stage(self):
        from arika_scene_state import node_state,hidden_nodes
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp));before=project.m_stage.m_data
            self.assertTrue(node_state(project.m_document,0)['locked'])
            self.assertFalse(node_state(project.m_document,0)['hidden'])
            project.set_node_state([0],locked=False,hidden=True)
            self.assertEqual(project.m_stage.m_data,before)
            self.assertFalse(node_state(project.m_document,0)['locked'])
            self.assertIn(0,hidden_nodes(project.m_document))
            self.assertEqual(len(project.m_history),1)
            project.set_node_state([0],locked=False,hidden=True)
            self.assertEqual(len(project.m_history),1)
            path=Path(tmp)/'saved.arika-scene.json';project.save(path)
            loaded=c_scene_project.load(path)
            self.assertEqual(node_state(loaded.m_document,0),dict(locked=False,hidden=True))
            project.undo();self.assertTrue(node_state(project.m_document,0)['locked'])
            self.assertNotIn(0,hidden_nodes(project.m_document))
            project.redo();self.assertIn(0,hidden_nodes(project.m_document))

    def test_node_state_validation_precedes_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp))
            for indices,flags in [([-1],dict(hidden=True)),([0],dict(locked=1)),([10000],dict(locked=False))]:
                with self.assertRaises(Exception):project.set_node_state(indices,**flags)
            self.assertEqual(project.m_history,[])

    def test_material_preview_remaps_texture_without_mutating_source(self):
        doc=dict(materials=[dict(pbrMetallicRoughness=dict(baseColorTexture=dict(index=1)))],textures=[dict(source=0),dict(source=1)],images=[dict(uri='first'),dict(uri='second')])
        preview=material_preview_document(doc,0)
        self.assertEqual(preview['images'],[dict(uri='second')])
        self.assertEqual(preview['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index'],0)
        self.assertEqual(doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index'],1)

    def test_untextured_material_preview_has_no_image_resources(self):
        doc=dict(materials=[dict(pbrMetallicRoughness=dict(baseColorFactor=[1,.5,0,1]))])
        preview=material_preview_document(doc,0)
        self.assertNotIn('textures',preview)
        self.assertEqual(len(preview['meshes']),1)

    def project(self,root):
        path=root/'source.stg';path.write_bytes(stg_fixture());obj=c_scene_project.__new__(c_scene_project)
        obj.m_stage=c_stage_document(path);obj.m_history=[];obj.m_future=[];obj.m_changed=False
        obj.m_document=dict(asset=dict(version='2.0'),nodes=[dict(extras=dict(stg_offset=n['offset'])) for n in obj.m_stage.m_scene['nodes']],
            materials=[dict(pbrMetallicRoughness=dict(baseColorTexture=dict(index=0)))],images=[dict(uri='data:image/png;base64,')],textures=[dict(source=0)],buffers=[])
        return obj

    def test_transform_node_drag_preview_is_one_undo_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp));index=next(i for i,n in enumerate(project.m_document['nodes'])
                if project.node_transform_values(i) is not None)
            before=project.snapshot();values=project.node_transform_values(index);changed=list(values);changed[0]+=12.5
            project.checkpoint();project.transform_node(index,changed,checkpoint=False)
            self.assertEqual(len(project.m_history),1)
            self.assertNotEqual(project.m_stage.m_data,before[0])
            project.undo()
            self.assertEqual(project.m_stage.m_data,before[0])
            self.assertEqual(project.node_transform_values(index),values)

    def test_opaque_stage_nodes_are_not_exposed_as_trs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp))
            for index,node in enumerate(project.m_stage.m_scene['nodes']):
                if 'translation' not in node:
                    self.assertIsNone(project.node_transform_values(index))

    def test_generic_node_transform_is_undoable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp));index=len(project.m_document['nodes'])
            project.m_document['nodes'].append(dict(name='generic',translation=[1,2,3],rotation=[0,0,0,1],scale=[1,1,1]))
            values=project.node_transform_values(index);changed=list(values);changed[1]=22
            project.transform_node(index,changed)
            self.assertEqual(project.m_document['nodes'][index]['translation'],[1,22,3])
            project.undo()
            self.assertEqual(project.m_document['nodes'][index]['translation'],[1,2,3])

    def test_material_edit_undo_and_redo(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj=self.project(Path(tmp));obj.material(0,-1,[.5,1,1,.7],'BLEND',True)
            self.assertNotIn('baseColorTexture',obj.m_document['materials'][0]['pbrMetallicRoughness'])
            obj.undo();self.assertEqual(obj.m_document['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index'],0)
            obj.redo();self.assertEqual(obj.m_document['materials'][0]['alphaMode'],'BLEND')

    def test_transform_updates_stage_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj=self.project(Path(tmp));original=obj.m_stage.m_data
            obj.transform(2,[30,40,50,0,0,0,1,1,1])
            self.assertEqual(obj.m_document['nodes'][2]['translation'],[30,40,50])
            obj.undo();self.assertEqual(obj.m_stage.m_data,original)

    def test_save_load_embeds_scene_and_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj=self.project(root);obj.material(0,0,[1,.5,1,1],'MASK',False)
            target=root/'scene.arika-scene.json';obj.save(target);other=c_scene_project.load(target)
            self.assertEqual(other.m_document,obj.m_document);self.assertEqual(other.m_stage.m_data,obj.m_stage.m_data)
            export=root/'scene.gltf';other.export(export);self.assertEqual(json.loads(export.read_text()),obj.m_document)

    def test_image_import_embeds_png_and_is_undoable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj=self.project(root);path=root/'test.png';Image.new('RGBA',(4,8),(255,0,0,128)).save(path)
            index=obj.import_texture(path);self.assertEqual(index,1)
            data=base64.b64decode(obj.m_document['images'][1]['uri'].split(',')[1]);self.assertTrue(data.startswith(b'\x89PNG'))
            obj.undo();self.assertEqual(len(obj.m_document['textures']),1)

    def test_audio_import_embeds_wav_and_is_undoable(self):
        import arika_audio
        from array import array
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj=self.project(root);path=root/'test.wav'
            arika_audio.write_wave(path,18000,[array('h',[0]*280)])
            index=obj.import_audio(path);self.assertEqual(index,0)
            a=obj.m_document['audios'][0]
            self.assertEqual(a['name'],'test.wav')
            self.assertTrue(a['uri'].startswith('data:audio/wav;base64,'))
            self.assertEqual(a['sampleRate'],18000)
            self.assertEqual(a['channels'],1)
            self.assertEqual(a['frames'],280)
            obj.undo();self.assertEqual(len(obj.m_document.get('audios',[])),0)

    def test_audio_import_ase_and_ams(self):
        import struct
        from array import array
        import arika_audio as audio
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj=self.project(root)
            # ASE bank with one sample
            payload=bytes([12,4])+bytes(14)+bytes([12,3])+bytes(14)
            header=struct.pack('<5I',100,1,32,1536,0).ljust(2048,b'\0')
            ase=root/'test.ase';ase.write_bytes(header+payload)
            idx=obj.import_audio(ase);self.assertEqual(idx,0)
            a=obj.m_document['audios'][0]
            self.assertEqual(a['name'],'test_000');self.assertEqual(a['sampleRate'],18000);self.assertEqual(a['channels'],1);self.assertEqual(a['frames'],56)
            # AMS stereo stream
            hdr=struct.pack('<4I',120,4096,(3*32768+16),2).ljust(2048,b'\0')
            body=b''.join(bytes([i*2])*32768+bytes([i*2+1])*32768 for i in range(4))
            ams=root/'test.ams';ams.write_bytes(hdr+body)
            idx=obj.import_audio(ams);self.assertEqual(idx,1)
            a=obj.m_document['audios'][1]
            self.assertEqual(a['name'],'test');self.assertEqual(a['sampleRate'],48000);self.assertEqual(a['channels'],2);self.assertEqual(a['frames'],172060)
            obj.undo();self.assertEqual(len(obj.m_document.get('audios',[])),1)
            obj.undo();self.assertEqual(len(obj.m_document.get('audios',[])),0)

    def test_invalid_material_has_no_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj=self.project(Path(tmp))
            with self.assertRaises(ValueError):obj.material(0,9,[1,1,1,1],'MASK',True)
            with self.assertRaises(ValueError):obj.material(0,0,[float('nan'),1,1,1],'MASK',True)
            self.assertEqual(obj.m_history,[])

    def test_protects_source_and_rejects_external_project_buffers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);obj=self.project(root)
            with self.assertRaises(ValueError):obj.export(root/'source.stg')
            path=root/'project.json';obj.save(path);data=json.loads(path.read_text());data['gltf']['buffers']=[dict(uri='/private/file')];path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):c_scene_project.load(path)
