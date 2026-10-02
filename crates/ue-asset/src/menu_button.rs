//! Add a button to a cooked menu widget, as new exports in its package.
//!
//! The main menu's buttons are designer instances in the widget's own package:
//! a button (a `WBP_MeteoriteStandaloneButtonDefault_C` with its label and
//! style), the container slot that holds it, a class variable of the button's
//! name, and a `ComponentDelegateBinding` row that binds its
//! `OnButtonBaseClicked` to a click function. The function stores the button
//! on the ubergraph frame and enters the ubergraph at its handler.
//!
//! [`add_menu_button`] copies all of that from an existing button (the
//! template, left as it is) and points the copy's click at a block appended to
//! the ubergraph. The block repeats a push the menu already makes
//! (`HaloUIManagerSubsystem.PushStreamableContentToLayerFullscreen`) with
//! another widget class, so the menu opens that screen itself.
//!
//! What has to stay consistent, all measured on CU4's `WBP_MainMenu`
//! (docs/multiplayer_menu.md):
//! - New exports go at the end of the export map, so no existing package
//!   index moves.
//! - The class variable goes last among the class's own properties, and the
//!   class default object's unversioned header moves its inherited values up
//!   one slot. A class's own slots come before its supers', so without that
//!   the CDO reads garbage and the game crashes when the menu loads.
//! - Each new export gets a dependency bundle like its template's, and its
//!   create and serialize commands sit beside the template's in the export
//!   bundle.
//! - The appended ubergraph block goes before `EX_EndOfScript`. Nothing earlier
//!   moves, so no jump or entry point changes.

use crate::edit::{open_export, slot_of, write_export};
use crate::kismet;
use crate::package::{public_export_hash, DependencyBundleHeader, ZenPackage};
use crate::props::{Block, Name, Val};
use crate::usmap::Usmap;
use crate::zen::{ObjectIndex, ObjectRef, ScriptObjects};

/// What to add.
#[derive(Debug, Clone)]
pub struct MenuButton<'a> {
    /// The new button's object and variable name, e.g. `MultiplayerButton`.
    pub name: &'a str,
    /// Its label, as culture-invariant text.
    pub label: &'a str,
    /// The existing button to copy; the new one goes right after it.
    pub template: &'a str,
    /// The widget class the click opens:
    /// `/Game/MJOLNIR/UI/WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C`.
    pub opens: &'a str,
    /// A substring of the class path in the existing push to copy, e.g.
    /// `WBP_CustomizationCategoryMenu`.
    pub push_like: &'a str,
}

/// Where everything went.
#[derive(Debug, Clone)]
pub struct Added {
    pub function: usize,
    pub function_name: String,
    pub slot: usize,
    pub button: usize,
    /// The ubergraph offset the click enters.
    pub entry: u32,
    /// The new button's index in the container.
    pub position: usize,
    /// The class variable's own-slot index.
    pub variable_slot: u32,
}

fn pidx(export: usize) -> i32 {
    export as i32 + 1
}

fn i32_at(b: &[u8], p: usize) -> i32 {
    i32::from_le_bytes(b[p..p + 4].try_into().unwrap())
}

fn u32_at(b: &[u8], p: usize) -> u32 {
    u32::from_le_bytes(b[p..p + 4].try_into().unwrap())
}

fn export_name(pkg: &ZenPackage, i: usize) -> String {
    let e = &pkg.export_map[i];
    pkg.mapped_name(e.name_index, e.name_number)
}

/// The one export with this name (and outer, when given).
fn export_named(pkg: &ZenPackage, name: &str, outer: Option<usize>) -> Result<usize, String> {
    let hits: Vec<usize> = (0..pkg.export_map.len())
        .filter(|&i| export_name(pkg, i) == name)
        .filter(|&i| outer.is_none_or(|o| pkg.export_map[i].outer == o as u64))
        .collect();
    match hits.as_slice() {
        [one] => Ok(*one),
        [] => Err(format!("no export named {name}")),
        _ => Err(format!("{} exports named {name}", hits.len())),
    }
}

fn name_is(pkg: &ZenPackage, v: Option<&Val>, want: &str) -> bool {
    matches!(v, Some(Val::Name(n)) if n.number == 0 && pkg.names.names.get(n.index as usize).is_some_and(|s| s == want))
}

fn slot(usmap: &Usmap, class: &str, prop: &str) -> Result<u16, String> {
    slot_of(usmap, class, prop)
        .map(|(s, _, _)| s)
        .ok_or_else(|| format!("{class} has no property {prop}"))
}

