//! C ABI bridge exposing arika_core functionality to arika-py_on_rs via ctypes.
//! All JSON payloads are UTF-8 bytes returned in ArikaBuffer.
//! Opaque handles are usize; 0 indicates an invalid/null handle.

mod editor_transform;
mod skeleton_batch;

use std::ffi::{CStr, CString};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::raw::{c_char, c_int};
use std::path::{Path, PathBuf};
use std::ptr;
use std::slice;

use arika_core::dat::{Archive, Entry};
use arika_core::error::ArikaError;
use arika_core::ani::parse_ani;
use arika_core::ebz::parse_ebz;
use arika_core::models::{attach_textures, model_to_json, parse_fmdl};
use arika_core::pas::parse_pas;
use arika_core::stages::{parse_hit, hit_to_json, parse_stg, stage_to_json};
use arika_core::spt::parse_spt;
use arika_core::tim2::{decode_tim2, decode_xpix};
use base64::engine::general_purpose::STANDARD as base64_engine;
use base64::Engine as _;
use serde::Serialize;

/// Returned binary / JSON payload: pointer to heap-allocated bytes plus length.
#[repr(C)]
pub struct ArikaBuffer {
    pub ptr: *mut u8,
    pub len: usize,
}

thread_local! {
    static LAST_ERROR: std::cell::RefCell<Option<CString>> = std::cell::RefCell::new(None);
}

fn set_last_error(msg: String) {
    LAST_ERROR.with(|e| {
        *e.borrow_mut() = Some(CString::new(msg).expect("error message contains interior nul"));
    })
}

fn read_c_string(ptr: *const c_char) -> Option<String> {
    if ptr.is_null() {
        return None;
    }
    unsafe { CStr::from_ptr(ptr).to_str().ok().map(|s| s.to_string()) }
}

fn read_bytes<'a>(ptr: *const u8, len: usize) -> Option<&'a [u8]> {
    if ptr.is_null() {
        return None;
    }
    unsafe { Some(slice::from_raw_parts(ptr, len)) }
}

/// Box a Vec<u8> into an ArikaBuffer. The caller must call arika_free_buffer.
fn to_buffer(vec: Vec<u8>) -> ArikaBuffer {
    let len = vec.len();
    let ptr = Box::into_raw(vec.into_boxed_slice()) as *mut u8;
    ArikaBuffer { ptr, len }
}

/// Serialize a Rust value to JSON and return it as an ArikaBuffer.
fn to_json_buffer<T: Serialize>(value: &T) -> ArikaBuffer {
    match serde_json::to_string(value) {
        Ok(json) => {
            let bytes = json.into_bytes();
            let len = bytes.len();
            let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
            ArikaBuffer { ptr, len }
        }
        Err(e) => {
            set_last_error(format!("JSON serialization error: {e}"));
            ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            }
        }
    }
}

fn error_buffer(e: ArikaError) -> ArikaBuffer {
    set_last_error(e.to_string());
    ArikaBuffer {
        ptr: ptr::null_mut(),
        len: 0,
    }
}

#[no_mangle]
pub extern "C" fn arika_free_buffer(buf: ArikaBuffer) {
    if buf.ptr.is_null() {
        return;
    }
    unsafe {
        let _ = Vec::from_raw_parts(buf.ptr, buf.len, buf.len);
    }
}

#[no_mangle]
pub extern "C" fn arika_last_error() -> *const c_char {
    LAST_ERROR.with(|e| {
        e.borrow()
            .as_ref()
            .map_or(ptr::null(), |s| s.as_ptr())
    })
}

// ---------------------------------------------------------------------------
// Archive / DAT
// ---------------------------------------------------------------------------

fn get_archive<'a>(handle: usize) -> Option<&'a Archive> {
    if handle == 0 {
        return None;
    }
    unsafe { Some(&*(handle as *const Archive)) }
}

fn relative_name(name: &str) -> Result<PathBuf, ArikaError> {
    let cleaned = name.replace('\\', "/");
    if cleaned.is_empty()
        || cleaned.starts_with('/')
        || cleaned.split('/').any(|part| part == "..")
        || cleaned.contains(':')
        || cleaned.chars().any(|c| c < ' ')
    {
        return Err(ArikaError::UnsafePath(name.to_string()));
    }
    Ok(PathBuf::from(cleaned))
}

