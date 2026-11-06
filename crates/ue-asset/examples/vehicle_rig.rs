//! Put a cloned vehicle actor (vehicle_actor) on its own SkeletalMesh.
//!
//! vehicle_rig <paks> <actor.uasset> <leader export> <folder> <stem> <bones.json> <out dir>
//!             [--anim <donor leaf>] [--orphans drop|hide]
//!
//! Writes ABP_<stem> beside the actor and rewrites the actor in place: its
//! leader takes SK_<stem> and the clone, whose target is SKEL_<stem>. Components
//! that hung from a bone the skeleton lacks are dropped from the construction
//! script, or with `hide` turned off where the codec can. Prints one line for
//! each, and `package <path>=<file>` for package_add.
use std::error::Error;
use ue_asset::{edit, package::ZenPackage, rig};

const DONOR: &str = "ABP_B40_Elevator";

fn fail(s: impl Into<String>) -> Box<dyn Error> {
    s.into().into()
}

fn read_leaf(containers: &[ue_iostore::Container], leaf: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    let suffix = format!("/{leaf}.uasset");
    let (c, i) = containers
        .iter()
        .find_map(|c| {
            c.files
                .iter()
                .find(|(p, _)| p.ends_with(&suffix))
                .map(|(_, i)| (c, *i))
        })
        .ok_or_else(|| fail(format!("{leaf} is in no container")))?;
    Ok(ue_iostore::read_chunk(c, &c.chunks[i], None, &[])?)
}

fn main() -> Result<(), Box<dyn Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (fixed, options) = a.split_at(a.len().min(7));
    let [paks, actor, leader, folder, stem, bones, out] = fixed else {
        return Err(fail(
            "vehicle_rig <paks> <actor.uasset> <leader> <folder> <stem> <bones.json> <out dir> [--anim <leaf>] [--orphans drop|hide]",
        ));
    };
    let option = |name: &str| {
        options
            .iter()
            .position(|o| o == name)
            .and_then(|i| options.get(i + 1))
    };
    let donor = option("--anim").map_or(DONOR, String::as_str);
    let mode = option("--orphans").map_or("drop", String::as_str);
    if mode != "drop" && mode != "hide" {
        return Err(fail("--orphans takes drop or hide"));
    }
    let tree: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(bones)?)?;
    // What a component can hang from: the node bones and the light bones.
    let mut bones: Vec<String> = tree["bones"]
        .as_array()
        .ok_or("bones.json has no bones")?
        .iter()
        .filter_map(|b| b["bone"].as_str().map(String::from))
        .collect();
    bones.extend(
        tree["light_bones"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|s| s["name"].as_str().map(String::from)),
    );

    let containers = ue_iostore::load_all(paks)?;
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .ok_or("no global container")?;
    let sc = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .ok_or("no script objects")?;
    let scripts =
        ue_asset::zen::ScriptObjects::parse(&ue_iostore::read_chunk(global, sc, None, &[])?)?;
    let usmap =
        ue_asset::Usmap::parse(include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap"))?;

    let (abp, sk, skel) = (
        format!("{folder}/ABP_{stem}"),
        format!("{folder}/SK_{stem}"),
        format!("{folder}/SKEL_{stem}"),
    );
    let clone =
        rig::clone_anim_blueprint(&read_leaf(&containers, donor)?, &abp, &skel).map_err(fail)?;

    let data = std::fs::read(actor)?;
    let header = rig::header_of(&data).map_err(fail)?;
    let mut bp = ZenPackage::parse(&data)?;
    let index = leader.parse::<usize>()?;
    let moved = rig::point_leader(&mut bp, &usmap, &scripts, index, &sk, &abp).map_err(fail)?;
    println!("{}: {moved} import(s) moved to {sk} and {abp}", bp.name());

    let all = rig::components(&bp, &usmap, &scripts).map_err(fail)?;
    let orphans = rig::orphans(&all, &bones);
    for c in &orphans {
        let what = c.class.as_deref().unwrap_or("Blueprint component");
        let bone = c.attach.as_deref().unwrap_or("");
        if mode == "drop" {
            println!("dropped {} ({what}, on {bone})", c.variable);
        } else if let Err(e) = rig::hide_component(&mut bp, &usmap, &scripts, c) {
            println!("left in {} ({what}, on {bone}): {e}", c.variable);
        } else {
            println!("hidden {} ({what}, on {bone})", c.variable);
        }
    }
    if mode == "drop" {
        rig::drop_components(&mut bp, &usmap, &scripts, &orphans).map_err(fail)?;
    }
    for c in all
        .iter()
        .filter(|c| !orphans.iter().any(|o| o.node == c.node))
    {
        if c.attach
            .as_ref()
            .is_some_and(|a| !bones.iter().any(|b| b.eq_ignore_ascii_case(a)))
        {
            println!(
                "kept on the root {} (on {})",
                c.variable,
                c.attach.as_deref().unwrap_or("")
            );
        }
    }
    let bp_out = rig::finish(&mut bp, header).map_err(fail)?;

    let read = ZenPackage::parse(&bp_out)?;
    let before = ZenPackage::parse(&data)?;
    if read.import_map != before.import_map {
        return Err(fail("the actor did not read back"));
    }
    edit::open_export(&read, &usmap, &scripts, index)?;
    let file = format!("{out}/ABP_{stem}.uasset");
    std::fs::write(&file, clone)?;
    std::fs::write(actor, bp_out)?;
    println!("package {abp}={file}");
    Ok(())
}
