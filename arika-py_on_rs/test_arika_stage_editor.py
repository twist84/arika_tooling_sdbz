import tempfile
from pathlib import Path
import unittest
from arika_stage_editor import c_stage_document,moved_translation,snapped_delta
from test_arika_stages import stg_fixture

class StageEditorTests(unittest.TestCase):
    def test_document_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'scene.stg';source.write_bytes(stg_fixture());doc=c_stage_document(source)
            before=doc.m_data;offset=doc.m_scene['nodes'][2]['offset']
            doc.set_transform(2,[20,30,40,0,.5,0,1,2,1])
            self.assertEqual(doc.m_data[:offset+8],before[:offset+8])
            self.assertEqual(doc.m_data[offset+44:],before[offset+44:])
            target=Path(tmp)/'edited.stg';doc.save_as(target)
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(c_stage_document(target).m_scene['nodes'][2]['translation'],[20,30,40])
            doc.undo();self.assertEqual(doc.m_data,before)
            doc.redo();self.assertEqual(doc.m_data,target.read_bytes())
            with self.assertRaises(ValueError):doc.save_as(source)
            with self.assertRaises(ValueError):doc.set_transform(2,[float('nan')]*9)

    def test_drag_converts_world_delta_through_parent(self):
        import math
        parent=dict(parent=-1,translation=[100,200,300],rotation_radians=[0,0,math.pi/2],scale=[2,2,2])
        child=dict(parent=0,translation=[0,0,0])
        result=moved_translation(dict(nodes=[parent,child]),1,2,0,'XY')
        self.assertAlmostEqual(result[0],0,places=6)
        self.assertAlmostEqual(result[1],-1,places=6)
        self.assertAlmostEqual(result[2],0,places=6)

    def test_drag_uses_selected_plane(self):
        scene=dict(nodes=[dict(parent=-1,translation=[1,2,3])])
        self.assertEqual(moved_translation(scene,0,4,5,'XZ'),[5,2,8])
        self.assertEqual(moved_translation(scene,0,4,5,'YZ'),[1,6,8])

    def test_drag_rejects_singular_parent(self):
        parent=dict(parent=-1,translation=[0,0,0],rotation_radians=[0,0,0],scale=[0,1,1])
        with self.assertRaises(ValueError):moved_translation(dict(nodes=[parent,dict(parent=0,translation=[0,0,0])]),1,1,1,'XZ')

    def test_snapped_drag_delta(self):
        self.assertEqual(snapped_delta(12,-18,10),(10,-20))
        self.assertEqual(snapped_delta(12,-18,0),(12,-18))
        with self.assertRaises(ValueError):snapped_delta(1,2,-1)
        with self.assertRaises(ValueError):snapped_delta(1,2,float('nan'))

    def test_export_uses_committed_bytes_and_sibling_assets(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'scene.stg';source.write_bytes(stg_fixture());doc=c_stage_document(source)
            doc.set_transform(2,[20,30,40,0,0,0,1,1,1])
            output=Path(tmp)/'scene.gltf'
            def exporter(scene,path,**options):
                self.assertEqual(Path(scene).read_bytes(),doc.m_data)
                self.assertEqual(options['model_path'],source.with_suffix('.mdl'))
                self.assertEqual(Path(path),output)
                return dict(mesh_instances=1)
            with patch('arika_stage_editor.export_stage',side_effect=exporter):
                self.assertEqual(doc.export_preview(output)['mesh_instances'],1)
            self.assertEqual(source.read_bytes(),stg_fixture())
            with self.assertRaises(ValueError):doc.export_preview(source)
