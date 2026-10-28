import base64
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import arika_models as models
import arika_import as importer
import arika_faces as faces
from test_arika_models import geometry_fixture, motion_fixture


def chunk(tag,count,payload):
    return tag+struct.pack('<II',32+len(payload),count)+bytes(20)+payload


def directory(tag,children):
    start=32+len(children)*4
    offsets=[]
    for child in children:
        offsets.append(start);start+=len(child)
    return chunk(tag,len(children),struct.pack('<'+'I'*len(offsets),*offsets)+b''.join(children))


def model_fixture():
    xmat=chunk(b'XMAT',1,struct.pack('<8fi3I',1,1,1,1,.7,.7,.7,1,-1,0,0,0))
    xmal=chunk(b'XMAL',1,struct.pack('<32i',0,*([-1]*31)))
    return directory(b'FMDL',[
        directory(b'DMOD',[geometry_fixture()]),directory(b'DMAT',[xmat,xmal]),
        chunk(b'XTEX',1,bytes(4)),chunk(b'XMON',1,b'test\0\0\0\0'),
        chunk(b'XCUD',1,struct.pack('<I4f2I',1,.5,.5,0,1,0,0))])


def face_fixture():
    data=bytearray(52)
    struct.pack_into('<I',data,0,1)
    struct.pack_into('<II',data,16,2,24)
    struct.pack_into('<II',data,24,32,32) # aliases reference one program
    struct.pack_into('<fBBH',data,32,0,0,6,0)
    struct.pack_into('<fBBH',data,40,.5,0,0,0x1000)
    return bytes(data[:48])


def package_fixture():
    motion=motion_fixture();data=bytearray(112)
    data[:16]=b'RFSML3'+struct.pack('<HII',1,48,99)
    data[16:32]=b'test.mot'.ljust(16,b'\0')
    struct.pack_into('<4I',data,32,112,len(motion),0,0x10006)
    struct.pack_into('<HHIII',data,48,1,1,64,80,98)
    data[64:80]=b'root'.ljust(16,b'\0')
    struct.pack_into('<III',data,80,0,92,96)
    struct.pack_into('<2Hh',data,92,0,0,0)
    data[98]=0x33
    return bytes(data)+bytes(motion)


