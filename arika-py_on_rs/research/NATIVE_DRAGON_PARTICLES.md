# EU-beta DRAGON SUMMONING particle lifecycle (instruction checkpoint)

Target: `SLES_541.61`, SHA-256 `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`. Addresses are EE virtual addresses. Checked against the actual ELF instructions, not inferred from the diagnostic timeline.

## Ownership: three distinct native objects

1. **First-component instance** (item 3, vtable `0x004F1D80`): field `this+0x320` is a float32 spawn timer, zeroed at `0x0037A7E0`. Phase-2 callback `0x0037A860` decrements it. The item is not the owner of the six particle slots.
2. **Shared/global particle allocation**: `0x0037AC10` allocates `0x430` bytes, calls the six-element constructor `0x00171A10` with stride `0xB0`, and stores the allocation pointer at `gp-0x170C = 0x004FDC64` (`0x0037AC30`). Six slots cover `0x000..0x41F`, and a pool vtable pointer is at `+0x420`. `0x0037AC00` returns this global pointer. This is a **single native global pool**, not seven independent item-local pools. A Python runtime may model a per-runtime *abstraction* of this global; it must not maintain duplicate authoritative copies.
3. **RNG state**: `0x00190450` reads active context pointer `0x00462C50`, then the 64-bit state at context `+0xA8`. The RNG recurrence is recovered in [NATIVE_MENU_RNG.md](NATIVE_MENU_RNG.md). Particle slots contain no RNG state. Other game systems can consume the same stream. The initial context seed is not established by this ELF-only analysis; an explicit seed for isolated tests is a test input, not a claim about the game's seed.

The allocation and timer lifetimes are *not identical*: constructor/setup `0x0037A7D0` sets timer 0, calls `0x0037AA90` for component resources, then `0x0037AC10` allocation and `0x0037ADB0` initialization. Destructor `0x0037A820` resets the six slots via `0x0037AF60`, then invokes `0x0037AD10` pool destruction through vtable +8. `0x0037AD10` itself does not zero the global pointer; code should not treat that stale pointer as a live allocation. Merely changing menu selection does not call these constructor/destructor routines.

## Call graph and ordering

```text
0x0037A7D0 constructor/setup
  -> 0x0037AA90 component setup
  -> 0x0037AC10 allocate pool (0x430; stride 0xB0; six slots)
  -> 0x0037AC00 fetch pool
  -> 0x0037ADB0 initialize six slots
       for slot 0..5: 0x0037B050 reset slot
       for slot 0..4 only: 0x00190450 RNG(template)
          -> 0x0037B0A0 sprite initialize
               -> 0x00190450 RNG(position Y)
               -> 0x00190450 RNG(speed)
          -> overwrite +0x90,+0x94 from five fixed seed positions

0x00373A10 first-component update, only phase 2
  -> vtable +0x24 = 0x0037A860
       subtract 1.0f from instance +0x320
       if new timer > 0:
          0x0037AC00 -> 0x0037AE80 update all six slots
       else:
          0x0037AC00 -> 0x0037AFC0 scan first inactive slot
             if free: 0x00190450 RNG(template)
                      -> 0x0037B0A0 (RNG Y, then RNG speed)
             0x00190450 RNG(timer) ALWAYS after scan
             +0x320 = 90.0f + 120.0f * normalized(timer_rng)
             branch 0x0037A8F4 -> 0x0037A890
          0x0037AC00 -> 0x0037AE80 update all six slots

0x0037A910 item first-layer draw
  -> 0x0037AC00 -> 0x0037AEE0 loop all six
       -> 0x0037B370 per active slot: write embedded sprite position
          and call sprite vtable +0x10 draw

0x0037A820 destructor
  -> 0x0037AC00 -> 0x0037AF60 reset all six
  -> 0x0037AD10 destroy pool
```

`0x0037A860` branch `0x0037A888` chooses the expired branch. Its `0x0037A88C` delay slot *always* stores the decremented timer. The non-expired path is `0x0037A890..0x0037A8A4`; the expired path begins `0x0037A8A8` and loops to `0x0037A890` **after** resetting `+0x320` in the `0x0037A8F8` branch delay slot. Thus even an expired callback updates every slot **once**, not twice. The common update is **after** the spawn attempt; a new slot moves on the same callback, while a slot retired during movement cannot be respawned until a later expired callback. The initial implementation mistakenly swapped this order, corrected in `7c487533`.

`0x0037AEE0` walks slots 0..5 in ascending order with +0xB0 stride. It is called by the item draw callback; Qt repaint must not run the particle logical updater or consume RNG.

## Fields: relative to each 176-byte slot

