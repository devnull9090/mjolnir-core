//! A readable listing of a decoded variant (`mjolnir megalo dump`): every
//! field of the [`raw`](crate::raw) tree with its value names, the string
//! tables as text, and the script as triggers holding their conditions and
//! actions, operands written as references (`current_player.score`,
//! `global.object[0]`, `team[1].timer[0]`).
//!
//! The listing is stable: the same tree always gives the same text, fields
//! in read order. Names come from the grammar (`grammar/megalo_cu4.json`);
//! `(reach: ...)` marks ReachVariantTool's Halo Reach names for a value,
//! which are hints for CU4, not verified.

use std::collections::BTreeSet;
use std::fmt::Write as _;
use std::io::Read as _;

use crate::raw::{self, field, int, FieldDef, Grammar, Kind, Node, Tree, TypeDef, Value};
use crate::Error;

/// The languages of a string table, in stream order.
pub const LANGUAGES: [&str; 12] = [
    "english",
    "japanese",
    "german",
    "french",
    "spanish",
    "mexican",
    "italian",
    "korean",
    "chinese_traditional",
    "chinese_simplified",
    "portuguese",
    "polish",
];

/// A decoded string table (`STRINGS(...)` in the grammar).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct StringTable {
    /// Per string, per language: the text when the language has an offset.
    pub strings: Vec<Vec<Option<String>>>,
    /// The data's size as the stream states it.
    pub size: usize,
    /// The bytes stored when the data is compressed (a big-endian u32 size,
    /// then a zlib stream).
    pub compressed: Option<usize>,
}

impl StringTable {
    /// Decode a `STRINGS(...)` struct, inflating compressed data.
    pub fn from_value(v: &Value) -> Result<StringTable, Error> {
        let f = v.fields();
        let size = int(f, "uncompressed_size").unwrap_or(0).max(0) as usize;
        let data = match field(f, "data").map(|n| &n.value) {
            Some(Value::Bytes(b)) => b.as_slice(),
            _ => &[],
        };
        let compressed = int(f, "compressed") == Some(1);
        let text: Vec<u8> = if compressed {
            if data.len() < 4 {
                return Err(Error::Mismatch {
                    path: "strings.data".into(),
                    msg: format!("{} compressed bytes", data.len()),
                });
            }
            let want = u32::from_be_bytes([data[0], data[1], data[2], data[3]]) as usize;
            let mut out = Vec::with_capacity(want.min(1 << 20));
            flate2::read::ZlibDecoder::new(&data[4..])
                .read_to_end(&mut out)
                .map_err(|e| Error::Mismatch {
                    path: "strings.data".into(),
                    msg: format!("zlib: {e}"),
                })?;
            out
        } else {
            data.to_vec()
        };
        let mut strings = Vec::new();
        if let Some(n) = field(f, "strings") {
            for item in n.value.items() {
                let offsets = field(item, "offsets")
                    .map(|o| o.value.items())
                    .unwrap_or(&[]);
                let mut langs = Vec::new();
                for o in offsets {
                    let off = int(o, "offset").unwrap_or(-1);
                    langs.push(if off < 0 {
                        None
                    } else {
                        let off = off as usize;
                        Some(match text.get(off..) {
                            Some(rest) => {
                                let end = rest.iter().position(|&b| b == 0).unwrap_or(rest.len());
                                String::from_utf8_lossy(&rest[..end]).into_owned()
                            }
                            None => format!("<offset {off} past {} bytes>", text.len()),
                        })
                    });
                }
                strings.push(langs);
            }
        }
        Ok(StringTable {
            strings,
            size,
            compressed: compressed.then_some(data.len()),
        })
    }

    /// String `i` in English.
    pub fn english(&self, i: i64) -> Option<&str> {
        usize::try_from(i)
            .ok()
            .and_then(|i| self.strings.get(i))
            .and_then(|s| s.first())
            .and_then(|s| s.as_deref())
    }
}

/// The text before a name's parenthesised note (`divide (b == 0 gives 0)`).
fn short(name: &str) -> &str {
    name.split(" (").next().unwrap_or(name)
}

fn quote(s: &str) -> String {
    format!("\"{}\"", s.escape_debug())
}

/// The field definition for `name` among `defs`, looking into `if`
/// branches (whose fields sit in the enclosing struct).
fn find_def<'g>(defs: &'g [FieldDef], name: &str) -> Option<&'g FieldDef> {
    for d in defs {
        if let Kind::If {
            then, otherwise, ..
        } = &d.kind
        {
            if let Some(f) = find_def(then, name).or_else(|| find_def(otherwise, name)) {
                return Some(f);
            }
        } else if d.name == name {
            return Some(d);
        }
    }
    None
}

/// Types written on one line as an operand.
const INLINE_TYPES: [&str; 15] = [
    "NUMBER",
    "PLAYER",
    "OBJECT",
    "TEAM",
    "TIMER",
    "VAR",
    "PLAYER_OR_GROUP",
    "PLAYER_SET",
    "FORMAT_TOKEN",
    "FORMAT_STRING",
    "VECTOR3",
    "SHAPE",
    "WAYPOINT_ICON",
    "METER",
    "TRIGGER_BLOCK",
];

