# Shared ten-slot companion effects

`arika_menu_companions.py` ports the isolated shared companion pool's spawn, movement, retirement and event-timer rules. The version 10 report adds `shared_companions`: three native templates, slot layout, relevant instruction words and unresolved reset-position addresses. This system is distinct from the six-slot item-3 particles.

```sh
python arika_menu_companions.py SLES_541.61 companions.json --svg companions.svg --rng native --seed 1
python arika_menu_companions.py SLES_541.61 replay.json --random-values examples/menu_companion_random_values.json
python -m unittest discover -p 'test_arika_menu*.py'
```

Native RNG algorithm mode is now the default; see `NATIVE_MENU_RNG.md`. Its seed is an explicit context-state input, with default 1 as a diagnostic choice rather than a recovered game seed. Use `--rng python` for the earlier stream. `--random-values` accepts an array of nonnegative 31-bit integers. Every consumed value and role is recorded. Runtime context state and calls made by other game systems are not inferred.

## Slot and template rules

The pool contains ten 112-byte slots. Spawn scans in index order and uses the first inactive slot. A full pool consumes no spawn random inputs. A successful spawn consumes three inputs: template selection, height, then speed. Template selection is `(value >> 5) % 3`. Height/speed normalization is float32 `(value & 0x7FFF) * float32(1 / 32767)`.

All templates use resource entry 2 and start at X=576:

| Template | UV X,Y,W,H | Base depth | Y base/span | Speed base/span |
|---:|---|---:|---|---|
| 0 | 296, 200, 72, 40 | 86 | 320 / 20 | 0.5 / 0.2 |
| 1 | 368, 200, 144, 80 | 87 | 324 / 28 | 0.7 / 0.3 |
| 2 | 344, 280, 168, 104 | 88 | 352 / 32 | 0.9 / 0.2 |

The table at `0x004A9EA0` uses 28-byte records: four s16 UV fields followed by five floats. Y is base + span times its random fraction. Speed uses a separate random fraction. Final depth is base depth + float32(0.1) times the chosen speed. Decimal values in this table summarize the float32 values preserved in JSON.

Active slots subtract speed from X once per update. They retire only when the result is **strictly below -240**. Inactive slots are skipped. Retirement clears the active flag/speed and resets the sprite. Reset X/Y values at `0x004FC990`/`0x004FC994` have now been verified as zero-fill startup defaults; the CLI uses (0, 0). The standalone slot helper can still represent unknown reset values when no baseline is supplied. See `MENU_STARTUP.md` for the constructor correction and scope.

## Event timer and isolated schedule

The event timer subtracts one. When it reaches zero or below, the code attempts a spawn and resets the timer to 90 + 120 times a further random fraction. The timer input is consumed even when the pool is full; therefore a successful event consumes four inputs, and a full-pool event consumes one.

The default preview starts with empty slots, timer zero and tile phase zero. Each isolated active pass moves/retires slots, processes the timer/spawn event, advances tile phase, then exports active-slot geometry. `--schedule owner` now adds the verified inner owner's entry/active/exit dispatch; see `NATIVE_MENU_OWNER.md`. Outer menu scheduling and native wall-clock frequency remain unresolved.

## Native helpers and validation

| Role | Address |
|---|---|
| First-free pool scan | `0x003766C0` |
| Slot spawn | `0x00376790` |
| Slot movement/retirement | `0x003768D0` |
| Slot draw | `0x00376950` |
| Pool update loop | `0x003765A0` |
| Pool draw loop | `0x00376600` |
| Owner event timer/phase | `0x003761B0` |

Fifty-two menu tests pass, including the added native RNG checks. The scalar interpreter executes the extracted companion helpers under controlled inputs:

- 192 spawn cases compare X, Y, speed, depth, active flag and UV setup.
- 134 slot updates compare movement, strict retirement and reset writes.
- 128 full-pool event-timer cases compare timer/phase values and RNG consumption. The spawn callback is stubbed to represent a full pool in these cases.

Other tests cover first-free selection, no spawn RNG consumption on a full pool, unknown reset positions, input validation and ten-slot SVG visibility timelines. GPU/resource callbacks are stubbed, not fully emulated. Both the port and interpreter use host float32 arithmetic; these checks do not establish PS2 hardware FPU/accumulator bit accuracy or native pixel output.

## Included example

`examples/menu_companion_trace.json` is the retained `--rng python --seed 1` example: 1,800 samples, 9,026 active-slot quads and 52 diagnostic inputs. `examples/menu_companion_random_values.json` contains those inputs alone. Replaying that array reproduced every frame, random-input role and final state. Native-mode examples are documented in `NATIVE_MENU_RNG.md`.

`previews/menu_companions.svg` animates the geometry. Colors identify slots; inactive slots are hidden. New sprites begin offscreen at X=576, so the first static sample may be empty. A later sample was rendered for visual inspection. Interactive browser playback remains untested here. The displayed 60 ticks/s and sample stride 15 are authored preview settings, not recovered game timing.

Textures, alpha, viewport clipping, depth compositing, global RNG synchronization and complete menu-state integration remain outside this preview.
