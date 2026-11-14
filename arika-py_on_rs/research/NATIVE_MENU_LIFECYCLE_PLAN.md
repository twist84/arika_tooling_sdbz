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
- [ ] Render shared tiles, banner and companion effects through native
  scheduler-owned clocks and geometry: companion *logical owner and RNG*
  are integrated, but Qt's companion graphics/other shared effects still
  need native draw ordering, visibility and pixel parity.
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

### Follow-up

Continue from the exact existing PR head, consult the particle research file
and CI logs, resolve any oracle discrepancies and keep making reviewable
commits. Do **not** restart at the historic outer-state-machine research
milestone or reintroduce sample-23/sample-120 timing assumptions.
