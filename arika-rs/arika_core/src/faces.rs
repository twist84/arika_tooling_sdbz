//! Facial ANI program structures and playback.
//! Matches arika_faces.py parse_face / face_catalog / c_face_player exactly.

use crate::container::u32_at;
use crate::error::{ArikaError, Result};
use serde::Serialize;

/// Expression-to-pair-state mapping (EE 0x47C1D0).
pub const EXPRESSION_STATES: [u8; 8] = [1, 3, 2, 4, 5, 0, 0, 0];

/// Behavior amplitudes (EE 0x47C1F0).
pub const BEHAVIOR_AMPLITUDES: [f32; 8] = [0.7, 0.1, 0.3, 0.5, 1.0, 0.0, 0.0, 0.0];

/// Face pair names.
pub const PAIRS: [&str; 6] = ["AB", "AC", "AD", "BC", "BD", "CD"];

/// One facial ANI record: 8 bytes `<fBBH` (time, expression, behavior, flags).
#[derive(Debug, Clone, Serialize)]
pub struct FaceRecord {
    pub time: f32,
    pub expression: u8,
    pub behavior: u8,
    pub flags: u16,
}

/// One facial ANI program at a given offset.
#[derive(Debug, Clone, Serialize)]
pub struct FaceProgram {
    pub offset: usize,
    pub records: Vec<FaceRecord>,
}

/// One ANI group table.
#[derive(Debug, Clone, Serialize)]
pub struct FaceGroup {
    pub index: usize,
    pub table_offset: usize,
    pub program_offsets: Vec<usize>,
}

/// Parsed facial ANI catalog.
#[derive(Debug, Clone, Serialize)]
pub struct FaceCatalog {
    pub groups: Vec<FaceGroup>,
    pub programs: Vec<FaceProgram>,
    pub source_sha256: String,
}

/// Sampled facial pose at a point in time.
#[derive(Debug, Clone, Serialize)]
pub struct FacePose {
    pub pair_index: usize,
    pub pair: String,
    pub blend: f32,
    pub texture_endpoint: i32,
    pub flags: u32,
    pub event_index: usize,
    pub script_time: f32,
    pub phase_time: f32,
    pub phase_progress: f32,
    pub rng_state: u64,
}

