//! PS2 ADPCM audio decoding/encoding and ASE/AMS bank parsing.
//! Matches arika_audio.py / arika_audio_import.py exactly.

use crate::error::{ArikaError, Result};

pub const HEADER: usize = 0x800;
pub const INTERLEAVE: usize = 0x8000;

/// SPU2 ADPCM prediction coefficients.
pub const COEFFICIENTS: [(i32, i32); 5] = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)];

/// Convert SPU2 pitch to sample rate: pitch * 48000 / 4096.
pub fn sample_rate(pitch: u32) -> u32 {
    if pitch == 0 || pitch > 0x3FFF {
        return 0;
    }
    pitch * 48000 / 4096
}

/// Truncate toward zero (C integer division semantics).
fn trunc_div(value: i32, divisor: i32) -> i32 {
    if value >= 0 {
        value / divisor
    } else {
        -((-value) / divisor)
    }
}

/// Decode one ADPCM block (16 bytes), updating history.
fn decode_block(data: &[u8], h1: &mut i32, h2: &mut i32, out: &mut Vec<i16>) -> Result<()> {
    if data.len() < 16 {
        return Err(ArikaError::Other("partial ADPCM frame".into()));
    }
    let header = data[0];
    let flags = data[1];
    let predictor = (header >> 4) as usize;
    let shift = (header & 0x0F) as usize;
    if predictor > 4 || shift > 12 || flags > 7 {
        return Err(ArikaError::Other(format!(
            "invalid ADPCM frame: predictor={predictor} shift={shift} flags={flags}"
        )));
    }
    let (c1, c2) = COEFFICIENTS[predictor];

    for byte in &data[2..16] {
        for nibble in [byte & 0x0F, byte >> 4] {
            let signed = if nibble & 0x08 != 0 {
                (nibble as i8 as i32) - 16
            } else {
                nibble as i32
            };
            let mut value = ((signed * 4096) >> shift) + trunc_div(*h1 * c1 + *h2 * c2, 64);
            if flags == 7 {
                value = 0;
            }
            value = value.clamp(-32768, 32767);
            out.push(value as i16);
            *h2 = *h1;
            *h1 = value;
        }
    }
    Ok(())
}

/// Decode PS2 ADPCM data, matching Python `arika_audio.decode_adpcm`.
pub fn decode_adpcm(data: &[u8]) -> Result<(Vec<i16>, (i32, i32))> {
    if data.len() % 16 != 0 {
        return Err(ArikaError::Other("partial ADPCM frame".into()));
    }
    let mut out = Vec::with_capacity(data.len() / 16 * 28);
    let mut h1 = 0i32;
    let mut h2 = 0i32;
    for at in (0..data.len()).step_by(16) {
        decode_block(&data[at..at + 16], &mut h1, &mut h2, &mut out)?;
    }
    Ok((out, (h1, h2)))
}

/// Estimate the prediction value from history (truncation toward zero).
fn predict(h1: i32, h2: i32, c1: i32, c2: i32) -> i32 {
    trunc_div(h1 * c1 + h2 * c2, 64)
}

