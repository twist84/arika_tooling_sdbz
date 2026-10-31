import unittest
from arika_face_player import c_face_player, sample_program, sample_timeline
from arika_faces import resolve_timeline
from test_arika_face_player import event


class TimelineTests(unittest.TestCase):
    def test_delayed_start_has_idle_preroll_and_snaps_forward(self):
        records=[event(0,0,4),event(.5,end=True)]
        output=sample_program(records,1,blink=False,face_start=.201)
        self.assertEqual(output['face_start_sampled'],13/60)
        self.assertTrue(all(s['blend']==0 and s['script_time']==-1 for s in output['samples'][:13]))
        self.assertEqual(output['samples'][13]['script_time'],0)
        self.assertGreater(output['samples'][13]['blend'],0)

    def test_start_preserves_rng_pose_and_phase(self):
        player=c_face_player(seed=7)
        for _ in range(12):
            player.tick()
        before=(player.m_seed,player.m_pose,player.m_elapsed,player.m_progress,player.m_blink_delay)
        flags=player.m_flags
        player.start_program([event(0,1,6),event(1,end=True)])
        self.assertEqual((player.m_seed,player.m_pose,player.m_elapsed,player.m_progress,player.m_blink_delay),before)
        self.assertEqual(player.m_flags,(flags|0x20)&0xFFFFF020)
        self.assertEqual((player.m_index,player.m_script_time),(0,-1))

    def test_restart_matches_continuous_player_not_new_random_seed(self):
        a=[event(0,0,6),event(2,end=True)]
        b=[event(0,1,6),event(2,end=True)]
        events=[dict(time=0,group=0,program=1,records=a),dict(time=.5,group=1,program=2,records=b)]
        timeline=sample_timeline(events,1,seed=7,blink=False)
        player=c_face_player(a,seed=7,blink=False)
        expected=[]
        for frame in range(61):
            if frame==30:
                player.start_program(b)
            expected.append(player.tick())
        for sample,state in zip(timeline['samples'],expected):
            self.assertEqual({k:v for k,v in sample.items() if k!='time'},state)
        self.assertEqual([e['group'] for e in timeline['program_events']],[0,1])

    def test_same_tick_unordered_out_of_range_and_nonfinite_rejected(self):
        record=[event(0,end=True)]
        for times in [[.201,.202],[.4,.2],[0,2],[float('nan')],[float('inf')],[-1]]:
            with self.assertRaises(ValueError):
                sample_timeline([dict(time=t,records=record) for t in times],1)
        with self.assertRaises(ValueError):
            sample_program(record,1,face_start=-.1)

    def test_exact_tick_and_default_behavior(self):
        records=[event(0),event(.5,end=True)]
        timeline=sample_timeline([dict(time=.2,records=records)],1,blink=False)
        self.assertEqual(timeline['program_events'][0]['sampled_time'],.2)
        output=sample_program(records,1,blink=False)
        player=c_face_player(records,blink=False)
        for sample in output['samples']:
            self.assertEqual({k:v for k,v in sample.items() if k!='time'},player.tick())

    def test_resolve_schedule_bounds_hash_and_aliases(self):
        records=[event(0,end=True)]
        source=dict(source_sha256='test',groups=[dict(program_offsets=[32,32])],programs=[dict(offset=32,records=records)])
        doc=dict(format='ARIKA_FACE_EVENTS',source_sha256='test',events=[dict(time=0,group=0,program=1)])
        self.assertEqual(resolve_timeline(source,doc)[0]['records'],records)
        for key,value in [('group',1),('group',-1),('program',2),('program',True),('time',float('nan'))]:
            with self.subTest(key=key,value=value):
                bad=dict(doc,events=[dict(doc['events'][0],**{key:value})])
                with self.assertRaises(ValueError):
                    resolve_timeline(source,bad)
        with self.assertRaises(ValueError):
            resolve_timeline(source,dict(doc,source_sha256='other'))


if __name__=='__main__':
    unittest.main()
