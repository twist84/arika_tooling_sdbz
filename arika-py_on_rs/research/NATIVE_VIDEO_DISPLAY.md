# Native PS2 display and menu coordinate research

## Sources

This analysis was made directly from the user's four game ELF files, extracted
from `ELFs(1).zip` (not committed), and from the user's existing
`dis/main_menu.pix` atlas extraction. The supported primary target is the
EU beta `SLES_541.61`, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
Disassembly was inspected with `llvm-objdump -d`. All addresses below are EE
virtual addresses, **not offsets inside the ELF file**.

The binary has one executable PT_LOAD segment starting at VA `0x00100000`,
file offset `0x80`. Functions are not identified by symbol names (the
ELF's symbol table is empty); their roles are assigned from instructions and
call relationships.

## Findings with instruction-level support

### 1. The game does define graphics dimensions — multiple sets

**EU beta `0x001066C0`** is a graphics initialization path. After the reset
and initialization calls, it passes these exact constants to
`0x001061D0`:

```asm
001066F4: addiu $a0, $zero, 0x280  # 640
001066F8: addiu $a1, $zero, 0x1c0  # 448
00106700: move  $a2, $a0           # 640
00106708: move  $a3, $a1           # 448
0010670C: jal   0x001061D0
00106710: move  $t0, $zero
```

This is a **640×448 default graphics configuration**, not proof that menu
sprites use 640-pixel coordinates or that television display pixels are square.

`0x001061D0` is the mode/geometry validator and dispatcher. It explicitly
checks the supplied width arguments against **512 and 640** and height
arguments against **448 and 512** (e.g. `0x106230–0x1062B8`,
`0x1062C8–0x106400`). It passes the selected combination onward to
`0x00105550` at `0x0010644C`.

**EU beta `0x0041F090–0x0041F0D8`** is another graphics-object configuration
path. It chooses `$s2 = 512` or `448` based on a condition, then calls
`0x001998A0` with `a1 = 512`, `a2 = s2`, and `t2 = s2`.
This is evidence for selectable **512×512 / 512×448** buffer dimensions, not
evidence that the television is outputting a square image.

**EU beta `0x0041F690–0x0041F738`** is a separate initial renderer setup:
it establishes 512-valued dimensions and calls `0x001999F0` at
`0x0041F738`. That routine first calls `0x001066C0` (the 640×448
default setup) at `0x00199A50`, then configures the requested buffers via
`0x001061D0` at `0x00199ACC`. Thus the binary **explicitly separates**
the system's initial GS configuration from subsequent render-buffer sizes.

### 2. This is real GS display-register programming

The graphics update path beginning at **`0x00104E00`** writes the PS2
privileged GS register bank at `0x12000000`. Among other stores:

- `0x00104F84`: write to `0x12000020` (**SMODE2**).
- `0x00105038`: write to `0x12000090` (**DISPFB2**).
- `0x00105098`: write to `0x120000A0` (**DISPLAY2**).
- Other branches configure scan/display fields and flip the selected buffer.

`0x00105550` also calls `0x00171DB8` with mode-dependent parameters,
and `0x00171DB8` proceeds to program the GS and call the CRT setup path.
These are **hardware register writes**, not just texture-size literals.

For register-name verification, see the ps2sdk
[GS privileged register definitions](https://github.com/ps2dev/ps2sdk/blob/master/common/include/gs_privileged.h)
and [GS register addresses](https://github.com/ps2dev/ps2sdk/blob/master/common/include/ee_regs.h).

### 3. Regional comparison

The same unique 640×448 immediate pair occurs in the corresponding graphics
initializer in **all four** inspected executables:

| Executable | Initialization pair VA | Immediates |
|---|---:|---|
| Europe beta SLES_541.61 | `0x1066F4` | `0x280, 0x1C0` |
| Europe release SLES_541.61 | `0x106814` | `0x280, 0x1C0` |
| Japan SLPS_256.42 | `0x1066F4` | `0x280, 0x1C0` |
| USA SLUS_214.42 | `0x106814` | `0x280, 0x1C0` |

The instruction pattern was checked in each ELF, but this does **not** prove
that all four boot with the same final video mode or that PAL and NTSC
timings match. Dynamic mode selection remains relevant.

### 4. Menu geometry is narrower than the graphics configuration

The ELF-derived menu background geometry is
`(0,0)–(512,448)`, from the existing verified sprite extraction.
The tile helper `0x00376290` draws entry-2 strips at native
Y = **320**, height **128** (bottom **448**). Its two X copies and
phase math are covered by the existing native-oracle tests.

FPIX atlas entry 4, the native help frame, is a 512×512 texture **atlas**;
its alpha-visible rectangle is `(6,2)–(458,176)` (width 452, height 174)
in the supplied extracted PNG. Texture dimensions **do not** establish
render-target or display dimensions.

## Interpretation and recommendations

**Confirmed:** 640×448 default GS setup, 512/640 width and 448/512 height
choices, GS `DISPFB`/`DISPLAY` programming, 512×448 menu sprite geometry.

**Not yet confirmed:** the complete runtime configuration selected when
`CMenuMainMenu` is visible, the GS `DISPLAY` `MAGH`/`MAGV`
values in that state, whether the reference square screenshots are
display-corrected, and the exact pixel aspect-ratio correction performed
by the console/emulator/capture process.

The 4:3 television target must not be confused with a 4:3 *numeric*
framebuffer ratio. In particular, **640/448 is not 4/3**, and
**512/448 is not 4/3**; output timing, horizontal/vertical magnification,
and CRT pixel aspect matter.

Do **not** rewrite native menu sprite coordinates, shift cloud quads,
or stretch the help frame based on assumed video dimensions. Preserve the
**512×448 menu coordinate space** as the source of truth and keep
display/capture transformations separate. Eventually expose at least
a raw logical view and a 4:3 TV presentation view in the editor.
Keep square presentation solely as an explicit comparison option.

## DISPLAY2 register field reconstruction (additional static trace)

The EU beta's `0x00105060–0x00105098` sequence constructs the 64-bit
`DISPLAY2` value written to GS address `0x120000A0`. The alternate
branch at `0x00105394–0x001053CC` uses the same packing pattern.
The corresponding pair of sites appears in all four inspected builds:

| ELF | DISPLAY2 store sites |
|---|---|
| EU beta | `0x105098`, `0x1053CC` |
| Final EU | `0x1051B8`, `0x1054EC` |
| Japan | `0x105098`, `0x1053CC` |
| USA | `0x1051B8`, `0x1054EC` |

The bit layout is independently confirmed by ps2sdk's
[`GS_SET_DISPLAY`](https://israpps.github.io/ps2sdk/gs__privileged_8h_source.html):
`DX[0:11]`, `DY[12:22]`, `MAGH[23:26]`, `MAGV[27:28]`,
`DW[32:43]`, `DH[44:54]`.

The straightforward branch of the native builder loads:

- **DW = 2559** (literal `0x9FF` at `0x105060`, shifted left 32).
- **DH = configured_height - 1** (loaded from global `0x004FF384`,
  decremented at `0x10507C`, shifted left 44 at `0x10508C`).
- **MAGH = 3 for 640 pixels**, or **4 for 512 pixels** (set by
  `0x1056A0–0x1056B4` and `0x105750–0x10576C`, stored at
  global `0x004FF390`; shifted left 23 at `0x10506C`).
- The horizontal nominal source span is `(DW+1)/(MAGH+1)`:
  **2560/4 = 640** or **2560/5 = 512**.
- **DX** is assembled from globals `0x004FF3EC` and
  `0x004FF3F4`; **DY** from `0x004FF3F0` and
  `0x004FF3F8`. These values can vary by video mode and are
  not fixed by the inspected `0x9FF` constant.

`0x00105038` also writes the framebuffer selector `DISPFB2`;
its fields follow `FBP[0:8]`, `FBW[9:14]`, `PSM[15:19]`,
`DBX[32:42]`, `DBY[43:53]`.
These registers must be decoded **from the value at the actual store**;
for example, the register's `DW=2559` counts horizontally magnified
display samples, not source texture pixels.

### Runtime procedure

At a stable main-menu frame in PCSX2, read the 64-bit values at
`0x12000080` (DISPLAY1), `0x120000A0` (DISPLAY2),
`0x12000070` (DISPFB1), `0x12000090` (DISPFB2), and
`0x12000020` (SMODE2) if the debugger exposes those privileged
registers. Alternatively, stop the EE at the `sd` instructions above
and inspect the source 64-bit register before execution.
The available values and accuracy of external GS-register inspection
depend on the PCSX2 debugging build.

Decode the captures without recompilation:

```sh
python elf_tooling/elf_gs_display.py --display 0x<16_hex_digits>
python elf_tooling/elf_gs_display.py --dispfb 0x<16_hex_digits>
python elf_tooling/elf_gs_display.py SLES_541.61
```

The decoder reports field values and nominal source dimensions,
but **nominal source height is not automatically the final perceived
TV height**: interlace, field parity, output mode, magnification, and
capture scaling require further verification. The probe also scans
regional builds without hardcoding the beta's offsets.

### Current editor presentation modes

The Qt preview now provides **Square capture** (existing default),
**Raw 512×448**, and **4:3 television** modes. These choices change
only the final presentation transform and intentionally leave all
native sprite and tile coordinates at 512×448. The 4:3 mode is a
comparison view, **not a claim that the native GS registers have been
verified for the main menu**.

## Remaining ELF work

1. Finish the dataflow from `0x0041F090`'s height-selection condition and
   `0x0041F690`'s graphics-object parameters to the actual menu-visible
   framebuffer configuration.
2. Capture the runtime 64-bit `DISPLAY1/2` words and decode their
   `DX/DY/MAGH/MAGV/DW/DH` fields; the static `DISPLAY2` packing
   has been identified but its menu-visible dynamic register values have not.
3. Compare the runtime mode selection and PAL/NTSC branches between the
   beta/final EU, Japan, and US executables.
4. Verify on PCSX2 by logging GS registers and the active framebuffer
   while `CMenuMainMenu` is drawn. Use that trace to pin down final
   scaling/capture instead of fitting screenshots blindly.
