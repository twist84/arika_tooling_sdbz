//! Generic FPIX / FMDL / RFSM style directory chunks.

use crate::error::{ArikaError, Result};
use byteorder::{LittleEndian, ReadBytesExt};
use std::collections::HashMap;
use std::io::Cursor;

/// A tagged chunk with magic + size header.
#[derive(Debug, Clone)]
pub struct Chunk {
    pub magic: [u8; 4],
    pub data: Vec<u8>,
}

impl Chunk {
    pub fn magic_str(&self) -> String {
        String::from_utf8_lossy(&self.magic)
            .trim_matches('\0')
            .to_string()
    }
}

/// Parse a top-level container (FPIX, FMDL, RFSM, …) that has:
/// magic[4] | size u32 | count u32 | reserved[16] | offsets[count]
pub fn parse_directory(data: &[u8], expected_magic: Option<&[u8; 4]>) -> Result<Vec<Chunk>> {
    if data.len() < 32 {
        return Err(ArikaError::Other("truncated directory header".into()));
    }
    let mut magic = [0u8; 4];
    magic.copy_from_slice(&data[0..4]);
    if let Some(exp) = expected_magic {
        if &magic != exp {
            return Err(ArikaError::Other(format!(
                "expected magic {:?}, got {:?}",
                String::from_utf8_lossy(exp),
                String::from_utf8_lossy(&magic)
            )));
        }
    }
    let size = u32_at(data, 4)? as usize;
    // Some extracts pad to sector size; allow trailing padding.
    if size > data.len() {
        return Err(ArikaError::Other(format!(
            "chunk size mismatch: header {size} vs data {}",
            data.len()
        )));
    }
    let count = u32_at(data, 8)? as usize;
    if 32 + count * 4 > data.len() {
        return Err(ArikaError::Other("truncated chunk directory".into()));
    }
    let mut offsets = Vec::with_capacity(count);
    for i in 0..count {
        offsets.push(u32_at(data, 32 + i * 4)? as usize);
    }
    let mut result = Vec::with_capacity(count);
    for (i, &start) in offsets.iter().enumerate() {
        let end = if i + 1 < count {
            offsets[i + 1]
        } else {
            data.len()
        };
        if start + 8 > end || end > data.len() {
            return Err(ArikaError::Other("invalid child extent".into()));
        }
        let child_size = u32_at(data, start + 4)? as usize;
        if child_size != end - start {
            return Err(ArikaError::Other("child size mismatch".into()));
        }
        let mut child_magic = [0u8; 4];
        child_magic.copy_from_slice(&data[start..start + 4]);
        result.push(Chunk {
            magic: child_magic,
            data: data[start..end].to_vec(),
        });
    }
    Ok(result)
}

/// Group chunks by magic string.
pub fn group_by_magic(chunks: &[Chunk]) -> HashMap<String, Vec<&Chunk>> {
    let mut map: HashMap<String, Vec<&Chunk>> = HashMap::new();
    for c in chunks {
        map.entry(c.magic_str()).or_default().push(c);
    }
    map
}

pub fn u32_at(data: &[u8], offset: usize) -> Result<u32> {
    if offset + 4 > data.len() {
        return Err(ArikaError::Other("truncated u32".into()));
    }
    let mut c = Cursor::new(&data[offset..offset + 4]);
    Ok(c.read_u32::<LittleEndian>()?)
}

pub fn i32_at(data: &[u8], offset: usize) -> Result<i32> {
    if offset + 4 > data.len() {
        return Err(ArikaError::Other("truncated i32".into()));
    }
    let mut c = Cursor::new(&data[offset..offset + 4]);
    Ok(c.read_i32::<LittleEndian>()?)
}

pub fn f32_at(data: &[u8], offset: usize) -> Result<f32> {
    if offset + 4 > data.len() {
        return Err(ArikaError::Other("truncated f32".into()));
    }
    let mut c = Cursor::new(&data[offset..offset + 4]);
    Ok(c.read_f32::<LittleEndian>()?)
}

pub fn read_vec4(data: &[u8], offset: usize) -> Result<[f32; 4]> {
    Ok([
        f32_at(data, offset)?,
        f32_at(data, offset + 4)?,
        f32_at(data, offset + 8)?,
        f32_at(data, offset + 12)?,
    ])
}

/// Sequential NUL-terminated CP932 strings after a 0x20-byte header.
pub fn string_list(data: &[u8], count: usize) -> Result<Vec<String>> {
    if data.len() < 32 {
        return Err(ArikaError::Other("truncated string list header".into()));
    }
    let body = &data[32..];
    let mut names = Vec::with_capacity(count);
    let mut at = 0usize;
    for _ in 0..count {
        if at >= body.len() {
            return Err(ArikaError::Other("truncated name list".into()));
        }
        let end = body[at..]
            .iter()
            .position(|&b| b == 0)
            .map(|p| at + p)
            .unwrap_or(body.len());
        let (name, _, _) = encoding_rs::SHIFT_JIS.decode(&body[at..end]);
        names.push(name.into_owned());
        at = end + 1;
    }
    Ok(names)
}
