//! A cloned vehicle actor on a skeleton of its own.
//!
//! The sim hands the animation Blueprint its node list while the game runs: one
//! local transform and one name per node. The pose node looks each name up in
//! the mesh's reference skeleton and skips what it does not find, so no bone
//! list is cooked into the Blueprint or the Skeleton. Any animation Blueprint
//! whose graph is that node alone therefore drives any skeleton, once its
//! target skeleton says so: [`clone_anim_blueprint`] makes that clone,
//! [`point_leader`] points an actor's leader at it, and [`orphans`] finds the
//! components that were attached to bones the new skeleton lacks.

use crate::edit;
use crate::package::{public_export_hash, NameBatch, ZenPackage};
use crate::props::{Block, Val};
use crate::usmap::Usmap;
use crate::zen::ScriptObjects;

const PACKAGE_IMPORT: u64 = 2;
/// Sound still plays from the root, and a Blueprint may address these by name.
const STAYS_WHEN_ORPHANED: &str = "HaloAudioTrackingComponent";

const SYNC_GRAPH: [&str; 4] = [
    "AnimGraphNode_BlamSyncPose",
    "AnimGraphNode_Root",
    "AnimGraphNode_StateMachine",
    "AnimGraphNode_StateResult",
];

fn swap(batch: &NameBatch, from: &str, to: &str) -> NameBatch {
    NameBatch::from_names(
        batch
            .names
            .iter()
            .map(|n| {
                if n.eq_ignore_ascii_case(from) {
                    to.to_string()
                } else {
                    n.clone()
                }
            })
            .collect(),
    )
}

fn leaf(path: &str) -> &str {
    path.rsplit('/').next().unwrap_or(path)
}

/// An export's path below its package, which its public hash is taken from.
fn export_path(pkg: &ZenPackage, index: usize, depth: usize) -> Result<String, String> {
    if depth > 32 {
        return Err("export outer cycle".into());
    }
    let e = pkg
        .export_map
        .get(index)
        .ok_or("export outer out of range")?;
    let name = pkg.mapped_name(e.name_index, e.name_number);
    if e.outer >> 62 == 0 {
        Ok(format!(
            "{}/{name}",
            export_path(pkg, e.outer as usize, depth + 1)?
        ))
    } else {
        Ok(name)
    }
}

/// Points every import of the package `from` at the same-shaped object of
/// `to`, by `(old object, new object)` pair. An import that is none of the
/// named objects is an error: it would dangle. Returns how many moved.
pub fn repoint(
    pkg: &mut ZenPackage,
    from: &str,
    to: &str,
    objects: &[(&str, &str)],
) -> Result<usize, String> {
    let index = pkg
        .imported_package_names
        .names
        .iter()
        .position(|n| n.eq_ignore_ascii_case(from))
        .ok_or_else(|| format!("{} does not import {from}", pkg.name()))?;
    let slots: Vec<usize> = pkg
        .import_map
        .iter()
        .filter(|i| **i >> 62 == PACKAGE_IMPORT && ((**i >> 32) & 0x3fff_ffff) as usize == index)
        .map(|i| (*i & 0xffff_ffff) as usize)
        .collect();
    for slot in &slots {
        let old = pkg.imported_public_export_hashes[*slot];
        let (_, new) = objects
            .iter()
            .find(|(o, _)| public_export_hash(o) == old)
            .ok_or_else(|| format!("{from}: import {slot} is none of the named objects"))?;
        pkg.imported_public_export_hashes[*slot] = public_export_hash(new);
    }
    pkg.imported_package_names = swap(&pkg.imported_package_names, from, to);
    pkg.names = swap(&pkg.names, from, to);
    Ok(slots.len())
}