pub fn add_menu_button(
    pkg: &mut ZenPackage,
    usmap: &Usmap,
    scripts: &ScriptObjects,
    spec: &MenuButton<'_>,
) -> Result<Added, String> {
    let package = pkg.name();
    let leaf = package.rsplit('/').next().unwrap_or(&package).to_string();
    let class_name = format!("{leaf}_C");
    let class = export_named(pkg, &class_name, None)?;
    let uber = export_named(pkg, &format!("ExecuteUbergraph_{leaf}"), Some(class))?;
    let tree = export_named(pkg, "WidgetTree", Some(class))?;
    let template = export_named(pkg, spec.template, Some(tree))?;
    if export_named(pkg, spec.name, Some(tree)).is_ok() {
        return Err(format!("{package} already has a {}", spec.name));
    }
    let class_of = |pkg: &ZenPackage, i: usize| crate::edit::export_class(pkg, scripts, i);

    // The template's click binding, and through it its click function.
    let bindings = (0..pkg.export_map.len())
        .find(|&i| class_of(pkg, i).as_deref() == Some("ComponentDelegateBinding"))
        .ok_or("no ComponentDelegateBinding export")?;
    let mut bind_edit = open_export(pkg, usmap, scripts, bindings)?;
    let rows_slot = slot(
        usmap,
        "ComponentDelegateBinding",
        "ComponentDelegateBindings",
    )?;
    const ROW: &str = "BlueprintComponentDelegateBinding";
    let (s_component, s_delegate, s_function) = (
        slot(usmap, ROW, "ComponentPropertyName")?,
        slot(usmap, ROW, "DelegatePropertyName")?,
        slot(usmap, ROW, "FunctionNameToBind")?,
    );
    let Some(Val::Array(rows)) = bind_edit.block.get(rows_slot).cloned() else {
        return Err("ComponentDelegateBindings is not an array".into());
    };
    let template_row = rows
        .iter()
        .find_map(|r| match r {
            Val::Struct(b)
                if name_is(pkg, b.get(s_component), spec.template)
                    && name_is(pkg, b.get(s_delegate), "OnButtonBaseClicked") =>
            {
                Some(b.clone())
            }
            _ => None,
        })
        .ok_or_else(|| format!("{} has no OnButtonBaseClicked binding", spec.template))?;
    let Some(Val::Name(tf)) = template_row.get(s_function) else {
        return Err("binding row without a function".into());
    };
    let template_function_name = pkg.mapped_name(tf.index, tf.number);
    let template_function = export_named(pkg, &template_function_name, Some(class))?;

    // The template's container slot, and the container.
    let mut template_slot = None;
    for i in 0..pkg.export_map.len() {
        let Some(c) = class_of(pkg, i) else { continue };
        let Some((s_content, _, _)) = slot_of(usmap, &c, "Content") else {
            continue;
        };
        if c.ends_with("Slot") {
            let e = open_export(pkg, usmap, scripts, i)?;
            if e.block.get(s_content) == Some(&Val::Object(pidx(template))) {
                template_slot = Some((i, e));
                break;
            }
        }
    }
    let (template_slot, slot_edit) = template_slot.ok_or("no slot holds the template")?;
    let slot_class = slot_edit.class.clone();
    let Some(Val::Object(parent)) = slot_edit
        .block
        .get(slot(usmap, &slot_class, "Parent")?)
        .cloned()
    else {
        return Err("the template's slot has no parent".into());
    };
    let container = (parent - 1) as usize;
    let mut cont_edit = open_export(pkg, usmap, scripts, container)?;
    let s_slots = slot(usmap, &cont_edit.class, "Slots")?;
    let Some(Val::Array(mut slots)) = cont_edit.block.get(s_slots).cloned() else {
        return Err("the container has no Slots".into());
    };
    let position = slots
        .iter()
        .position(|v| *v == Val::Object(pidx(template_slot)))
        .ok_or("the container does not list the template's slot")?
        + 1;

    // Indices and names of what gets added.
    let n = pkg.export_map.len();
    let (new_function, new_slot, new_button) = (n, n + 1, n + 2);
    let function_name = template_function_name.replace(spec.template, spec.name);
    if function_name == template_function_name {
        return Err(format!(
            "the click function {template_function_name} is not named after its button"
        ));
    }
    let n_button = pkg.names.intern(spec.name);
    let n_function = pkg.names.intern(&function_name);
    let slot_name_index = pkg.export_map[template_slot].name_index;
    let slot_number = pkg
        .export_map
        .iter()
        .filter(|e| e.name_index == slot_name_index)
        .map(|e| e.name_number)
        .max()
        .unwrap_or(0)
        + 1;

    // The click function: the template's stub, owning its own parameter and
    // entering the ubergraph at the appended block.
    let ub = pkg.export_bytes(uber).unwrap().to_vec();
    let us = kismet::script(&ub, &kismet::Raw).map_err(|e| format!("ubergraph: {e}"))?;
    let end = us.stmts.last().unwrap().clone();
    let entry = end.offset;
    let mut function = pkg.export_bytes(template_function).unwrap().to_vec();
    let fs = kismet::script(&function, &kismet::Raw).map_err(|e| format!("click stub: {e}"))?;
    let texts: Vec<&str> = fs.stmts.iter().map(|s| s.text.as_str()).collect();
    if fs.stmts.len() != 4
        || !texts[0].starts_with("letpersistent ")
        || texts[2] != "return nothing"
        || texts[3] != "end"
    {
        return Err(format!(
            "the click stub is not the expected shape: {texts:?}"
        ));
    }
    let owner_at = fs.start + fs.stmts[0].range.end - 4;
    if i32_at(&function, owner_at) != pidx(template_function) {
        return Err("the click stub's parameter is not owned by the stub".into());
    }
    function[owner_at..owner_at + 4].copy_from_slice(&pidx(new_function).to_le_bytes());
    let call = fs.start + fs.stmts[1].range.start;
    if function[call] != kismet::EX_LOCAL_FINAL_FUNCTION
        || i32_at(&function, call + 1) != pidx(uber)
        || function[call + 5] != kismet::EX_INT_CONST
    {
        return Err("the click stub does not enter the ubergraph".into());
    }
    function[call + 6..call + 10].copy_from_slice(&(entry as i32).to_le_bytes());

    // The ubergraph: the push to copy, retargeted, before EX_EndOfScript.
    let code = &ub[us.start..us.end];
    let pushes: Vec<usize> = us
        .stmts
        .iter()
        .enumerate()
        .filter(|(_, s)| {
            let b = &code[s.range.clone()];
            b.windows(spec.push_like.len())
                .any(|w| w == spec.push_like.as_bytes())
        })
        .map(|(i, _)| i)
        .collect();
    let [push] = pushes.as_slice() else {
        return Err(format!(
            "{} statements mention {}",
            pushes.len(),
            spec.push_like
        ));
    };
    let push = *push;
    if push == 0 || code[us.stmts[push - 1].range.start] != 0x5f {
        return Err("the push is not preceded by its player controller".into());
    }
    let mut push_bytes = code[us.stmts[push].range.clone()].to_vec();
    let at = push_bytes
        .windows(6)
        .position(|w| w == b"/Game/")
        .ok_or("the push has no /Game/ class path")?;
    let len = push_bytes[at..]
        .iter()
        .position(|&c| c == 0)
        .ok_or("unterminated class path")?;
    push_bytes.splice(at..at + len, spec.opens.bytes());
    let mut block = code[us.stmts[push - 1].range.clone()].to_vec();
    block.extend_from_slice(&push_bytes);
    block.push(kismet::EX_POP_EXECUTION_FLOW);
    let mut new_code = code[..end.range.start].to_vec();
    new_code.extend_from_slice(&block);
    new_code.push(kismet::EX_END_OF_SCRIPT);
    let memory = us.memory_size + kismet::memory_len(&block).map_err(|e| e.to_string())?;
    let mut ub_new = ub[..us.start - 8].to_vec();
    ub_new.extend_from_slice(&memory.to_le_bytes());
    ub_new.extend_from_slice(&(new_code.len() as u32).to_le_bytes());
    ub_new.extend_from_slice(&new_code);
    ub_new.extend_from_slice(&ub[us.end..]);
    let check =
        kismet::script(&ub_new, &kismet::Raw).map_err(|e| format!("rewritten ubergraph: {e}"))?;
    if check.memory_size != memory || check.stmts[check.stmts.len() - 4].offset != entry {
        return Err("the rewritten ubergraph does not walk as planned".into());
    }

    // The button: the template with its own label and slot.
    let mut button = pkg.export_bytes(template).unwrap().to_vec();
    relabel(&mut button, pkg.names.names.len(), spec.label)?;
    replace_one(
        &mut button,
        &pidx(template_slot).to_le_bytes(),
        &pidx(new_slot).to_le_bytes(),
        "the button's slot",
    )?;

    // The slot: the template's, holding the new button.
    let mut slot_new = slot_edit.clone();
    slot_new.block.set(
        slot(usmap, &slot_class, "Content")?,
        Val::Object(pidx(new_button)),
    );

    // The container lists the new slot after the template's.
    slots.insert(position, Val::Object(pidx(new_slot)));
    cont_edit.block.set(s_slots, Val::Array(slots));

    // The binding row.
    let mut row: Block = template_row.clone();
    row.set(
        s_component,
        Val::Name(Name {
            index: n_button,
            number: 0,
        }),
    );
    row.set(
        s_function,
        Val::Name(Name {
            index: n_function,
            number: 0,
        }),
    );
    let mut rows = rows;
    rows.push(Val::Struct(row));
    bind_edit.block.set(rows_slot, Val::Array(rows));

    // The class: the variable, the function as a child and in FuncMap.
    let class_bytes = pkg.export_bytes(class).unwrap().to_vec();
    let class_edit = open_export(pkg, usmap, scripts, class)?;
    let head = class_bytes.len() - class_edit.tail.len();
    let (tail, variable_slot) = extend_class(
        &class_edit.tail,
        &pkg.names.names,
        spec.template,
        n_button,
        n_function,
        pidx(new_function),
    )?;
    let mut class_new = class_bytes[..head].to_vec();
    class_new.extend_from_slice(&tail);

    // The public export hash formula, checked on the template function.
    let template_hash = pkg.export_map[template_function].public_export_hash;
    let function_hash = ["", "/", "."]
        .iter()
        .find_map(|sep| {
            let key = |f: &str| {
                if sep.is_empty() {
                    f.to_string()
                } else {
                    format!("{class_name}{sep}{f}")
                }
            };
            (public_export_hash(&key(&template_function_name)) == template_hash)
                .then(|| public_export_hash(&key(&function_name)))
        })
        .ok_or("no public export hash formula matches the template function")?;

    // Write the changed exports.
    pkg.set_export_bytes(uber, ub_new)
        .map_err(|e| e.to_string())?;
    write_export(pkg, usmap, &cont_edit)?;
    write_export(pkg, usmap, &bind_edit)?;
    pkg.set_export_bytes(class, class_new)
        .map_err(|e| e.to_string())?;
    for i in 0..pkg.export_map.len() {
        if ObjectIndex(pkg.export_map[i].class).classify() == ObjectRef::Export(class) {
            let shifted = shift_unversioned(pkg.export_bytes(i).unwrap(), variable_slot)?;
            pkg.set_export_bytes(i, shifted)
                .map_err(|e| e.to_string())?;
        }
    }

    // Append the new exports.
    let slot_bytes = {
        let mut b = slot_new
            .block
            .encode(usmap, &slot_class)
            .map_err(|e| e.to_string())?;
        b.extend_from_slice(&slot_new.tail);
        b
    };
    let mut append = |src: usize, bytes: Vec<u8>, name: u32, number: u32, hash: u64| {
        let mut e = pkg.export_map[src];
        e.cooked_serial_offset = pkg.export_data.len() as u64;
        e.cooked_serial_size = bytes.len() as u64;
        e.name_index = name;
        e.name_number = number;
        e.public_export_hash = hash;
        pkg.export_data.extend_from_slice(&bytes);
        pkg.export_map.push(e);
    };
    append(template_function, function, n_function, 0, function_hash);
    append(template_slot, slot_bytes, slot_name_index, slot_number, 0);
    append(template, button, n_button, 0, 0);

    // Dependency bundles: each new export like its template, with the
    // template's own indices swapped for the new ones.
    let mut groups = bundle_groups(pkg);
    let swap = |g: &[Vec<i32>; 4], from: &[(usize, usize)]| {
        let mut g = g.clone();
        for v in g.iter_mut() {
            for x in v.iter_mut() {
                if let Some((_, to)) = from.iter().find(|(f, _)| pidx(*f) == *x) {
                    *x = pidx(*to);
                }
            }
        }
        g
    };
    let pairs = [
        (template_function, new_function),
        (template_slot, new_slot),
        (template, new_button),
    ];
    let g_function = swap(&groups[template_function], &pairs);
    let g_slot = swap(&groups[template_slot], &pairs);
    let g_button = swap(&groups[template], &pairs);
    groups[container][2].push(pidx(new_slot));
    groups[class][2].push(pidx(new_function));
    groups.extend([g_function, g_slot, g_button]);
    set_bundle_groups(pkg, &groups);

    // Export bundle order: beside each template's commands.
    for (src, new) in pairs {
        for command in [0u32, 1] {
            let at = pkg
                .export_bundle_entries
                .iter()
                .position(|e| *e == (src as u32, command))
                .ok_or("a template export is missing from the export bundle")?;
            pkg.export_bundle_entries
                .insert(at + 1, (new as u32, command));
        }
    }

    Ok(Added {
        function: new_function,
        function_name,
        slot: new_slot,
        button: new_button,
        entry,
        position,
        variable_slot,
    })
}

