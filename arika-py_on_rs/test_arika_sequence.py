import unittest
from arika_sequence import next_segment,plan_sequence,sample_sequence,synthesize_motion


def record(motion=0,flags=0,speed=1,start=0,end=-1):
    return dict(motion_id=motion,variant=0,flags=flags,speed=speed,start_frame=start,end_frame=end)


def motion(nodes=None):
    return dict(name='fixture',fps=2,frame_count=2,duration=1,last_frame_time=.5,nodes=nodes or [])


def resolver(r):
    return motion(),dict(status='resolved',package_index=r['motion_id'])


class SequenceTests(unittest.TestCase):
    def test_native_transition_precedence_and_guards(self):
        for flags,target,reason in [(0,1,'advance'),(0x10000,None,'stop'),(0x20000,0,'replay'),
            (0x40001,1,'jump'),(0x30000,0,'replay'),(0x500FF,None,'stop'),(0x600FF,0,'replay')]:
            self.assertEqual(next_segment([record(flags=flags),record(flags=0x10000)],0),(target,reason))
        for flags in (0x100000,0x200000,0x400000,1,0x40002):
            with self.assertRaises(ValueError):next_segment([record(flags=flags)],0)
        with self.assertRaises(ValueError):next_segment([record()],0)

    def test_stop_and_final_pose_hold(self):
        plan,_=plan_sequence([record(flags=0x10000)],resolver)
        self.assertEqual(plan['total_path_duration'],1)
        samples=sample_sequence(plan,[0,.25,.5,.75,1,100])
        self.assertEqual([s['motion_time'] for s in samples],[0,.25,.5,.5,.5,.5])
        self.assertEqual([s['finished'] for s in samples],[False,False,False,False,True,True])

    def test_prefix_replay_and_large_cycle_skip(self):
        plan,_=plan_sequence([record(),record(1,0x20000)],resolver)
        self.assertEqual((plan['cycle_start'],plan['cycle_duration']),(1,1))
        samples=sample_sequence(plan,[0,.5,1,1.25,2,1000001.25])
        self.assertEqual([s['segment'] for s in samples],[0,0,1,1,1,1])
        self.assertEqual(samples[-1]['cycle_iteration'],1000000)
        self.assertEqual(samples[-1]['motion_time'],.25)

    def test_jump_and_unreachable_unsupported_segment(self):
        records=[record(flags=0x40002),record(flags=0x100000),record(2,0x40000)]
        plan,_=plan_sequence(records,resolver)
        self.assertEqual([s['segment'] for s in plan['segments']],[0,2])
        self.assertEqual((plan['cycle_start'],plan['cycle_duration']),(0,2))
        self.assertEqual(sample_sequence(plan,[1])[0]['segment'],2)

    def test_ranges_and_speed_floor(self):
        plan,_=plan_sequence([record(flags=0x10000,speed=0,start=-5,end=100)],resolver)
        entry=plan['segments'][0]
        self.assertEqual((entry['start_frame'],entry['end_frame'],entry['effective_speed']),(0,1,.01))
        self.assertEqual(plan['total_path_duration'],100)
        for r in [record(flags=0x10000,start=1,end=0),record(flags=0x10000,speed=float('nan'))]:
            with self.assertRaises(ValueError):plan_sequence([r],resolver)
        with self.assertRaises(ValueError):sample_sequence(plan,[1,0])

    def test_synthesis_rest_pose_and_retained_hands(self):
        def track(values):return dict(times=[0,.5],values=values)
        a=motion([dict(name='root',tracks=dict(translation=track([[0,0,0],[2,0,0]]))),
            dict(name='HandAni',tracks=dict(translation=track([[2,0,3],[2,0,3]])))])
        b=motion([dict(name='HandAni',tracks=dict(translation=track([[-1,0,-1],[-1,0,-1]])))])
        plan,motions=plan_sequence([record(),record(1,0x10000)],lambda r:([a,b][r['motion_id']],{}))
        samples=sample_sequence(plan,[0,.5,1,1.5,2])
        model=dict(nodes=[dict(name='root',translation=[9,8,7],rotation=[0,0,0,1],scale=[1,1,1])])
        synthetic=synthesize_motion(model,plan,motions,samples)
        self.assertEqual(synthetic['nodes'][0]['tracks']['translation']['values'],[[0,0,0],[2,0,0],[9,8,7],[9,8,7],[9,8,7]])
        self.assertEqual(synthetic['nodes'][-1]['tracks']['translation']['values'],[[2,0,3]]*5)


if __name__=='__main__':unittest.main()
