import math
import struct
import unittest
from arika_stages import parse_stg,parse_hit,hit_obj,assemble_document
from arika_models import c_gltf


def stg_fixture():
    names=['EFFECT','STAGE','cube','collider','face']
    data=struct.pack('<4I',256,0x20475453,len(names),0)+b''.join(n.encode().ljust(16,b'\0') for n in names)
    def node(kind,name,links=0,refs=(),translation=(0,0,0)):
        body=bytes((kind,len(refs),links,7 if kind==2 else 0))+struct.pack('<I9f',name,*translation,0,0,math.pi/2,1,1,1)
        return body+b''.join(struct.pack('<2I',i,flags) for i,flags in refs)
    return data+node(1,0)+node(1,1,1)+node(2,2,1,translation=(10,0,0))+node(3,3,refs=((4,0x80000040),))


def hit_fixture():
    return (struct.pack('<8I',0x20000,0x20544948,1,48,112,144,0,0)+b'face'.ljust(16,b'\0')+
        struct.pack('<3If12f',2,1,0,1.,*([0.,0.,0.,1.]*3))+
        struct.pack('<4I4f',4,0,0,0,0.,1.,0.,1.)+
        b''.join(struct.pack('<4f',*v,1.) for v in ((0,0,0),(1,0,0),(1,0,1),(0,0,1))))


class StageTests(unittest.TestCase):
    def test_scene_hierarchy_and_references(self):
        scene=parse_stg(stg_fixture())
        self.assertEqual(scene['roots'],[0,1]);self.assertEqual(scene['nodes'][3]['parent'],2)
        self.assertEqual(scene['nodes'][2]['translation'],[10.,0.,0.])
        self.assertEqual(scene['nodes'][3]['references'][0]['name'],'face')

    def test_truncated_and_unknown_scene_records_rejected(self):
        with self.assertRaises(ValueError):parse_stg(stg_fixture()[:-1])
        data=bytearray(stg_fixture());data[96]=99
        with self.assertRaises(ValueError):parse_stg(data)

    def test_unfulfilled_child_rejected(self):
        data=bytearray(stg_fixture());data[-52+2]=1
        with self.assertRaises(ValueError):parse_stg(data)

    def test_bad_scene_name_rejected(self):
        data=bytearray(stg_fixture());struct.pack_into('<I',data,100,100)
        with self.assertRaises(ValueError):parse_stg(data)

    def test_opaque_controls_are_not_interpreted_as_transforms(self):
        data=stg_fixture();control=bytes((6,0,0,0))+struct.pack('<I13I',0,*([0]*13))
        scene=parse_stg(data[:96]+control+data[140:])
        self.assertEqual(scene['nodes'][0]['size'],60)
        self.assertNotIn('translation',scene['nodes'][0])
        self.assertEqual(len(scene['nodes'][0]['opaque_words']),13)

    def test_hit_polygons_and_object_ranges(self):
        hit=parse_hit(hit_fixture())
        self.assertEqual(hit['objects'][0]['polygon_count'],1)
        self.assertEqual(hit['polygons'][0]['vertex_count'],4)
        self.assertEqual(len(hit['vertices']),4)

    def test_hit_obj_preserves_ngon(self):
        text=hit_obj(parse_hit(hit_fixture())).decode()
        self.assertIn('o face\n',text);self.assertIn('f 1 2 3 4\n',text)

    def test_invalid_hit_ranges_rejected(self):
        for offset,value in ((12,0),(52,9),(116,1000)):
            data=bytearray(hit_fixture());struct.pack_into('<I',data,offset,value)
            with self.assertRaises(ValueError):parse_hit(data)

    def test_scene_assembly_instances_mesh_and_collision(self):
        scene=parse_stg(stg_fixture());hit=parse_hit(hit_fixture());g=c_gltf()
        positions=g.array([[0,0,0],[1,0,0],[0,1,0]],'VEC3');indices=g.array([0,1,2],'SCALAR',5125)
        g.m_document['meshes']=[dict(name='cube',primitives=[dict(attributes=dict(POSITION=positions),indices=indices)])]
        import base64
        g.m_document['buffers']=[dict(uri='data:application/octet-stream;base64,'+base64.b64encode(g.m_blob).decode(),byteLength=len(g.m_blob))]
        model=dict(nodes=[],meshes=[dict(skinned=False)],source_sha256='fixture')
        result,report=assemble_document(scene,model,g.m_document,hit);doc=result.m_document
        self.assertEqual(report['mesh_instances'],1);self.assertEqual(report['collision_instances'],1)
        self.assertEqual(doc['nodes'][2]['mesh'],0)
        self.assertAlmostEqual(doc['nodes'][2]['rotation'][2],math.sqrt(.5),places=6)
        self.assertEqual(doc['scenes'][0]['nodes'],[1])
        self.assertEqual(doc['nodes'][7]['children'],[8])
        self.assertEqual(doc['nodes'][8]['mesh'],1)
        self.assertTrue(all(i<len(doc['nodes']) for n in doc['nodes'] for i in n.get('children',[])))


if __name__=='__main__':unittest.main()
