"""Standalone float32 port of the European beta's facial ANI/blink controller."""
import math
import struct
from arika_faces import EXPRESSION_STATES, BEHAVIOR_AMPLITUDES, PAIRS
from arika_models import require


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def add(a,b):
    return f32(a+b)


def mul(a,b):
    return f32(a*b)


class c_face_player:
    def __init__(self, records=None, seed=1, blink=True, super_form=False):
        self.m_records = records or []
        self.m_seed = seed & 0xFFFFFFFFFFFFFFFF
        self.m_blink = blink
        self.m_super = int(super_form)
        self.m_flags = 0
        self.m_index = 0 if records else -1
        self.m_script_time = -1.0
        self.m_rise = self.m_fall = 0.0
        self.m_hold = -1.0
        self.m_blink_delay = mul(10, mul(f32(1/32767), f32(self.random() & 32767)))
        self.m_elapsed = self.m_progress = self.m_previous = 0.0
        self.m_pair = self.m_random_amplitude = 0
        self.m_pose = (0, 0.0, self.m_super)
        if records:
            self.start_program(records)

    def start_program(self, records):
        # 0x1E60A0 changes program/index/clock/flags, preserving RNG and phase state.
        require(bool(records) and records[-1]['flags'] & 0x1000, 'program needs an END record')
        self.m_records = records
        self.m_index = 0
        self.m_script_time = -1.0
        self.m_flags = (self.m_flags | 0x20) & 0xFFFFF020

    def random(self):
        # Original rand() at EE 0x190450: high 31 bits of a 64-bit LCG.
        self.m_seed = (self.m_seed * 0x5851F42D4C957F2D + 1) & 0xFFFFFFFFFFFFFFFF
        return (self.m_seed >> 32) & 0x7FFFFFFF

    def set_pose(self, pair, blend):
        self.m_pose = (pair, f32(blend), self.m_super)

    def return_to_neutral(self, fall):
        epsilon = f32(1e-5)
        self.m_rise, self.m_hold = epsilon, -1.0
        self.m_fall = max(epsilon, f32(fall))
        self.m_flags = ((self.m_flags | 1) & ~0x8FE | 0x400) & ~0x300

    def phase(self, mask, pair, amplitude, delta):
        if not self.m_flags & mask:
            return
        self.m_elapsed = add(self.m_elapsed, delta)
        if self.m_flags & 0x100:
            self.m_pair = pair
            self.m_elapsed = min(self.m_elapsed, self.m_rise)
            self.m_progress = f32(self.m_elapsed / self.m_rise)
            self.set_pose(pair, add(self.m_previous, mul(self.m_progress, f32(amplitude-self.m_previous))))
            if self.m_elapsed == self.m_rise:
                self.m_elapsed = 0.0
                self.m_flags = (self.m_flags | 0x200) & ~0x500
        elif self.m_flags & 0x200:
            if self.m_hold < 0:
                return
            self.m_elapsed = min(self.m_elapsed, self.m_hold)
            if self.m_elapsed == self.m_hold:
                self.m_elapsed = 0.0
                self.m_flags = (self.m_flags | 0x400) & ~0x300
        elif self.m_flags & 0x400:
            self.m_pair = pair
            self.m_elapsed = min(self.m_elapsed, self.m_fall)
            self.m_progress = f32(1-f32(self.m_elapsed/self.m_fall))
            blend = mul(self.m_progress, amplitude)
            self.set_pose(pair, blend)
            if self.m_elapsed == self.m_fall:
                self.m_elapsed = 0.0
                if self.m_flags & 0x800:
                    self.m_random_amplitude = (self.random() >> 5) % 5
                    self.m_previous = blend
                    self.m_flags = (self.m_flags | 0x100) & ~0x600
                elif self.m_flags & 1:
                    self.m_pair = 0
                    self.set_pose(0,0)
                    self.m_flags &= ~0x701
                elif self.m_flags & 0x61:
                    self.m_flags &= ~(mask | 0x700)
                else:
                    self.return_to_neutral(f32(.1))

    def tick(self, delta=1/60):
        require(math.isfinite(delta) and delta > 0, 'tick delta must be positive')
        global_delta = f32(delta)
        phase_delta = mul(f32(1/60), f32(delta*60))
        if not self.m_flags & 0x3F and not self.m_super:
            if self.m_flags & 0x80:
                if not self.m_flags & 0x40 and self.m_progress == 0:
                    self.m_flags = ((self.m_flags & ~0x80) | 0x40 | 0x100) & ~0x600
                    self.m_rise,self.m_hold,self.m_fall = f32(.3),0.0,f32(.2)
            elif self.m_blink:
                self.m_blink_delay = f32(self.m_blink_delay-phase_delta)
                if self.m_blink_delay < 0:
                    self.m_flags |= 0x80
                    self.m_blink_delay = mul(10,mul(f32(1/32767),f32(self.random() & 32767)))
            self.phase(0x40,0,1.0,phase_delta)
        if self.m_flags & 0x20:
            self.m_script_time = 0.0 if self.m_script_time < 0 else add(self.m_script_time,global_delta)
            limit = 0
            while self.m_index < len(self.m_records) and self.m_script_time >= f32(self.m_records[self.m_index]['time']):
                record = self.m_records[self.m_index]
                limit += 1
                require(limit <= len(self.m_records), 'invalid facial program loop')
                if record['flags'] & 0x1000:
                    self.return_to_neutral(0)
                    self.m_progress = 0.0
                    break
                require(record['flags'] == 0, 'unsupported ANI branch flags')
                self.m_index += 1
                self.m_rise,self.m_fall = f32(.1),f32(.1)
                if record['behavior'] == 6:
                    self.m_hold = f32(.2)
                    self.m_random_amplitude = (self.random() >> 5) % 5
                    self.m_flags = (self.m_flags | 0x900) & ~0x600
                else:
                    require(self.m_index < len(self.m_records), 'missing next facial event')
                    next_time = f32(self.m_records[self.m_index]['time'])
                    self.m_hold = f32(f32(next_time-f32(record['time']))-f32(.2))
                    self.m_flags = (self.m_flags | 0x100) & ~0xE00
                self.m_previous = self.m_progress
            if self.m_flags & 0x20 and self.m_index > 0:
                record = self.m_records[self.m_index-1]
                behavior = self.m_random_amplitude if self.m_flags & 0x800 else record['behavior']
                require(0<=behavior<len(BEHAVIOR_AMPLITUDES) and 0<=record['expression']<len(EXPRESSION_STATES), 'invalid facial selector')
                self.phase(0x20,EXPRESSION_STATES[record['expression']],f32(BEHAVIOR_AMPLITUDES[behavior]),global_delta)
                self.m_flags |= 0x20
            elif self.m_flags & 0x20:
                # Before the first due event, the native helper still advances its timer.
                self.phase(0x20,0,0.0,global_delta)
                self.m_flags |= 0x20
        # Low-bit return/direct modes follow the script in the original tick.
        for mask,pair in ((1,self.m_pair),(2,3),(4,2),(16,5)):
            if self.m_flags & mask:
                self.phase(mask,pair,1.0,phase_delta)
        return self.snapshot()

    def snapshot(self):
        pair,blend,super_form = self.m_pose
        require(0<=pair<len(PAIRS), 'invalid controller pair')
        return dict(pair_index=pair,pair='SAD' if super_form else PAIRS[pair],blend=blend,
            super_form=bool(super_form),texture_endpoint=int(blend+.5),
            flags=self.m_flags,event_index=self.m_index,script_time=self.m_script_time,
            phase_time=self.m_elapsed,phase_progress=self.m_progress,rng_state=self.m_seed)

    def state(self):
        return [self.m_flags,self.m_index,self.m_script_time,self.m_rise,self.m_hold,self.m_fall,
            self.m_blink_delay,self.m_elapsed,self.m_progress,self.m_previous,
            self.m_pair,self.m_random_amplitude,self.m_seed]