/// Encode PCM samples to PS2 ADPCM, matching Python `arika_audio_import.encode_adpcm`.
pub fn encode_adpcm(
    samples: &[i16],
    first_flag: u8,
    last_flag: u8,
    minimum_frames: usize,
) -> Result<Vec<u8>> {
    if samples.is_empty() {
        return Err(ArikaError::Other("cannot encode empty audio".into()));
    }
    let frame_count = maximum(minimum_frames, (samples.len() + 27) / 28);
    let mut output = vec![0u8; frame_count * 16];
    let mut h1 = 0i32;
    let mut h2 = 0i32;

    for frame_index in 0..frame_count {
        let mut block: Vec<i32> = Vec::with_capacity(28);
        for k in 0..28 {
            let idx = frame_index * 28 + k;
            if idx < samples.len() {
                block.push(samples[idx] as i32);
            } else {
                block.push(0);
            }
        }

        let mut best: Option<(i64, usize, usize, Vec<u8>, i32, i32)> = None;
        for (filter_index, &(c1, c2)) in COEFFICIENTS.iter().enumerate() {
            let mut a = h1;
            let mut b = h2;
            let mut peak = 0i32;
            for &target in &block {
                peak = peak.max((target - predict(a, b, c1, c2)).abs());
                b = a;
                a = target;
            }
            let mut step = 1i32;
            while step < 4096 && peak > 7 * step {
                step *= 2;
            }
            let shift = 12 - (step as u32).ilog2() as usize;
            let shift_min = shift.saturating_sub(1);
            let shift_max = shift.min(11) + 1;

            for candidate_shift in shift_min..=shift_max {
                let quantizer = 1 << (12 - candidate_shift);
                let mut a = h1;
                let mut b = h2;
                let mut error: i64 = 0;
                let mut nibbles = Vec::with_capacity(14);
                for &target in &block {
                    let prediction = predict(a, b, c1, c2);
                    let delta = target - prediction;
                    let mut nibble = (delta + quantizer as i32 / 2) / quantizer as i32;
                    nibble = nibble.clamp(-8, 7);
                    let decoded = prediction + nibble * quantizer as i32;
                    let audible = decoded.clamp(-32768, 32767);
                    error += (audible as i64 - target as i64).pow(2);
                    nibbles.push((nibble & 15) as u8);
                    b = a;
                    a = decoded;
                }
                let candidate = (error, filter_index, candidate_shift, nibbles, a, b);
                if best.as_ref().map(|b| b.0 > candidate.0).unwrap_or(true) {
                    best = Some(candidate);
                }
            }
        }

        let (_, filter_index, shift, nibbles, new_h1, new_h2) = best.unwrap();
        let at = frame_index * 16;
        output[at] = (filter_index as u8) * 16 + (shift as u8);
        output[at + 1] = if frame_index == 0 { first_flag } else { 0 };
        if frame_index == frame_count - 1 {
            output[at + 1] = last_flag;
        }
        for index in 0..14 {
            output[at + 2 + index] = nibbles[index * 2] | (nibbles[index * 2 + 1] << 4);
        }
        h1 = new_h1;
        h2 = new_h2;
    }

    Ok(output)
}

/// One ASE sample entry: (pitch, offset).
#[derive(Debug, Clone)]
pub struct AseEntry {
    pub pitch: u32,
    pub offset: u32,
}

/// Parse an ASE audio bank, matching Python `arika_audio.ase_samples`.
pub fn ase_samples(data: &[u8]) -> Result<Vec<(u32, u32, Vec<u8>)>> {
    if data.len() < HEADER {
        return Err(ArikaError::Other("truncated ASE header".into()));
    }
    let version = u32_at(data, 0)?;
    let count = u32_at(data, 4)? as usize;
    let size = u32_at(data, 8)?;
    if version != 100 || size != (data.len() - HEADER) as u32 || 12usize + count * 8 > HEADER {
        return Err(ArikaError::Other("invalid ASE header".into()));
    }
    let mut entries = Vec::with_capacity(count);
    for i in 0..count {
        let pitch = u32_at(data, 12 + i * 8)?;
        let offset = u32_at(data, 12 + i * 8 + 4)?;
        entries.push(AseEntry { pitch, offset });
    }
    let mut offsets: Vec<usize> = entries.iter().map(|e| e.offset as usize).collect();
    offsets.push(size as usize);
    if offsets[0] != 0
        || offsets.windows(2).any(|w| w[0] >= w[1] || w[0] % 16 != 0)
        || size as usize % 16 != 0
    {
        return Err(ArikaError::Other("invalid ASE sample extents".into()));
    }
    let mut result = Vec::with_capacity(count);
    for (i, entry) in entries.iter().enumerate() {
        let end = offsets[i + 1];
        let payload_start = HEADER + entry.offset as usize;
        let payload_end = HEADER + end;
        if payload_end > data.len() {
            return Err(ArikaError::Other("ASE payload extends past data".into()));
        }
        let payload = &data[payload_start..payload_end];
        if payload.is_empty()
            || payload[1] != 4
            || payload[payload.len() - 15] != 3
        {
            return Err(ArikaError::Other("unexpected ASE start/end flags".into()));
        }
        result.push((entry.pitch, sample_rate(entry.pitch), payload.to_vec()));
    }
    Ok(result)
}