class ImportTests(unittest.TestCase):
    def test_model_noop_and_position_edit(self):
        source=model_fixture();j=models.parse_model(source)
        self.assertEqual(importer.model_from_json(source,j),source)
        j['meshes'][0]['vertices'][0]['position'][0]=-.5
        changed=importer.model_from_json(source,j)
        self.assertEqual(len(changed),len(source))
        self.assertEqual(models.parse_model(changed)['meshes'][0]['vertices'][0]['position'][0],-.5)
        top,_,_,_=importer.model_layout(changed)
        self.assertAlmostEqual(struct.unpack_from('<f',changed,top['XCUD']['offset']+36)[0],.25)
        j['meshes'][0]['primitives'][0]['triangles'].pop()
        with self.assertRaises(ValueError):importer.model_from_json(source,j)

    def test_motion_constant_copy_on_write(self):
        source=bytes(motion_fixture());j=models.parse_motion(source)
        self.assertEqual(importer.motion_from_json(source,j),source)
        # One constant vector is shared by the scale component; clone it on edit.
        j['nodes'][0]['tracks']['scale']['values'][0]=[2,1,1]
        changed=importer.motion_from_json(source,j)
        self.assertEqual(len(changed),len(source)+16)
        parsed=models.parse_motion(changed)
        self.assertEqual(parsed['nodes'][0]['tracks']['scale']['values'][0],[2,1,1])
        self.assertEqual(parsed['constant_vectors'][0],[1,1,1,1])
        self.assertEqual(parsed['nodes'][0]['tracks']['rotation']['values'],j['nodes'][0]['tracks']['rotation']['values'])

    def test_package_relocation(self):
        source=package_fixture();j=models.parse_motions(source)
        self.assertEqual(importer.motions_from_json(source,j),source)
        j['motions'][0]['nodes'][0]['tracks']['scale']['values'][0]=[2,2,2]
        changed=importer.motions_from_json(source,j)
        self.assertEqual(models.parse_motions(changed)['motions'][0]['nodes'][0]['tracks']['scale']['values'][0],[2,2,2])

    def test_face_alias_and_edit(self):
        source=face_fixture();j=faces.parse_face(source)
        self.assertEqual(len(j['programs']),1)
        self.assertEqual(faces.face_from_json(source,j),source)
        j['programs'][0]['records'][0]['behavior']=5
        changed=faces.face_from_json(source,j)
        self.assertEqual(faces.parse_face(changed)['programs'][0]['records'][0]['behavior'],5)
        j['programs'][0]['records'][0]['expression']=9
        with self.assertRaises(ValueError):faces.face_from_json(source,j)

    def test_gltf_roundtrip_and_geometry_mutation(self):
        source=model_fixture();model=models.parse_model(source)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.gltf';models.export_gltf(model,path)
            self.assertEqual(importer.model_from_gltf(source,path),source)
            d=json.loads(path.read_text());attribute=d['meshes'][0]['primitives'][0]['attributes']['POSITION']
            view=d['bufferViews'][d['accessors'][attribute]['bufferView']]
            blob=bytearray(base64.b64decode(d['buffers'][0]['uri'].split(',')[1]))
            struct.pack_into('<f',blob,view['byteOffset'],-.25)
            d['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode()
            path.write_text(json.dumps(d))
            result=importer.model_from_gltf(source,path)
            self.assertEqual(models.parse_model(result)['meshes'][0]['vertices'][0]['position'][0],-.25)
            del d['meshes'][0]['primitives'][0]['attributes']['_ARIKA_VERTEX'];path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):importer.model_from_gltf(source,path)

    def test_gltf_motion_roundtrip_and_key_mutation(self):
        source=package_fixture();motion=models.parse_motions(source)['motions'][0]
        meshmodel=models.parse_model(model_fixture())
        meshmodel['nodes']=[dict(name='root',parent=-1,translation=[0,0,0],rotation=[0,0,0,1],scale=[1,1,1])]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'motion.gltf';models.export_gltf(meshmodel,path,[motion])
            self.assertEqual(importer.motions_from_gltf(source,path),source)
            d=json.loads(path.read_text());anim=d['animations'][0]
            channel=next(c for c in anim['channels'] if c['target']['path']=='translation')
            accessor=d['accessors'][anim['samplers'][channel['sampler']]['output']]
            view=d['bufferViews'][accessor['bufferView']]
            blob=bytearray(base64.b64decode(d['buffers'][0]['uri'].split(',')[1]))
            struct.pack_into('<f',blob,view['byteOffset']+12,3)
            d['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode()
            path.write_text(json.dumps(d))
            changed=importer.motions_from_gltf(source,path)
            self.assertEqual(models.parse_motions(changed)['motions'][0]['nodes'][0]['tracks']['translation']['values'][1][0],3)

    def test_reordered_vertices_and_glb(self):
        source=model_fixture();model=models.parse_model(source)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.gltf';models.export_gltf(model,path)
            d=json.loads(path.read_text())
            blob=bytearray(base64.b64decode(d['buffers'][0]['uri'].split(',')[1]))
            primitive=d['meshes'][0]['primitives'][0]
            for ix in primitive['attributes'].values():
                ac=d['accessors'][ix];view=d['bufferViews'][ac['bufferView']]
                width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[ac['type']]
                start=view['byteOffset'];stride=width*4
                rows=[blob[start+i*stride:start+(i+1)*stride] for i in range(ac['count'])]
                blob[start:start+len(rows)*stride]=b''.join(reversed(rows))
            ix=d['accessors'][primitive['indices']];view=d['bufferViews'][ix['bufferView']]
            for i in range(ix['count']):
                at=view['byteOffset']+i*4;old=struct.unpack_from('<I',blob,at)[0]
                struct.pack_into('<I',blob,at,3-old)
            del d['buffers'][0]['uri']
            text=json.dumps(d).encode();text+=b' '*((-len(text))%4)
            glb=b'glTF'+struct.pack('<II',2,12+8+len(text)+8+len(blob))
            glb+=struct.pack('<II',len(text),0x4E4F534A)+text
            glb+=struct.pack('<II',len(blob),0x004E4942)+blob
            path=Path(tmp)/'test.glb';path.write_bytes(glb)
            self.assertEqual(importer.model_from_gltf(source,path),source)

    def test_output_protects_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'original';path.write_bytes(b'original')
            with self.assertRaises(ValueError):importer.write_output(path,b'changed',[path])
            self.assertEqual(path.read_bytes(),b'original')


if __name__=='__main__':unittest.main()
