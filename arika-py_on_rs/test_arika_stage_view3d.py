import math
import unittest
from arika_stage_view3d import project,prepare

class StageViewTests(unittest.TestCase):
    def fixture(self):
        root=dict(index=0,name='STAGE',kind=1,parent=-1,children=[1],references=[],translation=[0,0,0],rotation_radians=[0,0,0],scale=[1,1,1])
        child=dict(index=1,name='box',kind=2,parent=0,children=[],references=[],translation=[10,20,30],rotation_radians=[0,0,0],scale=[1,1,1])
        scene=dict(nodes=[root,child],roots=[0],stage_root=0)
        mesh=dict(name='box',vertices=[dict(position=p) for p in ([0,0,0],[1,0,0],[0,1,0])],primitives=[dict(triangles=[[0,1,2]])])
        return scene,dict(meshes=[mesh])
    def test_projection(self):
        self.assertEqual(project([1,2,3],0,0),(1,2,3))
        p=project([1,2,3],math.pi/2,0)
        self.assertAlmostEqual(p[0],3);self.assertAlmostEqual(p[2],-1)
    def test_geometry_uses_authored_transform(self):
        scene,model=self.fixture();data=prepare(scene,model)
        self.assertEqual(data['triangles'][0],(1,[(10,20,30),(11,20,30),(10,21,30)]))
        self.assertFalse(data['sampled'])
    def test_parent_translation_and_scale_propagate_to_child(self):
        scene, model = self.fixture()
        scene['nodes'][0]['translation'] = [2, 3, 4]
        scene['nodes'][0]['scale'] = [2, 2, 2]
        data = prepare(scene, model)
        vertices = data['triangles'][0][1]
        self.assertEqual(vertices, [(22, 43, 64), (24, 43, 64), (22, 45, 64)])

    def test_missing_model_still_produces_origins(self):
        scene,model=self.fixture();data=prepare(scene,None)
        self.assertEqual(data['triangles'],[]);self.assertEqual(len(data['points']),2)
    def test_large_mesh_sampling_is_bounded(self):
        scene,model=self.fixture();model['meshes'][0]['primitives'][0]['triangles']=[[0,1,2]]*25
        data=prepare(scene,model,limit=10)
        self.assertTrue(data['sampled']);self.assertLessEqual(len(data['triangles']),10)

    def test_default_keeps_all_faces(self):
        scene,model=self.fixture();model['meshes'][0]['primitives'][0]['triangles']=[[0,1,2]]*13001
        data=prepare(scene,model)
        self.assertEqual(len(data['triangles']),13001);self.assertFalse(data['sampled'])

    def test_image_renderer_fills_both_halves(self):
        from arika_stage_view3d import render_image
        data=dict(triangles=[(0,[(0,0,0),(1,0,0),(1,1,0)]),(0,[(0,0,0),(1,1,0),(0,1,0)])],lines=[])
        image=render_image(data,100,100,0,0,60,(20,80),selected=0)
        self.assertEqual(image.getpixel((30,30)),(255,202,102))
        self.assertEqual(image.getpixel((70,70)),(255,202,102))

    def test_nearer_triangle_overwrites_far_triangle(self):
        from arika_stage_view3d import render_image
        far=[(0,0,-1),(1,0,-1),(0,1,-1)];near=[(0,0,1),(1,0,1),(0,1,1)]
        data=dict(triangles=[(1,near),(0,far)],lines=[])
        image=render_image(data,100,100,0,0,60,(20,80),selected=1)
        self.assertEqual(image.getpixel((30,70)),(255,202,102))
