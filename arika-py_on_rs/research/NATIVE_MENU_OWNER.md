# Tile/companion owner lifecycle

The parent shared scheduler is now ported in `NATIVE_SHARED_SCHEDULER.md`, including child update/start ordering and entry/exit waits. It still delegates banner/small animations to callers.

Report version 13 adds `tile_companion_owner`. `arika_menu_owner.py` reconstructs the inner owner holding the shared tiled sprite and companion event timer. It closes the gap between isolated active updates and the owner's entry/active/exit dispatch. The outer menu lifecycle remains separate.

## Native evidence and fields

| Role | Address |
|---|---|
| Initialize owner and pool | `0x00375F90` |
| Update owner | `0x00376080` |
| Entry callback: returns 1 | `0x003761A0` |
| Active timer/tile callback: returns 0 | `0x003761B0` |
| Exit callback: returns 1 | `0x00376280` |
| Start/restart | `0x00376390` |

Table `0x004F19F0` contains the entry/active/exit callbacks at offsets 8/12/16. The extractor checks those entries and the entry/exit return instructions. The report includes function words and the field map.

| Offset | Meaning | Initialize | Start/restart |
|---:|---|---|---|
| +112 | Owner phase | 0: inactive | 1: entry |
| +116 | Owner age (float) | 0 | 0 |
| +120 | Tile phase (float) | 0 | 0 |
| +124/+128 | Tile offsets | Startup reset X/Y: 0, 0 | Preserved |
| +132 | Event timer (float) | 0 | Preserved |
| Separate pool | Ten slots | Reset | Preserved |

Initialization also configures the tiled sprite; resource/GPU setup is not emulated here. Outer shared entry routine `0x00377FB0` calls start. Its occurrence relative to shared updates is outside this isolated schedule.

## Update order

Phase zero returns immediately: no age increment, movement, timer change or random input. Every nonzero phase increments age, subtracting 99999 once only when the result is strictly greater than 99999, then updates all companion slots. This precedes dispatch, including entry and exit.

| Phase before update | Callback/result |
|---:|---|
| 1: entry | Returns 1; set phase 2 and age 0; no event RNG or tile advance |
| 2: active | Run timer/spawn/tile clock; return 0 and remain phase 2 |
| 3: exit | Returns 1; set phase 0 and age 0 after a final movement/retirement pass |
| Other nonzero | No callback; retain phase after age increment and slot update |

The active callback does not move slots. The port factors `advance_event` from the previous `step_state` so owner updates move slots once before processing the event. Existing isolated `step_state` behavior is preserved.

The first update after explicit start performs entry. The following update processes timer zero, attempts the first spawn and advances tile phase to 1. Restart resets tile phase while preserving the timer and slots. The fixed active callback never naturally enters exit; tests inject phase 3 to check that branch without claiming an exit trigger.

Owner phase is an **update gate**, not a proven visibility gate. Shared draw `0x00378170` calls tile drawing independently of this phase; tile drawing then draws active companions. Exported companion geometry continues to follow active slots, without invented phase-based hiding.

## Export

```sh
python arika_menu_companions.py SLES_541.61 owner_trace.json --schedule owner --rng native --seed 1 --steps 1801 --svg owner.svg
```

`--schedule active` remains the default. `--schedule owner` initializes the owner and explicitly starts it before sample zero. Version 4 traces add per-frame `owner_phase`, `owner_age` and dispatch metadata. Seed and start moment are diagnostic choices, not a captured game run.

`examples/menu_companion_owner_trace.json` contains one entry pass followed by 1800 active passes, 8559 quads and 48 random draws. `previews/menu_companions_owner.svg` shows isolated geometry. Removing the entry sample leaves matching positions, timers, tile phases and random draws against the existing native-seed-1 active trace. The SVG uses an authored 60 ticks/s, not measured native timing.

## Validation and limits

All 61 menu tests pass. Added checks cover:

- 580 owner updates across inactive, entry, active, exit and unexpected phases, age-wrap boundaries and event-timer boundaries. Dispatch and actual entry/active/exit instructions execute in the scalar interpreter. The pool callback delegates each slot to the independently interpreted native slot-update helper. Full-pool spawn attempts are stubbed and timer RNG consumption is checked.
- Initialization/start fields and timer/slot preservation on restart. Resource setup and pool initialization are stubs in the initialization comparison.
- Exit retirement followed by an inactive freeze.
- 1800 active steps after entry matching the older isolated schedule and final RNG state.

The default active CLI trace remains identical to the bundled earlier native trace. The owner SVG was rendered for static inspection; interactive SVG playback remains untested. Arithmetic uses host float32, not PS2 hardware FPU/accumulator emulation. Outer menu timing, exit requests, captured RNG synchronization, animation curves, textures and final compositing remain unresolved.
