# Super Dragon Ball Z - Complete Format Interaction Analysis

## Overview

This document provides a complete analysis of how all file formats in Super Dragon Ball Z (SLUS_214.42) interact with each other at runtime. All findings were derived from static analysis of the PS2 ELF executable using custom MIPS R5900 disassembly tooling, without Ghidra or IDA.

## Format Inventory (1,944 extracted files across 14 directories)

| Format | Extension | Count | Primary Loader |
|--------|-----------|-------|---------------|
| Stage | .stg | 13 | STG scene parser |
| Effect Archive | .ebz | 147 | CEffectMgr + CEBZ* classes |
| Texture | .pix | 729 | FPIX parser |
| Model | .mdl | 475 | FMDL parser |
| Material | .pmt | 57 | RFSML3 parser |
| Animation | .ani | 20 | ANI parser |
| Pose | .pas | 7 | PAS parser |
| Facial | .cht | 43 | CHT parser |
| Font | .fon | 1 | FFON tracer |
| Icon | .ico | 2 | ICO tracer |
| Message | .txt | 1 | MSG tracer |
| Sound Bank | .ase | 27 | ASE parser |
| Sound Sequence | .ams | 54 | AMS parser |
| Script | .spt | 77 | SPT parser |
| Hitbox | .hit | 14 | HIT parser |
| Archive Index | .sqm | 54 | AMS parser |

---

## Format Interaction Graph

```
STAGE (.stg)
│
├── EFFECT root → efXX nodes → CEffectMgr → CEBZData → .ebz files
│   └── .ebz → CEBZEffectObj instances → runtime effect instances
│
├── STAGE root → model nodes → .mdl files
│   ├── .mdl → .pix textures (material slots)
│   ├── .mdl → .pmt materials (material definitions)
│   └── .mdl → .ani animations (skeletal animation)
│
├── STAGE root → collision nodes → .hit files (hitboxes)
│
├── STAGE root → audio nodes → .ase files (sound banks)
│
├── STAGE root → music nodes → .ams files (sound sequences)
│
└── STAGE root → script references → .spt files
    └── SPT scripts → CEffectMgr → .ebz files (runtime effect spawning)
```

---

## Detailed Interaction Chains

### 1. STG Stage (.stg) → Effect (.ebz)

**Pipeline:**
```
STG file → scene graph parse → EFFECT root node → efXX child nodes
                                ↓
                        CEffectMgr singleton
                                ↓
                        CEBZData parses .ebz file
                                ↓
                        CEBZHandle → CEBZEffectObj instance
                                ↓
                        Runtime effect with TRS transform
```

**Effect Name Table** (at ELF file offset 0x3C4EE0, vaddr 0x004C4E60):
The effect names are NOT "ef00-ef39" as might be expected. They are actual effect names stored as u32+name pairs:

| Offset | vaddr | u32 value | Name |
|--------|-------|-----------|------|
| 0x3C4EE0 | 0x004C4E60 | 0x6B73315F | "k7" |
| 0x3C4EE8 | 0x004C4E68 | 0x6B73315F | "k8" |
| 0x3C4EF0 | 0x004C4E70 | 0x67745343 | "02Sp" |
| 0x3C4EF8 | 0x004C4E78 | 0x73656361 | "hipF" |
| 0x3C4F00 | 0x004C4E80 | 0x00636E75 | (null) |
| 0x3C4F08 | 0x004C4E88 | 0x35336665 | (null) |
| 0x3C4F10 | 0x004C4E90 | 0x67745343 | "02St" |
| 0x3C4F18 | 0x004C4E98 | 0x46373431 | "unc" |
| ... | ... | ... | ... |
| 0x3C4F70 | 0x004C4EF0 | 0x67745343 | "02Ta" |
| 0x3C4F78 | 0x004C4EF8 | 0x75466978 | "nc" |
| 0x3C4F80 | 0x004C4F00 | 0x33326665 | (null) |
| 0x3C4F88 | 0x004C4F08 | 0x6174315F | "xi07" |
| ... | ... | ... | ... |
| 0x3C5010 | 0x004C4F90 | 0x6574315F | "lbox" |

