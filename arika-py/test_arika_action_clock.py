import unittest
from arika_action_clock import startup_control,c_action_clock,sample_action
from arika_clock import c_native_clock
from arika_face_player import f32


class ActionClockTests(unittest.TestCase):
    def fixture(self,flags=0):
        records=[dict(motion_id=1,variant=0,speed=1,start_frame=0,end_frame=-1,flags=flags),
                 dict(motion_id=2,variant=0,speed=1,start_frame=0,end_frame=-1,flags=0x10000)]
        return {i:dict(record=r,motion=dict(fps=2,frame_count=3,channel_counts=[1,1,0]),control=startup_control(records,i)) for i,r in enumerate(records)}

    def test_common_start_clears_bridge_and_uses_record(self):
        segments=self.fixture();segments[0]['record'].update(speed=2,start_frame=1,end_frame=2)
        player=c_action_clock(segments)
        self.assertEqual((player.m_clock.m_start,player.m_clock.m_end,player.m_clock.m_speed),(.5,1,2))
        self.assertTrue(player.m_events[0]['clears_previous_bridge'])

    def test_zero_carry_starts_incoming_at_baseline(self):
        player=c_action_clock(self.fixture());state=player.step(1.5)
        self.assertEqual(state['segment'],1)
        self.assertEqual(state['clock']['position'],-.5)
        self.assertTrue(state['clock']['active'])

    def test_positive_carry_updates_incoming(self):
        player=c_action_clock(self.fixture());state=player.step(1.75)
        self.assertEqual(state['segment'],1)
        self.assertEqual(state['clock']['position'],-.25)
        self.assertEqual(player.m_events[1]['carry_in'],.25)

    def test_inherited_blend_does_not_restart(self):
        player=c_action_clock(self.fixture(),initial_blend=4)
        player.step(1.5)
        self.assertEqual((player.m_clock.m_blend_total,player.m_clock.m_blend_remaining),(4,2.5))
        self.assertEqual(player.m_events[1]['settings']['blend_request'],-1.)

    def test_outgoing_flag_resets_blend(self):
        player=c_action_clock(self.fixture(0x200000),initial_blend=4)
        player.step(1.5)
        self.assertEqual((player.m_clock.m_blend_total,player.m_clock.m_blend_remaining),(f32(.17),f32(.17)))

    def test_replay_priority_keeps_blend(self):
        records=[dict(flags=0x230000)]
        self.assertEqual(startup_control(records,0),dict(segment=0,transition='replay',blend_request=-1.))

    def test_multiple_transitions_in_one_delta(self):
        player=c_action_clock(self.fixture(0x20000));state=player.step(3.25)
        self.assertEqual(state['segment'],0)
        self.assertEqual(state['event_count'],3)
        self.assertEqual(state['clock']['position'],-.25)

    def test_terminal_stop_and_later_carry(self):
        player=c_action_clock(self.fixture());state=player.step(3.25)
        self.assertTrue(state['finished']);self.assertEqual(state['carry'],.25)
        self.assertEqual(player.step(.5)['carry'],.5)

    def test_jump_and_stop_precedence(self):
        self.assertEqual(startup_control([dict(flags=0x240001),dict(flags=0x10000)],0)['segment'],1)
        self.assertIsNone(startup_control([dict(flags=0x250001),dict(flags=0x10000)],0)['segment'])

    def test_unsupported_context_flags_rejected(self):
        with self.assertRaises(ValueError):startup_control([dict(flags=0x100000)],0)
        with self.assertRaises(ValueError):startup_control([dict(flags=0x400000)],0)

    def test_zero_range_rejected(self):
        segments=self.fixture();segments[0]['motion']['frame_count']=1
        with self.assertRaises(ValueError):c_action_clock(segments)

    def test_inheritance_precedes_special_setup_tick(self):
        clock=c_native_clock(2,1,blend=-1,inherited_blend=(2,1))
        self.assertEqual(clock.m_blend_remaining,.5)
        self.assertFalse(clock.snapshot()['active'])
        with self.assertRaises(ValueError):c_native_clock(2,2,blend=-1,inherited_blend=(1,2))

    def test_sampling_without_authored_switch_times(self):
        samples,events=sample_action(self.fixture(),4,60)
        self.assertEqual(len(samples),241)
        self.assertEqual([e['segment'] for e in events],[0,1])
        self.assertTrue(samples[-1]['finished'])


if __name__=='__main__':unittest.main()
