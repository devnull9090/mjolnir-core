//! Editing one property of a cooked package's export, by path.
//!
//! An export's serial bytes are its unversioned property block followed by
//! whatever its class serializes natively (a material instance's static
//! parameters, a component's cached bounds). [`open_export`] splits the two
//! with the lossless [`crate::props`] decoder; [`set`] changes a value the
//! path names; [`write_export`] puts the block back in front of the untouched
//! tail and re-lays the package.
//!
//! Paths read like the property tree: `ScalarParameterValues[1].ParameterValue`,
//! `RuntimeRegions{head}.Permutations{default}.SkeletalMeshes[0].Asset`. A
//! `[n]` indexes an array, set, or the n-th pair of a map; `{key}` finds a map
//! pair by its key's text.
//!
//! What can be set: numbers, bools, names, strings, enums (by name or
//! number), soft object paths (`/Game/Pkg.Asset[:sub]`), and the native
//! vector-like structs as comma lists. Object references are not: pointing a
//! property at another package needs import-map surgery this foundation
//! does not do.

use crate::package::{NameBatch, ZenPackage};
use crate::props::{self, Block, Name, Val};
use crate::usmap::{PropType, Usmap};
use crate::zen::{ObjectIndex, ScriptObjects};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Segment {
    Field(String),
    Index(usize),
    Key(String),
}

/// `A.B[2].C{key}` into segments. Names may carry `\.`, `\[` and `\{`.
pub fn parse_path(path: &str) -> Result<Vec<Segment>, String> {
    let mut out = Vec::new();
    let mut field = String::new();
    let mut chars = path.chars().peekable();
    let flush = |field: &mut String, out: &mut Vec<Segment>| {
        if !field.is_empty() {
            out.push(Segment::Field(std::mem::take(field)));
        }
    };
    while let Some(c) = chars.next() {
        match c {
            '\\' => {
                if let Some(n) = chars.next() {
                    field.push(n);
                }
            }
            '.' => flush(&mut field, &mut out),
            '[' => {
                flush(&mut field, &mut out);
                let mut digits = String::new();
                for n in chars.by_ref() {
                    if n == ']' {
                        break;
                    }
                    digits.push(n);
                }
                let i: usize = digits
                    .trim()
                    .parse()
                    .map_err(|_| format!("{path}: `[{digits}]` is not an index"))?;
                out.push(Segment::Index(i));
            }
            '{' => {
                flush(&mut field, &mut out);
                let mut key = String::new();
                for n in chars.by_ref() {
                    if n == '}' {
                        break;
                    }
                    key.push(n);
                }
                out.push(Segment::Key(key));
            }
            c => field.push(c),
        }
    }
    flush(&mut field, &mut out);
    if out.is_empty() {
        return Err("empty path".into());
    }
    Ok(out)
}

/// The script class leaf of an export, when its class is a script class.
pub fn export_class(pkg: &ZenPackage, scripts: &ScriptObjects, index: usize) -> Option<String> {
    let e = pkg.export_map.get(index)?;
    scripts.leaf(ObjectIndex(e.class)).map(|s| s.to_string())
}

/// One export opened for editing.
#[derive(Debug, Clone)]
pub struct ExportEdit {
    pub index: usize,
    pub class: String,
    pub block: Block,
    /// The class's native serialization after the properties (the guid guard
    /// included), kept verbatim.
    pub tail: Vec<u8>,
}

pub fn open_export(
    pkg: &ZenPackage,
    usmap: &Usmap,
    scripts: &ScriptObjects,
    index: usize,
) -> Result<ExportEdit, String> {
    let class = export_class(pkg, scripts, index).ok_or_else(|| {
        format!("export {index} has a Blueprint class, which the usmap does not describe")
    })?;
    let bytes = pkg
        .export_bytes(index)
        .ok_or_else(|| format!("export {index} out of range"))?;
    let (block, used) = props::decode_prefix(usmap, &class, bytes).map_err(|e| e.to_string())?;
    Ok(ExportEdit {
        index,
        class,
        block,
        tail: bytes[used..].to_vec(),
    })
}

/// Encode the block, append the tail, and put the export back.
pub fn write_export(pkg: &mut ZenPackage, usmap: &Usmap, edit: &ExportEdit) -> Result<(), String> {
    let mut bytes = edit
        .block
        .encode(usmap, &edit.class)
        .map_err(|e| e.to_string())?;
    bytes.extend_from_slice(&edit.tail);
    pkg.set_export_bytes(edit.index, bytes)
        .map_err(|e| e.to_string())
}

