//! Fields the engine recomputes when a tag loads.
//!
//! Tag definitions name these fields `runtime …` (or `runtime_…`): a rate
//! next to the authored time, a cosine next to the authored angle, a bounds
//! box next to the authored volume. The tools fill them when a tag is saved and
//! the game fills them again when it loads the tag, and the simulation reads
//! only the computed copy. Two consequences follow for an editor:
//!
//! - Editing a runtime field achieves nothing; the next load overwrites it.
//! - Changing the authored field it is derived from in a *running* game
//!   changes nothing either, because the sim goes on reading the runtime copy
//!   computed at load. The change takes effect once the tag loads again —
//!   a rebuilt or reinstalled tag, or a mission restart.
//!
//! Only value fields count as runtime fields. A `block`, `struct` or `array`
//! named `runtime …` is a container: the multiplayer globals' `runtime` block,
//! for one, holds authored data, and the fields inside any container carry
//! their own names and are judged by them.

/// Names the shipped definitions spell with the `runtime` prefix displaced.
/// `sruntime tructure design zone flags` is `runtime structure design zone
/// flags` with its first letter moved; it sits beside `runtime bsp zone flags`
/// in `scenario_zone_set_block`.
const MISSPELLED: &[&str] = &["sruntime tructure design zone flags"];

/// Structural types, never runtime fields themselves.
const CONTAINERS: &[&str] = &["block", "struct", "array"];

/// Whether a field of this name and type is recomputed by the engine at load.
///
/// The rule is the definition's own naming: the name starts with `runtime`
/// followed by a space or an underscore and more name. A bare `runtime` and
/// every container type are excluded — see the module docs.
pub fn is_runtime_field(name: &str, type_name: &str) -> bool {
    if CONTAINERS.contains(&type_name) {
        return false;
    }
    let name = name.trim();
    if MISSPELLED.contains(&name) {
        return true;
    }
    let lower = name.to_ascii_lowercase();
    match lower.strip_prefix("runtime") {
        Some(rest) => {
            (rest.starts_with(' ') || rest.starts_with('_')) && !rest[1..].trim().is_empty()
        }
        None => false,
    }
}

/// Words that name the *form* of a value rather than what it is about: an
/// authored `recharge time` becomes a runtime `recharge velocity`, a `maximum
/// aiming deviation` angle a runtime `aiming deviation cosines`. Dropped from
/// both names before they are compared.
const FORM_WORDS: &[&str] = &[
    "time", "rate", "velocity", "cosine", "cosines", "inverse", "maximum",
];

/// Pairs whose names share no words, stated outright. Each entry is a runtime
/// field's name and the path of its source relative to the struct holding the
/// runtime field; the path may reach into an inlined struct.
const STATED: &[(&str, &[&str])] = &[
    // weapon_barrels: the rate-of-fire ramps live in the inlined `firing`
    // struct, the error decay in `firing error`.
    (
        "runtime rate of fire acceleration rate",
        &["firing", "acceleration time"],
    ),
    (
        "runtime rate of fire deceleration rate",
        &["firing", "deceleration time"],
    ),
    (
        "runtime error deceleration rate",
        &["firing error", "deceleration time"],
    ),
    // character_physics_ground_struct: the slope limit becomes the minimum
    // ground normal, and each falloff/cutoff angle pair two coefficients.
    ("runtime_minimum_normal_k", &["maximum slope angle"]),
    ("runtime_downhill_k0", &["downhill falloff angle"]),
    ("runtime_downhill_k0", &["downhill cutoff angle"]),
    ("runtime_downhill_k1", &["downhill falloff angle"]),
    ("runtime_downhill_k1", &["downhill cutoff angle"]),
    ("runtime_uphill_k0", &["uphill falloff angle"]),
    ("runtime_uphill_k0", &["uphill cutoff angle"]),
    ("runtime_uphill_k1", &["uphill falloff angle"]),
    ("runtime_uphill_k1", &["uphill cutoff angle"]),
];

/// Real-valued types: every derived pair found is a real computed from a real
/// or an angle.
fn is_real(type_name: &str) -> bool {
    type_name.starts_with("real")
        || type_name.starts_with("angle")
        || type_name.starts_with("fraction")
}

/// The words a name is about, lowercased, with [`FORM_WORDS`] removed.
fn key(name: &str) -> Vec<String> {
    let mut words: Vec<String> = name
        .to_ascii_lowercase()
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|w| !w.is_empty() && !FORM_WORDS.contains(w))
        .map(str::to_string)
        .collect();
    words.sort();
    words.dedup();
    words
}

/// One field of a struct, as [`derived_pairs`] sees it.
#[derive(Debug, Clone)]
pub struct Member<'a> {
    /// Names from the struct down to the field: one name for a direct field,
    /// more for a field of an inlined struct (`["firing", "acceleration
    /// time"]`). Blocks and arrays are not descended into — their elements are
    /// structs of their own.
    pub path: Vec<&'a str>,
    pub type_name: &'a str,
}

