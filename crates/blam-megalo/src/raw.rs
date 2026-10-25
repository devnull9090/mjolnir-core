//! A grammar-driven Megalo codec: every field of a variant, in the order
//! and widths the simulation's decoder reads them (HaloSimulation CU4
//! `0x392a40` and its callees), kept as a tree that encodes back to the same
//! bits.
//!
//! The grammar is data (`grammar/megalo_cu4.json`, see its `_meta`): field
//! kinds `u`, `s`, `bool`, `opt`, `u64`, `f32`, `bytes`, `zstring`, `ref`,
//! `array`, `repeat`, `if` and `position`, struct and tagged-union types, and
//! the condition and action lists. It also describes the map variant
//! (`map_variant`, the simulation's `0x32d810`), which
//! [`decode_map_variant`] and [`round_trip_map_variant`] use with the same
//! types. [`decode`] walks it over a bitstream and
//! [`encode`] walks it over a tree, so a grammar fix changes both at once,
//! and a tree that no longer matches its grammar (a list count past its
//! width, a union case with the wrong fields) is refused rather than written.
//!
//! Nothing is reinterpreted on the way through: compressed string tables
//! keep their compressed bytes, floats their 32 bits, strings their
//! character codes and whether a terminator was read.

use std::collections::{BTreeMap, HashMap};
use std::sync::OnceLock;

use serde_json::Value as Json;

use crate::bits::{BitReader, BitWriter};
use crate::Error;

/// The grammar the crate decodes with: CU4's reader as research read it.
pub const GRAMMAR_JSON: &str = include_str!("../grammar/megalo_cu4.json");

/// The parsed [`GRAMMAR_JSON`].
pub fn grammar() -> Result<&'static Grammar, Error> {
    static GRAMMAR: OnceLock<Result<Grammar, String>> = OnceLock::new();
    GRAMMAR
        .get_or_init(|| Grammar::from_json(GRAMMAR_JSON).map_err(|e| e.to_string()))
        .as_ref()
        .map_err(|e| Error::Grammar(e.clone()))
}

// ---------------------------------------------------------------- grammar

/// A Megalo grammar: types, the top-level field list, and the condition
/// and action tables.
#[derive(Debug, Clone)]
pub struct Grammar {
    types: HashMap<String, TypeDef>,
    top: Vec<FieldDef>,
    /// The map variant's field list (`map_variant`; empty when the grammar
    /// has none). It shares the types with the game variant.
    map_variant: Vec<FieldDef>,
    /// Condition types by id (the `CONDITION` union's cases).
    pub conditions: Vec<OpDef>,
    /// Action types by id (the `ACTION` union's cases).
    pub actions: Vec<OpDef>,
    /// Named lists a field's `hint` points into (ReachVariantTool's Halo
    /// Reach names: hints for CU4, not verified).
    pub reach_names: HashMap<String, BTreeMap<i64, String>>,
}

/// A condition or action type.
#[derive(Debug, Clone)]
pub struct OpDef {
    pub id: i64,
    pub name: String,
    /// The CU4 executor/evaluator case, when known.
    pub handler: Option<String>,
    /// One line on what the simulation does with it.
    pub semantics: String,
    /// `VERIFIED` or `INFERRED`.
    pub status: String,
}

/// A named type.
#[derive(Debug, Clone)]
pub enum TypeDef {
    /// Fields read in order.
    Struct(Vec<FieldDef>),
    /// A selector, then the fields of the case it picks.
    Union(UnionDef),
}

/// A tagged union.
#[derive(Debug, Clone)]
pub struct UnionDef {
    /// Selector width.
    pub bits: u32,
    /// The selector is stored as the read value minus one.
    pub minus1: bool,
    /// Cases by (decoded) selector value.
    pub cases: BTreeMap<i64, CaseDef>,
}

/// One case of a union.
#[derive(Debug, Clone)]
pub struct CaseDef {
    pub name: String,
    pub fields: Vec<FieldDef>,
}

/// A field of a struct or case.
#[derive(Debug, Clone)]
pub struct FieldDef {
    pub name: String,
    pub kind: Kind,
    /// Value names (keys are decoded values; bit values when `flags`).
    pub names: Option<BTreeMap<i64, String>>,
    /// `names` are bit flags, not whole values.
    pub flags: bool,
    /// Element labels of a fixed `repeat` (rating parameters, languages).
    pub element_names: Option<Vec<String>>,
    /// A [`Grammar::reach_names`] table naming the value.
    pub hint: Option<String>,
    /// The value indexes the variant's main string table.
    pub string_ref: bool,
}

/// How a field is stored.
#[derive(Debug, Clone)]
pub enum Kind {
    /// Unsigned; `minus1`: the value is the bits read minus one.
    U {
        bits: u32,
        minus1: bool,
    },
    /// Two's complement.
    S {
        bits: u32,
    },
    Bool,
    /// A presence bit (absent when it reads 1, or 0 with `present_if`),
    /// then the value when present.
    Opt {
        bits: u32,
        present_if: bool,
    },
    U64,
    F32,
    Bytes {
        count: Count,
    },
    /// Characters until a zero one or `max` of them.
    ZString {
        char_bits: u32,
        max: usize,
    },
    /// A named type.
    Ref(String),
    /// A count of `count_bits`, then that many elements.
    Array {
        count_bits: u32,
        of: Vec<FieldDef>,
    },
    /// A fixed or field-given number of elements.
    Repeat {
        count: Count,
        of: Vec<FieldDef>,
    },
    /// A map-variant position (`0x50e990` with world bounds): a bit, then
    /// x, y and z, each as wide as [`position_widths`] makes it from
    /// `precision` and the six `bounds` fields (x min, x max, y min, y max,
    /// z min, z max; `f32`s decoded earlier, in this struct or an enclosing
    /// one).
    Position {
        precision: u32,
        bounds: Vec<String>,
    },
    /// Fields read only when a test of an earlier field holds; their nodes
    /// sit in the enclosing struct.
    If {
        cond: Cond,
        then: Vec<FieldDef>,
        otherwise: Vec<FieldDef>,
    },
}

/// A repeat or byte count.
#[derive(Debug, Clone)]
pub enum Count {
    Fixed(usize),
    /// The value of an earlier field.
    Field(String),
}

/// `<field> <op> <value>` over an earlier field's decoded value.
#[derive(Debug, Clone)]
pub struct Cond {
    pub field: String,
    pub op: CondOp,
}

/// A [`Cond`] operator.
#[derive(Debug, Clone)]
pub enum CondOp {
    Eq(i64),
    Ne(i64),
    Lt(i64),
    Le(i64),
    Gt(i64),
    Ge(i64),
    In(Vec<i64>),
    /// Any of these bits set.
    And(i64),
}

