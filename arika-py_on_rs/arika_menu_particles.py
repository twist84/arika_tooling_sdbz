"""EU-beta DRAGON SUMMONING six-slot pool, recovered from SLES_541.61.

Native ownership differs from the menu-first object:
  0x37AC10 allocates a process-global 0x430-byte pool at 0x4FDC64;
  0x37A860 advances the owning first-component's +0x320 spawn timer;
  0x190450 consumes the shared context RNG at context +0xA8.
Each c_menu_runtime holds ONE isolated model of that native global pool.
The caller supplies a context RNG and a verified/current clip boundary.
No renderer method advances this simulation or consumes random values.
"""
import struct


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def signed16(value):
    value = int(value) & 0xffff
    return value - 0x10000 if value & 0x8000 else value


# 0x38000100, loaded before every random float conversion in the ELF.
RNG_NORMALIZER = struct.unpack('<f', struct.pack('<I', 0x38000100))[0]
SPEED_DEPTH_SCALE = struct.unpack('<f', struct.pack('<I', 0x3dcccccd))[0]


def random_unit(value):
    return f32(f32(value & 0x7fff) * RNG_NORMALIZER)


class c_dragon_particle_pool:
    """Single authoritative, runtime-scoped abstraction of the global pool.

    rng is a shared c_native_rng or another object exposing next/get_state.
    Supplying an independent RNG to each particle is *not* permitted.
    """

    def __init__(self, specification, rng, clip_boundary):
        if specification['slot_count'] != 6 or specification['slot_stride'] != 176:
            raise ValueError('unexpected native particle pool layout')
        if len(specification['templates']) != 4:
            raise ValueError('expected four native particle templates')
        if len(specification['seed_positions']) != 5:
            raise ValueError('expected five native particle seed positions')
        self.m_specification = specification
        self.m_rng = rng
        self.m_clip_boundary = f32(clip_boundary)
        self.m_slots = []
        self.m_random_draws = []
        self.m_total_draws = 0
        self.m_alive = True
        # The ELF startup constructor zero-fills 0x4FC990/0x4FC994.
        # Later writes must be supplied explicitly before teardown.
        self.m_reset_position = [0.0, 0.0]
        self._initialize()

    def _ensure_live(self):
        if not self.m_alive:
            raise RuntimeError('native Dragon particle pool was destroyed')

    def close(self):
        """0x37A820 -> 0x37AF60 -> 0x37AD10, once per object lifetime.

        Native 0x37AF60 resets all six embedded sprites in ascending
        address order. 0x37AD10 destroys/frees the allocation but does
        not clear the stale 0x4FDC64 pointer; the isolated host model
        deliberately invalidates the object instead of keeping a dangling
        accessible allocation. No RNG is consumed by the destructor.
        """
        self._ensure_live()
        for slot in self.m_slots:
            self._retire(slot)
        self.m_alive = False

    def _rand(self, role):
        value = self.m_rng.next()
        self.m_random_draws.append((role, value))
        self.m_total_draws += 1
        return value

    def _empty_slot(self, index):
        return dict(index=index, active=False, template=None,
                    uv=[0, 0, 0, 0], x=0.0, y=0.0,
                    speed=0.0, depth_step=0.0)

    def _initialize(self):
        # 0x37ADB0: reset all six, then initialize slots 0..4 in order.
        self.m_slots = [self._empty_slot(i) for i in range(6)]
        for index, (x, y) in enumerate(self.m_specification['seed_positions']):
            self._activate(index)
            # 0x37AE40..0x37AE50 overwrite Y despite consuming its RNG.
            self.m_slots[index]['x'] = f32(x)
            self.m_slots[index]['y'] = f32(y)

    def _activate(self, index):
        # 0x37AFc0 / 0x37ADB0: template RNG precedes sprite init.
        value = self._rand('template')
        selection = (value >> 5) & 3
        entry = self.m_specification['templates'][selection]
        uv_x, uv_y, width, height = entry['uv_xywh']
        # Sprite vtable+0x18 sets UV edges; +0x90 receives 512.0.
        # 0x37B124 RNG #2 computes a randomized Y position.
        height_fraction = random_unit(self._rand('y'))
        y_range = f32(f32(260.0) - f32(height))
        # 0x37B188 ADDA.S then 0x37B18C MADD.S.
        y = f32(f32(y_range * height_fraction) + f32(-30.0))
        # 0x37B198 RNG #3 computes positive speed.
        speed_fraction = random_unit(self._rand('speed'))
        span = f32(entry['speed_random_span'])
        base = f32(entry['speed_base'])
        # 0x37B1E4 ADDA.S then 0x37B1E8 MADD.S.
        speed = f32(f32(span * speed_fraction) + base)
        slot = self.m_slots[index]
        slot.update(
            active=True, template=selection,
            uv=[signed16(uv_x), signed16(uv_y),
                signed16(uv_x + width), signed16(uv_y + height)],
            x=f32(512.0), y=y, speed=speed,
            depth_step=f32(SPEED_DEPTH_SCALE * speed))

    def _retire(self, slot):
        # 0x37B328..0x37B350: sprite reset, flag/speed zero, reset XY.
        # The native sprite may retain metadata while inactive.
        slot.update(active=False, speed=0.0,
                    x=self.m_reset_position[0],
                    y=self.m_reset_position[1])

    def _update_slot(self, slot):
        if not slot['active']:
            return
        # 0x37B22C..0x37B238
        slot['x'] = f32(slot['x'] - slot['speed'])
        if slot['x'] < self.m_clip_boundary:
            # 0x37B26C..0x37B324: crop UV-left and compensate X.
            # 0x37B288 converts the positive float32 clip delta with
            # CVT.W.S. The EE FPU chops fractional bits toward zero,
            # unlike Python round() (banker's rounding). 0x37B290 then
            # masks the result to the low unsigned 16 bits.
            # Precision beyond host float32 and values >= 2**31 remain
            # outside the currently validated game-coordinate range.
            delta = f32(self.m_clip_boundary - slot['x'])
            if not 0.0 <= delta < 2147483648.0:
                raise ValueError('particle clip delta outside verified range')
            amount = int(delta)
            amount = amount & 0xffff
            slot['uv'][0] = signed16(slot['uv'][0] + signed16(amount))
            slot['x'] = f32(slot['x'] + f32(amount))
        # 0x37B250..0x37B260, 0x37B328: retire when UV exhausted.
        if slot['uv'][0] >= slot['uv'][2]:
            self._retire(slot)

    def step(self, timer):
        """One 0x37A860 callback. Return first-instance +0x320 timer.

        On timer expiry, spawn and timer RNG occur BEFORE the one shared
        slot-update pass (0x37A8F4 branches back to 0x37A890).
        Exhausted pools consume only the timer RNG; a free slot consumes
        three additional RNG values before the timer value.
        """
        self._ensure_live()
        self.m_random_draws = []
        # 0x37A880 with the 0x37A88C branch-delay store.
        timer = f32(f32(timer) - f32(1.0))
        if not (timer > 0.0):
            # 0x37AFC0 scans in ascending order and takes the first
            # inactive slot; a full pool does not draw a template RNG.
            for slot in self.m_slots:
                if not slot['active']:
                    self._activate(slot['index'])
                    break
            # 0x37A8B8 happens after the spawn attempt in either case.
            timer_fraction = random_unit(self._rand('timer'))
            timer = f32(f32(f32(120.0) * timer_fraction) + f32(90.0))
        # 0x37A8F4 branches to 0x37A890 after the timer store.
        # Both branches reach exactly one 0x37AE80 pass, AFTER spawning.
        for slot in self.m_slots:
            self._update_slot(slot)
        return timer

    def snapshot(self):
        """Copy scalar fields; callers cannot mutate the live pool."""
        return dict(
            slots=tuple(dict(
                index=s['index'], active=s['active'], template=s['template'],
                uv=tuple(s['uv']), x=s['x'], y=s['y'],
                speed=s['speed'], depth_step=s['depth_step'])
                for s in self.m_slots),
            rng_state=self.m_rng.get_state(),
            random_draws=tuple(self.m_random_draws),
            total_random_draws=self.m_total_draws,
            clip_boundary=self.m_clip_boundary,
            alive=self.m_alive)

    def geometry(self, component_offset=(0.0, 0.0), depth=0.0):
        """Pure draw-command inspection for active sprites, slots 0..5.

        0x37B370 writes embedded sprite +0x10/+0x14/+0x18 before
        drawing. The preview computes those presentation values without
        persisting a competing mutable simulation or consuming RNG.
        """
        self._ensure_live()
        result = []
        for slot in self.m_slots:
            if not slot['active']:
                continue
            left, top, right, bottom = slot['uv']
            x = f32(component_offset[0] + slot['x'])
            y = f32(component_offset[1] + slot['y'])
            z = f32(f32(depth) + slot['depth_step'])
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                continue
            geometry = dict(
                position=[x, y], scale=[1.0, 1.0],
                uv_endpoints=[left, top, right, bottom],
                vertices=[[x, y], [f32(x + width), y],
                          [x, f32(y + height)],
                          [f32(x + width), f32(y + height)]],
                bounds=[x, y, f32(x + width), f32(y + height)],
                depth=z)
            result.append(dict(slot=slot['index'],
                               texture_entry=self.m_specification['texture_entry'],
                               geometry=geometry))
        return result
