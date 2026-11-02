# SLUS_214.42 - Complete Call Graph Map

## Overview

This document maps the complete call graph for Super Dragon Ball Z (SLUS_214.42), showing how all file formats interact at runtime through function calls, syscalls, and vtable dispatch. Based on static analysis of the PS2 ELF executable.

---

## 1. Top-Level Execution Flow

```
POWER ON
    ↓
PS2 Kernel loads ELF via sceExec
    ↓
Entry Point @ 0x00100008 (file 0x000088)
├─ MMI code (op 0x1C) - not standard MIPS
├─ FPU init: zero $f0-$f31 via mtc1, set FCR31=0
├─ Clear BSS: 0x00500680→0x00640380, then 0x00640380→0x00644380
├─ Set gp = 0x00503070 (runtime BSS)
├─ Syscall 60 → stack pointer
├─ Syscall 61 → unknown
└─ JAL chain: 0x0017F018 → 0x00174F20 → 0x00422630 → J 0x0018C518
    ↓
Main Loop @ 0x0018C518
├─ VTable dispatch: iterate CEBZ object chain
├─ Call method pointers via JALR ra, v0
├─ Frame loop (per-frame update/render)
└─ 817 JALR instructions in code section (virtual calls)
```

---

## 2. Format Interaction Call Graph

### 2.1 STG Stage (.stg) → All Formats

```
STG File (GAME.DAT/INFO.DAT archive)
    ↓
CFileLoadMng → cvFsOpen → CCDRead
    ↓
STG Scene Parser
    │
    ├─ EFFECT Root → .ebz effect files
    │   ├─ CEffectMgr singleton
    │   │   ├─ CEBZData (parsed .ebz)
    │   │   │   ├─ Header (magic " ZBE", version 1.1)
    │   │   │   ├─ Ref Table (name→value pairs)
    │   │   │   └─ Entries (per-effect transform data)
    │   │   ├─ CEBZHandle (handle to loaded .ebz)
    │   │   └─ CEBZEffectObj (runtime effect instance)
    │   │       ├─ CEBZEffMatrix (transformation matrix)
    │   │       ├─ CEBZEffectEle (effect element)
    │   │       └─ CEBZEffectGen (effect generator)
    │   └─ CEBZ loading code @ 0x003301E0-0x00330300
    │       ├─ 18 entries × 0x48 bytes each
    │       ├─ Dispatch on type: 0=setup, 1=load, 2=alt-load, 3=cleanup
    │       ├─ JAL 0x00191EF8 (string hash function)
    │       └─ JAL 0x00191638 (data unpacker function)
    │
    ├─ STAGE Root → .mdl model files
    │   ├─ FMDL parser
    │   │   ├─ .mdl → .pix textures (material slots)
    │   │   ├─ .mdl → .pmt materials (material definitions)
    │   │   └─ .mdl → .ani animations (skeletal animation)
    │   └─ %s.mdl @ 0x004CC5A8 (0 gp-relative refs)
    │
    ├─ STAGE Root → .hit collision files
    │   ├─ HIT parser
    │   └─ %s.hit format strings at various vaddrs
    │
    ├─ STAGE Root → .ase audio files
    │   ├─ ASE parser
    │   └─ ply/p%02d/voi/%s.ase @ 0x004C3AF0
    │
    ├─ STAGE Root → .ams music files
    │   ├─ AMS parser
    │   └─ %s.ams format strings at various vaddrs
    │
    └─ STAGE Root → .spt script files
        ├─ SPT parser
        └─ Effect commands → CEffectMgr → .ebz files
```

---

### 2.2 CEBZ Effect Call Graph (Detailed)

