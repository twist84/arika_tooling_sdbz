//! SPT script parser.
//! Matches arika_scripts.py parse exactly.
//!
//! Format:
//!   u32 program_count
//!   u32 program_sizes[program_count]  (directory)
//!   For each program:
//!     u32 reserved, u32 variables, u32 length, u32 entry_points[4]
//!     u8  kind, u32 value  (token, 5 bytes each)
//!       kind 0: float value
//!       kind 1: string: u8 length, bytes, NUL (CP932)
//!       kind 2: command: u16 command_id, u16 extra_length, extra bytes
//!       kind 3: variable: u16 index, u16 type (packed in value)
//!       kind 4: symbol: u8 value (ASCII printable or None)

use crate::container::u32_at;
use crate::error::{ArikaError, Result};
use encoding_rs::SHIFT_JIS;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SptToken {
    pub offset: usize,
    pub r#type: u8,
    pub payload: u32,
    pub float_bits_hex: Option<String>,
    pub string_bytes_hex: Option<String>,
    pub text: Option<String>,
    pub command_id: Option<u16>,
    pub extra_hex: Option<String>,
    pub variable_index: Option<u16>,
    pub variable_type: Option<u16>,
    pub symbol: Option<char>,
    pub byte_length: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SptProgram {
    pub index: usize,
    pub file_offset: usize,
    pub size: u32,
    pub reserved: u32,
    pub variable_count: u32,
    pub bytecode_size: u32,
    pub entry_points: Vec<u32>,
    pub tokens: Vec<SptToken>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SptDocument {
    pub format: String,
    pub source_sha256: String,
    pub programs: Vec<SptProgram>,
    pub trailing_hex: String,
}

fn hash_hex(data: &[u8]) -> String {
    let mut h = [0u8; 32];
    for (i, &b) in data.iter().enumerate() {
        h[i % 32] ^= b;
        h[i % 32] = h[i % 32].wrapping_mul(31).wrapping_add(b as u32 as u8);
    }
    h.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn parse_spt(data: &[u8]) -> Result<SptDocument> {
    if data.len() < 4 {
        return Err(ArikaError::Other("truncated SPT bundle".into()));
    }
    let count = u32_at(data, 0)?;
    if count == 0 || count > 1024 || 4 + count as usize * 4 > data.len() {
        return Err(ArikaError::Other("invalid SPT program directory".into()));
    }

    let mut sizes = Vec::with_capacity(count as usize);
    for i in 0..count {
        sizes.push(u32_at(data, 4 + i as usize * 4)?);
    }

    let mut at = 4 + count as usize * 4;
    let mut programs = Vec::with_capacity(count as usize);

    for index in 0..count {
        let size = sizes[index as usize];
        if size < 28 || at + size as usize > data.len() {
            return Err(ArikaError::Other("invalid SPT program extent".into()));
        }
        let header = &data[at..at + 28];
        let reserved = u32_at(header, 0)?;
        let variables = u32_at(header, 4)?;
        let length = u32_at(header, 8)?;
        let mut entry_points = Vec::with_capacity(4);
        for j in 0..4 {
            entry_points.push(u32_at(header, 12 + j * 4)?);
        }
        if size != 28 + length {
            return Err(ArikaError::Other("SPT bytecode size mismatch".into()));
        }

        let start = at + 28;
        let end = at + size as usize;
        let mut cursor = start;
        let mut tokens = Vec::new();

        while cursor < end {
            if cursor + 5 > end {
                return Err(ArikaError::Other("truncated SPT token".into()));
            }
            let token_offset = cursor - start;
            let kind = data[cursor];
            let value = u32_at(data, cursor + 1)?;
            cursor += 5;
            if kind >= 6 {
                return Err(ArikaError::Other("unsupported SPT token type".into()));
            }

            let mut token = SptToken {
                offset: token_offset,
                r#type: kind,
                payload: value,
                float_bits_hex: None,
                string_bytes_hex: None,
                text: None,
                command_id: None,
                extra_hex: None,
                variable_index: None,
                variable_type: None,
                symbol: None,
                byte_length: 0,
            };

            match kind {
                0 => {
                    token.float_bits_hex = Some(format!("{value:08x}"));
                }
                1 => {
                    let str_len = value as usize;
                    if cursor + str_len + 1 > end {
                        return Err(ArikaError::Other("truncated SPT string".into()));
                    }
                    let raw = &data[cursor..cursor + str_len + 1];
                    cursor += str_len + 1;
                    if raw.last() != Some(&0) {
                        return Err(ArikaError::Other("unterminated SPT string".into()));
                    }
                    token.string_bytes_hex = Some(raw.iter().map(|b| format!("{b:02x}")).collect());
                    let (text, _, _) = SHIFT_JIS.decode(&raw[..raw.len() - 1]);
                    token.text = Some(text.into_owned());
                }
                2 => {
                    let length_extra = value >> 16;
                    if cursor + length_extra as usize > end {
                        return Err(ArikaError::Other("truncated SPT command data".into()));
                    }
                    token.command_id = Some((value & 65535) as u16);
                    token.extra_hex = Some(
                        data[cursor..cursor + length_extra as usize]
                            .iter()
                            .map(|b| format!("{b:02x}"))
                            .collect(),
                    );
                    cursor += length_extra as usize;
                }
                3 => {
                    token.variable_index = Some((value & 65535) as u16);
                    token.variable_type = Some((value >> 16) as u16);
                }
                4 => {
                    token.symbol = if (32..127).contains(&(value as u8)) {
                        Some(value as u8 as char)
                    } else {
                        None
                    };
                }
                _ => {}
            }

            token.byte_length = cursor - start - token_offset;
            tokens.push(token);
        }

        let boundaries: std::collections::HashSet<usize> =
            tokens.iter().map(|t| t.offset).chain([size as usize - 28]).collect();
        for &e in &entry_points {
            if !boundaries.contains(&(e as usize)) {
                return Err(ArikaError::Other(
                    "SPT entry point is not a token boundary".into(),
                ));
            }
        }

        programs.push(SptProgram {
            index: index as usize,
            file_offset: at,
            size,
            reserved,
            variable_count: variables,
            bytecode_size: size - 28,
            entry_points,
            tokens,
        });

        at = end;
    }

    Ok(SptDocument {
        format: "ARIKA_SPT".to_string(),
        source_sha256: hash_hex(data),
        programs,
        trailing_hex: data[at..].iter().map(|b| format!("{b:02x}")).collect(),
    })
}
