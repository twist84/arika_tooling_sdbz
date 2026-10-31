import unittest
import numpy as np
from arika_webgpu import camera_matrix,selection_nodes,viewport_guides


class WebGpuCameraTests(unittest.TestCase):
    def test_world_guides_are_y_up_and_can_be_disabled(self):
        self.assertEqual(viewport_guides([0,0,0],100,False,False),[])
        grid=viewport_guides([30,5,40],100,True,False)
        self.assertEqual(len(grid),1)
        self.assertEqual(len(grid[0][0]),84)
        self.assertTrue(all(point[1]==0 for point in grid[0][0]))
        axes=viewport_guides([0,0,0],100,False,True)
        self.assertEqual(len(axes),3)
        self.assertLess(axes[1][0][0][1],0)
        self.assertGreater(axes[1][0][1][1],0)
        self.assertTrue(all(np.isfinite(np.asarray(positions)).all() for positions,_ in axes))

    def test_hidden_parent_hides_descendants_only(self):
        from arika_scene_state import hidden_nodes,node_state
        doc={'nodes':[{'children':[1],'extras':{'arika_editor':{'hidden':True}}},{},{}]}
        self.assertEqual(hidden_nodes(doc),{0,1})
        self.assertTrue(node_state(doc,2)['locked'])

    def test_selection_expands_groups_and_handles_empty_selection(self):
        doc={'nodes':[{'children':[1,2]},{'children':[3]},{},{}]}
        self.assertEqual(selection_nodes(doc,{0,1}),{0,1,2,3})
        self.assertEqual(selection_nodes(doc,{1,2}),{1,2,3})
        self.assertEqual(selection_nodes(doc,-1),set())
        self.assertEqual(selection_nodes(doc,set()),set())

    def test_orthographic_scale_depth_and_toggle_match(self):
        center=np.array([10,20,30]);distance=100
        ortho=camera_matrix(center,distance,0,0,1.5,True)
        perspective=camera_matrix(center,distance,0,0,1.5)
        for point in (center,center+[10,5,0]):
            a=ortho@np.append(point,1);b=perspective@np.append(point,1)
            np.testing.assert_allclose(a[:2]/a[3],b[:2]/b[3],atol=1e-6)
            self.assertGreaterEqual(a[2]/a[3],0);self.assertLessEqual(a[2]/a[3],1)
        a=ortho@np.append(center+[10,0,0],1)
        b=ortho@np.append(center+[10,0,-100],1)
        self.assertAlmostEqual(float(a[0]),float(b[0]))

    def test_target_center_and_webgpu_depth(self):
        matrix=camera_matrix([10,20,30],100,35,30,1.5)
        clip=matrix@np.array([10,20,30,1]);ndc=clip[:3]/clip[3]
        self.assertAlmostEqual(float(ndc[0]),0,places=5)
        self.assertAlmostEqual(float(ndc[1]),0,places=5)
        self.assertGreaterEqual(ndc[2],0);self.assertLessEqual(ndc[2],1)

    def test_aspect_changes_horizontal_scale_only(self):
        a=camera_matrix([0,0,0],100,0,0,1)
        b=camera_matrix([0,0,0],100,0,0,2)
        self.assertAlmostEqual(float(b[0,0]),float(a[0,0])/2)
        np.testing.assert_array_equal(a[1:],b[1:])
