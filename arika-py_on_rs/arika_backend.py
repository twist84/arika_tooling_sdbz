#!/usr/bin/env python3
"""ctypes loader for the arika_backend cdylib.

Loads the shared library built by build.py and declares C ABI signatures.
Raises BackendError (subclass of RuntimeError) on any backend failure.
No silent pure-Python fallback: if the library is missing, importing fails.
"""
import ctypes
import json
import os
import sys
import weakref
from pathlib import Path


class BackendError(ValueError):
    """Raised when the Rust backend reports an error."""


class ArikaBuffer(ctypes.Structure):
    """Opaque binary/JSON payload returned by the backend."""
    _fields_ = [
        ("ptr", ctypes.c_void_p),
        ("len", ctypes.c_size_t),
    ]


def _library_path():
    here = Path(__file__).resolve().parent
    if sys.platform == "win32":
        name = "arika_backend.dll"
    elif sys.platform == "darwin":
        name = "libarika_backend.dylib"
    else:
        name = "libarika_backend.so"
    path = here / name
    if not path.exists():
        raise RuntimeError(
            "arika_backend shared library not found at "
            f"{path}; run build.py first"
        )
    return path


_lib = ctypes.CDLL(str(_library_path()))

# --- error reporting -------------------------------------------------------
_lib.arika_last_error.restype = ctypes.c_char_p
_lib.arika_last_error.argtypes = []


def _last_error():
    msg = _lib.arika_last_error()
    if msg:
        return msg.decode("utf-8", "replace")
    return "unknown backend error"


def _raise_null(result, func, args):
    """ctypes errcheck: raise BackendError when a pointer return is null."""
    if not result:
        raise BackendError(f"{func.__name__}: {_last_error()}")
    return result


def _raise_negative(result, func, args):
    """ctypes errcheck: raise BackendError when an i32 return is negative."""
    if result < 0:
        raise BackendError(f"{func.__name__}: {_last_error()}")
    return result


def _free_buffer(buf):
    if buf and buf.ptr:
        _lib.arika_free_buffer(buf)


def _call_ptr(func, *args):
    """Call a function returning *mut c_char (JSON/payload). Return decoded str."""
    buf = func(*args)
    if not buf.ptr:
        raise BackendError(f"{func.__name__}: {_last_error()}")
    try:
        raw = ctypes.string_at(buf.ptr, buf.len)
        return raw.decode("utf-8")
    finally:
        _lib.arika_free_buffer(buf)


def _call_bytes(func, data):
    """Call a backend function taking (input: *const u8, len: usize)."""
    arr = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    ptr = ctypes.cast(arr, ctypes.c_void_p)
    return _call_ptr(func, ptr, len(data))


def _call_buffer(func, data):
    """Call a backend function returning ArikaBuffer (binary payload)."""
    arr = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    ptr = ctypes.cast(arr, ctypes.c_void_p)
    buf = func(ptr, len(data))
    if not buf.ptr:
        raise BackendError(f"{func.__name__}: {_last_error()}")
    try:
        return ctypes.string_at(buf.ptr, buf.len)
    finally:
        _lib.arika_free_buffer(buf)


# --- function signatures ----------------------------------------------------

# Archive
_lib.arika_archive_open.restype = ctypes.c_size_t
_lib.arika_archive_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

_lib.arika_archive_free.restype = None
_lib.arika_archive_free.argtypes = [ctypes.c_size_t]

_lib.arika_archive_entries.restype = ArikaBuffer
_lib.arika_archive_entries.argtypes = [ctypes.c_size_t]

_lib.arika_archive_used_bytes.restype = ctypes.c_uint64
_lib.arika_archive_used_bytes.argtypes = [ctypes.c_size_t]

_lib.arika_archive_extract.restype = ctypes.c_int
_lib.arika_archive_extract.argtypes = [
    ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
]
_lib.arika_archive_extract.errcheck = _raise_negative

_lib.arika_archive_rebuild.restype = ctypes.c_int
_lib.arika_archive_rebuild.argtypes = [
    ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p,
]
_lib.arika_archive_rebuild.errcheck = _raise_negative

_lib.arika_decode_info.restype = ArikaBuffer
_lib.arika_decode_info.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_encode_info.restype = ArikaBuffer
_lib.arika_encode_info.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