/// Parse an AMS audio stream, matching Python `arika_audio.ams_channels`.
pub fn ams_channels(data: &[u8]) -> Result<(u32, Vec<u8>, Vec<u8>)> {
    if data.len() < HEADER {
        return Err(ArikaError::Other("truncated AMS header".into()));
    }
    let version = u32_at(data, 0)?;
    let pitch = u32_at(data, 4)?;
    let channel_size = u32_at(data, 8)?;
    let pairs = u32_at(data, 12)?;
    if version != 120 {
        return Err(ArikaError::Other("invalid AMS version".into()));
    }
    if data.len() != HEADER + pairs as usize * 0x20000 {
        return Err(ArikaError::Other("invalid AMS header or padded size".into()));
    }
    if channel_size == 0 || channel_size > pairs as u32 * 0x10000u32 || channel_size % 16 != 0 {
        return Err(ArikaError::Other("invalid AMS audio length".into()));
    }
    // Physical stereo blocks: 0,2,4,... then ...,5,3,1 in playback order.
    let pair_count = pairs as usize;
    let mut order: Vec<usize> = (0..pair_count * 2).step_by(2).collect();
    order.extend((1..pair_count * 2).rev().step_by(2));

    let mut left = Vec::new();
    let mut right = Vec::new();
    for &index in &order {
        let at = HEADER + index * 0x10000;
        left.extend_from_slice(&data[at..at + INTERLEAVE]);
        right.extend_from_slice(&data[at + INTERLEAVE..at + 2 * INTERLEAVE]);
    }
    let channel_size = channel_size as usize;
    left.truncate(channel_size);
    right.truncate(channel_size);
    Ok((sample_rate(pitch), left, right))
}

/// WAV header (44 bytes, PCM format).
fn wav_header(channel_count: u16, sample_rate: u32, byte_count: usize) -> Vec<u8> {
    let block_align = channel_count * 2;
    let byte_rate = sample_rate * block_align as u32;
    let mut h: Vec<u8> = Vec::with_capacity(44);
    h.extend_from_slice(b"RIFF");
    h.extend_from_slice(&(36 + byte_count as u32).to_le_bytes());
    h.extend_from_slice(b"WAVE");
    h.extend_from_slice(b"fmt ");
    h.extend_from_slice(&16u32.to_le_bytes());
    h.extend_from_slice(&1u16.to_le_bytes()); // PCM
    h.extend_from_slice(&channel_count.to_le_bytes());
    h.extend_from_slice(&sample_rate.to_le_bytes());
    h.extend_from_slice(&byte_rate.to_le_bytes());
    h.extend_from_slice(&block_align.to_le_bytes());
    h.extend_from_slice(&16u16.to_le_bytes());
    h.extend_from_slice(b"data");
    h.extend_from_slice(&(byte_count as u32).to_le_bytes());
    h
}

/// Write interleaved 16-bit PCM WAV.
pub fn write_wav(channels: &[Vec<i16>], sample_rate: u32) -> Result<Vec<u8>> {
    if channels.is_empty() {
        return Err(ArikaError::Other("no channels".into()));
    }
    let frame_count = channels[0].len();
    if channels.iter().any(|c| c.len() != frame_count) {
        return Err(ArikaError::Other("unequal channel lengths".into()));
    }
    let channel_count = channels.len() as u16;
    let byte_count = frame_count * channel_count as usize * 2;
    let mut out = wav_header(channel_count, sample_rate, byte_count);
    for frame in 0..frame_count {
        for ch in 0..channel_count {
            let s = channels[ch as usize][frame];
            out.extend_from_slice(&s.to_le_bytes());
        }
    }
    Ok(out)
}