fn replace_one(b: &mut [u8], from: &[u8], to: &[u8], what: &str) -> Result<(), String> {
    let hits: Vec<usize> = (0..=b.len().saturating_sub(from.len()))
        .filter(|&i| &b[i..i + from.len()] == from)
        .collect();
    let [at] = hits.as_slice() else {
        return Err(format!("{what}: {} matches", hits.len()));
    };
    b[*at..*at + to.len()].copy_from_slice(to);
    Ok(())
}

/// Swap the button's string-table label (`FText` history 11: table name,
/// key) for culture-invariant text (history -1 with its string).
fn relabel(b: &mut Vec<u8>, name_count: usize, label: &str) -> Result<(), String> {
    let hits: Vec<(usize, usize)> = (0..b.len().saturating_sub(13))
        .filter_map(|p| {
            if b[p] != 0x0b || u32_at(b, p + 5) != 0 || u32_at(b, p + 1) as usize >= name_count {
                return None;
            }
            let len = i32_at(b, p + 9);
            if !(1..=256).contains(&len) {
                return None;
            }
            let s = p + 13;
            let e = s + len as usize;
            (e <= b.len()
                && b[e - 1] == 0
                && b[s..e - 1]
                    .iter()
                    .all(|c| c.is_ascii_graphic() || *c == b' '))
            .then_some((p, e))
        })
        .collect();
    let [(p, e)] = hits.as_slice() else {
        return Err(format!(
            "the template's label: {} string-table texts",
            hits.len()
        ));
    };
    let mut text = vec![0xff];
    text.extend_from_slice(&1u32.to_le_bytes());
    text.extend_from_slice(&(label.len() as i32 + 1).to_le_bytes());
    text.extend_from_slice(label.as_bytes());
    text.push(0);
    b.splice(*p..*e, text);
    Ok(())
}