# CHT
_lib.arika_parse_cht.restype = ArikaBuffer
_lib.arika_parse_cht.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_cht_lookup.restype = ArikaBuffer
_lib.arika_cht_lookup.argtypes = [
    ctypes.c_char_p, ctypes.c_uint, ctypes.c_size_t,
]

_lib.arika_runtime_motion_name.restype = ArikaBuffer
_lib.arika_runtime_motion_name.argtypes = [ctypes.c_char_p]

# Clock
_lib.arika_clock_init.restype = ArikaBuffer
_lib.arika_clock_init.argtypes = [ctypes.c_char_p]

_lib.arika_clock_snapshot.restype = ArikaBuffer
_lib.arika_clock_snapshot.argtypes = [
    ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
]

_lib.arika_clock_step.restype = ArikaBuffer
_lib.arika_clock_step.argtypes = [ctypes.c_char_p, ctypes.c_float]

# Faces
_lib.arika_parse_face.restype = ArikaBuffer
_lib.arika_parse_face.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_face_catalog.restype = ArikaBuffer
_lib.arika_face_catalog.argtypes = [ctypes.c_char_p]

# Audio
_lib.arika_sample_rate.restype = ctypes.c_uint
_lib.arika_sample_rate.argtypes = [ctypes.c_uint]

_lib.arika_decode_adpcm.restype = ArikaBuffer
_lib.arika_decode_adpcm.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_encode_adpcm.restype = ArikaBuffer
_lib.arika_encode_adpcm.argtypes = [
    ctypes.c_void_p, ctypes.c_size_t,
    ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_size_t,
]

_lib.arika_ase_samples.restype = ArikaBuffer
_lib.arika_ase_samples.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_ams_channels.restype = ArikaBuffer
_lib.arika_ams_channels.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_read_wav.restype = ArikaBuffer
_lib.arika_read_wav.argtypes = [ctypes.c_void_p, ctypes.c_size_t]

_lib.arika_write_wav.restype = ArikaBuffer
_lib.arika_write_wav.argtypes = [ctypes.c_char_p, ctypes.c_uint]

_lib.arika_pitch_for_rate.restype = ctypes.c_int
_lib.arika_pitch_for_rate.argtypes = [ctypes.c_uint, ctypes.c_uint]

# RNG
_lib.arika_next_rng.restype = ctypes.c_uint64
_lib.arika_next_rng.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint)]

# --- convenience wrappers ---------------------------------------------------

def decode_info(data):
    return _call_buffer(_lib.arika_decode_info, data)


def encode_info(data):
    return _call_buffer(_lib.arika_encode_info, data)


def parse_cht(data):
    return json.loads(_call_bytes(_lib.arika_parse_cht, data))


def cht_lookup(doc_json, motion_id, variant):
    return json.loads(
        _call_ptr(
            _lib.arika_cht_lookup,
            json.dumps(doc_json).encode("utf-8"),
            motion_id,
            variant,
        )
    )


def runtime_motion_name(name):
    buf = _lib.arika_runtime_motion_name(name.encode("utf-8"))
    if not buf.ptr:
        raise BackendError(f"runtime_motion_name: {_last_error()}")
    try:
        return json.loads(ctypes.string_at(buf.ptr, buf.len).decode("utf-8"))
    finally:
        _lib.arika_free_buffer(buf)


def parse_face(data):
    return json.loads(_call_bytes(_lib.arika_parse_face, data))


def face_catalog(directory):
    buf = _lib.arika_face_catalog(directory.encode("utf-8"))
    if not buf.ptr:
        raise BackendError(f"face_catalog: {_last_error()}")
    try:
        return json.loads(ctypes.string_at(buf.ptr, buf.len).decode("utf-8"))
    finally:
        _lib.arika_free_buffer(buf)


def sample_rate(pitch):
    return _lib.arika_sample_rate(pitch)


def decode_adpcm(data):
    return json.loads(_call_bytes(_lib.arika_decode_adpcm, data))


def encode_adpcm(samples, first_flag, last_flag, min_frames):
    raw = b"".join(s.to_bytes(2, "little", signed=True) for s in samples)
    arr = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    ptr = ctypes.cast(arr, ctypes.c_void_p)
    buf = _lib.arika_encode_adpcm(ptr, len(raw), first_flag, last_flag, min_frames)
    if not buf.ptr:
        raise BackendError(f"encode_adpcm: {_last_error()}")
    try:
        return ctypes.string_at(buf.ptr, buf.len)
    finally:
        _lib.arika_free_buffer(buf)


