import math
import unittest
from arika_gizmo import (gizmo_geometry, rotate_euler_local_axis, rotate_euler_world_axis,
    quaternion_from_matrix, quaternion_to_euler)


class GizmoGeometryTests(unittest.TestCase):
    def setUp(self):
        self.position=(3.0,4.0,5.0)
        self.axes=((1,0,0),(0,1,0),(0,0,1))
        self.size=10.0

    def test_move_gizmo_has_colored_axis_arrows(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'move')
        self.assertEqual(set(geometry),{0,1,2})
        for axis,segments in geometry.items():
            self.assertEqual(len(segments),5)
            self.assertEqual(segments[0][0],self.position)
            self.assertAlmostEqual(math.dist(*segments[0]),self.size)

    def test_scale_gizmo_has_axis_handles(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'scale')
        self.assertTrue(all(len(segments)==5 for segments in geometry.values()))
        self.assertTrue(all(math.isfinite(value) for segments in geometry.values() for line in segments for point in line for value in point))

    def test_rotation_gizmo_has_three_full_rings(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'rotate')
        self.assertTrue(all(len(segments)==48 for segments in geometry.values()))
        for segments in geometry.values():
            for a,b in segments:
                self.assertAlmostEqual(math.dist(self.position,a),self.size*.82,places=6)
                self.assertAlmostEqual(math.dist(self.position,b),self.size*.82,places=6)

    def test_rotation_changes_selected_local_axis(self):
        result = rotate_euler_local_axis((0.0, 0.0, 0.0), 1, math.pi / 2)
        self.assertAlmostEqual(result[0], 0.0, places=6)
        self.assertAlmostEqual(result[1], math.pi / 2, places=6)
        self.assertAlmostEqual(result[2], 0.0, places=6)

    def test_rotation_composes_with_existing_orientation(self):
        initial = (math.radians(30), math.radians(20), math.radians(10))
        result = rotate_euler_local_axis(initial, 2, math.radians(45))
        self.assertTrue(all(math.isfinite(value) for value in result))
        self.assertNotAlmostEqual(result[0], initial[0], places=5)
        self.assertNotAlmostEqual(result[1], initial[1], places=5)

    def test_rejects_unknown_mode_and_invalid_size(self):
        with self.assertRaises(ValueError):gizmo_geometry(self.position,self.axes,self.size,'shear')
        with self.assertRaises(ValueError):gizmo_geometry(self.position,self.axes,0,'move')

    def test_move_has_plane_and_view_plane_handles(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'move',include_extra=True)
        self.assertTrue({'plane_xy','plane_xz','plane_yz','plane_view'}.issubset(geometry))
        self.assertEqual(len(geometry['plane_xy']),4)

    def test_scale_has_plane_and_uniform_handles(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'scale',include_extra=True)
        self.assertTrue({'plane_xy','plane_xz','plane_yz','uniform'}.issubset(geometry))
        self.assertEqual(len(geometry['uniform']),4)

    def test_rotate_has_view_ring_and_trackball(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'rotate',include_extra=True)
        self.assertEqual(len(geometry['view']),48)
        self.assertEqual(len(geometry['trackball']),48)

    def test_combined_transform_has_move_rotate_scale_handles(self):
        geometry=gizmo_geometry(self.position,self.axes,self.size,'transform',include_extra=True)
        self.assertTrue({'move_x','rotate_x','scale_x','move_plane_xy','rotate_view','rotate_trackball','scale_uniform'}.issubset(geometry))

    def test_world_axis_rotation_and_matrix_quaternion_roundtrip(self):
        result=rotate_euler_world_axis((0.0,0.0,0.0),(0.0,1.0,0.0),math.pi/2)
        self.assertAlmostEqual(result[1],math.pi/2,places=6)
        quaternion=quaternion_from_matrix(((1,0,0),(0,1,0),(0,0,1)))
        euler=quaternion_to_euler(quaternion)
        self.assertTrue(all(abs(value)<1e-7 for value in euler))

    def test_native_quaternion_composition_parity(self):
        from arika_backend import quaternion_multiply
        pairs = [
            ((0., 0., 0., 1.), (0.2, -0.3, 0.1, 0.9)),
            ((0.5, 0., 0., math.sqrt(.75)), (0., 0.5, 0., math.sqrt(.75))),
            ((-0.2, 0.3, 0.4, 0.8), (0.25, -0.75, 0.1, 0.5)),
        ]
        for a, b in pairs:
            x, y, z, w = a
            dx, dy, dz, dw = b
            expected = (
                w*dx + x*dw + y*dz - z*dy,
                w*dy - x*dz + y*dw + z*dx,
                w*dz + x*dy - y*dx + z*dw,
                w*dw - x*dx - y*dy - z*dz,
            )
            actual = quaternion_multiply(a, b)
            for got, want in zip(actual, expected):
                self.assertAlmostEqual(got, want, places=12)

    def test_native_quaternion_rejects_invalid_components(self):
        from arika_backend import quaternion_multiply, BackendError
        with self.assertRaises(ValueError):
            quaternion_multiply((0, 0, 1), (0, 0, 0, 1))
        with self.assertRaises(BackendError):
            quaternion_multiply((math.nan, 0, 0, 1), (0, 0, 0, 1))



    def test_native_euler_conversion_at_pitch_singularity(self):
        from arika_backend import euler_to_quaternion, quaternion_to_euler
        for sign in (-1, 1):
            original = (0.0, sign * math.pi / 2, 0.0)
            quaternion = euler_to_quaternion(original)
            result = quaternion_to_euler(quaternion)
            for actual, expected in zip(result, original):
                self.assertAlmostEqual(actual, expected, places=9)

    def test_native_quaternion_inverse_identity_composition(self):
        from arika_backend import euler_to_quaternion, quaternion_inverse, quaternion_multiply
        quaternion = euler_to_quaternion((0.3, -0.4, 0.7))
        inverse = quaternion_inverse(quaternion)
        product = quaternion_multiply(quaternion, inverse)
        for actual, expected in zip(product, (0, 0, 0, 1)):
            self.assertAlmostEqual(actual, expected, places=10)
        with self.assertRaises(Exception):
            quaternion_inverse((0.0, 0.0, 0.0, 0.0))

    def test_native_hierarchy_matrix_matches_python_formula(self):
        from arika_backend import matrix_local, matrix_multiply, euler_to_quaternion
        from arika_models import local_matrix, multiply
        parent = dict(translation=[3.0, -2.0, 4.0],
                      rotation=euler_to_quaternion((0.4, 0.1, -0.2)),
                      scale=[2.0, 1.0, 0.5])
        child = dict(translation=[-1.0, 2.0, 0.5],
                     rotation=euler_to_quaternion((0.2, -0.3, 0.1)),
                     scale=[1.0, 3.0, 1.0])
        native_parent = matrix_local(parent['translation'], parent['rotation'], parent['scale'])
        native_child = matrix_local(child['translation'], child['rotation'], child['scale'])
        expected = multiply(local_matrix(parent), local_matrix(child))
        actual = matrix_multiply(native_parent, native_child)
        for row_a, row_b in zip(actual, expected):
            for value_a, value_b in zip(row_a, row_b):
                self.assertAlmostEqual(value_a, value_b, places=10)


if __name__=='__main__':
    unittest.main()