/// Read a 16-bit PCM WAV, returning (sample_rate, channels).
pub fn read_wav(data: &[u8]) -> Result<(u32, Vec<Vec<i16>>)> {
    if data.len() < 44 || &data[0..4] != b"RIFF" || &data[8..12] != b"WAVE" {
        return Err(ArikaError::Other("not a RIFF WAV".into()));
    }
    if &data[12..16] != b"fmt " {
        return Err(ArikaError::Other("missing fmt chunk".into()));
    }
    let fmt_size = u32_at(data, 16)?;
    if fmt_size < 16 {
        return Err(ArikaError::Other("truncated fmt chunk".into()));
    }
    let audio_format = u16_at(data, 20)?;
    if audio_format != 1 {
        return Err(ArikaError::Other("WAV must be PCM".into()));
    }
    let channel_count = u16_at(data, 22)? as usize;
    let rate = u32_at(data, 24)?;
    let _byte_rate = u32_at(data, 28)?;
    let block_align = u16_at(data, 32)?;
    let bits = u16_at(data, 34)?;
    if bits != 16 {
        return Err(ArikaError::Other("WAV must be 16-bit".into()));
    }
    if block_align as usize != channel_count * 2 {
        return Err(ArikaError::Other("unexpected block align".into()));
    }
    if &data[36..40] != b"data" {
        return Err(ArikaError::Other("missing data chunk".into()));
    }
    let data_size = u32_at(data, 40)? as usize;
    let data_start = 44;
    if data_start + data_size > data.len() {
        return Err(ArikaError::Other("truncated WAV data".into()));
    }
    let frames = data_size / (channel_count * 2);
    let mut channels = vec![Vec::with_capacity(frames); channel_count];
    for frame in 0..frames {
        for ch in 0..channel_count {
            let o = data_start + frame * channel_count * 2 + ch * 2;
            channels[ch].push(i16::from_le_bytes([data[o], data[o + 1]]));
        }
    }
    Ok((rate, channels))
}

/// Compute pitch from a sample rate (inverse of sample_rate).
pub fn pitch_for_rate(rate: u32, original_pitch: u32) -> Result<u32> {
    if rate == sample_rate(original_pitch) {
        return Ok(original_pitch);
    }
    let pitch = (rate * 4096 + 24000) / 48000;
    if pitch < 1 || pitch > 0x3FFF {
        return Err(ArikaError::Other(
            "WAV sample rate is outside the supported SPU2 pitch range".into(),
        ));
    }
    Ok(pitch)
}

fn u32_at(data: &[u8], offset: usize) -> Result<u32> {
    if offset + 4 > data.len() {
        return Err(ArikaError::Other("truncated u32".into()));
    }
    Ok(u32::from_le_bytes([data[offset], data[offset + 1], data[offset + 2], data[offset + 3]]))
}

fn u16_at(data: &[u8], offset: usize) -> Result<u16> {
    if offset + 2 > data.len() {
        return Err(ArikaError::Other("truncated u16".into()));
    }
    Ok(u16::from_le_bytes([data[offset], data[offset + 1]]))
}

