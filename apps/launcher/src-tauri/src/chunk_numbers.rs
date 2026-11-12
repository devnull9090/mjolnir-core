//! The numbers in a hub container's name in Paks:
//! `pakchunk<N>-MJOLNIRHUB-<slug>-<j>_<v>_P` (docs/chunk_numbering.md).
//!
//! `v` is the load order. The engine gives a pak whose name ends `_<v>_P`
//! priority `100 × (v + 1)` above its folder's base (FPakPlatformFile::Mount;
//! a plain `_P` counts as `v = 0`), and the IoStore containers follow the same
//! order. That is the engine's own priority field, so the order no longer
//! leans on how names sort (with equal priority the name that sorts lower
//! wins, which made the old "higher chunk number wins" backwards).
//!
//! `N` names the shader library. The engine opens a mounted pak's library by
//! the number in its file name, so two libraries cooked under the same number
//! cannot both open. Every container the launcher writes takes a local number
//! of its own from [`LOCAL_BASE`] up, and a container with a library has the
//! library renamed to that number as it is copied
//! (`ue_iostore::shader_library::renumber`). The containers in
//! `config/fixed_chunks.json` keep the number they were cooked with: Lua, a
//! tool or the launcher names them by it.
//!
//! Both numbers come from the container's place in the active profile,
//! counting every entry whether enabled or not, so enabling a mod or
//! installing one (appended at the end) renames nothing that is already
//! mounted.

use serde::Deserialize;
use std::sync::OnceLock;

/// The first local chunk number. Our fixed numbers and the game's own are all
/// below it.
pub const LOCAL_BASE: u32 = 10000;

/// The load-order suffix of the first hub container. Loose `_P` containers
/// in Paks (a plain `_P` is `v = 0`: the registration MJOLNIRREG, anything a
/// build script installs by hand) sit below every hub container, which is
/// what wins today in every case measured but one: hub copies beat local 99x
/// overrides (docs/chunk_numbering.md). Suffixes 1 to 999 are free for
/// anything of ours that must load above loose containers but below every
/// hub mod.
pub const HUB_BASE: u32 = 1000;

/// A loose container that has to beat every hub container (a developer's
/// test build of something a hub mod ships) names itself `…_<v>_P` with `v`
/// from here to [`OVERRIDE_MAX`]. The launcher never writes these.
pub const OVERRIDE_BASE: u32 = 20_000_100;

/// The highest suffix whose priority still fits the engine's int32.
pub const OVERRIDE_MAX: u32 = 21_000_000;

// The bands, checked when this compiles: hub suffixes and their live updates
// below the override band, and `100 × (v + 1)` plus a folder base below 10
// inside an int32 for every suffix either band holds.
const _: () = assert!(OVERRIDE_BASE > MAX_SUFFIX + STEP);
const _: () = assert!(100 * (OVERRIDE_MAX as u64 + 1) + 10 < i32::MAX as u64);

/// Suffixes between one container and the next. A live update of a container
/// the game holds open is written beside it at `v + 1`, `v + 2`, `v + 3`
/// (`patch_name`), still below the next container.
pub const STEP: u32 = 4;

/// The highest suffix the launcher writes. The engine keeps priority in an
/// int32, so `100 × (v + 1)` plus the folder's base must stay below 2³¹.
/// At [`STEP`] 4 that is five million containers; past it every container
/// shares the top suffix and their names decide.
pub const MAX_SUFFIX: u32 = 20_000_000;

/// The load-order suffix of the container at `position` (counted across the
/// active profile's entries, in order, then each entry's containers in
/// order). Later wins: a later profile entry over an earlier one, and within
/// one entry a later container over an earlier one.
pub fn suffix(position: usize) -> u32 {
    let v = (STEP as u64).saturating_mul(position as u64).saturating_add(HUB_BASE as u64);
    v.min(MAX_SUFFIX as u64) as u32
}

/// The local chunk number of the container at `position`.
pub fn local_number(position: usize) -> u32 {
    let n = (LOCAL_BASE as u64).saturating_add(position as u64);
    n.min(u32::MAX as u64) as u32
}

/// `pakchunk<digits>` at the start of `stem`: the number and what follows.
pub fn split_number(stem: &str) -> Option<(u32, &str)> {
    if stem.len() <= 8 || !stem[..8].eq_ignore_ascii_case("pakchunk") {
        return None;
    }
    let rest = &stem[8..];
    let digits = rest.bytes().take_while(u8::is_ascii_digit).count();
    let number = rest[..digits].parse().ok()?;
    Some((number, &rest[digits..]))
}

#[derive(Debug, Deserialize)]
pub struct Fixed {
    pub number: u32,
    pub name: String,
    pub library: bool,
    #[allow(dead_code)]
    pub named_by: String,
}

#[derive(Deserialize)]
struct FixedFile {
    fixed: Vec<Fixed>,
}

const FIXED_JSON: &str = include_str!("../../../../config/fixed_chunks.json");

fn parse_fixed(text: &str) -> Result<Vec<Fixed>, String> {
    serde_json::from_str::<FixedFile>(text)
        .map(|f| f.fixed)
        .map_err(|e| format!("config/fixed_chunks.json: {e}"))
}