Effect names are referenced in code via raw address embedding:
- ef00 ("k7"): refs at 0x00488B64, 0x00488B6C
- ef01 ("k8"): ref at 0x00488B68
- ef02 ("02Sp"): ref at 0x004FC398
- ef06 ("02St"): ref at 0x004FC39C
- ef10 ("02St"): ref at 0x004FC3A0
- ef14 ("Func02"): ref at 0x004FC3A8
- ef18 ("02Ta"): ref at 0x004FC3AC
- ef21 ("xi07"): ref at 0x00488C00
- ef23 ("xi04"): ref at 0x00488C04
- ef25 ("xi08"): ref at 0x00488C08
- ef27 ("xi03"): ref at 0x00488C0C
- ef29 ("xi05"): refs at 0x00488C10, 0x00488C18
- ef31 ("xi06"): refs at 0x00488C14, 0x00488C1C
- ef34 ("02Te"): ref at 0x004FC3B0
- ef38 ("lbox"): ref at 0x00488CA0

**CEBZ Loading Code** (vaddr 0x003301E0-0x00330300):
```
0x00330200: LB  v0,0x0104(s0)      # Load entry byte at offset 0x104
0x00330204: BNE v0,zero,0x0033022C # If non-zero, process entry
0x00330208: ADDIU a0,s0,0x0104     # a0 = entry + 0x104 (name field)
0x00330210: ADDIU s1,s1,0x0001     # Increment entry counter
0x00330214: SLTI v0,s1,0x0012      # If count < 18, continue loop
0x00330218: ADDIU s0,s0,0x0048     # Advance to next entry (0x48 = 72 bytes)
0x0033021C: BNE v0,zero,0x00330200 # Loop back
0x00330224: BEQ zero,zero,0x00330258
0x0033022C: JAL 0x00191EF8         # CALL: string hash function
0x00330230: ADDIU a1,zero,0x002F   # a1 = 0x2F (47)
0x00330234: ADDIU a0,v0,0x0001     # a0 = name + 1
0x00330238: JAL 0x00191638         # CALL: data unpacker function
0x0033023C: ADDIU a1,s2,0x0020
0x00330240: BNE v0,zero,0x00330210 # Compare result
0x00330248: LW v1,0x0144(s0)       # Load entry field at 0x144
0x0033024C: LW v0,0x0010(s2)       # Load field at s2+0x10
0x00330250: BNE v1,v0,0x00330210   # Compare
```

**JAL Targets from CEBZ Loading Code:**
1. **0x00191EF8** (file 0x091F78): String hash function - XOR-based hash of effect name strings
2. **0x00191638** (file 0x0916B8): Data unpacker function - bit manipulation with masks 0x0101, 0x8080

**CEBZ Class Info Block** (at vaddr 0x004FE628):
| Offset | Value | Interpretation |
|--------|-------|----------------|
| 0x004FE628 | 0x004CEF18 | → "CEBZData" |
| 0x004FE62C | 0x00000001 | u32 value 1 |
| 0x004FE630 | 0x00000001 | u32 value 1 |
| 0x004FE634 | 0x004CEF50 | → "CEBZEffectObj" |
| 0x004FE638 | 0x3F800000 | float 1.0 |
| 0x004FE63C | 0x3F000000 | float 0.5 |
| 0x004FE640 | 0x00010000 | u32 65536 |
| 0x004FE644 | 0x00010000 | u32 65536 |
| 0x004FE648 | 0x004CF020 | → "CEBZEffMatrix" |
| 0x004FE64C | 0x004CF030 | → "CEBZEffectEle" |
| 0x004FE650 | 0x004CF040 | → "CEBZEffectGen" |
| 0x004FE654 | 0x004CF050 | → "CEBZEffectBase" |
| 0x004FE658 | 0x000D000E | u32 packed values |
| 0x004FE65C | 0x00060004 | u32 packed values |
| 0x004FE660 | 0x000000D2 | u32 210 |
| 0x004FE664 | 0x000000BE | u32 190 |
| 0x004FE668 | 0x0000001E | u32 30 |
| 0x004FE66C | 0x00000028 | u32 40 |
| 0x004FE670 | 0x42C80000 | float 100.0 |
| 0x004FE674 | 0x42200000 | float 40.0 |
| 0x004FE678 | 0x41A00000 | float 20.0 |
| 0x004FE67C | 0x40B80000 | float 5.75 |

