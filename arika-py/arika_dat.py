#!/usr/bin/env python3
"""Inspect, extract and rebuild Super Dragon Ball Z's INFO.DAT / GAME.DAT."""
import argparse
import binascii
import csv
from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
import zlib

MAGIC = b"\x7fwww.arika.co.jp"
SECTOR = 2048
HEADER = 0x30
RECORD = 0x30


def swap_nibbles(value):
    return ((value & 15) << 4) | (value >> 4)


def decode_info(data):
    if len(data) < HEADER or data[1:16] != MAGIC[1:]:
        raise ValueError("not this game's Arika INFO.DAT")
    key = data[:16]
    return key + bytes((~swap_nibbles(value) - key[index & 15]) & 255 for index, value in enumerate(data[16:]))


def encode_info(data):
    if len(data) < HEADER or data[1:16] != MAGIC[1:]:
        raise ValueError("decoded INFO data has an invalid header")
    key = data[:16]
    return key + bytes(swap_nibbles(~(value + key[index & 15]) & 255) for index, value in enumerate(data[16:]))


# Region byte 0 values for the INFO.DAT codec key. Bytes 1..15 are always www.arika.co.jp.
INFO_REGIONS = {
    "eu-beta": 0x7F,
    "eubeta": 0x7F,
    "eu_beta": 0x7F,
    "eu": 0x11,
    "usa": 0xC2,
    "jpn": 0x60,
    "db1": 0xBB,
    "dvb1": 0xBB,
    "arcade": 0xBB,
    "db1.b": 0xBB,
}


def region_byte0(name):
    lowered = name.strip().lower()
    if lowered not in INFO_REGIONS:
        raise ValueError("unknown region: " + name + " (expected: " + ", ".join(sorted(INFO_REGIONS)) + ")")
    return INFO_REGIONS[lowered]


def make_decoded_info(byte_0, count):
    buf = bytearray(HEADER)
    buf[0] = byte_0
    buf[1:16] = MAGIC[1:]
    struct.pack_into("<I", buf, 0x2C, count)
    return buf


def write_info_record(decoded, index, name, unknown, sector, sectors, size):
    at = HEADER + index * RECORD
    if at + RECORD > len(decoded):
        raise ValueError("record index out of bounds: " + str(index))
    name_bytes = name.encode("cp932")
    if len(name_bytes) > 32:
        raise ValueError("asset name too long: " + name)
    decoded[at:at + len(name_bytes)] = name_bytes
    struct.pack_into("<IIII", decoded, at + 32, unknown, sector, sectors, size)


def encode_info_with_key(key, data):
    if len(data) < HEADER:
        raise ValueError("decoded INFO data has an invalid header")
    if len(key) != 16:
        raise ValueError("key must be exactly 16 bytes")
    return key + bytes(swap_nibbles(~(value + key[index & 15]) & 255) for index, value in enumerate(data[16:]))


def relative_name(name):
    path = PurePosixPath(name.replace("\\", "/"))
    if not name or path.is_absolute() or ".." in path.parts or ":" in name or any(ord(c) < 32 for c in name):
        raise ValueError("unsafe asset path: " + repr(name))
    return path


def asset_path(root, name):
    path = root.joinpath(*relative_name(name).parts)
    path.resolve().relative_to(root.resolve())
    return path


@dataclass
class Entry:
    index: int
    name: str
    unknown: int
    sector: int
    sectors: int
    size: int

    @property
    def offset(self):
        return self.sector * SECTOR