/// The containers that keep their cooked number.
pub fn fixed() -> &'static [Fixed] {
    static FIXED: OnceLock<Vec<Fixed>> = OnceLock::new();
    FIXED.get_or_init(|| {
        let list = parse_fixed(FIXED_JSON).expect("the bundled fixed-chunk list parses");
        check_fixed(&list).expect("the bundled fixed-chunk list has no duplicates");
        list
    })
}

/// The number a container keeps, when its cached name is one of the fixed
/// ones.
pub fn fixed_number(stem: &str) -> Option<u32> {
    let (number, rest) = split_number(stem)?;
    let rest = rest.strip_prefix('-')?;
    fixed()
        .iter()
        .filter(|f| f.number == number)
        .find(|f| {
            rest.len() >= f.name.len()
                && rest[..f.name.len()].eq_ignore_ascii_case(&f.name)
                && matches!(rest.as_bytes().get(f.name.len()), None | Some(b'-') | Some(b'_'))
        })
        .map(|f| f.number)
}

/// Why a fixed list cannot be used: a name twice, two libraries under one
/// number, or a number in the local range.
fn check_fixed(list: &[Fixed]) -> Result<(), String> {
    for (i, a) in list.iter().enumerate() {
        if a.number >= LOCAL_BASE {
            return Err(format!("{} {} is in the local range", a.number, a.name));
        }
        for b in &list[i + 1..] {
            if a.name.eq_ignore_ascii_case(&b.name) {
                return Err(format!("{} is listed twice ({} and {})", a.name, a.number, b.number));
            }
            if a.number == b.number && a.library && b.library {
                return Err(format!(
                    "{} and {} both carry a shader library under {}",
                    a.name, b.name, a.number
                ));
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_bundled_list_has_no_duplicates() {
        check_fixed(fixed()).unwrap();
        assert!(fixed().len() > 10);
    }

    #[test]
    fn a_duplicate_fails_the_check() {
        let entry = |number, name: &str, library| Fixed {
            number,
            name: name.into(),
            library,
            named_by: String::new(),
        };
        assert!(check_fixed(&[entry(990, "MJOLNIRA", false), entry(990, "MJOLNIRB", false)]).is_ok());
        assert!(check_fixed(&[entry(988, "MJOLNIRA", true), entry(988, "MJOLNIRB", true)])
            .unwrap_err()
            .contains("988"));
        assert!(check_fixed(&[entry(980, "MJOLNIRA", false), entry(981, "mjolnira", true)])
            .unwrap_err()
            .contains("twice"));
        assert!(check_fixed(&[entry(LOCAL_BASE, "MJOLNIRA", false)]).is_err());
        assert!(parse_fixed("{\"fixed\": [{\"number\": 1}]}").is_err());
    }

    #[test]
    fn the_registration_container_is_on_the_list() {
        let reg = crate::maps::REG_CONTAINER;
        assert_eq!(fixed_number(reg), Some(996), "{reg}");
    }

    #[test]
    fn a_fixed_name_matches_only_whole() {
        assert_eq!(fixed_number("pakchunk988-MJOLNIRMAT-Windows"), Some(988));
        assert_eq!(fixed_number("pakchunk990-MJOLNIRFLAGB_P"), Some(990));
        assert_eq!(fixed_number("pakchunk995-MJOLNIRBOT-elite-heroic_P"), Some(995));
        assert_eq!(fixed_number("pakchunk996-mjolnirreg_P"), Some(996));
        // Another container under a fixed number, or a fixed name under
        // another number, takes a local number like anything else.
        assert_eq!(fixed_number("pakchunk988-MJOLNIRMATTEST_P"), None);
        assert_eq!(fixed_number("pakchunk996-MJOLNIRVCOLL-YOY_P"), None);
        assert_eq!(fixed_number("pakchunk989-MJOLNIRMAT-Windows"), None);
        assert_eq!(fixed_number("pakchunk968-MJOLNIRCOOK-TST_P"), None);
        assert_eq!(fixed_number("MJOLNIRMAT"), None);
    }

    #[test]
    fn later_wins_and_patches_fit_between() {
        assert_eq!(suffix(0), HUB_BASE);
        assert!(suffix(1) > suffix(0));
        assert!(suffix(0) + STEP - 1 < suffix(1), "three live updates fit");
        assert_eq!(suffix(usize::MAX), MAX_SUFFIX);
        assert_eq!(local_number(0), LOCAL_BASE);
        assert_eq!(local_number(41), LOCAL_BASE + 41);
    }

    #[test]
    fn numbers_split_off_the_front() {
        assert_eq!(split_number("pakchunk20001-MJOLNIRTST_P"), Some((20001, "-MJOLNIRTST_P")));
        assert_eq!(split_number("PAKCHUNK7"), Some((7, "")));
        assert_eq!(split_number("pakchunkX-MJOLNIR"), None);
        assert_eq!(split_number("pakchunk"), None);
        assert_eq!(split_number("MJOLNIRMAP-BGL_P"), None);
    }
}
