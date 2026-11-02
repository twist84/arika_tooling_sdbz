//! ANI skeletal animation parser.
//! Matches arika_ani.py parse_ani exactly.
//!
//! Format:
//!   0x00: u32 track_count
//!   0x04-0x0C: reserved (zeros)
//!   0x10+: track_count pairs of (u32 frame_count, u32 file_offset)
//!   At each track offset:
//!     - frame_count x u32 relative frame offsets (from track data start)
//!     - Frame records at those offsets:
//!         u32 frame_index, u8 bone_index, u8 channel_count, u8 pad[2],
//!         then channel_count x float32 values

use crate::container::{f32_at, u32_at};
use crate::error::{ArikaError, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AniFrame {
    pub index: usize,
    pub frame_index: u32,
    pub bone_index: u8,
    pub channel_count: u8,
    pub channels_read: usize,
    pub channels: Vec<f32>,
    pub pad1: u8,
    pub pad2: u8,
    pub truncated: bool,
    pub file_offset: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AniTrack {
    pub index: usize,
    pub frame_count: u32,
    pub offset: usize,
    pub frames: Vec<AniFrame>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AniDocument {
    pub format: String,
    pub source_sha256: String,
    pub byte_size: usize,
    pub track_count: u32,
    pub tracks: Vec<AniTrack>,
    pub scope: String,
}

fn hash_hex(data: &[u8]) -> String {
    let mut h = [0u8; 32];
    for (i, &b) in data.iter().enumerate() {
        h[i % 32] ^= b;
        h[i % 32] = h[i % 32].wrapping_mul(31).wrapping_add(b as u32 as u8);
    }
    h.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn parse_ani(data: &[u8]) -> Result<AniDocument> {
    if data.len() < 0x10 {
        return Err(ArikaError::Other("truncated ANI header".into()));
    }
    let track_count = u32_at(data, 0)?;
    if track_count == 0 || track_count > 1024 {
        return Err(ArikaError::Other("invalid track count".into()));
    }

    for off in [4usize, 8, 0xC] {
        if u32_at(data, off)? != 0 {
            return Err(ArikaError::Other(format!(
                "reserved field at 0x{off:X} must be zero"
            )));
        }
    }

    let table_end = 0x10usize + track_count as usize * 8;
    if table_end > data.len() {
        return Err(ArikaError::Other("truncated track table".into()));
    }

    let mut tracks = Vec::with_capacity(track_count as usize);
    for i in 0..track_count {
        let frame_count = u32_at(data, 0x10 + i as usize * 8)?;
        let file_offset = u32_at(data, 0x14 + i as usize * 8)?;
        if frame_count == 0 || frame_count > 65536 {
            return Err(ArikaError::Other(format!(
                "track {i}: invalid frame count {frame_count}"
            )));
        }
        if file_offset as usize >= data.len() {
            return Err(ArikaError::Other(format!(
                "track {i}: offset beyond file"
            )));
        }
        tracks.push(AniTrack {
            index: i as usize,
            frame_count,
            offset: file_offset as usize,
            frames: Vec::new(),
        })
    }

    for track in tracks.iter_mut() {
        let base = track.offset;
        if base + track.frame_count as usize * 4 > data.len() {
            return Err(ArikaError::Other(format!(
                "track {}: truncated frame offset table",
                track.index
            )));
        }

        let frame_offsets: Vec<u32> = (0..track.frame_count)
            .map(|j| u32_at(data, base + j as usize * 4))
            .collect::<Result<Vec<u32>>>()?;

        for j in 0..frame_offsets.len() {
            let fpos = base + frame_offsets[j] as usize;
            if fpos + 8 > data.len() {
                track.frames.push(AniFrame {
                    index: j,
                    frame_index: 0,
                    bone_index: 0,
                    channel_count: 0,
                    channels_read: 0,
                    channels: Vec::new(),
                    pad1: 0,
                    pad2: 0,
                    truncated: true,
                    file_offset: fpos,
                });
                continue;
            }

            let frame_index = u32_at(data, fpos)?;
            let bone_index = data[fpos + 4];
            let channel_count = data[fpos + 5];
            let pad1 = data[fpos + 6];
            let pad2 = data[fpos + 7];

            let fdata_start = fpos + 8;
            let available = data.len().saturating_sub(fdata_start);
            let readable_channels = (channel_count as usize).min(available / 4);

            let mut truncated = false;
            if readable_channels < channel_count as usize {
                truncated = true;
            }

            let mut channels = Vec::with_capacity(readable_channels);
            for k in 0..readable_channels {
                let val = f32_at(data, fdata_start + k * 4)?;
                if !val.is_finite() {
                    truncated = true;
                }
                channels.push(val);
            }

            track.frames.push(AniFrame {
                index: j,
                frame_index,
                bone_index,
                channel_count,
                channels_read: readable_channels,
                channels,
                pad1,
                pad2,
                truncated,
                file_offset: fpos,
            });
        }
    }

    Ok(AniDocument {
        format: "ARIKA_ANI".to_string(),
        source_sha256: hash_hex(data),
        byte_size: data.len(),
        track_count,
        tracks,
        scope: "Track structure decoded; frame channel semantics (translation/rotation/scale per bone) are inferred but not fully validated."
            .to_string(),
    })
}