/// Writes a package whose header may have grown, keeping the distance from the
/// header to CookedHeaderSize, which `ZenPackage::write` preserves verbatim.
pub fn finish(pkg: &mut ZenPackage, old_header: u32) -> Result<Vec<u8>, String> {
    let once = pkg.write();
    let new_header = header_of(&once)?;
    pkg.cooked_header_size = u32::try_from(
        i64::from(pkg.cooked_header_size) + i64::from(new_header) - i64::from(old_header),
    )
    .map_err(|_| "cooked header size overflow")?;
    Ok(pkg.write())
}

pub fn header_of(data: &[u8]) -> Result<u32, String> {
    let bytes = data.get(4..8).ok_or("package too short")?;
    Ok(u32::from_le_bytes(bytes.try_into().unwrap()))
}

/// Clones an animation Blueprint to `path` with `skeleton` as its target. The
/// donor's graph may hold only the nodes in `SYNC_GRAPH`, which name no bones:
/// a look-at node, say, would point at a bone of the skeleton it was built for.
pub fn clone_anim_blueprint(donor: &[u8], path: &str, skeleton: &str) -> Result<Vec<u8>, String> {
    let header = header_of(donor)?;
    let mut abp = ZenPackage::parse(donor).map_err(|e| e.to_string())?;
    if let Some(node) = abp
        .names
        .names
        .iter()
        .find(|n| n.starts_with("AnimGraphNode_") && !SYNC_GRAPH.contains(&n.as_str()))
    {
        return Err(format!("{}: {node} may name bones", abp.name()));
    }
    let [old_skeleton] = abp.imported_package_names.names.as_slice() else {
        return Err(format!(
            "{} imports {} packages, not just a skeleton",
            abp.name(),
            abp.imported_package_names.names.len()
        ));
    };
    let old_skeleton = old_skeleton.clone();
    let old_path = abp.name();
    let (old_leaf, new_leaf) = (leaf(&old_path).to_string(), leaf(path).to_string());
    let pairs = [
        (old_path.clone(), path.to_string()),
        (format!("{old_leaf}_C"), format!("{new_leaf}_C")),
        (
            format!("Default__{old_leaf}_C"),
            format!("Default__{new_leaf}_C"),
        ),
    ];
    for (from, to) in &pairs {
        abp.names = swap(&abp.names, from, to);
    }
    for i in 0..abp.export_map.len() {
        if abp.export_map[i].public_export_hash != 0 {
            abp.export_map[i].public_export_hash = public_export_hash(&export_path(&abp, i, 0)?);
        }
    }
    repoint(
        &mut abp,
        &old_skeleton,
        skeleton,
        &[(leaf(&old_skeleton), leaf(skeleton))],
    )?;
    let out = finish(&mut abp, header)?;
    let read = ZenPackage::parse(&out).map_err(|e| e.to_string())?;
    if read.name() != path {
        return Err("the clone did not read back".into());
    }
    Ok(out)
}

/// The package an object reference of `block` imports from.
fn imported_package(pkg: &ZenPackage, block: &Block, slot: u16) -> Result<String, String> {
    let Some(Val::Object(object)) = block.get(slot) else {
        return Err(format!("slot {slot} holds no object"));
    };
    let import = usize::try_from(-i64::from(*object) - 1).map_err(|_| "not an import")?;
    let target = *pkg.import_map.get(import).ok_or("import out of range")?;
    if target >> 62 != PACKAGE_IMPORT {
        return Err(format!("import {import} is not in a package"));
    }
    let package = ((target >> 32) & 0x3fff_ffff) as usize;
    pkg.imported_package_names
        .names
        .get(package)
        .cloned()
        .ok_or_else(|| "imported package out of range".to_string())
}

