# ARKD_DVD.IRX: INFO.DAT lookup and count limits (US SLUS_214.42)

This analysis was performed on the original **71,133-byte** ARKD_DVD.IRX (32-bit little-endian MIPS IOP relocatable ELF) and US **SLUS_214.42** (EE ELF). IRX addresses below are **module-relative virtual addresses**, not final relocated IOP addresses. Results are from static disassembly; no PCSX2 modified-archive test has yet been run.

## Archive layout

- INFO.DAT: 98,304 bytes (0x18000), 48-byte decoded header and 48-byte records.
- Decoded header `u32 entry_count` at offset `0x2C`: **1,930** for original US archive.
- Physical INFO file extent: `(98,304 - 48) / 48 = 2,047` record slots; **117** spare slots. Encoded tail consists of `0x40` bytes (not decoded all-zero records).
- Record: filename `char[32]`, unknown `u32`, sector offset `u32`, allocated sectors `u32`, unpadded file size `u32`. GAME.DAT sectors are 2,048 bytes.

## Source of “File Len : 2047”

The EE executable formats the IRX startup parameters using `disk=DVD file=%d pitch=4096 sndeff=OFF` (EE address `0x4DCED0`). The call sequence at **EE `0x422354–0x422360`** supplies literal **`0x7FF` (2,047)**, then loads `cdrom0:\ARKD_DVD.IRX;1`.

The driver parses `file=` via its `strtol` import at **IRX `0xA810–0xA878`**, writes the resulting integer to the global at relative `0xB49C`, and prints `File Len : %d`. The initial default written at `0xA6FC–0xA704` is `0x4FF` (1,279). **The printed limit comes from initialization arguments, not INFO.DAT length.**

## Header count rejection

At **IRX `0x0410–0x043C`**, the code reads `INFO+0x2C` and compares `entry_count < configured_file_limit` with unsigned comparison. Otherwise it emits `TOC File len is Over at Max files len!!` and enters an error/retry loop.

With unmodified US `file=2047`, **2,047 active records are rejected** by this check. **2,046** passes this *particular* check, but is not a confirmed functional limit.

## Filename lookup

- **`0x04B4–0x0610`** constructs 26 first-letter bucket pointers from the sorted table, handling missing initial letters.
- **`0x0A60–0x0C98`** selects a bucket using the filename's initial lowercase letter `'a'..'z'`, then walks 48-byte records and uses `strcmp` on candidates.
- A matching record is converted to a 14-bit-indexed internal handle (`0x3FFF` masks appear in this path). This **does not** prove that 16,384 records are supported.
- The original 1,930 filenames are lexicographically sorted and start with lowercase a–z. **Maintain initial-letter grouping; lexicographically sorting the whole table is safest.** Appending unsorted records may make them unreachable.

Relevant strings: `TOC File len is Over at Max files len!!` (`0xB030`), `file not found! : %s` (`0xB05C`), `\\INFO.DAT;1` (`0xB1E4`), `\\GAME.DAT;1` (`0xB1F0`), `File Len : %d` (`0xB2F0`).

## Possible earlier sector-read boundary

At **IRX `0x1914–0x1950`** the driver computes:

```cpp
uint32_t sectors_to_read = (configured_file_limit * 48) >> 11;
```

With `file=2047`, that is `(2047*48)>>11 = 47` DVD sectors = **96,256 bytes**. A 48-byte header and **2,004** complete records occupy 96,240 bytes; a 2,005th record would exceed that extent.

This is **a suspected boundary, not a proven effective maximum**. Other read paths, buffer initialization, and wrapper semantics require live investigation before concluding records beyond 2,004 fail. The toolkit deliberately does not hard-limit the count to 2,004, 2,046, or 2,047.

## Emulator test matrix

| Active records | Goal |
| ---: | --- |
| 1,930 | Original, original-size rebuild, and compact INFO control; all should print `File Len : 2047` |
| 1,931 | First added entry; verify game-side name lookup |
| 2,004 | Last complete record within apparent 47-sector read |
| 2,005 | First record beyond apparent 47-sector read |
| 2,046 | Highest count permitted by header comparison |
| 2,047 | Header overflow error expected |

When adding assets, update header count, insert records in sorted order, encode INFO, update GAME.DAT sectors, and ensure ISO 9660 file lengths match outputs. Validate **real IOP lookup and read**, not only our local parser.

## External references

- PS2SDK IOP sysclib declarations and import ordinals: https://ps2dev.github.io/ps2sdk/sysclib_8h.html
- PS2SDK CD/DVD `sceCdRead` sector semantics: https://israpps.github.io/ps2sdk/ncmd_8c_source.html
- PS2SDK IOP IRX load/start arguments: https://ps2dev.github.io/ps2sdk/group__loadfile.html

No copyrighted binary is distributed in this repository document.
