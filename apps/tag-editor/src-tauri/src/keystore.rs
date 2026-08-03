//! The device signing key.
//!
//! One Ed25519 key per machine, generated here on first use and never
//! exported — a second machine gets its own key, registered alongside this
//! one. The 32-byte seed is stored under Windows DPAPI (user scope) in the
//! MJOLNIR config directory: the blob only decrypts for this Windows user on
//! this machine, so a copied file is useless anywhere else. Design:
//! `docs/mod_signing_design.md`.

use std::path::PathBuf;

use mjolnir_sign::SigningIdentity;

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

#[cfg(windows)]
mod dpapi {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::LocalFree;
    use windows::Win32::Security::Cryptography::{
        CryptProtectData, CryptUnprotectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };

    fn blob_of(bytes: &[u8]) -> CRYPT_INTEGER_BLOB {
        CRYPT_INTEGER_BLOB {
            cbData: bytes.len() as u32,
            pbData: bytes.as_ptr() as *mut u8,
        }
    }

    /// Copy the output blob and free the LocalAlloc'd buffer the API hands us.
    unsafe fn take(out: CRYPT_INTEGER_BLOB) -> Vec<u8> {
        let bytes = std::slice::from_raw_parts(out.pbData, out.cbData as usize).to_vec();
        let _ = LocalFree(Some(windows::Win32::Foundation::HLOCAL(
            out.pbData as *mut _,
        )));
        bytes
    }

    pub fn protect(secret: &[u8]) -> Result<Vec<u8>, String> {
        let input = blob_of(secret);
        let mut out = CRYPT_INTEGER_BLOB::default();
        unsafe {
            CryptProtectData(
                &input,
                PCWSTR::null(),
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                &mut out,
            )
            .map_err(|e| format!("DPAPI protect failed: {e}"))?;
            Ok(take(out))
        }
    }

    pub fn unprotect(blob: &[u8]) -> Result<Vec<u8>, String> {
        let input = blob_of(blob);
        let mut out = CRYPT_INTEGER_BLOB::default();
        unsafe {
            CryptUnprotectData(
                &input,
                None,
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                &mut out,
            )
            .map_err(|e| format!("DPAPI unprotect failed: {e}"))?;
            Ok(take(out))
        }
    }
}

#[cfg(not(windows))]
mod dpapi {
    // The game, and therefore the editor, ships for Windows; this exists so
    // the crate still compiles elsewhere for CI-style checks.
    pub fn protect(_secret: &[u8]) -> Result<Vec<u8>, String> {
        Err("signing keys are DPAPI-protected and need Windows".into())
    }
    pub fn unprotect(_blob: &[u8]) -> Result<Vec<u8>, String> {
        Err("signing keys are DPAPI-protected and need Windows".into())
    }
}