/// How a reference operand reads, by type and case (`{field}` is the
/// field's value).
fn reference_template(ty: &str, case: &str) -> Option<&'static str> {
    Some(match (ty, case) {
        ("NUMBER", "constant") => "{value}",
        ("NUMBER", "player_number") => "{player}.number[{index}]",
        ("NUMBER", "object_number") => "{object}.number[{index}]",
        ("NUMBER", "team_number") => "{team}.number[{index}]",
        ("NUMBER", "global_number") => "global.number[{index}]",
        ("NUMBER", "script_option") => "option[{index}]",
        ("NUMBER", "spawn_sequence") => "{object}.spawn_sequence",
        ("NUMBER", "team_score") => "{team}.score",
        ("NUMBER", "player_score") => "{player}.score",
        ("NUMBER", "player_money") => "{player}.money",
        ("NUMBER", "player_rating") => "{player}.rating",
        ("NUMBER", "player_stat") => "{player}.stat[{index}]",
        ("NUMBER", "team_stat") => "{team}.stat[{index}]",
        ("NUMBER", "temporary_number") => "temporaries.number[{index}]",
        ("PLAYER", "global_player") => "{player}",
        ("PLAYER", "player_player") => "{player}.player[{index}]",
        ("PLAYER", "object_player") => "{object}.player[{index}]",
        ("PLAYER", "team_player") => "{team}.player[{index}]",
        ("OBJECT", "global_object") => "{object}",
        ("OBJECT", "player_object") => "{player}.object[{index}]",
        ("OBJECT", "object_object") => "{object}.object[{index}]",
        ("OBJECT", "team_object") => "{team}.object[{index}]",
        ("OBJECT", "player_biped") => "{player}.biped",
        ("OBJECT", "player_player_biped") => "{player}.player[{index}].biped",
        ("OBJECT", "object_player_biped") => "{object}.player[{index}].biped",
        ("OBJECT", "team_player_biped") => "{team}.player[{index}].biped",
        ("TEAM", "global_team") => "{team}",
        ("TEAM", "player_team") => "{player}.team[{index}]",
        ("TEAM", "object_team") => "{object}.team[{index}]",
        ("TEAM", "team_team") => "{team}.team[{index}]",
        ("TEAM", "player_owner_team") => "{player}.team",
        ("TEAM", "object_owner_team") => "{object}.team",
        ("TIMER", "global_timer") => "global.timer[{index}]",
        ("TIMER", "player_timer") => "{player}.timer[{index}]",
        ("TIMER", "team_timer") => "{team}.timer[{index}]",
        ("TIMER", "object_timer") => "{object}.timer[{index}]",
        ("TIMER", "round_timer" | "sudden_death_timer" | "grace_period_timer") => "game.{case}",
        ("PLAYER_OR_GROUP", "team") => "{team}",
        ("PLAYER_OR_GROUP", "player") => "{player}",
        ("PLAYER_SET", "mod_player") => "mod_player({player}, {add})",
        ("FORMAT_TOKEN" | "VAR", _) => "{value}",
        _ => return None,
    })
}

/// A math operator as an assignment.
fn assign_op(op: i64) -> String {
    match op {
        0 => "+=".into(),
        1 => "-=".into(),
        2 => "*=".into(),
        3 => "/=".into(),
        4 => "=".into(),
        5 => "%=".into(),
        6 => "&=".into(),
        7 => "|=".into(),
        8 => "^=".into(),
        9 => "= ~".into(),
        10 => "<<=".into(),
        11 => ">>=".into(),
        12 => "= abs".into(),
        n => format!("<operator {n}>"),
    }
}

/// Days since 1970-01-01 to a civil date.
fn civil(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    (y, m, d)
}

fn unix_time(secs: u64) -> Option<String> {
    if secs == 0 || secs > 32_503_680_000 {
        return None;
    }
    let s = secs as i64;
    let (y, m, d) = civil(s.div_euclid(86_400));
    let t = s.rem_euclid(86_400);
    Some(format!(
        "{y:04}-{m:02}-{d:02} {:02}:{:02}:{:02} UTC",
        t / 3600,
        t / 60 % 60,
        t % 60
    ))
}

fn set_bits(words: &[i64]) -> Vec<usize> {
    let mut out = Vec::new();
    for (w, word) in words.iter().enumerate() {
        for b in 0..32 {
            if word >> b & 1 == 1 {
                out.push(w * 32 + b);
            }
        }
    }
    out
}

fn ranges(v: &[usize]) -> String {
    let mut parts = Vec::new();
    let mut i = 0;
    while i < v.len() {
        let mut j = i;
        while j + 1 < v.len() && v[j + 1] == v[j] + 1 {
            j += 1;
        }
        parts.push(if j > i {
            format!("{}..{}", v[i], v[j])
        } else {
            v[i].to_string()
        });
        i = j + 1;
    }
    if parts.is_empty() {
        "none".into()
    } else {
        parts.join(", ")
    }
}

struct Dumper<'a> {
    g: &'a Grammar,
    strings: StringTable,
    out: String,
    /// Translations, printed at the end: (table, string, language, text).
    translations: Vec<(String, usize, &'static str, String)>,
    /// Problems the script section found.
    problems: Vec<String>,
    /// Object filter (label) names by index.
    labels: Vec<String>,
    /// Script trait names by index.
    trait_names: Vec<String>,
}