/// One serialized `FField` (type name first): its length.
fn field_len(t: &[u8], at: usize, names: &[String]) -> Result<usize, String> {
    let ty = names
        .get(u32_at(t, at) as usize)
        .ok_or("a property type outside the name batch")?
        .as_str();
    // type, name, flags, then FProperty: ArrayDim, ElementSize, PropertyFlags,
    // RepIndex, RepNotifyFunc, BlueprintReplicationCondition.
    let base = 8 + 8 + 4 + 4 + 4 + 8 + 2 + 8 + 1;
    let p = at + base;
    Ok(base
        + match ty {
            "ObjectProperty"
            | "WeakObjectProperty"
            | "LazyObjectProperty"
            | "SoftObjectProperty"
            | "InterfaceProperty"
            | "StructProperty"
            | "ByteProperty"
            | "DelegateProperty"
            | "MulticastDelegateProperty"
            | "MulticastInlineDelegateProperty"
            | "MulticastSparseDelegateProperty" => 4,
            "ClassProperty" | "SoftClassProperty" | "FieldPathProperty" => 8,
            "BoolProperty" => 6,
            "EnumProperty" => 4 + field_len(t, p + 4, names)?,
            "ArrayProperty" | "SetProperty" | "OptionalProperty" => field_len(t, p, names)?,
            "MapProperty" => {
                let k = field_len(t, p, names)?;
                k + field_len(t, p + k, names)?
            }
            "IntProperty" | "Int8Property" | "Int16Property" | "Int64Property"
            | "UInt16Property" | "UInt32Property" | "UInt64Property" | "FloatProperty"
            | "DoubleProperty" | "StrProperty" | "NameProperty" | "TextProperty" => 0,
            other => return Err(format!("unhandled property type {other}")),
        })
}