| Offset | Type | Instruction evidence | Meaning |
|---|---|---|---|
| +0x00 | ptr | `0x0037B050`, `0x0037B370` | Embedded sprite vtable |
| +0x10/+0x14/+0x18 | f32 | `0x0037B3A4..0x0037B3AC` | **Draw-mutated** embedded sprite X/Y/Z |
| +0x28/+0x2A | s16 | `0x0037B250..0x0037B260` | Current UV left/right limits; draw setup initializes from template |
| +0x2C/+0x2E | s16 | `0x0037B2C0..0x0037B2CC` | Current UV top/bottom limits |
| +0x90 | f32 | `0x0037B124`, `0x0037B234..0x0037B238` | Local X; spawn 512.0, update subtracts speed |
| +0x94 | f32 | `0x0037B190`, `0x0037AE50` | Local Y, randomized on reuse; fixed seeds for first five |
| +0x98 | f32 | `0x0037B198`, `0x0037B1F0` | Positive horizontal speed |
| +0x9C | f32 | `0x0037B1F4`, `0x0037B384` | Depth contribution, 0.1 * speed |
| +0xA0 | u32 | `0x0037B050`, `0x0037B1C4`, `0x0037B220` | Inactive zero / active one |

`0x0037B050` resets the embedded sprite via vtable +0x24, then stores active=0, speed=0, and reset X/Y at `gp-0x29E0` and `gp-0x29DC`. Initial spawn seeds are five f32 XY pairs at `0x004AA0A0`: (260,8), (280,165), (380,60), (380,130), (400,20). Sixth slot remains inactive after initial construction. `0x0037ADB0` consumes **three RNG outputs per seeded active slot**: one template selection and two in sprite setup, for 15 total, even though seeded XY overwrite the randomized position Y.

## RNG transforms and timer

The template selector at `0x0037AE1C` / `0x0037AFF0` uses `(rng >> 5) & 3`, indexing `0x004AA060` (four 16-byte entries). The RNG returns a nonnegative 31-bit value, so the signed-remainder correction branch cannot apply. Template entries contain `s16 UV[4]`, speed base and speed span. The two sprite-init draws occur at `0x0037B124` (Y) and `0x0037B198` (speed). Each uses `float32((rng & 0x7fff) * float32(1/32767))`, with normalizer bits `0x38000100`.

- Spawn X: **512.0f** from `0x004CC910` (`0x0037B120`).
- Spawn Y: **-30.0f + (260.0f - texture_height) * random_unit** from `0x0037B178..0x0037B190` using constants at `gp-0x4C64` and `gp-0x4C60`.
- Speed: **template.speed_base + template.speed_random_span * random_unit**, `0x0037B1AC..0x0037B1F0`.
- Depth contribution: `float32(0.1f * speed)`, `0x0037B1EC..0x0037B1F4`.
- Expired timer: **90.0f + 120.0f * random_unit**, constants at `gp-0x4C6C` / `gp-0x4C68`, store `0x0037A8F8`.

The PS2 FPU `ADDA.S` / `MADD.S` instructions must be modeled using explicit float32 operation boundaries; host FMA/ACC differences remain a precision limitation until differential testing.

## Movement, expiration, draw mutations

`0x0037AE80` invokes `0x0037B210` for every slot, in index order; an inactive slot is skipped. Active X is decremented by speed before the clip check. At `0x0037B244`, X below global clip boundary at `gp-0x1710 = 0x004FDC60` triggers left UV clipping. The amount is converted to a signed-halfword-compatible value and added to UV-left; the sprite UV setter is called at `0x0037B2E4`, the clipped amount is added back into X, and the code rechecks whether left < right. If left >= right it invokes the embedded sprite reset, marks the slot inactive, zeros speed and restores reset XY (`0x0037B328..0x0037B350`). The present research verifies the control flow; exact EE float-to-s16 saturation/rounding and sprite setter side effects need differential cases before claiming parity on all clip boundaries.

**Draw is not fully read-only in the ELF**: `0x0037B370` tests active, then writes sprite +0x10 = parentX+localX, +0x14 = parentY+localY, and +0x18 = passed depth+localDepth before invoking sprite vtable +0x10. These draw-time writes are embedded sprite presentation fields, **not** logical lifetime or RNG updates. The native draw loop does not call `0x00190450`.

## Remaining before Phase A can be signed off

- Verify full pool destruction and pointer invalidation context (the destructor wrapper itself leaves `0x004FDC64` intact).
- Recover the sprite UV setter side effects and float-to-s16 conversion at clipping boundaries, then run instruction-level boundary oracle.
- Confirm global clip-boundary runtime writes beyond the startup 239.0 value.
- Validate `ADDA.S/MADD.S` float32/ACC precision against interpreted instructions.
- Confirm real runtime seed/context sharing with other systems; explicit seeded replay is not the same as a captured game.
- Confirm draw ordering relative to the item's other first-layer sprite draws and resource depth/blending.

No sample-23/sample-120 or FPS assumptions have been introduced. Ownership, input branches, and exact callback counts above are sufficient to build a **seed-injected isolated logical simulation** while leaving unresolved graphics and live-context synchronization explicit.
