# Explicit clip transitions

`arika_transitions.py` previews a user-authored schedule of motion switches. It combines the recovered native scalar clock and one-/two-source bone helpers across different MOT2 clips. It retains the current live pose and hand selections when switching clips.

Switch times and blend settings are explicit inputs. They are not recovered game events or measured native action-transition timestamps. The existing common-table sequence preview remains separate.

## Use

```sh
python arika_transitions.py animate extracted/ply/p01/p01act.cht examples/goku_transition_schedule.json transitions.gltf --model extracted/ply/p01/p01a.mdl --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 5 --rate 120
python arika_transitions.py sample extracted/ply/p01/p01act.cht examples/goku_transition_schedule.json transitions.json --model extracted/ply/p01/p01a.mdl --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 5 --rate 120
```

`animate` exports a body-and-hands glTF with neutral facial playback. Textures are found beside the model, or selected using `--textures`. `sample` records local TRS, clock state, selected segment, hands, and any two-source entry bridge. Output metadata includes the normalized schedule, each switch's resolved binding, and the outgoing sample time. The first clip starts from model rest.

The included five-second `examples/goku_explicit_transitions.gltf` switches from ID 232 variant 0 to variant 1 with looping, then returns to variant 0 in reverse. Its switch times are a demonstration chosen in `examples/goku_transition_schedule.json`.

## Schedule

```json
{
  "segments": [
    {"at": 0, "motion_id": 232, "variant": 0, "blend": 0.17},
    {"at": 1.3333333333333333, "motion_id": 232, "variant": 1, "blend": 0.17, "loop": true},
    {"at": 3.2, "motion_id": 232, "variant": 0, "blend": 0.25, "reverse": true}
  ]
}
```

| Field | Meaning | Default |
| --- | --- | --- |
| `at` | Wall-time switch point, in seconds | Required |
| `motion_id` | CHT logical motion ID | Required |
| `variant` | Zero-based CHT variant | 0 |
| `blend` | Incoming live-pose blend duration in scaled clock time | 0.17 |
| `speed` | Incoming clock speed, with native floor 0.01 | 1 |
| `start_frame` | First frame of incoming range | 0 |
| `end_frame` | Last frame; a negative value selects the clip's last frame | -1 |
| `reverse` | Play incoming range backward | false |
| `loop` | Repeat incoming range, including its one-frame seam | false |

The first switch must be at zero; subsequent times must strictly increase. Unknown fields, nonfinite values, invalid booleans, negative blends, unresolved CHT motions, and switches after the requested duration are rejected. At most 1,000 segments and 60 seconds are supported. Sample rates are 25, 30, 50, 60, 100, and 120 Hz.

## Transition structure

On a switch, the preview freezes the outgoing clip at its current clamped motion time and resets the incoming clock to its fresh baseline. The live bone pose is preserved. While the incoming position is within the baseline-to-first-key gap, the sampler mixes the outgoing sample into the incoming endpoint over one incoming frame period. In reverse, that endpoint is the incoming range's last frame. The incoming live-pose coefficient is then applied to the mixed target. After that interval, only the incoming motion supplies the target. Later loop seams use that motion's end/start samples as documented in NATIVE_POSE.md.

This uses the two-source helper structure dispatched by native `0x1B84A0` and the math checked at `0x1B1B00`, `0x1B3370`, `0x1B4450`, and `0x1B63A0`. The preview owns the switch and outgoing-time capture policy. Native `0x1B8FB0` and `0x1D7120` also involve motion lists, callbacks, flags, and recursive carry processing; those functions have not been replaced by this explicit scheduler.

An event between output ticks splits that tick's delta: the old clock advances to the event, the switch occurs, and the new clock receives the remainder. That extra pose evaluation is part of this offline preview's contract. It is not a claim about the game's own tick ordering. A completed non-looping clip holds until the next scheduled switch. Repeating or interrupting a clip uses another schedule entry. No automatic common-table advance is inferred.

Component masks and fallback rules apply across both sources. Packages must have identical named component masks; contextual rig rebinding is rejected. An incoming scale-enabled motion with an outgoing motion lacking scale channels is also rejected when a bridge is evaluated. Special scale-helper inheritance across native action startup is still unported. Bone translation is local; root-motion accumulation and IK remain outside the preview.

HandAni uses discrete incoming clamped-time sampling and retains negative hand requests across switches. It does not blend special-node callbacks. Facial programs and gameplay callbacks are not scheduled by this tool.

## Verification

The package has 104 passing unit tests. Ten transition tests cover live-pose retention, mixing before the live coefficient, direct entry mixing, reverse entry, off-tick delta splitting, stopped outgoing clips, hand retention, schedule validation, unsupported component-mask rebinding, and future-event rejection.

`transition_preview_validation.json` records a 601-sample Goku integration check with two switches, two entry-bridge samples, finite local pose values, and glTF buffer/accessor and animation-count checks. It is an export integrity check, not validation of native gameplay orchestration. `native_pose_validation.json` separately records 3,200 one-source and 25,600 two-source helper cases matched under the documented host float32/trig model. PS2 hardware and original libm bit equivalence remain unverified.

```sh
python -m unittest discover -s .
python validate_native_pose.py SLES_541.61 native_pose_validation.json --gltf examples/goku_explicit_transitions.gltf
```
