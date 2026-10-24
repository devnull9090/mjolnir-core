//! C ABI over [`blam_megalo::Variant::validate`] for the native map-registry
//! DLL (`native/map_registry/mjolnir_map_registry.c`), so it can check a
//! staged `.mglo` against the simulation's grammar and store bounds before the
//! file loader decodes it (docs/re/variant_network_safety.md). This is the last
//! line of defense for a `.mglo` that reached disk past the launcher's
//! install-time check — a sideloaded map, say.

/// Validate a `.mglo` byte buffer. Returns `0` when the simulation can decode
/// it safely, `1` when it is malformed or past the simulation's store bounds,
/// and `-1` for a null pointer. The caller stages the file only on `0`.
///
/// # Safety
/// `data` must point to `len` readable bytes, or be null.
#[no_mangle]
pub unsafe extern "C" fn mjolnir_mglo_validate(data: *const u8, len: usize) -> i32 {
    if data.is_null() {
        return -1;
    }
    let bytes = std::slice::from_raw_parts(data, len);
    match blam_megalo::Variant::validate(bytes) {
        Ok(()) => 0,
        Err(_) => 1,
    }
}
