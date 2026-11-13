import base64
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import arika_dat as archive
import arika_models as model


def motion_fixture():
    data = bytearray(168)
    data[:4] = b'MOT2'
    struct.pack_into('<If4HII', data, 4, len(data), 60, 7, 1, 1, 2, 144, 128)
    struct.pack_into('<HHII', data, 28, 1, 2, 64, 152)
    struct.pack_into('<HHII', data, 40, 1, 2, 96, 160)
    struct.pack_into('<HHII', data, 52, 0, 0, 128, 168)
    struct.pack_into('<8f', data, 64, 0,0,0,1, 2,4,6,1)
    struct.pack_into('<8f', data, 96, 0,0,0,1, 0,0,1,0)
    struct.pack_into('<4f', data, 128, 1,1,1,1)
    struct.pack_into('<4H', data, 144, 3,0,0,0)
    struct.pack_into('<4f', data, 152, 0,.1,0,.1)
    return data


def geometry_fixture():
    # Two UNPACK packets form one strip. The second packet continues its history.
    packets = []
    for points in [[(0,0,0,0x8000),(1,0,0,0x8000),(0,1,0,0)], [(1,1,0,0)]]:
        payload = struct.pack('<8I', 1,0,0,0,len(points),0,0,0)
        for x,y,z,adc in points:
            payload += struct.pack('<3fI', x,y,z,adc)
            payload += struct.pack('<4f', 0,0,1, -1 if y and x else 1)
            payload += struct.pack('<4f', x,y,1,0)
        count = len(payload)//16
        packets.append(struct.pack('<4I', 0,0,0x01000404,0x6C008000 | count<<16) + payload + struct.pack('<4I',0x17000000,0,0,0))
    stream = b''.join(packets)
    data = bytearray(0x1A0 + 16 + len(stream))
    data[:4] = b'XMOD'
    struct.pack_into('<I', data, 4, len(data))
    struct.pack_into('<II', data, 48, 4,2)
    struct.pack_into('<4I', data, 0x1A0, 0x60000000 | len(stream)//16,0,0,0)
    data[0x1B0:] = stream
    return data


class ModelTests(unittest.TestCase):
    def test_euler_quaternion_round_trip(self):
        import math
        from arika_models import euler_radians,quaternion
        angles=[.31,-.42,.77]
        rotation=quaternion([math.degrees(v) for v in angles])
        for actual,expected in zip(euler_radians(rotation),angles):
            self.assertAlmostEqual(actual,expected,places=6)

    def test_packet_continuation_and_winding(self):
        parsed = model.mesh_geometry(geometry_fixture(), [-1]*32, [0], 0)
        self.assertEqual(parsed['primitives'][0]['triangles'], [[0,1,2],[2,1,3]])
        bad = geometry_fixture()
        struct.pack_into('<I', bad, 48, 5)
        with self.assertRaises(ValueError): model.mesh_geometry(bad, [-1]*32, [0], 0)
        with self.assertRaises(ValueError): model.mesh_geometry(bad[:-1], [-1]*32, [0], 0)

    def test_motion_tracks_and_corruption(self):
        parsed = model.parse_motion(motion_fixture())
        self.assertEqual(parsed['channel_counts'], [1,1,0])
        tracks = parsed['nodes'][0]['tracks']
        self.assertEqual(tracks['translation']['values'], [[0,0,0],[2,4,6]])
        self.assertEqual(tracks['rotation']['values'], [[0,0,0,1],[0,0,1,0]])
        self.assertFalse(tracks['scale']['animated'])
        self.assertAlmostEqual(parsed['last_frame_time'], .1)
        bad = motion_fixture()
        struct.pack_into('<H', bad, 146, 1)
        with self.assertRaises(ValueError): model.parse_motion(bad)
        bad = motion_fixture()
        struct.pack_into('<f', bad, 156, 0)
        with self.assertRaises(ValueError): model.parse_motion(bad)

    def test_skeleton_transform_and_cycle(self):
        rotation = model.quaternion([-90,90,-90])
        self.assertAlmostEqual(abs(rotation[1]), math.sqrt(.5))
        self.assertAlmostEqual(abs(rotation[3]), math.sqrt(.5))
        nodes = [dict(parent=-1, translation=[1,2,3], rotation=[0,0,0,1], scale=[2,3,4]),
            dict(parent=0, translation=[1,1,1], rotation=[0,0,0,1], scale=[1,1,1])]
        matrices = model.world_matrices(nodes)
        self.assertEqual([matrices[1][r][3] for r in range(3)], [3,5,7])
        restored = model.multiply(matrices[1], model.inverse(matrices[1]))
        for r in range(4):
            for c in range(4): self.assertAlmostEqual(restored[r][c], int(r==c))
        nodes[0]['parent'] = 1
        with self.assertRaises(ValueError): model.world_matrices(nodes)

    def test_batch_skeleton_matches_independent_hierarchy(self):
        # Parent indices are intentionally not topologically sorted.
        nodes = [
            dict(parent=2, translation=[1, 0, 0],
                 rotation=model.quaternion([0, 30, 0]), scale=[1, 2, 1]),
            dict(parent=-1, translation=[-5, 1, 0],
                 rotation=[0, 0, 0, 1], scale=[1, 1, 1]),
            dict(parent=1, translation=[0, 2, 3],
                 rotation=model.quaternion([20, 0, 0]), scale=[2, 1, 0.5]),
            dict(parent=0, translation=[0, 0, -1],
                 rotation=model.quaternion([0, 0, 45]), scale=[1, 1, 1]),
        ]
        # Independent Python reference, not a call to the new world_matrices.
        def local(node):
            x, y, z, w = node['rotation']
            sx, sy, sz = node['scale']
            tx, ty, tz = node['translation']
            return [
                [(1-2*(y*y+z*z))*sx, 2*(x*y-z*w)*sy, 2*(x*z+y*w)*sz, tx],
                [2*(x*y+z*w)*sx, (1-2*(x*x+z*z))*sy, 2*(y*z-x*w)*sz, ty],
                [2*(x*z-y*w)*sx, 2*(y*z+x*w)*sy, (1-2*(x*x+y*y))*sz, tz],
                [0, 0, 0, 1],
            ]
        def mul(a, b):
            return [[sum(a[r][k]*b[k][c] for k in range(4))
                     for c in range(4)] for r in range(4)]
        def reference(index):
            local_matrix = local(nodes[index])
            parent = nodes[index]['parent']
            return mul(reference(parent), local_matrix) if parent >= 0 else local_matrix
        actual = model.world_matrices(nodes)
        for index, matrix in enumerate(actual):
            expected = reference(index)
            for r in range(4):
                for c in range(4):
                    self.assertAlmostEqual(matrix[r][c], expected[r][c], places=10)

    def test_batch_skeleton_validation_and_empty(self):
        self.assertEqual(model.world_matrices([]), [])
        def node(parent):
            return dict(parent=parent, translation=[0, 0, 0],
                        rotation=[0, 0, 0, 1], scale=[1, 1, 1])
        for nodes in ([node(1), node(0)],
                      [node(0)],
                      [node(3)],
                      [node(-2)],
                      [dict(node(-1), scale=[float('nan'), 1, 1])]):
            with self.subTest(nodes=nodes):
                with self.assertRaises(ValueError):
                    model.world_matrices(nodes)

    def test_native_matrix_multiplication_and_inversion_parity(self):
        # Independent reference equations, including nonuniform scales.
        q = model.quaternion([17.0, -29.0, 42.0])
        node = dict(translation=[-3.0, 4.5, 8.0],
                    rotation=q, scale=[2.0, 0.5, 3.0])
        x, y, z, w = q
        sx, sy, sz = node['scale']
        tx, ty, tz = node['translation']
        expected = [
            [(1-2*(y*y+z*z))*sx, 2*(x*y-z*w)*sy, 2*(x*z+y*w)*sz, tx],
            [2*(x*y+z*w)*sx, (1-2*(x*x+z*z))*sy, 2*(y*z-x*w)*sz, ty],
            [2*(x*z-y*w)*sx, 2*(y*z+x*w)*sy, (1-2*(x*x+y*y))*sz, tz],
            [0, 0, 0, 1],
        ]
        actual = model.local_matrix(node)
        for row_a, row_b in zip(actual, expected):
            for value_a, value_b in zip(row_a, row_b):
                self.assertAlmostEqual(value_a, value_b, places=11)
        inverse = model.inverse(actual)
        product = model.multiply(actual, inverse)
        for r in range(4):
            for c in range(4):
                self.assertAlmostEqual(product[r][c], int(r == c), places=10)

        # Multiply must accept arbitrary 4x4 row-major matrices.
        rhs = [[1.0, 2.0, 3.0, 4.0],
               [5.0, 6.0, 7.0, 8.0],
               [9.0, 10.0, 11.0, 12.0],
               [13.0, 14.0, 15.0, 16.0]]
        reference = [[sum(expected[r][k] * rhs[k][c] for k in range(4))
                      for c in range(4)] for r in range(4)]
        native = model.multiply(actual, rhs)
        for row_a, row_b in zip(native, reference):
            for value_a, value_b in zip(row_a, row_b):
                self.assertAlmostEqual(value_a, value_b, places=11)

    def test_native_inverse_rejects_singular_matrix(self):
        with self.assertRaises(ValueError):
            model.inverse([[0.0] * 4 for _ in range(4)])
        with self.assertRaises(ValueError):
            model.inverse([[1.0] * 4 for _ in range(3)])

    def test_native_inverse_swaps_pivot_rows(self):
        matrix = [[0, 1, 0, 0], [1, 0, 0, 0],
                  [0, 0, 1, 0], [0, 0, 0, 1]]
        self.assertEqual(model.inverse(matrix), matrix)

    def test_export_gltf_embeds_textures_without_splitting_archive(self):
        # Minimal 1x1 RGBA32 TIM2 picture inside a normal FPIX/XPIX chunk.
        tim2 = bytearray(68)
        tim2[:8] = b"TIM2" + struct.pack("<BBH", 4, 0, 1)
        struct.pack_into("<IIIHHBBBBHH", tim2, 16, 52, 0, 4, 48, 0, 0, 1, 0, 3, 1, 1)
        tim2[64:68] = bytes((255, 0, 0, 128))
        chunk = b"XPIX" + struct.pack("<I", 32 + len(tim2)) + bytes(24) + tim2
        pix = b"FPIX" + struct.pack("<III", 36 + len(chunk), 1, 0x100) + bytes(16) + struct.pack("<I", 36) + chunk
        mesh = model.mesh_geometry(geometry_fixture(), [-1] * 32, [0], 0)
        mesh.update(index=0, name="fixture")
        parsed = dict(source_sha256="fixture", nodes=[], materials=[dict(index=0, texture=-1)], meshes=[mesh])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            texture_path = root / "stage.pix"
            output = root / "stage.gltf"
            texture_path.write_bytes(pix)
            with patch.object(archive, "split_container", side_effect=AssertionError("must not split chunks to disk")):
                model.export_gltf(parsed, output, texture_path=texture_path)
            document = json.loads(output.read_text())
            self.assertEqual(len(document["images"]), 1)
            embedded = base64.b64decode(document["images"][0]["uri"].split(",", 1)[1])
            self.assertEqual(embedded, archive.tim2_png_bytes(tim2))
            self.assertEqual(document["textures"][0]["source"], 0)

    def test_gltf_skin_and_animation(self):
        mesh = model.mesh_geometry(geometry_fixture(), [0]+[-1]*31, [0], 1)
        mesh.update(index=0, name='body', skinned=True)
        for v in mesh['vertices']: v.update(joints=[0,0,0,0], weights=[1,0,0,0])
        parsed = dict(nodes=[dict(name='root', parent=-1, translation=[0,0,0], rotation=[0,0,0,1], scale=[1,1,1])],
            materials=[dict(index=0, texture=-1)], meshes=[mesh])
        motion = model.parse_motion(motion_fixture())
        motion.update(name='test')
        motion['nodes'][0]['name'] = 'root'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'test.gltf'
            model.export_gltf(parsed, out, [motion])
            data = json.loads(out.read_text())
            self.assertEqual(len(data['animations'][0]['channels']), 3)
            self.assertEqual(data['skins'][0]['joints'], [0])
            blob = base64.b64decode(data['buffers'][0]['uri'].split(',')[1])
            self.assertEqual(len(blob), data['buffers'][0]['byteLength'])
            self.assertTrue(all(v['byteOffset']%4==0 and v['byteOffset']+v['byteLength']<=len(blob) for v in data['bufferViews']))
            mesh['vertices'][0]['weights'] = [1.1,-.1,0,0]
            with self.assertRaises(ValueError): model.export_gltf(parsed, out)
            model.export_gltf(parsed, out, clamp_skin_weights=True)
            self.assertTrue(json.loads(out.read_text())['meshes'][0]['extras']['negative_skin_weights_clamped'])


if __name__ == '__main__': unittest.main()
