//! Oodle decompression via the redistributable `oo2core_*_win64.dll`.
//!
//! Unreal Engine 5.5 statically links Oodle, so shipped games do not carry the
//! DLL. A local engine install does. The caller supplies the path; nothing is
//! bundled or redistributed here.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use libloading::{Library, Symbol};

use crate::Error;

/// `OodleLZ_Decompress` as exported by `oo2core_9_win64.dll`.
type OodleDecompressFn = unsafe extern "C" fn(
    src: *const u8,
    src_len: i64,
    dst: *mut u8,
    dst_len: i64,
    fuzz_safe: i32,
    check_crc: i32,
    verbosity: i32,
    dec_buf: *mut u8,
    dec_buf_size: i64,
    fp_callback: *mut u8,
    callback_user_data: *mut u8,
    scratch: *mut u8,
    scratch_size: i64,
    thread_phase: i32,
) -> i64;

struct Oodle {
    _lib: Library,
    decompress: OodleDecompressFn,
}

// The Oodle decode entry point is reentrant and we never mutate library state.
unsafe impl Send for Oodle {}
unsafe impl Sync for Oodle {}

static OODLE: OnceLock<Oodle> = OnceLock::new();

/// Locate `oo2core_*_win64.dll` given either a direct file path or a directory
/// to search.
fn resolve(root: &Path) -> Option<PathBuf> {
    if root.is_file() {
        return Some(root.to_path_buf());
    }
    if root.is_dir() {
        let mut hits: Vec<PathBuf> = std::fs::read_dir(root)
            .ok()?
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| {
                p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| {
                        let n = n.to_ascii_lowercase();
                        n.starts_with("oo2core") && n.ends_with("win64.dll")
                    })
                    .unwrap_or(false)
            })
            .collect();
        hits.sort();
        return hits.pop();
    }
    None
}

/// Load the Oodle library once, from the first candidate that resolves.
fn load(search_roots: &[PathBuf]) -> Result<&'static Oodle, Error> {
    if let Some(existing) = OODLE.get() {
        return Ok(existing);
    }
    let dll = search_roots
        .iter()
        .find_map(|r| resolve(r))
        .ok_or(Error::OodleMissing)?;

    // SAFETY: loading a caller-supplied native library and resolving one symbol
    // with a signature fixed by the Oodle ABI.
    let oodle = unsafe {
        let lib = Library::new(&dll).map_err(|e| Error::OodleLoad(e.to_string()))?;
        let sym: Symbol<OodleDecompressFn> = lib
            .get(b"OodleLZ_Decompress\0")
            .map_err(|e| Error::OodleLoad(e.to_string()))?;
        let decompress = *sym;
        Oodle {
            _lib: lib,
            decompress,
        }
    };

    Ok(OODLE.get_or_init(|| oodle))
}

/// Decompress `src` into a buffer of exactly `out_size` bytes.
pub fn decompress(src: &[u8], out_size: usize, search_roots: &[PathBuf]) -> Result<Vec<u8>, Error> {
    let oodle = load(search_roots)?;
    let mut out = vec![0u8; out_size];

    // SAFETY: both buffers are valid for their stated lengths and the optional
    // scratch/callback pointers are null, which the ABI permits.
    let written = unsafe {
        (oodle.decompress)(
            src.as_ptr(),
            src.len() as i64,
            out.as_mut_ptr(),
            out_size as i64,
            1, // fuzz safe
            0, // no crc check
            0, // silent
            std::ptr::null_mut(),
            0,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            0,
            3, // OodleLZ_Decode_Unthreaded
        )
    };

    if written != out_size as i64 {
        return Err(Error::OodleDecompress {
            got: written,
            want: out_size,
        });
    }
    Ok(out)
}
