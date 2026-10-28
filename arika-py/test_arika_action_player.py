import copy
import unittest
from arika_action_clock import startup_control
from arika_action_player import c_action_player,sample_action_poses
from arika_face_player import f32


class ActionPlayerTests(unittest.TestCase):
    def fixture(self,flags=0):
        rest=dict(translation=[0.,0.,0.],rotation=[0.,0.,0.,1.],scale=[1.,1.,1.])
        model=dict(nodes=[dict(name='bone',**rest)])
        package=dict(bones=[dict(name='bone',flags=1)])
        records=[dict(motion_id=i,variant=0,speed=1,start_frame=0,end_frame=-1,flags=f) for i,f in enumerate((flags,0x10000))]
        segments={}
        for i,value in enumerate((8.,20.)):
            tracks={p:dict(animated=False,times=[0.],values=[v]) for p,v in dict(rest,translation=[value,0.,0.]).items()}
            motion=dict(fps=2,frame_count=3,last_frame_time=1.,duration=1.5,channel_counts=[0,0,0],nodes=[dict(name='bone',tracks=tracks)])
            segments[i]=dict(record=records[i],package=package,motion=motion,control=startup_control(records,i))
        return model,segments

    def test_initial_pose_and_first_evaluation(self):
        model,segments=self.fixture();p=c_action_player(model,segments)
        self.assertEqual(p.snapshot()['pose']['bone']['translation'][0],0.)
        state=p.step(.25)
        self.assertEqual(state['pose']['bone']['translation'][0],8.)
        self.assertEqual(state['evaluations'][0]['pose_dispatch'],'helper')

    def test_bulk_preserves_constants_and_missing_bones(self):
        model,segments=self.fixture()
        model['nodes'].append(dict(name='missing',translation=[5.,0.,0.],rotation=[0.,0.,0.,1.],scale=[1.,1.,1.]))
        segments[0]['package']['bones'].append(dict(name='missing',flags=1))
        p=c_action_player(model,segments);p.step(.25)
        p.m_pose.m_pose['bone']['translation'][0]=12.
        p.m_pose.m_pose['missing']['translation'][0]=13.
        state=p.step(.25)
        self.assertEqual(state['evaluations'][0]['pose_dispatch'],'animated_channels')
        self.assertEqual(state['pose']['bone']['translation'][0],12.)
        self.assertEqual(state['pose']['missing']['translation'][0],13.)

    def test_bulk_samples_animated_track(self):
        model,segments=self.fixture()
        track=segments[0]['motion']['nodes'][0]['tracks']['translation']
        track.update(animated=True,times=[0.,1.],values=[[0.,0.,0.],[8.,0.,0.]])
        segments[0]['motion']['channel_counts'][0]=1
        p=c_action_player(model,segments);p.step(.5);state=p.step(.25)
        self.assertEqual(state['pose']['bone']['translation'][0],2.)
        self.assertEqual(state['evaluations'][0]['pose_dispatch'],'animated_channels')

    def test_terminal_pose_before_zero_carry_start(self):
        model,segments=self.fixture();p=c_action_player(model,segments);state=p.step(1.5)
        self.assertEqual(state['segment'],1)
        self.assertEqual(state['pose']['bone']['translation'][0],8.)
        self.assertEqual([(e['segment'],e['terminal']) for e in state['evaluations']],[(0,True)])
        self.assertEqual(state['clock']['position'],-.5)

    def test_carry_evaluates_both_clips_in_order(self):
        model,segments=self.fixture();state=c_action_player(model,segments).step(1.75)
        self.assertEqual([e['segment'] for e in state['evaluations']],[0,1])
        self.assertEqual(state['pose']['bone']['translation'][0],20.)

    def test_common_start_has_no_outgoing_bridge(self):
        model,segments=self.fixture();p=c_action_player(model,segments);p.step(1.5)
        self.assertEqual(p.step(.25)['pose']['bone']['translation'][0],20.)

    def test_blend_reset_targets_incoming_directly(self):
        model,segments=self.fixture(0x200000);p=c_action_player(model,segments);p.step(1.5);state=p.step(.01)
        weight=state['clock']['blend_weight']
        self.assertEqual(state['pose']['bone']['translation'][0],f32(8+f32(12*weight)))
        self.assertTrue(state['evaluations'][0]['blend_active'])

    def test_blend_expiry_forces_helper_before_bulk(self):
        model,segments=self.fixture();p=c_action_player(model,segments,initial_blend=.3)
        p.step(.1);state=p.step(.25)
        self.assertEqual(state['evaluations'][0]['pose_dispatch'],'helper')
        self.assertFalse(state['evaluations'][0]['blend_active'])
        self.assertEqual(p.step(.1)['evaluations'][0]['pose_dispatch'],'animated_channels')

    def test_large_delta_replays_pose_per_clock_update(self):
        model,segments=self.fixture(0x20000);state=c_action_player(model,segments).step(3.25)
        self.assertEqual([e['segment'] for e in state['evaluations']],[0,0,0])
        self.assertEqual(state['evaluation_count'],3)

    def test_terminal_stop_holds_without_evaluating(self):
        model,segments=self.fixture();p=c_action_player(model,segments);p.step(3.25);state=p.step(.25)
        self.assertTrue(state['finished']);self.assertEqual(state['evaluations'],[])
        self.assertEqual(state['pose']['bone']['translation'][0],20.)

    def test_hands_carry_across_clip_start(self):
        model,segments=self.fixture()
        for segment,values in zip(segments.values(),([3.,0.,4.],[-1.,0.,-1.])):
            segment['motion']['nodes'].append(dict(name='HandAni',tracks=dict(translation=dict(animated=False,times=[0.],values=[values]))))
        p=c_action_player(model,segments);self.assertEqual(p.step(1.75)['hands'],[3,4])

    def test_contextual_rebinding_rejected(self):
        model,segments=self.fixture();segments[1]['package']=copy.deepcopy(segments[1]['package'])
        segments[1]['package']['bones'][0]['flags']=3
        with self.assertRaises(ValueError):c_action_player(model,segments)

    def test_sample_poses_automatically(self):
        model,segments=self.fixture();samples,events=sample_action_poses(model,segments,4,60)
        self.assertEqual(len(samples),241);self.assertEqual(len(events),2)
        self.assertTrue(samples[-1]['finished'])


if __name__=='__main__':unittest.main()