impl Cond {
    fn parse(s: &str) -> Result<Cond, Error> {
        let mut parts = s.splitn(3, ' ');
        let (Some(field), Some(op), Some(value)) = (parts.next(), parts.next(), parts.next())
        else {
            return Err(Error::Grammar(format!("condition {s:?}")));
        };
        let num =
            |v: &str| parse_int(v.trim()).ok_or_else(|| Error::Grammar(format!("condition {s:?}")));
        let op = match op {
            "==" => CondOp::Eq(num(value)?),
            "!=" => CondOp::Ne(num(value)?),
            "<" => CondOp::Lt(num(value)?),
            "<=" => CondOp::Le(num(value)?),
            ">" => CondOp::Gt(num(value)?),
            ">=" => CondOp::Ge(num(value)?),
            "&" => CondOp::And(num(value)?),
            "in" => CondOp::In(value.split(',').map(num).collect::<Result<_, _>>()?),
            _ => return Err(Error::Grammar(format!("condition {s:?}: operator {op:?}"))),
        };
        Ok(Cond {
            field: field.to_string(),
            op,
        })
    }

    fn holds(&self, x: i64) -> bool {
        match &self.op {
            CondOp::Eq(v) => x == *v,
            CondOp::Ne(v) => x != *v,
            CondOp::Lt(v) => x < *v,
            CondOp::Le(v) => x <= *v,
            CondOp::Gt(v) => x > *v,
            CondOp::Ge(v) => x >= *v,
            CondOp::In(vs) => vs.contains(&x),
            CondOp::And(v) => x & *v != 0,
        }
    }
}

fn parse_int(s: &str) -> Option<i64> {
    if let Some(h) = s.strip_prefix("0x") {
        i64::from_str_radix(h, 16).ok()
    } else {
        s.parse().ok()
    }
}

fn gerr(what: impl std::fmt::Display) -> Error {
    Error::Grammar(what.to_string())
}

fn get_u32(j: &Json, key: &str, ctx: &str) -> Result<u32, Error> {
    j.get(key)
        .and_then(Json::as_u64)
        .and_then(|v| u32::try_from(v).ok())
        .ok_or_else(|| gerr(format!("{ctx}: `{key}` missing or not a number")))
}

fn names_map(j: &Json, ctx: &str) -> Result<BTreeMap<i64, String>, Error> {
    let obj = j
        .as_object()
        .ok_or_else(|| gerr(format!("{ctx}: names are not an object")))?;
    let mut out = BTreeMap::new();
    for (k, v) in obj {
        let key = parse_int(k).ok_or_else(|| gerr(format!("{ctx}: name key {k:?}")))?;
        let name = v
            .as_str()
            .ok_or_else(|| gerr(format!("{ctx}: name for {k} is not a string")))?;
        out.insert(key, name.to_string());
    }
    Ok(out)
}

fn count_of(j: &Json, ctx: &str) -> Result<Count, Error> {
    match j.get("count") {
        Some(Json::Number(n)) => n
            .as_u64()
            .map(|v| Count::Fixed(v as usize))
            .ok_or_else(|| gerr(format!("{ctx}: count"))),
        Some(Json::String(s)) => Ok(Count::Field(s.clone())),
        _ => Err(gerr(format!("{ctx}: count missing"))),
    }
}

impl FieldDef {
    fn from_json(j: &Json, ctx: &str) -> Result<FieldDef, Error> {
        let kind_s = j
            .get("kind")
            .and_then(Json::as_str)
            .ok_or_else(|| gerr(format!("{ctx}: field without a kind")))?;
        let name = j
            .get("name")
            .and_then(Json::as_str)
            .unwrap_or(kind_s)
            .to_string();
        let ctx = format!("{ctx}.{name}");
        let fields = |key: &str| -> Result<Vec<FieldDef>, Error> {
            match j.get(key) {
                None | Some(Json::Null) => Ok(Vec::new()),
                Some(Json::Array(a)) => a.iter().map(|f| FieldDef::from_json(f, &ctx)).collect(),
                Some(_) => Err(gerr(format!("{ctx}: `{key}` is not a list"))),
            }
        };
        let kind = match kind_s {
            "u" => Kind::U {
                bits: get_u32(j, "bits", &ctx)?,
                minus1: j.get("minus1").and_then(Json::as_bool).unwrap_or(false),
            },
            "s" => Kind::S {
                bits: get_u32(j, "bits", &ctx)?,
            },
            "bool" => Kind::Bool,
            "opt" => Kind::Opt {
                bits: get_u32(j, "bits", &ctx)?,
                present_if: j.get("present_if").and_then(Json::as_u64) == Some(1),
            },
            "u64" => Kind::U64,
            "f32" => Kind::F32,
            "bytes" => Kind::Bytes {
                count: count_of(j, &ctx)?,
            },
            "zstring" => Kind::ZString {
                char_bits: get_u32(j, "char_bits", &ctx)?,
                max: get_u32(j, "max", &ctx)? as usize,
            },
            "ref" => Kind::Ref(
                j.get("type")
                    .and_then(Json::as_str)
                    .ok_or_else(|| gerr(format!("{ctx}: ref without a type")))?
                    .to_string(),
            ),
            "array" => Kind::Array {
                count_bits: get_u32(j, "count_bits", &ctx)?,
                of: fields("of")?,
            },
            "repeat" => Kind::Repeat {
                count: count_of(j, &ctx)?,
                of: fields("of")?,
            },
            "position" => {
                let bounds: Vec<String> = j
                    .get("bounds")
                    .and_then(Json::as_array)
                    .map(|a| {
                        a.iter()
                            .filter_map(Json::as_str)
                            .map(str::to_string)
                            .collect()
                    })
                    .unwrap_or_default();
                if bounds.len() != 6 {
                    return Err(gerr(format!("{ctx}: a position names six bounds")));
                }
                Kind::Position {
                    precision: get_u32(j, "precision", &ctx)?,
                    bounds,
                }
            }
            "if" => Kind::If {
                cond: Cond::parse(
                    j.get("when")
                        .and_then(Json::as_str)
                        .ok_or_else(|| gerr(format!("{ctx}: if without when")))?,
                )?,
                then: fields("then")?,
                otherwise: fields("else")?,
            },
            other => return Err(gerr(format!("{ctx}: unknown kind {other:?}"))),
        };
        match kind {
            Kind::U { bits, .. } | Kind::S { bits } | Kind::Opt { bits, .. }
                if bits == 0 || bits > 63 =>
            {
                return Err(gerr(format!("{ctx}: width {bits}")));
            }
            _ => {}
        }
        let (names, flags) = match (j.get("enum"), j.get("bits_enum")) {
            (Some(e), _) => (
                Some(names_map(e, &ctx)?),
                j.get("flags").and_then(Json::as_bool).unwrap_or(false),
            ),
            (None, Some(e)) => (Some(names_map(e, &ctx)?), true),
            (None, None) => (None, false),
        };
        let element_names = j
            .get("names")
            .or_else(|| j.get("languages"))
            .and_then(Json::as_array)
            .map(|a| {
                a.iter()
                    .map(|v| v.as_str().unwrap_or("?").to_string())
                    .collect()
            });
        Ok(FieldDef {
            name,
            kind,
            names,
            flags,
            element_names,
            hint: j.get("hint").and_then(Json::as_str).map(str::to_string),
            string_ref: j.get("string_ref").and_then(Json::as_bool).unwrap_or(false),
        })
    }
}

