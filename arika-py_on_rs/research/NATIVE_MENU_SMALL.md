# Shared small-component animation

Report version 16 adds `shared_small_animation`; `arika_menu_small.py` implements entry displacement, lifecycle dispatch and state-gated geometry for all seven shared small components. The shared-scheduler example can now update these components alongside the recovered banner and companion owner.

## Native evidence

| Role | Address |
|---|---|
| Initialize small component | `0x00376A00` |
| Update dispatch | `0x00376AC0` |
| State-gated draw | `0x00376C20` |
| Start entry | `0x00376C70` |
| Request stop | `0x00376C90` |
| Entry-start callback | `0x00376D10` |
| Entry-update callback | `0x00376DF0` |
| Shared interpolation helper | `0x002C2C10` |

The seven concrete tables at `0x004F1A50 + 64 * index` override the base active callback with a function returning zero. This matters: the base table's active callback returns one, but these concrete components remain active after entry. The extractor verifies entry callbacks, the concrete active return, the no-op active-start callback, and completion callbacks. Setup direction bytes are read from native instructions, including stores in call delay slots.

| Component | Direction X/Y | Setup |
|---:|---|---|
| 0 | 1, 0 | `0x00376F90` |
| 1 | 1, 1 | `0x00377110` |
| 2 | -1, -1 | `0x00377290` |
| 3 | 1, -1 | `0x00377410` |
| 4 | -1, 0 | `0x00377590` |
| 5 | -1, 1 | `0x00377710` |
| 6 | 0, 1 | `0x00377890` |

Resource entry 3, UV rectangles, base positions and setup evidence reuse the existing shared-layer extraction. Depth is 5. Component 2's base remains the verified startup zero-fill position; subsequent runtime writes are not inferred.

## Entry curves

The approach curve uses times (0, 5) at `0x004FA630` and values (256, 0) at `0x004FA638`. At ages at least 5, a second curve is added using age minus 5:

| Bounce times | Bounce values |
|---|---|
| 0 through 12, inclusive | 0, 3, 6, 3, 0, 2, 4, 2, 0, 1, 2, 1, 0 |

These arrays begin at `0x004A9F00` and `0x004A9F40`. Interpolation is the same host-float32 reconstruction verified for the banner. The resulting scalar displacement is multiplied independently by signed direction X and Y.

Starting entry sets phase 1, resets age to zero, and immediately computes offsets at age zero: 256 times each direction. Unlike banner start, small-component start does write offsets on the start pass. Entry completes at age 5 + 12 = 17, sets phase 2, and resets offsets to the startup reset position (0, 0). Age is preserved at 17, not reset by this transition.

## Lifecycle and visibility

Phase is at +4, float age at +8, offsets at +112/+116 and signed direction bytes at +120/+121. Inactive phase zero skips updates and drawing. Nonzero phases increment age, subtracting 99999 once only when the result is strictly greater than 99999.

| Phase | Behavior for these seven concrete components |
|---:|---|
| 1 | Entry curve; completion selects phase 2 without clearing age |
| 2 | Active callback returns zero; remain active |
| 3 | Completion callback returns one; select phase 2 without clearing age/offsets |
| 4 | Completion callback returns one; become inactive without clearing age/offsets |
| Other nonzero | Increment age without invoking a phase callback |

The stop helper sets phase 4 and calls a no-op callback; the next update becomes inactive. The shared exit scheduler does not itself issue these stop requests, so the example does not invent them. Geometry exports include every nonzero phase, matching the native state-gated draw. Positions are base plus current offsets; textures, clipping and scene compositing remain outside the preview.

## Integrated example

```sh
python examples/menu_shared_schedule.py examples/menu_shared_children_trace.json --banner --small
```

`--small` enables recovered small starts/updates and feeds their phases back into the shared scheduler before readiness checks. It can be used independently of `--banner`. Both options default off, preserving previous examples. Version 3 integrated traces add each component's phase, age, offset and optional geometry. Initialization at sample zero, seed 1 and shared exit at sample 120 remain authored diagnostic choices.

The shared stagger starts the last component at sample 39; all seven have completed entry by sample 56. The shared phase becomes active at sample 54, so the last component can still be finishing its bounce after that transition. The parent stops updating at sample 129; active children then freeze without invented stop calls.

`previews/menu_shared_small.svg` animates the seven components with a distinct color per component, every-update sampling and an authored 60 ticks/s. Static viewers show the first sample, which has no active components. A later sample was rendered for inspection. The preview represents recovered geometry motion, not textured native output or a measured game tick frequency.

## Validation and scope

All 72 menu tests pass. New tests compare 1,050 updates against actual native dispatch and curve instructions across all seven concrete components, six phase values, entry boundaries and age-wrap cases. Complete start, 17-update entry, active and stop sequences also execute against the native instructions. Tests check direction bytes, bounce values, signed float offset bits, age preservation, base geometry and inactive draw suppression.

The interpreter executes nested interpolation calls; only known no-op/constant concrete callbacks are supplied from verified instruction patterns. The earlier scheduler and banner examples regenerate identically with small motion disabled. The integrated example checks settling and shared-phase timing. Host float32 comparisons do not establish PS2 hardware FPU/accumulator accuracy. Interactive SVG playback remains untested.

Next work: actual outer menu activation/input/exit timing, item-specific animation curves, captured RNG synchronization, textures, viewport clipping and final compositing.
