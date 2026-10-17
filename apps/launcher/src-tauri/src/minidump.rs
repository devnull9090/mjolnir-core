//! Just enough of the Windows minidump format to say where a crash happened
//! and to write a slim copy of the dump for a crash report
//! (docs/crash_reports.md).
//!
//! The game's dumps are ~172 MB, nearly all of it memory: module data
//! sections and whatever the stacks point at. A report needs the exception,
//! the registers, the thread stacks and the module list; the rest is bulk,
//! and it is also where anything private sits. The slim copy keeps the file's
//! layout and size and zeroes what it drops, so no offset inside the dump
//! has to be rewritten, debuggers still open it, and the zeroes compress to
//! almost nothing in the report's zip.

use std::io::{self, Read, Seek, SeekFrom, Write};

const SIGNATURE: u32 = 0x504d_444d; // "MDMP"

/// Stream types (MINIDUMP_STREAM_TYPE) this module reads or removes.
const UNUSED_STREAM: u32 = 0;
const THREAD_LIST: u32 = 3;
const MODULE_LIST: u32 = 4;
const MEMORY_LIST: u32 = 5;
const EXCEPTION: u32 = 6;
const MEMORY64_LIST: u32 = 9;
const COMMENT_A: u32 = 10;
const COMMENT_W: u32 = 11;
const HANDLE_DATA: u32 = 12;
const HANDLE_OPERATION_LIST: u32 = 18;
const TOKEN: u32 = 19;
/// Streams from here up belong to whoever wrote the dump. UE puts its crash
/// context XML there (as UTF-16), machine and account ids included.
const FIRST_USER_STREAM: u32 = 0x10000;

/// What the slim copy removes outright, besides memory.
fn dropped_stream(kind: u32) -> bool {
    matches!(
        kind,
        MEMORY64_LIST | COMMENT_A | COMMENT_W | HANDLE_DATA | HANDLE_OPERATION_LIST | TOKEN
    ) || kind >= FIRST_USER_STREAM
}

#[derive(Debug, Clone, Copy)]
pub struct Stream {
    /// Position in the stream directory.
    pub index: usize,
    pub kind: u32,
    pub size: u32,
    pub rva: u32,
}

#[derive(Debug, Clone, Copy)]
pub struct Exception {
    pub code: u32,
    pub address: u64,
}

#[derive(Debug, Clone)]
pub struct Module {
    pub base: u64,
    pub size: u32,
    /// Full path as the process saw it.
    pub name: String,
    /// Where the name's MINIDUMP_STRING sits in the file.
    pub name_rva: u32,
}

impl Module {
    pub fn file_name(&self) -> &str {
        self.name.rsplit(['\\', '/']).next().unwrap_or(&self.name)
    }
}

#[derive(Debug, Clone, Copy)]
struct Range {
    /// Address in the crashed process.
    start: u64,
    size: u32,
    /// Where its bytes sit in the file.
    rva: u32,
}

#[derive(Debug)]
pub struct Dump {
    directory_rva: u32,
    pub streams: Vec<Stream>,
    pub exception: Option<Exception>,
    pub modules: Vec<Module>,
    /// Each thread's stack, as captured.
    stacks: Vec<Range>,
    memory: Vec<Range>,
    /// Memory64List's data block: one run from its base, `(rva, bytes)`.
    memory64: Option<(u64, u64)>,
}

fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}

fn u64_at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}

fn invalid(msg: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, msg.to_string())
}

fn read_at<R: Read + Seek>(r: &mut R, rva: u64, len: usize) -> io::Result<Vec<u8>> {
    r.seek(SeekFrom::Start(rva))?;
    let mut buf = vec![0; len];
    r.read_exact(&mut buf)?;
    Ok(buf)
}

/// A MINIDUMP_STRING: a byte length, then UTF-16.
fn read_string<R: Read + Seek>(r: &mut R, rva: u32) -> io::Result<String> {
    let len = u32_at(&read_at(r, rva as u64, 4)?, 0) as usize;
    if len > 64 * 1024 {
        return Err(invalid("string too long"));
    }
    let bytes = read_at(r, rva as u64 + 4, len)?;
    let units: Vec<u16> = bytes
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    Ok(String::from_utf16_lossy(&units))
}