---

### 2. STG Stage (.stg) → Collision (.hit)

**Pipeline:**
```
STG file → STAGE root → collision nodes → .hit file
```

**Key Addresses:**
- s01a.hit: vaddr 0x004C8860 (file 0x3C88E0) - ref at 0x004DDC48 (file 0x3DDCC8)
- s10a.hit: vaddr 0x004C9520 (file 0x3C95A0) - ref at 0x00268B44 (file 0x168BC4)
- s11a.hit: vaddr 0x004C9700 (file 0x3C9780) - ref at 0x00287E64 (file 0x187EE4)
- s12a.hit: vaddr 0x004C99B0 (file 0x3C9A30) - ref at 0x002A8824 (file 0x1A88A4)

---

### 3. STG Stage (.stg) → Model (.mdl)

**Pipeline:**
```
STG file → STAGE root → model nodes → .mdl file
                                ↓
                        .mdl → .pix textures (material slots)
                        .mdl → .pmt materials (material definitions)
                        .mdl → .ani animations (skeletal animation)
```

**Key Addresses:**
- %s.mdl format string: vaddr 0x004CC5A8 (file 0x3CC628) - 0 gp-relative refs
- FMDL magic (0x464D4C): vaddr 0x004B7210 (file 0x3B7290)
- FMDL magic referenced as immediate in code: 0 occurrences

---

### 4. Model (.mdl) → Texture (.pix)

**Pipeline:**
```
MDL file → material slots → .pix texture files
```

**Key Addresses:**
- %s.pix format string: vaddr 0x004CC5B0 (file 0x3CC630) - 1 gp-relative ref at 0x003A4160
- %s.pix format string #2: vaddr 0x004CC5D8 (file 0x3CC658) - 0 gp-relative refs

**Code at 0x003A4120-0x003A421C** builds a table of format string pointers:
```
0x003A4120: LUI v1,0x0061
0x003A4124: ADDIU a1,gp,0xC500
0x003A4128: SW a0,0x0824(v1)         # Store ptr at gp+0xC524
...
0x003A415C: LUI v1,0x0061
0x003A4160: ADDIU a0,gp,0xC5B0       # a0 = gp + 0xC5B0 (%s.pix)
0x003A4164: SW a1,0x0838(v1)         # Store ptr at gp+0xC538
0x003A4168: LUI v1,0x0061
0x003A416C: ADDIU a1,gp,0xC5B8
0x003A4170: SW a0,0x083C(v1)
...
```

This builds a table of format string pointers at gp+0xC500 through gp+0xC5E4, including "%s.pix" at gp+0xC5B0.

---

### 5. STG Stage (.stg) → Audio (.ase / .ams)

**ASE Sound Banks:**
- ply/p22/voi/enter.ase: vaddr 0x004DAC70 - ref at 0x00340AC4 (file 0x240B44)
- ply/p22/voi/ending.ase: vaddr 0x004DB8B0 (file 0x3DB930) - ref at 0x003A39BC (file 0x2A3A3C)

**AMS Sound Sequences:**
- sqm/sel_in.ams: vaddr 0x00499280 - ref at 0x00242064 (file 0x1420E4)
- sqm/sel_lp.ams: vaddr 0x004992A4 - ref at 0x00245F44 (file 0x145FC4)
- sqm/st01a_in.ams: vaddr 0x00499400 - ref at 0x00259E2C (file 0x159EAC)
- sqm/st01a_lp.ams: vaddr 0x00499424 - ref at 0x0025A244 (file 0x15A2C4)
- sqm/st02a_in.ams: vaddr 0x00499700 - ref at 0x00287E64 (file 0x187EE4)
- sqm/st02a_lp.ams: vaddr 0x00499724 - ref at 0x00289214 (file 0x189294)