```
CEBZ Loading Code @ 0x003301E0
    │
    ├─ Iterate 18 entries × 0x48 bytes
    │   ├─ Load entry byte at offset 0x104
    │   ├─ If non-zero → process entry
    │   ├─ JAL 0x00191EF8 (string hash function)
    │   │   └─ XOR-based hash of effect name strings
    │   ├─ JAL 0x00191638 (data unpacker function)
    │   │   └─ Bit manipulation with masks 0x0101, 0x8080
    │   └─ Compare results, loop
    │
    └─ CEBZ Dispatcher @ 0x00332CD0
        ├─ 24 JAL calls to helper functions
        ├─ JAL 0x00333A10
        ├─ JAL 0x00333C20
        ├─ JAL 0x00333CF0
        ├─ JAL 0x00334560
        ├─ JAL 0x0018E408
        └─ JAL 0x00190FF0
            ↓
    CEBZ Class Instance Table @ 0x004FE628
        ├─ CEBZData @ 0x004CEF18
        ├─ CEBZEffectObj @ 0x004CEF50
        └─ CEBZEffect @ 0x004CF030
            ├─ VTable @ 0x004CF060 (4 entries)
            │   ├─ vfunc[0] @ 0x0038DFCC (base 0x0039FEC0)
            │   ├─ vfunc[1] @ 0x0038DFD8 (base 0x0039FDE0)
            │   ├─ vfunc[2] @ 0x0038DFE4 (base 0x0039FD00)
            │   └─ vfunc[3] @ 0x0038DFF0 (base 0x0039FB60)
            └─ All fall through to dispatch @ 0x0038E07C
                ├─ Load object+0x30 value, compare vs 5
                └─ Switch-style dispatch to base+offset functions
```

---

### 2.3 Syscall Call Graph

```
User Code
    │
    ├─ Set syscall number in $v1 (NOT $v0 - non-standard!)
    ├─ JAL to wrapper @ 0x00174880 + N*0x10
    │   ├─ ADDIU v1,zero,N
    │   ├─ SYSCALL (trap to kernel)
    │   ├─ JR ra
    │   └─ SLL zero,zero,0 (delay slot)
    │
    └─ 11 unique syscalls called via JAL:
        ├─ Syscall 112  @ wrapper 0x00174B80  (4 calls)
        ├─ Syscall 208  @ wrapper 0x00174D80  (4 calls)
        ├─ Syscall 224  @ wrapper 0x00174E00
        ├─ Syscall 256  @ wrapper 0x00174F00
        ├─ Syscall 272  @ wrapper 0x00174F80
        ├─ Syscall 288  @ wrapper 0x00175000  (4 calls)
        ├─ Syscall 304  @ wrapper 0x00175080
        ├─ Syscall 320  @ wrapper 0x00175100
        ├─ Syscall 336  @ wrapper 0x00175180  (3 calls)
        ├─ Syscall 352  @ wrapper 0x00175200
        └─ Syscall 368  @ wrapper 0x00175280
            ↓
    PS2 Kernel Syscall Handler
        │
        ├─ Thread management (ExitThread, CreateThread, etc.)
        ├─ Synchronization (Sema, Mutex, EventFlag)
        ├─ File I/O (sceIoOpen, sceIoRead, etc.)
        ├─ Timers, DMA, VU, SIF/RPC
        └─ Debug/Exec (ExecPS2, printf)
```

---

### 2.4 Virtual Call Graph (JALR)

```
Main Loop @ 0x0018C518
    │
    ├─ Iterate CEBZ object chain
    ├─ Load vtable pointer into register ($15/$t7)
    ├─ JALR rd, rs (indirect call through register)
    │   ├─ JALR at 0x00430CA0 (call $t7)
    │   ├─ JALR at 0x00430CA8 (call $t7)
    │   ├─ JALR at 0x00430CB0 (call $t7)
    │   ├─ JALR at 0x00430CB8 (call $t7)
    │   ├─ JALR at 0x00430CC0 (JALR t2,t7)
    │   ├─ JALR at 0x00430CC8 (JALR t3,t7)
    │   ├─ JALR at 0x00430CD0 (JALR t4,t7)
    │   └─ JALR at 0x00430CD8 (JALR t5,t7)
    │
    └─ 817 total JALR instructions in code section
        └─ Call clusters at 0x00430CA0-0x00430CD8
```

---

### 2.4 Widescreen Patch Call Graph

```
Widescreen Patch @ 0x002B12D4 (LUI v0,0x3F40 → 0x3F10)
    │
    └─ Function @ 0x002B1280 (COP1 FPU pipeline leaf)
        ├─ No JAL calls (leaf function)
        ├─ COP1 LWC1 load
        ├─ COP1 MUL.S multiply
        ├─ COP1 DIV.S divide
        └─ Matrix/viewport constant setup
            ↓
    Called from 3 sites:
        ├─ Caller #1 @ 0x002B18FC (file 0x1B190C)
        ├─ Caller #2 @ 0x002B2A1C (file 0x1B2A9C)
        └─ Caller #3 @ 0x002B6194 (file 0x1B6214)
            ↓
    Caller chain:
        0x002D507C → 0x003D4FE0 (JALR indirect) → 0x002B1700 → 0x002B1280
```