impl Dumper<'_> {
    fn line(&mut self, indent: usize, s: impl std::fmt::Display) {
        let _ = writeln!(self.out, "{:width$}{s}", "", width = indent * 2);
    }

    // ------------------------------------------------------------ values

    /// A plain value: its number, the name the grammar gives it, string
    /// text, a Reach name hint.
    fn leaf(&self, def: Option<&FieldDef>, v: &Value, terse: bool) -> String {
        let n = match v {
            Value::Int { value, .. } => *value,
            Value::Opt { value: None, .. } => return "none".into(),
            Value::Opt { value: Some(x), .. } => *x as i64,
            Value::U64(x) => {
                return match def
                    .filter(|d| d.name == "timestamp")
                    .and_then(|_| unix_time(*x))
                {
                    Some(t) => format!("{x} ({t})"),
                    None => format!("{x:#x}"),
                };
            }
            Value::F32(bits) => {
                let f = f32::from_bits(*bits);
                return if f.is_finite() {
                    format!("{f}")
                } else {
                    format!("{f} ({bits:#010x})")
                };
            }
            Value::Bytes(b) => return format!("<{} bytes>", b.len()),
            Value::Text { .. } => return quote(&v.text().unwrap_or_default()),
            Value::Struct(_) | Value::Union { .. } | Value::List(_) => {
                return "<composite>".into();
            }
        };
        let Some(d) = def else {
            return n.to_string();
        };
        let mut s = n.to_string();
        if let Some(names) = &d.names {
            if d.flags {
                let mut set = Vec::new();
                let mut rest = n;
                for (bit, name) in names {
                    if *bit > 0 && n & bit != 0 {
                        set.push(short(name).to_string());
                        rest &= !bit;
                    }
                }
                if rest != 0 {
                    set.push(format!("{rest:#x}"));
                }
                if !set.is_empty() {
                    s = format!("{n:#x} ({})", set.join("|"));
                }
            } else if let Some(name) = names.get(&n) {
                s = if terse {
                    short(name).to_string()
                } else {
                    format!("{n} ({name})")
                };
            }
        } else if d.string_ref {
            s = if n < 0 {
                "none".into()
            } else {
                match self.strings.english(n) {
                    Some(t) => format!("{n} {}", quote(t)),
                    None => format!("{n} <no such string>"),
                }
            };
        } else if matches!(d.kind, Kind::U { minus1: true, .. }) && n == -1 {
            s = "none".into();
        } else if !terse {
            if let Kind::U { bits, .. } = d.kind {
                if bits >= 16 && n > 9 {
                    s = format!("{n} ({n:#x})");
                }
            }
        }
        if let Some(h) = &d.hint {
            if let Some(name) = self.g.reach_names.get(h).and_then(|t| t.get(&n)) {
                s = format!("{s} (reach: {name})");
            }
        }
        if !terse && d.name.starts_with("color_") {
            s = format!("{n:#010x}");
        }
        if !terse && d.name == "timestamp" {
            if let Some(t) = unix_time(n as u64) {
                s = format!("{s} ({t})");
            }
        }
        s
    }

    /// A field's value written inline.
    fn inline(&self, def: Option<&FieldDef>, v: &Value) -> String {
        match (def.map(|d| &d.kind), v) {
            (Some(Kind::Ref(t)), _) => self.operand(t, v),
            (Some(Kind::Array { of, .. } | Kind::Repeat { of, .. }), Value::List(items)) => {
                let parts: Vec<String> = items
                    .iter()
                    .map(|item| self.inline_fields(of, item))
                    .collect();
                format!("[{}]", parts.join(", "))
            }
            _ => self.leaf(def, v, true),
        }
    }

    /// Fields written inline: one alone as its value, more as
    /// `{name: value, ...}`.
    fn inline_fields(&self, defs: &[FieldDef], nodes: &[Node]) -> String {
        if nodes.len() == 1 {
            return self.inline(find_def(defs, &nodes[0].name), &nodes[0].value);
        }
        let parts: Vec<String> = nodes
            .iter()
            .map(|n| {
                format!(
                    "{}: {}",
                    n.name,
                    self.inline(find_def(defs, &n.name), &n.value)
                )
            })
            .collect();
        format!("{{{}}}", parts.join(", "))
    }

    /// An operand of type `ty`.
    fn operand(&self, ty: &str, v: &Value) -> String {
        let Some(def) = self.g.type_def(ty) else {
            return format!("<{ty}?>");
        };
        match (def, v) {
            (
                TypeDef::Union(u),
                Value::Union {
                    selector,
                    case,
                    fields,
                },
            ) => {
                let defs: &[FieldDef] = u.cases.get(selector).map_or(&[], |c| &c.fields);
                if let Some(t) = reference_template(ty, case) {
                    return self.fill(t, case, defs, fields);
                }
                if fields.is_empty() {
                    return match ty {
                        "NUMBER" if *selector <= 43 => format!("game.{case}"),
                        _ => case.clone(),
                    };
                }
                let parts: Vec<String> = fields
                    .iter()
                    .map(|n| self.inline(find_def(defs, &n.name), &n.value))
                    .collect();
                format!("{case}({})", parts.join(", "))
            }
            (TypeDef::Struct(defs), Value::Struct(fields)) => match ty {
                "FORMAT_STRING" => {
                    let s = self.inline(find_def(defs, "string"), field_value(fields, "string"));
                    let toks = field(fields, "tokens")
                        .map(|n| n.value.items())
                        .unwrap_or(&[]);
                    if toks.is_empty() {
                        s
                    } else {
                        let tdefs = match find_def(defs, "tokens").map(|d| &d.kind) {
                            Some(Kind::Array { of, .. }) => of.as_slice(),
                            _ => &[],
                        };
                        let parts: Vec<String> =
                            toks.iter().map(|t| self.inline_fields(tdefs, t)).collect();
                        format!("{s} % ({})", parts.join(", "))
                    }
                }
                "VECTOR3" => format!(
                    "({}, {}, {})",
                    int(fields, "x").unwrap_or(0),
                    int(fields, "y").unwrap_or(0),
                    int(fields, "z").unwrap_or(0)
                ),
                "TRIGGER_BLOCK" => format!(
                    "conditions {}+{}, actions {}+{}",
                    int(fields, "condition_start").unwrap_or(0),
                    int(fields, "condition_count").unwrap_or(0),
                    int(fields, "action_start").unwrap_or(0),
                    int(fields, "action_count").unwrap_or(0)
                ),
                _ => self.inline_fields(defs, fields),
            },
            _ => format!("<{ty}: {v:?}>"),
        }
    }

    fn fill(&self, template: &str, case: &str, defs: &[FieldDef], fields: &[Node]) -> String {
        let mut out = String::new();
        let mut rest = template;
        while let Some(open) = rest.find('{') {
            out.push_str(&rest[..open]);
            let after = &rest[open + 1..];
            let Some(close) = after.find('}') else {
                out.push_str(&rest[open..]);
                return out;
            };
            let key = &after[..close];
            if key == "case" {
                out.push_str(case);
            } else if let Some(n) = field(fields, key) {
                out.push_str(&self.inline(find_def(defs, key), &n.value));
            } else {
                out.push('?');
            }
            rest = &after[close + 1..];
        }
        out.push_str(rest);
        out
    }

    // ------------------------------------------------------------ tree

    fn nodes(&mut self, defs: &[FieldDef], nodes: &[Node], indent: usize) {
        for n in nodes {
            self.node(find_def(defs, &n.name), n, indent);
        }
    }

    /// The node is a value written on one line.
    fn is_inline(def: Option<&FieldDef>, v: &Value) -> bool {
        match (def.map(|d| &d.kind), v) {
            (Some(Kind::Ref(t)), _) => INLINE_TYPES.contains(&t.as_str()),
            (_, Value::Struct(_) | Value::Union { .. } | Value::List(_)) => false,
            _ => true,
        }
    }

    fn node(&mut self, def: Option<&FieldDef>, n: &Node, indent: usize) {
        let name = n.name.as_str();
        match (def.map(|d| &d.kind), &n.value) {
            (Some(Kind::Ref(t)), v) => self.typed_node(name, t, v, indent),
            (Some(Kind::Array { of, .. } | Kind::Repeat { of, .. }), Value::List(items)) => {
                let labels = def.and_then(|d| d.element_names.clone());
                if items.is_empty() {
                    self.line(indent, format!("{name}: none"));
                    return;
                }
                let all_leaves = items.iter().all(|item| {
                    item.len() == 1 && Self::is_inline(find_def(of, &item[0].name), &item[0].value)
                });
                if all_leaves && labels.is_none() {
                    let parts: Vec<String> = items
                        .iter()
                        .map(|item| self.inline(find_def(of, &item[0].name), &item[0].value))
                        .collect();
                    if parts.iter().map(String::len).sum::<usize>() < 100 {
                        let inner = &items[0][0].name;
                        self.line(indent, format!("{name} ({inner}) = [{}]", parts.join(", ")));
                        return;
                    }
                }
                for (i, item) in items.iter().enumerate() {
                    let label = labels
                        .as_ref()
                        .and_then(|l| l.get(i))
                        .cloned()
                        .unwrap_or_else(|| format!("{name}[{i}]"));
                    self.element(&label, of, item, indent);
                }
            }
            (_, v) => {
                let s = self.leaf(def, v, false);
                self.line(indent, format!("{name} = {s}"));
            }
        }
    }

    /// A list element or struct: on one line when its fields are all
    /// inline and few, else nested.
    fn element(&mut self, label: &str, defs: &[FieldDef], item: &[Node], indent: usize) {
        if item.len() == 1 {
            let d = find_def(defs, &item[0].name);
            if Self::is_inline(d, &item[0].value) {
                let s = self.inline_or_leaf(d, &item[0].value);
                self.line(indent, format!("{label} = {s}"));
                return;
            }
            if let Some(Kind::Ref(t)) = d.map(|d| &d.kind) {
                self.typed_node(label, t, &item[0].value, indent);
                return;
            }
        }
        if item.len() <= 7
            && item
                .iter()
                .all(|n| Self::is_inline(find_def(defs, &n.name), &n.value))
        {
            let parts: Vec<String> = item
                .iter()
                .map(|n| {
                    format!(
                        "{} = {}",
                        n.name,
                        self.inline_or_leaf(find_def(defs, &n.name), &n.value)
                    )
                })
                .collect();
            self.line(indent, format!("{label}: {}", parts.join(", ")));
            return;
        }
        self.line(indent, format!("{label}:"));
        self.nodes(defs, item, indent + 1);
    }

    fn inline_or_leaf(&self, def: Option<&FieldDef>, v: &Value) -> String {
        match def.map(|d| &d.kind) {
            Some(Kind::Ref(_)) => self.inline(def, v),
            _ => self.leaf(def, v, false),
        }
    }

    fn typed_node(&mut self, name: &str, t: &str, v: &Value, indent: usize) {
        if t == "TRAITS" {
            let s = self.traits(v);
            self.line(indent, format!("{name}: {s}"));
            return;
        }
        if t.starts_with("STRINGS(") {
            self.string_table(name, v, indent);
            return;
        }
        if INLINE_TYPES.contains(&t) {
            let s = self.operand(t, v);
            self.line(indent, format!("{name} = {s}"));
            return;
        }
        let g = self.g;
        match (g.type_def(t), v) {
            (Some(TypeDef::Struct(defs)), Value::Struct(fields)) => {
                self.element(name, defs, fields, indent);
            }
            (
                Some(TypeDef::Union(u)),
                Value::Union {
                    selector,
                    case,
                    fields,
                },
            ) => {
                self.line(indent, format!("{name} = {case} ({selector})"));
                let defs: &[FieldDef] = u.cases.get(selector).map_or(&[], |c| &c.fields);
                self.nodes(defs, fields, indent + 1);
            }
            _ => self.line(indent, format!("{name} = <{t}?>")),
        }
    }

    /// A TRAITS block: the fields that change something (0 = unchanged).
    fn traits(&self, v: &Value) -> String {
        let defs = match self.g.type_def("TRAITS") {
            Some(TypeDef::Struct(d)) => d.as_slice(),
            _ => &[],
        };
        let parts: Vec<String> = v
            .fields()
            .iter()
            .filter(|n| {
                let unchanged = find_def(defs, &n.name)
                    .and_then(|d| d.names.as_ref())
                    .zip(n.value.as_i64())
                    .and_then(|(names, v)| names.get(&v))
                    .is_some_and(|name| name == "unchanged");
                !unchanged
                    && !matches!(
                        n.value,
                        Value::Int { value: 0, .. } | Value::Opt { value: None, .. }
                    )
            })
            .map(|n| {
                format!(
                    "{}={}",
                    n.name,
                    self.leaf(find_def(defs, &n.name), &n.value, true)
                )
            })
            .collect();
        if parts.is_empty() {
            "all unchanged".into()
        } else {
            format!("{} (others unchanged)", parts.join(", "))
        }
    }

    fn string_table(&mut self, name: &str, v: &Value, indent: usize) {
        let t = match StringTable::from_value(v) {
            Ok(t) => t,
            Err(e) => {
                self.line(indent, format!("{name}: <{e}>"));
                return;
            }
        };
        for (i, langs) in t.strings.iter().enumerate() {
            let en = langs.first().cloned().flatten();
            for (l, text) in langs.iter().enumerate().skip(1) {
                if let Some(text) = text {
                    if Some(text) != en.as_ref() {
                        self.translations.push((
                            name.to_string(),
                            i,
                            LANGUAGES[l.min(11)],
                            text.clone(),
                        ));
                    }
                }
            }
        }
        let how = match t.compressed {
            Some(stored) => format!("{} bytes, zlib-compressed to {stored}", t.size),
            None => format!("{} bytes", t.size),
        };
        match t.strings.len() {
            0 => self.line(indent, format!("{name}: empty")),
            1 if name != "strings" => {
                let s = t.strings[0]
                    .first()
                    .cloned()
                    .flatten()
                    .map_or("<no english>".to_string(), |s| quote(&s));
                self.line(indent, format!("{name} = {s} ({how})"));
            }
            n => {
                self.line(indent, format!("{name}: {n} string(s), {how}"));
                for (i, langs) in t.strings.iter().enumerate() {
                    let s = langs
                        .first()
                        .cloned()
                        .flatten()
                        .map_or("<no english>".to_string(), |s| quote(&s));
                    let others = langs.iter().skip(1).filter(|x| x.is_some()).count();
                    self.line(indent + 1, format!("[{i}] {s}  (+{others} languages)"));
                }
            }
        }
    }

    // ------------------------------------------------------------ script

    /// An index into `names` with the name it has (labels, script traits).
    fn named(&self, names: &[String], v: &Value) -> String {
        match v.as_i64() {
            Some(n) if n >= 0 => match names.get(n as usize) {
                Some(name) => format!("{n} {name}"),
                None => format!("{n} <past the {}>", names.len()),
            },
            _ => "none".into(),
        }
    }

    fn op_line(&self, kind: &str, idx: usize, v: &Value) -> String {
        let Value::Union {
            selector, fields, ..
        } = v
        else {
            return format!("{kind} {idx}: <not a union>");
        };
        let (ops, ty) = if kind == "cond" {
            (&self.g.conditions, "CONDITION")
        } else {
            (&self.g.actions, "ACTION")
        };
        let name = usize::try_from(*selector)
            .ok()
            .and_then(|i| ops.get(i))
            .map_or_else(|| format!("type {selector}"), |o| o.name.clone());
        let defs: &[FieldDef] = match self.g.type_def(ty) {
            Some(TypeDef::Union(u)) => u.cases.get(selector).map_or(&[], |c| &c.fields),
            _ => &[],
        };
        let get = |k: &str| {
            field(fields, k).map_or("?".to_string(), |n| {
                self.inline(find_def(defs, k), &n.value)
            })
        };
        let params: Vec<&Node> = fields
            .iter()
            .filter(|n| !matches!(n.name.as_str(), "negate" | "or_sequence" | "action_offset"))
            .collect();
        let body = match (kind, *selector) {
            ("cond", 1) => format!("{} {} {}", get("a"), get("operator"), get("b")),
            ("act", 9) => {
                let op = int(fields, "operator").unwrap_or(-1);
                match op {
                    12 => format!("{} = abs({})", get("a"), get("b")),
                    _ => format!("{} {} {}", get("a"), assign_op(op), get("b")),
                }
            }
            ("act", 1) => format!(
                "{}.score {} {}",
                get("target"),
                assign_op(int(fields, "operator").unwrap_or(-1)),
                get("operand")
            ),
            _ => params
                .iter()
                .map(|n| {
                    let v = match (kind, *selector, n.name.as_str()) {
                        (_, _, "label") => self.named(&self.labels, &n.value),
                        ("act", 11, "traits") => self.named(&self.trait_names, &n.value),
                        _ => self.inline(find_def(defs, &n.name), &n.value),
                    };
                    format!("{}: {v}", n.name)
                })
                .collect::<Vec<_>>()
                .join(", "),
        };
        if kind == "cond" {
            let not = if int(fields, "negate") == Some(1) {
                "not "
            } else {
                ""
            };
            format!(
                "cond {idx} [or {}]: {not}{name}{}{body}",
                int(fields, "or_sequence").unwrap_or(0),
                if body.is_empty() { "" } else { ": " }
            )
        } else {
            format!(
                "act {idx}: {name}{}{body}",
                if body.is_empty() { "" } else { ": " }
            )
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn block(
        &mut self,
        conds: &[&Value],
        acts: &[&Value],
        range: (i64, i64, i64, i64),
        seen: &mut (BTreeSet<usize>, BTreeSet<usize>),
        indent: usize,
        depth: usize,
        what: &str,
    ) {
        let (c0, cn, a0, an) = range;
        let c_in = c0 >= 0 && cn >= 0 && (c0 + cn) as usize <= conds.len();
        let a_in = a0 >= 0 && an >= 0 && (a0 + an) as usize <= acts.len();
        if !c_in {
            self.problems.push(format!(
                "{what}: conditions {c0}+{cn} past the {}",
                conds.len()
            ));
        }
        if !a_in {
            self.problems
                .push(format!("{what}: actions {a0}+{an} past the {}", acts.len()));
        }
        let cl: Vec<usize> = if c_in {
            (c0 as usize..(c0 + cn) as usize).collect()
        } else {
            Vec::new()
        };
        let al: Vec<usize> = if a_in {
            (a0 as usize..(a0 + an) as usize).collect()
        } else {
            Vec::new()
        };
        let offset = |c: usize| int(conds[c].fields(), "action_offset").unwrap_or(0);
        for (k, &a) in al.iter().enumerate() {
            for &c in cl.iter().filter(|&&c| offset(c) == k as i64) {
                seen.0.insert(c);
                let s = self.op_line("cond", c, conds[c]);
                self.line(indent, s);
            }
            seen.1.insert(a);
            let s = self.op_line("act", a, acts[a]);
            self.line(indent, s);
            if let Value::Union {
                selector: 99,
                fields,
                ..
            } = acts[a]
            {
                if let Some(Value::Struct(b)) = field(fields, "block").map(|n| &n.value) {
                    let r = (
                        int(b, "condition_start").unwrap_or(0),
                        int(b, "condition_count").unwrap_or(0),
                        int(b, "action_start").unwrap_or(0),
                        int(b, "action_count").unwrap_or(0),
                    );
                    if depth > 32 {
                        self.problems
                            .push(format!("act {a}: inline blocks nest past 32"));
                    } else {
                        self.block(
                            conds,
                            acts,
                            r,
                            seen,
                            indent + 1,
                            depth + 1,
                            &format!("act {a}"),
                        );
                    }
                }
            }
        }
        for &c in cl.iter().filter(|&&c| offset(c) >= an.max(0)) {
            seen.0.insert(c);
            let s = self.op_line("cond", c, conds[c]);
            self.line(indent, format!("{s}  (after the last action)"));
        }
    }

    fn script(&mut self, tree: &Tree) {
        let list = |name: &str, inner: &str| -> Vec<Value> {
            field(&tree.fields, name)
                .map(|n| {
                    n.value
                        .items()
                        .iter()
                        .filter_map(|item| field(item, inner).map(|x| x.value.clone()))
                        .collect()
                })
                .unwrap_or_default()
        };
        let conds = list("conditions", "condition");
        let acts = list("actions", "action");
        let triggers = list("triggers", "trigger");
        let conds: Vec<&Value> = conds.iter().collect();
        let acts: Vec<&Value> = acts.iter().collect();
        self.line(
            0,
            format!(
                "== script: {} trigger(s), {} condition(s), {} action(s)",
                triggers.len(),
                conds.len(),
                acts.len()
            ),
        );
        const ENTRIES: [(&str, i64); 7] = [
            ("init", 2),
            ("local_init", 3),
            ("host_migration", 4),
            ("double_host_migration", 4),
            ("object_death", 5),
            ("local", 6),
            ("pregame", 7),
        ];
        let mut entry_of = vec![Vec::new(); triggers.len()];
        for (e, attr) in ENTRIES {
            let Some(t) = int(&tree.fields, &format!("entry_{e}")) else {
                continue;
            };
            if t < 0 {
                continue;
            }
            match triggers.get(t as usize) {
                Some(tr) => {
                    entry_of[t as usize].push(e);
                    let a = int(tr.fields(), "attribute").unwrap_or(-1);
                    if a != attr {
                        self.problems.push(format!(
                            "entry point {e} names trigger {t}, whose attribute is {a}, not {attr}"
                        ));
                    }
                }
                None => self.problems.push(format!(
                    "entry point {e} names trigger {t} of {}",
                    triggers.len()
                )),
            }
        }
        let tdefs = match self.g.type_def("TRIGGER") {
            Some(TypeDef::Struct(d)) => d.clone(),
            _ => Vec::new(),
        };
        let mut seen = (BTreeSet::new(), BTreeSet::new());
        for (i, t) in triggers.iter().enumerate() {
            let f = t.fields();
            let ty = self.leaf(
                find_def(&tdefs, "type"),
                &field_value(f, "type").clone(),
                true,
            );
            let attr = self.leaf(
                find_def(&tdefs, "attribute"),
                &field_value(f, "attribute").clone(),
                true,
            );
            let label = match field(f, "label") {
                Some(n) => format!(" label {}", self.named(&self.labels, &n.value)),
                None => String::new(),
            };
            let entry = if entry_of[i].is_empty() {
                String::new()
            } else {
                format!(" [entry: {}]", entry_of[i].join(", "))
            };
            let r = (
                int(f, "first_condition").unwrap_or(0),
                int(f, "condition_count").unwrap_or(0),
                int(f, "first_action").unwrap_or(0),
                int(f, "action_count").unwrap_or(0),
            );
            self.line(0, "");
            self.line(
                0,
                format!(
                    "trigger {i}: {ty}{label}, {attr}{entry}  (conditions {}+{}, actions {}+{})",
                    r.0, r.1, r.2, r.3
                ),
            );
            self.block(&conds, &acts, r, &mut seen, 1, 0, &format!("trigger {i}"));
        }
        // Nested trigger calls.
        for (a, v) in acts.iter().enumerate() {
            if let Value::Union {
                selector: 20,
                fields,
                ..
            } = v
            {
                let t = int(fields, "trigger").unwrap_or(-1);
                if t < 0 || t as usize >= triggers.len() {
                    self.problems
                        .push(format!("act {a} runs trigger {t} of {}", triggers.len()));
                }
            }
        }
        let lost_c: Vec<usize> = (0..conds.len()).filter(|c| !seen.0.contains(c)).collect();
        let lost_a: Vec<usize> = (0..acts.len()).filter(|a| !seen.1.contains(a)).collect();
        if !lost_c.is_empty() || !lost_a.is_empty() {
            self.line(0, "");
            self.line(
                0,
                "== conditions and actions no trigger or inline block holds",
            );
            for c in lost_c {
                let s = self.op_line("cond", c, conds[c]);
                self.line(1, s);
            }
            for a in lost_a {
                let s = self.op_line("act", a, acts[a]);
                self.line(1, s);
            }
        }
    }
}

fn field_value<'a>(fields: &'a [Node], name: &str) -> &'a Value {
    const NONE: Value = Value::Opt {
        bits: 0,
        value: None,
    };
    field(fields, name).map_or(&NONE, |n| &n.value)
}