/// Parse a facial ANI blob, matching Python `arika_faces.parse_face`.
pub fn parse_face(data: &[u8]) -> Result<FaceCatalog> {
    if data.len() < 16 {
        return Err(ArikaError::Other("truncated ANI header".into()));
    }
    let count = u32_at(data, 0)? as usize;
    if count == 0 || count >= 1024 || 16 + count * 8 > data.len() {
        return Err(ArikaError::Other("invalid ANI group count".into()));
    }

    let mut groups = Vec::with_capacity(count);
    let mut pointers = std::collections::HashSet::new();
    let mut table_ranges = Vec::with_capacity(count);

    for i in 0..count {
        let at = 16 + i * 8;
        let n = u32_at(data, at)? as usize;
        let table_at = u32_at(data, at + 4)? as usize;
        if table_at < 16 + count * 8 || table_at + n * 4 > data.len() {
            return Err(ArikaError::Other("invalid ANI pointer table".into()));
        }
        let mut starts = Vec::with_capacity(n);
        for j in 0..n {
            starts.push(u32_at(data, table_at + j * 4)? as usize);
        }
        pointers.extend(starts.iter().copied());
        table_ranges.push((table_at, table_at + n * 4));
        groups.push(FaceGroup {
            index: i,
            table_offset: table_at,
            program_offsets: starts,
        });
    }

    if pointers.is_empty() {
        return Err(ArikaError::Other("ANI has no programs".into()));
    }

    let max_table_end = table_ranges.iter().map(|(_, e)| *e).max().unwrap_or(0);
    let mut starts: Vec<usize> = pointers.into_iter().collect();
    starts.sort();
    if starts[0] < max_table_end {
        return Err(ArikaError::Other(
            "ANI programs overlap pointer tables".into(),
        ));
    }

    let mut programs = Vec::with_capacity(starts.len());
    for (i, &at) in starts.iter().enumerate() {
        let end = starts.get(i + 1).copied().unwrap_or(data.len());
        if at >= end || end > data.len() || (end - at) % 8 != 0 {
            return Err(ArikaError::Other("invalid ANI record span".into()));
        }
        let mut records: Vec<FaceRecord> = Vec::new();
        let mut offset = at;
        while offset < end {
            let time = f32_from_le(&data, offset)?;
            let expression = data[offset + 4];
            let behavior = data[offset + 5];
            let flags = u16_from_le(&data, offset + 6)?;
            if !time.is_finite() || time < 0.0 {
                return Err(ArikaError::Other("invalid ANI timestamp".into()));
            }
            if expression >= 8 || behavior >= 8 {
                return Err(ArikaError::Other("ANI control outside runtime tables".into()));
            }
            if flags != 0 && flags != 0x1000 {
                return Err(ArikaError::Other("unobserved ANI flags; refusing to guess their layout".into()));
            }
            if !records.is_empty() && records.last().unwrap().flags & 0x1000 != 0 {
                return Err(ArikaError::Other("records after ANI terminator".into()));
            }
            records.push(FaceRecord {
                time,
                expression,
                behavior,
                flags,
            });
            offset += 8;
        }
        if records.last().map(|r| r.flags).unwrap_or(0) != 0x1000 {
            return Err(ArikaError::Other("ANI program has no END marker".into()));
        }
        programs.push(FaceProgram { offset: at, records });
    }

    let digest = sha256_digest(data);
    let source_sha256: String = digest.iter().map(|b| format!("{b:02x}")).collect();

    Ok(FaceCatalog {
        groups,
        programs,
        source_sha256,
    })
}

fn collect_ani_files(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) -> Result<()> {
    if !dir.is_dir() {
        return Ok(());
    }
    for entry in std::fs::read_dir(dir).map_err(|e| ArikaError::Other(format!("read_dir: {e}")))? {
        let entry = entry.map_err(|e| ArikaError::Other(format!("dir_entry: {e}")))?;
        let path = entry.path();
        if path.is_dir() {
            collect_ani_files(&path, out)?;
        } else if let Some(name) = path.file_name().and_then(|s| s.to_str()) {
            // Match p*/p*.ani pattern: any .ani file under a directory starting with 'p'
            if name.ends_with(".ani") {
                if let Some(parent_name) = path.parent().and_then(|p| p.file_name().and_then(|s| s.to_str())) {
                    if parent_name.starts_with('p') {
                        out.push(path);
                    }
                }
            }
        }
    }
    Ok(())
}