---

### 2.5 No-Interlacing Patch Call Graph

```
No-Interlacing Patch @ EE 0x20104C6A (file offset 0x4CEA)
    │
    ├─ Current value: 0xC4B4AC62
    ├─ Patch value: 0xC4B4AC60 (alpha byte change only)
    ├─ Located in code segment at vaddr 0x00104C6A
    └─ NOT a GS register (GS is at 0x12000000+)
        ↓
    Likely display buffer setup / interlace control
    (outside ELF file range for direct patching - runtime register patch)
```

---

### 2.6 Mastercode Call Graph

```
Mastercode @ 0x00178010 (JAL 0x00177EB0)
    │
    ├─ File offset: 0x078090
    ├─ MATCH confirmed (existing hook in ELF)
    └─ Hooked into game execution at startup
        ↓
    Cheat patches applied after mastercode
        ├─ Widescreen: LUI v0,0x3F40→0x3F10 @ 0x002B12D4
        └─ No-Interlacing: EE 0x20104C62→0x20104C60 @ 0x20104C6A
```

---

## 3. Format-Specific Call Details

### 3.1 Texture (.pix) Loading
```
%s.pix @ 0x004CC5B0
    │
    ├─ 1 gp-relative ref at 0x003A4160
    └─ Code at 0x003A4120-0x003A421C builds format string pointer table
        ├─ LUI v1,0x0061
        ├─ ADDIU a1,gp,0xC500
        ├─ SW a0,0x0824(v1)  → gp+0xC524
        ├─ LUI v1,0x0061
        ├─ ADDIU a0,gp,0xC5B0  → a0 = %s.pix
        ├─ SW a1,0x0838(v1)  → gp+0xC538
        └─ Builds table at gp+0xC500 through gp+0xC5E4
```

### 3.2 Material (.pmt) Loading
```
%s.pmt @ 0x004CC728
    │
    └─ 1 gp-relative ref at 0x003A4280
```

### 3.3 Animation (.ani) Loading
```
%s.ani @ 0x004CFAF0
    │
    └─ 0 gp-relative refs (constructed at runtime)
```

### 3.4 Pose (.pas) Loading
```
%s.pas @ 0x004CFACA
    │
    └─ 0 direct references (constructed dynamically)
    └─ 7 .pas files in extracted/ply/ (shen.pas, fin01-06.pas)
    └─ Format: 64-byte header + variable entry array
    └─ Entries contain float data (pose/animation transforms)
```

### 3.5 Font (.fon) Loading
```
font/5-24-2.fon @ 0x004CD460
    │
    └─ 0 direct references (constructed at runtime)
    └─ Magic: FFON (0x46464F4E)
    └─ UI system font rendering
```

### 3.6 Icon (.ico) Loading
```
icon/memo.ico @ 0x004CDD98
icon/view.ico @ 0x004CDD8C
    │
    ├─ 8 gp-relative references:
    ├─ lw @ 0x002B112C (file 0x1B11AC)
    ├─ sw @ 0x002B1158 (file 0x1B11D8)
    ├─ lw @ 0x002B1308 (file 0x1B1388)
    ├─ lw @ 0x002B1314 (file 0x1B1394)
    ├─ lw @ 0x002B142C (file 0x1B14AC)
    ├─ lw @ 0x002B2EC0 (file 0x1B2F40)
    ├─ lw @ 0x002B4D0C (file 0x1B4D8C)
    └─ lw @ 0x002B6598 (file 0x1B6618)
    │
    └─ Code at 0x002B10CC-0x002B6598:
        ├─ COP1 mtc1, MOV.S float setup
        ├─ JAL 0x0019FF80
        ├─ JAL 0x001A0C70 (×3 calls)
        └─ Icon loading/rendering pipeline
```

### 3.7 Message (.txt) Loading
```
msg/key.txt @ 0x004CE34F
    │
    ├─ 0 direct references (message key system)
    └─ msgmkXXXX key strings at vaddr 0x004C5F88+
    └─ Shift-JIS encoded (0x82 A0 82 A2 ...)
```

---

