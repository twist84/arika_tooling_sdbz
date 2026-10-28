# Native pose sampling

`arika_pose.py` connects the isolated native segment clock to local bone poses. This is a research port of the supplied SLES_541.61 binary's one-source and two-source blend structures, not the full native action player. The initial pose is the model rest pose; subsequent updates blend the current live pose toward the newly sampled motion.

## Commands

Use extracted assets and run these commands from this tools directory. Change the asset paths as needed:

```sh
python arika_pose.py animate extracted/ply/p01/p01act.cht goku_pose.gltf --model extracted/ply/p01/p01a.mdl --id 232 --variant 0 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 2 --rate 60 --blend 0.17
python arika_pose.py sample extracted/ply/p01/p01act.cht goku_pose.json --model extracted/ply/p01/p01a.mdl --id 232 --variant 0 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 0.2 --rate 60 --blend 0.17
```

`animate` exports body pose and automatic HandAni selections with a neutral facial program. Textures are found beside the model when possible; `--textures` overrides that path. `sample` writes raw local TRS values, clock state, and hand selections at each tick. The output begins at setup time zero and ends on the first sample at or after the requested duration. Supported rates are 25, 30, 50, 60, 100, and 120 Hz; duration is limited to 60 seconds. `--speed`, `--reverse`, and `--loop` control the segment clock. The blend duration is in the clock's scaled-time units.

For looping previews, add `--loop` and choose a duration long enough to cross the last frame. Add `--reverse` to run backward. The included `examples/goku_native_pose_loop.gltf` and `examples/goku_native_pose_reverse_loop.gltf` demonstrate both directions.

The example `examples/goku_native_pose_blend.gltf` contains a two-second ID 232 variant 0 preview at 60 Hz. It demonstrates an isolated segment starting from model rest, not the complete in-game action transition. Binding identity and precision limits are embedded in the export's `native_pose` extras. `examples/goku_native_pose_trace.json` contains a short reverse-playback trace of that motion.

## Reconstructed behavior

| Native source | Ported behavior |
| --- | --- |
| `0x1B2E20` | One-source live-pose blending without scale channels |
| `0x1B5C60` | One-source live-pose blending with scale channels |
| `0x1B1B00`, `0x1B4450` | Two-source target mixing followed by live-pose blending, without/with scale |
| `0x1B3370`, `0x1B63A0` | Two-source target mixing with direct pose assignment, without/with scale |
| `0x1B41C0`, `0x1B7910`, `0x1B2C80` | Track key selection structure and quaternion interpolation |
| `0x1B84A0`, `0x1B9690` | Clock update and setup; see NATIVE_CLOCK.md |

The shared RFSM bone flags gate translation (bit 0), rotation (bit 1), and scale (bit 2). Components with cleared bits remain unchanged. Scale also requires a motion with scale channels. MOT2 descriptor flags are not a substitute for these shared component masks.

Translations and scales use `current + weight * (target - current)`. Each update reads the current live pose: a translation from 0 toward 10 at weight 0.5 becomes 5, then 7.5 on a second update. A missing motion bone uses the explicit rest translation and rotation, and unit XYZ scale. The standalone sampler supplies model rest as that explicit buffer.

Quaternion blending computes the dot product in Y, X, Z, W order, flips the target for a negative dot, and uses shortest-path spherical interpolation when `1 - dot > float32(0.001)`. The near-parallel branch uses a weighted linear combination without normalization. The raw JSON trace preserves that result; the existing glTF exporter normalizes exported rotations to satisfy its rotation representation.

Track sampling uses float32 time, snaps to a key when its difference is below float32 `1e-5`, holds endpoints, linearly interpolates vectors, and uses the same quaternion blend structure for rotations. The clock's final update is applied before holding the completed pose. Hand selections carry across ticks, including the special initialization tick.

## Loop boundary

The native period includes a one-frame interval between the last and first keys. After the first wrap, that interval samples the end and start poses separately, then mixes end toward start using the clock's `wrap_fraction`. Reverse playback traverses the same mix in the opposite direction. Setup before the first wrap retains the native clamped endpoint behavior. Large time steps can skip this short interval entirely.

The two-source target is computed before applying the live-pose coefficient. Missing bones use the same explicit rest TR and unit-scale fallback. When only the first source is missing, the native helper reverses the source operands and uses `1 - fraction`; the port retains that order for float32 rounding and quaternion signs. When both sources are missing, it directly applies the fallback rather than interpolating identical fallback values. `apply_bone_pair` exposes the helper structure separately for research; the looping CLI supplies two times from the same motion.

HandAni remains a discrete clamped-time preview selection; it is not interpolated through the skeletal seam. Full native special-node callback behavior remains outside this port.

## Validation and limits

`validate_native_pose.py` interprets the original ELF's constant-track and missing-node instruction paths. It checks 3,200 one-source cases and 25,600 two-source cases. The latter cover all eight component masks, all four source-presence combinations, scale enablement, active/inactive live blending, three live coefficients when active, and five source fractions. Twenty pose sets include identical, antipodal, and near-parallel quaternions. Native memory-copy and trigonometric calls are substituted with host functions. Run:

```sh
python validate_native_pose.py SLES_541.61 native_pose_validation.json --gltf examples/goku_native_pose_blend.gltf
python -m unittest discover -s .
```

The validator requires the exact reference ELF SHA-256 recorded in its report. Float operations use separately rounded IEEE float32 arithmetic, including emulated accumulator instructions. Matching these checks does not establish PS2 hardware or native-library bit equivalence. Animated key sampling has regression tests and code tracing, but is not covered by the constant-track instruction oracle.

The single-motion sampler does not implement full action startup and callback ordering, contextual bone binding, root motion, or IK. `arika_transitions.py` provides explicit authored switches between clips; see EXPLICIT_TRANSITIONS.md. `arika_action_player.py` now integrates the supported automatic common-action subset and native helper/direct-channel dispatch; see ACTION_POSES.md. Full gameplay orchestration remains unported. Sequence previews and facial timeline exports retain their existing timing.
