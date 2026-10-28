# Facial event timelines

You can now start several ANI programs at chosen points in one body-and-hands animation export. This supports aligning facial events to a captured runtime trace or building a preview schedule. Geometry, skeletal motion, hand selection, expressions, texture endpoint switching and optional idle blinks use the existing exporters.

## Delay one program

`sample` and `animate` accept `--face-start` in seconds. Body motion begins at export time zero. Before the facial start, the controller runs its usual idle/blink behavior. For example:

```sh
python arika_faces.py animate extracted/ply/p01/p01.ani delayed.gltf --model extracted/ply/p01/p01a.mdl --motion extracted/ply/p01/p01act.pmt --motion-index 4 --group 0 --program 0 --face-start 0.3 --duration 4 --auto-hands
```

If duration is omitted, the default includes the delay, the program's last authored timestamp, and the existing half-second tail. `--no-blink` makes the idle period neutral. `--super-form` remains a static setting for the whole export.

## Schedule several starts

Create an event file like `examples/goku_face_events.json`:

```json
{
  "format": "ARIKA_FACE_EVENTS",
  "events": [
    {"time": 0.3, "group": 0, "program": 0},
    {"time": 2.0, "group": 1, "program": 0}
  ]
}
```

An optional `source_sha256` binds the schedule to the original ANI bytes. The supplied example includes Goku's reference hash. Group and program indices refer to the same ANI pointer tables used by `json`, `catalog`, `sample`, and `animate`. Programs that share the same on-disk pointer are valid selections.

Export samples as JSON:

```sh
python arika_faces.py timeline-sample extracted/ply/p01/p01.ani examples/goku_face_events.json timeline.json --duration 4 --rate 60
```

Export an animated model:

```sh
python arika_faces.py timeline-animate extracted/ply/p01/p01.ani examples/goku_face_events.json timeline.gltf --model extracted/ply/p01/p01a.mdl --motion extracted/ply/p01/p01act.pmt --motion-index 4 --auto-hands --duration 4 --rate 60
```

The two facial starts and motion index 4 in this example are an explicit demonstration schedule. They do not establish a native gameplay pairing. The example glTF is included as `examples/goku_face_events.gltf`.

## Timing and interruption behavior

Each event starts before the first sample tick at or after its requested time. Both requested and sampled times are recorded in JSON `program_events` and glTF animation extras `facial_program_events`. Events must be ordered, inside the requested duration, and occupy distinct ticks at the selected sample rate. Conflicting same-tick starts are rejected rather than silently discarding a program.

Program starts follow `SLES_541.61` routine `0x001E60A0`: replace the program, reset its event index and clock, and apply the original flag mask. They preserve random-generator state, blink countdown, current pose, and phase state. A new event can therefore interrupt a running expression without constructing a fresh controller. The previous program's remaining events are abandoned. Existing exports with no delay retain their previous sampled poses.

Body motion and automatic HandAni selection continue from their export-time clocks across facial starts. Body selection can use a package index or the CHT ID/variant lookup in MOTION_BINDINGS.md. Goku ID 232 variants 0/1 select m01232m0a.mot / m01232m0l.mot through actual CHT records.

## Native readiness clarification

The voice-event wrapper at `0x001F5810` tail-calls the audio readiness query with channel index 15; its incoming context argument is discarded. It tests state 0/1 in a `0x28` byte channel record, in the table at `0x005D2D00`. The catalog now records this evidence. Elapsed streaming/voice wait time is not stored in ANI, so these tools require an explicit schedule instead of inventing the readiness timestamp.

## Verification

All 58 Python tests passed, including six new tests for delayed starts, preserved controller state, interrupted-program sampling, source/selection validation, tick collisions, and unchanged default playback. Explicit synthetic schedules exercised all 235 ANI group/program references across 18 supplied character files, producing 4,083 checked samples. These schedules test playback robustness, not native gameplay timing.

The supplied four-second Goku example contains 241 samples, body motion `m01210m0.mot`, automatic hands, and starts at 0.3 and 2.0 seconds. All 142 glTF accessors were read back and checked for bounds and finite values; its hierarchy, sampler times and animation output counts were checked through the package reader. This pass did not run the Khronos validator. See `timeline_validation.json`.