fn simple_glob_match(pattern: &str, name: &str) -> bool {
    let pat: Vec<char> = pattern.chars().collect();
    let nam: Vec<char> = name.chars().collect();
    match_glob(&pat, &nam)
}

fn match_glob(pat: &[char], nam: &[char]) -> bool {
    let mut pi = 0usize;
    let mut ni = 0usize;
    let mut star_p: Option<usize> = None;
    let mut star_n: Option<usize> = None;
    while ni < nam.len() {
        if pi < pat.len() && (pat[pi] == '?' || pat[pi] == nam[ni]) {
            pi += 1;
            ni += 1;
        } else if pi < pat.len() && pat[pi] == '*' {
            star_p = Some(pi);
            star_n = Some(ni);
            pi += 1;
        } else if let (Some(sp), Some(sn)) = (star_p, star_n) {
            pi = sp + 1;
            ni = sn + 1;
            star_n = Some(ni);
        } else {
            return false;
        }
    }
    while pi < pat.len() && pat[pi] == '*' {
        pi += 1;
    }
    pi == pat.len()
}

#[no_mangle]
pub extern "C" fn arika_archive_open(info_path: *const c_char, game_path: *const c_char) -> usize {
    let info = match read_c_string(info_path) {
        Some(s) => s,
        None => {
            set_last_error("info path is null".into());
            return 0;
        }
    };
    let game = read_c_string(game_path);
    match Archive::open(info, game.as_deref()) {
        Ok(archive) => Box::into_raw(Box::new(archive)) as usize,
        Err(e) => {
            set_last_error(e.to_string());
            0
        }
    }
}

#[no_mangle]
pub extern "C" fn arika_archive_free(handle: usize) {
    if handle == 0 {
        return;
    }
    unsafe {
        let _ = Box::from_raw(handle as *mut Archive);
    }
}