fn op_list(j: &Json, key: &str) -> Result<(Vec<OpDef>, BTreeMap<i64, CaseDef>), Error> {
    let list = j
        .get(key)
        .and_then(Json::as_array)
        .ok_or_else(|| gerr(format!("`{key}` list missing")))?;
    let mut ops = Vec::new();
    let mut cases = BTreeMap::new();
    for (i, e) in list.iter().enumerate() {
        let id = e
            .get("id")
            .and_then(Json::as_i64)
            .ok_or_else(|| gerr(format!("{key}[{i}]: id")))?;
        if id != i as i64 {
            return Err(gerr(format!("{key}[{i}]: id {id} out of order")));
        }
        let name = e
            .get("name")
            .and_then(Json::as_str)
            .unwrap_or("?")
            .to_string();
        let ctx = format!("{key}[{id}]");
        let fields = match e.get("params") {
            Some(Json::Array(a)) => a
                .iter()
                .map(|f| FieldDef::from_json(f, &ctx))
                .collect::<Result<Vec<_>, _>>()?,
            _ => Vec::new(),
        };
        let s = |k: &str| e.get(k).and_then(Json::as_str).map(str::to_string);
        ops.push(OpDef {
            id,
            name: name.clone(),
            handler: s("cu4_handler"),
            semantics: s("semantics").unwrap_or_default(),
            status: s("status").unwrap_or_default(),
        });
        cases.insert(id, CaseDef { name, fields });
    }
    Ok((ops, cases))
}

impl Grammar {
    /// Parse a grammar in the `grammar/megalo_cu4.json` format.
    pub fn from_json(text: &str) -> Result<Grammar, Error> {
        let j: Json = serde_json::from_str(text).map_err(|e| gerr(format!("JSON: {e}")))?;
        let (conditions, condition_cases) = match j.get("conditions") {
            Some(_) => op_list(&j, "conditions")?,
            None => (Vec::new(), BTreeMap::new()),
        };
        let (actions, action_cases) = match j.get("actions") {
            Some(_) => op_list(&j, "actions")?,
            None => (Vec::new(), BTreeMap::new()),
        };
        let mut types = HashMap::new();
        let tobj = j
            .get("types")
            .and_then(Json::as_object)
            .ok_or_else(|| gerr("`types` missing"))?;
        for (name, t) in tobj {
            let ctx = name.as_str();
            let def = if let Some(sel) = t.get("selector") {
                let bits = get_u32(sel, "bits", ctx)?;
                let minus1 = sel.get("minus1").and_then(Json::as_bool).unwrap_or(false);
                let cases = match t.get("cases_from").and_then(Json::as_str) {
                    Some("conditions") => condition_cases.clone(),
                    Some("actions") => action_cases.clone(),
                    Some(other) => return Err(gerr(format!("{ctx}: cases_from {other:?}"))),
                    None => {
                        let cobj = t
                            .get("cases")
                            .and_then(Json::as_object)
                            .ok_or_else(|| gerr(format!("{ctx}: union without cases")))?;
                        let mut cases = BTreeMap::new();
                        for (k, c) in cobj {
                            let key =
                                parse_int(k).ok_or_else(|| gerr(format!("{ctx}: case {k:?}")))?;
                            let cctx = format!("{ctx}[{k}]");
                            let fields = match c.get("fields") {
                                Some(Json::Array(a)) => a
                                    .iter()
                                    .map(|f| FieldDef::from_json(f, &cctx))
                                    .collect::<Result<Vec<_>, _>>()?,
                                _ => Vec::new(),
                            };
                            let cname = c
                                .get("name")
                                .and_then(Json::as_str)
                                .unwrap_or("?")
                                .to_string();
                            cases.insert(
                                key,
                                CaseDef {
                                    name: cname,
                                    fields,
                                },
                            );
                        }
                        cases
                    }
                };
                TypeDef::Union(UnionDef {
                    bits,
                    minus1,
                    cases,
                })
            } else if let Some(Json::Array(fs)) = t.get("fields") {
                TypeDef::Struct(
                    fs.iter()
                        .map(|f| FieldDef::from_json(f, ctx))
                        .collect::<Result<_, _>>()?,
                )
            } else {
                return Err(gerr(format!("{ctx}: neither fields nor a selector")));
            };
            types.insert(name.clone(), def);
        }
        let top = j
            .get("top_level")
            .and_then(Json::as_array)
            .ok_or_else(|| gerr("`top_level` missing"))?
            .iter()
            .map(|f| FieldDef::from_json(f, "top"))
            .collect::<Result<Vec<_>, _>>()?;
        let map_variant = match j.get("map_variant") {
            None | Some(Json::Null) => Vec::new(),
            Some(Json::Array(a)) => a
                .iter()
                .map(|f| FieldDef::from_json(f, "map_variant"))
                .collect::<Result<Vec<_>, _>>()?,
            Some(_) => return Err(gerr("`map_variant` is not a list")),
        };
        let mut reach_names = HashMap::new();
        if let Some(Json::Object(r)) = j.get("reach_names") {
            for (k, v) in r {
                reach_names.insert(k.clone(), names_map(v, k)?);
            }
        }
        let g = Grammar {
            types,
            top,
            map_variant,
            conditions,
            actions,
            reach_names,
        };
        g.check()?;
        Ok(g)
    }

    /// Every `ref` names a type.
    fn check(&self) -> Result<(), Error> {
        fn walk(g: &Grammar, fs: &[FieldDef], ctx: &str) -> Result<(), Error> {
            for f in fs {
                match &f.kind {
                    Kind::Ref(t) if !g.types.contains_key(t) => {
                        return Err(gerr(format!("{ctx}.{}: unknown type {t}", f.name)));
                    }
                    Kind::Array { of, .. } | Kind::Repeat { of, .. } => walk(g, of, ctx)?,
                    Kind::If {
                        then, otherwise, ..
                    } => {
                        walk(g, then, ctx)?;
                        walk(g, otherwise, ctx)?;
                    }
                    _ => {}
                }
            }
            Ok(())
        }
        walk(self, &self.top, "top")?;
        walk(self, &self.map_variant, "map_variant")?;
        for (name, t) in &self.types {
            match t {
                TypeDef::Struct(fs) => walk(self, fs, name)?,
                TypeDef::Union(u) => {
                    for c in u.cases.values() {
                        walk(self, &c.fields, name)?;
                    }
                }
            }
        }
        Ok(())
    }

    /// A named type.
    pub fn type_def(&self, name: &str) -> Option<&TypeDef> {
        self.types.get(name)
    }

