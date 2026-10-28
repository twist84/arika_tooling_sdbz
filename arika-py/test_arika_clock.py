import unittest
from arika_clock import c_native_clock,PAUSED,ACTIVE,WRAPPED


class NativeClockTests(unittest.TestCase):
    def test_forward_setup_and_first_tick(self):
        clock=c_native_clock(2,3)
        self.assertEqual(clock.snapshot()['position'],-.5)
        self.assertEqual(clock.step(.5)['position'],0)
        self.assertEqual(clock.step(.5)['position'],.5)
        state=clock.step(.5)
        self.assertEqual(state['position'],1)
        self.assertFalse(state['active'])
        self.assertEqual(state['carry'],0)

    def test_carry_is_in_wall_delta_units(self):
        clock=c_native_clock(2,3,speed=2)
        state=clock.step(1)
        self.assertEqual(state['position'],1)
        self.assertEqual(state['carry'],.25)
        self.assertEqual(clock.step(.125)['carry'],.125)

    def test_reverse(self):
        clock=c_native_clock(2,3,reverse=True)
        self.assertEqual(clock.step(.5)['position'],1)
        state=clock.step(2)
        self.assertEqual((state['position'],state['carry']),(0,1))
        self.assertFalse(state['active'])

    def test_loop_boundary_gap_fraction(self):
        clock=c_native_clock(2,3,loop=True)
        state=clock.step(1.6)
        self.assertTrue(state['flags']&WRAPPED)
        self.assertAlmostEqual(state['wrap_fraction'],.2,places=6)
        self.assertEqual(state['sample_time'],0)
        reverse=c_native_clock(2,3,loop=True,reverse=True).step(1.6)
        self.assertAlmostEqual(reverse['wrap_fraction'],.8,places=6)

    def test_blend_countdown_uses_scaled_time(self):
        clock=c_native_clock(2,100,speed=2,blend=1)
        clock.m_flags|=0x100
        state=clock.step(.25)
        self.assertEqual((state['blend_remaining'],state['blend_weight']),(.5,.5))
        state=clock.step(.3)
        self.assertEqual(state['blend_weight'],1)
        self.assertFalse(state['flags']&0x100)

    def test_stop_timer_truncates_motion_delta(self):
        state=c_native_clock(2,100,speed=2,blend=1,stop_after=.5).step(.5)
        self.assertEqual((state['position'],state['carry'],state['blend_remaining']),(0,.25,.5))
        self.assertFalse(state['active'])

    def test_pause_inactive_and_nonpositive_delta(self):
        clock=c_native_clock(2,3);position=clock.m_position;clock.m_flags|=PAUSED
        for delta in (0,-1,.5):
            self.assertEqual(clock.step(delta)['position'],position)
            self.assertEqual(clock.step(delta)['carry'],0)
        clock.m_flags&=~ACTIVE
        self.assertEqual(clock.step(-.5)['carry'],-.5)

    def test_initialization_special_update_and_invalid_setup(self):
        single=c_native_clock(2,1)
        self.assertIsNotNone(single.m_initialization_tick)
        self.assertFalse(single.snapshot()['active'])
        zero_timer=c_native_clock(2,3,stop_after=0)
        self.assertEqual(zero_timer.snapshot()['position'],0)
        with self.assertRaises(ValueError):c_native_clock(0,3)
        with self.assertRaises(ValueError):c_native_clock(1e-50,3)
        with self.assertRaises(ValueError):c_native_clock(60,3,start=2,end=0)


if __name__=='__main__':unittest.main()
