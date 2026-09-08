//! Wwise sound bank (`.bnk`) reading, enough to attribute media to events.
//!
//! Most of the library is never named by an event *package* — the cooked
//! `UAkAudioEvent` assets only list media for a fraction of it. The rest is
//! reachable through the bank's `HIRC` section, which holds the actual object
//! graph: events point at actions, actions at a container or a sound, and
//! every node names its parent.
//!
//! Walking that graph gives media-to-event edges keyed by Wwise's numeric IDs.
//! Turning those back into names needs the event names from the packages, via
//! [`event_id`]. See `docs/wwise_audio_format.md`.

use std::collections::HashMap;

/// Object types in `HIRC` that matter here.
const SOUND: u8 = 2;
const ACTION: u8 = 3;
const EVENT: u8 = 4;
/// Random/sequence, switch, actor-mixer and blend containers all carry a
/// parent pointer in the same place and are walked identically.
const CONTAINERS: [u8; 4] = [5, 6, 7, 9];

fn u32at(b: &[u8], o: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(o..o + 4)?.try_into().unwrap()))
}

/// The Wwise short ID of a name.
///
/// Wwise hashes object names with 32-bit FNV-1 over the lowercased name, which
/// is why banks and events are numbered rather than named on disk.
pub fn event_id(name: &str) -> u32 {
    let mut hash: u32 = 2_166_136_261;
    for b in name.as_bytes() {
        hash = hash.wrapping_mul(16_777_619);
        hash ^= b.to_ascii_lowercase() as u32;
    }
    hash
}

/// Offset of a node's parent pointer, given where its `NodeBaseParams` starts.
///
/// The parent sits eight bytes in, past the effect-override flags and the bus
/// id, unless the node overrides effects — then the effect records come first.
fn parent_offset(body: &[u8], base: usize) -> Option<usize> {
    let num_fx = *body.get(base + 1)? as usize;
    let fx = if num_fx > 0 { 1 + num_fx * 7 } else { 0 };
    Some(base + 8 + fx)
}

/// Where a node's `NodeBaseParams` begins, by object type.
///
/// A sound carries its source data first: id, plugin id, stream type, media
/// id, in-memory size and source bits.
fn node_base(kind: u8) -> Option<usize> {
    match kind {
        SOUND => Some(18),
        k if CONTAINERS.contains(&k) => Some(4),
        _ => None,
    }
}

/// One bank's media-to-event edges.
#[derive(Debug, Default)]
pub struct Bank {
    /// `(event id, media ids it can play)`.
    pub events: Vec<(u32, Vec<u32>)>,
    /// Every media id the bank references, event or not.
    pub media: Vec<u32>,
}

/// Parse a `.bnk`, returning what its `HIRC` says about media and events.
///
/// A bank without a `HIRC` section — some are pure data — yields an empty
/// result rather than an error.
pub fn parse(bnk: &[u8]) -> Bank {
    let mut at = 0;
    while at + 8 <= bnk.len() {
        let id = &bnk[at..at + 4];
        let Some(size) = u32at(bnk, at + 4).map(|s| s as usize) else {
            break;
        };
        if size == 0 || at + 8 + size > bnk.len() {
            break;
        }
        if id == b"HIRC" {
            return parse_hirc(&bnk[at + 8..at + 8 + size]);
        }
        at += 8 + size;
    }
    Bank::default()
}

