//! Conservative INFO.DAT checks informed by ARKD_DVD.IRX lookup research.
//! Structural extent and duplicate-name checks are performed by Archive::open.
//! This does not claim to emulate IOP lookup or enforce an unverified entry cap.

use arika_core::dat::Archive;

/// Report grouped buckets and ordering warnings without rejecting valid-but-unusual names.
pub fn audit(archive: &Archive) -> bool {
    let names: Vec<&str> = archive.entries.iter().map(|e| e.name.as_str()).collect();
    let (errors, warnings) = inspect_names(&names);

    println!("Active entries: {}", archive.entries.len());
    println!("Physical INFO slots: {}", archive.record_capacity());
    println!("Unused INFO slots: {}", archive.spare_record_slots());
    println!("Trailing INFO bytes: {}", archive.record_tail_bytes());
    println!("Indexed GAME extent: {} bytes", archive.used_bytes);
    println!("Note: record capacity is not an ARKD_DVD.IRX runtime entry limit.");

    for message in &errors {
        eprintln!("ERROR: {message}");
    }
    for message in &warnings {
        eprintln!("WARNING: {message}");
    }
    println!("Archive audit: {} error(s), {} warning(s)", errors.len(), warnings.len());
    errors.is_empty()
}

/// The driver uses initial-letter buckets. Alphabetic buckets must be contiguous
/// and ordered; lexicographic ordering *within* a bucket is a recommendation,
/// not a demonstrated hard requirement of the driver.
fn inspect_names(names: &[&str]) -> (Vec<String>, Vec<String>) {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    let mut last_bucket: Option<u8> = None;
    let mut last_name: Option<String> = None;

    for (index, name) in names.iter().enumerate() {
        let first = name.as_bytes().first().copied().map(|b| b.to_ascii_lowercase());
        let bucket = first.filter(|b| b.is_ascii_lowercase());
        match bucket {
            Some(letter) => {
                if let Some(previous) = last_bucket {
                    if letter < previous {
                        errors.push(format!(
                            "entry {index} ({name}) returns to bucket '{}' after '{}'",
                            letter as char, previous as char
                        ));
                    }
                }
                last_bucket = Some(letter);
                let folded = name.to_ascii_lowercase();
                if let Some(previous) = &last_name {
                    if folded.as_bytes().first() == previous.as_bytes().first()
                        && folded < *previous
                    {
                        warnings.push(format!(
                            "entry {index} ({name}) is not lexically sorted after {previous}"
                        ));
                    }
                }
                last_name = Some(folded);
            }
            None => {
                warnings.push(format!(
                    "entry {index} ({name}) does not begin with ASCII a-z; driver lookup unverified"
                ));
                last_name = None;
            }
        }
    }
    (errors, warnings)
}

#[cfg(test)]
mod tests {
    use super::inspect_names;

    #[test]
    fn sorted_names_are_clean() {
        let (errors, warnings) = inspect_names(&["a/one.bin", "a/two.bin", "b/file.bin"]);
        assert!(errors.is_empty());
        assert!(warnings.is_empty());
    }

    #[test]
    fn returning_to_an_earlier_bucket_is_an_error() {
        let (errors, _) = inspect_names(&["a/one", "b/two", "a/three"]);
        assert_eq!(errors.len(), 1);
    }

    #[test]
    fn unsorted_names_inside_bucket_are_only_a_warning() {
        let (errors, warnings) = inspect_names(&["a/z", "a/a"]);
        assert!(errors.is_empty());
        assert_eq!(warnings.len(), 1);
    }

    #[test]
    fn unknown_initial_is_warning_not_rejection() {
        let (errors, warnings) = inspect_names(&["a/a", "_file", "b/b"]);
        assert!(errors.is_empty());
        assert_eq!(warnings.len(), 1);
    }
}