    /// The map variant's fields, in read order (empty without one).
    pub fn map_variant_fields(&self) -> &[FieldDef] {
        &self.map_variant
    }

    /// The top-level fields, in read order.
    pub fn top_level(&self) -> &[FieldDef] {
        &self.top
    }
}

// ---------------------------------------------------------------- tree

/// One decoded field.
#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub name: String,
    /// First bit of the field, counted from the start of the buffer.
    pub at: usize,
    /// Bits the field took.
    pub len: usize,
    pub value: Value,
}

/// A decoded value.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    /// `u`, `s` and `bool`: what the bits stand for (the bits read minus one
    /// for `minus1`, sign-extended for `s`).
    Int {
        bits: u32,
        value: i64,
    },
    /// `opt`: `None` when the presence bit says absent.
    Opt {
        bits: u32,
        value: Option<u64>,
    },
    U64(u64),
    /// An `f32` as its 32 bits (never through a float, so every payload
    /// survives).
    F32(u32),
    Bytes(Vec<u8>),
    /// A `zstring`'s character codes, and whether a zero one ended it (not
    /// when `max` characters were read first).
    Text {
        chars: Vec<u32>,
        terminated: bool,
    },
    /// A struct type's fields.
    Struct(Vec<Node>),
    /// A union: the decoded selector, its case's name, and its fields.
    Union {
        selector: i64,
        case: String,
        fields: Vec<Node>,
    },
    /// `array` and `repeat` elements, each its fields.
    List(Vec<Vec<Node>>),
}

impl Value {
    /// The number a `when` test or a count reads: `Int`, an `opt` (-1 when
    /// absent), a `u64` or a union's selector.
    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Value::Int { value, .. } => Some(*value),
            Value::Opt { value, .. } => Some(value.map_or(-1, |v| v as i64)),
            Value::U64(v) => i64::try_from(*v).ok(),
            Value::Union { selector, .. } => Some(*selector),
            _ => None,
        }
    }

    /// The fields of a struct, a union case or a list element.
    pub fn fields(&self) -> &[Node] {
        match self {
            Value::Struct(f) | Value::Union { fields: f, .. } => f,
            _ => &[],
        }
    }

    /// The elements of a list.
    pub fn items(&self) -> &[Vec<Node>] {
        match self {
            Value::List(items) => items,
            _ => &[],
        }
    }

    /// A zstring as text (lossy).
    pub fn text(&self) -> Option<String> {
        match self {
            Value::Text { chars, .. } => Some(
                chars
                    .iter()
                    .map(|&c| char::from_u32(c).unwrap_or('\u{fffd}'))
                    .collect(),
            ),
            _ => None,
        }
    }
}

/// Look a field up by name among sibling nodes.
pub fn field<'a>(fields: &'a [Node], name: &str) -> Option<&'a Node> {
    fields.iter().find(|n| n.name == name)
}

/// A field's number (see [`Value::as_i64`]).
pub fn int(fields: &[Node], name: &str) -> Option<i64> {
    field(fields, name).and_then(|n| n.value.as_i64())
}

/// A decoded variant.
#[derive(Debug, Clone, PartialEq)]
pub struct Tree {
    /// The top-level fields.
    pub fields: Vec<Node>,
    /// The bit the stream began at.
    pub start: usize,
    /// The bit after the last one read.
    pub end: usize,
}

impl Tree {
    /// The encoding version (0x6a, or 0x6b for MCC's title update; anything
    /// else and the simulation reads nothing more).
    pub fn version(&self) -> Option<i64> {
        int(&self.fields, "encoding_version")
    }

    /// The simulation reads the rest only for versions 0x6a and 0x6b.
    pub fn is_megalo(&self) -> bool {
        matches!(self.version(), Some(0x6a | 0x6b))
    }
}

// ---------------------------------------------------------------- decode

/// The fields decoded so far at each enclosing level, for `when` tests and
/// counts.
struct Scope<'a> {
    fields: &'a [Node],
    parent: Option<&'a Scope<'a>>,
}

impl Scope<'_> {
    fn lookup(&self, name: &str) -> Option<i64> {
        int(self.fields, name).or_else(|| self.parent.and_then(|p| p.lookup(name)))
    }

    fn lookup_f32(&self, name: &str) -> Option<f32> {
        match field(self.fields, name).map(|n| &n.value) {
            Some(Value::F32(bits)) => Some(f32::from_bits(*bits)),
            _ => self.parent.and_then(|p| p.lookup_f32(name)),
        }
    }
}

/// The bit widths of a map-variant position's x, y and z (`0x512fc0`):
/// each axis is cut into steps of 1/60 world unit, finer by a factor of two
/// per `precision` bit past 16, and gets enough bits to count the steps
/// across its bounds (rounded up), at most 26.
pub fn position_widths(precision: u32, bounds: [f32; 6]) -> [u32; 3] {
    let (fine, step) = if precision < 17 {
        let f = (1u32 << (16 - precision)) as f32;
        (f * 0.008_333_334, f * 0.016_666_668)
    } else {
        let f = (1u32 << (precision - 16)) as f32;
        (0.008_333_334 / f, 0.016_666_668 / f)
    };
    if fine < 0.0001 {
        return [26; 3];
    }
    let axis = |lo: f32, hi: f32| -> u32 {
        let steps = ((hi - lo) / step).ceil() as i64;
        let n = steps.min(0x80_0000) as u32;
        if n == 0 {
            return 0;
        }
        let high = 31 - n.leading_zeros();
        (high + u32::from(n & ((1 << high) - 1) != 0)).min(26)
    };
    [
        axis(bounds[0], bounds[1]),
        axis(bounds[2], bounds[3]),
        axis(bounds[4], bounds[5]),
    ]
}

/// The widths of a `position` field from the bounds in scope.
fn scope_widths(
    precision: u32,
    bounds: &[String],
    fields: &[Node],
    parent: Option<&Scope>,
    path: &str,
) -> Result<[u32; 3], Error> {
    let s = Scope { fields, parent };
    let mut b = [0f32; 6];
    for (slot, name) in b.iter_mut().zip(bounds) {
        *slot = s.lookup_f32(name).ok_or_else(|| Error::Mismatch {
            path: path.to_string(),
            msg: format!("bound `{name}` not decoded before it"),
        })?;
    }
    Ok(position_widths(precision, b))
}

fn scope_value(fields: &[Node], parent: Option<&Scope>, name: &str) -> Option<i64> {
    let s = Scope { fields, parent };
    s.lookup(name)
}

fn resolve_count(
    count: &Count,
    fields: &[Node],
    parent: Option<&Scope>,
    path: &str,
) -> Result<usize, Error> {
    match count {
        Count::Fixed(n) => Ok(*n),
        Count::Field(f) => {
            let v = scope_value(fields, parent, f).ok_or_else(|| Error::Mismatch {
                path: path.to_string(),
                msg: format!("count field `{f}` not decoded before it"),
            })?;
            usize::try_from(v).map_err(|_| Error::Mismatch {
                path: path.to_string(),
                msg: format!("count field `{f}` is {v}"),
            })
        }
    }
}

