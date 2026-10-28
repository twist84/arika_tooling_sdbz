# Python ↔ Rust parity tracker

The Python tools remain the behavioral reference until each row has a matching
fixture-based test in Rust. Avoid replacing Python behavior with a cleaner but
incompatible interpretation of an undocumented format.

## Archive behavior

| Behavior | Python reference | Rust status |
|---|---|---|
| INFO.DAT decode/encode | `arika_dat.py:decode_info`, `encode_info` | Implemented; byte-identical fixture roundtrip tested |
| Entry table validation | `Archive.__init__` | Implemented; real INFO fixture validates 1,934 entries |
| Unsafe paths | `relative_name`, `asset_path` | Lexical traversal and existing-symlink containment checks implemented for extraction |
| Extraction matching | `extract` / `fnmatch.fnmatchcase` | Case-sensitive `*` / `?`; extraction preflights all selected outputs before writing |
| Existing extraction targets | Fail unless `overwrite=True` | Now matches Python instead of silently skipping existing files |
| Rebuild layout | `rebuild` | Now plans entries in table order and compacts from sector zero |
| Replacement sizes | `rebuild` | Updates sector, sector count and size; rejects >32-bit size and capacity overflow |
| Allocation padding | `rebuild` | Retains old padding only when size and allocation are unchanged; otherwise zero-fills |
| GAME.DAT trailing reserve | `rebuild` | Preserves original file capacity and copies bytes after the compacted indexed region |
| Output safety | `rebuild` | Rejects output paths that resolve to either input archive |
| Round-trip / replacement tests | `test_arika_dat.py` | Rust unit coverage now checks extraction, byte-identical unchanged rebuild, changed payload size, retained GAME.DAT capacity/trailing bytes, source immutability and capacity overflow |

## Remaining format / feature parity

Rust core currently has modules for archive/container parsing, FMDL models,
TIM2/XPIX textures, MOT2/RFSM motion, STG/HIT stages, facial ANI, glTF and
ASE/AMS audio. Python also has dedicated modules for scene-project editing,
menu reconstruction and animation, action sequencing/clock/player, script and
transition tooling, face baking/playback, audio import, and WebGPU math/rendering.
Those features should be ported by behavior group, with the Python tests used as
the specification. Each group should get shared golden JSON/binary fixtures and
Rust tests before being marked complete.

## Validation commands

```sh
python -m unittest discover -s ../arika-py -p 'test_*.py'
cargo test -p arika_core
cargo test -p arika_core --test validate_assets
```

Run the Python suite and Rust suite against the same extracted asset set before
claiming parity. This archive did not include a full extracted GAME.DAT payload,
so real-world model/stage parity still needs local asset validation.

## Shared golden fixtures (2026-10-28)

`arika_core/tests/fixtures/parity_fixtures.json` is the shared semantic baseline
for both languages. The Python suite reads it in
`arika-py/test_arika_rust_parity.py`; Rust reads the same file in
`arika_core/tests/validate_assets.rs::shared_python_rust_parity_manifest`.
The fixture set covers STG hierarchy/transforms, HIT object and polygon counts,
MOT2 timing and track samples, and TIM2 dimensions plus decoded RGBA bytes.

The synthetic STG and MOT2 binary fixtures were corrected to satisfy the
Python reference parser's structural validation. This matters: a Rust parser
accepting a fixture that Python rejects is not parity. Keep fixtures valid for
both parsers and update the shared manifest only when the intended behavior
changes.

Windows CMD validation from `arika-rs`:

```bat
python -m unittest discover -s ..\arika-py -p "test_*.py"
cargo test -p arika_core
cargo test -p arika_core --test validate_assets
```

## Archive regression tests (2026-10-28)

The Rust `dat.rs` tests now exercise the full archive path on a synthetic fixture:

- Extract an entry into a nested directory and compare its payload.
- Rebuild an unchanged archive and compare INFO.DAT and GAME.DAT byte-for-byte.
- Replace an entry with a larger payload, reopen the result, and check the size metadata and payload.
- Verify GAME.DAT capacity and trailing reserve bytes remain unchanged.
- Verify the input archive pair is not modified.
- Reject replacements that exceed the original GAME.DAT capacity without creating outputs.

Run these alongside the existing Python `test_arika_dat.py` tests. A passing Rust-only test is not evidence of cross-language parity until both suites pass on the same fixture.


## Extraction path containment (2026-10-28)

Rust extraction now canonicalizes the destination root and checks existing path components before writing. This closes the case where an otherwise-safe entry such as `redirect/file.bin` could escape through a pre-existing symlink inside the extraction directory. A Unix-only regression test covers the symlink case. The root directory is created before output preflight, but no asset payload is written unless every selected target passes validation.
