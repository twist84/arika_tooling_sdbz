# Common-action startup and clock chaining

`arika_action_clock.py` resolves a common action table through CHT and advances its scalar clock automatically. It follows supported advance, replay, stop, and jump records, forwards wall-time carry to the next clock, and preserves or resets the blend countdown according to recovered startup arguments. No authored switch schedule is required.

This is a scalar research tool. Skeletal integration is now available separately through `arika_action_player.py`; see ACTION_POSES.md. It uses common defaults; character-specific table overrides, gameplay callbacks, contextual binding, root transforms, and full action execution remain unported.

## Commands

```sh
python arika_action_clock.py plan SLES_541.61 extracted/ply/p01/p01act.cht startup_plan.json --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt
python arika_action_clock.py sample SLES_541.61 extracted/ply/p01/p01act.cht action_clock.json --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 5 --rate 120 --initial-blend 0.17
```

`plan` records each reachable segment once, its resolved motion binding, and outgoing control behavior. `sample` additionally records clock snapshots and startup events, including carry-in and the raw initializer settings. Duration must be in `(0,60]` seconds; rates are 25, 30, 50, 60, 100, or 120 Hz. A sample at the first tick on or after the requested duration is included.

The initial blend belongs to caller context, so `--initial-blend` is explicit and defaults to zero. Later settings are recovered from the common action records. The supplied five-second `examples/goku_action_232_native_clock.json` uses an initial blend of 0.17 and follows ID 232 variant 0 into repeated variant 1. Its startup events include the float32 carry passed between clocks. These are simulated clock values, not measurements from an in-game capture.

## Recovered startup rules

Native `0x1D7120` selects the next common record. Its call at `0x1D737C` passes through wrapper `0x1D7470` into initializer `0x1B9690`.

| Initializer input | Recovered value |
| --- | --- |
| Motion index | Low 16 bits of the resolved CHT binding |
| Resource selection | Resolved bank, with native caller-context arithmetic |
| Speed | Incoming common record `speed` |
| Start/end frame | Incoming common record `start_frame` / `end_frame` |
| Stop timer | -1 |
| Initializer flags | 0 |
| Blend request | -1, or float32 0.17 under the outgoing flag rule below |

Replay (`0x20000`) takes precedence over stop (`0x10000`), which takes precedence over jump (`0x40000`, low byte target), otherwise advancing to the next record. For an advancing or jumping outgoing record, `0x200000` changes the incoming blend request to float32 0.17. Replay and stop bypass that reset even if the bit is also present.

An initializer blend request below zero keeps both the existing total and remaining countdown. It does not restart a new blend of that length. A nonnegative request assigns both fields to the requested value. `c_native_clock` now accepts an optional `inherited_blend=(total, remaining)` to express this behavior before any special setup update.

The initializer clears the previous-motion bridge pointer. Consequently, common-action startup must not automatically reuse the outgoing/incoming first-frame bridge policy from the explicitly authored transition tool. This scalar tool records that clear but does not evaluate poses.

After startup, native `0x1D73A8` sends the outgoing clock's unused wall-time carry to the new clock. With zero carry the new clock stays at its baseline until a later positive tick. A large delta can cross several clips or replay periods; the tool iterates those transitions and limits one update to 4,096 startups. Terminal stop holds the final clock state and returns unused time.

## Supported subset

Reachable records may use only advance/replay/stop/jump and the `0x200000` blend-request bit. Other flags, including context-dependent `0x100000` and root-state flags, are rejected. Fall-through past the table, invalid jumps, unresolved exact-name CHT references, and zero-range setup are rejected. The latter invokes a special initializer update whose interaction with the high-level action caller still needs tracing. The standalone native clock continues to support its isolated zero-range case.

Native motion-list callbacks, table overrides, resource-context fallback, root accumulation and full special-node behavior are not reconstructed by this clock chain. `arika_action_player.py` now connects the supported chain to local poses, evaluating the outgoing pose before common startup and applying each positive carry update. The authored-frame sequence exporter and explicit-switch exporter retain their documented behavior.

## Verification

All 117 unit tests pass. Thirteen action-clock tests cover startup record inputs, zero/positive carry, blend inheritance/reset, transition precedence, multiple replays per delta, terminal stop, unsupported context flags, zero-range rejection, initializer ordering, and automatic sampling without switch times.

`validate_action_clock.py` executes the original R5900 control/startup prefix and wrapper, stopping at the initializer entry. A successful CHT lookup is stubbed to bank 1 / index 7; the checks verify lookup ID/variant, selected record, raw float arguments, flags, bank, and resource-pointer arithmetic. There are 285 matching common cases and 158 synthetic cases, including blend-request precedence combinations. A separate initializer-prefix interpreter checks 36 inheritance/reset combinations and the previous-reference clear. Root stores may be executed along the path but their semantic correctness is not part of the comparison.

The scalar clock's existing instruction audit still passes 4,444 steps. These independent prefix checks and unit tests do not establish whole-chain equivalence to native gameplay. They use the reference ELF and the documented host IEEE float32 model, not a PS2 hardware capture. See `action_startup_validation.json` and `native_clock_validation.json`.

```sh
python validate_action_clock.py SLES_541.61 action_startup_validation.json
python validate_native_clock.py SLES_541.61 native_clock_validation.json
python -m unittest discover -s .
```