fn eval_cond(
    cond: &Cond,
    fields: &[Node],
    parent: Option<&Scope>,
    path: &str,
) -> Result<bool, Error> {
    let v = scope_value(fields, parent, &cond.field).ok_or_else(|| Error::Mismatch {
        path: path.to_string(),
        msg: format!("`when` field `{}` not decoded before it", cond.field),
    })?;
    Ok(cond.holds(v))
}

struct Decoder<'g, 'b> {
    g: &'g Grammar,
    r: BitReader<'b>,
    path: Vec<String>,
}

impl Decoder<'_, '_> {
    fn path(&self) -> String {
        self.path.join(".")
    }

    fn read(&mut self, bits: u32) -> Result<u64, Error> {
        self.r.read(bits).map_err(|e| match e {
            Error::Truncated { at, want } => Error::Decode {
                path: self.path.join("."),
                at,
                msg: format!("the stream ends; {want} more bit(s) wanted"),
            },
            other => other,
        })
    }

    fn fields(
        &mut self,
        defs: &[FieldDef],
        parent: Option<&Scope>,
        out: &mut Vec<Node>,
    ) -> Result<(), Error> {
        for d in defs {
            self.field(d, parent, out)?;
        }
        Ok(())
    }

    fn list(
        &mut self,
        n: usize,
        of: &[FieldDef],
        parent: Option<&Scope>,
        out: &[Node],
    ) -> Result<Vec<Vec<Node>>, Error> {
        let mut items = Vec::with_capacity(n.min(4096));
        for i in 0..n {
            let mut item = Vec::new();
            self.path.push(format!("[{i}]"));
            let scope = Scope {
                fields: out,
                parent,
            };
            self.fields(of, Some(&scope), &mut item)?;
            self.path.pop();
            items.push(item);
        }
        Ok(items)
    }

    fn field(
        &mut self,
        d: &FieldDef,
        parent: Option<&Scope>,
        out: &mut Vec<Node>,
    ) -> Result<(), Error> {
        let at = self.r.position();
        self.path.push(d.name.clone());
        let value = match &d.kind {
            Kind::If {
                cond,
                then,
                otherwise,
            } => {
                let taken = eval_cond(cond, out, parent, &self.path())?;
                self.path.pop();
                return self.fields(if taken { then } else { otherwise }, parent, out);
            }
            Kind::U { bits, minus1 } => {
                let raw = self.read(*bits)? as i64;
                Value::Int {
                    bits: *bits,
                    value: raw - i64::from(*minus1),
                }
            }
            Kind::S { bits } => {
                let raw = self.read(*bits)?;
                let sign = 1u64 << (bits - 1);
                let value = if raw & sign != 0 {
                    raw as i64 - (1i64 << bits)
                } else {
                    raw as i64
                };
                Value::Int { bits: *bits, value }
            }
            Kind::Bool => Value::Int {
                bits: 1,
                value: self.read(1)? as i64,
            },
            Kind::Opt { bits, present_if } => {
                let flag = self.read(1)? == 1;
                let value = if flag == *present_if {
                    Some(self.read(*bits)?)
                } else {
                    None
                };
                Value::Opt { bits: *bits, value }
            }
            Kind::U64 => Value::U64(self.read(64)?),
            Kind::F32 => Value::F32(self.read(32)? as u32),
            Kind::Bytes { count } => {
                let n = resolve_count(count, out, parent, &self.path())?;
                let mut b = Vec::with_capacity(n.min(1 << 16));
                for _ in 0..n {
                    b.push(self.read(8)? as u8);
                }
                Value::Bytes(b)
            }
            Kind::ZString { char_bits, max } => {
                let mut chars = Vec::new();
                let mut terminated = false;
                while chars.len() < *max {
                    let c = self.read(*char_bits)? as u32;
                    if c == 0 {
                        terminated = true;
                        break;
                    }
                    chars.push(c);
                }
                Value::Text { chars, terminated }
            }
            Kind::Ref(t) => self.typed(t)?,
            Kind::Position { precision, bounds } => {
                let widths = scope_widths(*precision, bounds, out, parent, &self.path())?;
                let mut nodes = Vec::with_capacity(4);
                for (name, bits) in [
                    ("flag", 1),
                    ("x", widths[0]),
                    ("y", widths[1]),
                    ("z", widths[2]),
                ] {
                    let at = self.r.position();
                    let value = self.read(bits)? as i64;
                    nodes.push(Node {
                        name: name.to_string(),
                        at,
                        len: bits as usize,
                        value: Value::Int { bits, value },
                    });
                }
                Value::Struct(nodes)
            }
            Kind::Array { count_bits, of } => {
                let n = self.read(*count_bits)? as usize;
                Value::List(self.list(n, of, parent, out)?)
            }
            Kind::Repeat { count, of } => {
                let n = resolve_count(count, out, parent, &self.path())?;
                Value::List(self.list(n, of, parent, out)?)
            }
        };
        self.path.pop();
        out.push(Node {
            name: d.name.clone(),
            at,
            len: self.r.position() - at,
            value,
        });
        Ok(())
    }

    fn typed(&mut self, t: &str) -> Result<Value, Error> {
        let g = self.g;
        let def = g
            .types
            .get(t)
            .ok_or_else(|| gerr(format!("unknown type {t}")))?;
        match def {
            TypeDef::Struct(fs) => {
                let mut out = Vec::new();
                self.fields(fs, None, &mut out)?;
                Ok(Value::Struct(out))
            }
            TypeDef::Union(u) => {
                let at = self.r.position();
                let selector = self.read(u.bits)? as i64 - i64::from(u.minus1);
                let case = u.cases.get(&selector).ok_or_else(|| Error::UnknownCase {
                    ty: t.to_string(),
                    value: selector,
                    path: self.path(),
                    at,
                })?;
                let mut out = Vec::new();
                self.path.push(case.name.clone());
                self.fields(&case.fields, None, &mut out)?;
                self.path.pop();
                Ok(Value::Union {
                    selector,
                    case: case.name.clone(),
                    fields: out,
                })
            }
        }
    }
}

/// Decode a variant from the start of `bytes` with the crate's grammar.
pub fn decode(bytes: &[u8]) -> Result<Tree, Error> {
    decode_at(bytes, 0)
}

/// Decode a variant that begins `start` bits into `bytes` (a BLF `mpvr`
/// payload begins with a 4-bit engine type).
pub fn decode_at(bytes: &[u8], start: usize) -> Result<Tree, Error> {
    grammar()?.decode_at(bytes, start)
}

