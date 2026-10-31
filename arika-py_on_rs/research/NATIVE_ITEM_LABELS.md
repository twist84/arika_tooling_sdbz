# Selected-item label entry and exit

Report version 17 adds `item_label_animation`. `arika_menu_labels.py` reconstructs the entry, steady active and exit subset for all seven textured item labels. The textured viewer now enables this motion by default, with a **Recovered label motion** checkbox to compare against the previous startup pose.

## Evidence

| Role | Address |
|---|---|
| Label lifecycle update | `0x0037DF90` |
| Start entry / start exit | `0x0037E120` / `0x0037E140` |
| Entry-start callback | `0x0037E1C0` |
| Exit-start callback | `0x0037E290` |
| Entry curve callback | `0x0037E2D0` |
| Exit curve callback | `0x0037E3D0` |
| Emphasis callback (not ported) | `0x0037E460` |

Concrete label vtables and source rectangles reuse `composite_layout.layers.item_overlays`. The extractor verifies shared entry/exit callbacks, the active-start age reset and concrete active callbacks returning zero. Signed direction bytes are read from the concrete setup callbacks, including packed halfword stores.

| Item | Label | Direction X/Y |
|---:|---|---|
| 0 | ORIGINAL | 1, 0 |
| 1 | Z SURVIVOR | 1, 0 |
| 2 | VERSUS | 0, -1 |
| 3 | DRAGON SUMMONING | -1, 0 |
| 4 | TRAINING | 0, -1 |
| 5 | CUSTOMIZE | -1, 0 |
| 6 | OPTIONS | 0, 1 |

## Curves and lifecycle

Entry approach times (10, 20) are at `0x004FA7A8`; values (512, 0) at `0x004FA7B0`. The interpolation helper returns the first sample before age 10, so the label holds at its initial displacement for ten updates. It then approaches its base through age 20. From age 20, an additional curve at `0x004AA230` / `0x004AA270` adds the familiar twelve-update bounce: times 0–12, values 0,3,6,3,0,2,4,2,0,1,2,1,0. The scalar displacement is multiplied by each signed direction.

Entry start sets phase 1, age zero, component depth 45 and the initial directional offsets. At age 32, entry sets offsets to the verified reset position (0,0), selects active phase 2, and invokes its active-start callback, which resets age to zero. Active returns zero and keeps the component active.

Exit start sets phase 4, age zero, component depth 15 and offsets (0,0). Thus an interrupted entry snaps to its base before exiting; the port preserves that behavior. Exit uses times (0,10) at `0x004FA7C8` and values (0,512) at `0x004FA7D0`. At age 10, phase becomes zero while age and final offsets remain. Inactive labels neither update nor draw.

The draw path adds component offsets to the recovered base position and centers the label quad. Draw depth is component depth plus 25: 70 for entry/active and 40 during exit. These values are exported but do not establish final GPU depth composition. All nonzero phases increment float age, subtracting 99999 once only when the result is strictly greater than 99999.

**Phase 3 is excluded.** Its callback combines a repeating shake with a separate amplitude curve. `step_label` raises a clear error for that phase, rather than silently approximating it. This pass does not recover actual selection/input timing or the other item component groups.

## Trace and viewer

`examples/menu_label_trace.json` contains independent 140-sample timelines for all seven labels. They start before sample zero, request exit at sample 120, and become inactive at sample 130. The schedule is diagnostic, not a captured selection change. `trace_labels(report)` regenerates it from the report.

`arika_menu_textured.py` embeds these recovered coordinates into the offline viewer. Scrubbing or playing now moves the selected label while shared banner/tile/panel motion continues. Toggling label motion off shows its earlier static base pose. Character parts and selected scenery remain static. The existing seven-item/atlas/layer controls remain available.

## Validation and remaining work

All 75 menu tests pass. New tests compare 875 updates across seven directions, inactive/entry/active/exit/unknown phases, curve boundaries and age wrapping against actual lifecycle/callback/interpolation instructions. Complete native start, 32-update entry and ten-update exit sequences also match offsets, ages, phases and component depth. Geometry checks cover base placement, draw depth and inactive suppression; unreconstructed phase 3 is explicitly rejected.

The delivered HTML's JavaScript also passes real Canvas checks for settled-label visibility and exited-label suppression, in addition to its atlas, item, layer and flipped-UV tests. Full-browser playback remains untested. Arithmetic uses host float32 rather than PS2 hardware FPU/accumulator emulation.

Next: phase-3 emphasis, middle-group character-part motion, first-group scenery/effect motion, native selection scheduling, blend/depth behavior and final compositing.
