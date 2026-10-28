# Automatic common-action skeletal previews

`arika_action_player.py` connects the supported common-action clock chain to local skeletal poses and discrete HandAni selections. It resolves the common table and CHT references, advances automatically, applies each evaluated clip pose, and exports JSON traces or glTF animation. No authored switch schedule is required.

This covers the supported common-default subset, not complete gameplay execution. Character-specific table overrides, gameplay callbacks, contextual skeleton/resource rebinding, root transforms, IK, and special-node callback behavior remain outside the preview.

## Commands

```sh
python arika_action_player.py animate SLES_541.61 extracted/ply/p01/p01act.cht action.gltf --model extracted/ply/p01/p01a.mdl --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 5 --rate 120 --initial-blend 0.17
python arika_action_player.py sample SLES_541.61 extracted/ply/p01/p01act.cht poses.json --model extracted/ply/p01/p01a.mdl --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 5 --rate 120 --initial-blend 0.17
```

`animate` exports body and automatic hands with neutral facial playback. The sibling PIX supplies textures, or `--textures` selects another file. `sample` records local TRS, hands, clock snapshots, segment selection, startup events, and the pose evaluations performed within each output tick. These evaluations include intermediate outgoing/incoming clips when carry crosses a boundary.

The initial pose is model rest. Initial blend remains a caller input, defaults to zero, and is not inferred from the action ID. Supported rates are 25, 30, 50, 60, 100, and 120 Hz; duration must be in `(0,60]` seconds. Output ends at the first sample on or after the requested duration.

The included `examples/goku_action_232_native_poses.gltf` and `.json` run five seconds at 120 Hz with initial blend 0.17. The opening advances into variant 1 and replays automatically. Their clock states and startup events match the previously exported scalar trace `examples/goku_action_232_native_clock.json`. They are simulation outputs, not in-game captures.

## Evaluation order

Each positive clock update evaluates the current clip pose before its completion causes another common-record startup. With zero carry, the incoming clock stays at its baseline and the outgoing final pose remains visible until a later positive update. Positive carry evaluates the incoming clip in the same output tick. A large delta can evaluate multiple clips in sequence; each update changes the live pose before the next update reads it.

The native completion tail after `0x1B89B0` performs terminal cleanup and invokes the completion callback after returning from pose dispatch. The standalone controller reproduces this ordering for the supported common-action transition path. It does not execute arbitrary native callbacks.

Common startup clears the previous-motion pointer, so there is no outgoing/incoming entry bridge. The first incoming update uses its clamped endpoint as the target. Its live-pose blend coefficient either inherits the old countdown or resets to float32 0.17 according to the outgoing record. See ACTION_STARTUP.md for transition precedence and initializer settings. Replay is a fresh common-record startup, distinct from the isolated motion sampler's native loop-gap path.

## Pose dispatch

Native `0x1B8948` chooses between the per-bone helpers and the direct animated-channel path. The player uses helpers when the clock is dirty, blending remains active, or the blend expires on this update and marks the clock dirty. Helpers apply named component masks, constant values, and missing-bone rest/unit-scale fallbacks as documented in NATIVE_POSE.md.

Once those conditions clear, the native `0x1B0C30` path walks only animated channels. The port updates named tracks marked `animated` and leaves constants and missing bones untouched. It does not reapply helper fallback values on every bulk update. Bulk channel routing uses the parsed named forward mapping; contextual native rebinding is not inferred. Across action packages, named component masks must match or the tool rejects the action.

The older isolated-pose and explicit-transition samplers retain their helper-based evaluation contracts. This automatic player adds the direct-channel dispatch path. Raw pose traces retain native-style quaternion results; glTF rotations are normalized by the existing exporter.

HandAni uses discrete sampled requests and carries negative requests across evaluated clips. That is a preview policy, not an emulation of the full native special-node callback pipeline. Facial programs, world/root-state resets and root-motion accumulation are not applied.

## Verification

All 130 unit tests pass. Thirteen player tests cover initial state, constant/missing-track preservation in bulk mode, animated sampling, terminal pose before startup, positive carry ordering, cleared entry bridges, blend reset/expiry dispatch, multiple replays, terminal hold, hand retention, contextual-mask rejection, and automatic sampling.

`validate_action_player.py` composes original-instruction oracles for scalar timing, dispatch selection, startup arguments and constant-bone helper math. It checks 128 synthetic chains: 768 input steps and 880 pose evaluations across advance, replay, jump, blend-reset, eight component masks, scale enablement and two speeds. It also checks reference tail instructions showing pose return precedes terminal callback. This is not a single full-program emulator: constructors, binding fixtures and the high-level composition remain supplied by the validation harness. Animated key sampling and HandAni are covered by regression/integration checks, not this constant-pose instruction oracle.

The Goku integration check reads 601 pose samples and 603 evaluations (24 helper, 579 animated-channel updates), compares scalar states/startup events with the saved clock trace, checks finite local transforms and hand ranges, and validates glTF buffer/accessor and animation counts. It does not establish rendered fidelity or whole-game equivalence. Host IEEE float32 and substituted trig functions retain the precision limits in NATIVE_POSE.md.

```sh
python -m unittest discover -s .
python validate_action_player.py SLES_541.61 action_pose_validation.json --gltf examples/goku_action_232_native_poses.gltf --pose-trace examples/goku_action_232_native_poses.json --clock-trace examples/goku_action_232_native_clock.json
```

Unsupported common flags, unresolved motions, table fall-through, invalid jumps, zero-range common startup, and excessive per-tick transition counts retain the rejections documented in ACTION_STARTUP.md. See `action_pose_validation.json` for the audit report.
