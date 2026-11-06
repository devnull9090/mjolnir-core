//! Run `Variant::validate` over `.mglo` files: the check a launcher makes before
//! it installs one (`check_mglo` in apps/launcher/src-tauri/src/hub.rs).
//!
//! `release-mods.yml` copies this file into a checkout of the newest released
//! launcher and runs it over the game types a mods tag just built, so it has to
//! compile against that launcher's copy of this crate as well as this one.
//! `Variant::validate` and its error's `Display` are all it may use
//! (docs/update_check.md, "A mods release waits for the launcher").
//!
//! Exits 0 when every file is accepted, 1 when any is refused, 2 when it could
//! not check them. Every file is checked, so one run names all the refusals.
//!
//! ```text
//! cargo run -p blam-megalo --example validate_mglo -- variants/*.mglo
//! ```

use std::process::ExitCode;

use blam_megalo::Variant;

fn main() -> ExitCode {
    let paths: Vec<String> = std::env::args().skip(1).collect();
    if paths.is_empty() {
        eprintln!("usage: validate_mglo <file.mglo>...");
        return ExitCode::from(2);
    }

    let mut refused = 0;
    for path in &paths {
        let bytes = match std::fs::read(path) {
            Ok(bytes) => bytes,
            Err(e) => {
                eprintln!("cannot read {path}: {e}");
                return ExitCode::from(2);
            }
        };
        match Variant::validate(&bytes) {
            Ok(()) => println!("ok {path}"),
            Err(e) => {
                println!("refused {path}: {e}");
                refused += 1;
            }
        }
    }

    println!("{refused} of {} refused", paths.len());
    if refused > 0 {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}
