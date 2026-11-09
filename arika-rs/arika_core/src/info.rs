//! INFO.DAT codec and constants.
//!
//! Signature / key: first 16 bytes, of which bytes 1..16 must be `www.arika.co.jp`.
//! Byte 0 varies by region (EU beta 0x7F, etc.).

use crate::error::{ArikaError, Result};

/// Codec key / signature prefix (byte 0 is region-specific).
pub const MAGIC: &[u8; 16] = b"\x7fwww.arika.co.jp";

/// Bytes 1..16 of the INFO.DAT signature / codec key (always `www.arika.co.jp`).
pub const INFO_MAGIC_TAIL: &[u8; 15] = b"www.arika.co.jp";

pub const SECTOR: u64 = 2048;
pub const HEADER: usize = 0x30;
pub const RECORD: usize = 0x30;

/// Region-specific byte 0 values for the INFO.DAT codec key.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InfoRegion {
    EuBeta,
    Eu,
    Usa,
    Jpn,
    Dvb1,
}

impl InfoRegion {
    pub fn byte0(self) -> u8 {
        match self {
            InfoRegion::EuBeta => 0x7F,
            InfoRegion::Eu => 0x11,
            InfoRegion::Usa => 0xC2,
            InfoRegion::Jpn => 0x60,
            InfoRegion::Dvb1 => 0xBB,
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s.trim().to_lowercase().as_str() {
            "eu-beta" | "eubeta" | "eu_beta" => Some(InfoRegion::EuBeta),
            "eu" => Some(InfoRegion::Eu),
            "usa" => Some(InfoRegion::Usa),
            "jpn" => Some(InfoRegion::Jpn),
            "db1" | "dvb1" | "arcade" | "db1.b" | "db1_ver_b" => Some(InfoRegion::Dvb1),
            _ => None,
        }
    }
}

#[inline]
fn swap_nibbles(value: u8) -> u8 {
    ((value & 0x0F) << 4) | (value >> 4)
}

/// Decode an encoded INFO.DAT buffer.
pub fn decode_info(data: &[u8]) -> Result<Vec<u8>> {
    if data.len() < HEADER || data.len() < 16 || data[1..16] != MAGIC[1..] {
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
    if data.len() < HEADER || data.len() < 16 || data[1..16] != MAGIC[1..] {
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

/// Build a decoded INFO.DAT header buffer (no records yet) for a given region byte.
/// The buffer is `HEADER` bytes: byte 0 = region byte, bytes 1..16 = `www.arika.co.jp`,
/// u32 entry count at 0x2C, the rest zero.
pub fn make_decoded_info(byte_0: u8, count: u32) -> Vec<u8> {
    let mut buf = vec![0u8; HEADER];
    buf[0] = byte_0;
    buf[1..16].copy_from_slice(INFO_MAGIC_TAIL);
    buf[0x2C..0x30].copy_from_slice(&count.to_le_bytes());
    buf
}

/// Write one 0x30-byte entry record into a decoded INFO buffer at the given index.
/// The name is written as CP932/ASCII bytes; remaining name bytes stay zero.
pub fn write_info_record(
    decoded: &mut [u8],
    index: usize,
    name: &str,
    unknown: u32,
    sector: u32,
    sectors: u32,
    size: u32,
) -> Result<()> {
    let at = HEADER + index * RECORD;
    if at + RECORD > decoded.len() {
        return Err(ArikaError::Other(format!(
            "record index {} out of bounds (decoded len {})",
            index,
            decoded.len()
        )));
    }
    let name_bytes = name.as_bytes();
    if name_bytes.len() > 32 {
        return Err(ArikaError::Other(format!(
            "asset name too long ({} bytes): {}",
            name_bytes.len(),
            name
        )));
    }
    decoded[at..at + name_bytes.len()].copy_from_slice(name_bytes);
    decoded[at + 32..at + 36].copy_from_slice(&unknown.to_le_bytes());
    decoded[at + 36..at + 40].copy_from_slice(&sector.to_le_bytes());
    decoded[at + 40..at + 44].copy_from_slice(&sectors.to_le_bytes());
    decoded[at + 44..at + 48].copy_from_slice(&size.to_le_bytes());
    Ok(())
}

/// Encode a decoded INFO buffer using an explicitly supplied 16-byte key instead of
/// deriving it from `data[..16]`. Useful when building INFO.DAT from scratch without
/// a seed file: supply the region byte 0 plus `www.arika.co.jp` as the key.
pub fn encode_info_with_key(key: &[u8; 16], data: &[u8]) -> Result<Vec<u8>> {
    if data.len() < HEADER {
        return Err(ArikaError::InvalidDecodedHeader);
    }
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

    #[test]
    fn roundtrip_all_byte_values() {
        // Match Python test_codec_all_byte_values: for every first byte value,
        // encode then decode must roundtrip.
        for first_byte in 0u8..=255u8 {
            let mut plain = vec![0u8; HEADER + 256 * 7];
            plain[0] = first_byte;
            plain[1..16].copy_from_slice(&MAGIC[1..]);
            for (i, chunk) in plain[16..].chunks_mut(256).enumerate() {
                for (j, b) in chunk.iter_mut().enumerate() {
                    *b = ((i * 256 + j) % 256) as u8;
                }
            }
            let encoded = encode_info(&plain).unwrap();
            let decoded = decode_info(&encoded).unwrap();
            assert_eq!(decoded, plain, "roundtrip failed for first_byte={first_byte}");
        }
    }

    #[test]
    fn make_decoded_info_uses_region_byte0() {
        let buf = make_decoded_info(0xBB, 3);
        assert_eq!(buf[0], 0xBB);
        assert_eq!(&buf[1..16], INFO_MAGIC_TAIL);
        assert_eq!(u32::from_le_bytes(buf[0x2C..0x30].try_into().unwrap()), 3);
        assert_eq!(buf.len(), HEADER);
    }

    #[test]
    fn write_info_record_sets_fields() {
        let mut buf = make_decoded_info(0x7F, 1);
        buf.resize(HEADER + RECORD, 0);
        write_info_record(&mut buf, 0, "TEST.BIN", 0, 5, 2, 100).unwrap();
        assert_eq!(&buf[HEADER..HEADER + 8], b"TEST.BIN");
        assert_eq!(u32::from_le_bytes(buf[HEADER + 36..HEADER + 40].try_into().unwrap()), 5);
        assert_eq!(u32::from_le_bytes(buf[HEADER + 40..HEADER + 44].try_into().unwrap()), 2);
        assert_eq!(u32::from_le_bytes(buf[HEADER + 44..HEADER + 48].try_into().unwrap()), 100);
    }

    #[test]
    fn encode_info_with_key_matches_region() {
        let mut plain = vec![0u8; HEADER + 16];
        plain[0] = 0xC2;
        plain[1..16].copy_from_slice(INFO_MAGIC_TAIL);
        plain[0x2C..0x30].copy_from_slice(&1u32.to_le_bytes());
        let key: [u8; 16] = [0xC2, 0x77, 0x77, 0x77, 0x2E, 0x61, 0x72, 0x69, 0x6B, 0x61, 0x2E, 0x63, 0x6F, 0x2E, 0x6A, 0x70];
        let encoded = encode_info_with_key(&key, &plain).unwrap();
        let decoded = decode_info(&encoded).unwrap();
        assert_eq!(decoded, plain);
    }
}
