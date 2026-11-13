"""CPU skinning parity and palette safety without requiring a GPU."""
import unittest
from types import SimpleNamespace

import numpy as np
from arika_webgpu import c_webgpu_renderer, skin_vertices


class _queue:
    def __init__(self):
        self.writes=[]

    def write_buffer(self, buffer, offset, data):
        self.writes.append((buffer, offset, bytes(data)))


class SkinningTests(unittest.TestCase):
    def test_two_joint_weighted_vertex_normalizes_weights(self):
        positions=[[1,2,3]]
        joints=[[0,1,0,0]]
        weights=[[1,3,0,0]] # glTF should behave as 0.25, 0.75
        first=np.eye(4)
        second=np.eye(4)
        first[0,3]=2
        second[1,3]=4
        actual=skin_vertices(positions,joints,weights,[first,second])
        np.testing.assert_allclose(actual,[[1.5,5,3]],atol=1e-6)

    def test_zero_weight_influences_are_not_blended(self):
        matrix=np.eye(4)
        matrix[0,3]=5
        actual=skin_vertices([[1,0,0]],[[0,0,0,0]],[[0,0,0,1]],[matrix])
        np.testing.assert_allclose(actual,[[6,0,0]])

    def test_invalid_skin_data_cannot_index_joint_palette(self):
        positions=[[1,2,3]]
        matrix=np.eye(4)
        bad=[
            ([[1,0,0,0]],[[1,0,0,0]]),
            ([[-1,0,0,0]],[[1,0,0,0]]),
            ([[0.5,0,0,0]],[[1,0,0,0]]),
            ([[0,0,0,0]],[[0,0,0,0]]),
            ([[0,0,0,0]],[[-1,2,0,0]]),
            ([[0,0,0,0]],[[float('nan'),0,0,0]]),
        ]
        for joints,weights in bad:
            with self.subTest(joints=joints,weights=weights):
                with self.assertRaises(ValueError):
                    skin_vertices(positions,joints,weights,[matrix])

    def test_inverse_bind_and_mesh_world_are_applied_before_upload(self):
        # Mesh is positioned at world X=10; bone is at X=14.
        # Inverse bind offsets X by -2, so local mesh motion is +2.
        renderer=c_webgpu_renderer.__new__(c_webgpu_renderer)
        queue=_queue()
        renderer.m_device=SimpleNamespace(queue=queue)
        renderer.m_node_worlds={0:np.eye(4)}
        renderer.m_node_worlds[0][0,3]=14
        renderer.m_meshes={0:[dict(
            positions=np.asarray([[1,0,0]],dtype='f4'),
            uvs=np.asarray([[.25,.75]],dtype='f4'),
            joints=np.asarray([[0,0,0,0]],dtype='i4'),
            weights=np.asarray([[2,0,0,0]],dtype='f4'),
        )]}
        mesh=np.eye(4);mesh[0,3]=10
        inverse_bind=np.eye(4);inverse_bind[0,3]=-2
        instance=dict(
            mesh=0,matrix=mesh,
            joint_nodes=[0],inverse_binds=[inverse_bind],
            skinned_vbos={0:'dynamic-vertex-buffer'},
        )
        renderer._apply_skinning(instance)
        self.assertEqual(len(queue.writes),1)
        buffer,offset,blob=queue.writes[0]
        self.assertEqual((buffer,offset),('dynamic-vertex-buffer',0))
        row=np.frombuffer(blob,dtype='f4').reshape(1,5)
        np.testing.assert_allclose(row,[[3,0,0,.25,.75]],atol=1e-6)

    def test_invalid_weight_does_not_write_gpu_buffer(self):
        renderer=c_webgpu_renderer.__new__(c_webgpu_renderer)
        queue=_queue()
        renderer.m_device=SimpleNamespace(queue=queue)
        renderer.m_node_worlds={0:np.eye(4)}
        renderer.m_meshes={0:[dict(
            positions=np.asarray([[1,0,0]],dtype='f4'),
            uvs=np.asarray([[0,0]],dtype='f4'),
            joints=np.asarray([[0,0,0,0]],dtype='i4'),
            weights=np.asarray([[-1,2,0,0]],dtype='f4'),
        )]}
        instance=dict(mesh=0,matrix=np.eye(4),joint_nodes=[0],
                      inverse_binds=[np.eye(4)],skinned_vbos={0:'vbo'})
        with self.assertRaises(ValueError):
            renderer._apply_skinning(instance)
        self.assertEqual(queue.writes,[])


if __name__=='__main__':
    unittest.main()
