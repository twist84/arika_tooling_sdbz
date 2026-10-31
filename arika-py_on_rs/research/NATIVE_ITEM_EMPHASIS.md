# Common selected-item emphasis/shake

Report version 25 adds `item_emphasis`. `arika_menu_emphasis.py` reconstructs the common directional displacement used by label and character emphasis callbacks. The textured viewer has an optional sample-80 demo and a **Play shake** control. The default animation remains unchanged until the demo is enabled.

## Native helpers and curves

| Layer | Displacement helper | Pulse times / values | Amplitude times / values |
|---|---|---|---|
| Labels | `0x0037E460` | `0x004AA2B0` / `0x004AA2C0` | GP-19384 / GP-19376 |
| Characters | `0x0037F5F0` | `0x004AA350` / `0x004AA360` | GP-19280 / GP-19272 |

Both layers use pulse times (0,1,2,3), values (0,1,2,1), and period 3+1=4. Amplitude falls linearly from 6 to 0 over ages 0 through 15. The native helper calls float remainder `0x00185E50` for the pulse phase, multiplies the sampled pulse by amplitude, then multiplies by the component's signed X/Y direction. Label and character directions remain independent, so a given item can shake them along different axes.

The label callback resets its X/Y offsets to startup reset values at age 15 and beyond. The character displacement helper returns completion without clearing offsets itself; its caller `0x0037F460` performs the reset. The standalone math function supports both forms so the actual native helper can be compared accurately, including signed-zero results before caller cleanup.

## Activation and state persistence

Label emphasis request `0x0037E160` selects phase 3; start callback `0x0037E2B0` resets age and X/Y offsets without changing depth. Character request `0x0037F280` likewise selects phase 3; start callback `0x0037F330` clears age/offsets while preserving depth and the per-part idle arrays.

The label generic dispatcher increments age, whereas the character emphasis-update callback increments it. Their generic phase-3 dispatch branches ignore the completion return. Therefore displacement ends after 15 updates, but the component does **not** automatically return to phase 2. Part idle stops advancing when emphasis starts, and its last values remain through emphasis and exit. The preview preserves this instead of inventing automatic idle resumption.

## Viewer and trace

Enable **Emphasis demo at sample 80**, or click **Play shake**. The latter seeks to sample 80, enables the demo and starts playback. The demo triggers the selected label and whole-character emphasis together at an authored time; other controls still allow inspecting labels, character motion, per-part idle and scenery independently. Native input/selection timing is not inferred from this trigger.

`examples/menu_emphasis_trace.json` contains both label and character diagnostic traces. They retain the sample-120 authored exit request. Version 2 trace metadata identifies the emphasis trigger and persistent phase-3 behavior. Default traces remain compatible with earlier examples. The existing selected sky, global depth ordering, arrows and all seven idle patterns are retained.

## Validation and limits

All 89 menu tests pass. Added comparisons execute 1,120 actual native displacement helpers: seven label directions and seven character directions, with 80 integral/fractional/boundary ages each. The actual interpolation and multiplier instructions execute; the remainder call is stubbed with float32 host `fmod`, and its age/period arguments are checked. These tests validate the helpers surrounding the remainder call, not the entire native libm implementation or hardware floating-point behavior.

Other tests check that label phase 3 persists after age 15, offsets settle to zero, traces shake at the authored trigger, idle is interrupted and later exit still hides the geometry. The actual HTML Canvas validator checks the Play shake control and pixel differences between enabled and disabled emphasis, alongside earlier idle, UV, sky, depth and visibility checks. Full-browser playback remains untested.

Native selection/activation timing, interruption rules across real input changes, native math fidelity and final GPU blend behavior remain pending. OPTIONS/DRAGON SUMMONING idle retain their explicit host-trig approximation, and CUSTOMIZE retains its authored secondary-clock starting phase.