## 4. Complete Address Reference Table

| Address | Description |
|---------|-------------|
| 0x00100008 | ELF entry point |
| 0x00174880+N*0x10 | Syscall wrappers ($v1-based) |
| 0x0017F018 | Entry point JAL chain |
| 0x00174F20 | Entry point JAL chain |
| 0x00422630 | Entry point JAL chain → main loop |
| 0x0018C518 | Main loop (vtable dispatch) |
| 0x003301E0-0x00330300 | CEBZ effect loading |
| 0x00191EF8 | String hash function |
| 0x00191638 | Data unpacker |
| 0x002B1280 | Widescreen patch function |
| 0x002B12D4 | Widescreen patch site (LUI v0,0x3F40→0x3F10) |
| 0x002B18FC | Widescreen caller #1 |
| 0x002B2A1C | Widescreen caller #2 |
| 0x002B6194 | Widescreen caller #3 |
| 0x00332CD0 | CEBZ dispatcher (24 JALs) |
| 0x0038DFCC-0x0038DFF0 | CEBZEffect vfunc[0-3] |
| 0x0038E07C | CEBZEffect common dispatch |
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
| 0x004C5F88+ | "msgmkXXXX" message keys |
| 0x004CA870 | CEffectMgr class |
| 0x004CEF18 | CEBZData class |
| 0x004FE628 | CEBZ class info block |
| 0x004CEF50 | CEBZEffectObj class |
| 0x004CF030 | CEBZEffect class object |
| 0x004CF060 | CEBZEffect vtable |
| 0x004C3C08 | CEBZObject class object |

---

## 5. Tooling Used for Analysis

| Tool | Purpose |
|------|---------|
| mips_disasm.py | MIPS R5900 disassembler (98.6% decode rate, COP1/COP2/COP0/MMI) |
| elf_func_trace.py | JAL-target function boundaries + call graph |
| elf_patch_verify.py | .pnach/.cht cheat verification |
| elf_patch_apply.py | Apply patches → modified ELF |
| elf_sym_map.py | Symbol cross-reference map |
| elf_section_aware.py | PT_Load segment bounds validation |
| elf_syscall_map.py | PS2 EE syscall reference mapper |
| elf_file_corr.py | Extracted file ↔ ELF string correlation |
| elf_class_map.py | Class/vtable mapper |
| elf_cebz_class_map.py | CEBZ class vtable tracer |
| elf_vtable_trace.py | VTable function tracer |
| elf_vcall_finder.py | JALR virtual call site finder |
| elf_trace_vcall.py | Specific virtual call site tracer |
| elf_ebz_format.py | .ebz binary format parser |
| elf_eff_fmt.py | .ebz/eff format tracer |
| elf_fon_loader.py | .fon font format tracer |
| elf_ico_loader.py | .ico icon format tracer |
| elf_msg_loader.py | .txt message format tracer |
| elf_pas_loader.py | .pas pose format tracer |

All 19 tools pass `py_compile`.

---

## 6. Runtime Object Model

```
CEffectMgr (Singleton)
  ├── CEBZData (parsed .ebz file)
  │   ├── Header (magic " ZBE", version 1.1)
  │   ├── Ref Table (name→value pairs)
  │   └── Entries (per-effect transform data)
  ├── CEBZHandle (handle to loaded .ebz)
  ├── CEBZEffectObj (runtime effect instance)
  │   ├── CEBZEffMatrix (transformation matrix)
  │   ├── CEBZEffectEle (effect element)
  │   └── CEBZEffectGen (effect generator)
  └── CEBZEffectBase (base effect class)

File Loading Chain:
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

## 7. Conclusion

The call graph reveals a layered architecture:

1. **Entry point** (0x00100008): MMI init → FPU zero → BSS clear → gp=0x00503070 → main loop
2. **Main loop** (0x0018C518): vtable dispatch via JALR ra,v0 with 817 indirect calls
3. **Syscall layer**: $v1-based (non-standard), 16-byte wrappers, 11 unique syscalls called
4. **Effect system**: CEBZ with 18-entry dispatch table, 4-vfunc vtable, jump-table dispatch
5. **Format loading**: Mostly dynamic path construction via sprintf, few direct references
6. **Patch points**: Widescreen at 0x002B12D4 (COP1 FPU), No-interlacing at EE 0x20104C6A