/// A property's schema slot within `class` (supers included), with its
/// type, by name; a fixed array's n-th element is `name[n]`.
fn slot_of(usmap: &Usmap, class: &str, name: &str) -> Option<(u16, PropType, u8)> {
    let total = usmap.total_slots(class);
    let mut slot = 0u16;
    while slot < total {
        if let Some((_, prop)) = usmap.resolve(class, slot) {
            if prop.name == name {
                return Some((slot, prop.ty.clone(), prop.array_dim));
            }
            slot += prop.array_dim.max(1) as u16;
        } else {
            slot += 1;
        }
    }
    None
}

fn name_text(names: &[String], n: Name) -> String {
    let base = names
        .get(n.index as usize)
        .cloned()
        .unwrap_or_else(|| format!("name#{}", n.index));
    if n.number != 0 {
        format!("{base}_{}", n.number - 1)
    } else {
        base
    }
}

/// A value as text, for display and for `{key}` matching.
pub fn value_text(names: &[String], ty: Option<&PropType>, v: &Val) -> String {
    match v {
        Val::Bool(b) => b.to_string(),
        Val::Byte(b) => b.to_string(),
        Val::Int8(i) => i.to_string(),
        Val::Int16(i) => i.to_string(),
        Val::UInt16(i) => i.to_string(),
        Val::Int(i) => i.to_string(),
        Val::UInt32(i) => i.to_string(),
        Val::Int64(i) => i.to_string(),
        Val::UInt64(i) => i.to_string(),
        Val::Float(f) => f.to_string(),
        Val::Double(f) => f.to_string(),
        Val::Name(n) => name_text(names, *n),
        Val::Object(i) => match *i {
            0 => "null".into(),
            i if i < 0 => format!("import {}", -i - 1),
            i => format!("export {}", i - 1),
        },
        Val::SoftObject {
            package,
            asset,
            sub,
        } => {
            let mut s = format!(
                "{}.{}",
                name_text(names, *package),
                name_text(names, *asset)
            );
            if !sub.is_empty() {
                s.push(':');
                s.push_str(sub);
            }
            s
        }
        Val::Str(s) => s.clone(),
        Val::Text(b) => format!("<text {} bytes>", b.len()),
        Val::Native(b) => native_text(ty, b),
        Val::Array(items) => format!("[{} item(s)]", items.len()),
        Val::Set(items) => format!("{{{} item(s)}}", items.len()),
        Val::Map(pairs) => format!("{{{} pair(s)}}", pairs.len()),
        Val::Struct(_) => "{…}".into(),
        Val::Zeroed => "0 (zeroed)".into(),
    }
}

fn native_text(ty: Option<&PropType>, b: &[u8]) -> String {
    let name = match ty {
        Some(PropType::Struct(n)) => n.as_str(),
        _ => "",
    };
    let doubles = |n: usize| -> Option<String> {
        (b.len() == n * 8).then(|| {
            b.chunks_exact(8)
                .map(|c| f64::from_le_bytes(c.try_into().unwrap()).to_string())
                .collect::<Vec<_>>()
                .join(",")
        })
    };
    let floats = |n: usize| -> Option<String> {
        (b.len() == n * 4).then(|| {
            b.chunks_exact(4)
                .map(|c| f32::from_le_bytes(c.try_into().unwrap()).to_string())
                .collect::<Vec<_>>()
                .join(",")
        })
    };
    let hex = || b.iter().map(|x| format!("{x:02x}")).collect::<String>();
    match name {
        "Vector" | "Rotator" => doubles(3),
        "Vector2D" => doubles(2),
        "Vector4" | "Quat" | "Plane" => doubles(4),
        "Vector3f" => floats(3),
        "Vector2f" => floats(2),
        "LinearColor" | "Vector4f" | "Quat4f" => floats(4),
        "Color" => Some(format!("{},{},{},{}", b[0], b[1], b[2], b[3])),
        _ => None,
    }
    .unwrap_or_else(hex)
}

/// One row of a flattened block.
#[derive(Debug, Clone)]
pub struct Row {
    pub path: String,
    pub ty: String,
    pub value: String,
}

