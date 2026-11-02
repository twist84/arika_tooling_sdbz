//! EBZ effect / trajectory archive parser.
//! Matches arika_ebz.py parse_ebz exactly.
//!
//! Format:
//!   0x00 magic " ZBE" (4 bytes)
//!   0x04 u16 version, u16 type
//!   0x08 u32 offset to ref table
//!   0x0C float param0
//!   0x10 u32 pad1, pad2, pad3
//!   0x1C u32 entry count
//!   0x20 u16 u1, u2, u3
//!   0x26 u32 p0, p1, p2
//!   ref table at size_field: u32 table_size, u32 table_count,
//!     then table_count x 16 bytes (name[8] + u64 value)
//!   entries at size_field + table_size: count x 112 bytes (28 u32 fields)

use crate::container::{f32_at, u16_at, u32_at};
use crate::error::{ArikaError, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EbzRef {
    pub index: usize,
    pub name: String,
    pub value: u64,
    pub value_lo: u32,
    pub value_hi: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EbzEntry {
    pub index: usize,
    pub fields: Vec<u32>,
    pub floats: Vec<Option<f32>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EbzDocument {
    pub magic: String,
    pub version: u16,
    pub etype: u16,
    pub size_field: u32,
    pub param0: f32,
    pub pad: [u32; 3],
    pub count: u32,
    pub u1: u16,
    pub u2: u16,
    pub u3: u16,
    pub p0: u32,
    pub p1: u32,
    pub p2: u32,
    pub refs: Vec<EbzRef>,
    pub entries: Vec<EbzEntry>,
    pub entries_end: usize,
    pub remaining: usize,
    pub scope: String,
}

fn f32_from_u32(v: u32) -> Option<f32> {
    let f = f32::from_le_bytes(v.to_le_bytes());
    if f.is_nan() {
        None
    } else {
        Some(f)
    }
}

pub fn parse_ebz(data: &[u8]) -> Result<EbzDocument> {
    if data.len() < 0x30 {
        return Err(ArikaError::Other("file too small for EBZ header".into()));
    }
    if &data[0..4] != b" ZBE" {
        return Err(ArikaError::Other(format!(
            "bad EBZ magic: {:?}",
            &data[0..4]
        )));
    }

    let version = u16_at(data, 4)?;
    let etype = u16_at(data, 6)?;
    let size_field = u32_at(data, 0x08)?;
    let param0 = f32_at(data, 0x0C)?;
    let pad = [
        u32_at(data, 0x10)?,
        u32_at(data, 0x14)?,
        u32_at(data, 0x18)?,
    ];
    let count = u32_at(data, 0x1C)?;
    let u1 = u16_at(data, 0x20)?;
    let u2 = u16_at(data, 0x22)?;
    let u3 = u16_at(data, 0x24)?;
    let p0 = u32_at(data, 0x26)?;
    let p1 = u32_at(data, 0x2A)?;
    let p2 = u32_at(data, 0x2E)?;

    // Ref table at size_field
    if size_field as usize + 8 > data.len() {
        return Err(ArikaError::Other("truncated EBZ ref table".into()));
    }
    let table_size = u32_at(data, size_field as usize)?;
    let table_count = u32_at(data, size_field as usize + 4)?;

    if size_field as usize + table_size as usize > data.len() {
        return Err(ArikaError::Other("ref table extends beyond file".into()));
    }

    let mut refs = Vec::with_capacity(table_count as usize);
    for i in 0..table_count {
        let roff = size_field as usize + 8 + i as usize * 16;
        if roff + 16 > data.len() {
            return Err(ArikaError::Other("truncated ref record".into()));
        }
        let name_raw = &data[roff..roff + 8];
        let name = name_raw
            .split(|&b| b == 0)
            .next()
            .unwrap_or(&[])
            .iter()
            .copied()
            .filter(|&b| b != 0)
            .map(|b| b as char)
            .collect::<String>();
        let value = u64::from_le_bytes([
            data[roff + 8],
            data[roff + 9],
            data[roff + 10],
            data[roff + 11],
            data[roff + 12],
            data[roff + 13],
            data[roff + 14],
            data[roff + 15],
        ]);
        refs.push(EbzRef {
            index: i as usize,
            name,
            value,
            value_lo: value as u32,
            value_hi: (value >> 32) as u32,
        })
    }

    // Entries
    let entries_offset = size_field as usize + table_size as usize;
    let mut entries = Vec::with_capacity(count as usize);
    for i in 0..count {
        let eoff = entries_offset + i as usize * 112;
        if eoff + 112 > data.len() {
            return Err(ArikaError::Other("truncated EBZ entry".into()));
        }
        let mut fields = Vec::with_capacity(28);
        let mut floats = Vec::with_capacity(28);
        for j in 0..28 {
            let f = u32_at(data, eoff + j * 4)?;
            fields.push(f);
            floats.push(f32_from_u32(f));
        }
        entries.push(EbzEntry {
            index: i as usize,
            fields,
            floats,
        })
    }

    let entries_end = entries_offset + count as usize * 112;
    let remaining = data.len().saturating_sub(entries_end);

    Ok(EbzDocument {
        magic: " ZBE".to_string(),
        version,
        etype,
        size_field,
        param0,
        pad,
        count,
        u1,
        u2,
        u3,
        p0,
        p1,
        p2,
        refs,
        entries,
        entries_end,
        remaining,
        scope: "Header + ref table + entries decoded; trailing data after entries not interpreted."
            .to_string(),
    })
}
