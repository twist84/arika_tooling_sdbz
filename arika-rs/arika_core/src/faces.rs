//! Facial ANI program structures and basic timeline sampling.
//! Full controller equivalence is documented in FACE_PLAYBACK.md; this module
//! provides parse/inspect and a simple pose sampler.

use crate::container::u32_at;
use crate::error::{ArikaError, Result};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct FaceCatalog {
    pub programs: Vec<FaceProgram>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FaceProgram {
    pub index: usize,
    pub records: Vec<FaceRecord>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FaceRecord {
    pub kind: u32,
    pub duration_frames: u32,
    pub face_id: i32,
    pub blend: f32,
    pub texture_endpoint: i32,
    pub flags: u32,
    pub raw: Vec<u32>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FacePose {
    pub face_id: i32,
    pub blend: f32,
    pub texture_endpoint: i32,
    pub event_index: usize,
    pub phase_time: f32,
}

/// Best-effort parse of a facial ANI blob.
/// Layout varies; we scan for plausible program tables.
pub fn parse_face_ani(data: &[u8]) -> Result<FaceCatalog> {
    if data.len() < 16 {
        return Err(ArikaError::Other("truncated face ANI".into()));
    }
    // Many face resources start with a count then offset table
    let count = u32_at(data, 0).unwrap_or(0) as usize;
    let mut programs = Vec::new();
    if count > 0 && count < 512 && 4 + count * 4 <= data.len() {
        for i in 0..count {
            let off = u32_at(data, 4 + i * 4).unwrap_or(0) as usize;
            if off + 8 > data.len() {
                continue;
            }
            let records = parse_records(&data[off..]);
            programs.push(FaceProgram {
                index: i,
                records,
            });
        }
    }
    if programs.is_empty() {
        // single program fallback
        programs.push(FaceProgram {
            index: 0,
            records: parse_records(data),
        });
    }
    Ok(FaceCatalog { programs })
}

fn parse_records(data: &[u8]) -> Vec<FaceRecord> {
    let mut records = Vec::new();
    let mut at = 0usize;
    // Heuristic: records are groups of u32s; stop on zeros or EOF
    while at + 16 <= data.len() && records.len() < 256 {
        let kind = match u32_at(data, at) {
            Ok(k) => k,
            Err(_) => break,
        };
        if kind == 0 && at > 0 {
            break;
        }
        let duration = u32_at(data, at + 4).unwrap_or(0);
        let face_id = u32_at(data, at + 8).unwrap_or(0) as i32;
        let blend_bits = u32_at(data, at + 12).unwrap_or(0);
        let blend = f32::from_bits(blend_bits);
        let mut raw = vec![kind, duration, face_id as u32, blend_bits];
        let mut next = at + 16;
        // optional extra words
        if next + 8 <= data.len() {
            if let Ok(a) = u32_at(data, next) {
                raw.push(a);
                next += 4;
            }
            if let Ok(b) = u32_at(data, next) {
                raw.push(b);
                next += 4;
            }
        }
        records.push(FaceRecord {
            kind,
            duration_frames: duration,
            face_id,
            blend: if blend.is_finite() { blend } else { 0.0 },
            texture_endpoint: raw.get(4).copied().unwrap_or(0) as i32,
            flags: raw.get(5).copied().unwrap_or(0),
            raw,
        });
        at = next;
        if duration == 0 && kind > 1000 {
            break;
        }
    }
    records
}

/// Sample a face pose at a given time (seconds) for program 0.
pub fn sample_pose(program: &FaceProgram, time_sec: f32, fps: f32) -> FacePose {
    let fps = if fps <= 0.0 { 60.0 } else { fps };
    let mut frame = (time_sec * fps).max(0.0);
    let mut event_index = 0usize;
    let mut phase = 0.0f32;
    let mut face_id = 0i32;
    let mut blend = 0.0f32;
    let mut tex = 0i32;

    if program.records.is_empty() {
        return FacePose {
            face_id,
            blend,
            texture_endpoint: tex,
            event_index,
            phase_time: 0.0,
        };
    }

    // Loop through records by duration
    let total: f32 = program
        .records
        .iter()
        .map(|r| r.duration_frames as f32)
        .sum();
    if total > 0.0 {
        frame %= total;
    }
    let mut acc = 0.0f32;
    for (i, rec) in program.records.iter().enumerate() {
        let dur = rec.duration_frames as f32;
        if frame < acc + dur || i + 1 == program.records.len() {
            event_index = i;
            phase = if dur > 0.0 { (frame - acc) / dur } else { 0.0 };
            face_id = rec.face_id;
            blend = rec.blend;
            tex = rec.texture_endpoint;
            break;
        }
        acc += dur;
    }
    FacePose {
        face_id,
        blend,
        texture_endpoint: tex,
        event_index,
        phase_time: phase,
    }
}

pub fn faces_to_json(catalog: &FaceCatalog) -> Result<String> {
    Ok(serde_json::to_string_pretty(catalog)?)
}
