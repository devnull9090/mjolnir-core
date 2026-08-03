//! The platform side: finding the game process and reaching its memory.
//!
//! Declared against the Win32 API directly rather than through a binding crate,
//! because the surface used here is six functions and two structs, and the
//! workspace has no other reason to carry a Windows crate.

use crate::{Error, Result};

/// A running process we might attach to.
#[derive(Debug, Clone)]
pub struct ProcessInfo {
    pub pid: u32,
    pub exe: String,
}

/// One committed, readable span of the target's address space.
#[derive(Debug, Clone, Copy)]
pub struct Region {
    pub base: u64,
    pub size: u64,
    pub protect: u32,
}

#[cfg(windows)]
mod imp {
    use super::{Error, ProcessInfo, Region, Result};
    use std::io;

    type Handle = isize;

    const PROCESS_QUERY_INFORMATION: u32 = 0x0400;
    const PROCESS_VM_READ: u32 = 0x0010;
    const PROCESS_VM_WRITE: u32 = 0x0020;
    const PROCESS_VM_OPERATION: u32 = 0x0008;

    const TH32CS_SNAPPROCESS: u32 = 0x0000_0002;
    const MEM_COMMIT: u32 = 0x1000;
    /// Heap allocations are private. Image and mapped-file regions cannot hold a
    /// tag heap, and skipping them is a statement about what a heap *is* rather
    /// than a guess about size — which is the distinction that matters, because
    /// a size filter here silently skips the very regions the tag lives in.
    const MEM_PRIVATE: u32 = 0x0002_0000;

    const PAGE_READWRITE: u32 = 0x04;
    const PAGE_EXECUTE_READWRITE: u32 = 0x40;
    const PAGE_WRITECOPY: u32 = 0x08;
    const PAGE_EXECUTE_WRITECOPY: u32 = 0x80;
    /// Pages that can hold a tag heap: private, writable data.
    const WRITABLE: [u32; 4] = [
        PAGE_READWRITE,
        PAGE_EXECUTE_READWRITE,
        PAGE_WRITECOPY,
        PAGE_EXECUTE_WRITECOPY,
    ];
    /// Guard and no-access pages must never be touched; reading one is a fault
    /// in the target, not in us, and would be a rude way to crash the game.
    const PAGE_GUARD: u32 = 0x100;
    const PAGE_NOACCESS: u32 = 0x01;

    #[repr(C)]
    #[derive(Default, Clone, Copy)]
    struct MemoryBasicInformation {
        base_address: usize,
        allocation_base: usize,
        allocation_protect: u32,
        partition_id: u16,
        _pad: u16,
        region_size: usize,
        state: u32,
        protect: u32,
        kind: u32,
        _alignment: u32,
    }

    #[repr(C)]
    struct ProcessEntry32W {
        size: u32,
        usage: u32,
        process_id: u32,
        default_heap_id: usize,
        module_id: u32,
        threads: u32,
        parent_process_id: u32,
        pri_class_base: i32,
        flags: u32,
        exe_file: [u16; 260],
    }

    extern "system" {
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
        fn CloseHandle(h: Handle) -> i32;
        fn ReadProcessMemory(
            h: Handle,
            addr: usize,
            buf: *mut u8,
            len: usize,
            read: *mut usize,
        ) -> i32;
        fn WriteProcessMemory(
            h: Handle,
            addr: usize,
            buf: *const u8,
            len: usize,
            written: *mut usize,
        ) -> i32;
        fn VirtualQueryEx(
            h: Handle,
            addr: usize,
            info: *mut MemoryBasicInformation,
            len: usize,
        ) -> usize;
        fn VirtualProtectEx(h: Handle, addr: usize, len: usize, new: u32, old: *mut u32) -> i32;
        fn CreateToolhelp32Snapshot(flags: u32, pid: u32) -> Handle;
        fn Process32FirstW(snap: Handle, entry: *mut ProcessEntry32W) -> i32;
        fn Process32NextW(snap: Handle, entry: *mut ProcessEntry32W) -> i32;
    }

    /// An open handle to the game.
    pub struct Process {
        handle: Handle,
        pub pid: u32,
    }

    impl Drop for Process {
        fn drop(&mut self) {
            unsafe { CloseHandle(self.handle) };
        }
    }

    pub fn running(exe: &str) -> Result<Vec<ProcessInfo>> {
        let mut found = Vec::new();
        unsafe {
            let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if snap == -1 {
                return Err(Error::NotRunning(exe.to_string()));
            }
            let mut entry: ProcessEntry32W = std::mem::zeroed();
            entry.size = std::mem::size_of::<ProcessEntry32W>() as u32;
            let mut ok = Process32FirstW(snap, &mut entry);
            while ok != 0 {
                let end = entry
                    .exe_file
                    .iter()
                    .position(|c| *c == 0)
                    .unwrap_or(entry.exe_file.len());
                let name = String::from_utf16_lossy(&entry.exe_file[..end]);
                if name.eq_ignore_ascii_case(exe) {
                    found.push(ProcessInfo {
                        pid: entry.process_id,
                        exe: name,
                    });
                }
                ok = Process32NextW(snap, &mut entry);
            }
            CloseHandle(snap);
        }
        Ok(found)
    }