class Archive:
    def __init__(self, info, game=None):
        self.info = Path(info)
        self.game = Path(game) if game else None
        self.encoded = self.info.read_bytes()
        self.decoded = decode_info(self.encoded)
        count, = struct.unpack_from("<I", self.decoded, 0x2C)
        if count > (len(self.decoded) - HEADER) // RECORD:
            raise ValueError("invalid INFO entry count")
        self.entries = []
        names = set()
        for index in range(count):
            at = HEADER + index * RECORD
            raw = self.decoded[at:at + 32].split(b"\0", 1)[0]
            name = raw.decode("cp932")
            folded = str(relative_name(name)).casefold()
            if folded in names:
                raise ValueError("duplicate/case-colliding asset name: " + name)
            names.add(folded)
            unknown, sector, sectors, size = struct.unpack_from("<4I", self.decoded, at + 32)
            if sectors < (size + SECTOR - 1) // SECTOR:
                raise ValueError("asset is larger than its allocated sectors: " + name)
            self.entries.append(Entry(index, name, unknown, sector, sectors, size))
        last_end = 0
        for entry in sorted(self.entries, key=lambda entry: entry.offset):
            if entry.offset < last_end:
                raise ValueError("overlapping asset extents")
            last_end = entry.offset + entry.sectors * SECTOR
        self.used_bytes = last_end
        if self.game and self.used_bytes > self.game.stat().st_size:
            raise ValueError("GAME.DAT is too small for this INFO.DAT")

    def manifest(self):
        result = []
        source = self.game.open("rb") if self.game else None
        try:
            for entry in self.entries:
                row = dict(index=entry.index, name=entry.name, unknown=entry.unknown, sector=entry.sector,
                    offset=entry.offset, sectors=entry.sectors, size=entry.size)
                if source:
                    source.seek(entry.offset)
                    signature = source.read(min(4, entry.size))
                    row["magic_hex"] = signature.hex()
                    row["magic_ascii"] = "".join(chr(c) if 32 <= c < 127 else "." for c in signature)
                result.append(row)
        finally:
            if source: source.close()
        return result


def exact_copy(source, output, count):
    while count:
        chunk = source.read(min(count, 4 << 20))
        if not chunk:
            raise ValueError("unexpected end of input file")
        output.write(chunk)
        count -= len(chunk)


def extract(archive, destination, patterns=(), overwrite=False):
    root = Path(destination)
    selected = [entry for entry in archive.entries if not patterns or any(fnmatch.fnmatchcase(entry.name, pattern) for pattern in patterns)]
    targets = [(entry, asset_path(root, entry.name)) for entry in selected]
    for _, path in targets:
        if path.exists() and not overwrite:
            raise ValueError("output exists; use --overwrite: " + str(path))
    with archive.game.open("rb") as source:
        for entry, path in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            source.seek(entry.offset)
            with path.open("wb") as output:
                exact_copy(source, output, entry.size)
    print("Extracted %d assets to %s" % (len(targets), root))


def rebuild(archive, destination, replacements=None):
    root = Path(destination)
    out_info, out_game = root / "INFO.DAT", root / "GAME.DAT"
    originals = {archive.info.resolve(), archive.game.resolve()}
    if out_info.resolve() in originals or out_game.resolve() in originals:
        raise ValueError("rebuild output must differ from the input INFO.DAT and GAME.DAT")
    plan = []
    next_sector = 0
    for entry in archive.entries:
        replacement = asset_path(Path(replacements), entry.name) if replacements else None
        if replacement and not replacement.exists(): replacement = None
        if replacement and not replacement.is_file(): raise ValueError("replacement is not a file: " + str(replacement))
        size = replacement.stat().st_size if replacement else entry.size
        if size > 0xFFFFFFFF: raise ValueError("replacement exceeds the 32-bit asset-size field")
        sectors = (size + SECTOR - 1) // SECTOR
        plan.append((entry, replacement, next_sector, sectors, size))
        next_sector += sectors
    game_size = archive.game.stat().st_size
    if next_sector * SECTOR > game_size:
        raise ValueError("rebuilt assets exceed the original GAME.DAT capacity")
    root.mkdir(parents=True, exist_ok=True)
    decoded = bytearray(archive.decoded)
    info_temp = game_temp = None
    try:
        with tempfile.NamedTemporaryFile(prefix="GAME.", suffix=".tmp", dir=root, delete=False) as output:
            game_temp = Path(output.name)
            with archive.game.open("rb") as source:
                for entry, replacement, sector, sectors, size in plan:
                    struct.pack_into("<III", decoded, HEADER + entry.index * RECORD + 36, sector, sectors, size)
                    if replacement:
                        with replacement.open("rb") as changed: exact_copy(changed, output, size)
                    else:
                        source.seek(entry.offset)
                        exact_copy(source, output, size)
                    padding = sectors * SECTOR - size
                    if size == entry.size and sectors == entry.sectors:
                        source.seek(entry.offset + entry.size)
                        exact_copy(source, output, padding)
                    else:
                        output.write(bytes(padding))
                # Keep the original total size and untouched bytes after the new
                # indexed region, including the sample's 35 MiB reserve.
                source.seek(output.tell())
                exact_copy(source, output, game_size - output.tell())
        with tempfile.NamedTemporaryFile(prefix="INFO.", suffix=".tmp", dir=root, delete=False) as output:
            info_temp = Path(output.name)
            output.write(encode_info(decoded))
        game_temp.replace(out_game); game_temp = None
        info_temp.replace(out_info); info_temp = None
    finally:
        for path in [info_temp, game_temp]:
            if path and path.exists(): path.unlink()
    print("Wrote %s and %s; original archive sizes retained" % (out_info, out_game))