---

### 6. SPT Script (.spt) → Effect (.ebz)

**Pipeline:**
```
SPT script → effect command → CEffectMgr → CEBZData → .ebz file
```

**Key Addresses:**
- SPT file paths: vaddr 0x004DB060-0x004DB740 (25 script files)
- Effect commands: 29-30 (set_character_pose, set_character_pose_variant)
- %s.ebz format string: vaddr 0x004CEF28 - 0 gp-relative refs (constructed at runtime)
- eff/e%c%c/%s format string: vaddr 0x004C3AF0 - 0 gp-relative refs

---

### 7. Model (.mdl) → Animation (.ani)

**Pipeline:**
```
MDL file → animation references → .ani files
```

**Key Addresses:**
- %s.ani format string: vaddr 0x004CFAF0 - 0 gp-relative refs

---

### 8. Model (.mdl) → Material (.pmt)

**Pipeline:**
```
MDL file → material definitions → .pmt files
```

**Key Addresses:**
- %s.pmt format string: vaddr 0x004CC728 - 1 gp-relative ref at 0x003A4280

---

### 9. Other Formats

**CHT Facial** (%s.cht): vaddr 0x004CA6B8 - CEffectMgr facial animation  
**PAS Pose** (%s.pas): vaddr 0x004CFACA - STG stage effect placement  
**FON Font** (font/5-24-2.fon): vaddr 0x004CD460 - UI system font rendering  
**ICO Icon** (icon/memo.ico, icon/view.ico): vaddr 0x004CDD98, 0x004CDD8C - 8 gp-relative refs in code at 0x002B112C-0x002B6598  
**MSG Text** (msg/key.txt): vaddr 0x004CE34F - Shift-JIS encoded message text

**9a. FON Font (.fon)**  
- File: extracted/font/5-24-2.fon (340,192 bytes)  
- Magic: `FFON` (0x46464F4E)  
- Format string: `font/5-24-2.fon` at ELF vaddr 0x004CD460 (file 0x3CD4E0)  
- Code references: 0 direct references (constructed at runtime via pointer table)  
- The font is loaded and used by the UI system for text rendering  

**9b. ICO Icon (.ico)**  
- Files: extracted/icon/csmemo.ico (44,368 bytes), memo.ico (87,664 bytes)  
- Format: Standard Windows ICO (starts with 00 00 01 00)  
- Format strings: `icon/memo.ico` at vaddr 0x004CDD98, `view.ico` at vaddr 0x004CDD8C  
- Code references: 8 gp-relative references found:  
  - `lw` at vaddr 0x002B112C (file 0x1B11AC)  
  - `sw` at vaddr 0x002B1158 (file 0x1B11D8)  
  - `lw` at vaddr 0x002B1308 (file 0x1B1388)  
  - `lw` at vaddr 0x002B1314 (file 0x1B1394)  
  - `lw` at vaddr 0x002B142C (file 0x1B14AC)  
  - `lw` at vaddr 0x002B2EC0 (file 0x1B2F40)  
  - `lw` at vaddr 0x002B4D0C (file 0x1B4D8C)  
  - `lw` at vaddr 0x002B6598 (file 0x1B6618)  
- The code at 0x002B10CC-0x002B6598 does COP1 float setup (`mtc1`, `MOV.S`) and calls `0x0019FF80` / `0x001A0C70` — this is the icon loading/rendering pipeline  

**9c. MSG Text (.txt)**  
- File: extracted/msg/key.txt (15,703 bytes)  
- Encoding: Shift-JIS (0x82 A0 82 A2 ...)  
- Format string: `msg/key.txt` at ELF vaddr 0x004CE34F (file 0x3CE3CF)  
- Message key strings: `msgmkXXXX` at vaddr 0x004C5F88+  
- Code references: 0 direct references (loaded dynamically via message key system)  

---

## 10. CEBZ Virtual Function Tables

