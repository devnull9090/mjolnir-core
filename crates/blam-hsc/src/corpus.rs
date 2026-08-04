//! The scripting function table, recovered from the shipped scenarios.
//!
//! The engine identifies a function by opcode, and the opcode table is Halo
//! Campaign Evolved's own: of the 483 opcodes the campaign calls, 24 agree with
//! Halo Reach's table and 7 with Halo 4's, so no existing Blam tooling's table
//! fits. It does not have to be reverse-engineered out of the binary, though,
//! because every compiled call carries its own name: a call node points at a
//! child whose string offset names the callee. Reading those across all
//! thirteen campaign scenarios recovers the table with no disagreement.
//!
//! **Signatures here are inferred from use, not read from the engine.** A
//! function the campaign never calls is absent, and one called only with a
//! `short` never shows that it would also accept a `real`. Every entry carries
//! its evidence count so a consumer can tell a well-attested signature from a
//! single observation, and [`FunctionDef::well_attested`] is the check a
//! compiler should gate a hard error on.
//!
//! Two things the shipped tree does not preserve, and so neither does this:
//!
//! - **`cond` does not survive compilation.** The compiler desugars it to
//!   nested `if`, so no opcode is ever emitted for it even though the source
//!   files use it freely. A decompiler will render those sites as `if`.
//! - **Special forms are not marked.** The value-type enum has a `special_form`
//!   entry, but no node in any of the 272,190 shipped datums carries it, so
//!   there is no way to tell from the tree alone that `if` short-circuits and
//!   `wake` does not.
//!
//! Only schema is emitted — opcodes, function names, and type names. Script
//! names, global names, and source text are game content and are never written
//! here.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

use crate::expr::ExpressionType;
use crate::read::ScriptSection;
use crate::Error;

/// How many call sites make a signature worth trusting without a warning.
///
/// One call site fixes a parameter's type to whatever that one caller passed,
/// which is exactly the case where inference misleads. Two independent sites
/// is the cheapest evidence that the type is the signature rather than the
/// caller.
pub const WELL_ATTESTED: u32 = 2;

/// The number of argument positions modelled individually.
///
/// `begin` and its relatives take as many arguments as a script has statements;
/// past this point the positions stop being distinguishable and the histogram
/// only wastes space.
const MAX_MODELLED_PARAMS: usize = 8;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ScriptCorpus {
    pub generator: String,
    /// The game build the table was recovered from. An opcode table is
    /// per-build: an engine update that inserts a function shifts every later
    /// opcode, so a corpus is only valid for the build named here.
    pub build: String,
    /// Plain-English note on how the table was produced, so the file explains
    /// itself to anyone who finds it without this crate.
    pub derivation: String,
    /// The value-type enum in this build's order. An expression's `value_type`
    /// indexes it.
    pub value_types: Vec<String>,
    /// The `script type` enum in this build's order.
    pub script_types: Vec<String>,
    /// Value types whose literals are written in quotes.
    ///
    /// Nothing in the tag records this — a `damage` literal and an `ai` literal
    /// are both just a string offset — but the source writes the first quoted
    /// and the second bare. The set is recovered by asking, for every string
    /// the tree references, whether it appears in quotes in the source that
    /// produced it. See [`QuotedEvidence`].
    pub quoted_types: BTreeSet<String>,
    /// Per-type tallies behind `quoted_types`, kept so the classification can
    /// be argued with rather than taken on faith.
    pub quoted_evidence: BTreeMap<String, QuotedEvidence>,
    /// The share of agreeing observations that was required to call something
    /// quoted, recorded so the classification is reproducible.
    pub quoted_threshold: f32,
    /// Engine functions by opcode.
    pub functions: BTreeMap<u16, FunctionDef>,
}

/// How many literals of one value type were seen quoted, and how many bare.
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize)]
pub struct QuotedEvidence {
    pub quoted: u32,
    pub bare: u32,
}

/// The share of observations that must agree before a type or argument
/// position is called quoted.
///
/// Not unanimity. Evidence is gathered by matching a node's string against how
/// the source writes that string, and a handful of collisions survive the
/// unambiguous-only filter — `string` comes out 3,593 quoted against 48 bare,
/// and is plainly a quoted type. The default was chosen by measuring the
/// decompiler's agreement with the shipped source across candidate values —
/// `mjolnir scripting --quoted-threshold` re-runs that sweep. Anything from
/// 0.5 to 0.75 lands within four scripts of the best result out of 6,827;
/// demanding near-unanimity is what actually hurts, costing 1,600 scripts at
/// 0.99 by rejecting `string` over a few dozen collisions.
pub const DEFAULT_QUOTED_MAJORITY: f32 = 0.75;