/// Reads the header, the directory and the streams this module uses.
/// Seeks only; the memory itself is never read.
pub fn read<R: Read + Seek>(r: &mut R) -> io::Result<Dump> {
    let header = read_at(r, 0, 32)?;
    if u32_at(&header, 0) != SIGNATURE {
        return Err(invalid("not a minidump"));
    }
    let count = u32_at(&header, 8) as usize;
    let directory_rva = u32_at(&header, 12);
    if count > 1024 {
        return Err(invalid("too many streams"));
    }
    let dir = read_at(r, directory_rva as u64, count * 12)?;
    let streams: Vec<Stream> = (0..count)
        .map(|i| Stream {
            index: i,
            kind: u32_at(&dir, i * 12),
            size: u32_at(&dir, i * 12 + 4),
            rva: u32_at(&dir, i * 12 + 8),
        })
        .collect();
    let find = |kind: u32| streams.iter().find(|s| s.kind == kind && s.size > 0).copied();

    let exception = match find(EXCEPTION) {
        // ThreadId, alignment, then MINIDUMP_EXCEPTION: code, flags, record, address.
        Some(s) if s.size >= 32 => {
            let b = read_at(r, s.rva as u64, 32)?;
            Some(Exception { code: u32_at(&b, 8), address: u64_at(&b, 24) })
        }
        _ => None,
    };

    let mut modules = Vec::new();
    if let Some(s) = find(MODULE_LIST) {
        const ENTRY: usize = 108;
        let n = u32_at(&read_at(r, s.rva as u64, 4)?, 0) as usize;
        if 4 + n * ENTRY > s.size as usize {
            return Err(invalid("module list overruns its stream"));
        }
        let b = read_at(r, s.rva as u64 + 4, n * ENTRY)?;
        for i in 0..n {
            let at = i * ENTRY;
            let name_rva = u32_at(&b, at + 20);
            modules.push(Module {
                base: u64_at(&b, at),
                size: u32_at(&b, at + 8),
                name: read_string(r, name_rva).unwrap_or_default(),
                name_rva,
            });
        }
    }

    let mut stacks = Vec::new();
    if let Some(s) = find(THREAD_LIST) {
        const ENTRY: usize = 48;
        let n = u32_at(&read_at(r, s.rva as u64, 4)?, 0) as usize;
        if 4 + n * ENTRY > s.size as usize {
            return Err(invalid("thread list overruns its stream"));
        }
        let b = read_at(r, s.rva as u64 + 4, n * ENTRY)?;
        for i in 0..n {
            // Id, suspend count, priority class, priority, TEB, then the
            // stack's MINIDUMP_MEMORY_DESCRIPTOR.
            let at = i * ENTRY + 24;
            stacks.push(Range { start: u64_at(&b, at), size: u32_at(&b, at + 8), rva: u32_at(&b, at + 12) });
        }
    }

    let mut memory = Vec::new();
    if let Some(s) = find(MEMORY_LIST) {
        let n = u32_at(&read_at(r, s.rva as u64, 4)?, 0) as usize;
        if 4 + n * 16 > s.size as usize {
            return Err(invalid("memory list overruns its stream"));
        }
        let b = read_at(r, s.rva as u64 + 4, n * 16)?;
        for i in 0..n {
            let at = i * 16;
            memory.push(Range { start: u64_at(&b, at), size: u32_at(&b, at + 8), rva: u32_at(&b, at + 12) });
        }
    }

    let memory64 = match find(MEMORY64_LIST) {
        Some(s) if s.size >= 16 => {
            let head = read_at(r, s.rva as u64, 16)?;
            let n = u64_at(&head, 0) as usize;
            let base = u64_at(&head, 8);
            if 16 + n * 16 > s.size as usize {
                return Err(invalid("memory64 list overruns its stream"));
            }
            let b = read_at(r, s.rva as u64 + 16, n * 16)?;
            let total: u64 = (0..n).map(|i| u64_at(&b, i * 16 + 8)).sum();
            Some((base, total))
        }
        _ => None,
    };

    Ok(Dump { directory_rva, streams, exception, modules, stacks, memory, memory64 })
}

/// The module the faulting instruction is in, and its offset there.
pub fn fault(dump: &Dump) -> Option<(&Module, u64)> {
    let addr = dump.exception?.address;
    dump.modules
        .iter()
        .find(|m| m.base <= addr && addr < m.base + m.size as u64)
        .map(|m| (m, addr - m.base))
}

