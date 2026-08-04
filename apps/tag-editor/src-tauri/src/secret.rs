//! Secrets at rest, under Windows DPAPI (user scope).
//!
//! Two things the editor holds are worth stealing: the device signing key
//! (`keystore`) and the hub API key (`install`). Both are protected the same
//! way — a blob that only decrypts for this Windows user on this machine, so
//! a copied file is useless anywhere else.
//!
//! This lives apart from either caller because the rule is the shared part:
//! a credential that can publish under someone's name does not sit in a JSON
//! file next to their paks path.

/// Protect a UTF-8 secret for storage.
pub fn protect_string(secret: &str) -> Result<Vec<u8>, String> {
    dpapi::protect(secret.as_bytes())
}

/// Recover a secret written by `protect_string`.
///
/// A blob that will not decrypt is treated as absent by callers rather than
/// as an error: it means the file was copied from another machine or another
/// user profile, and the answer in both cases is to link again.
pub fn unprotect_string(blob: &[u8]) -> Result<String, String> {
    let bytes = dpapi::unprotect(blob)?;
    String::from_utf8(bytes).map_err(|_| "stored secret is not valid UTF-8".to_string())
}

#[cfg(windows)]
pub(crate) mod dpapi {
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
pub(crate) mod dpapi {
    // The game, and therefore the editor, ships for Windows; this exists so
    // the crate still compiles elsewhere for CI-style checks. Refusing rather
    // than falling back to plaintext is deliberate — a build that silently
    // stored these in the clear would be worse than one that cannot store
    // them at all.
    pub fn protect(_secret: &[u8]) -> Result<Vec<u8>, String> {
        Err("secrets are DPAPI-protected and need Windows".into())
    }
    pub fn unprotect(_blob: &[u8]) -> Result<Vec<u8>, String> {
        Err("secrets are DPAPI-protected and need Windows".into())
    }
}
