import copy
from pathlib import Path
import tempfile
import unittest
from arika_models import c_gltf
from arika_import import c_gltf_reader
from arika_scene_characters import bake_character,load_character,merge_character
from arika_scene_project import c_scene_project
from arika_scene_state import node_state


class CharacterPreviewTests(unittest.TestCase):
    def test_native_fmdl_import_uses_existing_decoder(self):
        from test_arika_import import model_fixture
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'character.mdl';path.write_bytes(model_fixture())
            character=load_character(path)
            self.assertEqual(len(character['meshes']),1)
            self.assertEqual(character['meshes'][0]['name'],'test')
            self.assertEqual(len(character['meshes'][0]['primitives']),1)

    def character(self,path,skin=True):
        g=c_gltf();d=g.m_document
        attrs=dict(POSITION=g.array([[0,0,0],[1,0,0],[0,1,0]],'VEC3'))
        if skin:
            attrs.update(JOINTS_0=g.array([[0,0,0,0]]*3,'VEC4',5123),WEIGHTS_0=g.array([[1,0,0,0]]*3,'VEC4'))
            # Bone moves +3; inverse bind removes original +1 bind translation.
            inverse=[1,0,0,0,0,1,0,0,0,0,1,0,-1,0,0,1]
            d['skins']=[dict(joints=[0],inverseBindMatrices=g.array([inverse],'MAT4'))]
        d['nodes']=[dict(name='bone',translation=[3,0,0]),dict(name='body',mesh=0,translation=[9,0,0])]
        if skin:d['nodes'][1]['skin']=0
        d['scenes'][0]['nodes']=[0,1]
        d['meshes']=[dict(name='Body',primitives=[dict(attributes=attrs,indices=g.array([0,1,2],'SCALAR',5125))])]
        g.save(path);return path

    def test_skin_bakes_joint_world_and_inverse_bind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.character(root/'skin.gltf')
            baked=load_character(path);target=root/'baked.gltf'
            import json
            target.write_text(json.dumps(baked));reader=c_gltf_reader(target)
            accessor=baked['meshes'][0]['primitives'][0]['attributes']['POSITION']
            self.assertEqual(reader.accessor(accessor),[[2,0,0],[3,0,0],[2,1,0]])
            self.assertNotIn('skins',baked)
            self.assertNotIn('skin',baked['nodes'][0])

    def test_rigid_node_world_transform_and_merge_remapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);character=load_character(self.character(root/'rigid.gltf',False))
            first,index=merge_character(copy.deepcopy(character),character,'Actor',translation=[10,20,30])
            self.assertEqual(first['nodes'][index]['translation'],[10,20,30])
            child=first['nodes'][index]['children'][0]
            self.assertEqual(first['nodes'][child]['mesh'],1)
            primitive=first['meshes'][1]['primitives'][0]
            accessor=first['accessors'][primitive['attributes']['POSITION']]
            view=first['bufferViews'][accessor['bufferView']]
            self.assertEqual(view['buffer'],1)
            import json
            path=root/'merged.gltf';path.write_text(json.dumps(first))
            self.assertEqual(c_gltf_reader(path).accessor(primitive['attributes']['POSITION'])[0],[9,0,0])
            self.assertTrue(node_state(first,index)['locked'])

    def test_project_character_transform_save_undo_and_native_bytes(self):
        from test_arika_scene_project import SceneProjectTests
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=SceneProjectTests().project(root);stage=project.m_stage.m_data
            project.m_document['scenes']=[dict(nodes=list(range(len(project.m_document['nodes']))))]
            character=load_character(self.character(root/'actor.gltf'))
            count=len(project.m_document['nodes']);index=project.add_character(character,'Actor')
            values=[10,20,30,0,.5,0,2,2,2]
            with self.assertRaises(ValueError):project.actor_transform(index,values)
            project.set_node_state([index],locked=False);project.actor_transform(index,values)
            self.assertEqual(project.m_document['nodes'][index]['translation'],[10,20,30])
            self.assertEqual(project.m_stage.m_data,stage)
            path=root/'project.arika-scene.json';project.save(path)
            loaded=c_scene_project.load(path)
            self.assertEqual(loaded.m_document['nodes'][index]['name'],'Actor')
            self.assertEqual(loaded.m_document['nodes'][index]['scale'],[2,2,2])
            self.assertIn(str((root/'actor.gltf').resolve()),loaded.source_inputs())
            project.undo();self.assertEqual(project.m_document['nodes'][index]['translation'],[0,0,0])
            project.undo();project.undo();self.assertEqual(len(project.m_document['nodes']),count)
            project.redo();self.assertEqual(project.m_document['nodes'][index]['name'],'Actor')

    def test_real_example_character_has_body_face_and_embedded_textures(self):
        path=Path(__file__).parent/'examples/goku_action_232_native_poses.gltf'
        character=load_character(path)
        self.assertEqual(len(character['meshes']),7)
        self.assertTrue(any('face' in m['name'] for m in character['meshes']))
        self.assertTrue(all(i['uri'].startswith('data:image/png;base64,') for i in character['images']))

    def test_no_mesh_selected_leaves_project_unchanged(self):
        from test_arika_scene_project import SceneProjectTests
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=SceneProjectTests().project(root)
            before=project.snapshot();character=load_character(self.character(root/'actor.gltf'))
            with self.assertRaises(ValueError):project.add_character(character,'Actor',[])
            self.assertEqual(project.snapshot(),before);self.assertEqual(project.m_history,[])