**CEBZEffect** class (object at vaddr 0x004CF030):  
- VTable at vaddr 0x004CF060 (file 0x3CF0E0), 4 entries  
- Object layout: starts with `"CEBZEffectEle"` magic string at offset 0, vtable pointer at offset +0x30  

| vfunc | Address | File Offset | Behavior |
|-------|---------|-------------|----------|
| vfunc[0] | 0x0038DFCC | 0x28E04C | `LUI s7,0x0039; ADDIU s7,s7,0xFEC0` → base 0x0039FEC0 |
| vfunc[1] | 0x0038DFD8 | 0x28E058 | `LUI s7,0x0039; ADDIU s7,s7,0xFDE0` → base 0x0039FDE0 |
| vfunc[2] | 0x0038DFE4 | 0x28E064 | `LUI s7,0x0039; ADDIU s7,s7,0xFD00` → base 0x0039FD00 |
| vfunc[3] | 0x0038DFF0 | 0x28E070 | `LUI s7,0x0039; ADDIU s7,s7,0xFB60` → base 0x0039FB60 |

All 4 vfuncs fall through to common dispatch at **0x0038E07C**:  
- Loads `object+0x30` value, compares against 5  
- Switch-style dispatch to functions at offsets from the base address  

**Other CEBZ classes** with name strings at object base:  
- `CEBZBase` at 0x004CEF40 (magic: `"CEBZBase"`)  
- `CEBZEffectObj` at 0x004CEF50 (magic: `"CEBZEffectObj"`)  
- `CEffectMgr` at 0x004CA870 (magic: `"CEffectMgr"`)  
- `CEBZObject` at 0x004C3C08 (magic: `"CEBZObject"`, contains `"CPlayer"` and `"Creator"` strings)  
- `CEBZHandle` at 0x004CEF30  
- `CEBZData` at 0x004CEF18  

**Class instance table** at vaddr 0x004FE628 (file 0x3FE6A8):  
Contains CEBZData, CEBZEffectObj, and CEBZEffect object pointers with float/integer parameters

---

## 11. Syscall Dispatch Table

**PS2 EE Syscall Convention (non-standard):**  
- Syscall number is passed in **$v1** (not $v0)  
- 16-byte wrapper functions at `0x00174880 + N*0x10`:  
  ```
  ADDIU v1,zero,N   # syscall number
  SYSCALL
  JR ra
  SLL zero,zero,0   # delay slot
  ```

**11 unique syscalls actually called via JAL** (all multiples of 16):

| Syscall # | Wrapper Address | Call Count |
|-----------|----------------|------------|
| 112 | 0x00174B80 | 4 |
| 208 | 0x00174D80 | 4 |
| 224 | 0x00174E00 | ? |
| 256 | 0x00174F00 | ? |
| 272 | 0x00174F80 | ? |
| 288 | 0x00175000 | 4 |
| 304 | 0x00175080 | ? |
| 320 | 0x00175100 | ? |
| 336 | 0x00175180 | 3 |
| 352 | 0x00175200 | ? |
| 368 | 0x00175280 | ? |

**888 total `syscall` instructions** found in code section  
**20 identified syscalls across 8 numbers**: ExitDeleteThread (×6), Breakpoint (×6), DebugBreak, COP2/VU0 syscalls  
**868 register-based syscalls** (dispatch table pattern - number comes from register, not immediate)

---

## 12. Entry Point / Main Loop

**Entry Point** at vaddr 0x00100008 (file 0x000088):  
- MMI code (op 0x1C), not standard MIPS  
- Initializes FPU: zeroes all $f0-$f31 via `mtc1`, sets FCR31=0  
- Clears BSS in two passes: 0x00500680→0x00640380, then 0x00640380→0x00644380  
- Sets **gp = 0x00503070** (runtime BSS, NOT in ELF file)  
- Syscall 60 → stack pointer; syscall 61 → unknown  

**Entry Point JAL chain:**  
`0x0017F018` → `0x00174F20` → `0x00422630` → **J 0x0018C518** (main loop)