/// Byte edits that turn the dump into its slim copy: `patches` overwrite,
/// `zeros` blank `(offset, length)` runs. Never overlapping each other.
#[derive(Debug, Default)]
pub struct Plan {
    pub patches: Vec<(u64, Vec<u8>)>,
    pub zeros: Vec<(u64, u64)>,
}

/// Same-length masking for strings inside the dump, which cannot grow.
pub type Mask = fn(&str) -> String;

/// Whether a memory range holds (part of) some thread's stack.
fn on_stack(dump: &Dump, m: &Range) -> bool {
    dump.stacks
        .iter()
        .any(|s| s.size > 0 && m.start < s.start + s.size as u64 && s.start < m.start + m.size as u64)
}

/// `\Users\<name>` in raw memory, as ASCII or UTF-16, either slash, any
/// case: `(offset, underscores)` over each name, the same length.
fn user_path_patches(bytes: &[u8]) -> Vec<(usize, Vec<u8>)> {
    const MAX_NAME: usize = 64;
    let sep = |c: u16| c == b'\\' as u16 || c == b'/' as u16;
    let name_char = |c: u16| c >= 0x20 && c != 0x7f && !matches!(c, 0x22 | 0x2a | 0x2f | 0x3a | 0x3c | 0x3e | 0x3f | 0x5c | 0x7c);
    let mut out = Vec::new();
    // Width 1 is ASCII (or UTF-8), width 2 UTF-16LE.
    for width in [1usize, 2] {
        let unit = |i: usize| -> Option<u16> {
            match width {
                1 => bytes.get(i).map(|&b| b as u16),
                _ => Some(u16::from_le_bytes([*bytes.get(i)?, *bytes.get(i + 1)?])),
            }
        };
        let mut i = 0;
        while i + 7 * width <= bytes.len() {
            let matches = unit(i).is_some_and(sep)
                && b"users".iter().enumerate().all(|(k, &ch)| {
                    unit(i + (k + 1) * width).is_some_and(|c| c < 0x80 && (c as u8).eq_ignore_ascii_case(&ch))
                })
                && unit(i + 6 * width).is_some_and(sep);
            if !matches {
                i += 1;
                continue;
            }
            let start = i + 7 * width;
            let mut end = start;
            while (end - start) / width < MAX_NAME && unit(end).is_some_and(name_char) {
                end += width;
            }
            if end > start {
                let masked = match width {
                    1 => vec![b'_'; end - start],
                    _ => [b'_', 0].repeat((end - start) / 2),
                };
                out.push((start, masked));
            }
            i = end.max(i + 1);
        }
    }
    out
}

