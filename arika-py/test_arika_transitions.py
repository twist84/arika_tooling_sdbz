import copy
import unittest
from arika_transitions import normalize_schedule,c_transition_player,sample_transitions


class TransitionTests(unittest.TestCase):
    def fixture(self,at=1.,blend=0,reverse=False):
        rest=dict(translation=[0.,0.,0.],rotation=[0.,0.,0.,1.],scale=[1.,1.,1.])
        model=dict(nodes=[dict(name='bone',**rest)])
        package=dict(bones=[dict(name='bone',flags=1)])
        rows=normalize_schedule(dict(segments=[dict(at=0,motion_id=1,blend=0),dict(at=at,motion_id=2,blend=blend,reverse=reverse)]))
        segments=[]
        for row,value in zip(rows,(8.,20.)):
            tracks={p:dict(times=[0.,.5],values=[v,v]) for p,v in dict(rest,translation=[value,0.,0.]).items()}
            motion=dict(fps=2,frame_count=2,last_frame_time=.5,duration=1,channel_counts=[1,1,0],nodes=[dict(name='bone',tracks=tracks)])
            segments.append(dict(setup=row,package=package,motion=motion))
        return model,segments

    def test_switch_keeps_live_pose(self):
        model,segments=self.fixture();player=c_transition_player(model,segments)
        player.switch(0);player.step(1);player.switch(1)
        self.assertEqual(player.snapshot(1)['pose']['bone']['translation'][0],8.)
        self.assertEqual(player.snapshot(1)['clock']['position'],-.5)

    def test_transition_gap_then_live_blend(self):
        model,segments=self.fixture(blend=1);player=c_transition_player(model,segments)
        player.switch(0);player.step(1);player.switch(1);player.step(.25)
        self.assertEqual(player.m_bridge['fraction'],.5)
        self.assertEqual(player.m_player.m_pose['bone']['translation'][0],9.5)
        player.step(.25)
        self.assertIsNone(player.m_bridge)
        self.assertEqual(player.m_player.m_pose['bone']['translation'][0],14.75)

    def test_direct_transition_gap(self):
        model,segments=self.fixture();player=c_transition_player(model,segments)
        player.switch(0);player.step(1);player.switch(1);player.step(.25)
        self.assertEqual(player.m_player.m_pose['bone']['translation'][0],14.)

    def test_reverse_incoming_gap(self):
        model,segments=self.fixture(reverse=True);player=c_transition_player(model,segments)
        player.switch(0);player.step(1);player.switch(1);player.step(.25)
        self.assertEqual(player.m_bridge['fraction'],.5)
        self.assertEqual(player.m_bridge['incoming_time'],.5)
        self.assertEqual(player.m_player.m_pose['bone']['translation'][0],14.)

    def test_off_tick_switch_splits_delta(self):
        model,segments=self.fixture(at=.505)
        samples,events=sample_transitions(model,segments,1,60)
        self.assertEqual(samples[30]['segment'],0)
        self.assertEqual(samples[31]['segment'],1)
        self.assertEqual(events[1]['at'],.505)
        self.assertAlmostEqual(samples[31]['bridge']['fraction'],(.5166666666666667-.505)/.5,places=6)
        self.assertAlmostEqual(samples[31]['pose']['bone']['translation'][0],8+12*(.5166666666666667-.505)/.5,places=5)

    def test_inactive_outgoing_holds_until_switch(self):
        model,segments=self.fixture(at=2)
        samples,events=sample_transitions(model,segments,3,60)
        self.assertFalse(samples[90]['clock']['active'])
        self.assertEqual(events[1]['outgoing_time'],.5)
        self.assertEqual(samples[90]['pose']['bone']['translation'][0],8.)

    def test_hand_requests_carry_between_segments(self):
        model,segments=self.fixture()
        for segment,value in zip(segments,([3.,0.,4.],[-1.,0.,-1.])):
            segment['motion']['nodes'].append(dict(name='HandAni',tracks=dict(translation=dict(times=[0.],values=[value]))))
        samples,_=sample_transitions(model,segments,2,60)
        self.assertEqual(samples[-1]['hands'],[3,4])

    def test_invalid_schedules_rejected(self):
        for rows in ([],[dict(at=1,motion_id=1)],[dict(at=0,motion_id=1),dict(at=0,motion_id=2)],
                     [dict(at=0,motion_id=1,unknown=1)],[dict(at=0,motion_id=1,loop=1)],
                     [dict(at=0,motion_id=1,blend=-1)],[dict(at=0,motion_id=1,speed=float('nan'))]):
            with self.assertRaises(ValueError):normalize_schedule(dict(segments=rows))

    def test_contextual_mask_rebinding_rejected(self):
        model,segments=self.fixture();segments[1]['package']=copy.deepcopy(segments[1]['package'])
        segments[1]['package']['bones'][0]['flags']=3
        with self.assertRaises(ValueError):c_transition_player(model,segments)

    def test_future_segment_rejected(self):
        model,segments=self.fixture(at=2)
        with self.assertRaises(ValueError):sample_transitions(model,segments,1,60)


if __name__=='__main__':unittest.main()