/// The listing of a decoded variant; `notes` are printed first (the file,
/// its container).
pub fn dump(tree: &Tree, notes: &[String]) -> Result<String, Error> {
    let g = raw::grammar()?;
    let strings = match field(&tree.fields, "strings") {
        Some(n) => StringTable::from_value(&n.value)?,
        None => StringTable::default(),
    };
    let label_name = |item: &[Node]| -> String {
        let f = item.first().map(|n| n.value.fields()).unwrap_or(&[]);
        match int(f, "name") {
            Some(i) if i >= 0 => strings.english(i).map_or(format!("<string {i}>"), quote),
            _ => match field(f, "object_type").and_then(|n| n.value.as_i64()) {
                Some(t) => format!("<unnamed, object type {t}>"),
                None => "<unnamed>".into(),
            },
        }
    };
    let labels = field(&tree.fields, "object_filters")
        .map(|n| n.value.items().iter().map(|i| label_name(i)).collect())
        .unwrap_or_default();
    let trait_names = field(&tree.fields, "script_traits")
        .map(|n| {
            n.value
                .items()
                .iter()
                .map(|item| {
                    let f = item.first().map(|n| n.value.fields()).unwrap_or(&[]);
                    let i = int(f, "name").unwrap_or(-1);
                    strings.english(i).map_or(format!("<string {i}>"), quote)
                })
                .collect()
        })
        .unwrap_or_default();
    let mut d = Dumper {
        g,
        strings,
        out: String::new(),
        translations: Vec::new(),
        problems: Vec::new(),
        labels,
        trait_names,
    };
    d.line(
        0,
        "# Megalo variant (blam_megalo::dump; grammar grammar/megalo_cu4.json)",
    );
    for n in notes {
        d.line(0, format!("# {n}"));
    }
    d.line(
        0,
        format!(
            "# {} bits decoded, bits {}..{} of the buffer",
            tree.end - tree.start,
            tree.start,
            tree.end
        ),
    );
    if !tree.is_megalo() {
        let v = tree.version().unwrap_or(-1);
        d.line(
            0,
            format!(
                "encoding_version = {v} ({v:#x}): not 0x6a or 0x6b; the simulation reads nothing more"
            ),
        );
        return Ok(d.out);
    }
    let top = g.top_level();
    for n in &tree.fields {
        let def = find_def(top, &n.name);
        match n.name.as_str() {
            "conditions" | "actions" | "triggers" => continue,
            "object_type_refs" => {
                let words: Vec<i64> = n
                    .value
                    .items()
                    .iter()
                    .filter_map(|w| w.first().and_then(|x| x.value.as_i64()))
                    .collect();
                let bits = set_bits(&words);
                let named: Vec<String> = bits
                    .iter()
                    .map(|&b| {
                        match g
                            .reach_names
                            .get("object_type")
                            .and_then(|t| t.get(&(b as i64)))
                        {
                            Some(name) => format!("{b} (reach: {name})"),
                            None => b.to_string(),
                        }
                    })
                    .collect();
                d.line(0, "");
                d.line(
                    0,
                    format!("== object types the script uses (bitset): {}", bits.len()),
                );
                for s in named {
                    d.line(1, s);
                }
            }
            "engine_options_disabled"
            | "engine_options_hidden"
            | "megalo_options_disabled"
            | "megalo_options_hidden" => {
                let words: Vec<i64> = n
                    .value
                    .items()
                    .iter()
                    .filter_map(|w| w.first().and_then(|x| x.value.as_i64()))
                    .collect();
                let s = ranges(&set_bits(&words));
                d.line(0, format!("{} = bits {s}", n.name));
            }
            _ => match (&n.value, def.map(|x| &x.kind)) {
                (Value::Struct(fields), Some(Kind::Ref(t)))
                    if matches!(g.type_def(t), Some(TypeDef::Struct(_)))
                        && t != "TRAITS"
                        && !t.starts_with("STRINGS(")
                        && !INLINE_TYPES.contains(&t.as_str()) =>
                {
                    d.line(0, "");
                    d.line(0, format!("== {}", n.name));
                    if let Some(TypeDef::Struct(defs)) = g.type_def(t) {
                        d.nodes(defs, fields, 1);
                    }
                }
                (Value::List(items), _) if items.is_empty() => d.node(def, n, 0),
                (Value::Struct(_) | Value::List(_) | Value::Union { .. }, _) => {
                    d.line(0, "");
                    d.line(0, format!("== {}", n.name));
                    d.node(def, n, 1);
                }
                _ => d.node(def, n, 0),
            },
        }
    }
    d.line(0, "");
    d.script(tree);
    d.line(0, "");
    if d.problems.is_empty() {
        d.line(
            0,
            "== checks: trigger ranges, inline blocks, entry points and nested trigger calls all hold",
        );
    } else {
        d.line(0, format!("== checks: {} problem(s)", d.problems.len()));
        let problems = std::mem::take(&mut d.problems);
        for p in problems {
            d.line(1, p);
        }
    }
    if !d.translations.is_empty() {
        d.line(0, "");
        d.line(0, "== translations (where a language differs from english)");
        let tr = std::mem::take(&mut d.translations);
        for (table, i, lang, text) in tr {
            d.line(1, format!("{table}[{i}] {lang}: {}", quote(&text)));
        }
    }
    Ok(d.out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Variant;

    #[test]
    fn slayer_dumps_its_script() {
        let bytes = Variant::slayer(25).write().unwrap();
        let tree = raw::decode(&bytes).unwrap();
        let text = dump(&tree, &["slayer".into()]).unwrap();
        assert!(text.contains("== script:"), "{text}");
        assert!(text.contains(".score += 1"), "{text}");
        assert!(text.contains("all hold"), "{text}");
    }

    #[test]
    fn dates_are_civil() {
        assert_eq!(
            unix_time(1_284_422_400).as_deref(),
            Some("2010-09-14 00:00:00 UTC")
        );
    }

    #[test]
    fn bit_ranges_collapse() {
        assert_eq!(ranges(&[0, 1, 2, 5, 7, 8]), "0..2, 5, 7..8");
        assert_eq!(set_bits(&[0b101, 1]), vec![0, 2, 32]);
    }
}