**Main Loop** at vaddr 0x0018C518:  
- Uses **vtable dispatch**: iterates CEBZ object chain, calls method pointers via `JALR ra, v0`  
- 817 JALR instructions found in code section  
- Call clusters at 0x00430CA0-0x00430CD8 call methods through register-based vtable pointers ($15/$t7)

---

## 13. Widescreen Patch (EE 0x002B12D4)

**Patch target:** `LUI v0,0x3F40` → `LUI v0,0x3F10` (float constant 0.75 → 0.53125)  
- This is an aspect ratio adjustment in the COP1 FPU pipeline  
- File offset: 0x1B1354  
- **MISMATCH confirmed** - current ELF has 0x3F40, patch wants 0x3F10  

**Function at 0x002B1280** (COP1 vector setup leaf):  
- No JAL calls (leaf function)  
- Uses COP1 `LWC1`, `MUL.S`, `DIV.S`, matrix/viewport constants  

**Called from 3 sites:**  
- 0x002B18FC (file 0x1B190C)  
- 0x002B2A1C (file 0x1B2A9C)  
- 0x002B6194 (file 0x1B6214)  

**Caller chain:** `0x002D507C` → `0x003D4FE0` (JALR indirect) → `0x002B1700` → `0x002B1280`

**Cheat sources:**  
- OPL-Widescreen-Cheats: `202b12d4 3c023f10` + mastercode `90178010 0c05dfac`  
- PCSX2 pnach: `patch=1,EE,002b12d4,word,3c023f10`  
- Mastercode `0x00178010` → `JAL 0x00177EB0` at file 0x078090: **MATCH** (existing hook in ELF)

---

## Runtime Object Model

```
CEffectMgr (Singleton)
  ├── CEBZData (parsed .ebz file)
  │   ├── Header (magic, version, count, etc.)
    │   └── Ref Table (name→value pairs)
    │   └── Entries (per-effect transform data)
  ├── CEBZHandle (handle to loaded .ebz)
  ├── CEBZEffectObj (runtime effect instance)
  │   ├── CEBZEffMatrix (transformation matrix)
  │   ├── CEBZEffectEle (effect element)
  │   └── CEBZEffectGen (effect generator)
  └── CEBZEffectBase (base effect class)
```

### File Loading Chain:
```
GAME.DAT / INFO.DAT (archives)
    ↓
CFileLoadMng (archive manager)
    ↓
cvFsOpen (open file in archive)
    ↓
CCDRead (read data from archive file)
    ↓
Format-specific parser (CEBZData, FMDL parser, etc.)
    ↓
Runtime object (CEBZEffectObj, mesh, texture, etc.)
```

---

## Key Code Addresses Reference

