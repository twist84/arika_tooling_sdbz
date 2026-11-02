//! PAS pose data parser.
//! Matches arika_pas.py parse_pas exactly.
//!
//! Format:
//!   0x00: u32 entry_count
//!   0x04-0x0C: reserved (zeros)
//!   0x10+: entry_count u32 file offsets to entry data blocks
//!   Each entry data block contains u32 cross-references to other entries

use crate::container::u32_at;
use crate::error::{ArikaError, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PasEntry {
    pub index: usize,
    pub file_offset: usize,
    pub size: usize,
    pub references: Vec<PasReference>,
    pub u32_values: Vec<u32>,
    pub raw_hex: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PasReference {
    pub target_index: usize,
    pub target_offset: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PasDocument {
    pub format: String,
    pub source_sha256: String,
    pub byte_size: usize,
    pub entry_count: u32,
    pub entries: Vec<PasEntry>,
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

pub fn parse_pas(data: &[u8]) -> Result<PasDocument> {
    if data.len() < 0x10 {
        return Err(ArikaError::Other("truncated PAS header".into()));
    }
    let entry_count = u32_at(data, 0)?;
    if entry_count == 0 || entry_count > 65536 {
        return Err(ArikaError::Other("invalid entry count".into()));
    }

    for off in [4usize, 8, 0xC] {
        if u32_at(data, off)? != 0 {
            return Err(ArikaError::Other(format!(
                "reserved field at 0x{off:X} must be zero"
            )));
        }
    }

    let table_end = 0x10usize + entry_count as usize * 4;
    if table_end > data.len() {
        return Err(ArikaError::Other("truncated entry offset table".into()));
    }

    let entry_offsets: Vec<u32> = (0..entry_count)
        .map(|i| u32_at(data, 0x10 + i as usize * 4))
        .collect::<Result<Vec<u32>>>()?;

    let mut entries = Vec::with_capacity(entry_count as usize);
    for i in 0..entry_count {
        let off = entry_offsets[i as usize] as usize;
        if off == 0 {
            entries.push(PasEntry {
                index: i as usize,
                file_offset: 0,
                size: 0,
                references: Vec::new(),
                u32_values: Vec::new(),
                raw_hex: String::new(),
            });
            continue;
        }

        if off >= data.len() {
            return Err(ArikaError::Other(format!(
                "entry {i}: offset {off} beyond file"
            )));
        }

        let next_off = entry_offsets
            .iter()
            .skip(i as usize + 1)
            .find(|&&v| v as usize > off)
            .copied()
            .unwrap_or(data.len() as u32) as usize;

        let entry_size = next_off - off;
        if entry_size < 4 {
            return Err(ArikaError::Other(format!(
                "entry {i}: too small ({entry_size} bytes)"
            )));
        }

        let mut references = Vec::new();
        let mut u32_values = Vec::new();
        let mut k = 0;
        while k + 4 <= entry_size {
            let val = u32_at(data, off + k)?;
            u32_values.push(val);
            if let Some(target_idx) = entry_offsets.iter().position(|&v| v == val && val != off as u32) {
                references.push(PasReference {
                    target_index: target_idx,
                    target_offset: val as usize,
                });
            }
            k += 4;
        }

        let raw_hex = data[off..next_off].iter().map(|b| format!("{b:02x}")).collect();

        entries.push(PasEntry {
            index: i as usize,
            file_offset: off,
            size: entry_size,
            references,
            u32_values: u32_values.into_iter().take(16).collect(),
            raw_hex,
        })
    }

    Ok(PasDocument {
        format: "ARIKA_PAS".to_string(),
        source_sha256: hash_hex(data),
        byte_size: data.len(),
        entry_count,
        entries,
        scope: "Entry data contains u32 cross-references forming a pose graph. Semantic meaning of individual fields is not decoded."
            .to_string(),
    })
}
