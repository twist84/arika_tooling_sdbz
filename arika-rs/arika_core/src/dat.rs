//! INFO.DAT / GAME.DAT archive handling.

use std::collections::HashSet;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use byteorder::{LittleEndian, ReadBytesExt};
use encoding_rs::SHIFT_JIS; // CP932 is a Microsoft extension of Shift_JIS; close enough for filenames

use crate::error::{ArikaError, Result};
use crate::info::{decode_info, encode_info, HEADER, RECORD, SECTOR};

/// One asset record from INFO.DAT.
#[derive(Debug, Clone)]
pub struct Entry {
    pub index: usize,
    pub name: String,
    pub unknown: u32,
    pub sector: u32,
    pub sectors: u32,
    pub size: u32,
}

impl Entry {
    pub fn offset(&self) -> u64 {
        self.sector as u64 * SECTOR
    }

    pub fn allocated_bytes(&self) -> u64 {
        self.sectors as u64 * SECTOR
    }
}

/// Opened INFO (+ optional GAME) archive.
#[derive(Debug)]
pub struct Archive {
    pub info_path: PathBuf,
    pub game_path: Option<PathBuf>,
    pub encoded: Vec<u8>,
    pub decoded: Vec<u8>,
    pub entries: Vec<Entry>,
    pub used_bytes: u64,
}

impl Archive {
    pub fn open(info: impl AsRef<Path>, game: Option<impl AsRef<Path>>) -> Result<Self> {
        let info_path = info.as_ref().to_path_buf();
        let game_path = game.map(|g| g.as_ref().to_path_buf());

        let encoded = std::fs::read(&info_path)?;
        let decoded = decode_info(&encoded)?;

        let count = {
            let mut cursor = std::io::Cursor::new(&decoded[0x2C..0x30]);
            cursor.read_u32::<LittleEndian>()?
        };

        if count as usize > (decoded.len() - HEADER) / RECORD {
            return Err(ArikaError::InvalidEntryCount);
        }

        let mut entries = Vec::with_capacity(count as usize);
        let mut names = HashSet::new();

        for index in 0..count as usize {
            let at = HEADER + index * RECORD;
            let raw_name = &decoded[at..at + 32];
            let nul = raw_name.iter().position(|&b| b == 0).unwrap_or(32);
            let (name, _, _) = SHIFT_JIS.decode(&raw_name[..nul]);
            let name = name.into_owned();

            let folded = name.to_lowercase();
            if !names.insert(folded) {
                return Err(ArikaError::DuplicateName(name));
            }

            let mut cursor = std::io::Cursor::new(&decoded[at + 32..at + 48]);
            let unknown = cursor.read_u32::<LittleEndian>()?;
            let sector = cursor.read_u32::<LittleEndian>()?;
            let sectors = cursor.read_u32::<LittleEndian>()?;
            let size = cursor.read_u32::<LittleEndian>()?;

            let needed = (size as u64 + SECTOR - 1) / SECTOR;
            if (sectors as u64) < needed {
                return Err(ArikaError::AssetTooLarge(name));
            }

            entries.push(Entry {
                index,
                name,
                unknown,
                sector,
                sectors,
                size,
            });
        }

        let mut last_end = 0u64;
        let mut sorted: Vec<_> = entries.iter().collect();
        sorted.sort_by_key(|e| e.offset());
        for e in sorted {
            if e.offset() < last_end {
                return Err(ArikaError::OverlappingExtents);
            }
            last_end = e.offset() + e.allocated_bytes();
        }

        if let Some(ref gp) = game_path {
            let game_size = std::fs::metadata(gp)?.len();
            if last_end > game_size {
                return Err(ArikaError::GameTooSmall);
            }
        }

        Ok(Self {
            info_path,
            game_path,
            encoded,
            decoded,
            entries,
            used_bytes: last_end,
        })
    }

    /// List of (index, name, size, sector).
    pub fn manifest(&self) -> Vec<(usize, &str, u32, u32)> {
        self.entries
            .iter()
            .map(|e| (e.index, e.name.as_str(), e.size, e.sector))
            .collect()
    }