/// A Blueprint class's native data after its properties: the guid guard,
/// SuperStruct, Children, ChildProperties, the script sizes, then FuncMap.
/// Adds the function to Children and FuncMap and a copy of the template's
/// variable, renamed, as the last property. Returns the new tail and the
/// variable's own-slot index.
fn extend_class(
    tail: &[u8],
    names: &[String],
    template: &str,
    variable: u32,
    function: u32,
    function_index: i32,
) -> Result<(Vec<u8>, u32), String> {
    if tail.len() < 12 || u32_at(tail, 0) != 0 {
        return Err("the class tail does not start with an empty guid guard".into());
    }
    let children_at = 8;
    let n_children = i32_at(tail, children_at) as usize;
    let props_at = children_at + 4 + 4 * n_children;
    let n_props = i32_at(tail, props_at) as usize;
    let mut at = props_at + 4;
    let mut own_slots = 0u32;
    let mut template_record = None;
    for _ in 0..n_props {
        let len = field_len(tail, at, names)?;
        let name = names.get(u32_at(tail, at + 8) as usize).map(String::as_str);
        if name == Some(template) && u32_at(tail, at + 12) == 0 {
            template_record = Some(at..at + len);
        }
        own_slots += i32_at(tail, at + 20).max(1) as u32;
        at += len;
    }
    let props_end = at;
    let record = template_record.ok_or_else(|| format!("the class has no {template} variable"))?;
    if u32_at(tail, props_end) != 0 || u32_at(tail, props_end + 4) != 0 {
        return Err("a class with script bytes".into());
    }
    let fm = props_end + 8;
    let n_fm = i32_at(tail, fm) as usize;
    if n_fm != n_children {
        return Err(format!(
            "FuncMap has {n_fm} entries for {n_children} children"
        ));
    }
    let fm_end = fm + 4 + 12 * n_fm;

    let mut out = tail[..children_at].to_vec();
    out.extend_from_slice(&((n_children + 1) as i32).to_le_bytes());
    out.extend_from_slice(&tail[children_at + 4..props_at]);
    out.extend_from_slice(&function_index.to_le_bytes());
    out.extend_from_slice(&((n_props + 1) as i32).to_le_bytes());
    out.extend_from_slice(&tail[props_at + 4..props_end]);
    let mut rec = tail[record].to_vec();
    rec[8..12].copy_from_slice(&variable.to_le_bytes());
    out.extend_from_slice(&rec);
    out.extend_from_slice(&tail[props_end..fm]);
    out.extend_from_slice(&((n_fm + 1) as i32).to_le_bytes());
    out.extend_from_slice(&tail[fm + 4..fm_end]);
    out.extend_from_slice(&function.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&function_index.to_le_bytes());
    out.extend_from_slice(&tail[fm_end..]);
    Ok((out, own_slots))
}

