//! Re-encode a stock-cooked package's properties in the game's layout.
//!
//! An unversioned property block names its properties by schema slot, and
//! 343's engine numbers them differently from stock UE 5.5: it carries
//! backported fields (`PrimitiveComponent` has 110 properties, among them
//! 5.6's `FirstPersonPrimitiveType`), so a component cooked by a stock editor
//! is misread from the first shifted slot on, and its native data after the
//! properties is read from the wrong place (the landscape spike, 2026-10-11:
//! "this landscape does not contain cooked data"). This decodes each export
//! against the stock schema (`defs/ue/UE-5.5-stock.usmap`, written by the
//! editor's `WriteUsmap`) and encodes it again against the game's, matching
//! properties by name, nested structs included. A property the game does not
//! have, or has with another type, is dropped and reported; one only the game
//! has stays absent, which loads as its default. The native serialization
//! after the properties is kept as it is.

use crate::edit::export_class;
use crate::package::ZenPackage;
use crate::props::{self, Block, Val};
use crate::usmap::{PropType, Usmap};
use crate::zen::ScriptObjects;

/// A property's flat slot in `class` (supers included) and the schema entry
/// that owns it, with the element index inside a fixed array.
fn at(usmap: &Usmap, class: &str, slot: u16) -> Option<(String, PropType, u16)> {
    let mut current = usmap.structs.get(class)?;
    let mut rest = slot;
    loop {
        if rest < current.prop_count {
            let p = current.prop_at(rest)?;
            return Some((p.name.clone(), p.ty.clone(), rest - p.schema_index));
        }
        rest -= current.prop_count;
        current = usmap.structs.get(current.super_name.as_deref()?)?;
    }
}

/// The flat slot of the property named `name` in `class`, with its type and
/// fixed-array size.
fn slot_named(usmap: &Usmap, class: &str, name: &str) -> Option<(u16, PropType, u8)> {
    let mut base = 0u16;
    let mut current = usmap.structs.get(class);
    while let Some(s) = current {
        if let Some(p) = s.props.iter().find(|p| p.name == name) {
            return Some((base + p.schema_index, p.ty.clone(), p.array_dim));
        }
        base += s.prop_count;
        current = s.super_name.as_deref().and_then(|n| usmap.structs.get(n));
    }
    None
}

fn byte_like(t: &PropType) -> bool {
    matches!(t, PropType::Byte)
        || matches!(t, PropType::Enum(inner, _) if **inner == PropType::Byte)
}

fn compatible(a: &PropType, b: &PropType) -> bool {
    match (a, b) {
        (PropType::Array(x), PropType::Array(y)) | (PropType::Set(x), PropType::Set(y)) => {
            compatible(x, y)
        }
        (PropType::Map(k1, v1), PropType::Map(k2, v2)) => compatible(k1, k2) && compatible(v1, v2),
        (PropType::Enum(x, _), PropType::Enum(y, _)) => x == y,
        _ if byte_like(a) && byte_like(b) => true,
        _ => a == b,
    }
}

/// One value moved between layouts; a reflected struct inside is translated
/// in turn.
fn value(
    from: &Usmap,
    to: &Usmap,
    ty: &PropType,
    v: &Val,
    path: &str,
    notes: &mut Vec<String>,
) -> Val {
    match (ty, v) {
        (PropType::Struct(name), Val::Struct(b)) => {
            Val::Struct(block(from, to, name, name, b, path, notes))
        }
        (PropType::Array(inner), Val::Array(items)) => Val::Array(
            items
                .iter()
                .enumerate()
                .map(|(i, x)| value(from, to, inner, x, &format!("{path}[{i}]"), notes))
                .collect(),
        ),
        (PropType::Set(inner), Val::Set(items)) => Val::Set(
            items
                .iter()
                .enumerate()
                .map(|(i, x)| value(from, to, inner, x, &format!("{path}[{i}]"), notes))
                .collect(),
        ),
        (PropType::Map(kt, vt), Val::Map(pairs)) => Val::Map(
            pairs
                .iter()
                .enumerate()
                .map(|(i, (k, x))| {
                    (
                        value(from, to, kt, k, &format!("{path}{{{i}}}"), notes),
                        value(from, to, vt, x, &format!("{path}[{i}]"), notes),
                    )
                })
                .collect(),
        ),
        _ => v.clone(),
    }
}

/// `b`, decoded against `from_class` in `from`, as a block of `to_class` in
/// `to`.
pub fn block(
    from: &Usmap,
    to: &Usmap,
    from_class: &str,
    to_class: &str,
    b: &Block,
    path: &str,
    notes: &mut Vec<String>,
) -> Block {
    let mut out = Block::default();
    for (slot, v) in &b.values {
        let Some((name, ty, element)) = at(from, from_class, *slot) else {
            notes.push(format!(
                "{path}: stock slot {slot} has no property; dropped"
            ));
            continue;
        };
        let here = format!("{path}.{name}");
        match slot_named(to, to_class, &name) {
            Some((to_slot, to_ty, dim))
                if compatible(&ty, &to_ty) && element < dim.max(1) as u16 =>
            {
                out.set(to_slot + element, value(from, to, &ty, v, &here, notes));
            }
            Some((_, to_ty, _)) => notes.push(format!(
                "{here}: {ty:?} in stock, {to_ty:?} in the game; dropped"
            )),
            None => notes.push(format!("{here}: not in the game's layout; dropped")),
        }
    }
    out
}

/// Re-encode every export with a script class both layouts describe. Returns
/// one line per export, plus a line per dropped property.
pub fn package(
    pkg: &mut ZenPackage,
    from: &Usmap,
    to: &Usmap,
    scripts: &ScriptObjects,
) -> Result<Vec<String>, String> {
    let mut lines = Vec::new();
    for index in 0..pkg.export_map.len() {
        let Some(class) = export_class(pkg, scripts, index) else {
            lines.push(format!("export {index}: not a script class; kept"));
            continue;
        };
        if !from.structs.contains_key(&class) || !to.structs.contains_key(&class) {
            lines.push(format!(
                "export {index} {class}: missing from a layout; kept"
            ));
            continue;
        }
        let bytes = pkg
            .export_bytes(index)
            .ok_or("export out of range")?
            .to_vec();
        let (stock, used) = props::decode_prefix(from, &class, &bytes)
            .map_err(|e| format!("export {index} {class}: {e}"))?;
        let mut notes = Vec::new();
        let game = block(from, to, &class, &class, &stock, &class, &mut notes);
        let mut out = game
            .encode(to, &class)
            .map_err(|e| format!("export {index} {class}: {e}"))?;
        out.extend_from_slice(&bytes[used..]);
        lines.push(format!(
            "export {index} {class}: {} -> {} property bytes, {} native byte(s) kept",
            used,
            out.len() - (bytes.len() - used),
            bytes.len() - used
        ));
        lines.extend(notes.into_iter().map(|n| format!("  {n}")));
        pkg.set_export_bytes(index, out)
            .map_err(|e| e.to_string())?;
    }
    Ok(lines)
}