/// Plans the slim copy: memory ranges that are not thread stacks, the
/// streams in `dropped_stream`, and module paths through `mask` (which must
/// keep the length).
pub fn slim_plan<R: Read + Seek>(r: &mut R, dump: &Dump, mask: Mask) -> io::Result<Plan> {
    let mut plan = Plan::default();
    // File runs that must survive whatever else is zeroed.
    let keep: Vec<(u64, u64)> = dump
        .stacks
        .iter()
        .filter(|s| s.size > 0)
        .map(|s| (s.rva as u64, s.size as u64))
        .collect();
    let zero = |plan: &mut Plan, start: u64, len: u64| {
        // Subtract every kept run from [start, start + len).
        let mut pieces = vec![(start, start + len)];
        for &(ks, kl) in &keep {
            let ke = ks + kl;
            pieces = pieces
                .into_iter()
                .flat_map(|(a, b)| {
                    if ke <= a || b <= ks {
                        vec![(a, b)]
                    } else {
                        let mut out = Vec::new();
                        if a < ks {
                            out.push((a, ks));
                        }
                        if ke < b {
                            out.push((ke, b));
                        }
                        out
                    }
                })
                .collect();
        }
        plan.zeros.extend(pieces.into_iter().filter(|(a, b)| b > a).map(|(a, b)| (a, b - a)));
    };

    // Memory: keep the ranges that hold a thread's stack.
    if let Some(list) = dump.streams.iter().find(|s| s.kind == MEMORY_LIST && s.size > 0) {
        let (kept, dropped): (Vec<Range>, Vec<Range>) = dump.memory.iter().partition(|m| on_stack(dump, m));
        let mut bytes = Vec::with_capacity(list.size as usize);
        bytes.extend_from_slice(&(kept.len() as u32).to_le_bytes());
        for m in &kept {
            bytes.extend_from_slice(&m.start.to_le_bytes());
            bytes.extend_from_slice(&m.size.to_le_bytes());
            bytes.extend_from_slice(&m.rva.to_le_bytes());
        }
        bytes.resize(list.size as usize, 0);
        plan.patches.push((list.rva as u64, bytes));
        for m in dropped {
            zero(&mut plan, m.rva as u64, m.size as u64);
        }
    }

    // Whole streams: mark them unused in the directory and blank their bytes.
    for s in dump.streams.iter().filter(|s| dropped_stream(s.kind)) {
        let mut entry = Vec::with_capacity(12);
        entry.extend_from_slice(&UNUSED_STREAM.to_le_bytes());
        entry.extend_from_slice(&0u32.to_le_bytes());
        entry.extend_from_slice(&0u32.to_le_bytes());
        plan.patches.push((dump.directory_rva as u64 + s.index as u64 * 12, entry));
        if s.size > 0 {
            zero(&mut plan, s.rva as u64, s.size as u64);
        }
    }
    if let Some((base, len)) = dump.memory64 {
        zero(&mut plan, base, len);
    }

    // Stacks hold strings too: a path a function was handed is often there.
    let mut runs: Vec<(u64, u64)> = dump
        .memory
        .iter()
        .filter(|m| on_stack(dump, m))
        .chain(dump.stacks.iter())
        .filter(|m| m.size > 0)
        .map(|m| (m.rva as u64, m.rva as u64 + m.size as u64))
        .collect();
    runs.sort_unstable();
    let mut merged: Vec<(u64, u64)> = Vec::new();
    for (a, b) in runs {
        match merged.last_mut() {
            Some(last) if a <= last.1 => last.1 = last.1.max(b),
            _ => merged.push((a, b)),
        }
    }
    for (a, b) in merged {
        let bytes = read_at(r, a, (b - a) as usize)?;
        for (at, masked) in user_path_patches(&bytes) {
            plan.patches.push((a + at as u64, masked));
        }
    }

    // Module paths name the Windows account when the game sits under it.
    for m in &dump.modules {
        let masked = mask(&m.name);
        if masked != m.name && masked.encode_utf16().count() == m.name.encode_utf16().count() {
            let bytes: Vec<u8> = masked.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
            plan.patches.push((m.name_rva as u64 + 4, bytes));
        }
    }

    // Checked here so `apply` can trust it: a patch inside a zeroed run would
    // depend on the order they are applied in.
    let file_len = r.seek(SeekFrom::End(0))?;
    plan.zeros.sort_unstable();
    for (off, bytes) in &plan.patches {
        let (off, len) = (*off, bytes.len() as u64);
        if off + len > file_len {
            return Err(invalid("patch past the end of the dump"));
        }
        if plan.zeros.iter().any(|&(z, zl)| off < z + zl && z < off + len) {
            return Err(invalid("patch overlaps a dropped range"));
        }
    }
    Ok(plan)
}

