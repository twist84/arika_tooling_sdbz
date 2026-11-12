#!/usr/bin/env python3
"""Build a real-asset INFO.DAT / GAME.DAT fixture for ARKD_DVD.IRX count tests.

Requires an extracted US (SLUS_214.42) asset directory and the Rust arika CLI
from this repository. Uses hard links where possible to avoid duplicating the
large source asset tree. Does not edit the original archive or game executable.

Examples:
    python tools/irx_boundary_fixture.py --assets extracted --out fixtures \\
        --target-count 2004 --arika target/release/arika
    python tools/irx_boundary_fixture.py --assets extracted --out fixtures \\
        --target-count 2005 --dry-run

IMPORTANT: This produces candidate archive pairs, not bootable ISOs. To test
the IRX, replace both files on the disc, update ISO9660 sizes if needed, and
exercise an actual game-side read of a record near the end of the table.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


SECTOR = 2048
INFO_HEADER = 48
INFO_RECORD = 48
US_INFO_SIZE = 98_304
US_GAME_SIZE = 732_073_984
ORIGINAL_US_COUNT = 1930
TARGET_COUNTS = (1930, 1931, 2004, 2005, 2046, 2047)
PROBE_PREFIX = "a__irx_probe_"
PROBE_PAYLOAD = b"ARKD_IRX_PROBE\x00"


def inventory(root: Path) -> list[tuple[str, Path]]:
    if not root.is_dir():
        raise ValueError(f"asset directory does not exist: {root}")
    entries = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError(f"unsafe relative asset path: {relative}")
        if not ("a" <= relative[0] <= "z"):
            raise ValueError(f"IRX letter buckets require lowercase a-z: {relative}")
        if len(relative.encode("utf-8")) > 32:
            raise ValueError(f"INFO record name exceeds 32 bytes: {relative}")
        entries.append((relative, path))
    entries.sort(key=lambda item: item[0])
    return entries


def planned_names(source_names: list[str], target_count: int) -> tuple[list[str], list[str]]:
    if target_count not in TARGET_COUNTS:
        raise ValueError(f"target must be one of {TARGET_COUNTS}")
    if len(source_names) != ORIGINAL_US_COUNT:
        raise ValueError(
            f"expected {ORIGINAL_US_COUNT} extracted US files, got {len(source_names)}; "
            "verify this is a complete extraction from SLUS_214.42"
        )
    if len(set(source_names)) != len(source_names):
        raise ValueError("duplicate source paths")
    extra = target_count - len(source_names)
    names = [f"{PROBE_PREFIX}{i:04d}.bin" for i in range(extra)]
    collisions = set(names).intersection(source_names)
    if collisions:
        raise ValueError(f"probe filename collision: {sorted(collisions)[0]}")
    ordered = sorted(source_names + names)
    if len(ordered) != target_count:
        raise AssertionError("record count mismatch")
    if INFO_HEADER + target_count * INFO_RECORD > US_INFO_SIZE:
        raise ValueError("target INFO table does not fit the original US file size")
    return names, ordered


def create_staging(source: list[tuple[str, Path]], probes: list[str], root: Path) -> None:
    for name, path in source:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, destination)
        except OSError:
            shutil.copy2(path, destination)
    for name in probes:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(PROBE_PAYLOAD)


def make_fixture(
    assets: Path,
    output_root: Path,
    target_count: int,
    arika: str,
    dry_run: bool = False,
    game_size: int = US_GAME_SIZE,
) -> dict:
    source = inventory(assets)
    source_names = [name for name, _ in source]
    probes, ordered = planned_names(source_names, target_count)
    required_game_size = sum(
        ((path.stat().st_size + SECTOR - 1) // SECTOR) * SECTOR
        for _, path in source
    ) + len(probes) * SECTOR
    if game_size < required_game_size:
        raise ValueError(
            f"GAME.DAT size {game_size} is too small for the expected "
            f"{required_game_size} allocated bytes"
        )

    manifest = {
        "target_count": target_count,
        "original_count": len(source_names),
        "added_probe_count": len(probes),
        "info_size": US_INFO_SIZE,
        "game_size": game_size,
        "minimum_game_size": required_game_size,
        "sector_read_47_boundary": 2004,
        "record_2004": ordered[2003] if len(ordered) >= 2004 else None,
        "record_2005": ordered[2004] if len(ordered) >= 2005 else None,
        "last_record": ordered[-1],
        "last_eight_records": ordered[-8:],
        "probe_names": probes,
        "warning": "Fixture-only: test the IOP driver's real lookup/read and rebuild the ISO.",
    }

    if dry_run:
        return manifest

    output = output_root / f"irx_{target_count}"
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="arika_irx_staging_") as temporary:
            staging = Path(temporary)
            create_staging(source, probes, staging)
            command = [
                arika, "rebuild", "--assets", str(staging), "--version", "usa",
                "--out-info", str(output / "INFO.DAT"),
                "--out-game", str(output / "GAME.DAT"),
                "--info-size", str(US_INFO_SIZE),
                "--game-size", str(game_size),
            ]
            subprocess.run(command, check=True)
        info = output / "INFO.DAT"
        game = output / "GAME.DAT"
        if info.stat().st_size != US_INFO_SIZE or game.stat().st_size != game_size:
            raise ValueError("rebuilder returned unexpected archive sizes")
        # Parse the encoded header independently of the Rust backend.
        encoded = info.read_bytes()
        key = encoded[:16]
        decoded_count = bytes(
            ((~(((value << 4) | (value >> 4)) & 255)) - key[(offset - 16) & 15]) & 255
            for offset, value in enumerate(encoded[44:48], 44)
        )
        if int.from_bytes(decoded_count, "little") != target_count:
            raise ValueError("rebuilt INFO header count mismatch")
        (output / "fixture.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-count", type=int, choices=TARGET_COUNTS, required=True)
    parser.add_argument("--arika", default="arika", help="path to built Rust CLI")
    parser.add_argument("--game-size", type=int, default=US_GAME_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = make_fixture(
        args.assets, args.out, args.target_count, args.arika,
        dry_run=args.dry_run, game_size=args.game_size,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
