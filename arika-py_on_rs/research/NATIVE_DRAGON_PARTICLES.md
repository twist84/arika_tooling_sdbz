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
       for slot 0..5, in order: 0x0037B050 reset this slot
       if slot < 5: 0x00190450 RNG(template)
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

## Deterministic validation checkpoint

The Windows/Linux Actions suite `43651092179` passed after registering the
particle tests in the workflow (155 menu/editor tests). Subsequent work
adds a native-word sprite-initialization oracle and pending-item ownership
regressions, and must be verified again on the final head.

- `0x0037A860`: 30 native instruction comparisons (six timer values × five
  RNG outputs), checking timer float bits, scan/RNG/update call ordering and
  the branch-delay timer store. Pool calls are controlled stubs.
- `0x0037B210`: seven native instruction comparison cases covering active,
  inactive, movement, clip and retirement. Sprite UV setter/reset calls are
  controlled stubs; tests intentionally use integral clip deltas while
  FCR31 rounding remains unverified.
- `0x0037ADB0`: native loop test establishes reset interleaving, six stable
  slots, initial five activations, three RNG inputs each, template indices,
  seed position overrides and final context state. Sprite setup is stubbed,
  so this test does not validate its internal numeric arithmetic.
- `0x0037B0A0`: 12 further native instruction cases over all four templates
  and three RNG pairs compare exact float32 X/Y, speed, depth contribution,
  active flag and UV edges. Resource/GS setters are controlled stubs; the
  Python UV order [left,top,right,bottom] maps to native fields
  [left,right,top,bottom] at +0x28..+0x2E.
- Independent-runtime, deterministic replay, first-free slot reuse,
  pending exit, snapshot immutability and pure Qt paint tests exercise
  ownership rather than only arithmetic.
- The Qt first-layer has item-3 depth tiers from `0x0037A9B4`,
  `0x0037A980` and `0x0037AA24`: literal sprites at first depth,
  particles at first depth + 1 + 0.1 * speed, and decorations at first
  depth + 10. This replaces a generic depth fallback for item 3.

Native stubbed-call tests validate their exact stated scope only. In
particular they do not establish complete GS blending or live-context RNG
parity.

## Follow-up: lifetime, clip-init provenance and draw instruction audit

The exact EU-beta ELF vtable at `0x004F1D80` has item-3 first-component
constructor `0x0037A7D0` at +8 and destructor `0x0037A820` at +12.
No direct `JAL 0x37A820` exists in the file-backed image: the owning
runtime invokes its destructor via the vtable. The destructor calls
`0x37AC00`, then the six-slot `0x37AF60` reset loop, then `0x37AD10`
to invoke the pool vtable +8 destructor with a delete flag of one.
Native `0x37AD10` **does not zero** the global `0x4FDC64` pointer.
A pointer left in that location is not proof that the pool remains alive.

The Python `close()` operation now represents the native reset/destructor:
it resets exactly the six slots without RNG input and invalidates the host
object. Subsequent `step()`, `geometry()`, or a second `close()` raise
rather than dereference a destroyed pool. Editor `c_menu_runtime.reset()`
retires the previous object before building a fresh one. Selection changes
do not trigger global-pool destruction. This deliberately prevents the
native dangling-pointer hazard in a safe host implementation while preserving
the observed lifetime/order.

The only direct GP-relative write to `gp-0x1710 = 0x4FDC60` in the
file-backed EU-beta image occurs at `0x004E23CC`, a **return delay-slot**
of initialization function `0x004E23B0`. It loads `249.0f` from
`gp-0x4C78 = 0x4FA6F8`, subtracts literal `10.0f`, and stores
`239.0f`. The same initializer writes the adjacent second-sprite Y field
`gp-0x1714 = 0x4FDC5C` at `0x004E23C4` using the value `204.0f`
from `gp-0x4C70 = 0x4FA700`. The direct reader is `0x0037B23C`.
An ELF-word oracle now tests both stores, including the JR delay slot.
This exhaustive direct
GP-access scan does not exclude pointer-based aliases or external writes;
therefore it establishes the initializer, not a proof that the field is
globally immutable at runtime.

The clipping path `0x0037B26C..0x0037B324` uses `CVT.W.S` at
`0x0037B288` and applies a 16-bit mask at `0x0037B294`. The EE's
conversion truncates fractional bits, whereas Python `round()` uses
ties-to-even; the host model now uses `int(float32_delta)` for the
verified nonnegative sub-`2**31` game-coordinate range. Out-of-range
inputs are flagged instead of assuming native behavior in the large-value
split path `0x0037B298`. The test-only scalar interpreter implements this
conversion with `math.trunc`. More fractional-boundary tests cover cases
where rounding and truncation disagree. EE arithmetic last-bit differences,
signed-short overflow and pathological deltas still need hardware checks.

The native draw callback `0x0037B370` is separately interpreted: its
position/depth stores at sprite +`0x10`/+ `0x14`/+ `0x18` occur
before sprite vtable +`0x10` is called, and an inactive slot skips all
writes. The Qt geometry builder computes identical presentation values
without modifying the logical particle slots or advancing RNG. Separate
instruction tests cover the draw-write boundary; GPU backend draw is a stub.