/// Copies `src` to `dst` with the plan applied, streaming. Returns the bytes
/// written, which is the dump's own size.
pub fn apply<R: Read, W: Write>(src: &mut R, dst: &mut W, plan: &Plan) -> io::Result<u64> {
    let mut buf = vec![0u8; 1 << 20];
    let mut pos = 0u64;
    loop {
        let n = src.read(&mut buf)?;
        if n == 0 {
            break;
        }
        let (a, b) = (pos, pos + n as u64);
        for &(z, zl) in &plan.zeros {
            let (s, e) = (z.max(a), (z + zl).min(b));
            if s < e {
                buf[(s - a) as usize..(e - a) as usize].fill(0);
            }
        }
        for (off, bytes) in &plan.patches {
            let (s, e) = ((*off).max(a), (off + bytes.len() as u64).min(b));
            if s < e {
                buf[(s - a) as usize..(e - a) as usize]
                    .copy_from_slice(&bytes[(s - off) as usize..(e - off) as usize]);
            }
        }
        dst.write_all(&buf[..n])?;
        pos = b;
    }
    Ok(pos)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::io::Cursor;

    /// A small dump laid out the way MiniDumpWriteDump lays one out: header,
    /// directory, streams, then memory. Two threads; memory holds both
    /// stacks, a data section, and a heap range the second stack points at.
    pub(crate) fn sample_dump(module_path: &str) -> Vec<u8> {
        let mut f = vec![0u8; 0x1000];
        let put32 = |f: &mut Vec<u8>, at: usize, v: u32| f[at..at + 4].copy_from_slice(&v.to_le_bytes());
        let put64 = |f: &mut Vec<u8>, at: usize, v: u64| f[at..at + 8].copy_from_slice(&v.to_le_bytes());

        // Header: 6 streams, directory at 0x20.
        put32(&mut f, 0, SIGNATURE);
        put32(&mut f, 4, 0xa793);
        put32(&mut f, 8, 6);
        put32(&mut f, 12, 0x20);
        let dir = |f: &mut Vec<u8>, i: usize, kind: u32, size: u32, rva: u32| {
            put32(f, 0x20 + i * 12, kind);
            put32(f, 0x24 + i * 12, size);
            put32(f, 0x28 + i * 12, rva);
        };

        // Exception at 0x100: access violation inside the module.
        dir(&mut f, 0, EXCEPTION, 168, 0x100);
        put32(&mut f, 0x100 + 8, 0xc000_0005);
        put64(&mut f, 0x100 + 24, 0x7ff6_0000_0000 + 0x2580d7);

        // Module list at 0x200: one module, its name at 0x300.
        dir(&mut f, 1, MODULE_LIST, 4 + 108, 0x200);
        put32(&mut f, 0x200, 1);
        put64(&mut f, 0x204, 0x7ff6_0000_0000);
        put32(&mut f, 0x204 + 8, 0x0100_0000);
        put32(&mut f, 0x204 + 20, 0x300);
        let name: Vec<u8> = module_path.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
        put32(&mut f, 0x300, name.len() as u32);
        f[0x304..0x304 + name.len()].copy_from_slice(&name);

        // Thread list at 0x500: stacks at 0x10000 (0x100 bytes, file 0x1000)
        // and 0x20000 (0x100 bytes, file 0x1100).
        dir(&mut f, 2, THREAD_LIST, 4 + 2 * 48, 0x500);
        put32(&mut f, 0x500, 2);
        for (i, (start, rva)) in [(0x10000u64, 0x1000u32), (0x20000, 0x1100)].into_iter().enumerate() {
            let at = 0x504 + i * 48 + 24;
            put64(&mut f, at, start);
            put32(&mut f, at + 8, 0x100);
            put32(&mut f, at + 12, rva);
        }

        // Memory list at 0x700: both stacks, a data section, a heap range.
        dir(&mut f, 3, MEMORY_LIST, 4 + 4 * 16, 0x700);
        put32(&mut f, 0x700, 4);
        let ranges = [(0x10000u64, 0x100u32, 0x1000u32), (0x20000, 0x100, 0x1100), (0x7ff6_0080_0000, 0x200, 0x1200), (0x5000_0000, 0x80, 0x1400)];
        for (i, (start, size, rva)) in ranges.into_iter().enumerate() {
            let at = 0x704 + i * 16;
            put64(&mut f, at, start);
            put32(&mut f, at + 8, size);
            put32(&mut f, at + 12, rva);
        }

        // Handle data at 0x800, and UE's XML as a user stream at 0x900.
        dir(&mut f, 4, HANDLE_DATA, 0x40, 0x800);
        f[0x800..0x840].fill(0x48);
        dir(&mut f, 5, FIRST_USER_STREAM, 0x40, 0x900);
        f[0x900..0x940].fill(0x58);

        // Memory: stacks 0xAA, data 0xDD, heap 0xEE.
        f.resize(0x1480, 0);
        f[0x1000..0x1200].fill(0xaa);
        f[0x1200..0x1400].fill(0xdd);
        f[0x1400..0x1480].fill(0xee);
        f
    }

    fn mask_will(s: &str) -> String {
        s.replace("\\will\\", "\\____\\")
    }

    #[test]
    fn paths_on_the_stack_lose_the_user_name() {
        let mut bytes = sample_dump(r"C:\Games\UE4SS.dll");
        let wide: Vec<u8> = r"C:\Users\will\AppData".encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
        // One string at an odd offset, as a packed struct might leave it.
        bytes[0x1011..0x1011 + wide.len()].copy_from_slice(&wide);
        bytes[0x1100..0x1100 + 18].copy_from_slice(b"d:/USERS/will.doe\0");
        let mut cur = Cursor::new(&bytes);
        let dump = read(&mut cur).unwrap();
        let plan = slim_plan(&mut cur, &dump, mask_will).unwrap();
        let mut out = Vec::new();
        cur.set_position(0);
        apply(&mut cur, &mut out, &plan).unwrap();

        let masked: Vec<u8> = r"C:\Users\____\AppData".encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
        assert_eq!(&out[0x1011..0x1011 + masked.len()], &masked[..]);
        assert_eq!(&out[0x1100..0x1100 + 18], b"d:/USERS/________\0");
        // Nothing else on the stacks changed.
        assert_eq!(out[0x1000..0x1011], bytes[0x1000..0x1011]);
        assert_eq!(out[0x1112..0x1200], bytes[0x1112..0x1200]);
        assert!(user_path_patches(b"\\users without a slash after").is_empty());
    }

    #[test]
    fn the_fault_is_the_module_and_offset_of_the_exception() {
        let bytes = sample_dump(r"C:\Games\ue4ss\UE4SS.dll");
        let dump = read(&mut Cursor::new(&bytes)).unwrap();
        let (module, offset) = fault(&dump).unwrap();
        assert_eq!(module.file_name(), "UE4SS.dll");
        assert_eq!(offset, 0x2580d7);
        assert_eq!(dump.exception.unwrap().code, 0xc000_0005);
    }

    #[test]
    fn the_slim_copy_keeps_stacks_and_drops_the_rest() {
        let bytes = sample_dump(r"C:\Users\will\Games\UE4SS.dll");
        let mut cur = Cursor::new(&bytes);
        let dump = read(&mut cur).unwrap();
        let plan = slim_plan(&mut cur, &dump, mask_will).unwrap();
        let mut out = Vec::new();
        cur.set_position(0);
        assert_eq!(apply(&mut cur, &mut out, &plan).unwrap(), bytes.len() as u64);
        assert_eq!(out.len(), bytes.len());

        // Stacks survive; the data section, the heap, the handles and the
        // XML are gone.
        assert_eq!(out[0x1000..0x1200], bytes[0x1000..0x1200]);
        assert!(out[0x1200..0x1480].iter().all(|&b| b == 0));
        assert!(out[0x800..0x840].iter().all(|&b| b == 0));
        assert!(out[0x900..0x940].iter().all(|&b| b == 0));

        // It still reads: two memory ranges, both stacks; the dropped
        // streams are unused; the module path no longer names the account.
        let slim = read(&mut Cursor::new(&out)).unwrap();
        assert_eq!(slim.memory.len(), 2);
        assert!(slim.memory.iter().all(|m| m.start == 0x10000 || m.start == 0x20000));
        assert!(slim.streams.iter().all(|s| s.kind != HANDLE_DATA && s.kind < FIRST_USER_STREAM));
        assert_eq!(slim.modules[0].name, r"C:\Users\____\Games\UE4SS.dll");
        assert_eq!(fault(&slim).unwrap().1, 0x2580d7);
    }

    #[test]
    fn apply_matches_across_buffer_boundaries() {
        // A plan whose runs straddle the 1 MiB read buffer.
        let src: Vec<u8> = (0..3_000_000u32).map(|i| (i % 251) as u8 + 1).collect();
        let plan = Plan {
            patches: vec![((1 << 20) - 2, vec![7, 7, 7, 7])],
            zeros: vec![((2 << 20) - 10, 20)],
        };
        let mut out = Vec::new();
        apply(&mut Cursor::new(&src), &mut out, &plan).unwrap();
        assert_eq!(&out[(1 << 20) - 2..(1 << 20) + 2], &[7, 7, 7, 7]);
        assert!(out[(2 << 20) - 10..(2 << 20) + 10].iter().all(|&b| b == 0));
        assert_eq!(out[(2 << 20) + 10], src[(2 << 20) + 10]);
        assert_eq!(out[..(1 << 20) - 2], src[..(1 << 20) - 2]);
    }
}
