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

            // Validate path safety (matches Python Archive.__init__)
            relative_name(&name)?;

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

    /// Extract all entries matching an optional, case-sensitive Python-style glob.
    /// As in arika_dat.py, validate every destination before writing any files.
    pub fn extract_all(
        &self,
        dest: impl AsRef<Path>,
        pattern: Option<&str>,
        overwrite: bool,
    ) -> Result<usize> {
        let game = self.game_path.as_ref().ok_or_else(|| {
            ArikaError::Other("GAME.DAT not opened".into())
        })?;
        let root = dest.as_ref();
        // Resolve the root before validating paths so existing symlinks below it
        // cannot redirect extraction outside the requested destination.
        std::fs::create_dir_all(root)?;
        let canonical_root = root.canonicalize()?;
        let mut targets = Vec::new();
        for entry in &self.entries {
            if let Some(pat) = pattern {
                if !simple_glob_match(pat, &entry.name) {
                    continue;
                }
            }
            let rel = relative_name(&entry.name)?;
            let out_path = canonical_root.join(&rel);
            ensure_contained_path(&canonical_root, &out_path)?;
            if out_path.exists() && !overwrite {
                return Err(ArikaError::Other(format!(
                    "output exists; use --overwrite: {}", out_path.display()
                )));
            }
            targets.push((entry, out_path));
        }

        let mut file = File::open(game)?;
        for (entry, out_path) in &targets {
            if let Some(parent) = out_path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            file.seek(SeekFrom::Start(entry.offset()))?;
            let mut output = File::create(out_path)?;
            let mut remaining = entry.size as u64;
            let mut buffer = [0u8; 1024 * 1024];
            while remaining > 0 {
                let wanted = remaining.min(buffer.len() as u64) as usize;
                file.read_exact(&mut buffer[..wanted])?;
                std::io::Write::write_all(&mut output, &buffer[..wanted])?;
                remaining -= wanted as u64;
            }
        }
        Ok(targets.len())
    }

    /// Rebuild INFO.DAT (and optionally GAME.DAT) from a directory of assets.
    /// For now this is a stub that re-encodes the current decoded table.
    pub fn write_info(&self, path: impl AsRef<Path>) -> Result<()> {
        let encoded = encode_info(&self.decoded)?;
        std::fs::write(path, encoded)?;
        Ok(())
    }

    /// Rebuild INFO.DAT and GAME.DAT using the same compact, entry-order layout
    /// as the Python implementation. Unchanged allocations retain their padding;
    /// the original GAME.DAT capacity and bytes after the indexed region are kept.
    pub fn rebuild_from_dir(
        &self,
        asset_dir: impl AsRef<std::path::Path>,
        out_info: impl AsRef<std::path::Path>,
        out_game: Option<impl AsRef<std::path::Path>>,
    ) -> Result<()> {
        use std::io::{Seek, SeekFrom, Write};

        let asset_dir = asset_dir.as_ref();
        let out_info = out_info.as_ref();
        let out_game = out_game.map(|p| p.as_ref().to_path_buf());
        let game_path = self.game_path.as_ref().ok_or_else(|| {
            ArikaError::Other("GAME.DAT is required to rebuild the archive".into())
        })?;
        let out_game = out_game.ok_or_else(|| {
            ArikaError::Other("an output GAME.DAT path is required to rebuild the archive".into())
        })?;

        let info_abs = std::fs::canonicalize(&self.info_path).unwrap_or_else(|_| self.info_path.clone());
        let game_abs = std::fs::canonicalize(game_path).unwrap_or_else(|_| game_path.clone());
        let out_info_abs = std::fs::canonicalize(out_info).unwrap_or_else(|_| out_info.to_path_buf());
        let out_game_abs = std::fs::canonicalize(&out_game).unwrap_or_else(|_| out_game.clone());
        if out_info_abs == info_abs || out_info_abs == game_abs
            || out_game_abs == info_abs || out_game_abs == game_abs
        {
            return Err(ArikaError::Other(
                "rebuild output must differ from the input INFO.DAT and GAME.DAT".into(),
            ));
        }

        struct PlannedEntry {
            index: usize,
            replacement: Option<PathBuf>,
            sector: u32,
            sectors: u32,
            size: u32,
            preserve_padding: bool,
            old_offset: u64,
            old_size: u32,
        }

        let mut plan = Vec::with_capacity(self.entries.len());
        let mut next_sector: u64 = 0;
        for entry in &self.entries {
            let replacement_path = asset_dir.join(relative_name(&entry.name)?);
            let replacement = if replacement_path.exists() {
                if !replacement_path.is_file() {
                    return Err(ArikaError::Other(format!(
                        "replacement is not a file: {}", replacement_path.display()
                    )));
                }
                Some(replacement_path)
            } else {
                None
            };
            let size = match &replacement {
                Some(path) => {
                    let len = std::fs::metadata(path)?.len();
                    u32::try_from(len).map_err(|_| ArikaError::Other(
                        "replacement exceeds the 32-bit asset-size field".into()
                    ))?
                }
                None => entry.size,
            };
            let sectors = (size as u64 + SECTOR - 1) / SECTOR;
            let sector = u32::try_from(next_sector).map_err(|_| ArikaError::Other(
                "rebuilt sector index exceeds the 32-bit field".into()
            ))?;
            let sectors_u32 = u32::try_from(sectors).map_err(|_| ArikaError::Other(
                "rebuilt sector count exceeds the 32-bit field".into()
            ))?;
            plan.push(PlannedEntry {
                index: entry.index,
                replacement,
                sector,
                sectors: sectors_u32,
                size,
                preserve_padding: size == entry.size && sectors_u32 == entry.sectors,
                old_offset: entry.offset(),
                old_size: entry.size,
            });
            next_sector = next_sector.checked_add(sectors).ok_or_else(|| ArikaError::Other(
                "rebuilt archive size overflow".into()
            ))?;
        }

        let game_size = std::fs::metadata(game_path)?.len();
        let indexed_size = next_sector.checked_mul(SECTOR).ok_or_else(|| ArikaError::Other(
            "rebuilt archive size overflow".into()
        ))?;
        if indexed_size > game_size {
            return Err(ArikaError::Other(
                "rebuilt assets exceed the original GAME.DAT capacity".into(),
            ));
        }

        let mut decoded = self.decoded.clone();
        let parent = out_game.parent().filter(|p| !p.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        std::fs::create_dir_all(parent)?;
        let mut game_temp = tempfile::NamedTempFile::new_in(parent)?;
        let mut source = File::open(game_path)?;
        let mut output_pos = 0u64;
        let mut buffer = [0u8; 1024 * 1024];

        for item in &plan {
            let at = HEADER + item.index * RECORD;
            decoded[at + 36..at + 40].copy_from_slice(&item.sector.to_le_bytes());
            decoded[at + 40..at + 44].copy_from_slice(&item.sectors.to_le_bytes());
            decoded[at + 44..at + 48].copy_from_slice(&item.size.to_le_bytes());

            if let Some(path) = &item.replacement {
                let mut replacement = File::open(path)?;
                let mut remaining = item.size as u64;
                while remaining > 0 {
                    let wanted = remaining.min(buffer.len() as u64) as usize;
                    let read = replacement.read(&mut buffer[..wanted])?;
                    if read == 0 {
                        return Err(ArikaError::Other(format!(
                            "replacement changed while rebuilding: {}", path.display()
                        )));
                    }
                    game_temp.write_all(&buffer[..read])?;
                    remaining -= read as u64;
                }
            } else {
                source.seek(SeekFrom::Start(item.old_offset))?;
                let mut remaining = item.size as u64;
                while remaining > 0 {
                    let wanted = remaining.min(buffer.len() as u64) as usize;
                    source.read_exact(&mut buffer[..wanted])?;
                    game_temp.write_all(&buffer[..wanted])?;
                    remaining -= wanted as u64;
                }
            }
            output_pos += item.size as u64;
            let allocation = item.sectors as u64 * SECTOR;
            let padding = allocation - item.size as u64;
            if padding > 0 {
                if item.preserve_padding {
                    source.seek(SeekFrom::Start(item.old_offset + item.old_size as u64))?;
                    let mut remaining = padding;
                    while remaining > 0 {
                        let wanted = remaining.min(buffer.len() as u64) as usize;
                        source.read_exact(&mut buffer[..wanted])?;
                        game_temp.write_all(&buffer[..wanted])?;
                        remaining -= wanted as u64;
                    }
                } else {
                    buffer.fill(0);
                    let mut remaining = padding;
                    while remaining > 0 {
                        let wanted = remaining.min(buffer.len() as u64) as usize;
                        game_temp.write_all(&buffer[..wanted])?;
                        remaining -= wanted as u64;
                    }
                }
            }
            output_pos += padding;
        }

        // Preserve the original trailing reserve and any other bytes after the
        // newly compacted indexed region, exactly as arika_dat.py does.
        source.seek(SeekFrom::Start(output_pos))?;
        let mut remaining = game_size - output_pos;
        while remaining > 0 {
            let wanted = remaining.min(buffer.len() as u64) as usize;
            source.read_exact(&mut buffer[..wanted])?;
            game_temp.write_all(&buffer[..wanted])?;
            remaining -= wanted as u64;
        }
        game_temp.flush()?;
        game_temp.as_file_mut().set_len(game_size)?;

        let info_parent = out_info.parent().filter(|p| !p.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        std::fs::create_dir_all(info_parent)?;
        let mut info_temp = tempfile::NamedTempFile::new_in(info_parent)?;
        info_temp.write_all(&encode_info(&decoded)?)?;
        info_temp.flush()?;
        game_temp.persist(&out_game).map_err(|e| ArikaError::Io(e.error))?;
        info_temp.persist(out_info).map_err(|e| ArikaError::Io(e.error))?;
        Ok(())
    }

}

fn relative_name(name: &str) -> Result<PathBuf> {
    let cleaned = name.replace('\\', "/");
    if cleaned.is_empty()
        || cleaned.starts_with('/')
        || cleaned.split('/').any(|part| part == "..")
        || cleaned.contains(':')
        || cleaned.chars().any(|c| c < ' ')
    {
        return Err(ArikaError::UnsafePath(name.to_string()));
    }
    Ok(PathBuf::from(cleaned))
}

/// Reject output paths that escape the canonical extraction root through an
/// already-existing symlink in any parent component.
fn ensure_contained_path(root: &Path, path: &Path) -> Result<()> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| ArikaError::UnsafePath(path.display().to_string()))?;
    let mut current = root.to_path_buf();
    for component in relative.components() {
        current.push(component.as_os_str());
        if !current.exists() {
            continue;
        }
        let resolved = current.canonicalize()?;
        if !resolved.starts_with(root) {
            return Err(ArikaError::UnsafePath(path.display().to_string()));
        }
        current = resolved;
    }
    Ok(())
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
        if pi < pat.len() && (pat[pi] == '?' || pat[pi] == nam[ni]) {
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
    use tempfile::NamedTempFile;

    #[test]
    fn glob_matching_matches_python_fnmatchcase() {
        assert!(simple_glob_match("*.pix", "CHARA.pix"));
        assert!(!simple_glob_match("*.PIX", "CHARA.pix"));
        assert!(simple_glob_match("char?.bin", "char1.bin"));
        assert!(!simple_glob_match("char?.bin", "char12.bin"));
    }

    #[test]
    fn relative_name_rejects_traversal() {
        assert!(relative_name("../evil").is_err());
        assert!(relative_name("ok/file.pix").is_ok());
        assert!(relative_name("folder/name..bak").is_ok());
        assert!(relative_name("folder/../escape").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn extraction_rejects_symlink_escape() {
        use std::os::unix::fs::symlink;
        let temp = tempfile::tempdir().expect("tempdir");
        let root = temp.path().join("extract");
        let outside = temp.path().join("outside");
        std::fs::create_dir_all(&root).expect("root");
        std::fs::create_dir_all(&outside).expect("outside");
        symlink(&outside, root.join("redirect")).expect("symlink");
        let canonical_root = root.canonicalize().expect("canonical root");
        let escaped = root.join("redirect").join("payload.bin");
        assert!(ensure_contained_path(&canonical_root, &escaped).is_err());
        assert!(!outside.join("payload.bin").exists());
    }

    fn make_info_with_entry(name: &str, sector: u32, sectors: u32, size: u32) -> Vec<u8> {
        // Build decoded INFO buffer: header(48) + 1 record(48), then encode.
        let mut decoded = vec![0u8; HEADER + RECORD];
        decoded[..16].copy_from_slice(crate::info::MAGIC);
        decoded[0x2C..0x30].copy_from_slice(&1u32.to_le_bytes()); // count
        let name_bytes = name.as_bytes();
        decoded[HEADER..HEADER + name_bytes.len()].copy_from_slice(name_bytes);
        decoded[HEADER + 32..HEADER + 36].copy_from_slice(&0u32.to_le_bytes()); // unknown
        decoded[HEADER + 36..HEADER + 40].copy_from_slice(&sector.to_le_bytes());
        decoded[HEADER + 40..HEADER + 44].copy_from_slice(&sectors.to_le_bytes());
        decoded[HEADER + 44..HEADER + 48].copy_from_slice(&size.to_le_bytes());
        crate::info::encode_info(&decoded).expect("encode")
    }

    #[test]
    fn test_archive_entry_parsing() {
        let encoded = make_info_with_entry("dir/test.bin", 0, 1, 3);
        let mut game = Vec::new();
        game.resize(2048, 0x7e);
        game[0..3].copy_from_slice(b"abc");

        let info_file = NamedTempFile::new().expect("info tmp");
        let game_file = NamedTempFile::new().expect("game tmp");
        std::fs::write(info_file.path(), &encoded).expect("write info");
        std::fs::write(game_file.path(), &game).expect("write game");

        let archive = Archive::open(info_file.path(), Some(game_file.path())).expect("open");
        assert_eq!(archive.entries.len(), 1);
        assert_eq!(archive.entries[0].name, "dir/test.bin");
        assert_eq!(archive.entries[0].size, 3);
        assert_eq!(archive.entries[0].sector, 0);
        assert_eq!(archive.used_bytes, 2048);
    }

    #[test]
    fn archive_extract_and_rebuild_preserves_bytes_and_capacity() {
        use std::fs;

        let root = tempfile::tempdir().expect("temp dir");
        let info_path = root.path().join("INFO.DAT");
        let game_path = root.path().join("GAME.DAT");
        let mut game = vec![0x7e; (SECTOR * 2) as usize];
        game[..3].copy_from_slice(b"abc");
        let encoded = make_info_with_entry("dir/test.bin", 0, 1, 3);
        fs::write(&info_path, &encoded).expect("write info");
        fs::write(&game_path, &game).expect("write game");

        let archive = Archive::open(&info_path, Some(&game_path)).expect("open archive");
        let extracted = root.path().join("assets");
        assert_eq!(archive.extract_all(&extracted, None, false).expect("extract"), 1);
        assert_eq!(fs::read(extracted.join("dir/test.bin")).expect("read asset"), b"abc");

        let rebuilt_dir = root.path().join("rebuilt");
        let rebuilt_info = rebuilt_dir.join("INFO.DAT");
        let rebuilt_game = rebuilt_dir.join("GAME.DAT");
        archive.rebuild_from_dir(&extracted, &rebuilt_info, Some(&rebuilt_game)).expect("rebuild");
        assert_eq!(fs::read(&rebuilt_info).expect("read rebuilt info"), encoded);
        assert_eq!(fs::read(&rebuilt_game).expect("read rebuilt game"), game);
        assert_eq!(fs::metadata(&rebuilt_game).expect("rebuilt metadata").len(), (SECTOR * 2) as u64);

        fs::write(extracted.join("dir/test.bin"), b"longer test").expect("write replacement");
        let changed_dir = root.path().join("changed");
        let changed_info = changed_dir.join("INFO.DAT");
        let changed_game = changed_dir.join("GAME.DAT");
        archive.rebuild_from_dir(&extracted, &changed_info, Some(&changed_game)).expect("rebuild changed");
        let changed = Archive::open(&changed_info, Some(&changed_game)).expect("open changed archive");
        assert_eq!(changed.entries[0].size, 11);
        let changed_bytes = fs::read(&changed_game).expect("read changed game");
        assert_eq!(&changed_bytes[..11], b"longer test");
        assert_eq!(&changed_bytes[SECTOR as usize..], &game[SECTOR as usize..]);

        // Rebuilding must never mutate the source pair.
        assert_eq!(fs::read(&info_path).expect("read source info"), encoded);
        assert_eq!(fs::read(&game_path).expect("read source game"), game);
    }

    #[test]
    fn rebuild_rejects_assets_that_exceed_archive_capacity() {
        use std::fs;

        let root = tempfile::tempdir().expect("temp dir");
        let info_path = root.path().join("INFO.DAT");
        let game_path = root.path().join("GAME.DAT");
        let encoded = make_info_with_entry("big.bin", 0, 1, 3);
        fs::write(&info_path, encoded).expect("write info");
        fs::write(&game_path, vec![0u8; SECTOR as usize]).expect("write game");
        let archive = Archive::open(&info_path, Some(&game_path)).expect("open archive");
        let assets = root.path().join("assets");
        fs::create_dir_all(&assets).expect("create assets");
        fs::write(assets.join("big.bin"), vec![0u8; (SECTOR * 2) as usize]).expect("write oversized asset");
        let result = archive.rebuild_from_dir(
            &assets,
            root.path().join("out/INFO.DAT"),
            Some(root.path().join("out/GAME.DAT")),
        );
        assert!(result.is_err());
        assert!(!root.path().join("out/INFO.DAT").exists());
        assert!(!root.path().join("out/GAME.DAT").exists());
    }

    #[test]
    fn test_archive_rejects_unsafe_path() {
        let encoded = make_info_with_entry("../escape", 0, 1, 3);
        let mut game = Vec::new();
        game.resize(2048, 0);

        let info_file = NamedTempFile::new().expect("info tmp");
        let game_file = NamedTempFile::new().expect("game tmp");
        std::fs::write(info_file.path(), &encoded).expect("write info");
        std::fs::write(game_file.path(), &game).expect("write game");

        let result = Archive::open(info_file.path(), Some(game_file.path()));
        assert!(result.is_err());
    }

    #[test]
    fn test_archive_rejects_asset_too_large() {
        // size=4096 needs 2 sectors but only 1 allocated
        let encoded = make_info_with_entry("big.bin", 0, 1, 4096);
        let mut game = Vec::new();
        game.resize(2048, 0);

        let info_file = NamedTempFile::new().expect("info tmp");
        let game_file = NamedTempFile::new().expect("game tmp");
        std::fs::write(info_file.path(), &encoded).expect("write info");
        std::fs::write(game_file.path(), &game).expect("write game");

        let result = Archive::open(info_file.path(), Some(game_file.path()));
        assert!(result.is_err());
    }
}
