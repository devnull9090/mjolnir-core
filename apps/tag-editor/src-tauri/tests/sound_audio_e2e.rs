//! The sound-tag audio walk and bank-embedded extraction, proven against a
//! real installation rather than fixtures.
//!
//! Ignored by default because it needs Halo Campaign Evolved on disk:
//!
//! ```text
//! cargo test --test sound_audio_e2e -- --ignored --nocapture
//! ```
//!
//! What it proves, in one catalog pass:
//!
//! - a tag whose media ships only inside a bank (`sniper_ammo` — the preview
//!   walk finds nothing for it) resolves to embedded media, and the embedded
//!   bytes rebuild into a playable stream;
//! - a tag with loose media resolves those to catalog sound indices;
//! - across a broad sample, the exhaustive walk resolves far more tags than
//!   the single-hit preview walk it grew out of;
//! - the reverse-reference index round-trips through its disk cache: a
//!   second catalog over the same installation answers warm-fast.

use std::time::Instant;

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{bnk, decode, install, wwise_audio_for_tag, wwise_media_for_tag};

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn sound_tags_resolve_playable_media_against_the_shipped_catalog() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let oodle = found.oodle.unwrap_or_default();
    let c = Catalog::open(&paks, &oodle).expect("catalog open");

    // ── Embedded-only: the preview walk sees nothing, the audio walk must. ──
    let sniper = c
        .tags
        .iter()
        .position(|t| t.group == "sound" && t.short.ends_with("sniper_rifle/sniper_ammo"))
        .expect("sniper_ammo tag missing");
    assert!(
        wwise_media_for_tag(&c, sniper).is_none(),
        "sniper_ammo grew loose media — update this test's premise"
    );
    let audio = wwise_audio_for_tag(&c, sniper).expect("audio walk");
    assert_eq!(audio.events, vec!["Play_WEP_SniperRifle_Ammo_Pickup"]);
    assert!(
        audio.media.len() >= 2,
        "the ammo-pickup event has variations; got {}",
        audio.media.len()
    );
    for hit in &audio.media {
        let bank = hit.bank.expect("sniper_ammo media should be bank-embedded");
        assert!(hit.sound.is_none());
        let bytes = c.read_sound(bank, None).expect("bank read");
        let wem = bnk::embedded(&bytes, hit.id).expect("media in the bank's DIDX");
        assert_eq!(Some(wem.len() as u64), hit.size);
        let out = decode::to_playable(wem).expect("embedded wem rebuilds");
        assert!(!out.bytes.is_empty());
    }
    println!(
        "sniper_ammo: {} embedded variation(s), all rebuild into playable streams",
        audio.media.len()
    );

    // ── Loose media resolves to catalog sounds the player can already open. ──
    let door = c
        .tags
        .iter()
        .position(|t| t.group.starts_with("sound") && t.short.ends_with("cov_prison_door_switch_off"))
        .expect("door switch tag missing");
    let audio = wwise_audio_for_tag(&c, door).expect("audio walk");
    assert!(!audio.media.is_empty(), "door switch resolved no media");
    assert!(
        audio.media.iter().all(|m| m.sound.is_some()),
        "door switch media should all ship loose"
    );

    // ── Breadth: the exhaustive walk beats the single-hit preview walk. ──
    let sample: Vec<usize> = c
        .tags
        .iter()
        .enumerate()
        .filter(|(_, t)| t.group.starts_with("sound"))
        .map(|(i, _)| i)
        .step_by(37)
        .take(120)
        .collect();
    let t0 = Instant::now();
    let preview_hits = sample.iter().filter(|&&i| wwise_media_for_tag(&c, i).is_some()).count();
    let full_hits = sample
        .iter()
        .filter(|&&i| wwise_audio_for_tag(&c, i).map(|a| !a.media.is_empty()).unwrap_or(false))
        .count();
    println!(
        "sample of {}: preview walk resolves {preview_hits}, audio walk {full_hits} ({:?})",
        sample.len(),
        t0.elapsed()
    );
    assert!(full_hits >= preview_hits, "the exhaustive walk lost tags the preview finds");
    assert!(
        full_hits * 100 >= sample.len() * 70,
        "under 70% of sampled sound tags resolve; the survey said ~89% should"
    );
}

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn reverse_ref_index_roundtrips_through_the_disk_cache() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let oodle = found.oodle.unwrap_or_default();

    let c = Catalog::open(&paks, &oodle).expect("catalog open");
    let target = c
        .tags
        .iter()
        .position(|t| t.group == "sound" && t.short.ends_with("sniper_rifle/sniper_ammo"))
        .expect("sniper_ammo tag missing");
    let t0 = Instant::now();
    let rows = c.referencing(target, 500).expect("reverse lookup");
    let first = t0.elapsed();

    // A second catalog is a new process as far as the OnceLock is concerned:
    // its only warm path is the disk cache.
    let c2 = Catalog::open(&paks, &oodle).expect("second catalog open");
    let t1 = Instant::now();
    let rows2 = c2.referencing(target, 500).expect("cached reverse lookup");
    let cached = t1.elapsed();
    println!("reverse index: built in {first:?}, from disk cache in {cached:?}");

    assert_eq!(
        rows.iter().map(|r| r.index).collect::<Vec<_>>(),
        rows2.iter().map(|r| r.index).collect::<Vec<_>>(),
        "the cached index answers differently from the built one"
    );
    assert!(
        cached.as_secs_f64() < first.as_secs_f64() / 4.0 || cached.as_millis() < 2000,
        "the disk cache ({cached:?}) is not meaningfully faster than the build ({first:?})"
    );
}
