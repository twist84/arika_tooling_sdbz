//! TIM2 texture decode (PS2) — matches arika_dat.tim2_rgba.

use crate::error::{ArikaError, Result};

#[derive(Debug, Clone)]
pub struct Tim2Image {
    pub width: u32,
    pub height: u32,
    pub format: Tim2Format,
    /// RGBA8 pixels, row-major, top-left origin.
    pub rgba: Vec<u8>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tim2Format {
    Rgba32,
    Indexed4,
    Indexed8,
}

/// Decode an XPIX-wrapped TIM2 payload (32-byte XPIX wrapper then TIM2).
pub fn decode_xpix(data: &[u8]) -> Result<Tim2Image> {
    if data.len() < 36 {
        return Err(ArikaError::Other("truncated XPIX".into()));
    }
    // Full XPIX chunk: magic at 0, TIM2 at 32
    let tim2 = if &data[0..4] == b"XPIX" {
        if &data[32..36] != b"TIM2" {
            return Err(ArikaError::Other("XPIX without TIM2 body".into()));
        }
        &data[32..]
    } else if &data[0..4] == b"TIM2" {
        data
    } else {
        return Err(ArikaError::Other("expected XPIX or TIM2".into()));
    };
    decode_tim2(tim2)
}

/// Decode TIM2 matching Python `tim2_rgba`.
pub fn decode_tim2(data: &[u8]) -> Result<Tim2Image> {
    if data.len() < 16 || &data[0..4] != b"TIM2" {
        return Err(ArikaError::Other("expected TIM2".into()));
    }
    let version = data[4];
    let format_value = data[5];
    let pictures = u16::from_le_bytes([data[6], data[7]]);
    let _ = version;
    if format_value > 1 || pictures != 1 {
        return Err(ArikaError::Other(format!(
            "TIM2 format/pictures unsupported: format={format_value} pictures={pictures}"
        )));
    }
    // format 1 starts picture header at 128, format 0 at 16
    let at = if format_value == 1 { 128 } else { 16 };
    if at + 48 > data.len() {
        return Err(ArikaError::Other("truncated TIM2 picture".into()));
    }
    let total = u32_at(data, at)? as usize;
    let clut_size = u32_at(data, at + 4)? as usize;
    let image_size = u32_at(data, at + 8)? as usize;
    let header_size = u16_at(data, at + 12)? as usize;
    let colors = u16_at(data, at + 14)? as usize;
    let _clut_type_unused = data[at + 16]; // picture format field in python pack is different order
    // Python: <IIIHHBBBBHH  at `at`
    // total, clut_size, image_size, header_size, colors, picture_format, mipmaps, clut_type, image_type, width, height
    let picture_format = data[at + 16];
    let mipmaps = data[at + 17];
    let clut_type = data[at + 18];
    let image_type = data[at + 19];
    let width = u16_at(data, at + 20)? as u32;
    let height = u16_at(data, at + 22)? as u32;
    let _ = picture_format;

    if mipmaps != 1 || width == 0 || height == 0 || header_size < 48 {
        return Err(ArikaError::Other("unsupported TIM2 layout".into()));
    }
    if header_size + image_size + clut_size > total || at + total > data.len() {
        return Err(ArikaError::Other("truncated TIM2 extents".into()));
    }

    let image = &data[at + header_size..at + header_size + image_size];
    let palette = &data[at + header_size + image_size..at + header_size + image_size + clut_size];

    let mut rgba = Vec::with_capacity((width * height * 4) as usize);
    let expand_a = |a: u8| -> u8 { ((a as u16) * 2).min(255) as u8 };

    match image_type {
        3 => {
            // RGBA32
            if image.len() != (width * height * 4) as usize {
                return Err(ArikaError::Other("unexpected RGBA32 size".into()));
            }
            for chunk in image.chunks_exact(4) {
                rgba.extend_from_slice(&[chunk[0], chunk[1], chunk[2], expand_a(chunk[3])]);
            }
            Ok(Tim2Image {
                width,
                height,
                format: Tim2Format::Rgba32,
                rgba,
            })
        }
        4 | 5 => {
            if (clut_type & 0x3F) != 3 || palette.len() < colors * 4 {
                return Err(ArikaError::Other("CLUT must be RGBA32".into()));
            }
            let expected = if image_type == 4 {
                ((width * height + 1) / 2) as usize
            } else {
                (width * height) as usize
            };
            if image.len() != expected {
                return Err(ArikaError::Other("unexpected indexed image size".into()));
            }
            let linear_clut = false;
            for pixel in 0..(width * height) as usize {
                let mut color = if image_type == 4 {
                    (image[pixel / 2] >> ((pixel & 1) * 4)) & 15
                } else {
                    image[pixel]
                };
                // CSM1 swizzle for indexed8 when not linear
                if image_type == 5 && !linear_clut && (clut_type & 0x80) == 0 {
                    color = (color & !0x18) | ((color & 8) << 1) | ((color & 16) >> 1);
                }
                if color as usize >= colors {
                    return Err(ArikaError::Other("palette index OOB".into()));
                }
                let o = color as usize * 4;
                rgba.extend_from_slice(&[
                    palette[o],
                    palette[o + 1],
                    palette[o + 2],
                    expand_a(palette[o + 3]),
                ]);
            }
            Ok(Tim2Image {
                width,
                height,
                format: if image_type == 4 {
                    Tim2Format::Indexed4
                } else {
                    Tim2Format::Indexed8
                },
                rgba,
            })
        }
        _ => Err(ArikaError::Other(format!(
            "unsupported TIM2 image_type {image_type}"
        ))),
    }
}

pub fn encode_png(width: u32, height: u32, rgba: &[u8]) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_compression(png::Compression::Best);
        encoder.set_filter(png::FilterType::Paeth);
        let mut writer = encoder
            .write_header()
            .map_err(|e| ArikaError::Other(format!("png header: {e}")))?;
        writer
            .write_image_data(rgba)
            .map_err(|e| ArikaError::Other(format!("png data: {e}")))?;
    }
    Ok(out)
}

pub fn write_ppm(img: &Tim2Image, out: &std::path::Path) -> Result<()> {
    let mut buf = Vec::with_capacity(img.rgba.len());
    buf.extend_from_slice(format!("P6\n{} {}\n255\n", img.width, img.height).as_bytes());
    for chunk in img.rgba.chunks_exact(4) {
        buf.extend_from_slice(&[chunk[0], chunk[1], chunk[2]]);
    }
    std::fs::write(out, buf).map_err(|e| ArikaError::Other(format!("write ppm: {e}")))?;
    Ok(())
}

fn u32_at(data: &[u8], o: usize) -> Result<u32> {
    if o + 4 > data.len() {
        return Err(ArikaError::Other("u32 OOB".into()));
    }
    Ok(u32::from_le_bytes(data[o..o + 4].try_into().unwrap()))
}
fn u16_at(data: &[u8], o: usize) -> Result<u16> {
    if o + 2 > data.len() {
        return Err(ArikaError::Other("u16 OOB".into()));
    }
    Ok(u16::from_le_bytes(data[o..o + 2].try_into().unwrap()))
}