/// Points the actor's leader mesh at `mesh` and its animation at `anim`, and
/// every other user of those imports with them: the sync component names the
/// same animation class. Returns the imports moved.
pub fn point_leader(
    actor: &mut ZenPackage,
    usmap: &Usmap,
    scripts: &ScriptObjects,
    leader: usize,
    mesh: &str,
    anim: &str,
) -> Result<usize, String> {
    let e = edit::open_export(actor, usmap, scripts, leader)?;
    let slot = |field| {
        edit::slot_of(usmap, &e.class, field)
            .map(|s| s.0)
            .ok_or_else(|| format!("{} has no {field}", e.class))
    };
    let old_mesh = imported_package(actor, &e.block, slot("SkeletalMesh")?)?;
    let old_anim = imported_package(actor, &e.block, slot("AnimClass")?)?;
    let moved = repoint(actor, &old_mesh, mesh, &[(leaf(&old_mesh), leaf(mesh))])?;
    let (old_leaf, new_leaf) = (leaf(&old_anim), leaf(anim));
    let (old_c, new_c) = (format!("{old_leaf}_C"), format!("{new_leaf}_C"));
    let (old_d, new_d) = (format!("Default__{old_c}"), format!("Default__{new_c}"));
    Ok(moved
        + repoint(
            actor,
            &old_anim,
            anim,
            &[
                (old_c.as_str(), new_c.as_str()),
                (old_d.as_str(), new_d.as_str()),
            ],
        )?)
}

/// One component of the actor's construction script.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Component {
    /// Export index of its construction script node.
    pub node: usize,
    /// Export index of its template.
    pub template: usize,
    pub variable: String,
    /// The template's script class, when it has one.
    pub class: Option<String>,
    /// The bone or socket it hangs from, when it names one.
    pub attach: Option<String>,
    pub children: usize,
}

fn name_at(pkg: &ZenPackage, block: &Block, slot: Option<u16>) -> Option<String> {
    match block.get(slot?)? {
        Val::Name(n) => Some(pkg.mapped_name(n.index, n.number)).filter(|s| s != "None"),
        _ => None,
    }
}

/// Every node of the actor's construction script.
pub fn components(
    pkg: &ZenPackage,
    usmap: &Usmap,
    scripts: &ScriptObjects,
) -> Result<Vec<Component>, String> {
    const NODE: &str = "SCS_Node";
    let slot = |field| edit::slot_of(usmap, NODE, field).map(|s| s.0);
    let mut out = Vec::new();
    for node in 0..pkg.export_map.len() {
        if edit::export_class(pkg, scripts, node).as_deref() != Some(NODE) {
            continue;
        }
        let e = edit::open_export(pkg, usmap, scripts, node)?;
        let template = match slot("ComponentTemplate").and_then(|s| e.block.get(s)) {
            Some(Val::Object(o)) if *o > 0 => *o as usize - 1,
            _ => return Err(format!("export {node}: a node without a template")),
        };
        let children = match slot("ChildNodes").and_then(|s| e.block.get(s)) {
            Some(Val::Array(items)) => items.len(),
            _ => 0,
        };
        out.push(Component {
            node,
            template,
            variable: name_at(pkg, &e.block, slot("InternalVariableName"))
                .ok_or_else(|| format!("export {node}: a node without a name"))?,
            class: edit::export_class(pkg, scripts, template),
            attach: name_at(pkg, &e.block, slot("AttachToName")),
            children,
        });
    }
    Ok(out)
}

/// The components a skeleton of `bones` leaves with nothing to hang from, sound
/// excepted. A socket lookup that fails puts them on the mesh's root, so a light
/// or a landscape brush built for a bone would work from the wrong place.
pub fn orphans(all: &[Component], bones: &[String]) -> Vec<Component> {
    all.iter()
        .filter(|c| {
            c.attach
                .as_ref()
                .is_some_and(|a| !bones.iter().any(|b| b.eq_ignore_ascii_case(a)))
                && c.class.as_deref() != Some(STAYS_WHEN_ORPHANED)
        })
        .cloned()
        .collect()
}