/// Decode a map variant (an `mvar` payload) with the crate's grammar.
pub fn decode_map_variant(bytes: &[u8]) -> Result<Tree, Error> {
    grammar()?.decode_map_variant_at(bytes, 0)
}

impl Grammar {
    /// Decode a variant that begins `start` bits into `bytes`.
    pub fn decode_at(&self, bytes: &[u8], start: usize) -> Result<Tree, Error> {
        self.decode_fields_at(&self.top, bytes, start)
    }

    /// Decode a map variant that begins `start` bits into `bytes`.
    pub fn decode_map_variant_at(&self, bytes: &[u8], start: usize) -> Result<Tree, Error> {
        if self.map_variant.is_empty() {
            return Err(gerr("this grammar has no `map_variant`"));
        }
        self.decode_fields_at(&self.map_variant, bytes, start)
    }

    /// Encode a map-variant tree.
    pub fn encode_map_variant_into(&self, tree: &Tree, w: &mut BitWriter) -> Result<(), Error> {
        self.encode_fields_into(&self.map_variant, tree, w)
    }

    fn decode_fields_at(
        &self,
        top: &[FieldDef],
        bytes: &[u8],
        start: usize,
    ) -> Result<Tree, Error> {
        let mut r = BitReader::new(bytes);
        r.seek(start)?;
        let mut d = Decoder {
            g: self,
            r,
            path: Vec::new(),
        };
        let mut fields = Vec::new();
        d.fields(top, None, &mut fields)?;
        Ok(Tree {
            fields,
            start,
            end: d.r.position(),
        })
    }

    /// Encode a tree; `w` may already hold a prefix (a BLF engine type).
    pub fn encode_into(&self, tree: &Tree, w: &mut BitWriter) -> Result<(), Error> {
        self.encode_fields_into(&self.top, tree, w)
    }

    fn encode_fields_into(
        &self,
        top: &[FieldDef],
        tree: &Tree,
        w: &mut BitWriter,
    ) -> Result<(), Error> {
        let mut e = Encoder {
            g: self,
            w,
            path: Vec::new(),
        };
        let mut i = 0;
        e.fields(top, &tree.fields, &mut i, None)?;
        if i != tree.fields.len() {
            return Err(Error::Mismatch {
                path: tree.fields[i].name.clone(),
                msg: "a field the grammar does not have here".into(),
            });
        }
        Ok(())
    }
}

// ---------------------------------------------------------------- encode

struct Encoder<'g, 'w> {
    g: &'g Grammar,
    w: &'w mut BitWriter,
    path: Vec<String>,
}

impl Encoder<'_, '_> {
    fn mismatch(&self, msg: impl Into<String>) -> Error {
        Error::Mismatch {
            path: self.path.join("."),
            msg: msg.into(),
        }
    }

    fn put(&mut self, v: u64, bits: u32) -> Result<(), Error> {
        let path = self.path.join(".");
        self.w.write(v, bits).map_err(|e| Error::Mismatch {
            path,
            msg: e.to_string(),
        })
    }

    /// Encode `defs` from `nodes[*i..]`, advancing `*i` past what they used.
    fn fields(
        &mut self,
        defs: &[FieldDef],
        nodes: &[Node],
        i: &mut usize,
        parent: Option<&Scope>,
    ) -> Result<(), Error> {
        for d in defs {
            if let Kind::If {
                cond,
                then,
                otherwise,
            } = &d.kind
            {
                let taken = eval_cond(cond, &nodes[..*i], parent, &self.path.join("."))?;
                self.fields(if taken { then } else { otherwise }, nodes, i, parent)?;
                continue;
            }
            let node = nodes.get(*i).ok_or_else(|| Error::Mismatch {
                path: self.path.join("."),
                msg: format!("field `{}` missing", d.name),
            })?;
            if node.name != d.name {
                return Err(self.mismatch(format!(
                    "field `{}` where the grammar has `{}`",
                    node.name, d.name
                )));
            }
            self.path.push(d.name.clone());
            self.field(d, node, &nodes[..*i], parent)?;
            self.path.pop();
            *i += 1;
        }
        Ok(())
    }

    fn list(
        &mut self,
        of: &[FieldDef],
        items: &[Vec<Node>],
        before: &[Node],
        parent: Option<&Scope>,
    ) -> Result<(), Error> {
        for (k, item) in items.iter().enumerate() {
            self.path.push(format!("[{k}]"));
            let scope = Scope {
                fields: before,
                parent,
            };
            let mut j = 0;
            self.fields(of, item, &mut j, Some(&scope))?;
            if j != item.len() {
                return Err(self.mismatch(format!("extra field `{}`", item[j].name)));
            }
            self.path.pop();
        }
        Ok(())
    }

    fn field(
        &mut self,
        d: &FieldDef,
        node: &Node,
        before: &[Node],
        parent: Option<&Scope>,
    ) -> Result<(), Error> {
        let wrong =
            |e: &Self| e.mismatch(format!("value {:?} for a {:?} field", node.value, d.kind));
        match (&d.kind, &node.value) {
            (Kind::U { bits, minus1 }, Value::Int { value, .. }) => {
                let raw = value + i64::from(*minus1);
                if raw < 0 {
                    return Err(self.mismatch(format!("{value} is below the field's range")));
                }
                self.put(raw as u64, *bits)
            }
            (Kind::S { bits }, Value::Int { value, .. }) => {
                let path = self.path.join(".");
                self.w
                    .write_signed(*value, *bits)
                    .map_err(|e| Error::Mismatch {
                        path,
                        msg: e.to_string(),
                    })
            }
            (Kind::Bool, Value::Int { value, .. }) => match value {
                0 | 1 => self.put(*value as u64, 1),
                _ => Err(self.mismatch(format!("{value} for a bool"))),
            },
            (Kind::Opt { bits, present_if }, Value::Opt { value, .. }) => match value {
                Some(v) => {
                    self.put(u64::from(*present_if), 1)?;
                    self.put(*v, *bits)
                }
                None => self.put(u64::from(!*present_if), 1),
            },
            (Kind::U64, Value::U64(v)) => self.put(*v, 64),
            (Kind::F32, Value::F32(v)) => self.put(u64::from(*v), 32),
            (Kind::Bytes { count }, Value::Bytes(b)) => {
                let n = resolve_count(count, before, parent, &self.path.join("."))?;
                if n != b.len() {
                    return Err(
                        self.mismatch(format!("{} bytes where the count says {n}", b.len()))
                    );
                }
                for &x in b {
                    self.put(u64::from(x), 8)?;
                }
                Ok(())
            }
            (Kind::ZString { char_bits, max }, Value::Text { chars, terminated }) => {
                if chars.len() > *max || (!terminated && chars.len() != *max) {
                    return Err(self.mismatch(format!(
                        "{} characters ({}terminated); at most {max}, unterminated only at {max}",
                        chars.len(),
                        if *terminated { "" } else { "un" }
                    )));
                }
                for &c in chars {
                    if c == 0 {
                        return Err(self.mismatch("a zero character inside a string"));
                    }
                    self.put(u64::from(c), *char_bits)?;
                }
                if *terminated {
                    self.put(0, *char_bits)?;
                }
                Ok(())
            }
            (Kind::Ref(t), v) => self.typed(t, v),
            (Kind::Position { precision, bounds }, Value::Struct(nodes)) => {
                let widths =
                    scope_widths(*precision, bounds, before, parent, &self.path.join("."))?;
                let want = [1, widths[0], widths[1], widths[2]];
                if nodes.len() != 4 {
                    return Err(self.mismatch(format!("{} position fields", nodes.len())));
                }
                for (n, bits) in nodes.iter().zip(want) {
                    let v = n.value.as_i64().ok_or_else(|| wrong(self))?;
                    if v < 0 {
                        return Err(wrong(self));
                    }
                    self.put(v as u64, bits)?;
                }
                Ok(())
            }
            (Kind::Array { count_bits, of }, Value::List(items)) => {
                self.put(items.len() as u64, *count_bits)?;
                self.list(of, items, before, parent)
            }
            (Kind::Repeat { count, of }, Value::List(items)) => {
                let n = resolve_count(count, before, parent, &self.path.join("."))?;
                if n != items.len() {
                    return Err(
                        self.mismatch(format!("{} elements where the count says {n}", items.len()))
                    );
                }
                self.list(of, items, before, parent)
            }
            _ => Err(wrong(self)),
        }
    }

