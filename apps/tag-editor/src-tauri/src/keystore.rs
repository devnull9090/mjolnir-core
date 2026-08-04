//! The device signing key.
//!
//! One Ed25519 key per machine, generated here on first use and never
//! exported — a second machine gets its own key, registered alongside this
//! one. The 32-byte seed is stored under Windows DPAPI (user scope) in the
//! MJOLNIR config directory: the blob only decrypts for this Windows user on
//! this machine, so a copied file is useless anywhere else. Design:
//! `docs/mod_signing_design.md`.
//!
//! The DPAPI wrapper itself lives in `secret`, shared with the stored hub
//! API key.

use std::path::PathBuf;

use mjolnir_sign::SigningIdentity;

use crate::secret::dpapi;

const KEY_FILE: &str = "signing-key.dpapi";

fn key_path() -> Option<PathBuf> {
    Some(dirs::config_dir()?.join("MJOLNIR").join(KEY_FILE))
}

/// The identity already on this machine, if one was ever created.
pub fn existing() -> Option<SigningIdentity> {
    let blob = std::fs::read(key_path()?).ok()?;
    let seed: [u8; 32] = dpapi::unprotect(&blob).ok()?.try_into().ok()?;
    Some(SigningIdentity::from_seed(&seed))
}

/// The device identity, created on first use.
pub fn load_or_create() -> Result<SigningIdentity, String> {
    if let Some(identity) = existing() {
        return Ok(identity);
    }
    let mut seed = [0u8; 32];
    getrandom::fill(&mut seed).map_err(|e| format!("no randomness source: {e}"))?;
    let path = key_path().ok_or("no config directory")?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("{}: {e}", parent.display()))?;
    }
    let blob = dpapi::protect(&seed)?;
    std::fs::write(&path, blob).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(SigningIdentity::from_seed(&seed))
}

