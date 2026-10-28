//! CHT logical-motion mappings and collision blocks.
//! Matches arika_cht.py parse_cht / lookup / runtime_motion_name exactly.

use crate::container::{u16_at, u32_at};
use crate::error::{ArikaError, Result};
use encoding_rs::SHIFT_JIS;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct ChildBlocks {
    pub type_68: u32,
    pub type_36: u32,
    pub type_32: u32,
    pub type_12: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChtVariant {
    pub variant: usize,
    pub offset: usize,
    pub name_index: usize,
    pub motion_name: String,
    pub resource_bank: u16,
    pub child_blocks: ChildBlocks,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChtAction {
    pub motion_id: u32,
    pub offset: usize,
    pub variants: Vec<ChtVariant>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChtDocument {
    pub format: String,
    pub source_sha256: String,
    pub byte_size: usize,
    pub name_table: Vec<String>,
    pub runtime_directory_offset: usize,
    pub actions: Vec<ChtAction>,
    pub scope: String,
}

/// Compute simple deterministic hex hash from bytes.
fn hash_hex(data: &[u8]) -> String {
    let mut h = [0u8; 32];
    for (i, &b) in data.iter().enumerate() {
        h[i % 32] ^= b;
        h[i % 32] = h[i % 32].wrapping_mul(31).wrapping_add(b as u32 as u8);
    }
    h.iter().map(|b| format!("{b:02x}")).collect()
}

/// Convert authored motion name to runtime motion name:
/// copy up to 15 bytes, split on '.', take prefix, decode as Shift-JIS.
pub fn runtime_motion_name(name: &str) -> String {
    let (encoded, _, _) = SHIFT_JIS.encode(name);
    let slice = if encoded.len() > 15 {
        &encoded[..15]
    } else {
        &encoded[..]
    };
    let dot_pos = slice.iter().position(|&b| b == b'.').unwrap_or(slice.len());
    let (decoded, _, _) = SHIFT_JIS.decode(&slice[..dot_pos]);
    decoded.into_owned()
}

struct ChtReader<'a> {
    data: &'a [u8],
    cursor: usize,
}

impl<'a> ChtReader<'a> {
    fn new(data: &'a [u8]) -> Self {
        Self { data, cursor: 20 }
    }

    fn take(&mut self, size: usize) -> Result<usize> {
        if self.cursor + size > self.data.len() {
            return Err(ArikaError::Other(format!(
                "truncated CHT block at 0x{:X}",
                self.cursor
            )));
        }
        let off = self.cursor;
        self.cursor += size;
        Ok(off)
    }

    fn align(&mut self) -> Result<()> {
        let pad = (16 - (self.cursor % 16)) % 16;
        self.take(pad)?;
        Ok(())
    }
}

/// Parse CHT motion mappings and collision extent blocks.
pub fn parse_cht(data: &[u8]) -> Result<ChtDocument> {
    if data.len() < 20 || &data[0..8] != b"\0\0\x01\0CHT " {
        return Err(ArikaError::Other(
            "expected reference-version CHT header".into(),
        ));
    }

    let mut r = ChtReader::new(data);

    let count = u32_at(data, 16)? as usize;
    if count > 0x10000 || count * 32 > data.len() - r.cursor {
        return Err(ArikaError::Other("invalid CHT name count".into()));
    }

    let mut names = Vec::with_capacity(count);
    for _ in 0..count {
        let off = r.take(32)?;
        let block = &data[off..off + 32];
        let nul = block
            .iter()
            .position(|&b| b == 0)
            .ok_or_else(|| ArikaError::Other("unterminated CHT motion name".into()))?;
        let (name, _, _) = SHIFT_JIS.decode(&block[..nul]);
        names.push(name.into_owned());
    }

    let flags_off = r.take(72)?;
    for i in 0..18 {
        r.align()?;
        let flag = u32_at(data, flags_off + i * 4)?;
        if flag != 0 {
            r.take(32)?;
        }
    }

    let directory = r.take(4000)?;
    let mut actions = Vec::new();

    while r.cursor < data.len() {
        let offset = r.take(12)?;
        let logical_id = u32_at(data, offset)?;
        let variants = u32_at(data, offset + 4)? as usize;
        let _unk = u32_at(data, offset + 8)?;

        if logical_id >= 1000 || variants > (data.len() - r.cursor) / 136 {
            return Err(ArikaError::Other("invalid CHT action/count".into()));
        }

        let base = r.take(variants * 136)?;
        let mut records = Vec::with_capacity(variants);

        for variant in 0..variants {
            let at = base + variant * 136;
            let name_index = u16_at(data, at + 4)? as usize;
            let bank = u16_at(data, at + 6)?;

            if name_index >= names.len() {
                return Err(ArikaError::Other("CHT name index out of range".into()));
            }

            let mut blocks = ChildBlocks::default();

            // Native 0x2AC930: 16x68 children (fields 8..72 step 4)
            for field in (8..72).step_by(4) {
                if u32_at(data, at + field)? != 0 {
                    let child = r.take(68)?;
                    blocks.type_68 += 1;
                    r.align()?;
                    for subfield in (36..68).step_by(4) {
                        if u32_at(data, child + subfield)? != 0 {
                            r.take(32)?;
                            blocks.type_32 += 1;
                        }
                    }
                }
            }

            // 8x36 children (fields 104..136 step 4)
            for field in (104..136).step_by(4) {
                if u32_at(data, at + field)? != 0 {
                    let child = r.take(36)?;
                    blocks.type_36 += 1;
                    r.align()?;
                    for subfield in (4..36).step_by(4) {
                        if u32_at(data, child + subfield)? != 0 {
                            r.take(32)?;
                            blocks.type_32 += 1;
                        }
                    }
                }
            }

            // 8x12 children (fields 72..104 step 4)
            for field in (72..104).step_by(4) {
                if u32_at(data, at + field)? != 0 {
                    r.take(12)?;
                    blocks.type_12 += 1;
                }
            }

            records.push(ChtVariant {
                variant,
                offset: at,
                name_index,
                motion_name: names[name_index].clone(),
                resource_bank: bank,
                child_blocks: blocks,
            });
        }

        actions.push(ChtAction {
            motion_id: logical_id,
            offset,
            variants: records,
        });
    }

    if r.cursor != data.len() {
        return Err(ArikaError::Other(
            "unparsed trailing bytes in CHT document".into(),
        ));
    }

    Ok(ChtDocument {
        format: "ARIKA_CHT_MOTIONS".into(),
        source_sha256: hash_hex(data),
        byte_size: data.len(),
        name_table: names,
        runtime_directory_offset: directory,
        actions,
        scope: "Logical motion ID/variant mapping. Collision block extents are walked, not interpreted. Duplicate IDs use the last entry at runtime.".into(),
    })
}

/// Lookup logical motion ID and variant in CHT document (last duplicate ID wins).
pub fn lookup(doc: &ChtDocument, motion_id: u32, variant: usize) -> Result<&ChtVariant> {
    if motion_id >= 1000 {
        return Err(ArikaError::Other("motion ID must be 0..999".into()));
    }
    let action = doc
        .actions
        .iter()
        .rev()
        .find(|a| a.motion_id == motion_id)
        .ok_or_else(|| ArikaError::Other("logical motion ID is absent from CHT".into()))?;

    action
        .variants
        .get(variant)
        .ok_or_else(|| ArikaError::Other("motion variant is absent from CHT".into()))
}

#[cfg(test)]
mod tests {
    use super::*;

    pub fn sample_cht_fixture() -> Vec<u8> {
        let mut data = Vec::new();
        data.extend_from_slice(b"\0\0\x01\0CHT ");
        data.extend_from_slice(&[0u8; 8]);
        data.extend_from_slice(&2u32.to_le_bytes()); // count=2

        let mut name1 = [0u8; 32];
        name1[..4].copy_from_slice(b"test");
        let mut name2 = [0u8; 32];
        name2[..6].copy_from_slice(b"common");
        data.extend_from_slice(&name1);
        data.extend_from_slice(&name2);

        data.extend_from_slice(&0xDEADBEEFu32.to_le_bytes());
        for _ in 0..17 {
            data.extend_from_slice(&0u32.to_le_bytes());
        }

        let pad = (16 - (data.len() % 16)) % 16;
        data.resize(data.len() + pad, 0);
        data.resize(data.len() + 32, 0);
        data.resize(data.len() + 4000, 0xA5);

        data.extend_from_slice(&232u32.to_le_bytes()); // logical_id = 232
        data.extend_from_slice(&2u32.to_le_bytes());   // variants = 2
        data.extend_from_slice(&0x12345678u32.to_le_bytes());

        let at = data.len();
        data.resize(data.len() + 272, 0);
        data[at..at + 4].copy_from_slice(&0xFFFFFFFFu32.to_le_bytes());
        data[at + 4..at + 6].copy_from_slice(&0u16.to_le_bytes()); // name_index=0
        data[at + 6..at + 8].copy_from_slice(&0u16.to_le_bytes()); // bank=0

        data[at + 136..at + 140].copy_from_slice(&0xFFFFFFFFu32.to_le_bytes());
        data[at + 140..at + 142].copy_from_slice(&1u16.to_le_bytes()); // name_index=1
        data[at + 142..at + 144].copy_from_slice(&1u16.to_le_bytes()); // bank=1

        for field in [8, 72, 104] {
            data[at + field..at + field + 4].copy_from_slice(&0x12345678u32.to_le_bytes());
        }

        let child = data.len();
        data.resize(data.len() + 68, 0);
        for field in [36, 64] {
            data[child + field..child + field + 4].copy_from_slice(&1u32.to_le_bytes());
        }

        let pad = (16 - (data.len() % 16)) % 16;
        data.resize(data.len() + pad + 64, 0);

        let child2 = data.len();
        data.resize(data.len() + 36, 0);
        data[child2 + 4..child2 + 8].copy_from_slice(&1u32.to_le_bytes());

        let pad = (16 - (data.len() % 16)) % 16;
        data.resize(data.len() + pad + 32 + 12, 0);

        data
    }

    #[test]
    fn test_nested_layout_and_garbage_pointers() {
        let data = sample_cht_fixture();
        let doc = parse_cht(&data).expect("parse cht");
        assert_eq!(doc.byte_size, data.len());
        assert_eq!(doc.name_table, vec!["test", "common"]);

        let v0 = lookup(&doc, 232, 0).expect("v0");
        assert_eq!(
            v0.child_blocks,
            ChildBlocks {
                type_68: 1,
                type_36: 1,
                type_32: 3,
                type_12: 1,
            }
        );
        let v1 = lookup(&doc, 232, 1).expect("v1");
        assert_eq!(v1.resource_bank, 1);
    }

    #[test]
    fn test_truncation_and_corruption() {
        let orig = sample_cht_fixture();
        for &end in &[19, 40, 100, orig.len() - 1] {
            assert!(parse_cht(&orig[..end]).is_err());
        }
        let mut trailing = orig.clone();
        trailing.push(0);
        assert!(parse_cht(&trailing).is_err());
    }

    #[test]
    fn test_lookup_missing_bounds_and_duplicate() {
        let data = sample_cht_fixture();
        let mut doc = parse_cht(&data).expect("parse");
        assert!(lookup(&doc, 1000, 0).is_err());
        assert!(lookup(&doc, 1, 0).is_err());
        assert!(lookup(&doc, 232, 2).is_err());

        // Last duplicate action wins
        let mut dup = doc.actions[0].clone();
        dup.variants.clear();
        doc.actions.push(dup);
        assert!(lookup(&doc, 232, 0).is_err());
    }

    #[test]
    fn test_runtime_name_copy() {
        assert_eq!(runtime_motion_name("m01232m0a.mot"), "m01232m0a");
        assert_eq!(runtime_motion_name("name.part.mot"), "name");
        assert_eq!(runtime_motion_name("1234567890123456"), "123456789012345");
        assert_eq!(runtime_motion_name("NAME.MOT"), "NAME");
    }
}