    fn typed(&mut self, t: &str, v: &Value) -> Result<(), Error> {
        let g = self.g;
        let def = g
            .types
            .get(t)
            .ok_or_else(|| gerr(format!("unknown type {t}")))?;
        match (def, v) {
            (TypeDef::Struct(fs), Value::Struct(nodes)) => {
                let mut i = 0;
                self.fields(fs, nodes, &mut i, None)?;
                if i != nodes.len() {
                    return Err(self.mismatch(format!("extra field `{}`", nodes[i].name)));
                }
                Ok(())
            }
            (
                TypeDef::Union(u),
                Value::Union {
                    selector, fields, ..
                },
            ) => {
                let case = u
                    .cases
                    .get(selector)
                    .ok_or_else(|| self.mismatch(format!("{t} has no case {selector}")))?;
                let raw = selector + i64::from(u.minus1);
                if raw < 0 {
                    return Err(self.mismatch(format!("{t} selector {selector}")));
                }
                self.put(raw as u64, u.bits)?;
                self.path.push(case.name.clone());
                let mut i = 0;
                self.fields(&case.fields, fields, &mut i, None)?;
                if i != fields.len() {
                    return Err(self.mismatch(format!("extra field `{}`", fields[i].name)));
                }
                self.path.pop();
                Ok(())
            }
            _ => Err(self.mismatch(format!("a {t} where the value is {v:?}"))),
        }
    }
}

/// Encode a tree with the crate's grammar: the bytes, the last one
/// zero-padded.
pub fn encode(tree: &Tree) -> Result<Vec<u8>, Error> {
    let mut w = BitWriter::new();
    grammar()?.encode_into(tree, &mut w)?;
    Ok(w.finish())
}

/// What a round trip of `bytes` showed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RoundTrip {
    /// Bits the variant took (from its first bit).
    pub bits: usize,
    /// Bits after it to the end of the buffer.
    pub trailing_bits: usize,
    /// Set trailing bits (all zero when the decoder read everything).
    pub trailing_ones: usize,
}

/// Decode `bytes` from bit `start`, encode the tree after `prefix` (bits
/// written first, as `(value, width)`), and check the result equals `bytes`
/// up to the decoded length. A mismatch names the first differing bit and
/// the field holding it.
pub fn round_trip(bytes: &[u8], start: usize, prefix: &[(u64, u32)]) -> Result<RoundTrip, Error> {
    let g = grammar()?;
    round_trip_fields(g, &g.top, bytes, start, prefix)
}

/// [`round_trip`] for a map variant (an `mvar` payload, from bit 0).
pub fn round_trip_map_variant(bytes: &[u8]) -> Result<RoundTrip, Error> {
    let g = grammar()?;
    if g.map_variant.is_empty() {
        return Err(gerr("this grammar has no `map_variant`"));
    }
    round_trip_fields(g, &g.map_variant, bytes, 0, &[])
}

fn round_trip_fields(
    g: &Grammar,
    top: &[FieldDef],
    bytes: &[u8],
    start: usize,
    prefix: &[(u64, u32)],
) -> Result<RoundTrip, Error> {
    let tree = g.decode_fields_at(top, bytes, start)?;
    let mut w = BitWriter::new();
    for &(v, bits) in prefix {
        w.write(v, bits)?;
    }
    if w.len() != start {
        return Err(Error::Mismatch {
            path: String::new(),
            msg: format!("a {}-bit prefix for a stream at bit {start}", w.len()),
        });
    }
    g.encode_fields_into(top, &tree, &mut w)?;
    let written = w.len();
    let out = w.finish();
    if written != tree.end {
        return Err(Error::Mismatch {
            path: String::new(),
            msg: format!("encoded {written} bits, decoded {}", tree.end),
        });
    }
    let bit = |b: &[u8], i: usize| b.get(i / 8).is_some_and(|x| x >> (7 - i % 8) & 1 == 1);
    if let Some(i) = (0..written).find(|&i| bit(&out, i) != bit(bytes, i)) {
        let path = locate(&tree.fields, i).unwrap_or_default();
        return Err(Error::Mismatch {
            path,
            msg: format!("bit {i} differs after a round trip"),
        });
    }
    let total = bytes.len() * 8;
    let trailing_ones = (written..total).filter(|&i| bit(bytes, i)).count();
    Ok(RoundTrip {
        bits: written - start,
        trailing_bits: total.saturating_sub(written),
        trailing_ones,
    })
}

