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

_lib.arika_archive_capacity.restype = ArikaBuffer
_lib.arika_archive_capacity.argtypes = [ctypes.c_size_t]

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

# Gizmo quaternion math (glTF XYZW, f64)
_quaternion4 = ctypes.c_double * 4
_lib.arika_quaternion_multiply.restype = ctypes.c_int
_lib.arika_quaternion_multiply.argtypes = [
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
_lib.arika_quaternion_multiply.errcheck = _raise_negative

# Editor transform math: all inputs and outputs are f64 arrays.
for _name, _count in (
    ("arika_euler_to_quaternion", 1),
    ("arika_quaternion_to_euler", 1),
    ("arika_quaternion_inverse", 1),
    ("arika_matrix_multiply", 2),
    ("arika_matrix_inverse", 1),
    ("arika_matrix_local", 3),
):
    _fn = getattr(_lib, _name)
    _fn.restype = ctypes.c_int
    _fn.argtypes = [ctypes.POINTER(ctypes.c_double)] * (_count + 1)
    _fn.errcheck = _raise_negative


def _float_array(values, size):
    if len(values) != size:
        raise ValueError(f"expected {size} components")
    return (ctypes.c_double * size)(*(float(value) for value in values))


def _transform_call(name, output_size, *inputs):
    args = [_float_array(values, length) for values, length in inputs]
    result = (ctypes.c_double * output_size)()
    getattr(_lib, name)(*args, result)
    return list(result)


def euler_to_quaternion(euler):
    return _transform_call("arika_euler_to_quaternion", 4, (euler, 3))


def quaternion_to_euler(quaternion):
    return tuple(_transform_call("arika_quaternion_to_euler", 3, (quaternion, 4)))


def quaternion_inverse(quaternion):
    return _transform_call("arika_quaternion_inverse", 4, (quaternion, 4))


def matrix_inverse(matrix):
    if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
        raise ValueError("expected a 4x4 matrix")
    result = _transform_call(
        "arika_matrix_inverse", 16,
        ([value for row in matrix for value in row], 16),
    )
    return [result[index:index + 4] for index in range(0, 16, 4)]


def matrix_local(translation, rotation, scale):
    result = _transform_call(
        "arika_matrix_local", 16,
        (translation, 3), (rotation, 4), (scale, 3),
    )
    return [result[index:index + 4] for index in range(0, 16, 4)]


def matrix_multiply(a, b):
    if len(a) != 4 or len(b) != 4 or any(len(row) != 4 for row in (*a, *b)):
        raise ValueError("expected two 4x4 matrices")
    result = _transform_call(
        "arika_matrix_multiply", 16,
        ([value for row in a for value in row], 16),
        ([value for row in b for value in row], 16),
    )
    return [result[index:index + 4] for index in range(0, 16, 4)]


# Batch skeleton world matrices. Input: i32 parents and f64 packed TRS.
_lib.arika_skeleton_world_matrices.restype = ctypes.c_int
_lib.arika_skeleton_world_matrices.argtypes = [
    ctypes.POINTER(ctypes.c_int32),
    ctypes.POINTER(ctypes.c_double),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_double),
]


def skeleton_world_matrices(nodes):
    """Evaluate row-major world matrices for all skeleton nodes in one native call."""
    count = len(nodes)
    if not count:
        return []
    if count > 100_000:
        raise ValueError("skeleton exceeds 100000 nodes")
    parents = (ctypes.c_int32 * count)()
    transforms = (ctypes.c_double * (count * 10))()
    for index, node in enumerate(nodes):
        parent = node['parent']
        if not isinstance(parent, int) or parent < -1 or parent >= count:
            raise ValueError("invalid skeleton parent index")
        parents[index] = parent
        values = (
            list(node['translation']) + list(node['rotation']) + list(node['scale'])
        )
        if len(values) != 10:
            raise ValueError("expected translation xyz, quaternion xyzw and scale xyz")
        for component, value in enumerate(values):
            transforms[index * 10 + component] = float(value)
    result = (ctypes.c_double * (count * 16))()
    if _lib.arika_skeleton_world_matrices(parents, transforms, count, result) != 0:
        raise ValueError("skeleton parent cycle or invalid/nonfinite transform")
    return [
        [[result[i * 16 + r * 4 + c] for c in range(4)] for r in range(4)]
        for i in range(count)
    ]


# MOT2 pose sampler: descriptors u32[track_count * 2], times f64[keys],
# values f64[keys * 4], output f64[node_count * 10].
_lib.arika_motion_sample_pose.restype = ctypes.c_int
_lib.arika_motion_sample_pose.argtypes = [
    ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
    ctypes.c_size_t, ctypes.c_double, ctypes.POINTER(ctypes.c_double),
]


def motion_sample_pose(motion, time):
    """Sample each MOT2 bone's local TRS at seconds using one native call.

    Returns nodes with translation, rotation (glTF XYZW), and scale.
    Values before or after authored key times clamp to the end keys.
    """
    nodes = motion['nodes']
    if not nodes:
        return []
    if len(nodes) > 100_000:
        raise ValueError("motion exceeds 100000 bones")
    descriptions = []
    times = []
    values = []
    for node in nodes:
        for path, components in (('translation', 3), ('rotation', 4), ('scale', 3)):
            track = node['tracks'][path]
            t = list(track['times'])
            v = list(track['values'])
            if not t or len(t) != len(v):
                raise ValueError("track keys and values must have equal nonzero lengths")
            descriptions.extend((len(times), len(t)))
            times.extend(t)
            for item in v:
                if len(item) != components:
                    raise ValueError("unexpected MOT2 track component count")
                values.extend(item if components == 4 else [*item, 0.0])
    if len(times) > 5_000_000:
        raise ValueError("motion exceeds 5000000 keys")
    descriptors_buf = (ctypes.c_uint32 * len(descriptions))(*descriptions)
    times_buf = (ctypes.c_double * len(times))(*times)
    values_buf = (ctypes.c_double * len(values))(*values)
    output = (ctypes.c_double * (len(nodes) * 10))()
    if _lib.arika_motion_sample_pose(
        descriptors_buf, len(descriptions) // 2, times_buf, values_buf,
        len(times), float(time), output,
    ) != 0:
        raise ValueError("invalid MOT2 time, keys, or quaternion")
    return [
        dict(
            translation=list(output[i*10:i*10+3]),
            rotation=list(output[i*10+3:i*10+7]),
            scale=list(output[i*10+7:i*10+10]),
        )
        for i in range(len(nodes))
    ]


# --- convenience wrappers ---------------------------------------------------
def quaternion_multiply(a, b):
    """Multiply two glTF XYZW quaternions using native f64 math."""
    if len(a) != 4 or len(b) != 4:
        raise ValueError("expected two four-component quaternions")
    lhs = _quaternion4(*(float(v) for v in a))
    rhs = _quaternion4(*(float(v) for v in b))
    output = _quaternion4()
    _lib.arika_quaternion_multiply(lhs, rhs, output)
    return list(output)




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
        self._capacity = None
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

    @property
    def capacity(self):
        """Physical INFO.DAT record capacity, not a verified game-side limit."""
        if self._capacity is None:
            self._capacity = json.loads(_call_ptr(_lib.arika_archive_capacity, self._handle))
        return self._capacity

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