#[no_mangle]
pub extern "C" fn arika_archive_entries(handle: usize) -> ArikaBuffer {
    let archive = match get_archive(handle) {
        Some(a) => a,
        None => {
            set_last_error("invalid archive handle".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let entries: Vec<serde_json::Value> = archive
        .entries
        .iter()
        .map(|e| {
            serde_json::json!({
                "index": e.index,
                "name": e.name,
                "unknown": e.unknown,
                "sector": e.sector,
                "sectors": e.sectors,
                "size": e.size,
                "offset": e.offset(),
            })
        })
        .collect();
    to_json_buffer(&entries)
}

/// Return physical INFO table geometry without implying a verified game-side limit.
#[no_mangle]
pub extern "C" fn arika_archive_capacity(handle: usize) -> ArikaBuffer {
    let archive = match get_archive(handle) {
        Some(a) => a,
        None => {
            set_last_error("invalid archive handle".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    to_json_buffer(&serde_json::json!({
        "active_entries": archive.entries.len(),
        "record_capacity": archive.record_capacity(),
        "spare_record_slots": archive.spare_record_slots(),
        "trailing_bytes": archive.record_tail_bytes(),
        "info_size": archive.encoded.len(),
    }))
}

#[no_mangle]
pub extern "C" fn arika_archive_used_bytes(handle: usize) -> u64 {
    match get_archive(handle) {
        Some(a) => a.used_bytes,
        None => {
            set_last_error("invalid archive handle".into());
            0
        }
    }
}

#[no_mangle]
pub extern "C" fn arika_archive_extract(
    handle: usize,
    dest: *const c_char,
    patterns_json: *const c_char,
    overwrite: c_int,
) -> c_int {
    let archive = match get_archive(handle) {
        Some(a) => a,
        None => {
            set_last_error("invalid archive handle".into());
            return -1;
        }
    };
    let dest_str = match read_c_string(dest) {
        Some(s) => s,
        None => {
            set_last_error("dest path is null".into());
            return -1;
        }
    };
    let patterns: Vec<String> = match read_c_string(patterns_json) {
        Some(s) => serde_json::from_str(&s).unwrap_or_default(),
        None => Vec::new(),
    };
    let game = match archive.game_path.as_ref() {
        Some(g) => g,
        None => {
            set_last_error("GAME.DAT not opened".into());
            return -1;
        }
    };

    let dest_path = Path::new(&dest_str);
    if let Err(e) = std::fs::create_dir_all(dest_path) {
        set_last_error(format!("cannot create dest directory: {e}"));
        return -1;
    }
    let canonical_root = match dest_path.canonicalize() {
        Ok(c) => c,
        Err(e) => {
            set_last_error(format!("cannot canonicalize dest: {e}"));
            return -1;
        }
    };

    let mut targets: Vec<(&Entry, PathBuf)> = Vec::new();
    for entry in &archive.entries {
        if !patterns.is_empty() && !patterns.iter().any(|p| simple_glob_match(p, &entry.name)) {
            continue;
        }
        let rel = match relative_name(&entry.name) {
            Ok(r) => r,
            Err(e) => {
                set_last_error(e.to_string());
                return -1;
            }
        };
        let out_path = canonical_root.join(&rel);
        if out_path.exists() && overwrite == 0 {
            set_last_error(format!(
                "output exists; use --overwrite: {}",
                out_path.display()
            ));
            return -1;
        }
        targets.push((entry, out_path));
    }

    let mut file = match std::fs::File::open(game) {
        Ok(f) => f,
        Err(e) => {
            set_last_error(format!("cannot open GAME.DAT: {e}"));
            return -1;
        }
    };

    for (entry, out_path) in &targets {
        if let Some(parent) = out_path.parent() {
            if let Err(e) = std::fs::create_dir_all(parent) {
                set_last_error(format!("cannot create output directory: {e}"));
                return -1;
            }
        }
        if let Err(e) = file.seek(SeekFrom::Start(entry.offset())) {
            set_last_error(format!("seek error: {e}"));
            return -1;
        }
        let mut output = match std::fs::File::create(out_path) {
            Ok(f) => f,
            Err(e) => {
                set_last_error(format!("cannot create output: {e}"));
                return -1;
            }
        };
        let mut remaining = entry.size as u64;
        let mut buffer = [0u8; 1024 * 1024];
        while remaining > 0 {
            let wanted = remaining.min(buffer.len() as u64) as usize;
            if let Err(e) = file.read_exact(&mut buffer[..wanted]) {
                set_last_error(format!("read error: {e}"));
                return -1;
            }
            if let Err(e) = output.write_all(&buffer[..wanted]) {
                set_last_error(format!("write error: {e}"));
                return -1;
            }
            remaining -= wanted as u64;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn arika_archive_rebuild(
    handle: usize,
    dest: *const c_char,
    replacements_dir: *const c_char,
) -> c_int {
    let archive = match get_archive(handle) {
        Some(a) => a,
        None => {
            set_last_error("invalid archive handle".into());
            return -1;
        }
    };
    let dest_str = match read_c_string(dest) {
        Some(s) => s,
        None => {
            set_last_error("dest path is null".into());
            return -1;
        }
    };
    let replacements = read_c_string(replacements_dir);

    let dest_path = Path::new(&dest_str);
    let out_info = dest_path.join("INFO.DAT");
    let out_game = dest_path.join("GAME.DAT");
    let asset_dir: PathBuf = match &replacements {
        Some(s) => Path::new(s.as_str()).to_path_buf(),
        None => dest_path.to_path_buf(),
    };

    match archive.rebuild_from_dir(asset_dir, &out_info, Some(&out_game)) {
        Ok(()) => 0,
        Err(e) => {
            set_last_error(e.to_string());
            -1
        }
    }
}

#[no_mangle]
pub extern "C" fn arika_decode_info(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::info::decode_info(data) {
        Ok(vec) => to_buffer(vec),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_encode_info(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::info::encode_info(data) {
        Ok(vec) => to_buffer(vec),
        Err(e) => error_buffer(e),
    }
}

// ---------------------------------------------------------------------------
// CHT
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn arika_parse_cht(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::cht::parse_cht(data) {
        Ok(doc) => match serde_json::to_vec(&doc) {
            Ok(bytes) => {
                let len = bytes.len();
                let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                ArikaBuffer { ptr, len }
            }
            Err(e) => error_buffer(e.into()),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_cht_lookup(
    doc_json: *const c_char,
    motion_id: u32,
    variant: usize,
) -> ArikaBuffer {
    let doc_str = match read_c_string(doc_json) {
        Some(s) => s,
        None => {
            set_last_error("doc JSON is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let doc: arika_core::cht::ChtDocument = match serde_json::from_str(&doc_str) {
        Ok(d) => d,
        Err(e) => {
            set_last_error(format!("invalid CHT document JSON: {e}"));
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::cht::lookup(&doc, motion_id, variant) {
        Ok(v) => match serde_json::to_vec(&v) {
            Ok(bytes) => {
                let len = bytes.len();
                let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                ArikaBuffer { ptr, len }
            }
            Err(e) => error_buffer(e.into()),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_runtime_motion_name(name: *const c_char) -> ArikaBuffer {
    let name_str = match read_c_string(name) {
        Some(s) => s,
        None => {
            set_last_error("name is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let result = arika_core::cht::runtime_motion_name(&name_str);
    let bytes = result.into_bytes();
    let len = bytes.len();
    let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
    ArikaBuffer { ptr, len }
}

// ---------------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn arika_clock_init(params_json: *const c_char) -> ArikaBuffer {
    let params_str = match read_c_string(params_json) {
        Some(s) => s,
        None => {
            set_last_error("params JSON is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let params: serde_json::Value = match serde_json::from_str(&params_str) {
        Ok(v) => v,
        Err(e) => {
            set_last_error(format!("invalid clock params JSON: {e}"));
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };

    let fps = params["fps"].as_f64().unwrap_or(0.0) as f32;
    let frame_count = params["frame_count"].as_u64().unwrap_or(0) as u16;
    let start_frame = params["start_frame"].as_f64().unwrap_or(0.0) as f32;
    let end_frame = params["end_frame"].as_f64().unwrap_or(-1.0) as f32;
    let speed = params["speed"].as_f64().unwrap_or(1.0) as f32;
    let blend = params["blend"].as_f64().unwrap_or(0.0) as f32;
    let reverse = params["reverse"].as_bool().unwrap_or(false);
    let loop_mode = params["loop"].as_bool().unwrap_or(false);
    let stop_after = params["stop_after"].as_f64().unwrap_or(-1.0) as f32;
    let scale_channels = params["scale_channels"].as_u64().unwrap_or(0) as usize;
    let inherited_blend = params["inherited_blend"]
        .as_array()
        .map(|arr| {
            (
                arr.get(0).and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
                arr.get(1).and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
            )
        });

    match arika_core::clock::NativeClock::new(
        fps,
        frame_count,
        start_frame,
        end_frame,
        speed,
        blend,
        reverse,
        loop_mode,
        stop_after,
        scale_channels,
        inherited_blend,
    ) {
        Ok(clock) => to_json_buffer(&clock),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_clock_snapshot(
    state_json: *const c_char,
    carry: c_int,
    has_wrap: c_int,
    wrap: c_int,
    advanced: c_int,
) -> ArikaBuffer {
    let state_str = match read_c_string(state_json) {
        Some(s) => s,
        None => {
            set_last_error("state JSON is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let clock: arika_core::clock::NativeClock =
        match serde_json::from_str(&state_str) {
            Ok(c) => c,
            Err(e) => {
                set_last_error(format!("invalid clock state JSON: {e}"));
                return ArikaBuffer {
                    ptr: ptr::null_mut(),
                    len: 0,
                };
            }
        };
    let wrap_fraction = if has_wrap != 0 { Some(wrap as f32) } else { None };
    let snapshot = clock.snapshot(carry as f32, wrap_fraction, advanced != 0);
    to_json_buffer(&snapshot)
}

#[no_mangle]
pub extern "C" fn arika_clock_step(state_json: *const c_char, delta: f32) -> ArikaBuffer {    let state_str = match read_c_string(state_json) {
        Some(s) => s,
        None => {
            set_last_error("state JSON is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let mut clock: arika_core::clock::NativeClock =
        match serde_json::from_str(&state_str) {
            Ok(c) => c,
            Err(e) => {
                set_last_error(format!("invalid clock state JSON: {e}"));
                return ArikaBuffer {
                    ptr: ptr::null_mut(),
                    len: 0,
                };
            }
        };
    let snapshot = clock.step(delta as f32);
    let result = serde_json::json!({ "state": clock, "snapshot": snapshot });
    to_json_buffer(&result)
}

// ---------------------------------------------------------------------------
// Faces
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn arika_parse_face(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::faces::parse_face(data) {
        Ok(catalog) => to_json_buffer(&catalog),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_face_catalog(directory: *const c_char) -> ArikaBuffer {
    let dir_str = match read_c_string(directory) {
        Some(s) => s,
        None => {
            set_last_error("directory is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::faces::face_catalog(Path::new(&dir_str)) {
        Ok(catalog) => to_json_buffer(&catalog),
        Err(e) => error_buffer(e),
    }
}

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn arika_sample_rate(pitch: u32) -> u32 {
    arika_core::audio::sample_rate(pitch)
}

#[no_mangle]
pub extern "C" fn arika_decode_adpcm(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::audio::decode_adpcm(data) {
        Ok((pcm, (h1, h2))) => {
            let result = serde_json::json!({
                "pcm": pcm.iter().map(|&s| s as i64).collect::<Vec<i64>>(),
                "h1": h1,
                "h2": h2,
            });
            to_json_buffer(&result)
        }
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_encode_adpcm(
    input: *const u8,
    len: usize,
    first_flag: u8,
    last_flag: u8,
    min_frames: usize,
) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    if len % 2 != 0 {
        set_last_error("PCM input length must be even".into());
        return ArikaBuffer {
            ptr: ptr::null_mut(),
            len: 0,
        };
    }
    let samples: Vec<i16> = data
        .chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect();
    match arika_core::audio::encode_adpcm(&samples, first_flag, last_flag, min_frames) {
        Ok(adpcm) => to_buffer(adpcm),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_ase_samples(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::audio::ase_samples(data) {
        Ok(samples) => {
            let result: Vec<serde_json::Value> = samples
                .into_iter()
                .enumerate()
                .map(|(i, (_pitch, rate, payload))| {
                    serde_json::json!({
                        "index": i,
                        "sample_rate": rate,
                        "payload": base64_engine.encode(&payload),
                    })
                })
                .collect();
            to_json_buffer(&result)
        }
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_ams_channels(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::audio::ams_channels(data) {
        Ok((rate, left, right)) => {
            let result = serde_json::json!({
                "sample_rate": rate,
                "left": base64_engine.encode(&left),
                "right": base64_engine.encode(&right),
            });
            to_json_buffer(&result)
        }
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_read_wav(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::audio::read_wav(data) {
        Ok((rate, channels)) => {
            let result = serde_json::json!({
                "sample_rate": rate,
                "channels": channels.iter().map(|c| c.iter().map(|&s| s as i64).collect::<Vec<i64>>()).collect::<Vec<_>>(),
            });
            to_json_buffer(&result)
        }
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_write_wav(
    channels_json: *const c_char,
    sample_rate: u32,
) -> ArikaBuffer {
    let channels_str = match read_c_string(channels_json) {
        Some(s) => s,
        None => {
            set_last_error("channels JSON is null".into());
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    let channels: Vec<Vec<i16>> = match serde_json::from_str(&channels_str) {
        Ok(c) => c,
        Err(e) => {
            set_last_error(format!("invalid channels JSON: {e}"));
            return ArikaBuffer {
                ptr: ptr::null_mut(),
                len: 0,
            };
        }
    };
    match arika_core::audio::write_wav(&channels, sample_rate) {
        Ok(wav) => to_buffer(wav),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_pitch_for_rate(rate: u32, original_pitch: u32) -> c_int {
    match arika_core::audio::pitch_for_rate(rate, original_pitch) {
        Ok(pitch) => pitch as c_int,
        Err(e) => {
            set_last_error(e.to_string());
            -1
        }
    }
}

// ---------------------------------------------------------------------------
// Model (FMDL) / Texture (TIM2/XPIX)
// ---------------------------------------------------------------------------

#[derive(Serialize)]
struct Tim2Json {
    width: u32,
    height: u32,
    format: String,
    rgba: String, // base64
}

#[no_mangle]
pub extern "C" fn arika_parse_fmdl(
    input: *const u8,
    len: usize,
    name: *const c_char,
) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    let name_str = match read_c_string(name) {
        Some(s) => s,
        None => "model".to_string(),
    };
    match arika_core::models::parse_fmdl(data, &name_str) {
        Ok(model) => match arika_core::models::model_to_json(&model) {
            Ok(json) => {
                let bytes = json.into_bytes();
                let len = bytes.len();
                let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                ArikaBuffer { ptr, len }
            }
            Err(e) => error_buffer(e),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_attach_textures(
    model_json: *const c_char,
    fpix_data: *const u8,
    fpix_len: usize,
) -> ArikaBuffer {
    let model_str = match read_c_string(model_json) {
        Some(s) => s,
        None => {
            set_last_error("model json is null".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    let fpix = match read_bytes(fpix_data, fpix_len) {
        Some(d) => d,
        None => {
            set_last_error("invalid fpix buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    let mut model: arika_core::models::Model = match serde_json::from_str(&model_str) {
        Ok(m) => m,
        Err(e) => {
            set_last_error(format!("invalid model JSON: {e}"));
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::models::attach_textures(&mut model, fpix) {
        Ok(()) => match arika_core::models::model_to_json(&model) {
            Ok(json) => {
                let bytes = json.into_bytes();
                let len = bytes.len();
                let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                ArikaBuffer { ptr, len }
            }
            Err(e) => error_buffer(e),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_parse_fmdl_with_textures(
    input: *const u8,
    len: usize,
    name: *const c_char,
    fpix_data: *const u8,
    fpix_len: usize,
) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    let name_str = match read_c_string(name) {
        Some(s) => s,
        None => "model".to_string(),
    };
    let fpix = match read_bytes(fpix_data, fpix_len) {
        Some(d) => d,
        None => {
            set_last_error("invalid fpix buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::models::parse_fmdl(data, &name_str) {
        Ok(mut model) => match arika_core::models::attach_textures(&mut model, fpix) {
            Ok(()) => match arika_core::models::model_to_json(&model) {
                Ok(json) => {
                    let bytes = json.into_bytes();
                    let len = bytes.len();
                    let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                    ArikaBuffer { ptr, len }
                }
                Err(e) => error_buffer(e),
            },
            Err(e) => error_buffer(e),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_decode_tim2(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::tim2::decode_tim2(data) {
        Ok(img) => {
            let result = Tim2Json {
                width: img.width,
                height: img.height,
                format: format!("{:?}", img.format),
                rgba: base64_engine.encode(&img.rgba),
            };
            to_json_buffer(&result)
        }
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_decode_xpix(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::tim2::decode_xpix(data) {
        Ok(img) => {
            let result = Tim2Json {
                width: img.width,
                height: img.height,
                format: format!("{:?}", img.format),
                rgba: base64_engine.encode(&img.rgba),
            };
            to_json_buffer(&result)
        }
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_decode_fpix(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    if data.len() < 32 || &data[0..4] != b"FPIX" {
        set_last_error("expected FPIX".into());
        return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
    }
    let chunks = match arika_core::container::parse_directory(data, Some(b"FPIX")) {
        Ok(c) => c,
        Err(e) => return error_buffer(e),
    };
    let mut textures: Vec<serde_json::Value> = Vec::new();
    for (i, chunk) in chunks.iter().enumerate() {
        if chunk.magic != *b"XPIX" {
            continue;
        }
        match arika_core::tim2::decode_xpix(&chunk.data) {
            Ok(img) => {
                textures.push(serde_json::json!({
                    "index": textures.len(),
                    "width": img.width,
                    "height": img.height,
                    "format": format!("{:?}", img.format),
                    "rgba": base64_engine.encode(&img.rgba),
                }));
            }
            Err(e) => {
                set_last_error(format!("XPIX[{i}]: {e}"));
                return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
            }
        }
    }
    if textures.is_empty() {
        set_last_error("no XPIX textures found in FPIX".into());
        return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
    }
    to_json_buffer(&textures)
}

// ---------------------------------------------------------------------------
// Animation / Scene / Script
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn arika_parse_ani(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::ani::parse_ani(data) {
        Ok(doc) => to_json_buffer(&doc),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_parse_ebz(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::ebz::parse_ebz(data) {
        Ok(doc) => to_json_buffer(&doc),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_parse_stg(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::stages::parse_stg(data) {
        Ok(stage) => match stage_to_json(&stage) {
            Ok(json) => {
                let bytes = json.into_bytes();
                let len = bytes.len();
                let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                ArikaBuffer { ptr, len }
            }
            Err(e) => error_buffer(e),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_parse_hit(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::stages::parse_hit(data) {
        Ok(hit) => match hit_to_json(&hit) {
            Ok(json) => {
                let bytes = json.into_bytes();
                let len = bytes.len();
                let ptr = Box::into_raw(bytes.into_boxed_slice()) as *mut u8;
                ArikaBuffer { ptr, len }
            }
            Err(e) => error_buffer(e),
        },
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_parse_pas(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::pas::parse_pas(data) {
        Ok(doc) => to_json_buffer(&doc),
        Err(e) => error_buffer(e),
    }
}

#[no_mangle]
pub extern "C" fn arika_parse_spt(input: *const u8, len: usize) -> ArikaBuffer {
    let data = match read_bytes(input, len) {
        Some(d) => d,
        None => {
            set_last_error("invalid input buffer".into());
            return ArikaBuffer { ptr: ptr::null_mut(), len: 0 };
        }
    };
    match arika_core::spt::parse_spt(data) {
        Ok(doc) => to_json_buffer(&doc),
        Err(e) => error_buffer(e),
    }
}

// ---------------------------------------------------------------------------
// RNG
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn arika_next_rng(state: u64, out_value: *mut u32) -> u64 {
    let (next_state, value) = arika_core::rng::next_rng(state);
    if !out_value.is_null() {
        unsafe {
            *out_value = value;
        }
    }
    next_state
}

// ---------------------------------------------------------------------------
// Editor transform math
// ---------------------------------------------------------------------------

/// Hamilton product in glTF XYZW order. Uses f64 so repeated editor
/// rotations do not lose precision when crossing the Python/Rust boundary.
/// The caller supplies three arrays of four doubles (a, b, output).
#[no_mangle]
pub extern "C" fn arika_quaternion_multiply(
    a: *const f64,
    b: *const f64,
    output: *mut f64,
) -> c_int {
    if a.is_null() || b.is_null() || output.is_null() {
        set_last_error("null quaternion input or output".into());
        return -1;
    }
    // Copy inputs before writing output so aliasing is safe.
    let (a, b) = unsafe {
        let a = std::array::from_fn(|i| *a.add(i));
        let b = std::array::from_fn(|i| *b.add(i));
        (a, b)
    };
    if !a.iter().chain(b.iter()).all(|v| v.is_finite()) {
        set_last_error("nonfinite quaternion component".into());
        return -1;
    }
    let [x, y, z, w] = a;
    let [dx, dy, dz, dw] = b;
    let result = [
        w * dx + x * dw + y * dz - z * dy,
        w * dy - x * dz + y * dw + z * dx,
        w * dz + x * dy - y * dx + z * dw,
        w * dw - x * dx - y * dy - z * dz,
    ];
    unsafe {
        std::ptr::copy_nonoverlapping(result.as_ptr(), output, 4);
    }
    0
}

#[cfg(test)]
mod gizmo_quaternion_tests {
    use super::arika_quaternion_multiply;

    #[test]
    fn identity_and_axis_composition() {
        let identity = [0.0, 0.0, 0.0, 1.0];
        let x = [0.5, 0.0, 0.0, (0.75f64).sqrt()];
        let mut result = [0.0; 4];
        assert_eq!(arika_quaternion_multiply(identity.as_ptr(), x.as_ptr(), result.as_mut_ptr()), 0);
        assert_eq!(result, x);

        let y = [0.0, 0.5, 0.0, (0.75f64).sqrt()];
        assert_eq!(arika_quaternion_multiply(x.as_ptr(), y.as_ptr(), result.as_mut_ptr()), 0);
        assert!((result[2] - 0.25).abs() < 1e-12);
        assert_eq!(arika_quaternion_multiply(y.as_ptr(), x.as_ptr(), result.as_mut_ptr()), 0);
        assert!((result[2] + 0.25).abs() < 1e-12);
    }

    #[test]
    fn rejects_invalid_inputs() {
        let identity = [0.0, 0.0, 0.0, 1.0];
        let mut result = [0.0; 4];
        assert_eq!(arika_quaternion_multiply(std::ptr::null(), identity.as_ptr(), result.as_mut_ptr()), -1);
        let invalid = [f64::NAN, 0.0, 0.0, 1.0];
        assert_eq!(arika_quaternion_multiply(invalid.as_ptr(), identity.as_ptr(), result.as_mut_ptr()), -1);
    }
}