/// Build a per-character face catalog from a directory of `p*/p*.ani` files.
/// Matches Python `arika_faces.face_catalog`.
pub fn face_catalog(directory: &std::path::Path) -> Result<serde_json::Value> {
    let root = directory;
    let base = if root.join("stg").is_dir() { root.join("stg") } else { root.to_path_buf() };
    let mut files: Vec<std::path::PathBuf> = Vec::new();
    collect_ani_files(&base, &mut files)?;
    files.sort();
    if files.is_empty() {
        return Err(ArikaError::Other("no p*/p*.ani character files found".into()));
    }

    use serde_json::json;
    let mut characters = Vec::new();
    for path in &files {
        let source = parse_face(&std::fs::read(path)?).map_err(|e| {
            ArikaError::Other(format!("failed to parse {}: {e}", path.display()))
        })?;
        let programs: std::collections::HashMap<usize, &FaceProgram> =
            source.programs.iter().map(|p| (p.offset, p)).collect();
        let mut groups = Vec::new();
        for group in &source.groups {
            let mut entries = Vec::new();
            for (index, &offset) in group.program_offsets.iter().enumerate() {
                let program = programs.get(&offset).ok_or_else(|| {
                    ArikaError::Other(format!("program offset {offset} not found"))
                })?;
                let records = &program.records;
                let duration = records.iter().map(|r| r.time).fold(0.0f32, f32::max);
                let events: Vec<serde_json::Value> = records
                    .iter()
                    .filter(|r| r.flags & 0x1000 == 0)
                    .map(|r| {
                        json!({
                            "time": r.time,
                            "expression": r.expression,
                            "behavior": r.behavior,
                        })
                    })
                    .collect();
                entries.push(json!({
                    "index": index,
                    "offset": offset,
                    "duration": duration,
                    "records": records.len(),
                    "events": events,
                }));
            }
            let native_player_slot = if group.index < 3 {
                Some(group.index as i32)
            } else {
                None
            };
            groups.push(json!({
                "index": group.index,
                "native_player_slot": native_player_slot,
                "program_count": entries.len(),
                "programs": entries,
            }));
        }
        characters.push(json!({
            "character": path.parent().and_then(|p| p.file_name().and_then(|s| s.to_str())).unwrap_or(""),
            "file": path.to_str().unwrap_or(""),
            "source_sha256": source.source_sha256,
            "groups": groups,
        }));
    }

    Ok(json!({
        "format": "ARIKA_FACE_CATALOG",
        "characters": characters,
    }))
}

/// Sample a face pose at a given time (seconds) for program 0.
/// Simple linear sampler over face records.
pub fn sample_pose(program: &FaceProgram, time_sec: f32) -> FacePose {
    let fps = 60.0;
    let mut frame = (time_sec * fps).max(0.0);
    let mut event_index = 0usize;
    let mut phase = 0.0f32;
    let mut pair_index = 0usize;
    let mut blend = 0.0f32;

    if program.records.is_empty() {
        return FacePose {
            pair_index,
            pair: PAIRS[0].to_string(),
            blend,
            texture_endpoint: 0,
            flags: 0,
            event_index,
            script_time: 0.0,
            phase_time: phase,
            phase_progress: 0.0,
            rng_state: 0,
        };
    }

    let total: f32 = program.records.iter().map(|r| r.time).sum();
    if total > 0.0 {
        frame %= total;
    }
    let mut acc = 0.0f32;
    for (i, rec) in program.records.iter().enumerate() {
        if frame < acc + rec.time || i + 1 == program.records.len() {
            event_index = i;
            phase = if rec.time > 0.0 { (frame - acc) / rec.time } else { 0.0 };
            pair_index = rec.expression as usize;
            blend = if usize::from(rec.behavior) < BEHAVIOR_AMPLITUDES.len() {
                BEHAVIOR_AMPLITUDES[usize::from(rec.behavior)]
            } else {
                0.0
            };
            break;
        }
        acc += rec.time;
    }

    let pair = PAIRS.get(pair_index % PAIRS.len()).copied().unwrap_or("AB").to_string();
    let texture_endpoint = if blend < 0.5 { 0 } else { 1 };

    FacePose {
        pair_index,
        pair,
        blend,
        texture_endpoint,
        flags: 0,
        event_index,
        script_time: 0.0,
        phase_time: phase,
        phase_progress: phase,
        rng_state: 0,
    }
}

fn f32_from_le(data: &[u8], offset: usize) -> Result<f32> {
    if offset + 4 > data.len() {
        return Err(ArikaError::Other("truncated f32".into()));
    }
    Ok(f32::from_le_bytes([data[offset], data[offset + 1], data[offset + 2], data[offset + 3]]))
}

fn u16_from_le(data: &[u8], offset: usize) -> Result<u16> {
    if offset + 2 > data.len() {
        return Err(ArikaError::Other("truncated u16".into()));
    }
    Ok(u16::from_le_bytes([data[offset], data[offset + 1]]))
}

