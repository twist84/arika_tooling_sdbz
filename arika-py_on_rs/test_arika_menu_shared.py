import copy
import json
from pathlib import Path
import random
import unittest
from arika_menu_shared import initialize_shared,request_exit,step_shared
from menu_strip_oracle import c_strip_oracle,bits


class c_shared_oracle(c_strip_oracle):
    def __init__(self,kernel,state,small_update=None):
        super().__init__(dict(draw_address=0,draw_words=[],clock_address=0,clock_words=[]),[0,0,1,1],0,0,1,1,0,[0,0])
        self.m_events=[];self.m_state=state;self.m_kernel=kernel
        self.m_registers[28]=0x4ff370;self.write_int(0x1000,0x4000,4)
        for i,address in enumerate(kernel['callbacks']):self.write_int(0x4008+i*4,address,4)
        for function in kernel['functions'].values():
            self.m_code.update({function['address']+i*4:w for i,w in enumerate(function['words'])})
        for name,offset in kernel['fields'].items():
            if name in state:
                if name in ('age','overlay_alpha'):self.write_float(0x1000+offset,state[name])
                else:self.write_int(0x1000+offset,int(state[name]),1 if name=='overlay_hidden' else 4)
        for i,phase in enumerate(state['small_phases']):
            self.write_int(0x10e4+i*4,0x5000+i*128,4);self.write_int(0x5004+i*128,phase,4)
            self.write_float(0x4a9f80+i*4,kernel['small_start_times'][i])
        self.write_float(0x4fa670,kernel['entry_wait']);self.write_float(0x4fa674,kernel['overlay_target'])
        def action(role,index=None):
            def callback(machine):
                current=index
                if role in ('update_small','start_small'):current=(machine.m_registers[4]-0x5000)//128
                self.m_events.append(dict(role=role,index=current))
                if role=='start_small':self.write_int(0x5004+current*128,1,4)
                if role=='update_small' and small_update is not None:self.write_int(0x5004+current*128,small_update[current],4)
            return callback
        self.m_direct_stubs={
            0x378480:action('update_banner'),0x376080:action('update_owner'),0x376ac0:action('update_small'),
            0x3786f0:action('start_banner'),0x376390:action('start_owner'),0x376c70:action('start_small'),
            0x378700:action('exit_banner'),
            0x376cd0:lambda m:m.m_registers.__setitem__(2,int(m.read_int(m.m_registers[4]+4,4)!=0))}


class MenuSharedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kernel=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())['shared_scheduler']

    def compare(self,state,small_update=None):
        before=copy.deepcopy(state);machine=c_shared_oracle(self.kernel,before,small_update)
        machine.run(self.kernel['functions']['update']['address'])
        def child(role,index):
            if role=='update_small' and small_update is not None:state['small_phases'][index]=small_update[index]
        calls=step_shared(state,self.kernel,child)
        self.assertEqual(calls,machine.m_events)
        for name in ('phase','subphase','age','started_count','overlay_hidden','overlay_alpha'):
            offset=self.kernel['fields'][name]
            if name in ('age','overlay_alpha'):self.assertEqual(bits(state[name]),machine.read_int(0x1000+offset,4),name)
            else:self.assertEqual(int(state[name])&0xffffffff,machine.read_int(0x1000+offset,1 if name=='overlay_hidden' else 4),name)
        self.assertEqual(state['small_phases'],[machine.read_int(0x5004+i*128,4) for i in range(7)])
        return calls

    def test_600_controlled_updates_match_native(self):
        rng=random.Random(0x377de0)
        for _ in range(600):
            state=initialize_shared();state.update(phase=rng.choice([0,1,2,3,4]),subphase=rng.choice([0,1,2,3]),
                age=rng.choice([0,8,9,10,13,14,15,19,24,29,34,39,99998,99999,199998]),
                started_count=rng.randrange(8),overlay_hidden=bool(rng.randrange(2)),
                overlay_alpha=rng.choice([-.1,0,.05,.45,.49,.5,.6]))
            state['small_phases']=[rng.randrange(5) for _ in range(7)]
            self.compare(state,[rng.randrange(5) for _ in range(7)])

    def test_entry_stagger_wait_and_fade_match_native(self):
        state=initialize_shared();state['phase']=1;starts=[]
        for tick in range(70):
            for call in self.compare(state):
                if call['role']=='start_small':starts.append((tick,call['index']))
            if tick==0:self.assertEqual(state['subphase'],1)
            if tick==39:self.assertEqual((state['subphase'],state['age']),(2,0))
            if tick==54:
                self.assertEqual((state['phase'],state['age']),(2,0));self.assertFalse(state['overlay_hidden']);self.assertEqual(state['overlay_alpha'],0)
            if tick==55:self.assertEqual(bits(state['overlay_alpha']),bits(.05))
        self.assertEqual(starts,[(9,0),(14,6),(19,3),(24,4),(29,1),(34,5),(39,2)])
        self.assertEqual(state['overlay_alpha'],.5)

    def test_busy_children_and_update_order(self):
        state=initialize_shared();state.update(phase=1,subphase=1,age=39)
        state['small_phases']=[2]*7
        self.assertEqual(len(self.compare(state)),9);self.assertEqual(state['started_count'],0)
        calls=self.compare(state,[0]*7)
        self.assertEqual([v['role'] for v in calls[:9]],['update_banner','update_owner']+['update_small']*7)
        self.assertEqual(state['started_count'],7);self.assertEqual(state['age'],0)

    def test_exit_wait_and_inactive_gate(self):
        state=initialize_shared();state.update(phase=2,subphase=9,age=300,overlay_hidden=False)
        machine=c_shared_oracle(self.kernel,state);machine.run(self.kernel['functions']['request_exit']['address'])
        request_exit(state)
        for name in ('phase','subphase','age'):
            value=machine.read_int(0x1000+self.kernel['fields'][name],4)
            self.assertEqual(bits(state[name]) if name=='age' else state[name],value)
        for tick in range(10):
            calls=self.compare(state)
            self.assertEqual(any(c['role']=='exit_banner' for c in calls),tick==0)
        self.assertEqual(state['phase'],0)
        frozen=copy.deepcopy(state);self.assertEqual(self.compare(state),[]);self.assertEqual(state,frozen)


if __name__=='__main__':unittest.main()