    impl Process {
        pub fn open(pid: u32) -> Result<Process> {
            let handle = unsafe {
                OpenProcess(
                    PROCESS_QUERY_INFORMATION
                        | PROCESS_VM_READ
                        | PROCESS_VM_WRITE
                        | PROCESS_VM_OPERATION,
                    0,
                    pid,
                )
            };
            if handle == 0 {
                return Err(Error::Open {
                    pid,
                    source: io::Error::last_os_error(),
                });
            }
            Ok(Process { handle, pid })
        }

        pub fn read(&self, addr: u64, len: usize) -> Result<Vec<u8>> {
            let mut buf = vec![0u8; len];
            let got = self.read_into(addr, &mut buf)?;
            buf.truncate(got);
            Ok(buf)
        }

        /// Read into a caller-owned buffer, returning how many bytes arrived.
        ///
        /// The scan reads gigabytes in 128 MB windows; allocating and zeroing a
        /// fresh buffer for each one is pure waste, so the hot path reuses one.
        pub fn read_into(&self, addr: u64, buf: &mut [u8]) -> Result<usize> {
            let mut got = 0usize;
            let ok = unsafe {
                ReadProcessMemory(
                    self.handle,
                    addr as usize,
                    buf.as_mut_ptr(),
                    buf.len(),
                    &mut got,
                )
            };
            if ok == 0 && got == 0 {
                return Err(Error::Read {
                    addr,
                    len: buf.len(),
                    source: io::Error::last_os_error(),
                });
            }
            Ok(got)
        }

        /// Write bytes, lifting page protection for the duration if needed.
        ///
        /// The tag heap is already writable, so the protection dance is usually
        /// a no-op — it is here so a caller poking a read-only page gets a clear
        /// success or failure rather than a silent partial write.
        pub fn write(&self, addr: u64, data: &[u8]) -> Result<()> {
            let mut old = 0u32;
            unsafe {
                VirtualProtectEx(
                    self.handle,
                    addr as usize,
                    data.len(),
                    PAGE_READWRITE,
                    &mut old,
                )
            };
            let mut put = 0usize;
            let ok = unsafe {
                WriteProcessMemory(
                    self.handle,
                    addr as usize,
                    data.as_ptr(),
                    data.len(),
                    &mut put,
                )
            };
            let err = io::Error::last_os_error();
            if old != 0 {
                let mut back = 0u32;
                unsafe { VirtualProtectEx(self.handle, addr as usize, data.len(), old, &mut back) };
            }
            if ok == 0 || put != data.len() {
                return Err(Error::Write {
                    addr,
                    len: data.len(),
                    source: err,
                });
            }
            Ok(())
        }

        /// Every committed writable region, in address order.
        ///
        /// Deliberately unbounded in region size: the tag heap lives in regions
        /// of several hundred megabytes up to a couple of gigabytes, so any
        /// "skip the huge ones" filter skips precisely the memory being looked
        /// for and turns a hit into a confident miss.
        pub fn writable_regions(&self) -> Result<Vec<Region>> {
            let mut out = Vec::new();
            let mut addr: usize = 0;
            loop {
                let mut info = MemoryBasicInformation::default();
                let got = unsafe {
                    VirtualQueryEx(
                        self.handle,
                        addr,
                        &mut info,
                        std::mem::size_of::<MemoryBasicInformation>(),
                    )
                };
                if got == 0 {
                    break;
                }
                let size = info.region_size;
                let base = if info.base_address == 0 {
                    addr
                } else {
                    info.base_address
                };
                let prot = info.protect;
                let usable = info.state == MEM_COMMIT
                    && info.kind == MEM_PRIVATE
                    && prot & PAGE_GUARD == 0
                    && prot & PAGE_NOACCESS == 0
                    && WRITABLE.contains(&(prot & 0xFF));
                if usable {
                    out.push(Region {
                        base: base as u64,
                        size: size as u64,
                        protect: prot,
                    });
                }
                let Some(next) = base.checked_add(size.max(0x1000)) else {
                    break;
                };
                addr = next;
            }
            Ok(out)
        }
    }
}

#[cfg(not(windows))]
mod imp {
    use super::{Error, ProcessInfo, Region, Result};

    pub struct Process {
        pub pid: u32,
    }

    pub fn running(_exe: &str) -> Result<Vec<ProcessInfo>> {
        Err(Error::Unsupported)
    }

    impl Process {
        pub fn open(_pid: u32) -> Result<Process> {
            Err(Error::Unsupported)
        }
        pub fn read(&self, _addr: u64, _len: usize) -> Result<Vec<u8>> {
            Err(Error::Unsupported)
        }
        pub fn read_into(&self, _addr: u64, _buf: &mut [u8]) -> Result<usize> {
            Err(Error::Unsupported)
        }
        pub fn write(&self, _addr: u64, _data: &[u8]) -> Result<()> {
            Err(Error::Unsupported)
        }
        pub fn writable_regions(&self) -> Result<Vec<Region>> {
            Err(Error::Unsupported)
        }
    }
}

pub use imp::Process;

impl Process {
    /// Attach to the single running game, or say plainly why we cannot.
    pub fn attach() -> Result<Process> {
        let mut found = imp::running(crate::GAME_EXE)?;
        match found.len() {
            0 => Err(Error::NotRunning(crate::GAME_EXE.to_string())),
            1 => Process::open(found.remove(0).pid),
            // Two copies means two tag heaps and no way to tell which the player
            // is looking at, so refuse rather than pick.
            n => Err(Error::Ambiguous(n)),
        }
    }
}