/// Which fields feed which runtime fields, as `(source, runtime)` indices into
/// `members`.
///
/// The heuristic, deliberately narrow so it names only pairs it can stand
/// behind:
///
/// 1. Both fields are reals (`real…`, `angle…`, `fraction…`); the source is
///    not itself a runtime field.
/// 2. They sit in the same struct (same path up to the name), and their names
///    are the same once `runtime` is dropped from the one and the form words
///    `time`, `rate`, `velocity`, `cosine(s)`, `inverse` and `maximum` from
///    both — `crouch transition time` feeds `runtime crouch transition
///    velocity`, `turret holster time` feeds `runtime inverse turret holster
///    time`.
/// 3. Or the pair is one of the few stated outright ([`STATED`]), where the
///    names share nothing (`maximum slope angle` → `runtime_minimum_normal_k`)
///    or the source is in an inlined struct (`firing.acceleration time` →
///    `runtime rate of fire acceleration rate`).
///
/// Runtime fields with no source this finds — the biped's
/// `runtime_camera_height_velocity`, a projectile's `runtime acceleration
/// bound inverse`, trigger-volume sector bounds, and the node, material and
/// region indices — are read-only in the editor all the same; changing what
/// they derive from simply carries no warning.
pub fn derived_pairs(members: &[Member<'_>]) -> Vec<(usize, usize)> {
    let mut pairs = Vec::new();
    for (r, runtime) in members.iter().enumerate() {
        let Some((&name, parent)) = runtime.path.split_last() else {
            continue;
        };
        let name = name.trim();
        if !is_real(runtime.type_name) || !is_runtime_field(name, runtime.type_name) {
            continue;
        }
        let runtime_key = key(&name["runtime".len()..]);
        for (s, source) in members.iter().enumerate() {
            let Some((&source_name, source_parent)) = source.path.split_last() else {
                continue;
            };
            if s == r
                || !is_real(source.type_name)
                || is_runtime_field(source_name, source.type_name)
            {
                continue;
            }
            let by_name = source_parent == parent
                && !runtime_key.is_empty()
                && key(source_name) == runtime_key;
            let stated = STATED.iter().any(|(rt, rel)| {
                *rt == name
                    && source.path.len() == parent.len() + rel.len()
                    && source.path[..parent.len()] == *parent
                    && source.path[parent.len()..]
                        .iter()
                        .zip(rel.iter())
                        .all(|(a, b)| a.trim() == *b)
            });
            if by_name || stated {
                pairs.push((s, r));
            }
        }
    }
    pairs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_prefix_rule() {
        assert!(is_runtime_field(
            "runtime crouch transition velocity",
            "real"
        ));
        assert!(is_runtime_field("runtime_minimum_normal_k", "real"));
        assert!(is_runtime_field("runtime sector bounds x0", "real"));
        assert!(is_runtime_field(
            "runtime rounds inventory maximum",
            "short integer"
        ));
        assert!(is_runtime_field("runtime distance bounds", "real bounds"));
        assert!(is_runtime_field(
            "sruntime tructure design zone flags",
            "long block flags"
        ));
        // Containers, a bare `runtime`, and names that merely start alike.
        assert!(!is_runtime_field("runtime", "block"));
        assert!(!is_runtime_field("runtime nodes", "block"));
        assert!(!is_runtime_field(
            "runtime object placement (magnified skull)",
            "struct"
        ));
        assert!(!is_runtime_field("runtime", "real"));
        assert!(!is_runtime_field("runtimes", "real"));
        assert!(!is_runtime_field("crouch transition time", "real"));
    }

    fn members<'a>(fields: &[(&[&'a str], &'a str)]) -> Vec<Member<'a>> {
        fields
            .iter()
            .map(|(path, type_name)| Member {
                path: path.to_vec(),
                type_name,
            })
            .collect()
    }

    fn named(members: &[Member<'_>], pairs: &[(usize, usize)]) -> Vec<(String, String)> {
        pairs
            .iter()
            .map(|(s, r)| (members[*s].path.join("."), members[*r].path.join(".")))
            .collect()
    }

    #[test]
    fn names_pair_within_one_struct_only() {
        let m = members(&[
            (&["recharge time"], "real"),
            (&["runtime recharge velocity"], "real"),
            (&["inner", "recharge time"], "real"),
            (&["flags"], "long flags"),
            (&["runtime flags"], "long flags"),
        ]);
        assert_eq!(
            named(&m, &derived_pairs(&m)),
            vec![("recharge time".into(), "runtime recharge velocity".into())]
        );
    }

    #[test]
    fn stated_pairs_reach_into_inlined_structs() {
        let m = members(&[
            (&["firing", "acceleration time"], "real"),
            (&["firing", "deceleration time"], "real"),
            (&["firing error", "deceleration time"], "real"),
            (&["runtime rate of fire acceleration rate"], "real"),
            (&["runtime rate of fire deceleration rate"], "real"),
            (&["runtime error deceleration rate"], "real"),
        ]);
        assert_eq!(
            named(&m, &derived_pairs(&m)),
            vec![
                (
                    "firing.acceleration time".into(),
                    "runtime rate of fire acceleration rate".into()
                ),
                (
                    "firing.deceleration time".into(),
                    "runtime rate of fire deceleration rate".into()
                ),
                (
                    "firing error.deceleration time".into(),
                    "runtime error deceleration rate".into()
                ),
            ]
        );
    }
}
