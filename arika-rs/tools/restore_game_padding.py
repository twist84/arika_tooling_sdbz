#!/usr/bin/env python3
"""Restore original GAME.DAT sector padding after an otherwise identical rebuild.

This tool is deliberately strict: it requires byte-identical INFO.DAT files,
identical GAME.DAT lengths, and identical bytes of *every indexed asset*. It
then copies only non-asset regions from the original GAME.DAT into the rebuilt
GAME.DAT. Original archive inputs are never modified.

Use after a seedless rebuild when byte-for-byte reproduction is required:

    python tools/restore_game_padding.py \\
        --original-info source_data/INFO.DAT \\
        --original-game source_data/GAME.DAT \\
        --rebuilt-info source_data/test/INFO.DAT \\
        --rebuilt-game source_data/test/GAME.DAT

A no-op --check reports differences without changing files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct


SECTOR = 2048
HEADER = 0x30
RECORD = 0x30
COPY_CHUNK = 1024 * 1024


def decode_info(encoded: bytes) -> bytes:
    if len(encoded) < HEADER or encoded[1:16] != b"www.arika.co.jp":
        raise ValueError("invalid INFO.DAT signature")
    key = encoded[:16]
    decoded = bytearray(encoded)
    for offset in range(16, len(encoded)):
        value = encoded[offset]
        swapped = ((value & 15) << 4) | (value >> 4)
        decoded[offset] = ((~swapped) - key[(offset - 16) & 15]) & 255
    return bytes(decoded)


def asset_extents(info: bytes) -> tuple[list[tuple[int, int, int]], int]:
    decoded = decode_info(info)
    count = struct.unpack_from("<I", decoded, 0x2C)[0]
    if count > (len(decoded) - HEADER) // RECORD:
        raise ValueError("INFO entry count exceeds table capacity")

    extents = []
    for i in range(count):
        at = HEADER + i * RECORD
        sector, sectors, size = struct.unpack_from("<III", decoded, at + 36)
        if (size + SECTOR - 1) // SECTOR > sectors:
            raise ValueError(f"entry {i} allocation smaller than asset")
        start = sector * SECTOR
        allocated_end = start + sectors * SECTOR
        extents.append((start, start + size, allocated_end))

    extents.sort()
    last_end = 0
    for start, end, allocated_end in extents:
        if start < last_end:
            raise ValueError("INFO asset extents overlap")
        last_end = allocated_end
    return extents, last_end


def compare_range(original, rebuilt, start: int, end: int) -> bool:
    original.seek(start)
    rebuilt.seek(start)
    remaining = end - start
    while remaining:
        size = min(remaining, COPY_CHUNK)
        if original.read(size) != rebuilt.read(size):
            return False
        remaining -= size
    return True


def copy_range(original, rebuilt, start: int, end: int, check_only: bool) -> int:
    original.seek(start)
    rebuilt.seek(start)
    remaining = end - start
    changed = 0
    while remaining:
        size = min(remaining, COPY_CHUNK)
        source = original.read(size)
        destination = rebuilt.read(size)
        if len(source) != size or len(destination) != size:
            raise ValueError("GAME.DAT truncated during operation")
        changed += sum(a != b for a, b in zip(source, destination))
        if source != destination and not check_only:
            rebuilt.seek(-size, 1)
            rebuilt.write(source)
        remaining -= size
    return changed


def restore_padding(
    original_info: Path,
    original_game: Path,
    rebuilt_info: Path,
    rebuilt_game: Path,
    check_only: bool = False,
) -> dict:
    if original_game.resolve() == rebuilt_game.resolve():
        raise ValueError("original and rebuilt GAME.DAT must be different files")

    encoded = original_info.read_bytes()
    if encoded != rebuilt_info.read_bytes():
        raise ValueError(
            "INFO.DAT files differ; refusing to copy padding across different tables"
        )
    extents, indexed_end = asset_extents(encoded)
    original_size = original_game.stat().st_size
    rebuilt_size = rebuilt_game.stat().st_size
    if original_size != rebuilt_size:
        raise ValueError("GAME.DAT lengths differ")
    if indexed_end > original_size:
        raise ValueError("INFO entries exceed GAME.DAT length")

    # Validate *all* real asset data before touching the rebuilt output.
    with original_game.open("rb") as original, rebuilt_game.open("rb") as rebuilt:
        for index, (start, data_end, _) in enumerate(extents):
            if not compare_range(original, rebuilt, start, data_end):
                raise ValueError(
                    f"entry {index} payload differs; no files were modified"
                )

    differing_bytes = 0
    mode = "rb" if check_only else "r+b"
    with original_game.open("rb") as original, rebuilt_game.open(mode) as rebuilt:
        last_end = 0
        for start, data_end, allocated_end in extents:
            # Copy any gaps between indexed allocations as well as sector padding.
            differing_bytes += copy_range(
                original, rebuilt, last_end, start, check_only
            )
            differing_bytes += copy_range(
                original, rebuilt, data_end, allocated_end, check_only
            )
            last_end = allocated_end
        differing_bytes += copy_range(
            original, rebuilt, last_end, original_size, check_only
        )
        if not check_only:
            rebuilt.flush()

    return {
        "entries": len(extents),
        "game_size": original_size,
        "indexed_end": indexed_end,
        "padding_bytes_differing": differing_bytes,
        "restored": not check_only,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-info", type=Path, required=True)
    parser.add_argument("--original-game", type=Path, required=True)
    parser.add_argument("--rebuilt-info", type=Path, required=True)
    parser.add_argument("--rebuilt-game", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="report only")
    args = parser.parse_args()
    report = restore_padding(
        args.original_info,
        args.original_game,
        args.rebuilt_info,
        args.rebuilt_game,
        check_only=args.check,
    )
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