fn maximum(a: usize, b: usize) -> usize {
    if a > b { a } else { b }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_signed_nibbles() {
        let data = bytes([12u8, 0])
            .into_iter()
            .chain(bytes([0x8f]).repeat(14).into_iter())
            .collect::<Vec<_>>();
        let (pcm, _) = decode_adpcm(&data).expect("decode");
        let expected: Vec<i16> = [-1i16, -8].repeat(14);
        assert_eq!(pcm, expected);
    }

    #[test]
    fn test_history_across_chunks() {
        let block = bytes([0x12u8, 0])
            .into_iter()
            .chain(bytes([0x12]).repeat(14).into_iter())
            .collect::<Vec<_>>();
        let whole_data = block
            .clone()
            .into_iter()
            .chain(block.clone().into_iter())
            .collect::<Vec<_>>();
        let (whole, _) = decode_adpcm(&whole_data).expect("decode whole");
        let (first, history) = decode_adpcm(&block).expect("decode first");
        let (last, _) = decode_adpcm_with_history(&block, history).expect("decode last");
        assert_eq!(
            whole,
            first.iter().chain(last.iter()).copied().collect::<Vec<_>>()
        );
    }

    #[test]
    fn test_pitch() {
        assert_eq!(sample_rate(4096), 48000);
        assert_eq!(sample_rate(1536), 18000);
        assert_eq!(sample_rate(1365), 15996);
    }

    #[test]
    fn test_bank() {
        let payload = bytes([12u8, 4])
            .into_iter()
            .chain(zero_bytes(14).into_iter())
            .chain(bytes([12u8, 3]).into_iter())
            .chain(zero_bytes(14).into_iter())
            .collect::<Vec<_>>();
        let mut header = vec![0u8; 2048];
        header[0..4].copy_from_slice(&100u32.to_le_bytes()); // version
        header[4..8].copy_from_slice(&1u32.to_le_bytes());   // count
        header[8..12].copy_from_slice(&32u32.to_le_bytes()); // size
        header[12..16].copy_from_slice(&1536u32.to_le_bytes()); // pitch
        header[16..20].copy_from_slice(&0u32.to_le_bytes()); // offset
        let data: Vec<u8> = header.iter().chain(payload.iter()).copied().collect();
        let samples = ase_samples(&data).expect("ase");
        assert_eq!(samples.len(), 1);
        assert_eq!(samples[0].0, 1536);
        assert_eq!(samples[0].1, 18000);
        assert_eq!(samples[0].2, payload);
    }

    #[test]
    fn test_stream_order_and_trim() {
        // Physical blocks 0,1,2,3 become 0,2,3,1; two channel chunks per block.
        let mut header = vec![0u8; 2048];
        header[0..4].copy_from_slice(&120u32.to_le_bytes()); // version
        header[4..8].copy_from_slice(&4096u32.to_le_bytes()); // pitch
        header[8..12].copy_from_slice(&((3 * 32768 + 16) as u32).to_le_bytes()); // channel_size
        header[12..16].copy_from_slice(&2u32.to_le_bytes()); // pairs
        let mut body = Vec::new();
        for i in 0..4usize {
            body.extend(bytes([(i * 2) as u8]).repeat(32768));
            body.extend(bytes([(i * 2 + 1) as u8]).repeat(32768));
        }
        let data: Vec<u8> = header.iter().chain(body.iter()).copied().collect();
        let (rate, left, right) = ams_channels(&data).expect("ams");
        assert_eq!(rate, 48000);
        assert_eq!(
            left,
            bytes([0])
                .repeat(32768)
                .into_iter()
                .chain(bytes([4]).repeat(32768).into_iter())
                .chain(bytes([6]).repeat(32768).into_iter())
                .chain(bytes([2]).repeat(16).into_iter())
                .collect::<Vec<_>>()
        );
        assert_eq!(
            right,
            bytes([1])
                .repeat(32768)
                .into_iter()
                .chain(bytes([5]).repeat(32768).into_iter())
                .chain(bytes([7]).repeat(32768).into_iter())
                .chain(bytes([3]).repeat(16).into_iter())
                .collect::<Vec<_>>()
        );
    }

    #[test]
    fn test_reject_invalid_frames() {
        let payloads: Vec<Vec<u8>> = vec![
            zero_bytes(15),
            bytes([0x50u8, 0]).into_iter().chain(zero_bytes(14).into_iter()).collect(),
            bytes([13u8, 0]).into_iter().chain(zero_bytes(14).into_iter()).collect(),
        ];
        for payload in payloads {
            assert!(decode_adpcm(&payload).is_err());
        }
    }

    fn zero_bytes(n: usize) -> Vec<u8> {
        vec![0u8; n]
    }

    fn bytes<const N: usize>(arr: [u8; N]) -> Vec<u8> {
        arr.to_vec()
    }

    fn decode_adpcm_with_history(data: &[u8], history: (i32, i32)) -> Result<(Vec<i16>, (i32, i32))> {
        if data.len() % 16 != 0 {
            return Err(ArikaError::Other("partial ADPCM frame".into()));
        }
        let mut out = Vec::with_capacity(data.len() / 16 * 28);
        let mut h1 = history.0;
        let mut h2 = history.1;
        for at in (0..data.len()).step_by(16) {
            decode_block(&data[at..at + 16], &mut h1, &mut h2, &mut out)?;
        }
        Ok((out, (h1, h2)))
    }
}