/// The path of the innermost field holding bit `at`.
pub fn locate(fields: &[Node], at: usize) -> Option<String> {
    for n in fields {
        if at >= n.at && at < n.at + n.len {
            let inner = match &n.value {
                Value::Struct(f) | Value::Union { fields: f, .. } => locate(f, at),
                Value::List(items) => items
                    .iter()
                    .enumerate()
                    .find_map(|(k, item)| locate(item, at).map(|p| format!("[{k}].{p}"))),
                _ => None,
            };
            return Some(match inner {
                Some(p) if p.starts_with('[') => format!("{}{p}", n.name),
                Some(p) => format!("{}.{p}", n.name),
                None => n.name.clone(),
            });
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Forge World's bounds, from Bungie's map variants: 20, 21 and 19 bits.
    #[test]
    fn position_widths_follow_the_bounds() {
        let forge_world = [
            -203.600_31,
            277.661_93,
            -360.830_08,
            324.920_9,
            -25.010_01,
            117.791_7,
        ];
        assert_eq!(position_widths(21, forge_world), [20, 21, 19]);
        assert_eq!(position_widths(21, [0.0; 6]), [0, 0, 0]);
        assert_eq!(position_widths(40, forge_world), [26, 26, 26]);
    }

    /// A position's widths come from bounds decoded earlier, and it encodes
    /// back to the same bits.
    #[test]
    fn position_round_trips_against_its_bounds() {
        let g = Grammar::from_json(
            r#"{
              "types": {},
              "top_level": [],
              "map_variant": [
                {"name": "lo", "kind": "f32"}, {"name": "hi", "kind": "f32"},
                {"name": "items", "kind": "repeat", "count": 2, "of": [
                  {"name": "p", "kind": "position", "precision": 21,
                   "bounds": ["lo", "hi", "lo", "hi", "lo", "hi"]}
                ]}
              ]
            }"#,
        )
        .unwrap();
        let mut w = BitWriter::new();
        w.write(u64::from(0f32.to_bits()), 32).unwrap();
        w.write(u64::from(1f32.to_bits()), 32).unwrap();
        // 1 unit at 1/1920 per step: 1920 steps, 11 bits an axis.
        for v in [(1, 5, 1919, 0), (0, 7, 8, 9)] {
            w.write(v.0, 1).unwrap();
            for a in [v.1, v.2, v.3] {
                w.write(a, 11).unwrap();
            }
        }
        let bytes = w.finish();
        let tree = g.decode_map_variant_at(&bytes, 0).unwrap();
        assert_eq!(tree.end, 64 + 2 * 34);
        let mut out = BitWriter::new();
        g.encode_map_variant_into(&tree, &mut out).unwrap();
        assert_eq!(out.finish(), bytes);
    }

    const MINI: &str = r#"{
      "types": {
        "T": {"selector": {"bits": 2, "minus1": true}, "cases": {
          "-1": {"name": "none", "fields": []},
          "0": {"name": "num", "fields": [{"name": "v", "kind": "s", "bits": 5}]},
          "1": {"name": "text", "fields": [{"name": "s", "kind": "zstring", "char_bits": 8, "max": 3}]}
        }}
      },
      "top_level": [
        {"name": "n", "kind": "u", "bits": 3, "minus1": true},
        {"name": "o", "kind": "opt", "bits": 4},
        {"name": "p", "kind": "opt", "bits": 4, "present_if": 1},
        {"kind": "if", "when": "n >= 1", "then": [
          {"name": "items", "kind": "array", "count_bits": 2, "of": [{"name": "t", "kind": "ref", "type": "T"}]}
        ], "else": [{"name": "f", "kind": "f32"}]},
        {"name": "k", "kind": "u", "bits": 2},
        {"name": "raw", "kind": "bytes", "count": "k"}
      ]
    }"#;

    #[test]
    fn a_mini_grammar_round_trips() {
        let g = Grammar::from_json(MINI).unwrap();
        // n=2 (raw 3), o absent, p present 9, 3 items: num -3, text "ab", text "xyz" (unterminated), k=1, raw 0xa5
        let mut w = BitWriter::new();
        w.write(3, 3).unwrap();
        w.bool(true);
        w.bool(true);
        w.write(9, 4).unwrap();
        w.write(3, 2).unwrap();
        w.write(1, 2).unwrap();
        w.write_signed(-3, 5).unwrap();
        w.write(2, 2).unwrap();
        for c in [b'a', b'b', 0] {
            w.write(u64::from(c), 8).unwrap();
        }
        w.write(2, 2).unwrap();
        for c in [b'x', b'y', b'z'] {
            w.write(u64::from(c), 8).unwrap();
        }
        w.write(1, 2).unwrap();
        w.write(0xa5, 8).unwrap();
        let bits = w.len();
        let bytes = w.finish();
        let t = g.decode_at(&bytes, 0).unwrap();
        assert_eq!(t.end, bits);
        assert_eq!(int(&t.fields, "n"), Some(2));
        assert_eq!(int(&t.fields, "o"), Some(-1));
        assert_eq!(int(&t.fields, "p"), Some(9));
        let items = field(&t.fields, "items").unwrap().value.items();
        assert_eq!(items.len(), 3);
        let third = &field(&items[2], "t").unwrap().value;
        assert_eq!(
            field(third.fields(), "s").unwrap().value.text().unwrap(),
            "xyz"
        );
        assert!(field(&t.fields, "f").is_none());
        let mut w = BitWriter::new();
        g.encode_into(&t, &mut w).unwrap();
        assert_eq!(w.len(), bits);
        assert_eq!(w.finish(), bytes);
    }

    #[test]
    fn a_tree_that_breaks_its_grammar_is_refused() {
        let g = Grammar::from_json(MINI).unwrap();
        let mut w = BitWriter::new();
        w.write(0, 3).unwrap(); // n = -1: the else branch
        w.bool(true);
        w.bool(false);
        w.write(0x3f80_0000, 32).unwrap();
        w.write(0, 2).unwrap();
        let bytes = w.finish();
        let mut t = g.decode_at(&bytes, 0).unwrap();
        assert_eq!(
            field(&t.fields, "f").unwrap().value,
            Value::F32(0x3f80_0000)
        );
        // A byte the count does not cover.
        let raw = t.fields.iter_mut().find(|n| n.name == "raw").unwrap();
        raw.value = Value::Bytes(vec![1]);
        let mut w = BitWriter::new();
        assert!(matches!(
            g.encode_into(&t, &mut w),
            Err(Error::Mismatch { .. })
        ));
    }

    #[test]
    fn the_crate_grammar_parses() {
        let g = grammar().unwrap();
        assert_eq!(g.actions.len(), 128);
        assert_eq!(g.conditions.len(), 32);
        assert!(matches!(g.type_def("NUMBER"), Some(TypeDef::Union(_))));
    }

    #[test]
    fn the_typed_builder_and_the_grammar_agree() {
        let v = crate::Variant::ctf(crate::ctf::Ctf {
            flag_type: 18,
            blue_flag_type: Some(20),
            score_to_win: 3,
            reset_ticks: 900,
            debug: false,
        });
        let bytes = v.write().unwrap();
        let t = decode(&bytes).unwrap();
        let count = |name: &str| field(&t.fields, name).map_or(0, |n| n.value.items().len());
        assert_eq!(count("conditions"), v.conditions.len());
        assert_eq!(count("actions"), v.actions.len());
        assert_eq!(count("triggers"), v.triggers.len());
        assert_eq!(int(&t.fields, "score_to_win"), Some(3));
        assert!(bytes.len() * 8 - t.end < 8);
        assert_eq!(encode(&t).unwrap(), bytes);
    }

    #[test]
    fn another_version_reads_nothing_more() {
        let t = decode(&[0x70, 0x00, 0x05, 0x32, 0xff]).unwrap();
        assert_eq!(t.end, 32);
        assert!(!t.is_megalo());
    }
}