fn parse_hirc(h: &[u8]) -> Bank {
    let Some(count) = u32at(h, 0) else {
        return Bank::default();
    };
    let mut at = 4;

    let mut parent: HashMap<u32, u32> = HashMap::new();
    // Sound object id to the media it plays.
    let mut sounds: Vec<(u32, u32)> = Vec::new();
    // Action id to the object it targets.
    let mut actions: HashMap<u32, u32> = HashMap::new();
    // Event id to the actions it fires.
    let mut events: Vec<(u32, Vec<u32>)> = Vec::new();

    for _ in 0..count {
        let Some(size) = u32at(h, at + 1).map(|s| s as usize) else {
            break;
        };
        let Some(kind) = h.get(at).copied() else { break };
        let end = at + 5 + size;
        let Some(body) = h.get(at + 5..end.min(h.len())) else {
            break;
        };
        at = end;

        let Some(id) = u32at(body, 0) else { continue };
        match kind {
            SOUND => {
                if let Some(media) = u32at(body, 9) {
                    sounds.push((id, media));
                }
            }
            ACTION => {
                // id, scope byte, action type byte, then the target.
                if let Some(target) = u32at(body, 6) {
                    actions.insert(id, target);
                }
            }
            EVENT => {
                // A leading byte counts the actions in current bank versions.
                let n = body.get(4).copied().unwrap_or(0) as usize;
                let list: Vec<u32> = (0..n).filter_map(|i| u32at(body, 5 + i * 4)).collect();
                if list.len() == n {
                    events.push((id, list));
                }
            }
            _ => {}
        }
        if let Some(base) = node_base(kind) {
            if let Some(p) = parent_offset(body, base).and_then(|o| u32at(body, o)) {
                if p != 0 {
                    parent.insert(id, p);
                }
            }
        }
    }

    // For each event, the objects its actions target; a sound belongs to the
    // event when any of its ancestors is one of them.
    let out = events
        .into_iter()
        .map(|(event, list)| {
            let targets: Vec<u32> = list.iter().filter_map(|a| actions.get(a).copied()).collect();
            let media = sounds
                .iter()
                .filter(|(sound, _)| reaches(*sound, &targets, &parent))
                .map(|(_, media)| *media)
                .collect();
            (event, media)
        })
        .filter(|(_, media): &(u32, Vec<u32>)| !media.is_empty())
        .collect();

    Bank {
        events: out,
        media: sounds.into_iter().map(|(_, m)| m).collect(),
    }
}

/// Whether a node or any of its ancestors is one of `targets`.
///
/// The walk is depth-capped: a malformed bank could otherwise describe a cycle.
fn reaches(mut node: u32, targets: &[u32], parent: &HashMap<u32, u32>) -> bool {
    for _ in 0..32 {
        if targets.contains(&node) {
            return true;
        }
        match parent.get(&node) {
            Some(next) => node = *next,
            None => return false,
        }
    }
    false
}

/// The media a bank carries in its own body, as `(media id, size in bytes)`.
///
/// A `DIDX` section is a run of `(id, offset, size)` triples; the offsets
/// point into the `DATA` section that follows. Banks without one stream all
/// their media from loose `.wem` files and return nothing here.
pub fn embedded_index(bnk: &[u8]) -> Vec<(u32, u32)> {
    didx(bnk)
        .map(|d| d.chunks_exact(12).filter_map(|e| Some((u32at(e, 0)?, u32at(e, 8)?))).collect())
        .unwrap_or_default()
}

/// The bytes of one embedded media file: a complete RIFF `.wem`, exactly what
/// a loose file would hold.
pub fn embedded(bnk: &[u8], media: u32) -> Option<&[u8]> {
    let d = didx(bnk)?;
    let entry = d.chunks_exact(12).find(|e| u32at(e, 0) == Some(media))?;
    let offset = u32at(entry, 4)? as usize;
    let size = u32at(entry, 8)? as usize;
    let data = section(bnk, b"DATA")?;
    data.get(offset..offset + size)
}

fn didx(bnk: &[u8]) -> Option<&[u8]> {
    section(bnk, b"DIDX")
}