/// Takes these components out of the construction script, so they are never
/// built. Their templates stay in the package, unreferenced; a Blueprint that
/// calls one finds an empty variable, which script steps over.
pub fn drop_components(
    pkg: &mut ZenPackage,
    usmap: &Usmap,
    scripts: &ScriptObjects,
    gone: &[Component],
) -> Result<(), String> {
    if let Some(c) = gone.iter().find(|c| c.children != 0) {
        return Err(format!("{} has children", c.variable));
    }
    let refs: Vec<i32> = gone.iter().map(|c| c.node as i32 + 1).collect();
    let holders = [
        ("SCS_Node", vec!["ChildNodes"]),
        ("SimpleConstructionScript", vec!["RootNodes", "AllNodes"]),
    ];
    let mut removed = 0;
    for index in 0..pkg.export_map.len() {
        let class = edit::export_class(pkg, scripts, index);
        let Some((class, fields)) = holders.iter().find(|h| class.as_deref() == Some(h.0)) else {
            continue;
        };
        let mut e = edit::open_export(pkg, usmap, scripts, index)?;
        let mut changed = false;
        for field in fields {
            let slot = edit::slot_of(usmap, class, field).ok_or("no such field")?.0;
            if let Some((_, Val::Array(items))) =
                e.block.values.iter_mut().find(|(s, _)| *s == slot)
            {
                let before = items.len();
                items.retain(|v| !matches!(v, Val::Object(o) if refs.contains(o)));
                changed |= items.len() != before;
                if *field != "AllNodes" {
                    removed += before - items.len();
                }
            }
        }
        if changed {
            edit::write_export(pkg, usmap, &e)?;
        }
    }
    if removed != gone.len() {
        return Err(format!(
            "{removed} of {} components had a parent",
            gone.len()
        ));
    }
    Ok(())
}