    /// Extract one entry by name (case-insensitive) into `dest` directory.
    pub fn extract_one(&self, name: &str, dest: impl AsRef<Path>) -> Result<PathBuf> {
        let entry = self
            .entries
            .iter()
            .find(|e| e.name.eq_ignore_ascii_case(name))
            .ok_or_else(|| ArikaError::Other(format!("asset not found: {name}")))?;

        let game = self
            .game_path
            .as_ref()
            .ok_or_else(|| ArikaError::Other("GAME.DAT not opened".into()))?;

        let mut file = File::open(game)?;
        file.seek(SeekFrom::Start(entry.offset()))?;
        let mut buf = vec![0u8; entry.size as usize];
        file.read_exact(&mut buf)?;

        let rel = relative_name(&entry.name)?;
        let out_path = dest.as_ref().join(&rel);
        if let Some(parent) = out_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&out_path, &buf)?;
        Ok(out_path)
    }

    /// Extract all entries matching an optional glob pattern.
    pub fn extract_all(
        &self,
        dest: impl AsRef<Path>,
        pattern: Option<&str>,
        overwrite: bool,
    ) -> Result<usize> {
        let game = self
            .game_path
            .as_ref()
            .ok_or_else(|| ArikaError::Other("GAME.DAT not opened".into()))?;

        let mut file = File::open(game)?;
        let mut count = 0usize;

        for entry in &self.entries {
            if let Some(pat) = pattern {
                // simple glob: * and ?
                if !simple_glob_match(pat, &entry.name) {
                    continue;
                }
            }

            let rel = relative_name(&entry.name)?;
            let out_path = dest.as_ref().join(&rel);
            if out_path.exists() && !overwrite {
                continue;
            }
            if let Some(parent) = out_path.parent() {
                std::fs::create_dir_all(parent)?;
            }

            file.seek(SeekFrom::Start(entry.offset()))?;
            let mut buf = vec![0u8; entry.size as usize];
            file.read_exact(&mut buf)?;
            std::fs::write(&out_path, &buf)?;
            count += 1;
        }
        Ok(count)
    }

    /// Rebuild INFO.DAT (and optionally GAME.DAT) from a directory of assets.
    /// For now this is a stub that re-encodes the current decoded table.
    pub fn write_info(&self, path: impl AsRef<Path>) -> Result<()> {
        let encoded = encode_info(&self.decoded)?;
        std::fs::write(path, encoded)?;
        Ok(())
    }

    /// Rebuild INFO.DAT (and optionally a new GAME.DAT) from a directory of assets
    /// matching the current entry names. Files that exist replace payload bytes;
    /// missing files keep the original size with zero fill (or skip).
    /// Sector layout is preserved for same-or-smaller sizes; larger files expand
    /// contiguous allocation from the end of the used region.
    pub fn rebuild_from_dir(
        &self,
        asset_dir: impl AsRef<std::path::Path>,
        out_info: impl AsRef<std::path::Path>,
        out_game: Option<impl AsRef<std::path::Path>>,
    ) -> Result<()> {
        let asset_dir = asset_dir.as_ref();
        let mut new_decoded = self.decoded.clone();
        let mut game_buf: Option<Vec<u8>> = None;
        if let Some(ref gp) = self.game_path {
            game_buf = Some(std::fs::read(gp)?);
        } else if out_game.is_some() {
            // allocate enough for existing used region
            game_buf = Some(vec![0u8; self.used_bytes as usize]);
        }

        let mut next_free = self.used_bytes;
        for entry in &self.entries {
            let rel = relative_name(&entry.name)?;
            let path = asset_dir.join(&rel);
            if !path.exists() {
                continue;
            }
            let data = std::fs::read(&path)?;
            let new_size = data.len() as u32;
            let at = HEADER + entry.index * RECORD;
            // update size field
            new_decoded[at + 0x2C..at + 0x30].copy_from_slice(&new_size.to_le_bytes());

            if let Some(ref mut gb) = game_buf {
                let need_sectors = (new_size as u64 + SECTOR - 1) / SECTOR;
                let old_sectors = entry.sectors as u64;
                let (sector, sectors) = if need_sectors <= old_sectors {
                    (entry.sector, entry.sectors)
                } else {
                    // allocate at end
                    let sec = (next_free / SECTOR) as u32;
                    let sectors = need_sectors as u32;
                    next_free = (sec as u64 + need_sectors) * SECTOR;
                    // update sector fields
                    new_decoded[at + 0x24..at + 0x28].copy_from_slice(&sec.to_le_bytes());
                    new_decoded[at + 0x28..at + 0x2C].copy_from_slice(&sectors.to_le_bytes());
                    (sec, sectors)
                };
                let offset = sector as u64 * SECTOR;
                let end = offset + sectors as u64 * SECTOR;
                if end as usize > gb.len() {
                    gb.resize(end as usize, 0);
                }
                // clear allocation then write
                for b in &mut gb[offset as usize..end as usize] {
                    *b = 0;
                }
                gb[offset as usize..offset as usize + data.len()].copy_from_slice(&data);
            }
        }

        let encoded = crate::info::encode_info(&new_decoded)?;
        std::fs::write(out_info, encoded)?;
        if let (Some(og), Some(gb)) = (out_game, game_buf) {
            std::fs::write(og.as_ref(), gb)?;
        }
        Ok(())
    }

}

fn relative_name(name: &str) -> Result<PathBuf> {
    let cleaned = name.replace('\\', "/");
    if cleaned.is_empty()
        || cleaned.starts_with('/')
        || cleaned.contains("..")
        || cleaned.contains(':')
        || cleaned.chars().any(|c| c < ' ')
    {
        return Err(ArikaError::UnsafePath(name.to_string()));
    }
    Ok(PathBuf::from(cleaned))
}

fn simple_glob_match(pattern: &str, name: &str) -> bool {
    // very basic * and ? support
    let pat: Vec<char> = pattern.chars().collect();
    let nam: Vec<char> = name.chars().collect();
    match_glob(&pat, &nam)
}

fn match_glob(pat: &[char], nam: &[char]) -> bool {
    let mut pi = 0;
    let mut ni = 0;
    let mut star_p = None;
    let mut star_n = None;

    while ni < nam.len() {
        if pi < pat.len() && (pat[pi] == '?' || pat[pi].eq_ignore_ascii_case(&nam[ni])) {
            pi += 1;
            ni += 1;
        } else if pi < pat.len() && pat[pi] == '*' {
            star_p = Some(pi);
            star_n = Some(ni);
            pi += 1;
        } else if let (Some(sp), Some(sn)) = (star_p, star_n) {
            pi = sp + 1;
            ni = sn + 1;
            star_n = Some(ni);
        } else {
            return false;
        }
    }
    while pi < pat.len() && pat[pi] == '*' {
        pi += 1;
    }
    pi == pat.len()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relative_name_rejects_traversal() {
        assert!(relative_name("../evil").is_err());
        assert!(relative_name("ok/file.pix").is_ok());
    }
}