The tests in `test_arika_menu_particle_teardown.py` and
`test_arika_menu_particle_draw.py` use extracted native words and controlled
resource/destructor callbacks. The new tests are part of Windows/Linux CI.
Check the current head's Action run before marking this checkpoint green.

## Texture-backed sprite UV setter and shared RNG scheduling

The DRAGON SUMMONING embedded sprite uses the subclass vtable at
`0x004EDCB0`, constructed by `0x002FCCB0`:

| Virtual entry | Native function | Recovered behavior |
| --- | --- | --- |
| +0x18 | `0x002FCDD0` | Convert XYWH sprite template to endpoint UVs |
| +0x1C | `0x002FCE20` | Call base `0x002FD9E0` to update four signed 16-bit UV endpoints, then recalculate texture-coordinate floats if a texture is attached |
| +0x24 | `0x002FDA00` | Clear the four short UV endpoints and reset sprite fields; the existing normalized floats remain in the inactive allocation |

A nonzero texture pointer at sprite +`0x44` supplies dimensions via its
vtable +`0x40` (width) and +`0x44` (height). The setter writes the
following eight `float32` fields, using the width and height retrieved
from the native texture object:

| Sprite offset | Derived float |
| --- | --- |
| +0x60 | left / width |
| +0x64 | top / height |
| +0x68 | right / width |
| +0x6C | top / height |
| +0x70 | left / width |
| +0x74 | bottom / height |
| +0x78 | right / width |
| +0x7C | bottom / height |

`test_arika_menu_particle_uv.py` interprets the native `0x2FCE20`
instructions with controlled resource width/height getters and checks all
eight float fields across 36 endpoint/texture-size combinations. It also
tests the null-texture early exit and executes the `0x2FDA00` reset.
The test-only scalar interpreter gained `SRL` to run the positive-texture
code path. The test substitutes resource getters, not native GS rendering.

The Python particle pool now records the four distinct normalized values
as **derived presentation metadata** in `uv_normalized`, and retains them
through retirement while clearing the short UV fields as the native reset
does. A missing texture has explicit unknown normalized metadata. The Qt
editor reads the **actual decoded TIM2 dimensions of texture entry 11** from
an opened `dis/main_menu.pix`; there is no hardcoded 512x512 assumption
or relation to the separate 512x448 menu display. Supplying dimensions
does not advance simulation or consume the RNG.

The shared context RNG call order is not only local to the six particle
slots. The recovered menu update is:

```text
0x00379A40 outer component update
  -> 0x00377DE0 shared scheduler
     -> 0x00376080 ten-slot companion owner update
        -> (owner phase 2) 0x003761B0 active callback
           -> 0x003766C0 first-free companion spawn search
              -> 0x00190450 global RNG (template/Y/speed when free)
           -> 0x00190450 global RNG (event timer on expiry)
  -> pending item and current item update
     -> 0x00373A10 first-component phase dispatcher
        -> 0x0037A860 DRAGON SUMMONING phase-2 callback
           -> 0x00190450 shared global RNG
```

The shared entry callback `0x00377FB0` issues
`0x00376390` to start the inner companion owner. The runtime now
executes those **already-recovered** `update_owner` and `start_owner`
callbacks in `step_shared`, with the ten-slot companion state
`initialize_owner/step_owner` and the six-slot Dragon pool consuming the
*same* `c_native_rng` instance. The companion update occurs before the
selected-item particle callback. A seeded unit test checks both the shared
entry/update ordering and same-frame competition for template/height/speed/
timer RNG outputs, as well as deterministic reset, snapshot purity, and
unseeded unresolved state. The isolated seed (1 in the Qt diagnostic
preview) is not the game's captured active-context seed; other systems can
also consume this context RNG and have not all been accounted for.

These changes reconstruct logical owner/RNG ordering only. They do not yet
render the companions through Qt's native mode, claim pixel-exact GS
blending, or establish actual in-game seed/state/call-count parity.

## Remaining before Phase A can be signed off

- [x] Verify pool reset/destructor ordering and document dangling global-pointer behavior; the host representation explicitly invalidates the object and the indirect owner destruction timing beyond its vtable remains runtime-dependent.
- [x] Recover subclass sprite UV setter, attached-texture normalization, and UV reset side effects; 36 interpreted sprite-setter cases and texture-size-aware Qt plumbing added.
- [ ] Verify remaining CVT.W.S overflow branches, EE hardware float-to-short behavior, and GS texture setup; host-chop fractional tests are not a full hardware oracle.
- [x] Establish the unique direct GP-relative initializer at `0x4E23CC` (`249 - 10 = 239`), and mark pointer-based runtime writers unresolved.
- Validate `ADDA.S/MADD.S` float32/ACC precision against interpreted instructions.
- [x] Couple the recovered ten-slot companion owner and six-slot Dragon pool to the same isolated context RNG, respecting shared-before-item callback order.
- [ ] Capture actual live-context RNG seed and other consumers; injected seed replay is not equivalent to a running game.
- Confirm draw ordering relative to the item's other first-layer sprite draws and resource depth/blending.

No sample-23/sample-120 or FPS assumptions have been introduced. Ownership, input branches, and exact callback counts above are sufficient to build a **seed-injected isolated logical simulation** while leaving unresolved graphics and live-context synchronization explicit.