/// Turns a component off in place. Refused for classes the codec cannot write.
pub fn hide_component(
    pkg: &mut ZenPackage,
    usmap: &Usmap,
    scripts: &ScriptObjects,
    component: &Component,
) -> Result<(), String> {
    let mut e = edit::open_export(pkg, usmap, scripts, component.template)?;
    edit::set(
        usmap,
        &e.class.clone(),
        &mut pkg.names,
        &mut e.block,
        "bVisible",
        "false",
    )?;
    edit::write_export(pkg, usmap, &e)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn component(variable: &str, class: &str, attach: Option<&str>) -> Component {
        Component {
            node: 1,
            template: 2,
            variable: variable.into(),
            class: Some(class.into()),
            attach: attach.map(String::from),
            children: 0,
        }
    }

    #[test]
    fn an_orphan_hangs_from_a_missing_bone_and_is_not_sound() {
        let all = [
            component("lamp", "SpotLightComponent", Some("VFX_Headlight_L")),
            component("kept", "SpotLightComponent", Some("frame_hull")),
            component("engine", STAYS_WHEN_ORPHANED, Some("VFX_Engine")),
            component("root", "BoxComponent", None),
        ];
        let found = orphans(&all, &["frame_hull".to_string()]);
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].variable, "lamp");
    }

    #[test]
    fn a_leaf_is_the_last_path_part() {
        assert_eq!(leaf("/Game/A/B_C"), "B_C");
        assert_eq!(leaf("B_C"), "B_C");
    }

    fn shipped() -> Option<(Vec<ue_iostore::Container>, ScriptObjects, Usmap)> {
        let paks = std::env::var("HCE_PAKS").ok()?;
        let containers = ue_iostore::load_all(&paks).unwrap();
        let global = containers
            .iter()
            .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
            .unwrap();
        let chunk = global
            .chunks
            .iter()
            .find(|c| c.type_name() == "ScriptObjects")
            .unwrap();
        let scripts =
            ScriptObjects::parse(&ue_iostore::read_chunk(global, chunk, None, &[]).unwrap())
                .unwrap();
        static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");
        Some((containers, scripts, Usmap::parse(USMAP).unwrap()))
    }

    fn read(containers: &[ue_iostore::Container], name: &str) -> Vec<u8> {
        let suffix = format!("/{name}.uasset");
        let (c, i) = containers
            .iter()
            .find_map(|c| {
                c.files
                    .iter()
                    .find(|(p, _)| p.ends_with(&suffix))
                    .map(|(_, i)| (c, *i))
            })
            .unwrap();
        ue_iostore::read_chunk(c, &c.chunks[i], None, &[]).unwrap()
    }

    /// Against the installed game: the clone answers to its new name, imports
    /// only the new skeleton, and keeps every export's bytes.
    #[test]
    fn shipped_elevator_graph_clones_onto_another_skeleton() {
        let Some((containers, ..)) = shipped() else {
            return;
        };
        let donor = read(&containers, "ABP_B40_Elevator");
        let before = ZenPackage::parse(&donor).unwrap();
        let out = clone_anim_blueprint(
            &donor,
            "/Game/MJOLNIR/Vehicles/X/ABP_X",
            "/Game/MJOLNIR/Vehicles/X/SKEL_X",
        )
        .unwrap();
        let after = ZenPackage::parse(&out).unwrap();
        assert_eq!(after.name(), "/Game/MJOLNIR/Vehicles/X/ABP_X");
        assert_eq!(
            after.imported_package_names.names,
            ["/Game/MJOLNIR/Vehicles/X/SKEL_X"]
        );
        assert_eq!(
            after.imported_public_export_hashes,
            [public_export_hash("SKEL_X")]
        );
        assert_eq!(after.import_map, before.import_map);
        for i in 0..before.export_map.len() {
            assert_eq!(after.export_bytes(i), before.export_bytes(i));
        }
    }

    /// Against the installed game: the donor's graph holds no bone names, which
    /// is what lets one clone serve any skeleton; the Warthog's look-at graph,
    /// built for its own bones, is refused.
    #[test]
    fn shipped_elevator_graph_names_no_bones() {
        let Some((containers, ..)) = shipped() else {
            return;
        };
        let warthog = read(&containers, "ABP_Warthog_01");
        assert!(clone_anim_blueprint(&warthog, "/Game/X/ABP_X", "/Game/X/SKEL_X").is_err());
        let elevator = ZenPackage::parse(&read(&containers, "ABP_B40_Elevator")).unwrap();
        let skeleton = ZenPackage::parse(&read(&containers, "SKEL_B40_Elevator")).unwrap();
        for bone in ["elevator_world", "platform", "root"] {
            assert!(skeleton.names.names.iter().any(|n| n == bone));
            assert!(!elevator.names.names.iter().any(|n| n == bone));
        }
    }

    /// Against the installed game: dropped components leave every list, the
    /// rest stay, and the actor still reads back.
    #[test]
    fn shipped_warthog_loses_only_the_dropped_components() {
        let Some((containers, scripts, usmap)) = shipped() else {
            return;
        };
        let data = read(&containers, "BP_WarthogVehicleActor");
        let header = header_of(&data).unwrap();
        let mut pkg = ZenPackage::parse(&data).unwrap();
        let all = components(&pkg, &usmap, &scripts).unwrap();
        let gone = orphans(&all, &[]);
        assert!(!gone.is_empty() && gone.len() < all.len());
        drop_components(&mut pkg, &usmap, &scripts, &gone).unwrap();
        let read_back = ZenPackage::parse(&finish(&mut pkg, header).unwrap()).unwrap();
        for index in 0..read_back.export_map.len() {
            let class = edit::export_class(&read_back, &scripts, index);
            if matches!(
                class.as_deref(),
                Some("SCS_Node" | "SimpleConstructionScript")
            ) {
                let e = edit::open_export(&read_back, &usmap, &scripts, index).unwrap();
                for o in e.block.object_refs() {
                    assert!(!gone.iter().any(|c| c.node as i32 + 1 == o));
                }
            }
        }
    }
}