def create_from_dir(region, key_override, asset_dir, out_info, out_game=None):
    asset_dir = Path(asset_dir)
    out_info = Path(out_info)
    out_game = Path(out_game) if out_game else None

    if not asset_dir.is_dir():
        raise ValueError("asset directory does not exist: " + str(asset_dir))
    if region is None and key_override is None:
        raise ValueError("region or codec key is required")
    if key_override is not None and (len(key_override) != 16 or key_override[1:] != MAGIC[1:]):
        raise ValueError("codec key must be 16 bytes ending in www.arika.co.jp")
    if out_game and out_info.resolve() == out_game.resolve():
        raise ValueError("output INFO.DAT and GAME.DAT must differ")
    for output in (out_info, out_game):
        if output is not None and output.resolve().is_relative_to(asset_dir.resolve()):
            raise ValueError("archive output must be outside the source asset directory")

    # Collect all regular files under asset_dir, keyed by relative POSIX path.
    files = []
    for path in sorted(asset_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(asset_dir).as_posix()
            relative_name(rel)
            size = path.stat().st_size
            files.append((rel, path, size))

    # Sort by name for deterministic sector ordering.
    files.sort(key=lambda f: f[0])
    names = set()
    for rel, _path, _size in files:
        folded = rel.casefold()
        if folded in names:
            raise ValueError("duplicate/case-colliding asset name: " + rel)
        names.add(folded)

    if region is not None:
        byte_0 = region_byte0(region)
    else:
        byte_0 = key_override[0]

    count = len(files)
    decoded = make_decoded_info(byte_0, count)
    needed = HEADER + count * RECORD
    if len(decoded) < needed:
        decoded.extend(b"\0" * (needed - len(decoded)))

    next_sector = 0
    planned = []
    for index, (rel, path, size) in enumerate(files):
        if size > 0xFFFFFFFF:
            raise ValueError("asset size exceeds the 32-bit field: " + rel)
        sectors = (size + SECTOR - 1) // SECTOR
        write_info_record(decoded, index, rel, 0, next_sector, sectors, size)
        if next_sector > 0xFFFFFFFF or sectors > 0xFFFFFFFF or next_sector + sectors > 0x100000000:
            raise ValueError("archive sector offset exceeds the 32-bit field: " + rel)
        planned.append((index, rel, path, next_sector, sectors, size))
        next_sector += sectors

    game_size = next_sector * SECTOR

    if key_override is not None:
        encoded = encode_info_with_key(key_override, decoded)
    else:
        encoded = encode_info(decoded)

    root = out_info.parent
    root.mkdir(parents=True, exist_ok=True)

    if out_game:
        game_root = out_game.parent
        game_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="GAME.", suffix=".tmp", dir=game_root, delete=False) as output:
            game_temp = Path(output.name)
            with open(game_temp, "wb") as out:
                for _index, _rel, path, _sector, sectors, size in planned:
                    with open(path, "rb") as source:
                        exact_copy(source, out, size)
                    padding = sectors * SECTOR - size
                    if padding > 0:
                        out.write(bytes(padding))
                out.truncate(game_size)
        game_temp.replace(out_game)

    info_root = out_info.parent
    info_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="INFO.", suffix=".tmp", dir=info_root, delete=False) as output:
        info_temp = Path(output.name)
        output.write(encoded)
    info_temp.replace(out_info)

    msg = "Wrote %s" % out_info
    if out_game:
        msg += " and %s" % out_game
    print(msg)


