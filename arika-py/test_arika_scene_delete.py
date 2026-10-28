import copy
from pathlib import Path
import tempfile
import unittest
from arika_scene_project import c_scene_project


class SceneDeleteTests(unittest.TestCase):
    def project(self,root):
        from test_arika_scene_project import SceneProjectTests
        project=SceneProjectTests().project(root)
        project.m_document['nodes']=[dict(name='group',children=[1,2]),dict(name='leaf'),dict(name='child group',children=[3]),dict(name='child leaf'),dict(name='survivor')]
        project.m_document['scenes']=[dict(nodes=[0,4]),dict(nodes=[4])]
        return project

    def test_delete_compacts_references_and_survives_save_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=self.project(root);stage=project.m_stage.m_data
            project.set_node_state([0],locked=False)
            before=copy.deepcopy(project.m_document)
            result=project.delete_nodes([1,2,3])
            self.assertEqual(result,dict(count=3,remap={0:0,4:1}))
            self.assertEqual(project.m_document['nodes'][0]['children'],[])
            self.assertEqual(project.m_document['scenes'][0]['nodes'],[0,1])
            self.assertEqual(project.m_document['scenes'][1]['nodes'],[1])
            self.assertEqual(project.m_stage.m_data,stage)
            path=root/'deleted.arika-scene.json';project.save(path)
            self.assertEqual(len(c_scene_project.load(path).m_document['nodes']),2)
            project.undo();self.assertEqual(project.m_document,before)
            project.redo();self.assertEqual(len(project.m_document['nodes']),2)

    def test_locked_descendants_block_atomic_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp));project.set_node_state([0],locked=False);project.set_node_state([3],locked=True)
            before=project.snapshot();count=len(project.m_history)
            with self.assertRaisesRegex(ValueError,'Unlock'):project.delete_nodes([0,1])
            self.assertEqual(project.snapshot(),before);self.assertEqual(len(project.m_history),count)
            with self.assertRaisesRegex(ValueError,'Unlock'):project.delete_nodes([1,4])
            self.assertEqual(project.snapshot(),before)

    def test_empty_invalid_and_delete_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp))
            self.assertEqual(project.delete_nodes([])['count'],0);self.assertEqual(project.m_history,[])
            for index in (-1,999,True):
                with self.assertRaises(ValueError):project.delete_nodes([index])
            self.assertEqual(project.m_history,[])
            project.set_node_state([0,4],locked=False);result=project.delete_nodes([0,4])
            self.assertEqual(result['count'],5);self.assertEqual(project.m_document['nodes'],[])
            self.assertTrue(all(not s['nodes'] for s in project.m_document['scenes']))

    def test_animation_targets_remap_and_skin_dependencies_are_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self.project(Path(tmp));project.set_node_state([0,4],locked=False)
            project.m_document['animations']=[dict(channels=[dict(target=dict(node=1,path='translation')),dict(target=dict(node=4,path='scale'))])]
            project.delete_nodes([1])
            self.assertEqual(project.m_document['animations'][0]['channels'],[dict(target=dict(node=3,path='scale'))])
            project=self.project(Path(tmp));project.set_node_state([0,4],locked=False)
            project.m_document['nodes'][4]['skin']=0;project.m_document['skins']=[dict(joints=[1])]
            before=project.snapshot()
            with self.assertRaisesRegex(ValueError,'joints'):project.delete_nodes([1])
            self.assertEqual(project.snapshot(),before)
