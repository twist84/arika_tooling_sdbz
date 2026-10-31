# Selected-character common entry and exit

Report version 19 adds `item_character_animation`. `arika_menu_characters.py` recovers the common whole-character entry/exit displacement used by all seven middle component groups. The textured viewer now animates this displacement with a **Recovered character entry/exit** toggle. Per-part idle and emphasis callbacks are not included.

## Evidence and curves

The concrete component tables reuse the seven `composite_layout.composites` vtables. Their initialization callbacks supply signed direction bytes at +24/+25. All seven use entry-update callback `0x0037F350` and exit-update callback `0x0037F3F0`. These callbacks increment age themselves; generic dispatcher `0x0037F100` does not increment age globally. The common entry math is `0x0037F500`, and exit math is `0x0037F6D0`. The report records these helper words and curve addresses.

| Item | Direction X/Y |
|---:|---|
| 0 | 1, 1 |
| 1 | 0, 1 |
| 2 | -1, 0 |
| 3 | 0, 1 |
| 4 | 1, 0 |
| 5 | 1, 1 |
| 6 | 0, -1 |

Entry uses times (0,10) at `0x004FA810` and values (512,0) at `0x004FA818`. After age 10 it adds the twelve-update bounce at `0x004AA2D0` / `0x004AA310`, with values 0,3,6,3,0,2,4,2,0,1,2,1,0. Entry completes at age 22. Exit uses times (0,10) at `0x004FA830` and values (0,512) at `0x004FA838`, completing at age 10. Samples are multiplied by the signed X/Y directions.

Geometry uses the existing `pose_part` function, which preserves each component's native addition/subtraction convention, anchor mode, per-part placement, UV endpoints and depth offset. Item 2 subtracts its component offset; this convention is retained rather than applying a generic translation to every character. Individual part offsets remain zero in this pass.

The preview uses entry component depth 45 and exit depth 15; character part depth adds 15 and its record's depth offset. The existing shared/selected depth queue is preserved. Settled geometry at sample 70 remains pixel-identical to the reference-corrected preview, including selected sky strips and arrows.

## Trace and scheduling

`examples/menu_character_trace.json` contains all seven independent character timelines. `trace_characters(report)` regenerates the trace. It starts the groups before sample zero, requests exit at sample 120, and removes character geometry at sample 130. Entry reaches the settled pose at sample 22. This is an authored visualization schedule, not recovered native selection/input timing.

The textured viewer embeds the trace. The new toggle compares recovered whole-character entry/exit with the earlier static pose. Label motion remains independently controlled. Scenery and effects retain their existing startup offsets and scrolling strips.

## Validation and limits

All 78 menu tests pass. New tests compare 560 common curve-helper calls against the actual native instructions, across all seven directions, entry and exit, endpoint/fractional ages and completion returns. Trace checks verify every settled quad against the previous geometry and every part's depth; exit visibility is checked at samples 129 and 130. The actual HTML JavaScript renderer also checks settled-character visibility and suppression after exit. The settled ORIGINAL PNG matches the preceding corrected preview pixel-for-pixel.

These tests validate the common displacement helpers, not the complete concrete character lifecycle. Concrete active callbacks can animate individual part offsets; phase-3 emphasis uses another helper. Those callbacks are deliberately not simulated. Likewise, outer selection timing, inter-component activation offsets, active idle motion, interruption behavior and native blending remain unresolved. Host float32 arithmetic is not PS2 hardware FPU/accumulator emulation; full-browser playback remains untested.

Next: individual character-part idle/emphasis motion and the actual selected-item activation schedule.