/// Every leaf of the block as `(path, type, value)` rows, in slot order.
pub fn describe(usmap: &Usmap, class: &str, names: &[String], block: &Block) -> Vec<Row> {
    let mut rows = Vec::new();
    describe_block(usmap, class, names, block, "", &mut rows);
    rows
}

fn describe_block(
    usmap: &Usmap,
    class: &str,
    names: &[String],
    block: &Block,
    prefix: &str,
    rows: &mut Vec<Row>,
) {
    for (slot, v) in &block.values {
        let Some((_, prop)) = usmap.resolve(class, *slot) else {
            continue;
        };
        let name = if prop.array_dim > 1 {
            format!("{}[{}]", prop.name, slot - prop.schema_index)
        } else {
            prop.name.clone()
        };
        let path = if prefix.is_empty() {
            name
        } else {
            format!("{prefix}.{name}")
        };
        describe_value(usmap, names, &path, &prop.ty, v, rows);
    }
}

fn type_text(ty: &PropType) -> String {
    format!("{ty:?}")
}

fn describe_value(
    usmap: &Usmap,
    names: &[String],
    path: &str,
    ty: &PropType,
    v: &Val,
    rows: &mut Vec<Row>,
) {
    match (v, ty) {
        (Val::Struct(b), PropType::Struct(name)) => {
            describe_block(usmap, name, names, b, path, rows)
        }
        (Val::Array(items), PropType::Array(inner)) | (Val::Set(items), PropType::Set(inner)) => {
            rows.push(Row {
                path: path.to_string(),
                ty: type_text(ty),
                value: value_text(names, Some(ty), v),
            });
            for (i, item) in items.iter().enumerate() {
                describe_value(usmap, names, &format!("{path}[{i}]"), inner, item, rows);
            }
        }
        (Val::Map(pairs), PropType::Map(key, value)) => {
            rows.push(Row {
                path: path.to_string(),
                ty: type_text(ty),
                value: value_text(names, Some(ty), v),
            });
            for (k, item) in pairs {
                let key_text = value_text(names, Some(key), k);
                describe_value(
                    usmap,
                    names,
                    &format!("{path}{{{key_text}}}"),
                    value,
                    item,
                    rows,
                );
            }
        }
        _ => rows.push(Row {
            path: path.to_string(),
            ty: type_text(ty),
            value: value_text(names, Some(ty), v),
        }),
    }
}

/// Walk `segments` from `class`'s block to the value they name; returns the
/// value, its type, and the struct class it sits in (for a further step).
fn locate<'b>(
    usmap: &Usmap,
    class: &str,
    names: &[String],
    block: &'b mut Block,
    segments: &[Segment],
    create: bool,
) -> Result<(&'b mut Val, PropType), String> {
    let Segment::Field(field) = &segments[0] else {
        return Err("a path starts with a property name".into());
    };
    let (slot, ty, _) =
        slot_of(usmap, class, field).ok_or_else(|| format!("{class} has no property {field}"))?;
    if block.get(slot).is_none() {
        if !create {
            return Err(format!("{field} is not present in this object"));
        }
        block.set(slot, Val::Zeroed);
    }
    let (_, value) = block.values.iter_mut().find(|(s, _)| *s == slot).unwrap();
    descend(usmap, names, value, ty, &segments[1..])
}

fn descend<'b>(
    usmap: &Usmap,
    names: &[String],
    value: &'b mut Val,
    ty: PropType,
    rest: &[Segment],
) -> Result<(&'b mut Val, PropType), String> {
    let Some(seg) = rest.first() else {
        return Ok((value, ty));
    };
    if matches!(value, Val::Zeroed) {
        return Err(
            "the value is zeroed (all defaults), so there is nothing inside it to address".into(),
        );
    }
    match (seg, value, ty) {
        (Segment::Field(_), Val::Struct(b), PropType::Struct(name)) => {
            locate(usmap, &name, names, b, rest, false)
        }
        (Segment::Index(i), Val::Array(items), PropType::Array(inner))
        | (Segment::Index(i), Val::Set(items), PropType::Set(inner)) => {
            let n = items.len();
            let item = items
                .get_mut(*i)
                .ok_or_else(|| format!("index {i} is past the {n} item(s)"))?;
            descend(usmap, names, item, *inner, &rest[1..])
        }
        (Segment::Index(i), Val::Map(pairs), PropType::Map(_, inner)) => {
            let n = pairs.len();
            let pair = pairs
                .get_mut(*i)
                .ok_or_else(|| format!("index {i} is past the {n} pair(s)"))?;
            descend(usmap, names, &mut pair.1, *inner, &rest[1..])
        }
        (Segment::Key(k), Val::Map(pairs), PropType::Map(key, inner)) => {
            let pos = pairs
                .iter()
                .position(|(pk, _)| value_text(names, Some(&key), pk) == *k)
                .ok_or_else(|| format!("no pair with key {k:?}"))?;
            descend(usmap, names, &mut pairs[pos].1, *inner, &rest[1..])
        }
        (seg, _, ty) => Err(format!("{seg:?} does not apply to a {ty:?}")),
    }
}

