# Native RNG used by the menu

The 64-bit RNG at `0x00190450` is ported in Python (`arika_menu_rng.py`) and portable C++03 (`arika_menu_rng.h`). The version 11 report includes its instructions and multiplication helper under `native_rng`.

```
state = (state * 0x5851F42D4C957F2D + 1) modulo 2^64
result = (state >> 32) & 0x7FFFFFFF
```

The result is a nonnegative 31-bit integer. The new state is stored before the result is extracted. Both ports preserve all 64 state bits using integer arithmetic.

## Companion exporter

Native RNG mode is now the default. The seed is an explicit context-state input; default 1 is an authored diagnostic choice, not a recovered game seed.

```sh
python arika_menu_companions.py SLES_541.61 native.json --rng native --seed 0x1 --svg native.svg
python arika_menu_companions.py SLES_541.61 old_python.json --rng python --seed 1
python arika_menu_companions.py SLES_541.61 replay.json --random-values examples/menu_companion_native_random_values.json
python -m unittest discover -p 'test_arika_menu*.py'
```

`--seed` accepts decimal or Python-style hexadecimal notation. Native seeds must fit an unsigned 64-bit integer. `--rng python` retains the earlier diagnostic stream. A recorded-input file takes precedence over either generator.

New companion traces use format version 2 and include `rng_state.initial`/`final` in native mode. Those fields describe RNG state only: starting another export at the final RNG state does not resume the companion pool or owner animation. Every consumed result and role remains recorded in `random_draws`.

Python exposes `next_rng(state)` and `c_native_rng(state)` with `next()`/`get_state()`. The C++03 header exposes `c_menu_rng` with the same explicit-state constructor and operations, without STL dependencies.

## Context and synchronization

The routine loads an active context pointer from `0x00462C50`, then reads/writes its state at context +0xA8. The exporter does not infer the active runtime context, its state, or calls by other game systems. An explicit state and identical call sequence produce identical results; native algorithm support alone does not synchronize the menu with a captured game run.

## Validation

Fifty-two menu tests pass. A separate integer interpreter executes the complete native RNG, including its call to multiplication helper `0x00195E08`:

- 1,024 operand pairs validate the helper's unsigned 64-bit low product.
- 1,536 RNG steps compare Python output and full state against interpreted native instructions, across 96 starting states.
- The C++03 header is compiled and compared against 256 native results/states.

The interpreter implements the integer shifts, sign extensions, 32-bit multiplies, MULT1 destination behavior, HI/LO reads, loads/stores and delay slots. It does not substitute the high-level 64-bit recurrence for the multiplication helper. No floating-point approximation is involved in this RNG. These are interpreted-instruction comparisons, not execution on PS2 hardware.

## Examples

`examples/menu_companion_native_trace.json` uses native mode with seed 1: 1,800 samples, 8,559 quads and 48 RNG results. Its final RNG state is `0xFD157D8D36B9C4D1`. The SVG is `previews/menu_companions_native.svg`.

Replaying `examples/menu_companion_native_random_values.json` reproduced every frame, recorded role/value and final companion state. The older Python example is retained; `--rng python --seed 1` reproduces its frames and final companion state.

The SVGs remain geometry diagnostics with authored display rates and no textures/alpha/compositing. Interactive browser playback remains untested here. Runtime positions, owner startup/exit states and global RNG synchronization remain separate work.