impl QuotedEvidence {
    pub fn total(&self) -> u32 {
        self.quoted + self.bare
    }

    /// The share of observations that were quoted.
    pub fn quoted_share(&self) -> f32 {
        if self.total() == 0 {
            return 0.0;
        }
        self.quoted as f32 / self.total() as f32
    }

    /// Whether this type's literals are written in quotes, at some threshold.
    pub fn is_quoted_at(&self, threshold: f32) -> bool {
        self.total() > 0 && self.quoted_share() >= threshold
    }

    /// Whether the evidence is mixed enough to be worth a second look.
    pub fn is_split(&self) -> bool {
        self.quoted > 0 && self.bare > 0
    }

    pub fn is_unattested(&self) -> bool {
        self.total() == 0
    }

    /// Whether there is enough here to overrule the type-level rule.
    ///
    /// One observation is not: it fixes a whole argument position on a single
    /// caller's spelling, which is the mistake the type-level rule already
    /// guards against.
    pub fn decides(&self) -> bool {
        self.total() >= WELL_ATTESTED
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FunctionDef {
    pub name: String,
    /// Value types this call evaluated to, by type name, with call-site counts.
    /// More than one entry means the return type depends on the arguments, as
    /// it does for `if` and the comparison operators.
    pub returns: BTreeMap<String, u32>,
    /// Fewest and most arguments observed, excluding the name node.
    pub min_args: usize,
    pub max_args: usize,
    /// Observed types per argument position, up to [`MAX_MODELLED_PARAMS`].
    pub parameters: Vec<ParameterDef>,
    /// How many calls this was seen at, and how many scenarios called it.
    pub call_sites: u32,
    pub scenarios: u32,
}

impl FunctionDef {
    /// Whether there is enough evidence to treat this signature as the
    /// function's real one rather than one caller's habit.
    pub fn well_attested(&self) -> bool {
        self.call_sites >= WELL_ATTESTED
    }

    /// Whether the argument count varies between call sites.
    pub fn is_variadic(&self) -> bool {
        self.min_args != self.max_args
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ParameterDef {
    /// Value types passed at this position, with counts.
    pub types: BTreeMap<String, u32>,
    /// Whether every observed call filled this position.
    pub always_present: bool,
    /// Whether literals at this position are written in quotes, when there is
    /// enough evidence to say.
    ///
    /// Quoting is not purely a property of the value type: a `string_id` is
    /// quoted as the marker name in `(object_at_marker x "primary_weapon")` and
    /// bare in plenty of other places. Where a position has its own evidence it
    /// beats the type-level rule. Decided at generation time so that reading
    /// the corpus cannot apply a different threshold than the one recorded in
    /// it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub quoted: Option<bool>,
    /// The tallies behind `quoted`, kept so it can be argued with.
    #[serde(default, skip_serializing_if = "QuotedEvidence::is_unattested")]
    pub quoting: QuotedEvidence,
}

impl ScriptCorpus {
    pub fn load(path: impl AsRef<std::path::Path>) -> Result<Self, Error> {
        let text = std::fs::read_to_string(path)?;
        Ok(serde_json::from_str(&text)?)
    }

    pub fn save(&self, path: impl AsRef<std::path::Path>) -> Result<(), Error> {
        std::fs::write(path, self.to_json()?)?;
        Ok(())
    }

    pub fn to_json(&self) -> Result<String, Error> {
        let mut text = serde_json::to_string_pretty(self)?;
        text.push('\n');
        Ok(text)
    }

    /// Look an opcode up by the name a script would call it with.
    pub fn by_name(&self, name: &str) -> Option<(u16, &FunctionDef)> {
        self.functions
            .iter()
            .find(|(_, f)| f.name == name)
            .map(|(op, f)| (*op, f))
    }

    /// Functions attested by a single call site, which are the ones whose
    /// inferred signature is most likely to be wrong.
    pub fn thinly_attested(&self) -> Vec<(u16, &FunctionDef)> {
        self.functions
            .iter()
            .filter(|(_, f)| !f.well_attested())
            .map(|(op, f)| (*op, f))
            .collect()
    }
}

/// One opcode seen under two different names, which would mean the recovery
/// rule is wrong.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Conflict {
    pub opcode: u16,
    pub names: Vec<String>,
}

/// Accumulates observations across scenarios into a corpus.
#[derive(Debug, Default)]
pub struct CorpusBuilder {
    functions: BTreeMap<u16, Observed>,
    value_types: Vec<String>,
    script_types: Vec<String>,
    quoted: BTreeMap<String, QuotedEvidence>,
    scenarios: u32,
}

#[derive(Debug, Default)]
struct Observed {
    names: BTreeSet<String>,
    returns: BTreeMap<String, u32>,
    min_args: Option<usize>,
    max_args: usize,
    params: Vec<BTreeMap<String, u32>>,
    /// Calls that reached at least this position, per position.
    filled: Vec<u32>,
    /// How each position's literals are written.
    quoting: Vec<QuotedEvidence>,
    call_sites: u32,
    scenarios: BTreeSet<u32>,
}

impl CorpusBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    /// How many scenarios have been folded in.
    pub fn scenarios(&self) -> u32 {
        self.scenarios
    }

    /// Fold one scenario's calls into the table.
    pub fn observe(&mut self, section: &ScriptSection) {
        let ordinal = self.scenarios;
        self.scenarios += 1;

        // The enums are per-build, not per-scenario, so the first scenario sets
        // them and the rest are expected to agree.
        if self.value_types.is_empty() {
            self.value_types = section.value_types.names().to_vec();
            self.script_types = section.script_types.names().to_vec();
        }

        let type_name = |t: u16| {
            section
                .value_types
                .name_of(t)
                .unwrap_or("<unknown>")
                .to_string()
        };

        // How the source that produced this tree writes each string it
        // mentions, used for both the type-level and per-argument rules.
        let mut forms = crate::lex::LiteralForms::default();
        for f in &section.source_files {
            forms.merge(crate::lex::literal_forms(&f.text()));
        }
        let has_source = !section.source_files.is_empty();
        if has_source {
            self.observe_quoting(section, &type_name, &forms);
        }

        for (_, call) in section.live() {
            // A script call carries a script index in `opcode`, not an engine
            // opcode, so it says nothing about the function table.
            if call.expression_type != ExpressionType::Group {
                continue;
            }
            let chain = section.arguments(call);
            // The first child names the callee; the rest are the arguments.
            let Some((name_handle, args)) = chain.split_first() else {
                continue;
            };
            let Some(name_node) = section.get(*name_handle) else {
                continue;
            };
            let name = section.string_at(name_node.string_offset);
            if name.is_empty() {
                continue;
            }

            let e = self.functions.entry(call.opcode).or_default();
            e.names.insert(name.to_string());
            *e.returns.entry(type_name(call.value_type)).or_default() += 1;
            e.call_sites += 1;
            e.scenarios.insert(ordinal);
            e.min_args = Some(e.min_args.map_or(args.len(), |m| m.min(args.len())));
            e.max_args = e.max_args.max(args.len());

            for (i, arg) in args.iter().take(MAX_MODELLED_PARAMS).enumerate() {
                let Some(node) = section.get(*arg) else {
                    continue;
                };
                if e.params.len() <= i {
                    e.params.resize_with(i + 1, Default::default);
                    e.filled.resize(i + 1, 0);
                    e.quoting.resize(i + 1, QuotedEvidence::default());
                }
                *e.params[i].entry(type_name(node.value_type)).or_default() += 1;
                e.filled[i] += 1;

                // A literal at this position teaches how the position is
                // written; a nested call teaches nothing.
                if !has_source || node.expression_type != ExpressionType::Expression {
                    continue;
                }
                let text = section.string_at(node.string_offset);
                if text.is_empty() {
                    continue;
                }
                if forms.quoted.contains(text) {
                    e.quoting[i].quoted += 1;
                } else if forms.bare.contains(text) {
                    e.quoting[i].bare += 1;
                }
            }
        }
    }

    /// Tally, per value type, how many of its literals the source wrote in
    /// quotes.
    ///
    /// A scenario with no source files teaches nothing here and is skipped
    /// rather than counted as evidence for "bare".
    fn observe_quoting(
        &mut self,
        section: &ScriptSection,
        type_name: &dyn Fn(u16) -> String,
        forms: &crate::lex::LiteralForms,
    ) {
        for (_, e) in section.live() {
            // Only leaves carry literals; a call's string offset names the
            // callee, which is never quoted.
            if e.expression_type != ExpressionType::Expression {
                continue;
            }
            let text = section.string_at(e.string_offset);
            if text.is_empty() {
                continue;
            }
            let name = type_name(e.value_type);
            // `function_name` is the callee-naming node, not a literal.
            if name == "function_name" {
                continue;
            }
            // A string the source writes both ways is in neither set, and is
            // no evidence about either type.
            if forms.quoted.contains(text) {
                self.quoted.entry(name).or_default().quoted += 1;
            } else if forms.bare.contains(text) {
                self.quoted.entry(name).or_default().bare += 1;
            }
        }
    }

    /// Opcodes seen under more than one name. An empty result is the check that
    /// the recovery rule holds.
    pub fn conflicts(&self) -> Vec<Conflict> {
        self.functions
            .iter()
            .filter(|(_, o)| o.names.len() > 1)
            .map(|(op, o)| Conflict {
                opcode: *op,
                names: o.names.iter().cloned().collect(),
            })
            .collect()
    }

    pub fn finish(self, generator: String, build: String) -> ScriptCorpus {
        self.finish_at(generator, build, DEFAULT_QUOTED_MAJORITY)
    }

    /// [`CorpusBuilder::finish`], with an explicit quoting threshold.
    pub fn finish_at(self, generator: String, build: String, threshold: f32) -> ScriptCorpus {
        let scenarios = self.scenarios;
        let functions = self
            .functions
            .iter()
            .map(|(op, o)| {
                let def = FunctionDef {
                    // A conflicting opcode keeps its first name; `conflicts`
                    // is where a caller finds out that happened.
                    name: o.names.iter().next().cloned().unwrap_or_default(),
                    returns: o.returns.clone(),
                    min_args: o.min_args.unwrap_or(0),
                    max_args: o.max_args,
                    parameters: o
                        .params
                        .iter()
                        .enumerate()
                        .map(|(i, types)| ParameterDef {
                            types: types.clone(),
                            always_present: o.filled.get(i) == Some(&o.call_sites),
                            quoted: o
                                .quoting
                                .get(i)
                                .filter(|e| e.decides())
                                .map(|e| e.is_quoted_at(threshold)),
                            quoting: o.quoting.get(i).copied().unwrap_or_default(),
                        })
                        .collect(),
                    call_sites: o.call_sites,
                    scenarios: o.scenarios.len() as u32,
                };
                (*op, def)
            })
            .collect();

        ScriptCorpus {
            generator,
            build,
            derivation: format!(
                "Recovered from {scenarios} shipped scenario tags by reading the name node of \
                 every compiled call. Signatures are inferred from observed call sites, not read \
                 from the engine: a function the campaign never calls is absent, and an argument \
                 type seen once may be one caller's habit rather than the signature."
            ),
            value_types: self.value_types,
            script_types: self.script_types,
            quoted_types: self
                .quoted
                .iter()
                .filter(|(_, e)| e.is_quoted_at(threshold))
                .map(|(n, _)| n.clone())
                .collect(),
            quoted_evidence: self.quoted,
            quoted_threshold: threshold,
            functions,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expr::{DatumHandle, Expression, ValueTypes};

    fn types() -> ValueTypes {
        ValueTypes::new(
            [
                "unparsed",
                "special_form",
                "function_name",
                "void",
                "boolean",
                "short",
            ]
            .iter()
            .map(|s| s.to_string())
            .collect(),
        )
    }

    fn node(
        generation: u16,
        opcode: u16,
        value_type: u16,
        ty: ExpressionType,
        next: DatumHandle,
        string_offset: u32,
        data: u32,
    ) -> Expression {
        Expression {
            generation,
            opcode,
            value_type,
            expression_type: ty,
            next,
            string_offset,
            data,
            line: 0,
            tail: 0,
        }
    }

    /// `(wake 3)` compiled: a group, its name node, and one argument.
    fn one_call(opcode: u16, arg_type: u16, name_type: u16) -> ScriptSection {
        ScriptSection {
            strings: b"wake\0".to_vec(),
            expressions: vec![
                node(
                    1,
                    opcode,
                    3,
                    ExpressionType::Group,
                    DatumHandle::NULL,
                    0,
                    0x0002_0001,
                ),
                node(
                    2,
                    opcode,
                    name_type,
                    ExpressionType::Expression,
                    DatumHandle::new(2, 3),
                    0,
                    0,
                ),
                node(
                    3,
                    0,
                    arg_type,
                    ExpressionType::Expression,
                    DatumHandle::NULL,
                    0,
                    7,
                ),
            ],
            value_types: types(),
            ..ScriptSection::default()
        }
    }

    #[test]
    fn a_call_yields_its_opcode_name_return_and_argument_types() {
        let mut b = CorpusBuilder::new();
        b.observe(&one_call(0x19c, 5, 2));
        let c = b.finish("test".into(), "build".into());

        let f = &c.functions[&0x19c];
        assert_eq!(f.name, "wake");
        assert_eq!(f.returns.get("void"), Some(&1));
        assert_eq!(f.min_args, 1);
        assert_eq!(f.max_args, 1);
        assert_eq!(f.parameters[0].types.get("short"), Some(&1));
        assert!(f.parameters[0].always_present);
    }

    #[test]
    fn the_node_naming_the_callee_is_not_counted_as_an_argument() {
        let mut b = CorpusBuilder::new();
        // The name node is typed `function_name`; only the node after it is an
        // argument. Counting the name would make every function look like it
        // takes one more parameter than it does.
        b.observe(&one_call(0x19c, 5, 2));
        let c = b.finish("test".into(), "build".into());
        let f = &c.functions[&0x19c];
        assert_eq!(f.max_args, 1);
        assert_eq!(f.parameters.len(), 1);
        assert!(!f.parameters[0].types.contains_key("function_name"));
    }

    #[test]
    fn one_call_site_is_not_well_attested() {
        let mut b = CorpusBuilder::new();
        b.observe(&one_call(0x19c, 5, 2));
        let c = b.finish("test".into(), "build".into());
        assert!(!c.functions[&0x19c].well_attested());
        assert_eq!(c.thinly_attested().len(), 1);

        let mut b = CorpusBuilder::new();
        b.observe(&one_call(0x19c, 5, 2));
        b.observe(&one_call(0x19c, 5, 2));
        let c = b.finish("test".into(), "build".into());
        assert!(c.functions[&0x19c].well_attested());
        assert_eq!(c.functions[&0x19c].scenarios, 2);
        assert!(c.thinly_attested().is_empty());
    }

    #[test]
    fn differing_argument_types_are_both_kept() {
        let mut b = CorpusBuilder::new();
        b.observe(&one_call(0x19c, 5, 2));
        b.observe(&one_call(0x19c, 4, 2));
        let c = b.finish("test".into(), "build".into());
        let p = &c.functions[&0x19c].parameters[0];
        assert_eq!(p.types.get("short"), Some(&1));
        assert_eq!(p.types.get("boolean"), Some(&1));
    }

    #[test]
    fn an_opcode_under_two_names_is_reported_rather_than_silently_merged() {
        let mut b = CorpusBuilder::new();
        b.observe(&one_call(7, 5, 2));
        let mut other = one_call(7, 5, 2);
        other.strings = b"and\0".to_vec();
        b.observe(&other);

        let conflicts = b.conflicts();
        assert_eq!(conflicts.len(), 1);
        assert_eq!(conflicts[0].opcode, 7);
        assert_eq!(conflicts[0].names, vec!["and", "wake"]);
    }

    #[test]
    fn a_script_call_is_not_mistaken_for_an_engine_function() {
        let mut s = one_call(0x19c, 5, 2);
        // `opcode` on a script reference indexes the scenario's own scripts.
        s.expressions[0].expression_type = ExpressionType::ScriptReference;
        let mut b = CorpusBuilder::new();
        b.observe(&s);
        assert!(b.finish("t".into(), "b".into()).functions.is_empty());
    }

    #[test]
    fn a_corpus_round_trips_through_json() {
        let mut b = CorpusBuilder::new();
        b.observe(&one_call(0x19c, 5, 2));
        let c = b.finish("test".into(), "build".into());
        let json = c.to_json().unwrap();
        let back: ScriptCorpus = serde_json::from_str(&json).unwrap();
        assert_eq!(back.functions[&0x19c].name, "wake");
        assert_eq!(back.value_types, c.value_types);
    }
}