/// Read the value at `path`.
pub fn get(
    usmap: &Usmap,
    class: &str,
    names: &[String],
    block: &Block,
    path: &str,
) -> Result<(Val, PropType), String> {
    let segments = parse_path(path)?;
    let mut copy = block.clone();
    let (v, ty) = locate(usmap, class, names, &mut copy, &segments, false)?;
    Ok((v.clone(), ty))
}

/// Set the value at `path` from `text`. Names the text introduces are
/// interned into the package's name batch.
pub fn set(
    usmap: &Usmap,
    class: &str,
    names: &mut NameBatch,
    block: &mut Block,
    path: &str,
    text: &str,
) -> Result<Val, String> {
    let segments = parse_path(path)?;
    let snapshot = names.names.clone();
    let (slot_value, ty) = locate(usmap, class, &snapshot, block, &segments, true)?;
    let new = parse_value(usmap, names, &ty, text)?;
    *slot_value = new.clone();
    Ok(new)
}

fn intern_name(names: &mut NameBatch, text: &str) -> Name {
    Name {
        index: names.intern(text),
        number: 0,
    }
}

fn parse_value(
    usmap: &Usmap,
    names: &mut NameBatch,
    ty: &PropType,
    text: &str,
) -> Result<Val, String> {
    let t = text.trim();
    let num = |what: &str| -> Result<i64, String> {
        let s = t.trim_start_matches('+');
        if let Some(h) = s.strip_prefix("0x") {
            i64::from_str_radix(h, 16).map_err(|_| format!("{t:?} is not a {what}"))
        } else {
            s.parse::<i64>()
                .map_err(|_| format!("{t:?} is not a {what}"))
        }
    };
    let list = |n: usize| -> Result<Vec<f64>, String> {
        let parts: Vec<f64> = t
            .split(',')
            .map(|p| {
                p.trim()
                    .parse::<f64>()
                    .map_err(|_| format!("{t:?}: {p:?} is not a number"))
            })
            .collect::<Result<_, _>>()?;
        if parts.len() != n {
            return Err(format!("{t:?}: expected {n} comma-separated numbers"));
        }
        Ok(parts)
    };
    Ok(match ty {
        PropType::Bool => match t.to_ascii_lowercase().as_str() {
            "true" | "1" | "yes" => Val::Bool(true),
            "false" | "0" | "no" => Val::Bool(false),
            _ => return Err(format!("{t:?} is not a bool")),
        },
        PropType::Byte => Val::Byte(num("byte")? as u8),
        PropType::Int8 => Val::Int8(num("int8")? as i8),
        PropType::Int16 => Val::Int16(num("int16")? as i16),
        PropType::UInt16 => Val::UInt16(num("uint16")? as u16),
        PropType::Int => Val::Int(num("int")? as i32),
        PropType::UInt32 => Val::UInt32(num("uint32")? as u32),
        PropType::Int64 => Val::Int64(num("int64")?),
        PropType::UInt64 => Val::UInt64(num("uint64")? as u64),
        PropType::Float => Val::Float(t.parse::<f32>().map_err(|_| format!("{t:?} is not a float"))?),
        PropType::Double => Val::Double(t.parse::<f64>().map_err(|_| format!("{t:?} is not a double"))?),
        PropType::Enum(inner, enum_name) => {
            // By entry name (`Opaque` or `EBlendMode::Opaque`) or by number.
            let leaf = t.rsplit("::").next().unwrap_or(t);
            let by_name = usmap.enums.get(enum_name).and_then(|entries| {
                entries
                    .iter()
                    .find(|(_, n)| n == leaf || n.rsplit("::").next() == Some(leaf))
                    .map(|(v, _)| *v)
            });
            let value = match by_name {
                Some(v) => v,
                None => num(&format!("value of {enum_name}"))?,
            };
            parse_value(usmap, names, inner, &value.to_string())?
        }
        PropType::Name => Val::Name(intern_name(names, t)),
        PropType::Str => Val::Str(t.to_string()),
        PropType::SoftObject | PropType::AssetObject => soft_path(names, t)?,
        PropType::Struct(name) => match name.as_str() {
            "SoftObjectPath" | "SoftClassPath" => soft_path(names, t)?,
            "Vector" | "Rotator" => Val::Native(list(3)?.iter().flat_map(|v| v.to_le_bytes()).collect()),
            "Vector2D" => Val::Native(list(2)?.iter().flat_map(|v| v.to_le_bytes()).collect()),
            "Vector4" | "Quat" | "Plane" => Val::Native(list(4)?.iter().flat_map(|v| v.to_le_bytes()).collect()),
            "Vector3f" => Val::Native(list(3)?.iter().flat_map(|v| (*v as f32).to_le_bytes()).collect()),
            "Vector2f" => Val::Native(list(2)?.iter().flat_map(|v| (*v as f32).to_le_bytes()).collect()),
            "LinearColor" | "Vector4f" | "Quat4f" => {
                Val::Native(list(4)?.iter().flat_map(|v| (*v as f32).to_le_bytes()).collect())
            }
            "Color" => Val::Native(list(4)?.iter().map(|v| *v as u8).collect()),
            "Guid" => {
                let hex: String = t.chars().filter(|c| c.is_ascii_hexdigit()).collect();
                if hex.len() != 32 {
                    return Err(format!("{t:?} is not a 32-digit guid"));
                }
                Val::Native((0..16).map(|i| u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16).unwrap()).collect())
            }
            _ => return Err(format!("a {name} struct is set field by field, not as one value")),
        },
        PropType::Object | PropType::Interface | PropType::WeakObject => {
            return Err("an object reference points into the import map; retargeting it needs import surgery, which this does not do".into())
        }
        other => return Err(format!("{other:?} cannot be set from text")),
    })
}