def container(data):
    if len(data) < 32 or data[:4] not in [b"FPIX", b"FMDL"]:
        raise ValueError("expected FPIX or FMDL")
    size, count, version = struct.unpack_from("<III", data, 4)
    if size != len(data) or not count or 32 + count * 4 > size:
        raise ValueError("invalid container header")
    offsets = struct.unpack_from("<" + "I" * count, data, 32)
    if offsets[0] != 32 + count * 4:
        raise ValueError("unexpected container table layout")
    chunks = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else size
        if not offset < end <= size or end - offset < 8:
            raise ValueError("invalid container chunk extent")
        chunk_size, = struct.unpack_from("<I", data, offset + 4)
        if chunk_size != end - offset:
            raise ValueError("chunk size does not match offset table")
        chunks.append(dict(index=index, magic=data[offset:offset + 4].decode("ascii"), offset=offset, size=chunk_size))
    return dict(magic=data[:4].decode("ascii"), size=size, version=version, chunks=chunks)


def split_container(path, destination, overwrite=False):
    data = Path(path).read_bytes()
    metadata = container(data)
    root = Path(destination)
    files = [(root / "container.json", json.dumps(metadata, indent=2).encode())]
    for chunk in metadata["chunks"]:
        tag = chunk["magic"]
        if not tag.isascii() or not tag.isalnum(): raise ValueError("unsafe chunk tag")
        body = data[chunk["offset"]:chunk["offset"] + chunk["size"]]
        files.append((root / ("%04d.%s" % (chunk["index"], tag)), body))
        if tag == "XPIX" and body[32:36] == b"TIM2": files.append((root / ("%04d.tm2" % chunk["index"]), body[32:]))
    for filename, _ in files:
        if filename.exists() and not overwrite: raise ValueError("output exists: " + str(filename))
    root.mkdir(parents=True, exist_ok=True)
    for filename, body in files: filename.write_bytes(body)
    print("Split %d chunks to %s" % (len(metadata["chunks"]), root))


def motion_archive(data):
    if len(data) < 16 or data[:6] != b"RFSML3": raise ValueError("expected RFSM/L3")
    count, = struct.unpack_from("<H", data, 6)
    shared, shared_end = struct.unpack_from("<II", data, 8)
    if shared != 16 + count * 32 or not shared + 16 <= shared_end <= len(data):
        raise ValueError("invalid RFSM shared block")
    shared_count, bones, names, bindings, flags = struct.unpack_from("<HHIII", data, shared)
    if shared_count != count or names != shared + 16 or bindings != names + bones * 16 or shared_end != flags + bones or not bindings <= flags <= len(data):
        raise ValueError("unexpected RFSM skeleton layout")
    bone_list = [dict(index=index, name=data[names + index * 16:names + (index + 1) * 16].split(b"\0", 1)[0].decode("cp932"), flags=data[flags + index]) for index in range(bones)]
    motions = []
    for index in range(count):
        at = 16 + index * 32
        name = data[at:at + 16].split(b"\0", 1)[0].decode("cp932")
        relative_name(name)
        offset, size, unknown, format_value = struct.unpack_from("<4I", data, at + 16)
        if offset < shared_end or offset + size > len(data) or size < 8 or data[offset:offset + 4] != b"MOT2" or struct.unpack_from("<I", data, offset + 4)[0] != size:
            raise ValueError("invalid MOT2 extent")
        motions.append(dict(index=index, name=name, offset=offset, size=size, unknown=unknown, format_value=format_value))
    return dict(magic="RFSM", tag="L3", count=count, shared_offset=shared, shared_end=shared_end,
        bone_names_offset=names, bindings_offset=bindings, bone_flags_offset=flags, bones=bone_list, motions=motions)


