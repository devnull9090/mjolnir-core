//! xinput1_4.dll proxy that fabricates a second gamepad.
//!
//! Halo Campaign Evolved's second local player (created with
//! `UGameplayStatics::CreatePlayer(world, 1, true)` at the main menu, then a
//! real campaign launch) is a fully embodied co-op Spartan, but the Blam
//! simulation overwrites every UE-reflection control path — movement injection,
//! control rotation, teleports all revert. Input has to arrive where the game
//! actually reads it. The game exe imports `XInputGetState`/`XInputSetState`
//! from `xinput1_4.dll` by name and detects controller presence from the return
//! code of `XInputGetState` alone (it does not import `XInputGetCapabilities`).
//!
//! So this DLL, dropped in the game's Win64 folder to shadow the system copy,
//! answers `XInputGetState` for one synthetic user index with a controller that
//! is always "connected" and whose stick/button state is read from a small
//! command file. Every other index and every other export is passed through to
//! the real DLL (copied beside us as `xinput1_4_orig.dll`).
//!
//! Every export is a real function rather than a PE forwarder, because Rust's
//! cdylib export generation does not compose with `.def`/`/EXPORT` forwarders.
//! The game imports xinput by name, so plain name exports resolve fine.
//!
//! Command file (default `<exe dir>/ue4ss/mjolnir-bridge/pad1.txt`, overridable
//! with `MJOLNIR_PAD_FILE`), one line of whitespace-separated numbers:
//!
//! ```text
//! <ttl_ms> <lx> <ly> <rx> <ry> <lt> <rt> <buttons_hex>
//! ```
//!
//! Sticks are floats in [-1, 1], triggers in [0, 1], buttons a hex XInput mask.
//! If the file is missing, unparsable, or older than `ttl_ms`, the pad reports
//! centered sticks and no buttons — a dead driver leaves the bot standing still
//! rather than running forever. Synthetic index defaults to 1, override with
//! `MJOLNIR_PAD_INDEX`.

use std::ffi::c_void;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, SystemTime};

const ERROR_SUCCESS: u32 = 0;
const ERROR_DEVICE_NOT_CONNECTED: u32 = 1167;

#[repr(C)]
#[derive(Clone, Copy, PartialEq, Default)]
pub struct XinputGamepad {
    buttons: u16,
    left_trigger: u8,
    right_trigger: u8,
    thumb_lx: i16,
    thumb_ly: i16,
    thumb_rx: i16,
    thumb_ry: i16,
}

#[repr(C)]
pub struct XinputState {
    packet_number: u32,
    gamepad: XinputGamepad,
}

#[repr(C)]
#[derive(Default)]
pub struct XinputVibration {
    left_motor: u16,
    right_motor: u16,
}

#[repr(C)]
pub struct XinputCapabilities {
    kind: u8,
    sub_type: u8,
    flags: u16,
    gamepad: XinputGamepad,
    vibration: XinputVibration,
}

// ---- real DLL binding -------------------------------------------------------

type GetStateFn = unsafe extern "system" fn(u32, *mut XinputState) -> u32;
type SetStateFn = unsafe extern "system" fn(u32, *mut XinputVibration) -> u32;
type GetCapsFn = unsafe extern "system" fn(u32, u32, *mut XinputCapabilities) -> u32;
type EnableFn = unsafe extern "system" fn(i32);
type GetBatteryFn = unsafe extern "system" fn(u32, u8, *mut c_void) -> u32;
type GetKeystrokeFn = unsafe extern "system" fn(u32, u32, *mut c_void) -> u32;
type GetAudioIdsFn =
    unsafe extern "system" fn(u32, *mut u16, *mut u32, *mut u16, *mut u32) -> u32;

#[derive(Default)]
struct Real {
    get_state: Option<GetStateFn>,
    get_state_ex: Option<GetStateFn>,
    set_state: Option<SetStateFn>,
    get_caps: Option<GetCapsFn>,
    enable: Option<EnableFn>,
    get_battery: Option<GetBatteryFn>,
    get_keystroke: Option<GetKeystrokeFn>,
    get_audio_ids: Option<GetAudioIdsFn>,
}

#[link(name = "kernel32")]
extern "system" {
    fn LoadLibraryW(name: *const u16) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const u8) -> *mut c_void;
}

/// Reinterpret a resolved address as a typed function pointer, or `None` if the
/// lookup failed. A fn pointer is the same width as the raw address.
unsafe fn cast<T: Copy>(p: *mut c_void) -> Option<T> {
    if p.is_null() {
        None
    } else {
        Some(std::mem::transmute_copy(&p))
    }
}

