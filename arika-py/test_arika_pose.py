import unittest
from arika_pose import apply_bone,apply_bone_pair,blend_quaternion,sample_native_track,c_native_pose,sample_pose


class NativePoseTests(unittest.TestCase):
    def setUp(self):
        self.rest=dict(translation=[0.,0.,0.],rotation=[0.,0.,0.,1.],scale=[2.,2.,2.])
        self.target=dict(translation=[10.,20.,30.],rotation=[0.,0.,1.,0.],scale=[4.,4.,4.])

    def test_masks_preserve_disabled_components(self):
        out=apply_bone(self.rest,self.target,self.rest,1,.5)
        self.assertEqual(out['translation'],[5.,10.,15.])
        self.assertEqual(out['rotation'],self.rest['rotation'])
        self.assertEqual(out['scale'],self.rest['scale'])
        self.assertEqual(apply_bone(self.rest,self.target,self.rest,4,1,scale_enabled=False),self.rest)

    def test_missing_node_uses_rest_and_unit_scale(self):
        out=apply_bone(self.target,None,self.rest,7,1,blend_active=False)
        self.assertEqual(out,dict(self.rest,scale=[1.,1.,1.]))

    def test_blend_uses_live_pose(self):
        first=apply_bone(self.rest,self.target,self.rest,1,.5)
        second=apply_bone(first,self.target,self.rest,1,.5)
        self.assertEqual(second['translation'],[7.5,15.,22.5])

    def test_quaternion_shortest_path(self):
        q=[0.,0.,0.,1.]
        self.assertEqual(blend_quaternion(q,[0.,0.,0.,-1.],.5),q)
        self.assertAlmostEqual(blend_quaternion(q,self.target['rotation'],.5)[2],2**-.5,places=6)

    def test_near_parallel_does_not_normalize(self):
        q=blend_quaternion([0.,0.,0.,1.],[.01,0.,0.,.99995],.5)
        self.assertNotEqual(sum(v*v for v in q),1.)

    def test_track_snap_and_endpoints(self):
        track=dict(times=[0.,1.,2.],values=[[0.,0.,0.],[10.,0.,0.],[20.,0.,0.]])
        self.assertEqual(sample_native_track(track,1.000001,'translation'),[10.,0.,0.])
        self.assertEqual(sample_native_track(track,.5,'translation'),[5.,0.,0.])
        self.assertEqual(sample_native_track(track,9.,'translation'),[20.,0.,0.])
        self.assertEqual(sample_native_track(track,-1.,'translation'),[0.,0.,0.])

    def test_player_missing_node_and_scale_gate(self):
        player=c_native_pose({'bone':self.target},{'bone':7})
        motion=dict(nodes=[],channel_counts=[0,0,0])
        out=player.apply(motion,0,1,False)['bone']
        self.assertEqual(out,self.target) # Its explicit rest buffer is the initial pose.
        motion['channel_counts'][2]=1
        self.assertEqual(player.apply(motion,0,1,False)['bone']['scale'],[1.,1.,1.])

    def test_clock_end_holds_pose(self):
        model=dict(nodes=[dict(name='bone',**self.rest)])
        package=dict(bones=[dict(name='bone',flags=1)])
        tracks={p:dict(times=[0.,.5],values=[self.rest[p],self.target[p]]) for p in self.rest}
        motion=dict(fps=2,frame_count=2,last_frame_time=.5,duration=1.,channel_counts=[1,1,0],nodes=[dict(name='bone',tracks=tracks)])
        samples=sample_pose(model,package,motion,2,30,blend=0)
        self.assertEqual(samples[-1]['pose']['bone']['translation'],self.target['translation'])
        self.assertEqual(samples[-1]['pose'],samples[-2]['pose'])
        self.assertFalse(samples[-1]['clock']['active'])
        self.assertEqual(model['nodes'][0]['translation'],[0.,0.,0.])

    def loop_fixture(self,reverse=False,blend=0):
        model=dict(nodes=[dict(name='bone',**self.rest)])
        package=dict(bones=[dict(name='bone',flags=1)])
        tracks={p:dict(times=[0.,.5],values=[self.rest[p],self.target[p]]) for p in self.rest}
        motion=dict(fps=2,frame_count=2,last_frame_time=.5,duration=1.,channel_counts=[1,1,0],nodes=[dict(name='bone',tracks=tracks)])
        return sample_pose(model,package,motion,2.25,60,blend=blend,reverse=reverse,loop=True)

    def test_two_sources_before_live_blend(self):
        current=dict(self.rest,translation=[12.,12.,12.])
        out=apply_bone_pair(current,self.target,self.rest,self.rest,1,.25,.5)
        self.assertEqual(out['translation'],[9.75,13.5,17.25])

    def test_pair_missing_sources(self):
        a=apply_bone_pair(self.rest,None,self.target,self.rest,7,.25,1,False)
        b=apply_bone_pair(self.rest,self.target,None,self.rest,7,.75,1,False)
        self.assertEqual(a,b)
        self.assertEqual(a['translation'],[2.5,5.,7.5])
        self.assertEqual(a['scale'],[1.75,1.75,1.75])
        self.assertEqual(apply_bone_pair(self.target,None,None,self.rest,7,.9,1,False),dict(self.rest,scale=[1.,1.,1.]))

    def test_pair_component_masks(self):
        out=apply_bone_pair(self.rest,self.target,self.rest,self.rest,1,.5,1,False)
        self.assertEqual(out['rotation'],self.rest['rotation'])
        self.assertEqual(out['scale'],self.rest['scale'])

    def test_pair_rejects_invalid_fraction(self):
        for fraction in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):apply_bone_pair(self.rest,self.target,self.rest,self.rest,7,fraction,1)

    def test_forward_loop_seam(self):
        samples=self.loop_fixture()
        for tick in (75,135):
            self.assertAlmostEqual(samples[tick]['clock']['wrap_fraction'],.5,places=4)
            self.assertAlmostEqual(samples[tick]['pose']['bone']['translation'][0],5.,places=4)
        self.assertTrue(samples[-1]['clock']['active'])

    def test_reverse_loop_seam(self):
        samples=self.loop_fixture(reverse=True)
        self.assertAlmostEqual(samples[75]['clock']['wrap_fraction'],.5,places=4)
        self.assertAlmostEqual(samples[75]['pose']['bone']['translation'][0],5.,places=4)
        self.assertTrue(samples[-1]['clock']['active'])

    def test_no_seam_blend_before_first_wrap(self):
        samples=self.loop_fixture()
        self.assertIsNone(samples[15]['clock']['wrap_fraction'])
        self.assertEqual(samples[15]['pose']['bone']['translation'],[0.,0.,0.])

    def test_loop_seam_during_live_blend(self):
        samples=self.loop_fixture(blend=2)
        previous=samples[74]['pose']['bone'];state=samples[75]['clock']
        expected=apply_bone_pair(previous,self.target,self.rest,self.rest,1,state['wrap_fraction'],state['blend_weight'])
        self.assertEqual(samples[75]['pose']['bone'],expected)


if __name__=='__main__':unittest.main()
