import copy
import json
from pathlib import Path
import random
import unittest
from arika_menu_companions import step_state,spawn_slot
from arika_menu_owner import initialize_owner,start_owner,step_owner
from arika_menu_rng import c_native_rng
from menu_strip_oracle import bits
from test_arika_menu_tiles import c_tile_oracle
from test_arika_menu_companions import c_companion_oracle


class c_owner_oracle(c_tile_oracle):
    def __init__(self,report,state,value=12345):
        tile=report['tile_scroll_kernel'];kernel=report['shared_companions']
        super().__init__(tile,state['phase'],tile['base_position'],state['offset'],tile['uv_xywh'],85)
        self.m_kernel=kernel;self.m_pool_snapshots=[]
        for function in report['tile_companion_owner']['functions'].values():
            self.m_code.update({function['address']+i*4:w for i,w in enumerate(function['words'])})
        self.write_int(0x1000,0x4000,4)
        for offset,target in zip((8,12,16),report['tile_companion_owner']['callbacks']):self.write_int(0x4000+offset,target,4)
        self.write_int(0x1070,state['owner_phase'],4);self.write_float(0x1074,state['owner_age'])
        self.write_float(0x1084,state['timer'])
        for address,v in zip(kernel['reset_position_addresses'],state['reset_position']):self.write_float(address,v)
        for index,slot in enumerate(state['slots']):
            base=0x5000+index*112
            for name,offset in [('x',96),('y',100),('speed',104),('depth',24)]:self.write_float(base+offset,slot[name])
            self.write_int(base+108,int(slot['active']),4)
        def update_pool(machine):
            self.m_pool_snapshots.append((self.read_int(0x1070,4),self.read_float(0x1074),self.read_float(0x1084)))
            for index in range(10):
                base=0x5000+index*112;child=c_companion_oracle(kernel)
                child.write(0x1000,self.read(base,112))
                child.write_int(0x1000,0x3000,4)
                for address,v in zip(kernel['reset_position_addresses'],state['reset_position']):child.write_float(address,v)
                child.run(kernel['update_address']);self.write(base,child.read(0x1000,112))
        def initialize_pool(machine):
            for index in range(10):self.write(0x5000+index*112,bytes(112))
        self.m_direct_stubs.update({0x3765a0:update_pool,0x3766c0:{},0x190450:{2:value},
            0x375fe0:{},0x376540:initialize_pool})
        gp=kernel['global_pointer'];self.write_float(gp-19784,90);self.write_float(gp-19780,120)


class MenuOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        cls.kernel=cls.report['shared_companions'];cls.owner=cls.report['tile_companion_owner']

    def state(self):return initialize_owner(self.kernel,self.owner)

    def assert_fields(self,state,machine):
        self.assertEqual(state['owner_phase']&0xffffffff,machine.read_int(0x1070,4))
        for name,offset in [('owner_age',116),('phase',120),('timer',132)]:
            self.assertEqual(bits(state[name]),machine.read_int(0x1000+offset,4),name)
        for index,slot in enumerate(state['slots']):
            base=0x5000+index*112
            self.assertEqual(slot['active'],bool(machine.read_int(base+108,4)))
            for name,offset in [('x',96),('y',100),('speed',104),('depth',24)]:
                self.assertEqual(bits(slot[name]),machine.read_int(base+offset,4),name)

    def test_580_updates_match_native_dispatch_and_slot_updates(self):
        rng=random.Random(376080)
        cases=[(p,a,t) for p in (0,1,2,3,-1,4) for a in (0,99998,99999,199998,1000000) for t in (0,.5,1,2,100,209)]
        cases += [(rng.choice([0,1,2,3]),rng.randint(0,200000)/2,rng.choice([0,.5,1,2,100])) for _ in range(400)]
        self.assertEqual(len(cases),580)
        for owner_phase,age,timer in cases:
            state=self.state();state.update(owner_phase=owner_phase,owner_age=age,timer=timer,phase=2047)
            state['slots']=[spawn_slot(self.kernel['templates'][i%3],0,0) for i in range(10)]
            value=rng.randrange(0x80000000);machine=c_owner_oracle(self.report,state,value)
            machine.run(self.owner['functions']['update']['address'])
            draws=[]
            def draw(role):draws.append(role);return value
            event=step_owner(state,self.kernel['templates'],draw);self.assert_fields(state,machine)
            self.assertEqual(len(machine.m_pool_snapshots),int(owner_phase!=0))
            self.assertEqual(event['slots_updated'],owner_phase!=0)
            self.assertEqual(len(draws),machine.m_direct_calls.count(0x190450))
            self.assertEqual(len(draws),int(owner_phase==2 and timer<=1))
            if machine.m_pool_snapshots:
                self.assertEqual(machine.m_pool_snapshots[0],(owner_phase&0xffffffff,age+1-99999 if age+1>99999 else age+1,timer))

    def test_initialization_and_start_preserve_distinct_fields(self):
        state=self.state();state.update(owner_phase=3,owner_age=77,timer=45,phase=2047)
        state['slots'][0]=spawn_slot(self.kernel['templates'][0],0,0)
        machine=c_owner_oracle(self.report,state);machine.run(self.owner['functions']['start']['address'])
        previous=copy.deepcopy(state);start_owner(state);self.assert_fields(state,machine)
        self.assertEqual(state['slots'],previous['slots']);self.assertEqual(state['timer'],45)
        machine=c_owner_oracle(self.report,previous);machine.run(self.owner['functions']['initialize']['address'])
        expected=self.state();self.assert_fields(expected,machine)
        self.assertEqual([machine.read_float(0x107c),machine.read_float(0x1080)],expected['offset'])
        self.assertEqual(machine.m_direct_calls,[0x375fe0,0x3763b0,0x376540])

    def test_entry_delays_rng_and_active_stream_by_one_update(self):
        owner=self.state();start_owner(owner);active=self.state()
        a=c_native_rng(1);b=c_native_rng(1);draws=[]
        def draw(role):draws.append(role);return a.next()
        event=step_owner(owner,self.kernel['templates'],draw)
        self.assertEqual(event['callback'],'entry');self.assertEqual(draws,[])
        for _ in range(1800):
            step_owner(owner,self.kernel['templates'],draw)
            step_state(active,self.kernel['templates'],lambda role:b.next())
            for field in ('slots','timer','phase'):self.assertEqual(owner[field],active[field])
        self.assertEqual(a.get_state(),b.get_state())

    def test_exit_moves_and_retires_before_stopping_then_freezes(self):
        state=self.state();state.update(owner_phase=3,owner_age=13,timer=17,phase=27)
        state['slots'][0]=spawn_slot(self.kernel['templates'][0],0,0);state['slots'][0]['x']=-240
        machine=c_owner_oracle(self.report,state);machine.run(self.owner['functions']['update']['address'])
        def no_random(role):self.fail('exit/inactive consumed RNG')
        step_owner(state,self.kernel['templates'],no_random);self.assert_fields(state,machine)
        self.assertFalse(state['slots'][0]['active']);self.assertEqual(state['owner_phase'],0)
        stopped=copy.deepcopy(state);step_owner(state,self.kernel['templates'],no_random)
        self.assertEqual(state,stopped)


if __name__=='__main__':unittest.main()