fn real() -> &'static Real {
    static REAL: OnceLock<Real> = OnceLock::new();
    REAL.get_or_init(|| unsafe {
        let name: Vec<u16> = "xinput1_4_orig.dll\0".encode_utf16().collect();
        let module = LoadLibraryW(name.as_ptr());
        if module.is_null() {
            return Real::default();
        }
        let by_name = |sym: &[u8]| GetProcAddress(module, sym.as_ptr());
        // XInputGetStateEx has no name in the real DLL; resolve it by ordinal 100
        // (MAKEINTRESOURCE: the ordinal is passed as the name pointer).
        let by_ord = |ord: usize| GetProcAddress(module, ord as *const u8);
        Real {
            get_state: cast(by_name(b"XInputGetState\0")),
            get_state_ex: cast(by_ord(100)),
            set_state: cast(by_name(b"XInputSetState\0")),
            get_caps: cast(by_name(b"XInputGetCapabilities\0")),
            enable: cast(by_name(b"XInputEnable\0")),
            get_battery: cast(by_name(b"XInputGetBatteryInformation\0")),
            get_keystroke: cast(by_name(b"XInputGetKeystroke\0")),
            get_audio_ids: cast(by_name(b"XInputGetAudioDeviceIds\0")),
        }
    })
}

// ---- synthetic pad ----------------------------------------------------------

fn synth_index() -> u32 {
    static IDX: OnceLock<u32> = OnceLock::new();
    *IDX.get_or_init(|| {
        std::env::var("MJOLNIR_PAD_INDEX")
            .ok()
            .and_then(|s| s.trim().parse().ok())
            .unwrap_or(1)
    })
}

fn pad_path() -> &'static PathBuf {
    static PATH: OnceLock<PathBuf> = OnceLock::new();
    PATH.get_or_init(|| {
        if let Ok(p) = std::env::var("MJOLNIR_PAD_FILE") {
            return PathBuf::from(p);
        }
        // current_exe() in a hosted DLL is the game exe; its parent is Win64.
        let base = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_default();
        base.join("ue4ss").join("mjolnir-bridge").join("pad1.txt")
    })
}

/// Parse the command file, returning the pad only if it is fresh. Any failure
/// (missing, unreadable, malformed, stale) yields `None` -> neutral state.
fn read_pad() -> Option<XinputGamepad> {
    let path = pad_path();
    let meta = std::fs::metadata(path).ok()?;
    let modified = meta.modified().ok()?;
    let text = std::fs::read_to_string(path).ok()?;
    let mut it = text.split_whitespace();

    let ttl_ms: u64 = it.next()?.parse().ok()?;
    if SystemTime::now()
        .duration_since(modified)
        .unwrap_or(Duration::ZERO)
        > Duration::from_millis(ttl_ms)
    {
        return None;
    }

    let f = |s: Option<&str>| -> Option<f32> { s?.parse().ok() };
    let lx = f(it.next())?.clamp(-1.0, 1.0);
    let ly = f(it.next())?.clamp(-1.0, 1.0);
    let rx = f(it.next())?.clamp(-1.0, 1.0);
    let ry = f(it.next())?.clamp(-1.0, 1.0);
    let lt = f(it.next())?.clamp(0.0, 1.0);
    let rt = f(it.next())?.clamp(0.0, 1.0);
    let buttons = u16::from_str_radix(it.next()?.trim_start_matches("0x"), 16).ok()?;

    let axis = |v: f32| (v * 32767.0).round().clamp(-32767.0, 32767.0) as i16;
    let trig = |v: f32| (v * 255.0).round().clamp(0.0, 255.0) as u8;
    Some(XinputGamepad {
        buttons,
        left_trigger: trig(lt),
        right_trigger: trig(rt),
        thumb_lx: axis(lx),
        thumb_ly: axis(ly),
        thumb_rx: axis(rx),
        thumb_ry: axis(ry),
    })
}

struct Cache {
    last_tick: SystemTime,
    gamepad: XinputGamepad,
}

/// Current synthetic gamepad, re-reading the command file at most every few ms
/// so a per-frame poll does not hammer the filesystem. The packet number only
/// advances when the produced state actually changes, matching XInput semantics
/// (the game ignores an unchanged packet).
fn current_gamepad() -> (u32, XinputGamepad) {
    static CACHE: OnceLock<Mutex<Cache>> = OnceLock::new();
    static PACKET: AtomicU32 = AtomicU32::new(0);
    let cache = CACHE.get_or_init(|| {
        Mutex::new(Cache {
            last_tick: SystemTime::UNIX_EPOCH,
            gamepad: XinputGamepad::default(),
        })
    });
    let mut c = cache.lock().unwrap_or_else(|e| e.into_inner());
    let stale = c
        .last_tick
        .elapsed()
        .map(|d| d > Duration::from_millis(4))
        .unwrap_or(true);
    if stale {
        let next = read_pad().unwrap_or_default();
        if next != c.gamepad {
            c.gamepad = next;
            PACKET.fetch_add(1, Ordering::Relaxed);
        }
        c.last_tick = SystemTime::now();
    }
    (PACKET.load(Ordering::Relaxed), c.gamepad)
}

