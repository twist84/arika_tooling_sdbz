# DRAGON SUMMONING combined idle

Report version 24 adds item 3 to `character_idle`. The textured viewer now has idle motion for all seven items. DRAGON SUMMONING combines two circular paths with an extra sway curve; both this item and OPTIONS use explicitly documented host-trigonometry approximations.

## Native evidence

The callback is `0x00380450`. Float age increments by one and subtracts 480 once when it reaches or exceeds 480. Angle values (0, float32(-2*pi)) start at `0x004FA8A0`, with times (0,480) at `0x004FA8A8`. Radii 15 and 10 are stored at `0x004FA898` and `0x004FA89C`. The negative angle produces clockwise motion in the underlying offset calculation.

The five-sample sway curve has values (0,-2,0,2,0) at `0x004AA5E0` and times (0,120,240,360,480) at `0x004AA600`. The sample-count bytes at GP-19136 and GP-19132 are two and five. Both circular paths use the same interpolated angle and native cosine/sine calls at `0x001859D8` / `0x00185C78`.

For radius R, the circular offset is X=R-R*cos(angle), Y=R*sin(angle). Let L be the radius-15 pair, S the radius-10 pair, and W the sway value. Native jump table `0x004CC960` routes the eight part offsets at component +1184 onward:

| Part | Offset |
|---:|---|
| 0 | L.x, L.y-W |
| 1 | L.x, L.y |
| 2 | S.x, -S.y |
| 3 | L.x, L.y+W |
| 4 | L.x+W, L.y+W |
| 5 | L.x, L.y-W |
| 6 | L.x, L.y-W |
| 7 | L.x+W, L.y+W |

The decompiler's apparent infinite loop is another bounded native switch. The report includes the original words, curve/radius/count locations and all eight jump-table targets. The port preserves signed float zero and native operation boundaries around the multiply/subtract and sway additions.

## Integration and accuracy

`step_dragon_idle` supplies the offsets to the existing per-part geometry builder. The integrated trace and viewer keep the existing authored entry/idle/exit schedule and hold the last idle offsets during exit. The idle toggle switches all seven items back to zero per-part offsets for comparison.

The preview evaluates sine/cosine with host math, rounded to float32. It does not emulate native libm argument reduction or claim native trig last-bit equivalence. That limitation is stored in `trig_model` and trace metadata. CUSTOMIZE's independent secondary clock still uses an explicit authored zero starting phase. Actual selection timing and emphasis remain unresolved.

## Validation

All 86 menu tests pass. Added cases execute 600 actual native DRAGON SUMMONING callbacks with the real interpolation helper and controlled trig returns. They verify the updated clock, all four trig-call angle arguments, the native eight-case jump table and all sixteen stored offset float bits. Cases span the full 480-update cycle, fractional and out-of-range ages, and wrap boundaries. Separate host-trig tests check both radii, sway routing and full-cycle closure.

These comparisons validate the callback surrounding its trig calls; they do not validate native sine/cosine internals. Prior native linear/coupled/circular callback tests still pass. The actual HTML Canvas validator checks that enabling DRAGON SUMMONING idle changes its rendered parts while retaining the earlier atlas, layer, depth, sky and exit checks. Full-browser playback remains untested.

Next: selected-item emphasis/shake callbacks, native activation/selection timing, and native trig/blend fidelity where required.