def split_motion_archive(path, destination, overwrite=False):
    data = Path(path).read_bytes()
    metadata = motion_archive(data)
    root = Path(destination)
    files = [(root / "motion_archive.json", json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8")),
        (root / "shared.bin", data[metadata["shared_offset"]:(metadata["shared_end"] + 15) & ~15])]
    for motion in metadata["motions"]:
        name = "%04d_%s" % (motion["index"], PurePosixPath(motion["name"]).name)
        files.append((root / name, data[motion["offset"]:motion["offset"] + motion["size"]]))
    for filename, _ in files:
        if filename.exists() and not overwrite: raise ValueError("output exists: " + str(filename))
    root.mkdir(parents=True, exist_ok=True)
    for filename, body in files: filename.write_bytes(body)
    print("Split %d MOT2 motions and %d bone names to %s" % (metadata["count"], len(metadata["bones"]), root))


def tim2_rgba(data, linear_clut=False):
    if len(data) < 16 or data[:4] != b"TIM2": raise ValueError("expected TIM2")
    version, format_value, pictures = struct.unpack_from("<BBH", data, 4)
    if format_value not in (0, 1) or pictures != 1: raise ValueError("PNG preview supports a single TIM2 picture")
    at = 128 if format_value == 1 else 16
    if at + 48 > len(data): raise ValueError("truncated TIM2 picture")
    total, clut_size, image_size, header_size, colors, picture_format, mipmaps, clut_type, image_type, width, height = struct.unpack_from("<IIIHHBBBBHH", data, at)
    if mipmaps != 1 or not width or not height or header_size < 48 or header_size + image_size + clut_size > total or at + total > len(data):
        raise ValueError("unsupported/truncated TIM2 layout")
    image = data[at + header_size:at + header_size + image_size]
    palette = data[at + header_size + image_size:at + header_size + image_size + clut_size]
    output = bytearray()
    if image_type == 3:
        if len(image) != width * height * 4: raise ValueError("unexpected RGBA32 image size")
        for index in range(0, len(image), 4): output += image[index:index + 3] + bytes([min(255, image[index + 3] * 2)])
    elif image_type in (4, 5):
        if (clut_type & 0x3F) != 3 or len(palette) < colors * 4: raise ValueError("preview requires RGBA32 palette entries")
        expected = (width * height + 1) // 2 if image_type == 4 else width * height
        if len(image) != expected: raise ValueError("unexpected indexed image size")
        for pixel in range(width * height):
            color = image[pixel // 2] >> ((pixel & 1) * 4) & 15 if image_type == 4 else image[pixel]
            if image_type == 5 and not linear_clut and not clut_type & 0x80:
                color = (color & ~0x18) | ((color & 8) << 1) | ((color & 16) >> 1)
            if color >= colors: raise ValueError("palette index out of range")
            entry = palette[color * 4:color * 4 + 4]
            output += entry[:3] + bytes([min(255, entry[3] * 2)])
    else: raise ValueError("preview supports the sample's RGBA32, indexed4 and indexed8 image types")
    return width, height, bytes(output)


def tim2_png_bytes(data, linear_clut=False):
    """Decode one TIM2 picture to PNG bytes without temporary files."""
    width, height, rgba = tim2_rgba(data, linear_clut)

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", binascii.crc32(tag + body) & 0xFFFFFFFF)

    scanlines = b"".join(b"\0" + rgba[row * width * 4:(row + 1) * width * 4] for row in range(height))
    return (b"\x89PNG\r\n\x1a\n" +
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
        chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def tim2_png(path, output, linear_clut=False):
    if Path(path).resolve() == Path(output).resolve(): raise ValueError("PNG output must differ from input")
    Path(output).write_bytes(tim2_png_bytes(Path(path).read_bytes(), linear_clut))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    listing = subs.add_parser("list")
    listing.add_argument("info"); listing.add_argument("--game"); listing.add_argument("--json", type=Path); listing.add_argument("--csv", type=Path)
    decoding = subs.add_parser("decode-info")
    decoding.add_argument("info", type=Path); decoding.add_argument("output", type=Path)
    encoding = subs.add_parser("encode-info")
    encoding.add_argument("info", type=Path); encoding.add_argument("output", type=Path)
    extracting = subs.add_parser("extract")
    extracting.add_argument("info"); extracting.add_argument("game"); extracting.add_argument("output"); extracting.add_argument("--pattern", action="append", default=[]); extracting.add_argument("--overwrite", action="store_true")
    repacking = subs.add_parser("repack")
    repacking.add_argument("--info", default=None, help="seed INFO.DAT (omit with --version/--key to build without a seed)")
    repacking.add_argument("--game", default=None, help="seed GAME.DAT (required when rebuilding from a seed)")
    repacking.add_argument("output")
    repacking.add_argument("--replacements", required=True)
    repacking.add_argument("--version", help="region name (eu-beta, eu, usa, jpn, db1) to build INFO.DAT without a seed")
    repacking.add_argument("--key", help="raw 16-byte codec key as hex (overrides --version)")
    splitting = subs.add_parser("split-container")
    splitting.add_argument("input"); splitting.add_argument("output"); splitting.add_argument("--overwrite", action="store_true")
    motions = subs.add_parser("split-rfsm")
    motions.add_argument("input"); motions.add_argument("output"); motions.add_argument("--overwrite", action="store_true")
    preview = subs.add_parser("tim2-png")
    preview.add_argument("input"); preview.add_argument("output"); preview.add_argument("--linear-clut", action="store_true")
    args = parser.parse_args()
    try:
        if args.command in ("decode-info", "encode-info"):
            if args.output.resolve() == args.info.resolve(): raise ValueError("decoded output must differ from input")
            transform = decode_info if args.command == "decode-info" else encode_info
            args.output.write_bytes(transform(args.info.read_bytes()))
        elif args.command == "split-container": split_container(args.input, args.output, args.overwrite)
        elif args.command == "split-rfsm": split_motion_archive(args.input, args.output, args.overwrite)
        elif args.command == "tim2-png": tim2_png(args.input, args.output, args.linear_clut)
        else:
            if args.command == "repack" and args.info is None:
                # Build INFO.DAT from scratch without a seed.
                key_bytes = None
                if args.key:
                    key_bytes = bytes.fromhex(args.key.strip())
                    if len(key_bytes) != 16:
                        raise ValueError("--key must be exactly 16 bytes (32 hex chars)")
                if key_bytes is None:
                    if args.version is None:
                        raise ValueError("--version is required when no seed INFO.DAT is provided")
                    region = args.version
                else:
                    region = None
                out_info_path = Path(args.output) / "INFO.DAT"
                if args.game is not None:
                    raise ValueError("--game is a seed archive; omit it when rebuilding without --info")
                out_game_path = Path(args.output) / "GAME.DAT"
                create_from_dir(region, key_bytes, args.replacements, out_info_path, out_game_path)
            else:
                archive = Archive(args.info, args.game)
                if args.command == "extract": extract(archive, args.output, args.pattern, args.overwrite)
                elif args.command == "repack": rebuild(archive, args.output, args.replacements)
                else:
                    rows = archive.manifest()
                    if args.json: args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
                    if args.csv:
                        with args.csv.open("w", encoding="utf-8-sig", newline="") as out:
                            writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["index", "name"])
                            writer.writeheader(); writer.writerows(rows)
                    if not args.json and not args.csv:
                        for row in rows: print("%4d %10d %10d %s" % (row["index"], row["offset"], row["size"], row["name"]))
                    print("%d assets; indexed extent %d bytes" % (len(rows), archive.used_bytes), file=sys.stderr)
    except (OSError, ValueError, UnicodeError, struct.error) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
