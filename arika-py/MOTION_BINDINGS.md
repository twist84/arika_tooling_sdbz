# CHT action-to-motion bindings

Logical motion IDs and variants now resolve through the companion CHT file to exact RFSM package entries. The CHT variant selects the full stored name, including `a`/`l` suffixes; the tools do not derive the mapping from filename digits.

## Use

For complete supported common-table paths rather than individual motion resolution, use `arika_sequence.py`; see ACTION_SEQUENCES.md. It adds transition planning and offline preview export while keeping native runtime-dependent behavior explicit.

Extract CHT and PMT assets with the normal archive tool. For character actions, bank 0 is the companion action PMT and bank 1 is the shared `ply/p00/p00x.pmt`:

```sh
python arika_cht.py map extracted/ply/p01/p01act.cht goku_motion_map.json --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt
```

Selection/finisher CHT files use their own companion PMT for bank 0. These bank numbers refer to the encoded CHT values, not necessarily absolute runtime registration slots. `json` instead of `map` dumps the CHT without loading motion packages.

Resolve all segments of a common action slot:

```sh
python arika_actions.py resolve SLES_541.61 extracted/ply/p01/p01act.cht action_232.json --slot 232 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt
```

The result retains segment speed, start/end frames, flags, CHT offsets, bank, exact name, package hash and package index. It distinguishes missing CHT entries, missing banks and absent package motions. This inspects common defaults; it does not execute native overrides or complete sequence control flow.

Export by logical motion ID and variant, with automatic hands:

```sh
python arika_actions.py motion-id extracted/ply/p01/p01act.cht motion_232_1.gltf --id 232 --variant 1 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --model extracted/ply/p01/p01a.mdl --duration 2 --no-blink
```

This previews the resolved motion, without applying an action segment's speed/frame range or sequencer flags. Looping remains an explicit `--loop-motion` preview option.

Facial `animate` and `timeline-animate` accept the same lookup in place of `--motion`/`--motion-index`:

```sh
python arika_faces.py timeline-animate extracted/ply/p01/p01.ani examples/goku_face_events.json bound.gltf --model extracted/ply/p01/p01a.mdl --cht extracted/ply/p01/p01act.cht --motion-id 232 --variant 1 --bank 0=extracted/ply/p01/p01act.pmt --bank 1=extracted/ply/p00/p00x.pmt --duration 4 --auto-hands --loop-motion
```

The supplied schedule is an authored demonstration, not recovered gameplay timing. Animation extras record `source_motion_binding` and its hashes. Existing manual-index commands remain available. Unresolved lookups fail before exporting.

## Goku reference results

| Logical ID | Variant | Bank | Exact package entry | Index |
| --- | --- | --- | --- | --- |
| 55 | 0 | 0 | `m01056m0.mot` | 37 |
| 210 | 0 | 0 | `m01210m0.mot` | 4 |
| 232 | 0 | 0 | `m01232m0a.mot` | 40 |
| 232 | 1 | 0 | `m01232m0l.mot` | 39 |
| 233 | 0 | 0 | `m01233m0a.mot` | 18 |
| 233 | 1 | 0 | `m01233m0l.mot` | 19 |
| 235 | 0 | 1 | `m00235m0l.mot` | 106 |

Logical ID 55 demonstrates why filename-number guesses fail. A common action record can also refer to a variant absent from the selected CHT; it remains unresolved instead of being replaced with another variant.

## Native evidence and CHT layout

The lookup chain is `0x1D7870` (read ID and variant from the sequence record), `0x1D74A0`, and `0x2AF5B0` (select a 136-byte CHT variant record). `0x2AF470` loads CHT through `0x2AC930`. `0x1D6DD0` and `0x1B9CF0` bind its names to RFSM entries by exact comparison. `0x1B12F0` copies 15 bytes of the directory name, terminates it and replaces dots with NUL. The Python resolver preserves case, applies this truncation, and uses the first matching package entry.

The supported header version is `0x00010000`, followed by `CHT `. All integers are little-endian. The u32 name count is at `+0x10`; 32-byte CP932 name records begin at `+0x14`. These are followed by 18 u32 presence values. For each value the loader aligns the file cursor to 16 bytes, then consumes a 32-byte block if present. Next is a 4,000-byte runtime pointer workspace; its on-disk contents are ignored and cleared by the loader.

Logical-motion groups continue to EOF: u32 logical ID, u32 variant count, ignored runtime pointer, then contiguous `0x88` byte variant records. IDs address a 1,000-entry table. Duplicate groups use the final occurrence at runtime and in the Python lookup.

| Variant offset | Type | Role |
| --- | --- | --- |
| `0x00` | u32 | Runtime name pointer, rebuilt on load |
| `0x04` | u16 | CHT name index |
| `0x06` | u16 | Resource bank |
| `0x08` | u32[16] | Presence values for 68-byte children |
| `0x48` | u32[8] | Presence values for 12-byte children |
| `0x68` | u32[8] | Presence values for 36-byte children |

After the variant array, each variant's children are visited in this order: 16 possible 68-byte blocks, eight possible 36-byte blocks, then eight possible 12-byte blocks. Each 68/36-byte child is followed by alignment to 16 bytes, then optional 32-byte subblocks. Eight presence values select these at child offsets `+0x24` and `+0x04` respectively. Serialized pointer values are treated as presence flags; they are never followed as file offsets. Every consumed extent is bounds checked. Collision payload meanings remain unimplemented.

`0x1D74A0` has an additional contextual fallback: when runtime resource slot 2 selects a bank-1 record, it retries against the primary CHT. This requires the actual registration context. The tools resolve the explicitly supplied CHT/bank mapping and do not infer that context.

## Verification

All 64 unit tests pass. Six new tests cover nested traversal, malformed input, ignored runtime pointers, duplicate IDs, name handling, bank selection, missing mappings and action metadata retention.

All 43 supplied CHT files parse to exact EOF: 3,931 groups and 8,533 variant references. Companion/common packages resolve 8,525 references. Eight exact-name references remain absent in the p02/p09/p30 action packages and are listed in `cht_mapping_validation.json` without substitutions.

The supplied RAM snapshot independently confirms 916 relocated name pointers and packed bank/name indices: 467 records in loaded `p01act.cht`, and 449 in `p25act.cht`. Reproduce the audit with:

```sh
python validate_cht_mapping.py extracted cht_mapping_validation.json --snapshot stage_stall.bin
```

The optional snapshot must begin with 32 MiB of raw EE RAM. This validates loaded table relocations, not whole-game behavior. Repeated `--gltf file.gltf` arguments add buffer/accessor and animation checks. The new logical-motion and combined facial examples pass with 108/126 accessors and 211/215 animation channels respectively. This uses the package reader; the Khronos validator was not run in this pass.