fn soft_path(names: &mut NameBatch, t: &str) -> Result<Val, String> {
    let (top, sub) = match t.split_once(':') {
        Some((a, b)) => (a, b.to_string()),
        None => (t, String::new()),
    };
    let (package, asset) = top
        .rsplit_once('.')
        .ok_or_else(|| format!("{t:?} is not `/Path/Package.Asset`"))?;
    Ok(Val::SoftObject {
        package: intern_name(names, package),
        asset: intern_name(names, asset),
        sub,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paths_parse_fields_indexes_and_keys() {
        assert_eq!(
            parse_path("A.B[2].C{key one}.D").unwrap(),
            vec![
                Segment::Field("A".into()),
                Segment::Field("B".into()),
                Segment::Index(2),
                Segment::Field("C".into()),
                Segment::Key("key one".into()),
                Segment::Field("D".into()),
            ]
        );
        assert_eq!(
            parse_path("Odd\\.Name").unwrap(),
            vec![Segment::Field("Odd.Name".into())]
        );
        assert!(parse_path("A[x]").is_err());
        assert!(parse_path("").is_err());
    }

    #[test]
    fn native_values_parse_to_their_byte_size() {
        let usmap = Usmap::default();
        let mut names = NameBatch::from_names(Vec::new());
        let v = parse_value(
            &usmap,
            &mut names,
            &PropType::Struct("LinearColor".into()),
            "1, 0.5, 0, 1",
        )
        .unwrap();
        assert_eq!(
            v,
            Val::Native(
                [1.0f32, 0.5, 0.0, 1.0]
                    .iter()
                    .flat_map(|f| f.to_le_bytes())
                    .collect()
            )
        );
        let v = parse_value(
            &usmap,
            &mut names,
            &PropType::Struct("Vector".into()),
            "1,2,3",
        )
        .unwrap();
        assert!(matches!(v, Val::Native(ref b) if b.len() == 24));
        let v = parse_value(&usmap, &mut names, &PropType::SoftObject, "/Game/A/B.B:Sub").unwrap();
        assert!(matches!(v, Val::SoftObject { ref sub, .. } if sub == "Sub"));
        assert_eq!(names.names, vec!["/Game/A/B".to_string(), "B".to_string()]);
        assert!(parse_value(&usmap, &mut names, &PropType::Object, "x").is_err());
    }
}