def sample_timeline(events, duration, rate=60, seed=1, blink=True, super_form=False):
    require(math.isfinite(duration) and 0<duration<=600, 'duration must be in (0,600] seconds')
    require(rate in (25,30,50,60,100,120), 'supported sample rates: 25,30,50,60,100,120')
    require(isinstance(seed,int) and 0<=seed<=0xFFFFFFFFFFFFFFFF, 'seed must fit uint64')
    player=c_face_player(None,seed,blink,super_form)
    scheduled=[]
    for event in events:
        time=event['time']
        require(math.isfinite(time) and 0<=time<=duration, 'event time must be within the export duration')
        require(event['records'] and event['records'][-1]['flags'] & 0x1000, 'program needs an END record')
        # Match the comparison used by the sampling loop; no epsilon moves an event early.
        frame=math.ceil(time*rate)
        while frame/rate<time:
            frame+=1
        while frame>0 and (frame-1)/rate>=time:
            frame-=1
        require(not scheduled or frame>scheduled[-1][0], 'events must be ordered and occupy distinct sample ticks')
        scheduled.append((frame,event))
    samples=[]
    starts=[]
    cursor=0
    count=math.ceil(duration*rate)
    while count/rate<duration:
        count+=1
    for frame in range(count+1):
        if cursor<len(scheduled) and frame==scheduled[cursor][0]:
            event=scheduled[cursor][1]
            player.start_program(event['records'])
            starts.append(dict(time=event['time'],sampled_time=frame/rate,
                group=event.get('group'),program=event.get('program')))
            cursor+=1
        state=player.tick(1/rate)
        state['time']=frame/rate
        samples.append(state)
    return dict(format='ARIKA_FACE_PLAYBACK',duration=count/rate,sample_rate=rate,seed=seed,
        idle_blink=blink,super_form=super_form,program_events=starts,
        face_start_requested=starts[0]['time'] if starts else None,
        face_start_sampled=starts[0]['sampled_time'] if starts else None,samples=samples)


def sample_program(records, duration, rate=60, seed=1, blink=True, super_form=False, face_start=0):
    require(math.isfinite(face_start) and 0<=face_start<=duration, 'face start must be within the export duration')
    events=[dict(time=face_start,records=records)] if records else []
    result=sample_timeline(events,duration,rate,seed,blink,super_form)
    result.update(face_start_requested=face_start,
        face_start_sampled=result['program_events'][0]['sampled_time'] if events else None)
    return result