def ase_samples(data):
    return json.loads(_call_bytes(_lib.arika_ase_samples, data))


def ams_channels(data):
    return json.loads(_call_bytes(_lib.arika_ams_channels, data))


def read_wav(data):
    return json.loads(_call_bytes(_lib.arika_read_wav, data))


def write_wav(channels, sample_rate):
    payload = json.dumps(channels).encode("utf-8")
    buf = _lib.arika_write_wav(payload, sample_rate)
    if not buf.ptr:
        raise BackendError(f"write_wav: {_last_error()}")
    try:
        return ctypes.string_at(buf.ptr, buf.len)
    finally:
        _lib.arika_free_buffer(buf)


def pitch_for_rate(rate, original_pitch):
    result = _lib.arika_pitch_for_rate(rate, original_pitch)
    if result < 0:
        raise BackendError(f"pitch_for_rate: {_last_error()}")
    return result


def next_rng(state):
    value = ctypes.c_uint(0)
    next_state = _lib.arika_next_rng(state, ctypes.byref(value))
    return next_state, value.value


class Archive:
    """Opaque handle to a Rust arika_core::dat::Archive.

    Lifetime is managed with weakref.finalize; the backend frees the handle
    when the Python object is garbage collected.
    """

    def __init__(self, info, game=None):
        self.info = Path(info)
        self.game = Path(game) if game else None
        game_b = str(self.game).encode("utf-8") if self.game else None
        handle = _lib.arika_archive_open(
            str(self.info).encode("utf-8"), game_b
        )
        if not handle:
            raise BackendError(f"archive_open: {_last_error()}")
        self._handle = handle
        self._entries = None
        self._used_bytes = None
        weakref.finalize(self, _lib.arika_archive_free, self._handle)

    @property
    def entries(self):
        if self._entries is None:
            raw = json.loads(_call_ptr(_lib.arika_archive_entries, self._handle))
            self._entries = [Entry(**e) for e in raw]
        return self._entries

    @property
    def used_bytes(self):
        if self._used_bytes is None:
            self._used_bytes = _lib.arika_archive_used_bytes(self._handle)
        return self._used_bytes

    def manifest(self):
        result = []
        source = self.game.open("rb") if self.game else None
        try:
            for entry in self.entries:
                row = dict(
                    index=entry.index,
                    name=entry.name,
                    unknown=entry.unknown,
                    sector=entry.sector,
                    offset=entry.offset,
                    sectors=entry.sectors,
                    size=entry.size,
                )
                if source:
                    source.seek(entry.offset)
                    signature = source.read(min(4, entry.size))
                    row["magic_hex"] = signature.hex()
                    row["magic_ascii"] = "".join(
                        chr(c) if 32 <= c < 127 else "." for c in signature
                    )
                result.append(row)
        finally:
            if source:
                source.close()
        return result

    def extract(self, destination, patterns=(), overwrite=False):
        patterns_bytes = json.dumps(list(patterns)).encode("utf-8")
        _lib.arika_archive_extract(
            self._handle,
            str(Path(destination)).encode("utf-8"),
            patterns_bytes,
            1 if overwrite else 0,
        )

    def rebuild(self, destination, replacements=None):
        replacements_b = (
            str(replacements).encode("utf-8") if replacements else None
        )
        _lib.arika_archive_rebuild(
            self._handle,
            str(Path(destination)).encode("utf-8"),
            replacements_b,
        )

    def extract(self, destination, patterns=(), overwrite=False):
        patterns_bytes = json.dumps(list(patterns)).encode("utf-8")
        _lib.arika_archive_extract(
            self._handle,
            str(Path(destination)).encode("utf-8"),
            patterns_bytes,
            1 if overwrite else 0,
        )


class Entry:
    def __init__(self, index, name, unknown, sector, sectors, size, offset=0):
        self.index = index
        self.name = name
        self.unknown = unknown
        self.sector = sector
        self.sectors = sectors
        self.size = size
        self._offset = offset

    @property
    def offset(self):
        return self._offset

    def __repr__(self):
        return f"Entry(index={self.index}, name={self.name!r}, size={self.size})"