/// The body of the first section with the given magic.
fn section<'a>(bnk: &'a [u8], magic: &[u8; 4]) -> Option<&'a [u8]> {
    let mut at = 0;
    while at + 8 <= bnk.len() {
        let size = u32at(bnk, at + 4)? as usize;
        if size == 0 || at + 8 + size > bnk.len() {
            return None;
        }
        if &bnk[at..at + 4] == magic {
            return Some(&bnk[at + 8..at + 8 + size]);
        }
        at += 8 + size;
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Assemble a HIRC object.
    fn object(kind: u8, body: Vec<u8>) -> Vec<u8> {
        let mut v = vec![kind];
        v.extend_from_slice(&(body.len() as u32).to_le_bytes());
        v.extend_from_slice(&body);
        v
    }

    /// A sound: id, plugin, stream type, media, size, bits, then node params.
    fn sound(id: u32, media: u32, parent: u32) -> Vec<u8> {
        let mut b = Vec::new();
        b.extend_from_slice(&id.to_le_bytes());
        b.extend_from_slice(&0u32.to_le_bytes()); // plugin id
        b.push(0); // stream type
        b.extend_from_slice(&media.to_le_bytes());
        b.extend_from_slice(&0u32.to_le_bytes()); // in-memory size
        b.push(0); // source bits
        // NodeBaseParams at 18: override flag, fx count, then six bytes to the
        // parent pointer at 26.
        b.push(0);
        b.push(0);
        b.extend_from_slice(&[0; 6]);
        b.extend_from_slice(&parent.to_le_bytes());
        b
    }

    fn container(id: u32, parent: u32) -> Vec<u8> {
        let mut b = id.to_le_bytes().to_vec();
        b.push(0);
        b.push(0);
        b.extend_from_slice(&[0; 6]);
        b.extend_from_slice(&parent.to_le_bytes());
        b
    }

    fn action(id: u32, target: u32) -> Vec<u8> {
        let mut b = id.to_le_bytes().to_vec();
        b.push(0); // scope
        b.push(1); // action type
        b.extend_from_slice(&target.to_le_bytes());
        b
    }

    fn event(id: u32, actions: &[u32]) -> Vec<u8> {
        let mut b = id.to_le_bytes().to_vec();
        b.push(actions.len() as u8);
        for a in actions {
            b.extend_from_slice(&a.to_le_bytes());
        }
        b
    }

    fn bank(objects: Vec<Vec<u8>>) -> Vec<u8> {
        let mut hirc = (objects.len() as u32).to_le_bytes().to_vec();
        for o in objects {
            hirc.extend_from_slice(&o);
        }
        let mut out = b"BKHD".to_vec();
        out.extend_from_slice(&8u32.to_le_bytes());
        out.extend_from_slice(&[0; 8]);
        out.extend_from_slice(b"HIRC");
        out.extend_from_slice(&(hirc.len() as u32).to_le_bytes());
        out.extend_from_slice(&hirc);
        out
    }

    #[test]
    fn wwise_hashes_names_with_fnv1_over_lowercase() {
        // Case must not matter: Wwise lowercases before hashing.
        assert_eq!(event_id("AMB_A10"), event_id("amb_a10"));
        assert_ne!(event_id("Play_Foo"), event_id("Play_Bar"));
        // FNV-1 of the empty string is the offset basis.
        assert_eq!(event_id(""), 2_166_136_261);
    }

    #[test]
    fn an_event_collects_media_from_a_container_of_sounds() {
        let b = bank(vec![
            object(7, container(100, 0)),     // actor-mixer
            object(5, container(200, 100)),   // random container under it
            object(SOUND, sound(300, 4001, 200)),
            object(SOUND, sound(301, 4002, 200)),
            object(ACTION, action(400, 200)),
            object(EVENT, event(500, &[400])),
        ]);
        let parsed = parse(&b);
        assert_eq!(parsed.events.len(), 1);
        let (id, mut media) = parsed.events[0].clone();
        media.sort();
        assert_eq!(id, 500);
        assert_eq!(media, vec![4001, 4002]);
        // Every media the bank mentions is reported, event or not.
        let mut all = parsed.media.clone();
        all.sort();
        assert_eq!(all, vec![4001, 4002]);
    }

    #[test]
    fn an_action_may_target_a_sound_directly() {
        let b = bank(vec![
            object(SOUND, sound(300, 4001, 0)),
            object(ACTION, action(400, 300)),
            object(EVENT, event(500, &[400])),
        ]);
        assert_eq!(parse(&b).events, vec![(500, vec![4001])]);
    }

    #[test]
    fn sounds_outside_the_event_are_not_attributed_to_it() {
        let b = bank(vec![
            object(5, container(200, 0)),
            object(SOUND, sound(300, 4001, 200)),
            // A second container the event never targets.
            object(5, container(201, 0)),
            object(SOUND, sound(301, 4002, 201)),
            object(ACTION, action(400, 200)),
            object(EVENT, event(500, &[400])),
        ]);
        assert_eq!(parse(&b).events, vec![(500, vec![4001])]);
    }

    #[test]
    fn a_bank_with_no_hierarchy_is_empty_not_an_error() {
        assert!(parse(b"").events.is_empty());
        assert!(parse(&[0u8; 32]).events.is_empty());
        // Header-only bank.
        let mut only_header = b"BKHD".to_vec();
        only_header.extend_from_slice(&8u32.to_le_bytes());
        only_header.extend_from_slice(&[0; 8]);
        assert!(parse(&only_header).events.is_empty());
    }

    #[test]
    fn a_parent_cycle_terminates() {
        let b = bank(vec![
            object(5, container(200, 201)),
            object(5, container(201, 200)),
            object(SOUND, sound(300, 4001, 200)),
            object(ACTION, action(400, 999)),
            object(EVENT, event(500, &[400])),
        ]);
        // The walk must end rather than spin; nothing reaches the target.
        assert!(parse(&b).events.is_empty());
    }

    #[test]
    fn effect_overrides_shift_the_parent_pointer() {
        // A node with two effects carries a bypass byte and two 7-byte records
        // before its parent pointer.
        let mut b = 300u32.to_le_bytes().to_vec();
        b.extend_from_slice(&0u32.to_le_bytes());
        b.push(0);
        b.extend_from_slice(&4001u32.to_le_bytes());
        b.extend_from_slice(&0u32.to_le_bytes());
        b.push(0);
        b.push(1); // overrides parent fx
        b.push(2); // two effects
        b.push(0); // bypass bits
        b.extend_from_slice(&[0; 14]); // two 7-byte fx records
        b.extend_from_slice(&[0; 6]);
        b.extend_from_slice(&200u32.to_le_bytes());
        let bank_bytes = bank(vec![
            object(5, container(200, 0)),
            object(SOUND, b),
            object(ACTION, action(400, 200)),
            object(EVENT, event(500, &[400])),
        ]);
        assert_eq!(parse(&bank_bytes).events, vec![(500, vec![4001])]);
    }

    /// A section as it sits in a bank file: magic, size, body.
    fn chunk(magic: &[u8; 4], body: &[u8]) -> Vec<u8> {
        let mut v = magic.to_vec();
        v.extend_from_slice(&(body.len() as u32).to_le_bytes());
        v.extend_from_slice(body);
        v
    }

    #[test]
    fn embedded_media_extracts_from_didx_and_data() {
        // Two media files: 7001 at offset 0, 7002 at offset 4.
        let mut didx = Vec::new();
        for (id, offset, size) in [(7001u32, 0u32, 4u32), (7002, 4, 3)] {
            didx.extend_from_slice(&id.to_le_bytes());
            didx.extend_from_slice(&offset.to_le_bytes());
            didx.extend_from_slice(&size.to_le_bytes());
        }
        let mut b = chunk(b"BKHD", &[0; 8]);
        b.extend(chunk(b"DIDX", &didx));
        b.extend(chunk(b"DATA", b"AAAABBB"));

        assert_eq!(embedded_index(&b), vec![(7001, 4), (7002, 3)]);
        assert_eq!(embedded(&b, 7001), Some(&b"AAAA"[..]));
        assert_eq!(embedded(&b, 7002), Some(&b"BBB"[..]));
        assert_eq!(embedded(&b, 7003), None);
        // A bank without a DIDX has nothing embedded.
        assert_eq!(embedded_index(&chunk(b"BKHD", &[0; 8])), Vec::new());
    }
}