/// Re-encode an unversioned property header with every slot at or past `at`
/// moved up one, for a property inserted there. Value bytes are untouched.
pub fn shift_unversioned(b: &[u8], at: u32) -> Result<Vec<u8>, String> {
    let mut p = 0;
    let mut slot = 0u32;
    let mut values: Vec<(u32, bool)> = Vec::new(); // (slot, in a zero-mask fragment)
    let mut zero_count = 0usize;
    loop {
        let v = u16::from_le_bytes(
            b.get(p..p + 2)
                .ok_or("header ends early")?
                .try_into()
                .unwrap(),
        ) as u32;
        p += 2;
        slot += v & 0x7f;
        let zeros = v & 0x80 != 0;
        let n = v >> 9;
        for s in slot..slot + n {
            values.push((s, zeros));
        }
        if zeros {
            zero_count += n as usize;
        }
        slot += n;
        if v & 0x100 != 0 {
            break;
        }
    }
    let mask_len = match zero_count {
        0 => 0,
        1..=8 => 1,
        9..=16 => 2,
        n => 4 * n.div_ceil(32),
    };
    let mask = b.get(p..p + mask_len).ok_or("zero mask ends early")?;
    let body = &b[p + mask_len..];
    let mut zero = Vec::with_capacity(values.len());
    let mut bit = 0;
    for (_, flagged) in &values {
        if *flagged {
            zero.push(mask[bit / 8] >> (bit % 8) & 1 == 1);
            bit += 1;
        } else {
            zero.push(false);
        }
    }
    if values.is_empty() {
        return Ok(b.to_vec());
    }
    // Fragments of consecutive slots (at most 127 values each).
    let mut frags: Vec<(u32, Vec<bool>)> = Vec::new();
    for ((s, _), z) in values.iter().zip(&zero) {
        let s = if *s >= at { s + 1 } else { *s };
        match frags.last_mut() {
            Some((start, zs)) if *start + zs.len() as u32 == s && zs.len() < 127 => zs.push(*z),
            _ => frags.push((s, vec![*z])),
        }
    }
    let mut out = Vec::new();
    let mut mask_bits: Vec<bool> = Vec::new();
    let mut cursor = 0u32;
    for (i, (start, zs)) in frags.iter().enumerate() {
        let mut skip = start - cursor;
        while skip > 127 {
            out.extend_from_slice(&127u16.to_le_bytes());
            skip -= 127;
        }
        let any_zero = zs.iter().any(|z| *z);
        if any_zero {
            mask_bits.extend(zs);
        }
        let last = if i + 1 == frags.len() { 0x100 } else { 0 };
        let v = skip | if any_zero { 0x80 } else { 0 } | last | ((zs.len() as u32) << 9);
        out.extend_from_slice(&(v as u16).to_le_bytes());
        cursor = start + zs.len() as u32;
    }
    let bytes = match mask_bits.len() {
        0 => 0,
        1..=8 => 1,
        9..=16 => 2,
        n => 4 * n.div_ceil(32),
    };
    let mut m = vec![0u8; bytes];
    for (i, z) in mask_bits.iter().enumerate() {
        if *z {
            m[i / 8] |= 1 << (i % 8);
        }
    }
    out.extend_from_slice(&m);
    out.extend_from_slice(body);
    Ok(out)
}

