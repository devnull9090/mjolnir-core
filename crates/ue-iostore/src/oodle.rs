//! Oodle decompression, by either of two paths that produce the same bytes.
//!
//! `oozextract` is a pure-Rust decoder compiled in, so reading a container
//! needs no setup at all. The redistributable `oo2core_*_win64.dll` is the
//! reference implementation and roughly four times faster, so it is used
//! instead whenever the caller can point at one — it is an override, not a
//! requirement.
//!
//! Unreal Engine 5.5 statically links Oodle, so shipped games do not carry the
//! DLL. A local engine install does. The caller supplies the path; nothing is
//! bundled or redistributed here.

use std::cell::RefCell;
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
    /// Where it was loaded from, for `backend` to report.
    path: PathBuf,
}

// The Oodle decode entry point is reentrant and we never mutate library state.
unsafe impl Send for Oodle {}
unsafe impl Sync for Oodle {}

/// The DLL, if one was found. A miss is cached as `None` on purpose: without
/// that, every block would re-scan the search roots looking for a DLL that is
/// not there.
///
/// Resolved once per process from the roots of the first call, so switching
/// installations mid-session keeps the first decision until a restart.
static OODLE: OnceLock<Option<Oodle>> = OnceLock::new();

thread_local! {
    /// An `Extractor` owns ~768 KiB of scratch, which is far too much to
    /// allocate per 64 KiB block, so each thread keeps one and reuses it.
    static EXTRACTOR: RefCell<oozextract::Extractor> =
        RefCell::new(oozextract::Extractor::new());
}

/// Which decoder a call would use.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Backend {
    /// The reference implementation, at the given path.
    Dll(PathBuf),
    /// The compiled-in pure-Rust decoder.
    Pure,
}

/// The `9` in `oo2core_9_win64.dll`, or `None` if this is not that file.
///
/// A decoder reads streams written by its own version and older, never newer,
/// so where several are present the highest one is the safest choice.
fn version_of(name: &str) -> Option<u32> {
    let name = name.to_ascii_lowercase();
    name.strip_prefix("oo2core_")?
        .strip_suffix("_win64.dll")?
        .parse()
        .ok()
}

/// Locate `oo2core_*_win64.dll` given either a direct file path or a directory
/// to search, preferring the newest version present.
fn resolve(root: &Path) -> Option<PathBuf> {
    if root.is_file() {
        return Some(root.to_path_buf());
    }
    if root.is_dir() {
        return std::fs::read_dir(root)
            .ok()?
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter_map(|p| {
                let version = p
                    .file_name()
                    .and_then(|n| n.to_str())
                    .and_then(version_of)?;
                Some((version, p))
            })
            .max_by_key(|(version, _)| *version)
            .map(|(_, p)| p);
    }
    None
}

/// Load the Oodle library once, from the first candidate that resolves.
///
/// A DLL that is absent, or present but unloadable, both come back `None`: the
/// pure decoder produces the same bytes either way, so a bad path costs speed
/// rather than failing the read. `backend` reports which one is in play.
fn load(search_roots: &[PathBuf]) -> Option<&'static Oodle> {
    OODLE
        .get_or_init(|| {
            let dll = search_roots.iter().find_map(|r| resolve(r))?;

            // SAFETY: loading a caller-supplied native library and resolving
            // one symbol with a signature fixed by the Oodle ABI.
            unsafe {
                let lib = Library::new(&dll).ok()?;
                let sym: Symbol<OodleDecompressFn> = lib.get(b"OodleLZ_Decompress\0").ok()?;
                let decompress = *sym;
                Some(Oodle {
                    _lib: lib,
                    decompress,
                    path: dll,
                })
            }
        })
        .as_ref()
}

/// Which decoder `decompress` will use for these roots.
///
/// Loads the DLL as a side effect, so the answer holds for the rest of the
/// process.
pub fn backend(search_roots: &[PathBuf]) -> Backend {
    match load(search_roots) {
        Some(oodle) => Backend::Dll(oodle.path.clone()),
        None => Backend::Pure,
    }
}

/// Decompress with the compiled-in pure-Rust decoder.
fn decompress_pure(src: &[u8], out_size: usize) -> Result<Vec<u8>, Error> {
    let mut out = vec![0u8; out_size];
    let written = EXTRACTOR
        .with(|e| e.borrow_mut().read_from_slice(src, &mut out))
        .map_err(|e| Error::OodlePure(format!("{e:?}")))?;
    if written != out_size {
        return Err(Error::OodleDecompress {
            got: written as i64,
            want: out_size,
        });
    }
    Ok(out)
}

/// Decompress `src` into a buffer of exactly `out_size` bytes, preferring the
/// DLL when the caller supplied a usable one.
pub fn decompress(src: &[u8], out_size: usize, search_roots: &[PathBuf]) -> Result<Vec<u8>, Error> {
    let Some(oodle) = load(search_roots) else {
        return decompress_pure(src, out_size);
    };
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
