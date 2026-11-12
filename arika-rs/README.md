# arika-rs

Rust rewrite of the **Super Dragon Ball Z** (SLES-541.61 / Arika) INFO.DAT / GAME.DAT toolkit.

## Crates

| Crate          | Purpose |
|----------------|---------|
| `arika_core`   | Formats + glTF export with embedded PNG textures |
| `arika_cli`    | `arika` CLI |
| `arika_editor` | Bevy viewport + egui; **load FMDL/PIX into the 3D scene** |

## Build

```bash
cargo build -p arika_core -p arika_cli
cargo build -p arika_editor   # needs GPU deps / larger download
```

## CLI

```bash
arika list|extract|info|rebuild …
arika model-json|model-obj|model-gltf path.mdl out […]
arika motion-json|stg-json|hit-json|hit-obj|texture-ppm|face-json …
```

`model-gltf` now embeds TIM2/XPIX textures as PNG data-URIs and wires `baseColorTexture` on materials.

## Editor

```bash
cargo run -p arika_editor
```

1. Enter FMDL (+ optional PIX) → **Load model**  
2. Or enter STG (+ MDL/PIX) → **Load stage** (places kind-2 mesh instances)  
3. Select in outliner → edit T/R/S in Properties → **Apply transform**  
4. Axis helpers draw on the selection; camera frames bounds  
5. MMB orbit · Shift+MMB pan · +/- zoom · Home reset  

`arika stage-gltf s01a.stg out.gltf` exports MDL geometry with instance list in extras.


## INFO.DAT record capacity and US disc layout

The original US SLUS_214.42 archive contains 1,930 active entries in a
98,304-byte (0x18000) INFO.DAT. Both the header and each record are 48 bytes:

```text
INFO.DAT = 48-byte header + 2,047 x 48-byte record slots
         = 98,304 bytes
active   = 1,930 entries (header count at 0x2C)
spare    = 117 record slots (5,616 bytes of encoded 0x40 padding)
```

A published PCSX2 boot log shows Arika's IOP driver reporting
`File Len : 2047`, which matches the table's physical capacity:
https://forums.pcsx2.net/Thread-PCSX2-Widescreen-Game-Patches?page=393

**Important:** `ARKD_DVD.IRX` has not been disassembled to verify what
`File Len` represents. It is unknown whether 2,047 is a hard-coded limit,
a value derived from the INFO.DAT length, or something else. Spare record
slots are *potential* capacity, not proof that the game accepts added assets.
The tooling does **not** impose a global 2,047-entry limit.

The CLI `arika info INFO.DAT` now reports active entries, the number of
complete record slots, unused slots, and any non-record trailing bytes.
This is a layout calculation, **not** a loader compatibility check.

### Seedless rebuild policy

For `--version usa`, seedless CLI builds now default to a 98,304-byte
INFO.DAT with encoded `0x40` padding. This preserves the observed US
table extent even if fewer than 2,047 records are active:

```bash
arika rebuild --assets extracted --version usa \
  --out-info rebuilt/INFO.DAT --out-game rebuilt/GAME.DAT \
  --game-size 732073984
```

`--compact-info` explicitly requests a minimal INFO.DAT. `--info-size N`
overrides the default capacity and can be larger than 98,304 if testing
more than 2,047 records; an undersized capacity is rejected. These options
apply only to seedless builds. Other regions and custom codec keys retain
their existing minimal default until their loader behaviour is verified.

The original US GAME.DAT is 732,073,984 bytes. Its indexed extent is
695,373,824 bytes, leaving 35 MiB of zero-filled reserve. This remains
**optional** via `--game-size 732073984`; by default seedless GAME.DAT
uses the minimum required size. A seed-based rebuild already preserves
the seed's INFO and GAME file sizes.

### Emulator verification still needed

1. Boot the original disc and record `File Len : 2047`.
2. Boot a rebuilt disc with `--compact-info` (1,930 entries); check whether
   the log changes to `File Len : 1930` or remains 2,047.
3. Add a 1,931st asset, update the table, and exercise an actual loader
   lookup. Merely parsing an extra record in this toolkit is insufficient.
4. Test the 2,047/2,048 boundary before declaring a hard limit.

Full-size files still require game-side validation. Matching lengths alone
does not guarantee byte-identical record ordering or runtime compatibility.
The GUI/frontend is maintained in `arika-py_on_rs`; the standalone Rust
editor is legacy.

## Implemented

- INFO/GAME archive (extract + rebuild)
- FMDL geometry, hierarchy, skinning, materials
- FPIX/TIM2 decode + **PNG encode**
- **glTF with embedded textures**, skins, animations
- RFSM/MOT2, STG, HIT, facial ANI
- **Bevy FMDL loader** (meshes + textures + outliner)

## Still open

- Full facial morph/texture endpoints in glTF animations
- Menu reconstruction, audio
- Interactive drag gizmos / undo stack (panel Apply transform is available)
- Hierarchical STG parent transforms (kind-2 instances are placed)


Docs from the original research: `docs/`.

## Validation

```bash
cargo test -p arika_core --test validate_assets
```

Uses real EU-beta `INFO.decoded.bin` (1934 entries) + `files.json`, plus synthetic TIM2/XPIX/HIT/STG/MOT2 fixtures.

Verified:
- Full INFO encode↔decode byte-identical roundtrip (98,304 bytes)
- All 1934 entry names/sectors/sizes match `files.json`
- Used region 693,350,400 bytes (matches archive research)
- CLI `arika info` / `list` on re-encoded INFO.DAT

FMDL/PMT/real STG payloads need a GAME.DAT extract (not shipped in the tools package).
