//! Scene project files (.arika-scene.json).
//! Matches arika_scene_project.py c_scene_project project packaging.

use crate::error::{ArikaError, Result};
use base64::prelude::*;
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SceneProject {
    pub format: String,
    pub version: u32,
    pub source_stage: String,
    pub original_stage: String,
    pub edited_stage: String,
    pub gltf: serde_json::Value,
}

impl SceneProject {
    pub fn new(
        source_stage: impl Into<String>,
        original_stage_bytes: &[u8],
        edited_stage_bytes: &[u8],
        gltf: serde_json::Value,
    ) -> Self {
        Self {
            format: "ARIKA_SCENE_PROJECT".into(),
            version: 1,
            source_stage: source_stage.into(),
            original_stage: BASE64_STANDARD.encode(original_stage_bytes),
            edited_stage: BASE64_STANDARD.encode(edited_stage_bytes),
            gltf,
        }
    }

    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let project: SceneProject = serde_json::from_str(&content)
            .map_err(|e| ArikaError::Other(format!("invalid scene project JSON: {e}")))?;
        if project.format != "ARIKA_SCENE_PROJECT" || project.version != 1 {
            return Err(ArikaError::Other(
                "unsupported editor project format/version".into(),
            ));
        }
        Ok(project)
    }

    pub fn save(&self, path: impl AsRef<Path>) -> Result<()> {
        let json = serde_json::to_string_pretty(self)
            .map_err(|e| ArikaError::Other(format!("failed to serialize project: {e}")))?;
        std::fs::write(path, json)?;
        Ok(())
    }

    pub fn decode_original_stage(&self) -> Result<Vec<u8>> {
        BASE64_STANDARD
            .decode(&self.original_stage)
            .map_err(|e| ArikaError::Other(format!("base64 decode original_stage failed: {e}")))
    }

    pub fn decode_edited_stage(&self) -> Result<Vec<u8>> {
        BASE64_STANDARD
            .decode(&self.edited_stage)
            .map_err(|e| ArikaError::Other(format!("base64 decode edited_stage failed: {e}")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_project_roundtrip() {
        let orig = b"original stage content";
        let edited = b"edited stage content";
        let proj = SceneProject::new("stage.stg", orig, edited, serde_json::json!({"asset": {"version": "2.0"}}));
        assert_eq!(proj.format, "ARIKA_SCENE_PROJECT");
        assert_eq!(proj.version, 1);
        assert_eq!(proj.decode_original_stage().unwrap(), orig);
        assert_eq!(proj.decode_edited_stage().unwrap(), edited);
    }
}

