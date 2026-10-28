//! INFO.DAT codec and constants.
//!
//! Signature / key: first 16 bytes, of which bytes 1..16 must be `www.arika.co.jp`.
//! Byte 0 varies by region (EU beta 0x7F, etc.).

use crate::error::{ArikaError, Result};

/// Codec key / signature prefix (byte 0 is region-specific).
pub const MAGIC: &[u8; 16] = b"\x7fwww.arika.co.jp";

pub const SECTOR: u64 = 2048;
pub const HEADER: usize = 0x30;
pub const RECORD: usize = 0x30;

#[inline]
fn swap_nibbles(value: u8) -> u8 {
    ((value & 0x0F) << 4) | (value >> 4)
}

/// Decode an encoded INFO.DAT buffer.
pub fn decode_info(data: &[u8]) -> Result<Vec<u8>> {
    if data.len() < HEADER || &data[1..16] != &MAGIC[1..] {
        return Err(ArikaError::InvalidInfoMagic);
    }
    let key = &data[..16];
    let mut out = Vec::with_capacity(data.len());
    out.extend_from_slice(key);
    for (i, &value) in data[16..].iter().enumerate() {
        let decoded = (!swap_nibbles(value)).wrapping_sub(key[i & 15]);
        out.push(decoded);
    }
    Ok(out)
}

/// Encode a decoded INFO buffer back to the on-disk form.
pub fn encode_info(data: &[u8]) -> Result<Vec<u8>> {
    if data.len() < HEADER || &data[1..16] != &MAGIC[1..] {
        return Err(ArikaError::InvalidDecodedHeader);
    }
    let key = &data[..16];
    let mut out = Vec::with_capacity(data.len());
    out.extend_from_slice(key);
    for (i, &value) in data[16..].iter().enumerate() {
        let encoded = swap_nibbles((!value.wrapping_add(key[i & 15])) & 0xFF);
        out.push(encoded);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_emptyish() {
        let mut raw = vec![0u8; HEADER];
        raw[..16].copy_from_slice(MAGIC);
        // set file count = 0
        raw[0x2C..0x30].copy_from_slice(&0u32.to_le_bytes());
        let decoded = decode_info(&raw).unwrap();
        let encoded = encode_info(&decoded).unwrap();
        assert_eq!(encoded, raw);
    }
}