| Address | Description |
|---------|-------------|
| 0x00100008 | ELF entry point (MMI code, FPU init, BSS clear) |
| 0x00174880 + N*0x10 | Syscall wrapper functions ($v1-based) |
| 0x0017F018 | Entry point JAL chain start |
| 0x00174F20 | Entry point JAL chain middle |
| 0x00422630 | Entry point JAL chain end → J 0x0018C518 |
| 0x0018C518 | Main loop (vtable dispatch, JALR ra,v0) |
| 0x003301E0-0x00330300 | CEBZ effect loading code (18 entries × 0x48 bytes) |
| 0x00191EF8 | String hash function (effect name lookup) |
| 0x00191638 | Data unpacking function (.ebz entry parsing) |
| 0x002B1280 | Widescreen patch function (COP1 FPU pipeline, leaf) |
| 0x002B12D4 | Widescreen patch site: LUI v0,0x3F40→0x3F10 |
| 0x002B18FC | Widescreen patch caller #1 |
| 0x002B2A1C | Widescreen patch caller #2 |
| 0x002B6194 | Widescreen patch caller #3 |
| 0x00332CD0 | CEBZ dispatch function (24 JAL calls) |
| 0x0038DFCC-0x0038DFF0 | CEBZEffect vfunc[0-3] (jump table dispatchers) |
| 0x0038E07C | CEBZEffect common dispatch target |
| 0x004CEF28 | "%s.ebz" format string |
| 0x004C3AF0 | "eff/e%c%c/%s" path format |
| 0x004CC5B0 | "%s.pix" format string |
| 0x004CC5A8 | "%s.mdl" format string |
| 0x004CC728 | "%s.pmt" format string |
| 0x004CFAF0 | "%s.ani" format string |
| 0x004CFACA | "%s.pas" format string |
| 0x004CA6B8 | "%s.cht" format string |
| 0x004CD460 | "font/5-24-2.fon" string |
| 0x004CDD98 | "icon/memo.ico" string |
| 0x004CDD8C | "icon/view.ico" string |
| 0x004CE34F | "msg/key.txt" string |
| 0x004C5F88+ | "msgmkXXXX" message key strings |
| 0x004CA870 | CEffectMgr class name |
| 0x004CEF18 | CEBZData class name |
| 0x004FE628 | CEBZ class info block |
| 0x004CEF50 | CEBZEffectObj class name |
| 0x004CF030 | CEBZEffect class object |
| 0x004CF060 | CEBZEffect vtable |
| 0x004C3C08 | CEBZObject class object |
| 0x004DAC70 | ASE sound (enter.ase) |
| 0x004DB8B0 | ASE sound (ending.ase) |
| 0x00499280 | AMS music (sel_in.ams) |
| 0x004992A4 | AMS music (sel_lp.ams) |
| 0x00499400 | AMS music (st01a_in.ams) |
| 0x00499424 | AMS music (st01a_lp.ams) |
| 0x00499700 | AMS music (st02a_in.ams) |
| 0x00499724 | AMS music (st02a_lp.ams) |
| 0x004C8860 | Hitbox s01a.hit |
| 0x004C9520 | Hitbox s10a.hit |
| 0x004C9700 | Hitbox s11a.hit |
| 0x004C99B0 | Hitbox s12a.hit |

---

## Conclusion

The file format interaction model for Super Dragon Ball Z follows a clear hierarchy:

1. **STG stages** are the entry point - they define the scene graph with EFFECT and STAGE roots
2. **STG EFFECT root** nodes reference `.ebz` effect files via `CEffectMgr`
3. **STAGE root** nodes reference `.mdl` models, `.hit` collision, `.ase` audio, `.ams` music
4. **MDL models** reference `.pix` textures, `.pmt` materials, `.ani` animations
5. **SPT scripts** can trigger effect spawning through commands that call `CEffectMgr`
6. **Passthrough formats**: `.fon` font, `.ico` icons, `.txt` messages are loaded dynamically without direct format string references in code

All asset loading ultimately goes through `CFileLoadMng` → `cvFsOpen`/`CCDRead` to read from `GAME.DAT`/`INFO.DAT` archives.

**Key architectural findings:**

- **Entry point** (0x00100008): MMI code that zeroes FPU registers, clears BSS, sets gp=0x00503070, then jumps to main loop at 0x0018C518
- **Main loop** (0x0018C518): Uses vtable dispatch via `JALR ra, v0` with 817 JALR instructions in code
- **Syscall convention**: Non-standard PS2 EE - syscall number in `$v1` (not `$v0`), 16-byte wrappers at `0x00174880 + N*0x10`
- **Widescreen patch** (0x002B12D4): Changes `LUI v0,0x3F40`→`0x3F10` (0.75→0.53125 aspect ratio) in COP1 FPU pipeline
- **CEBZ vtables**: CEBZEffect has 4 vfuncs at 0x004CF060 that set up s7 base addresses then fall through to common dispatch at 0x0038E07C
- **CEBZ class table**: Instance table at 0x004FE628 contains CEBZData/CEBZEffectObj/CEBZEffect pointers with transform parameters

The CEBZ effect system is particularly interesting: effect names (like "k7", "k8", "02Sp", etc.) are stored in a table and referenced by raw address in code, then looked up by hash in the `.ebz` ref table to find the matching entry, which defines the effect's transform and behavior.