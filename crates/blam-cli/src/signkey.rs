//! Signing keys for `.mjolnir` archives the CLI writes (`map pack --sign`).
//!
//! The hub accepts an upload only when it carries an author signature from a
//! key registered to the uploader's account (docs/mod_signing_design.md).
//! The tag editor creates that key on first use and keeps its 32-byte seed
//! under Windows DPAPI (user scope) at `%APPDATA%\MJOLNIR\signing-key.dpapi`;
//! the CLI, run as the same Windows user, signs with the same identity, so
//! no second key needs registering. `--sign-seed` takes a seed file instead,
//! for other machines and platforms.
//!
//! DPAPI is called directly through `crypt32` rather than the `windows`
//! crate, which this workspace does not otherwise pull in.

use std::path::Path;

use anyhow::{bail, Context, Result};
use mjolnir_sign::SigningIdentity;

/// The tag editor's device key, as it stores it.
pub fn device_identity() -> Result<SigningIdentity> {
    let dir = std::env::var_os("APPDATA").context("APPDATA is not set")?;
    let path = Path::new(&dir).join("MJOLNIR").join("signing-key.dpapi");
    let blob = std::fs::read(&path).with_context(|| {
        format!(
            "{}: no device key; open the tag editor once (it creates and registers one), \
             or pass --sign-seed",
            path.display()
        )
    })?;
    let seed = dpapi::unprotect(&blob)?;
    let seed: [u8; 32] = seed
        .try_into()
        .map_err(|_| anyhow::anyhow!("{}: not a 32-byte seed", path.display()))?;
    Ok(SigningIdentity::from_seed(&seed))
}

/// A seed file: 32 raw bytes, or 64 hex characters.
pub fn seed_file_identity(path: &Path) -> Result<SigningIdentity> {
    let bytes = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    let seed: Vec<u8> = if bytes.len() == 32 {
        bytes
    } else {
        let text = String::from_utf8_lossy(&bytes);
        let hex = text.trim();
        if hex.len() != 64 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
            bail!("{}: a seed is 32 raw bytes or 64 hex characters", path.display());
        }
        (0..32)
            .map(|i| u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16).unwrap())
            .collect()
    };
    Ok(SigningIdentity::from_seed(&seed.try_into().unwrap()))
}

#[cfg(windows)]
mod dpapi {
    use anyhow::{bail, Result};

    #[repr(C)]
    struct Blob {
        len: u32,
        data: *mut u8,
    }

    #[link(name = "crypt32")]
    extern "system" {
        fn CryptUnprotectData(
            data_in: *const Blob,
            description: *mut *mut u16,
            entropy: *const Blob,
            reserved: *mut core::ffi::c_void,
            prompt: *const core::ffi::c_void,
            flags: u32,
            data_out: *mut Blob,
        ) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(mem: *mut core::ffi::c_void) -> *mut core::ffi::c_void;
    }

    const CRYPTPROTECT_UI_FORBIDDEN: u32 = 0x1;

    pub fn unprotect(blob: &[u8]) -> Result<Vec<u8>> {
        let input = Blob {
            len: blob.len() as u32,
            data: blob.as_ptr() as *mut u8,
        };
        let mut out = Blob {
            len: 0,
            data: std::ptr::null_mut(),
        };
        // SAFETY: `input` points at `blob`, alive for the call; `out` is
        // filled by the API with a LocalAlloc'd buffer, copied and freed here.
        unsafe {
            if CryptUnprotectData(
                &input,
                std::ptr::null_mut(),
                std::ptr::null(),
                std::ptr::null_mut(),
                std::ptr::null(),
                CRYPTPROTECT_UI_FORBIDDEN,
                &mut out,
            ) == 0
            {
                bail!(
                    "DPAPI could not decrypt the device key (another Windows user's, or another machine's)"
                );
            }
            let bytes = std::slice::from_raw_parts(out.data, out.len as usize).to_vec();
            LocalFree(out.data as *mut core::ffi::c_void);
            Ok(bytes)
        }
    }
}

#[cfg(not(windows))]
mod dpapi {
    pub fn unprotect(_blob: &[u8]) -> anyhow::Result<Vec<u8>> {
        anyhow::bail!("the device key is DPAPI-protected and needs Windows; pass --sign-seed")
    }
}
