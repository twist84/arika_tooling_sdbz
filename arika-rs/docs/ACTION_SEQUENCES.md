# Common action sequence previews

`arika_sequence.py` follows the confirmed common-table transition graph, resolves each reachable segment through CHT, and exports a body-and-hands sequence. An optional facial event schedule runs alongside it. This is an offline local-track preview: it does not reproduce native tick carry, pose blending, root-motion accumulation, IK, native table overrides or event-driven transitions.

## Plan and inspect

```sh
python arika_sequence.py plan SLES_541.61 extracted/ply/p01/p01act.cht sequence.json --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt
```

The JSON includes ordered reachable segments, motion bindings, frame ranges, effective speeds, transitions and any repeating cycle. It visits each segment once when building the graph; loops do not produce an unbounded list. Unresolved motions, invalid jumps, table fall-throughs and unsupported reachable flags cause an error. Unreachable records do not prevent a valid path from being previewed.

Goku's common action 232 advances from variant 0 (`m01232m0a.mot`) to variant 1 (`m01232m0l.mot`), which replays. The authored-frame preview has a 1.333333-second opening and a 1.666667-second repeating section. These durations describe the preview clock, not measured native transition timestamps.

Inspect sampled segment and motion times:

```sh
python arika_sequence.py sample SLES_541.61 extracted/ply/p01/p01act.cht samples.json --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 5 --rate 60
```

## Animated model

```sh
python arika_sequence.py animate SLES_541.61 extracted/ply/p01/p01act.cht sequence.gltf --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --model extracted/ply/p01/p01a.mdl --duration 5 --no-blink
```

Duration is required for sampled/exported previews and must be in `(0, 600]` seconds. Rates are 25, 30, 50, 60, 100 or 120. The sibling PIX supplies textures automatically; `--textures` selects another file. Automatic HandAni selection is always included. Negative hand requests retain the last selection across segment changes; a missing HandAni track requests the default hands. Missing named skeletal nodes use the model's rest transform. Geometry and independent skin visibility use the existing exporter.

Add explicit facial starts using the previous timeline feature:

```sh
python arika_sequence.py animate SLES_541.61 extracted/ply/p01/p01act.cht sequence_faces.gltf --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --model extracted/ply/p01/p01a.mdl --ani extracted/ply/p01/p01.ani --events examples/goku_face_events.json --duration 5 --no-blink
```

`--ani` and `--events` must be supplied together. Facial starts preserve the controller's random and phase state, while body segments follow their own preview clock. The supplied facial schedule is a user-authored demonstration, not a recovered gameplay pairing. `--seed` and static `--super-form` are also available. Exported animation extras retain `action_sequence`, its bindings and its timing model. Baked outputs are playback previews, not model-edit import templates.

## Confirmed transitions

The branch-selection prefix of native `0x001D7120` establishes this order:

| Flag | Effect |
| --- | --- |
| `0x20000` | Replay the current segment; takes precedence over stop/jump |
| `0x10000` | Stop sequencing; takes precedence over jump |
| `0x40000` | Jump to zero-based segment index `flags & 0xFF` |
| None of these | Advance to the next record |

The native replay mask also contains `0x100000`, whose advancement can be controlled through `0x001D7580`. That requires runtime context and is rejected by this preview. `0x200000` affects transition blend timing and is likewise unsupported. Root-state flags such as `0x400000` and `0x800000`, other unknown bits and unused low-byte flags are rejected on reachable records. The tool does not silently clear them.

## Preview clock

The newly ported scalar native clock can be inspected separately with `arika_clock.py`; see NATIVE_CLOCK.md. It is not yet connected to complete action-startup and skeletal blending orchestration, so these glTF previews continue to use the convention below.

For a resolved MOT2, start is clamped to `[0, frame_count - 1]`; a negative end selects the last authored frame. Positive end is clamped to the last frame. Reversed ranges are rejected. Speed has the observed native floor of `0.01`.

The preview deliberately gives every authored frame, including the final frame, a complete frame interval:

```text
segment_duration = (end_frame - start_frame + 1) / (fps * effective_speed)
```

Within a segment, motion time advances with speed and holds at its final frame during that final interval. Stopped sequences hold their final pose for the remaining export duration. Cycles use modulo arithmetic, so even a long preview does not enumerate every repeated segment. Exact native float32 startup updates, overshoot carry and blend windows are not modeled. glTF LINEAR channels interpolate the sampled local poses between export ticks; native inter-motion blending is not inferred from that interpolation.

## Verification

All 70 unit tests pass. Six added tests cover transition precedence and rejection, stop/hold, replay, large cycle skips, jump cycles, unreachable unsupported records, clamped ranges, speed flooring, rest-pose fallback and hand retention across segments.

`validate_sequence.py` executes the original ELF's integer branch-selection prefix, including MIPS branch delay slots, and stops before root reset or motion lookup. All 284 supported common-record transitions and 79 synthetic jump/precedence cases match the Python index selection. This validates transitions only, not the preview clock or whole-game execution.

Across 18 supplied character action CHT files, 2,474 of 2,754 common-slot/character combinations produced preview plans. The remaining 280 are reported as absent IDs, absent variants or missing exact-name motions. Native overrides/contextual fallback are not inferred to fill these gaps. Sampling checks include segment boundaries and cycles. See `sequence_validation.json`.

The five-second examples `goku_action_232_sequence.gltf` and `goku_action_232_faces.gltf` include the opening-to-replay path, automatic hands and, in the second file, explicit facial events. The package reader checks all buffers/accessors, finite values, sampler ordering and animation output counts. The Khronos validator was not run in this pass.

Reproduce the audit with optional repeated glTF checks:

```sh
python validate_sequence.py SLES_541.61 extracted sequence_validation.json --gltf examples/goku_action_232_sequence.gltf --gltf examples/goku_action_232_faces.gltf
```
