//! Stop a cloned vehicle Blueprint playing its donor's engine audio, so the
//! CE vehicle's own sounds (mods/MJOLNIRLevelLoader/Scripts/vehicle_sounds.lua)
//! play alone. Everything else in its graph runs as before: `EngineOn` still
//! follows the seat, and wheels, impacts and EMP keep their sounds.
//!
//!   vehicle_mute <in.uasset> <out.uasset>
//!
//! In the ubergraph this jumps over the `PlaySound` of the engine loop and the
//! gear shift, and over the stop that follows. The stop has to go with the
//! start: its guard `IsTrackedSoundIdValid` pops the flow when no sound runs,
//! which would skip `EngineOn = false` and `Audio_StopAllWheelSFX` on leaving.
//!
//! A jump target is an in-memory offset, so nothing may move: a statement
//! becomes `EX_Jump` plus never-run padding the same size on disk and in
//! memory. An object constant is 5 on disk and 9 in memory, an instance
//! variable 17 and 9, a `nothing` 1 and 1. The loader walks those as it walks
//! any script, then the walk here checks that every later statement stayed put.
use std::error::Error;
use ue_asset::{
    kismet::{self, Names, Stmt},
    package::ZenPackage,
};

const EX_INSTANCE_VARIABLE: u8 = 0x01;
const EX_JUMP: u8 = 0x06;
const EX_NOTHING: u8 = 0x0b;
const EX_OBJECT_CONST: u8 = 0x20;
const PATH_LEN: usize = 17;

struct Text<'a>(&'a ZenPackage);

impl Names for Text<'_> {
    fn name(&self, index: u32, number: u32) -> String {
        self.0.mapped_name(index, number)
    }
    fn object(&self, index: i32) -> String {
        format!("object{index}")
    }
}

fn find(stmts: &[Stmt], text: &str) -> Result<usize, Box<dyn Error>> {
    let hits: Vec<usize> = (0..stmts.len())
        .filter(|&i| stmts[i].text.contains(text))
        .collect();
    match hits[..] {
        [i] => Ok(i),
        _ => Err(format!("{} statement(s) hold `{text}`, wanted 1", hits.len()).into()),
    }
}

/// An instance variable expression inside `code`, to pad with.
fn instance_variable(code: &[u8]) -> Option<&[u8]> {
    (0..code.len().saturating_sub(PATH_LEN)).find_map(|k| {
        let e = &code[k..k + PATH_LEN];
        (e[0] == EX_INSTANCE_VARIABLE
            && e[1..5] == 1i32.to_le_bytes()
            && kismet::memory_len(e).ok() == Some(9))
        .then_some(e)
    })
}

/// Statement `at` as a jump to `target`, the same size as it was.
fn jump_over(
    code: &mut [u8],
    stmts: &[Stmt],
    at: usize,
    target: u32,
) -> Result<(), Box<dyn Error>> {
    let range = stmts[at].range.clone();
    let memory = (stmts[at + 1].offset - stmts[at].offset) as i64 - 5;
    let disk = range.len() as i64 - 5;
    let more = disk - memory;
    if more % 4 != 0 {
        return Err(format!("statement at {}: {more} left to balance", stmts[at].offset).into());
    }
    let (paths, objects) = if more >= 0 {
        ((more + 4) / 8, (more % 8) / 4)
    } else {
        (0, -more / 4)
    };
    let nothings = memory - 9 * (paths + objects);
    if nothings < 0 {
        return Err(format!("statement at {} is too small to pad", stmts[at].offset).into());
    }
    let mut out = vec![EX_JUMP];
    out.extend_from_slice(&target.to_le_bytes());
    if paths > 0 {
        let path = instance_variable(&code[range.clone()])
            .ok_or("no instance variable to pad with")?
            .to_vec();
        for _ in 0..paths {
            out.extend_from_slice(&path);
        }
    }
    for _ in 0..objects {
        out.push(EX_OBJECT_CONST);
        out.extend_from_slice(&0i32.to_le_bytes());
    }
    out.resize(out.len() + nothings as usize, EX_NOTHING);
    if out.len() != range.len() {
        return Err("padding came out the wrong size".into());
    }
    code[range].copy_from_slice(&out);
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let [input, output] = &a[..] else {
        return Err("vehicle_mute <in.uasset> <out.uasset>".into());
    };
    let mut pkg = ZenPackage::parse(&std::fs::read(input)?)?;
    let index = (0..pkg.export_map.len())
        .find(|&i| {
            let e = &pkg.export_map[i];
            pkg.mapped_name(e.name_index, e.name_number)
                .starts_with("ExecuteUbergraph_")
        })
        .ok_or("no ubergraph")?;
    let mut bytes = pkg.export_bytes(index).ok_or("export")?.to_vec();
    let before = kismet::script(&bytes, &Text(&pkg))?;
    let stmts = &before.stmts;
    let (start, end) = (before.start, before.end);

    // Imported functions print as numbers here: the variables say which is which.
    let engine = find(stmts, "(inst:SoundVariant_EngineLoop,")?;
    let gear = find(stmts, "(inst:SoundVariant_GearShift,")?;
    let guard = find(stmts, "CallFunc_IsTrackedSoundIdValid_ReturnValue = ")?;
    let stop = guard
        + 1
        + find(&stmts[guard + 1..], "(inst:SoundID_EngineLoop)")?;
    let code = &mut bytes[start..end];
    jump_over(code, stmts, engine, stmts[engine + 1].offset)?;
    jump_over(code, stmts, gear, stmts[gear + 1].offset)?;
    jump_over(code, stmts, guard, stmts[stop + 1].offset)?;

    let after = kismet::script(&bytes, &Text(&pkg))?;
    if after.memory_size != before.memory_size {
        return Err("the script changed size in memory".into());
    }
    // Every statement but the three keeps its offset and its text.
    for (i, s) in stmts.iter().enumerate() {
        if [engine, gear, guard].contains(&i) {
            continue;
        }
        if !after
            .stmts
            .iter()
            .any(|t| t.offset == s.offset && t.text == s.text)
        {
            return Err(format!("statement at {} moved: {}", s.offset, s.text).into());
        }
    }
    for i in [engine, gear, guard] {
        let s = after
            .stmts
            .iter()
            .find(|s| s.offset == stmts[i].offset)
            .ok_or("patched statement gone")?;
        println!(
            "{:6}: {}  (was {} bytes)",
            s.offset,
            s.text,
            stmts[i].range.len()
        );
    }
    pkg.set_export_bytes(index, bytes)?;
    let data = pkg.write();
    ZenPackage::parse(&data)?;
    std::fs::write(output, data)?;
    Ok(())
}