fn bundle_groups(pkg: &ZenPackage) -> Vec<[Vec<i32>; 4]> {
    pkg.dependency_bundle_headers
        .iter()
        .map(|h| {
            let mut at = h.first_entry_index.max(0) as usize;
            let mut g: [Vec<i32>; 4] = Default::default();
            for (k, c) in h.counts.iter().enumerate() {
                g[k] = pkg.dependency_bundle_entries[at..at + *c as usize].to_vec();
                at += *c as usize;
            }
            g
        })
        .collect()
}

fn set_bundle_groups(pkg: &mut ZenPackage, groups: &[[Vec<i32>; 4]]) {
    pkg.dependency_bundle_entries.clear();
    pkg.dependency_bundle_headers.clear();
    for g in groups {
        let first = pkg.dependency_bundle_entries.len() as i32;
        let counts = [
            g[0].len() as u32,
            g[1].len() as u32,
            g[2].len() as u32,
            g[3].len() as u32,
        ];
        for v in g {
            pkg.dependency_bundle_entries.extend_from_slice(v);
        }
        pkg.dependency_bundle_headers.push(DependencyBundleHeader {
            first_entry_index: first,
            counts,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shift_moves_inherited_slots() {
        // CU4 WBP_MainMenu's CDO header: own slots 0, 27, 29, 33, inherited
        // 87 and 89. A variable added at own slot 35 moves 87 and 89 up one.
        let cdo = [
            0x00, 0x02, 0x1a, 0x02, 0x01, 0x02, 0x03, 0x02, 0x35, 0x02, 0x01, 0x03, 0xaa,
        ];
        let out = shift_unversioned(&cdo, 35).unwrap();
        assert_eq!(
            out,
            [0x00, 0x02, 0x1a, 0x02, 0x01, 0x02, 0x03, 0x02, 0x36, 0x02, 0x01, 0x03, 0xaa]
        );
        // Nothing past the insertion point: unchanged.
        assert_eq!(shift_unversioned(&cdo, 200).unwrap(), cdo);
    }

    #[test]
    fn shift_splits_a_run_and_keeps_zero_bits() {
        // Slots 3,4,5 in one zero-mask fragment (slot 4 zeroed), last.
        let h = (3u16 | 0x80 | 0x100 | (3 << 9)).to_le_bytes();
        let b = [h[0], h[1], 0b010, 0x11, 0x22];
        let out = shift_unversioned(&b, 4).unwrap();
        // Slot 3 alone (no zeros), then 5,6 with the zero on 5.
        let f1 = (3u16 | (1 << 9)).to_le_bytes();
        let f2 = (1u16 | 0x80 | 0x100 | (2 << 9)).to_le_bytes();
        assert_eq!(out, [f1[0], f1[1], f2[0], f2[1], 0b01, 0x11, 0x22]);
    }

    #[test]
    fn relabel_swaps_a_string_table_text() {
        let mut b = vec![0x01, 0, 0, 0, 0];
        b.push(0x0b);
        b.extend_from_slice(&5u32.to_le_bytes());
        b.extend_from_slice(&0u32.to_le_bytes());
        b.extend_from_slice(&4i32.to_le_bytes());
        b.extend_from_slice(b"key\0");
        b.extend_from_slice(&[0x48, 0, 0, 0]);
        relabel(&mut b, 10, "HI").unwrap();
        let mut want = vec![0x01, 0, 0, 0, 0, 0xff, 1, 0, 0, 0, 3, 0, 0, 0];
        want.extend_from_slice(b"HI\0");
        want.extend_from_slice(&[0x48, 0, 0, 0]);
        assert_eq!(b, want);
    }

    /// The real thing, when the game is at hand: CU4's main menu gets a
    /// MULTIPLAYER button after Remix that opens our lobby.
    #[test]
    fn shipped_main_menu_gets_a_button() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
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
        let usmap = Usmap::parse(USMAP).unwrap();
        let (c, rel) = containers
            .iter()
            .find_map(|c| {
                c.files
                    .keys()
                    .find(|r| {
                        c.full_path(r)
                            .ends_with("MainMenu/Widgets/WBP_MainMenu.uasset")
                    })
                    .map(|r| (c, r.clone()))
            })
            .expect("WBP_MainMenu");
        let data = ue_iostore::read_chunk(c, &c.chunks[c.files[&rel]], None, &[]).unwrap();
        let mut pkg = ZenPackage::parse(&data).unwrap();
        let before = pkg.export_map.len();
        let spec = MenuButton {
            name: "MultiplayerButton",
            label: "MULTIPLAYER",
            template: "RemixButton",
            opens: "/Game/MJOLNIR/UI/WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C",
            push_like: "WBP_CustomizationCategoryMenu",
        };
        let added = add_menu_button(&mut pkg, &usmap, &scripts, &spec).unwrap();
        let back = ZenPackage::parse(&pkg.write()).unwrap();
        assert_eq!(back.export_map.len(), before + 3);
        assert_eq!(back.dependency_bundle_headers.len(), before + 3);
        assert_eq!(
            back.export_bundle_entries.len(),
            pkg.export_bundle_entries.len()
        );

        // The click enters the appended block, which pushes the lobby.
        let f = kismet::script(back.export_bytes(added.function).unwrap(), &kismet::Raw).unwrap();
        assert_eq!(f.stmts[1].text, format!("o38({})", added.entry));
        let uber = (0..back.export_map.len())
            .find(|&i| export_name(&back, i) == "ExecuteUbergraph_WBP_MainMenu")
            .unwrap();
        let ub = back.export_bytes(uber).unwrap();
        let u = kismet::script(ub, &kismet::Raw).unwrap();
        let block: Vec<&kismet::Stmt> =
            u.stmts.iter().filter(|s| s.offset >= added.entry).collect();
        assert_eq!(block.len(), 4);
        assert!(block[1].text.contains("WBP_MJOLNIRLobby_C"));
        assert_eq!(block[2].text, "pop");

        // The container lists the slot right after Remix's; the slot holds the button.
        let container = (0..back.export_map.len())
            .find(|&i| export_name(&back, i) == "MainButtonContainer")
            .unwrap();
        let ce = open_export(&back, &usmap, &scripts, container).unwrap();
        let Some(Val::Array(slots)) = ce.block.get(slot(&usmap, &ce.class, "Slots").unwrap())
        else {
            panic!()
        };
        assert_eq!(slots[added.position], Val::Object(pidx(added.slot)));
        let se = open_export(&back, &usmap, &scripts, added.slot).unwrap();
        assert_eq!(
            se.block.get(slot(&usmap, &se.class, "Content").unwrap()),
            Some(&Val::Object(pidx(added.button)))
        );

        // The label is ours, and the CDO's first inherited value moved to 88.
        let button = back.export_bytes(added.button).unwrap();
        assert!(button.windows(12).any(|w| w == b"MULTIPLAYER "));
        assert_eq!(added.variable_slot, 35);
        let cdo = (0..back.export_map.len())
            .find(|&i| export_name(&back, i) == "Default__WBP_MainMenu_C")
            .unwrap();
        assert_eq!(&back.export_bytes(cdo).unwrap()[8..10], &[0x36, 0x02]);

        // A second run refuses.
        let mut again = back.clone();
        assert!(add_menu_button(&mut again, &usmap, &scripts, &spec).is_err());
    }
}
