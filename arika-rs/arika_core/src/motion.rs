//! RFSM packages and MOT2 skeletal animations.

use crate::container::{f32_at, u32_at};
use crate::error::{ArikaError, Result};
use byteorder::{LittleEndian, ReadBytesExt};
use encoding_rs::SHIFT_JIS;
use serde::Serialize;
use std::io::Cursor;

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

/// Parse an RFSM (.pmt) package, matching Python `arika_dat.motion_archive`.
///
/// Validates the RFSM/L3 shared block layout, reads bone names (CP932) and
/// flags, then parses each MOT2 motion entry referenced by the header.
pub fn parse_rfsm(data: &[u8]) -> Result<MotionPackage> {
    if data.len() < 16 || &data[0..6] != b"RFSML3" {
        return Err(ArikaError::Other("expected RFSM/L3".into()));
    }
    let count = u16_at(data, 6)? as usize;
    let shared = u32_at(data, 8)? as usize;
    let shared_end = u32_at(data, 12)? as usize;
    if shared != 16 + count * 32 {
        return Err(ArikaError::Other("invalid RFSM shared block".into()));
    }
    if shared + 16 > shared_end || shared_end > data.len() {
        return Err(ArikaError::Other("invalid RFSM shared block".into()));
    }

    let mut cur = Cursor::new(&data[shared..shared + 16]);
    let shared_count = cur.read_u16::<LittleEndian>()? as usize;
    let bones = cur.read_u16::<LittleEndian>()? as usize;
    let names_off = cur.read_u32::<LittleEndian>()? as usize;
    let bindings_off = cur.read_u32::<LittleEndian>()? as usize;
    let flags_off = cur.read_u32::<LittleEndian>()? as usize;

    if shared_count != count
        || names_off != shared + 16
        || bindings_off != names_off + bones * 16
        || shared_end != flags_off + bones
        || bindings_off > flags_off
        || flags_off > data.len()
    {
        return Err(ArikaError::Other("unexpected RFSM skeleton layout".into()));
    }

    // Bone names: CP932, 16 bytes each, NUL-terminated.
    let mut bone_names = Vec::with_capacity(bones);
    for i in 0..bones {
        let start = names_off + i * 16;
        let nul = data[start..start + 16]
            .iter()
            .position(|&b| b == 0)
            .unwrap_or(16);
        let (name, _, _) = SHIFT_JIS.decode(&data[start..start + nul]);
        bone_names.push(name.into_owned());
    }

    // Bone flags: one byte per bone.
    let _bone_flags: Vec<u8> = data[flags_off..flags_off + bones].to_vec();

    // Motion directory entries: 32 bytes each at 16 + index*32.
    let mut motions = Vec::with_capacity(count);
    for i in 0..count {
        let at = 16 + i * 32;
        let nul = data[at..at + 16]
            .iter()
            .position(|&b| b == 0)
            .unwrap_or(16);
        let (name, _, _) = SHIFT_JIS.decode(&data[at..at + nul]);
        let name = name.into_owned();
        let offset = u32_at(data, at + 16)? as usize;
        let size = u32_at(data, at + 20)? as usize;
        let _unknown = u32_at(data, at + 24)?;
        let _format_value = u32_at(data, at + 28)?;

        if offset < shared_end
            || offset + size > data.len()
            || size < 8
            || &data[offset..offset + 4] != b"MOT2"
            || u32_at(data, offset + 4)? != size as u32
        {
            return Err(ArikaError::Other(format!("invalid MOT2 extent for motion {i}")));
        }

        let m = parse_mot2(&data[offset..offset + size])?;
        motions.push(Motion {
            name,
            fps: m.fps,
            frame_count: m.frame_count,
            duration: m.duration,
            nodes: m.nodes,
        });
    }

    // Assign bone names to motion nodes.
    for m in &mut motions {
        for (ni, node) in m.nodes.iter_mut().enumerate() {
            if node.name.is_empty() {
                node.name = bone_names.get(ni).cloned().unwrap_or_else(|| format!("node_{ni}"));
            }
        }
    }

    Ok(MotionPackage {
        bones: bone_names,
        motions,
    })
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

#[cfg(test)]
mod tests {
    use super::*;

    fn build_rfsm() -> Vec<u8> {
        // 224 bytes: RFSM header(16) + motion entry(32) + shared block(16) +
        // bone name(16) + padding(4) + MOT2(128)
        let mut data = vec![0u8; 224];
        data[..6].copy_from_slice(b"RFSML3");
        data[6..8].copy_from_slice(&1u16.to_le_bytes());
        data[8..12].copy_from_slice(&48u32.to_le_bytes());
        data[12..16].copy_from_slice(&85u32.to_le_bytes());
        data[16..24].copy_from_slice(b"test.mot");
        data[32..36].copy_from_slice(&96u32.to_le_bytes());
        data[36..40].copy_from_slice(&128u32.to_le_bytes());
        data[40..44].copy_from_slice(&0u32.to_le_bytes());
        data[44..48].copy_from_slice(&0x10006u32.to_le_bytes());
        data[48..50].copy_from_slice(&1u16.to_le_bytes());
        data[50..52].copy_from_slice(&1u16.to_le_bytes());
        data[52..56].copy_from_slice(&64u32.to_le_bytes());
        data[56..60].copy_from_slice(&80u32.to_le_bytes());
        data[60..64].copy_from_slice(&84u32.to_le_bytes());
        data[64..71].copy_from_slice(b"HipRoot");
        data[84] = 0x22;
        data[96..100].copy_from_slice(b"MOT2");
        data[100..104].copy_from_slice(&128u32.to_le_bytes());
        // MOT2 header (relative to offset 96)
        data[104..108].copy_from_slice(&60.0f32.to_le_bytes()); // fps
        data[108..110].copy_from_slice(&2u16.to_le_bytes()); // frame_count
        data[110..112].copy_from_slice(&1u16.to_le_bytes()); // node_count
        data[112..114].copy_from_slice(&0u16.to_le_bytes()); // constants
        data[114..116].copy_from_slice(&0u16.to_le_bytes()); // anim_channels
        data[116..120].copy_from_slice(&64u32.to_le_bytes()); // nodes_offset
        data[120..124].copy_from_slice(&68u32.to_le_bytes()); // constants_offset
        // 3 channel descriptors at 0x1C (28) = abs 124, each 12 bytes
        for (t, _base) in [(124usize, 0), (136, 12), (148, 24)] {
            data[t..t + 2].copy_from_slice(&1u16.to_le_bytes()); // ch_count
            data[t + 2..t + 4].copy_from_slice(&1u16.to_le_bytes()); // key_count
            data[t + 4..t + 8].copy_from_slice(&80u32.to_le_bytes()); // vec_off
            data[t + 8..t + 12].copy_from_slice(&96u32.to_le_bytes()); // time_off
        }
        // Node 0 at abs 160: flags=7 (all animated), t/r/s idx=0
        data[160..162].copy_from_slice(&7u16.to_le_bytes());
        data[162..164].copy_from_slice(&0u16.to_le_bytes());
        data[164..166].copy_from_slice(&0u16.to_le_bytes());
        data[166..168].copy_from_slice(&0u16.to_le_bytes());
        // Vector data at abs 176 (vec_off=80 -> 96+80=176): 4 floats
        data[176..180].copy_from_slice(&1.0f32.to_le_bytes());
        data[180..184].copy_from_slice(&2.0f32.to_le_bytes());
        data[184..188].copy_from_slice(&3.0f32.to_le_bytes());
        data[188..192].copy_from_slice(&4.0f32.to_le_bytes());
        // Time at abs 192 (time_off=96 -> 96+96=192): 1 float
        data[192..196].copy_from_slice(&0.5f32.to_le_bytes());
        data
    }

    #[test]
    fn parse_rfsm_l3_header() {
        let data = build_rfsm();
        let pkg = parse_rfsm(&data).expect("rfsm");
        assert_eq!(pkg.bones, vec!["HipRoot"]);
        assert_eq!(pkg.motions.len(), 1);
        assert_eq!(pkg.motions[0].name, "test.mot");
    }

    #[test]
    fn parse_rfsm_rejects_bad_magic() {
        let mut data = build_rfsm();
        data[0] = b'X';
        assert!(parse_rfsm(&data).is_err());
    }

    #[test]
    fn parse_rfsm_rejects_bad_mot2_extent() {
        let mut data = build_rfsm();
        // Point motion offset past end of data
        data[32..36].copy_from_slice(&200u32.to_le_bytes());
        assert!(parse_rfsm(&data).is_err());
    }
}