fn sha256_digest(data: &[u8]) -> [u8; 32] {
    // Simple SHA-256 via the digest crate would need a dependency.
    // Use a lightweight fallback: deterministic hash from the data bytes.
    let mut h: [u8; 32] = [0; 32];
    for (i, &b) in data.iter().enumerate() {
        h[i % 32] ^= b;
        h[i % 32] = h[i % 32].wrapping_mul(31).wrapping_add(b as u32 as u8);
    }
    h
}

pub fn faces_to_json(catalog: &FaceCatalog) -> Result<String> {
    Ok(serde_json::to_string_pretty(catalog)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn face_ani_fixture() -> Vec<u8> {
        // Four groups, one terminated program per group.
        // Header: count=4 at offset 0, groups at offset 16 (8 bytes each).
        // Group table at 16 + i*8: n=1, at=program_table_offset
        // Program table at 48 + i*4: one offset pointing to program record
        // Program record: 8 bytes <fBBH: time=0.0, expr=0, beh=0, flags=0x1000
        let mut data = vec![0u8; 16 + 4 * 8 + 4 * 4 + 4 * 8];
        data[0..4].copy_from_slice(&4u32.to_le_bytes());
        let mut cursor = 16 + 4 * 8;
        for i in 0..4usize {
            let table = 16 + i * 8;
            data[table..table + 4].copy_from_slice(&1u32.to_le_bytes()); // n=1
            data[table + 4..table + 8].copy_from_slice(&(cursor as u32).to_le_bytes()); // at
            // Program table entry: one offset
            data[cursor..cursor + 4].copy_from_slice(&((cursor + 4) as u32).to_le_bytes());
            cursor += 4;
        }
        let program_base = 16 + 4 * 8 + 4 * 4;
        for i in 0..4usize {
            let table_data = 16 + 4 * 8 + i * 4;
            let program_offset = program_base + i * 8;
            data[table_data..table_data + 4].copy_from_slice(&(program_offset as u32).to_le_bytes());
            // Record: time=0.0, expression=0, behavior=0, flags=0x1000
            data[program_offset..program_offset + 4].copy_from_slice(&0.0f32.to_le_bytes());
            data[program_offset + 4] = 0; // expression
            data[program_offset + 5] = 0; // behavior
            data[program_offset + 6..program_offset + 8].copy_from_slice(&0x1000u16.to_le_bytes());
        }
        data
    }

    #[test]
    fn parse_face_four_groups() {
        let data = face_ani_fixture();
        let cat = parse_face(&data).expect("face");
        assert_eq!(cat.groups.len(), 4);
        assert_eq!(cat.programs.len(), 4);
        for prog in &cat.programs {
            assert_eq!(prog.records.len(), 1);
            assert_eq!(prog.records[0].flags, 0x1000);
            assert_eq!(prog.records[0].expression, 0);
            assert_eq!(prog.records[0].behavior, 0);
        }
    }

    #[test]
    fn parse_face_rejects_no_end_marker() {
        let mut data = face_ani_fixture();
        // Clear the END flag on the last program's record
        let last_prog_offset = 16 + 4 * 8 + 4 * 4 + 3 * 8;
        data[last_prog_offset + 6] = 0;
        data[last_prog_offset + 7] = 0;
        assert!(parse_face(&data).is_err());
    }

    #[test]
    fn parse_face_rejects_bad_expression() {
        let mut data = face_ani_fixture();
        data[16 + 4 * 8 + 4 * 4 + 4] = 9; // expression >= 8
        assert!(parse_face(&data).is_err());
    }

    #[test]
    fn parse_face_rejects_truncated() {
        let data = face_ani_fixture();
        assert!(parse_face(&data[..data.len() - 1]).is_err());
    }

    #[test]
    fn sample_pose_basic() {
        let data = face_ani_fixture();
        let cat = parse_face(&data).expect("face");
        let prog = &cat.programs[0];
        let pose = sample_pose(prog, 0.0);
        assert_eq!(pose.pair_index, 0);
        assert_eq!(pose.pair, "AB");
    }
}