// ---- exports ----------------------------------------------------------------

/// # Safety
/// `state` must be a valid pointer to an `XINPUT_STATE`, per the XInput ABI.
#[no_mangle]
pub unsafe extern "system" fn XInputGetState(user_index: u32, state: *mut XinputState) -> u32 {
    if user_index == synth_index() {
        if !state.is_null() {
            let (packet, gamepad) = current_gamepad();
            (*state).packet_number = packet;
            (*state).gamepad = gamepad;
        }
        return ERROR_SUCCESS;
    }
    match real().get_state {
        Some(f) => f(user_index, state),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}

/// XInputGetStateEx: identical shape; the guide button lives in a bit we leave
/// clear. Overridden for parity in case anything reads the synthetic pad through
/// the extended entry point instead of XInputGetState.
///
/// # Safety
/// Same contract as [`XInputGetState`].
#[no_mangle]
pub unsafe extern "system" fn XInputGetStateEx(user_index: u32, state: *mut XinputState) -> u32 {
    if user_index == synth_index() {
        return XInputGetState(user_index, state);
    }
    match real().get_state_ex.or(real().get_state) {
        Some(f) => f(user_index, state),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}

/// # Safety
/// `vibration` must be a valid pointer to an `XINPUT_VIBRATION`.
#[no_mangle]
pub unsafe extern "system" fn XInputSetState(
    user_index: u32,
    vibration: *mut XinputVibration,
) -> u32 {
    if user_index == synth_index() {
        // The synthetic pad has no motors; accept and ignore rumble.
        return ERROR_SUCCESS;
    }
    match real().set_state {
        Some(f) => f(user_index, vibration),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}

/// # Safety
/// `caps` must be a valid pointer to an `XINPUT_CAPABILITIES`.
#[no_mangle]
pub unsafe extern "system" fn XInputGetCapabilities(
    user_index: u32,
    flags: u32,
    caps: *mut XinputCapabilities,
) -> u32 {
    if user_index == synth_index() {
        if !caps.is_null() {
            // A standard wired gamepad advertising the full button/axis surface.
            (*caps).kind = 1; // XINPUT_DEVTYPE_GAMEPAD
            (*caps).sub_type = 1; // XINPUT_DEVSUBTYPE_GAMEPAD
            (*caps).flags = 0;
            (*caps).gamepad = XinputGamepad {
                buttons: 0xF3FF,
                left_trigger: 0xFF,
                right_trigger: 0xFF,
                thumb_lx: -1,
                thumb_ly: -1,
                thumb_rx: -1,
                thumb_ry: -1,
            };
            (*caps).vibration = XinputVibration { left_motor: 0xFF, right_motor: 0xFF };
        }
        return ERROR_SUCCESS;
    }
    match real().get_caps {
        Some(f) => f(user_index, flags, caps),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}

/// # Safety
/// XInput ABI: `enable` is a BOOL. Pure pass-through.
#[no_mangle]
pub unsafe extern "system" fn XInputEnable(enable: i32) {
    if let Some(f) = real().enable {
        f(enable);
    }
}

/// # Safety
/// `battery` must be a valid pointer to an `XINPUT_BATTERY_INFORMATION`.
#[no_mangle]
pub unsafe extern "system" fn XInputGetBatteryInformation(
    user_index: u32,
    dev_type: u8,
    battery: *mut c_void,
) -> u32 {
    match real().get_battery {
        Some(f) => f(user_index, dev_type, battery),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}

/// # Safety
/// `keystroke` must be a valid pointer to an `XINPUT_KEYSTROKE`.
#[no_mangle]
pub unsafe extern "system" fn XInputGetKeystroke(
    user_index: u32,
    reserved: u32,
    keystroke: *mut c_void,
) -> u32 {
    match real().get_keystroke {
        Some(f) => f(user_index, reserved, keystroke),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}

/// # Safety
/// Pointers must be valid per the XInputGetAudioDeviceIds ABI.
#[no_mangle]
pub unsafe extern "system" fn XInputGetAudioDeviceIds(
    user_index: u32,
    render_id: *mut u16,
    render_count: *mut u32,
    capture_id: *mut u16,
    capture_count: *mut u32,
) -> u32 {
    match real().get_audio_ids {
        Some(f) => f(user_index, render_id, render_count, capture_id, capture_count),
        None => ERROR_DEVICE_NOT_CONNECTED,
    }
}
