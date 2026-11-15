# Native Main-Menu Lifecycle Recovery Plan

Project: [twist84/arika_tooling_sdbz](https://github.com/twist84/arika_tooling_sdbz)  
Working branch: `feature/main-menu-native-navigation` / PR #14  
Primary target: **Super Dragon Ball Z EU beta, SLES_541.61**  
Goal: replace the Qt menu editor's authored 140-frame diagnostic schedule with a native-style, stateful main-menu update loop, preserving existing diagnostic tools.

## Current baseline

The editor already renders original `dis/main_menu.pix` textures from the user's `INFO.DAT` / `GAME.DAT`, FFON `font/5-24-2.fon` help text, a 512×448 native coordinate layout, and a 4:3 presentation (now the default). Seven-item navigation and history-dependent neighbours are recovered. The arrow displacement helper at `0x003753A0` is recovered as a 40-tick piecewise-linear curve with key times `(0,10,30,40)` and values `(0,+3,-3,0)`. The arrow's `+0xB0` float age is initialized to zero and advances one per active update. **The editor currently passes the global preview clock, not the actual component age.**

The baked layout has 140 samples with an **authored** example schedule: whole-character entry complete at 22, idle begins at 23, exit requested at 120, and geometry removed at 130. Selection emphasis is also activated by an **editor-authored** event clock. These diagnostic sample indices must not be mistaken for native scheduler timing.

The screenshot baseline is **4:3**. Do not introduce fresh global scaling or hand-aligned text/frame offsets while recovering the state machine.

## Evidence inventory and first targets

| Address (EU beta EE VA) | Known role / question |
|---|---|
| `0x00379B50` | Main-menu update/state logic — primary entry point |
| `0x00379C80` | Input processing and gating |
| `0x00379F00` | Selected-item switch, prior/current history, entry callbacks |
| `0x00375270` | Item directional neighbour vtable dispatch |
| `0x00336430–0x00336480` | Input-helper family used by menu |
| `0x0037F100` | Character component phase dispatcher |
| `0x0037F280 / 0x0037F330 / 0x0037F460` | Character emphasis request/start/update |
| `0x0037E160 / 0x0037E2B0` | Label emphasis request/start |
| `0x00374F38 / 0x00374FC8–0x00374FF0` | Arrow clock reset and update |
| `0x003753A0` | Native arrow displacement interpolation |
| `0x00376290 / 0x003761B0` | Background tile draw / phase update |
| `0x003763B0 / 0x00376600` | Companion-effect calls, not fully integrated |
| `0x003FE020` | Post-menu selection route |

Use `arika-py_on_rs/research/main_menu_map.json`, `NATIVE_MENU_INTERACTION.md`, `NATIVE_ITEM_CHARACTERS.md`, `NATIVE_CHARACTER_IDLE.md`, `NATIVE_CUSTOMIZE_IDLE.md`, `NATIVE_ITEM_EMPHASIS.md`, `NATIVE_MENU_TILES.md`, and `NATIVE_VIDEO_DISPLAY.md` as existing evidence. Validate addresses against the exact EU-beta ELF before interpreting instructions. Do not assume they are identical in the final EU/US executable.

## Phase 0 — Baseline and reproducibility

1. Fetch latest PR #14 branch, open remaining CI results, and verify the working tree.
2. Run the existing Python/Qt (offscreen) and ELF differential/oracle tests.
3. Keep `previews/menu_frames_*.json`, the existing frame slider, Match Pose, and manual layer toggles intact as diagnostic fixtures.
4. Add a native-lifecycle research file with **instruction evidence**, addresses, object offset tables, and a known/unknown column.
5. No copyrighted ELF/PIX/FFON data or reference screenshots should be committed.

**Exit:** existing tests green (or known failures documented), no uncontrolled visual regressions.

## Phase 1 — Recover the outer menu state machine

Disassemble `0x00379B50` and trace every call and branch, including `0x00379C80`, the selection update path, and init/shutdown callbacks.

Recover:
- state names and numerical state values; identify exactly which offsets `+0xC8` through `+0xD5` represent;
- callback order within each game update (poll input, transition, component updates, exit checks, render);
- counter increments, wrap/reset points and branch conditions;
- transition completion and interruption conditions;
- selection-change calls, pending next-item and previous-item persistence;
- confirm/cancel routes and app-lifecycle boundaries.

Document a transition table with `(state, input/event, predicate, side effect, next state)`, referencing exact branch addresses. Where logic is unclear, mark it unresolved rather than filling gaps with UI assumptions.

**Exit:** deterministic, address-annotated transition table validated with representative instruction traces.

## Phase 2 — Recover input timing and gating

Trace `0x00336430–0x00336480` and all helpers called by `0x00379C80`.

Determine:
- logical arrow and confirm/cancel button identities and priority;
- pressed vs held edges, repeat delay/rate, and simultaneous directions;
- state-dependent input blocking;
- queued, dropped, or interrupted selections;
- behaviour when a neighbour is `-1`.

Use synthetic per-frame button masks and native instruction/oracle comparisons. Don't introduce keyboard/mouse support beyond the editor's existing diagnostic shortcuts.

**Exit:** input tests reproduce native neighbour traversal and gating across transitions, not merely the graph.

## Phase 3 — Stateful component lifecycle and clocks

Implement independent component states in a **new** small module such as `arika-py_on_rs/arika_menu_runtime.py`, rather than rewriting the geometry exporters.

Cover at least:
- per-object arrow `+0xB0` age initialization, increments and its `99999` wrap;
- character and label phase transitions (entry, idle, emphasis, exit), component offsets and direction;
- lifetime and reactivation of character per-part idle arrays;
- entry and exit activation times, relative ordering and completion;
- selection-change and cancellation effects on active components;
- sceneries/tiles clocks, if updated by the outer menu scheduler.

Keep game state separate from render state. Prefer `step(input_mask)` / `snapshot()` interfaces, with one native logical update per call. No wall-clock timers inside the simulation. The Qt timer only decides how many logical updates to execute.

**Exit:** replaying a button-mask trace deterministically yields the same component states and positions.

## Phase 4 — Validate against interpreted native code

Extend existing ELF instruction comparison tools. Run targeted traces with synthetic initial state and button streams, capturing:
- outer state fields and per-component phase/age;
- previous/current selection;
- arrow displacement at clock/period boundaries;
- label/character entry, idle, shake, and exit offsets;
- completion and input-lockout updates.

Compare values after **each** update, not only final screenshots. Preserve float32 boundaries and acknowledge where host libm / FPU differ from the EE. Add tests for repeated selection, interruption, confirm/cancel, same-frame input conflicts, and wrap.

**Exit:** all implemented state transitions have native-oracle coverage; unknown paths remain explicit.

## Phase 5 — Integrate native mode into the Qt editor

Add **Native runtime / Diagnostic timeline** modes. Leave the existing `140`-sample slider functional in diagnostic mode.

- Default to native runtime **only once validated**.
- Move `navigate()` and confirm/cancel from immediate state changes to queued **logical input events** in native mode; avoid inventing a transition.
- Render from `snapshot()` and existing texture/geometry pipeline.
- Give every arrow its own actual age rather than `m_time`.
- Preserve 4:3 presentation, original atlas-4 help texture and FFON glyphs, Smooth default enabled, seven-item graph, and all layer/debug toggles.
- Surface on-screen diagnostic data: outer menu state, current/previous selection, pending selection, active component phases, input lockout, individual ages.
- Match Pose continues as a **reference comparator**, not a source of native timing.

**Exit:** user can replay a menu sequence in the editor without authored entry/idle/exit time anchors.

## Phase 6 — Complete dependent visual recovery

Only after lifecycle timing is stable:
1. Recover remaining per-part idle callbacks for VERSUS, DRAGON SUMMONING and OPTIONS.
2. Determine CUSTOMIZE's secondary age at `+488` during object construction and re-entry.
3. Integrate background companions and RNG/event timing.
4. Recover native help-panel draw geometry/UV and FFON spacing/line advances.
5. Capture live GS display registers to establish final video output and blending details.

These are separate milestones, not blockers for shipping a tested lifecycle emulator.

### Phase 6 implementation status (15 November 2026)

The numbered targets above are **historical**: several have been
completed in subsequent PR #14 checkpoints. The current status is:

- [x] All seven per-part idle callbacks are implemented (including
  VERSUS, DRAGON SUMMONING and OPTIONS) and their native-word suites
  are now included in both platforms' CI. OPTIONS and DRAGON SUMMONING
  callback arithmetic is instruction-tested with injected trig outputs;
  **bit-exact native libm** is still outstanding.
- [x] CUSTOMIZE's +488 secondary age **re-entry reset** is confirmed by
  executing the `0x37F7E0` callback and its return delay slot.
  The constructor's pre-entry value remains unknown and is not used
  to infer active-phase behavior.
- [x] Ten-slot shared companions and six DRAGON SUMMONING particles
  consume one explicitly seeded diagnostic RNG, respecting recovered
  shared-before-item update ordering. Real runtime seed/other
  consumers still require capture.
- [x] Screen-reference normalization for the existing help frame and
  FFON line positions is now tested using separate axes for the
  512×448 logical raster displayed at 4:3. The previous apparent
  40-unit Y offset was mostly a pixel-aspect comparison error.
- [x] Trace the **actual native help-panel/text owner**, its 27/5-update
  entry/exit phases, sprite bounds, native X/Y and text-row placement.
  `NATIVE_MENU_HELP_DRAW.md` documents the verified `0x37BF60` and
  `0x37C1C0` paths; native Qt preview uses these with diagnostic
  screenshot-calibrated mode still available.
- [x] Recover resident FFON vtable `0x4E3390`, 24-unit font
  dimensions, and the exact `0x19A030` ASCII half-cell advance.
  Native Qt mode now uses 12-unit fixed advances (scaled to 9)
  while diagnostic mode retains its earlier proportional glyph preview.
  Synthetic glyph and ELF-word tests cover these values.
- [ ] Trace native glyph UV/bitmap command lowering beyond
  `0x199EE0 → 0x112780`; capture runtime GS output. The
  font-run advance is established, but exact per-pixel glyph sampling,
  alpha/depth and EU-beta asset identity are still unresolved.
- [x] Reconstruct file-backed PS2 GS TEST/ALPHA/ZBUF and texture
  register writers, including the six-register TEX0/TEX1/TEXA/CLAMP
  GIF path and 240 synthetic ELF differential cases.
- [x] Trace the native sprite-command opcode-1 filtering and
  clamping selector tables (EE `0x4F73C8` / `0x4F73D0`),
  `0x104820` flag setter and `0x10DA20 → 0x10C3E0`
  conditional `TEX1` emission. Synthetic packet and
  optional original-ELF-word tests added, plus a
  `--resolve-sampling` packet-inspection flag. A periodic
  PR-diff review also corrected stale decoder documentation.
  **Do not apply per-atlas filters without a captured binding map.**
\n- [x] Follow sprite resource attachment through `0x2FD8F0`
  into `0x2FE920` opcode-1 packet fields, verifying four
  named menu constructors and a bounded exact-ELF inventory
  of 59 linear / 7 nearest / 11 unclassified callsites.
  Constructor flags are **not** live GS filtering captures.
- [x] Remove the screenshot comparator's hardcoded
  four-help-line assumption; VERSUS and OPTIONS use their
  verified three-line ELF text records, with all seven
  item counts regression-tested.

- [ ] Capture **active** GS register state, runtime texture records,
  actual filtering/blending and per-pixel depth behavior via PCSX2.

See [NATIVE_MENU_PHASE6_OFFLINE.md](NATIVE_MENU_PHASE6_OFFLINE.md)
for addresses, code paths, screenshot anchor measurements, test
coverage and explicit unknowns.

## Acceptance checklist

- [ ] No authored sample-23 idle start or sample-120 exit trigger in native mode.
- [ ] No global preview `m_time` substitution for component clocks.
- [ ] State transitions and input gating trace to ELF branches.
- [ ] Arrow per-component 40-tick animation matches native update order.
- [ ] Multiple selection/confirm/cancel sequences replay deterministically.
- [ ] Existing diagnostic timeline and screenshot matcher remain intact.
- [ ] No 4:3 framing, text, atlas placement, or smoothing regression.
- [ ] Windows/Linux CI and focused Qt tests pass.
- [ ] Research notes distinguish recovered behavior, runtime-dependent values, and remaining approximations.
- [ ] Changes committed to PR #14 in reviewable increments.

## Current checkpoint — DRAGON SUMMONING particle milestone (14 November 2026)

The historic "first task" below this section has been superseded: outer lifecycle,
selection, first/character/label clocks and scrolling strips were implemented and
validated previously. The next ongoing scope is **the item-3 six-slot particle pool**.
See [NATIVE_DRAGON_PARTICLES.md](NATIVE_DRAGON_PARTICLES.md) for ELF addresses,
ownership, precise branch order and validation limitations.

### Implementation/ownership checklist

- [x] Verified source ELF SHA-256 and disassembled 0x37A860, 0x37AC10,
  0x37ADB0, 0x37AE80, 0x37AFC0, 0x37B0A0, 0x37B210 and 0x37B370.
- [x] Identified 0x4FDC64 global allocation pointer, 6 * 176-byte slots,
  item-3 instance +0x320 timer and global context +0xA8 RNG.
- [x] Modeled one authoritative six-slot pool per isolated menu runtime,
  plus explicitly shared stream and stable indexed slots.
- [x] Preserved initial five seed positions and 15 RNG outputs, followed by
  timer-expiry spawn/skip and timer RNG calls.
- [x] Fixed the 0x37A8F4 branch ordering: expiry spawns **before** a single
  common movement pass, not afterward.
- [x] Wired the phase-2 callback through `step_first`; paints only read geometry.
- [x] Added Qt particle rendering for selected and pending item 3 and a
  synthetic-texture pixel regression; diagnostic timeline remains independent.
- [x] Added deterministic independent-instance, slot-reuse, reset/replay and
  non-mutating snapshot/repaint tests.
- [x] Added controlled-stub instruction oracle for first-component timer
  (0x37A860), movement/clip (0x37B210), and initial slot sequencing
  (0x37ADB0). These compare supported instructions, **not** the full GS,
  sprite setup/texture setter or real RNG context.
- [x] Registered the new test module in the Windows/Linux CI workflow.
- [x] Established earlier Windows/Linux green baseline at run
  `43653039361` (163 menu/editor tests). New UV and shared-RNG milestones
  must be validated on the latest head independently.
- [x] Added interpreted native 0x37B0A0 initialization, 0x37B210
  fractional clip, 0x37B370 draw writes, 0x37A820 / 0x37AF60 pool
  teardown and 0x4E23B0 boundary initializer regression cases.
- [x] Recovered particle subclass UV vtable 0x4EDCB0: +0x18
  0x2FCDD0, +0x1C 0x2FCE20, +0x24 0x2FDA00. Attached-texture
  normalization and reset have native-word tests; Qt supplies actual
  TIM2 atlas dimensions rather than assuming 512x512.
- [ ] Confirm pathological float-to-short, native GS blend/texture
  configuration and EE FPU hardware last-bit behavior.
- [x] Integrated ten-slot companion logical owner through recovered
  shared-scheduler update_owner/start_owner events; both companion effects
  and item-3 Dragon particles consume one context RNG instance in their
  native shared-before-item update order. Added same-frame interleaving
  and replay/reset tests without guessing native timing.
- [ ] Capture actual live-context seed and further RNG consumers. The
  isolated `particle_seed=1` Qt editor run remains a diagnostic replay.
  Audit pointer-based writes to clip global 0x4FDC60; the direct GP
  initializer 0x4E23B0 stores verified 239.0f.
- [ ] Prove 512×448 native PIX scale, depth, transparency, blending and
  ordering against a game capture before claiming pixel-perfect rendering.
- [x] Render ten-slot companions in Qt native mode using recovered
  `0x378170 → 0x376290 → 0x376600 → 0x376950` active-gated
  sprite path, original texture entry 2 and native depths. Keep
  diagnostic frames and paint/RNG state independent. Added native-word
  draw and offscreen Qt pixel regressions.
- [x] Replace shared tile/banner/seven-small/overlay diagnostic-frame
  clocks with state owned by 0x377DE0, 0x378480, 0x376080 and
  0x376AC0; render from 0x378170 draw order. The existing 140-frame
  diagnostic mode remains independently playable.
- [x] Add integrated shared entry/exit/clock and offscreen Qt pixel
  regressions, plus native-word 0x378170 draw-order/overlay-gate oracle.
  Windows and Ubuntu passed 181 menu/editor tests at 1026084975.
- [x] Recover GS TEST/ALPHA/ZBUF and six texture register writers
  from the EU-beta ELF; test native packet layouts and, for texture
  registers, 240 controlled ELF-word differential cases.
- [ ] Capture live GS TEST/ALPHA/ZBUF/TEXA/TEX1/TEX0/CLAMP state,
  texture uploads and relevant framebuffer/zbuffer values; establish
  true filtering, blending, alpha/depth writes and screenshot parity.
  The current host depth-sort is still a renderer approximation.
- [ ] Keep PR #14 draft until acceptance criteria are satisfied; do not
  conflate passing stubbed instruction tests with complete ELF parity.

### Texture setter and cross-owner RNG checkpoint

The next commits recover texture-backed sprite UV normalization at
`0x2FCE20`, retain native reset metadata from `0x2FDA00`, and
supply real texture 11 dimensions from the opened PIX. The tests include
36 attached-texture setter combinations, a null-texture path, reset,
fractional-clipping cases and non-mutating editor/runtime rebinding.

The shared scheduler now advances the recovered ten-slot companion owner
before item updates. The companion and six-slot Dragon pool share one
injected native LCG context, and a focused test verifies first-entry
companion callbacks and competing same-update RNG draws. Other live
context consumers and the true game seed remain unknown. Research details
are in [NATIVE_DRAGON_PARTICLES.md](NATIVE_DRAGON_PARTICLES.md).

### Shared visual scheduling checkpoint (15 November 2026)

The remaining banner, tile and seven small-sprite layers now run on
their existing recovered ELF state machines, connected through
`step_shared` callback order; the tint overlay uses native shared
opacity/visibility. Geometry is pure and no logical update or RNG
draw happens on Qt repaint. A separate 39-word native draw oracle
tests background → banner → tiles+companions → seven small slots
→ conditional overlay.

The verified native geometry and callback sources are recorded in
[NATIVE_SHARED_VISUAL_LIFECYCLE.md](NATIVE_SHARED_VISUAL_LIFECYCLE.md).
The first full integration passed Ubuntu and Windows in Actions run
`43688998874` (181 menu/editor tests). The additional compositor
oracle must be verified separately on the latest head. The next
scope is compositing/GS state against genuine game output rather
than guessing image blending or frame duration.

### Sprite command and native painter ordering checkpoint (15 November 2026)

After the shared visual milestone, the top-level renderer was found to
globally sort the native draw queue by depth. The actual `0x379E60`
draw callback issues **shared → pending → selected → arrow** in that
order; `0x378170` issues **background → banner → tiles/companions
→ seven small sprites → conditional overlay**. The Qt native renderer
now constructs a command queue in this instruction-verified order,
including the item-3 `0x37A910`
literal/decorations-before-particles order. The rasterizer applies
a stable, depth-ordered **software compositing fallback** (see the
screenshot checkpoint below); native command submission itself is
not a GS Z-buffer implementation. The diagnostic 140-frame renderer
retains its previous depth sort for comparison.

`test_arika_menu_gs_state.py` interprets the native `0x2FDA00`
sprite reset, `0x2FD8F0` texture binding and `0x2FD8A0`
vtable dispatch. These recover raw engine mode fields and the
0/512/0/448 sprite raster bounds; they **do not** recover the
hardware GS `ALPHA`, `TEST`, `ZBUF`, or texture filtering.
Detailed command formats, evidence and remaining unknowns appear in
[NATIVE_MENU_GS_COMMANDS.md](NATIVE_MENU_GS_COMMANDS.md).
The next milestone is tracing intermediate engine command consumers to
real GS state and validating with a game/PCSX2 capture, not inferring
blend mode from byte values. No timing assumptions were added.

### Intermediate renderer packet and context checkpoint

The native sprite command stream is now traceable past the draw
vtable. The dispatcher `0x19B5C0` reads a count-prefixed packet,
switches on nine command opcodes through a verified table at
`0x4C02C0`, and passes the current six-field render context to
`0x199340`. The direct native function `0x199500` copies that
state (13 instructions, including return delay slot).
`0x199340` resolves two backend setter argument sets using
file-backed lookup tables. These are still **engine-side raw
parameters**, not decoded GS `ALPHA/TEST/ZBUF/TEX0` registers.

`arika_menu_gs_packet.py` and `arika_menu_gs_context.py`
provide strict, asset-independent decoders for a future game capture.
Unknown state fields, unverified lookup indices and arbitrary byte
modes are not guessed. Tests check every packet opcode and native
state copy, and reject malformed records or unsupported lookup
indices. The next step is tracing the resulting backend functions
`0x104920 -> 0x104210` and `0x104840 -> 0x103F20`
to a real GS register dump before altering the Qt compositor's
blend or depth modes. See
[NATIVE_MENU_GS_COMMANDS.md](NATIVE_MENU_GS_COMMANDS.md).

### PCSX2 versus Qt screenshot: banner occlusion regression

The supplied 15 November 2026 screenshot pair (958×719 PCSX2 and
706×529 Qt) pinpoints the missing `MAIN MENU` header. The banner is
**not** missing from the PNG atlas or its animation state. Native
`0x378170` submits the title at `[0,16]..[264,64]`, Z=99,
then submits small sprite #2 at `[0,0]..[320,152]`, Z=5.
A QPainter source-over implementation that directly follows the EE
call sequence necessarily hides the entire title. The reference game
renders it in front, so EE submission order alone cannot specify
the final graphics composition.

The editor now retains that exact recovered **submission order**
and separately applies `software_painter_order` as a stable
low-to-high-depth **Qt approximation**. Equal-Z sprites retain
native callback order, while the banner is painted after the
overlapping small sprite. The fix has synthetic-asset offscreen
pixel coverage and is read-only with respect to logical native
state/RNG. It introduces no guessed offsets or clocks.
See [NATIVE_MENU_GS_COMMANDS.md](NATIVE_MENU_GS_COMMANDS.md).

Unresolved: hardware GS depth compare/write bits, alpha test and
blending for semitransparent overlapping sprites. The screenshot is
empirical evidence for this one visible stacking result, **not**
an exhaustive GS trace.

### Hardware GS ALPHA/TEST/ZBUF emitter checkpoint

The previously unresolved backend calls now reach confirmed GS
register writes. The exact EU-beta `0x103F20` function emits
`ZBUF_1/TEST_1` and optionally `ZBUF_2/TEST_2`; `0x104210`
emits `ALPHA_1/ALPHA_2`, both using GIF A+D packets through the
`0x103B00` allocator and `0x102C90` submission path.

The renderer startup selector values map to `TEST=0x0005000F`
(alpha test NOTEQUAL zero and depth comparison GEQUAL) and the
file-backed lookup at `0x4392DB` maps to `ALPHA=0x44`
(source-alpha equation). These explain a plausible native
reason why the later-submitted Z=5 small sprite does not cover
the Z=99 menu banner. They are **not** live-frame GS captures.
The actual ZBUF values depend on BSS globals `0x4FF3BC`
and `0x4FF3B0`, still unknown without running the game.

`arika_menu_gs_registers.py` recovers the GS bit fields,
emitter DMA/GIF packet layout, native lookup selectors and an
optional exact-ELF alpha table reader. Regression tests cover
the default mode, alternative comparison selections, AREF
conversion, packet branches and unknown runtime data.
See [NATIVE_MENU_GS_COMMANDS.md](NATIVE_MENU_GS_COMMANDS.md).

The remaining GS task is narrowing **actual active-frame state**
via PCSX2 GS dumps or instrumentation (including texture
`TEX0/TEX1/CLAMP/TEXA`, Z allocation, alpha and depth write
rules) and then updating Qt compositing. Do not mark pixel
parity complete from a recovered default alone.

### GS texture-register reconstruction checkpoint

The native texture path now has an end-to-end, asset-independent
register reconstruction. The resource selector stored at
`0x4FF470/0x4FF474` passes through `0x10DA20` to
`0x10C3E0`, which reads a 48-byte runtime texture
descriptor from `0x4FF8F0 + (id-1)*0x30`. Its
six-register A+D GIF template at `0x439E70` targets
**TEXA, TEX1_1, TEX0_1, CLAMP_1, MIPTBP1_1
and MIPTBP2_1**. A separate native helper
`0x10C7C0` supplies the mip allocation calculations.
`0x103E70` submits the fixed six-register packet.
See [NATIVE_MENU_GS_TEXTURE.md](NATIVE_MENU_GS_TEXTURE.md)
for verified offsets, formulas, DMA format, inputs and
the remaining unknowns.

`arika_menu_gs_texture.py` now exposes a read-only
48-byte descriptor decoder, the six 64-bit register
values, GIF packet reconstruction and a CLI for a
future PCSX2 runtime record dump. The optional
`arika_menu_gs_texture_elf_oracle.py` executes actual
`0x10C3E0/0x10C7C0` words from the exact
SHA256-verified, user-owned ELF; **240 seeded
synthetic cases matched bit-for-bit**.
The Windows/Ubuntu CI suite uses asset-free tests.
No game textures, ELF bytes or sampled animation
times are introduced.

**Still pending:** real 48-byte runtime records and
BSS renderer selection flags, actual GS packet
captures and active sampling/blending across a
frame, and 4:3/output/FFON screenshot parity.
The Qt software painter is unchanged until those
runtime values are observed.

### Offline native sine/cosine dispatch checkpoint

The remaining OPTIONS and DRAGON SUMMONING idle precision gap has been
narrowed. The actual `0x1859D8` cosine and `0x185C78` sine wrappers
compare float32 `abs(input)` bits with `0x3F490FD8` (π/4). For
larger arguments they call native reducer `0x182900`, receive a
quadrant and two-word f32 remainder, and dispatch to leaf
`0x183DE0` (cosine) or `0x184798` (sine) with native quadrant
sign changes. The complete four-quadrant kernel map is in
[NATIVE_MENU_TRIG_DISPATCH.md](NATIVE_MENU_TRIG_DISPATCH.md).

`arika_menu_native_trig.py` implements a **read-only dispatch
decoder**, including native NEG.S signed-zero handling; it refuses
to invent reducer outputs. The new tests cover thresholds, both
wrappers, four quadrants, signs and the exact native JAL/NEG.S
instruction sites when a SHA256-verified user-owned ELF is supplied.
This is not an EE polynomial or argument-reduction port, so Qt's
host sine/cosine motion remains unchanged. Next: recover the
normal-menu-angle range of the native reducer and the leaf kernels
before claiming last-bit idle-motion parity.

### Follow-up

Continue from the exact existing PR head, consult the particle research file
and CI logs, resolve any oracle discrepancies and keep making reviewable
commits. Do **not** restart at the historic outer-state-machine research
milestone or reintroduce sample-23/sample-120 timing assumptions.
