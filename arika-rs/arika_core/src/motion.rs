//! RFSM packages and MOT2 skeletal animations.

use crate::container::{f32_at, u32_at};
use crate::error::{ArikaError, Result};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct MotionPackage {
    pub bones: Vec<String>,
    pub motions: Vec<Motion>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Motion {
    pub name: String,
    pub fps: f32,
    pub frame_count: u16,
    pub duration: f32,
    pub nodes: Vec<MotionNode>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MotionNode {
    pub name: String,
    pub translation: Track,
    pub rotation: Track,
    pub scale: Track,
}

#[derive(Debug, Clone, Serialize)]
pub struct Track {
    pub animated: bool,
    pub times: Vec<f32>,
    pub values: Vec<Vec<f32>>,
}

/// Parse an RFSM (.pmt) package.
pub fn parse_rfsm(data: &[u8]) -> Result<MotionPackage> {
    if data.len() < 16 || &data[0..4] != b"RFSM" {
        return Err(ArikaError::Other("expected RFSM".into()));
    }
    // RFSM L3 header
    let motion_count = u16_at(data, 6)? as usize;
    // After header: directory-like structure of MOT2 + bone names + bindings
    // Simplified: find MOT2 chunks and bone name list
    let mut motions = Vec::new();
    let mut bones = Vec::new();

    // Scan for MOT2 signatures
    let mut i = 0usize;
    while i + 4 <= data.len() {
        if &data[i..i + 4] == b"MOT2" {
            if let Ok(size) = u32_at(data, i + 4) {
                let end = i + size as usize;
                if end <= data.len() {
                    if let Ok(m) = parse_mot2(&data[i..end]) {
                        motions.push(m);
                    }
                    i = end;
                    continue;
                }
            }
        }
        i += 1;
    }

    // Try to recover bone names from XNON-style or trailing strings
    // RFSM often has a bone name block; best-effort scan for CP932 strings
    if bones.is_empty() && motion_count > 0 {
        // placeholder names
        if let Some(m) = motions.first() {
            for (ni, _) in m.nodes.iter().enumerate() {
                bones.push(format!("bone_{ni}"));
            }
        }
    }

    // Bindings: assign sequential names if we have bones
    for m in &mut motions {
        for (ni, node) in m.nodes.iter_mut().enumerate() {
            if node.name.is_empty() {
                node.name = bones.get(ni).cloned().unwrap_or_else(|| format!("node_{ni}"));
            }
        }
    }

    let _ = motion_count;
    Ok(MotionPackage { bones, motions })
}

/// Parse a single MOT2 motion.
pub fn parse_mot2(data: &[u8]) -> Result<Motion> {
    if data.len() < 0x40 || &data[0..4] != b"MOT2" {
        return Err(ArikaError::Other("expected MOT2".into()));
    }
    let fps = f32_at(data, 0x08)?;
    let frame_count = u16_at(data, 0x0C)?;
    let node_count = u16_at(data, 0x0E)? as usize;
    let constants = u16_at(data, 0x10)? as usize;
    let _anim_channels = u16_at(data, 0x12)?;
    let nodes_offset = u32_at(data, 0x14)? as usize;
    let constants_offset = u32_at(data, 0x18)? as usize;

    // Channel descriptors: translation, rotation, scale at fixed offsets
    // From header: after constants_offset field come three channel structs
    // Each: channel_count u16, key_count u16, vectors_offset u32, times_offset u32
    let mut channel_info = Vec::with_capacity(3);
    let mut off = 0x1C;
    for _ in 0..3 {
        if off + 12 > data.len() {
            break;
        }
        let ch_count = u16_at(data, off)? as usize;
        let key_count = u16_at(data, off + 2)? as usize;
        let vec_off = u32_at(data, off + 4)? as usize;
        let time_off = u32_at(data, off + 8)? as usize;
        channel_info.push((ch_count, key_count, vec_off, time_off));
        off += 12;
    }

    // Constant vectors
    let mut constant_values = Vec::with_capacity(constants);
    for i in 0..constants {
        let o = constants_offset + i * 16;
        if o + 16 > data.len() {
            break;
        }
        constant_values.push([
            f32_at(data, o)?,
            f32_at(data, o + 4)?,
            f32_at(data, o + 8)?,
            f32_at(data, o + 12)?,
        ]);
    }

    // Nodes
    let mut nodes = Vec::with_capacity(node_count);
    for i in 0..node_count {
        let no = nodes_offset + i * 8;
        if no + 8 > data.len() {
            break;
        }
        let flags = u16_at(data, no)?;
        let t_idx = u16_at(data, no + 2)? as usize;
        let r_idx = u16_at(data, no + 4)? as usize;
        let s_idx = u16_at(data, no + 6)? as usize;

        let translation = build_track(
            data,
            (flags & 1) != 0,
            t_idx,
            0,
            &channel_info,
            &constant_values,
            false,
        )?;
        let rotation = build_track(
            data,
            (flags & 2) != 0,
            r_idx,
            1,
            &channel_info,
            &constant_values,
            true,
        )?;
        let scale = build_track(
            data,
            (flags & 4) != 0,
            s_idx,
            2,
            &channel_info,
            &constant_values,
            false,
        )?;

        nodes.push(MotionNode {
            name: String::new(),
            translation,
            rotation,
            scale,
        });
    }

    Ok(Motion {
        name: String::new(),
        fps,
        frame_count,
        duration: if fps > 0.0 {
            frame_count as f32 / fps
        } else {
            0.0
        },
        nodes,
    })
}

fn build_track(
    data: &[u8],
    animated: bool,
    index: usize,
    typ: usize, // 0 trans, 1 rot, 2 scale
    channel_info: &[(usize, usize, usize, usize)],
    constants: &[[f32; 4]],
    is_quat: bool,
) -> Result<Track> {
    if !animated {
        let v = constants.get(index).copied().unwrap_or([0.0, 0.0, 0.0, 1.0]);
        let vals = if is_quat {
            vec![vec![v[0], v[1], v[2], v[3]]]
        } else {
            vec![vec![v[0], v[1], v[2]]]
        };
        return Ok(Track {
            animated: false,
            times: vec![0.0],
            values: vals,
        });
    }
    if typ >= channel_info.len() {
        return Ok(Track {
            animated: false,
            times: vec![0.0],
            values: vec![vec![0.0, 0.0, 0.0]],
        });
    }
    let (ch_count, key_count, vec_off, time_off) = channel_info[typ];
    if index >= ch_count || key_count == 0 {
        return Ok(Track {
            animated: false,
            times: vec![0.0],
            values: vec![vec![0.0, 0.0, 0.0]],
        });
    }
    let comps = if is_quat { 4 } else { 3 };
    let mut times = Vec::with_capacity(key_count);
    for k in 0..key_count {
        let o = time_off + index * key_count * 4 + k * 4;
        if o + 4 > data.len() {
            break;
        }
        times.push(f32_at(data, o)?);
    }
    let mut values = Vec::with_capacity(key_count);
    for k in 0..key_count {
        let o = vec_off + (index * key_count + k) * 16;
        if o + 16 > data.len() {
            break;
        }
        let mut v = Vec::with_capacity(comps);
        for c in 0..comps {
            v.push(f32_at(data, o + c * 4)?);
        }
        values.push(v);
    }
    Ok(Track {
        animated: true,
        times,
        values,
    })
}

fn u16_at(data: &[u8], offset: usize) -> Result<u16> {
    use byteorder::{LittleEndian, ReadBytesExt};
    use std::io::Cursor;
    if offset + 2 > data.len() {
        return Err(ArikaError::Other("truncated u16".into()));
    }
    let mut c = Cursor::new(&data[offset..offset + 2]);
    Ok(c.read_u16::<LittleEndian>()?)
}

pub fn motion_to_json(pkg: &MotionPackage) -> Result<String> {
    Ok(serde_json::to_string_pretty(pkg)?)
}
