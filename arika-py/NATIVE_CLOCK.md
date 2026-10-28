# Native segment clock research

`arika_clock.py` ports the scalar MOT2 player clock from the European beta's `0x001B9690` setup and `0x001B84A0` update paths. It exposes the timing state, unused delta carry, loop-gap interpolation factor and scalar blend countdown coefficient. This is a separate trace tool; existing action glTF previews retain their documented authored-frame timing model.

## Trace a mapped motion

```sh
python arika_clock.py extracted/ply/p01/p01act.cht clock.json --id 232 --variant 0 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 2 --rate 60 --blend 0.17
```

CHT selection uses the existing exact ID/variant/bank mapping. The trace records the motion/package hashes, FPS, frame count, setup parameters and one snapshot per tick. Tick zero is the state immediately after fresh segment setup, including its special initialization update if applicable. It is not a snapshot of the native action handler's full startup sequence.

Options include `--start-frame`, `--end-frame`, `--speed`, `--blend`, `--stop-after`, `--reverse`, and `--loop`. `--duration` is required and bounded to `(0, 600]`; rates are 25, 30, 50, 60, 100 or 120. Input files are protected from output-path aliases.

## Recovered scalar behavior

- Intermediate arithmetic is rounded to float32. FPS is stored as float32 before computing its reciprocal. Speed has the native float32 floor of 0.01.
- Start is clamped to the authored range; a negative end chooses `frame_count - 1`. Reversed ranges are rejected.
- The forward setup baseline is one frame period before start. Reverse setup is one frame period after end. A normal first tick moves from this baseline; the full action handler may perform additional startup updates outside this isolated clock.
- Non-looping forward motion stops when its time reaches or exceeds end; reverse stops at or below start. It clamps the position and returns excess time divided by speed, in the caller's delta-time units. Once inactive, it returns the input delta unchanged.
- Active paused/nonpositive-delta updates do not advance and return zero carry. Inactive handling takes precedence over pause.
- Looping uses the stored baseline to include the boundary frame interval. The native subtraction/addition loop is reproduced with a guard against unrepresentable or excessive iteration. Time can lie in the short gap before start or after end; `wrap_fraction` records the native end/start interpolation coefficient. `sample_time` alone is clamped and does not reconstruct that blended pose.
- `--stop-after` controls the native field at player offset `+0x14`: positive values are a countdown in scaled motion time. Expiry truncates that update's motion delta and returns the unused time. Negative values disable this countdown. A value of zero triggers the initializer's immediate frame-period update, rather than acting as an immediate stop.
- A positive blend countdown at `+0x1C` decreases by scaled motion time. Its coefficient is float32 `1 - remaining / total`, becoming 1 when the remaining time is nonpositive. The native code can retain a negative countdown after expiry; the trace preserves it. If playback stops during a blend, the stored counter/coefficient can remain incomplete while the clock is inactive.
- The initializer also performs an immediate frame-period update when end equals start. The trace includes this as `initialization_tick`. Fresh setup is supported; reusing an existing player with preserved blend history is outside this tool's model.

The trace's flags belong to the low-level MOT2 player. In particular, MOT2 clock `0x10000` means loop and `0x20000` means reverse. These are distinct from identically numbered flags in the outer action-sequence records.

## Blend scope

The scalar coefficient at `0x001B8C34..0x001B8C44` is verified. Per-bone helper structure is now available separately in `arika_pose.py`; see NATIVE_POSE.md. A scalar coefficient trace alone is not a complete native skeletal blend.

Callback motion lists, root-motion accumulation, IK and hardware FPU quirks remain outside this isolated clock. `arika_action_clock.py` now connects the supported common-action control/startup subset to scalar carry and blend inheritance; see ACTION_STARTUP.md. Full action pose/callback orchestration and the existing action exporter remain separate.

## Verification

All 78 tests pass. Eight added tests cover baseline/first tick, carry units, reverse, loop-gap fractions, scaled blend countdown, timed stop, pause/inactive precedence, special initialization updates and invalid setup.

`validate_native_clock.py` interprets the original ELF timing instructions with IEEE float32 operations and MIPS delay slots. It stops before the pose backend and compares position, stop timer, blend remaining, flags, unused carry and wrap coefficient bit-for-bit. The blend coefficient arithmetic is separately executed from the original divide/subtract instructions. Terminal/dirty flag cleanup is modeled from the subsequent code with callbacks absent.

The audit covers 4,444 steps across 456 setup combinations plus repeated-loop and early-exit checks. All compared fields match. Random cases use a fixed seed and include fractional frame ranges and noninteger FPS/speeds. This is an instruction-interpreter comparison, not a PS2 hardware capture or complete R5900 FPU emulator. The initializer translation is inspected and unit tested separately; this prefix oracle does not execute the full initializer.

```sh
python validate_native_clock.py SLES_541.61 native_clock_validation.json
```

See `native_clock_validation.json` and the reference traces `examples/goku_motion_232_native_clock.json` and `examples/goku_motion_232_reverse_clock.json`.
