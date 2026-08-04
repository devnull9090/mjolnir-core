//! Render a compiled expression tree back to HSC source.
//!
//! This needs no function table. Every call node points at a child that names
//! the callee, so the tree names itself — the opcode corpus is for the
//! compiler, which has to go the other way.
//!
//! Two things cannot come back, because the tree never held them:
//!
//! - **Comments.** Roughly a fifth of the shipped source is comment lines.
//! - **`cond`.** The compiler desugars it into nested `if` before emitting any
//!   node, so a `cond` in the original reappears as `if`.
//!
//! Line breaks *do* come back. Every node records the source line it came
//! from, so laying arguments out by line number reproduces the original shape
//! rather than guessing at one with a column-width heuristic.
//!
//! # How good is it
//!
//! `mjolnir script --verify` decompiles all 6,827 scripts in the shipped
//! campaign and compares each against the source the same scenario carries.
//! As of the build named in `defs/hce/scripting.json`:
//!
//! | Outcome | Scripts |
//! |---|---:|
//! | Token-for-token match | 6,241 (91.4%) |
//! | Differ only because the source used `cond` | 205 |
//! | No source block to compare against | 150 |
//! | Genuinely differ | 231 |
//!
//! Of the 231, 186 are a literal quoted on one side and bare on the other.
//! Quoting is not recorded anywhere in the tag — see
//! [`crate::corpus::QuotedEvidence`] — so it is inferred, and the inference is
//! not perfect. The remaining 45 are unexplained and worth investigating before
//! anyone relies on decompiled output for a scenario whose source was stripped.
//!
//! None of this affects reading a shipped scenario in an editor: the original
//! source is right there in the tag, and that is what gets shown. The
//! decompiler matters when the source is missing, and as the check that this
//! crate's model of the format is right.

use std::collections::BTreeSet;
use std::fmt::Write as _;

use crate::expr::{DatumHandle, Expression, ExpressionType};
use crate::read::{Global, Script, ScriptSection};

/// Deepest nesting rendered before the walk gives up.
///
/// Real scripts nest perhaps twenty deep. A tag edited by hand can point a node
/// at its own ancestor, and this is what stops that from being a stack
/// overflow.
const MAX_DEPTH: u32 = 128;

/// The `none` a null handle or unset value renders as.
const NONE: &str = "none";

/// Where a node sits, so its literal can be formatted the way that position is
/// written. A node that is not an argument — a script root, a global's
/// initializer — carries no opcode.
#[derive(Debug, Clone, Copy, Default)]
struct At {
    opcode: Option<u16>,
    position: usize,
}

#[derive(Debug, Clone)]
pub struct Options {
    /// One indent level. The shipped source uses a tab.
    pub indent: String,
    /// Emit a `; ...` banner above each section.
    pub banners: bool,
    /// Value types whose literals are written in quotes.
    ///
    /// Nothing in the tag says which those are, so without a corpus only
    /// `string` is quoted — which renders a `damage` literal as a bare tag path
    /// that will not compile back. [`Options::with_corpus`] fills this in.
    pub quoted_types: BTreeSet<String>,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            indent: "\t".to_string(),
            banners: true,
            quoted_types: ["string"].iter().map(|s| s.to_string()).collect(),
        }
    }
}

impl Options {
    /// Take the quoted-type set from a recovered corpus.
    pub fn with_corpus(mut self, corpus: &crate::corpus::ScriptCorpus) -> Self {
        if !corpus.quoted_types.is_empty() {
            self.quoted_types = corpus.quoted_types.clone();
        }
        self
    }
}

pub struct Decompiler<'a> {
    section: &'a ScriptSection,
    options: Options,
    corpus: Option<&'a crate::corpus::ScriptCorpus>,
}

impl<'a> Decompiler<'a> {
    pub fn new(section: &'a ScriptSection) -> Self {
        Decompiler {
            section,
            options: Options::default(),
            corpus: None,
        }
    }

    pub fn with_options(section: &'a ScriptSection, options: Options) -> Self {
        Decompiler {
            section,
            options,
            corpus: None,
        }
    }

    /// Use a recovered corpus for the quoting rules, which resolves cases the
    /// value type alone cannot.
    pub fn with_corpus(
        section: &'a ScriptSection,
        corpus: &'a crate::corpus::ScriptCorpus,
    ) -> Self {
        Decompiler {
            section,
            options: Options::default().with_corpus(corpus),
            corpus: Some(corpus),
        }
    }

    /// The whole scenario: globals, then scripts, in declaration order.
    pub fn scenario(&self) -> String {
        let mut out = String::new();
        if !self.section.globals.is_empty() {
            if self.options.banners {
                out.push_str("; globals\n\n");
            }
            for g in &self.section.globals {
                out.push_str(&self.global(g));
                out.push('\n');
            }
            out.push('\n');
        }
        if !self.section.scripts.is_empty() {
            if self.options.banners {
                out.push_str("; scripts\n\n");
            }
            for s in &self.section.scripts {
                out.push_str(&self.script(s));
                out.push_str("\n\n");
            }
        }
        out
    }

    /// `(global <type> <name> <initializer>)`
    pub fn global(&self, g: &Global) -> String {
        let ty = self.type_name(g.value_type);
        let init = self
            .render(g.initializer, 0, At::default())
            .unwrap_or_else(|| NONE.to_string());
        format!("(global {ty} {} {init})", g.name)
    }

    /// A script, header and body.
    ///
    /// `static` and `stub` scripts declare a return type; the rest are void by
    /// construction and the shipped source omits it, so this does too.
    pub fn script(&self, s: &Script) -> String {
        let kind = self.script_type_name(s.script_type);
        let declares_return = matches!(kind, "static" | "stub");

        let mut header = String::from("(script ");
        header.push_str(kind);
        if declares_return {
            header.push(' ');
            header.push_str(self.type_name(s.return_type));
        }
        header.push(' ');

        // Parameters put the name inside its own parenthesised list, which is
        // what turns `f_md_3d_play` into `(f_md_3d_play (short delay) ...)`.
        if s.parameters.is_empty() {
            header.push_str(&s.name);
        } else {
            let params: Vec<String> = s
                .parameters
                .iter()
                .map(|p| format!("({} {})", self.type_name(p.value_type), p.name))
                .collect();
            let _ = write!(header, "({} {})", s.name, params.join(" "));
        }

        let body = self.body(s.root);
        format!("{header}\n{body}\n)")
    }

    /// A script body, indented one level.
    ///
    /// The root of a script is usually a `begin`, whose statements are the
    /// script's statements. Rendering the `begin` itself would wrap every body
    /// in a redundant layer the source never had, so it is unwrapped.
    fn body(&self, root: DatumHandle) -> String {
        let indent = &self.options.indent;
        let Some(node) = self.section.get(root) else {
            return String::new();
        };

        if let Some(statements) = self.implicit_begin(node) {
            let mut out = String::new();
            for (i, h) in statements.iter().enumerate() {
                if i > 0 {
                    out.push('\n');
                }
                out.push_str(indent);
                out.push_str(&self.render(*h, 1, At::default()).unwrap_or_default());
            }
            return out;
        }

        format!(
            "{indent}{}",
            self.render(root, 1, At::default())
                .unwrap_or_else(|| NONE.to_string())
        )
    }

    /// The statements of a `begin` that wraps a whole script body, if this node
    /// is one.
    fn implicit_begin(&self, node: &Expression) -> Option<Vec<DatumHandle>> {
        if node.expression_type != ExpressionType::Group {
            return None;
        }
        if self.section.callee_name(node)? != "begin" {
            return None;
        }
        let chain = self.section.arguments(node);
        // Drop the node that names `begin`; the rest are the statements.
        Some(chain.get(1..)?.to_vec())
    }

    /// Render one node, or `None` if it is one the compiler marked as carrying
    /// no source of its own.
    fn render(&self, handle: DatumHandle, depth: u32, at: At) -> Option<String> {
        if depth > MAX_DEPTH {
            return Some("; <nesting too deep to render>".to_string());
        }
        let node = self.section.get(handle)?;

        match node.expression_type {
            ExpressionType::Group | ExpressionType::ScriptReference => self.call(node, depth),
            // A global or parameter read is just its name.
            ExpressionType::GlobalsReference | ExpressionType::ParameterReference => {
                let name = self.section.string_at(node.string_offset);
                Some(if name.is_empty() {
                    NONE.to_string()
                } else {
                    name.to_string()
                })
            }
            _ => self.literal(node, at),
        }
    }

    /// Whether a literal in this position is written in quotes.
    ///
    /// A position with its own evidence beats the type-level rule, because
    /// quoting is not purely a property of the type — `string_id` is quoted as
    /// the marker name in `(object_at_marker x "primary_weapon")` and bare in
    /// most other places.
    fn is_quoted(&self, at: At, type_name: &str) -> bool {
        if let (Some(corpus), Some(opcode)) = (self.corpus, at.opcode) {
            if let Some(quoted) = corpus
                .functions
                .get(&opcode)
                .and_then(|f| f.parameters.get(at.position))
                .and_then(|p| p.quoted)
            {
                return quoted;
            }
        }
        self.options.quoted_types.contains(type_name)
    }

    /// `(name arg arg)`, laid out by the line numbers the nodes carry.
    fn call(&self, node: &Expression, depth: u32) -> Option<String> {
        let chain = self.section.arguments(node);
        let (name_handle, args) = chain.split_first()?;
        let name_node = self.section.get(*name_handle)?;
        let name = self.section.string_at(name_node.string_offset);
        let name = if name.is_empty() {
            // An opcode with no name in the blob still has to render as
            // something a reader can act on.
            format!("<opcode {:#06x}>", node.opcode)
        } else {
            name.to_string()
        };

        let mut out = String::from("(");
        out.push_str(&name);

        let call_line = name_node.line;
        let mut current_line = call_line;
        let mut multiline = false;

        // A script call's opcode indexes the scenario's scripts, not the engine
        // function table, so it must not be used to look up argument rules.
        let opcode = (node.expression_type == ExpressionType::Group).then_some(node.opcode);

        for (position, handle) in args.iter().enumerate() {
            let Some(arg) = self.section.get(*handle) else {
                continue;
            };
            let Some(text) = self.render(*handle, depth + 1, At { opcode, position }) else {
                continue;
            };
            // A node whose line differs from the one before it started a new
            // line in the original, so it starts one here too.
            if arg.line != current_line && arg.line != 0 && current_line != 0 {
                multiline = true;
                out.push('\n');
                out.push_str(&self.options.indent.repeat((depth + 1) as usize));
            } else {
                out.push(' ');
            }
            out.push_str(&text);
            current_line = self.last_line(*handle, arg);
        }

        if multiline {
            out.push('\n');
            out.push_str(&self.options.indent.repeat(depth as usize));
        }
        out.push(')');
        Some(out)
    }

    /// The last source line a subtree occupies, so the next sibling knows
    /// whether it began a new line.
    fn last_line(&self, handle: DatumHandle, node: &Expression) -> u16 {
        let mut last = node.line;
        let mut stack = vec![(handle, 0u32)];
        while let Some((h, depth)) = stack.pop() {
            if depth > MAX_DEPTH {
                continue;
            }
            let Some(n) = self.section.get(h) else {
                continue;
            };
            last = last.max(n.line);
            for child in self.section.arguments(n) {
                stack.push((child, depth + 1));
            }
        }
        last
    }

    /// A leaf value, formatted by the type it carries.
    fn literal(&self, node: &Expression, at: At) -> Option<String> {
        let text = self.section.string_at(node.string_offset);
        match self.type_name(node.value_type) {
            // A void leaf contributes nothing; emitting it would add a stray
            // token the source never had.
            "void" | "unparsed" => None,
            "boolean" => Some(
                if node.data & 0xFF != 0 {
                    "true"
                } else {
                    "false"
                }
                .to_string(),
            ),
            "short" => Some((node.data as u16 as i16).to_string()),
            "long" => Some((node.data as i32).to_string()),
            "real" => Some(format_real(f32::from_bits(node.data))),
            name => {
                // Everything else names something: an object, a trigger volume,
                // an enum case, a tag path. The name is in the blob; only the
                // quoting depends on where it sits.
                let quoted = self.is_quoted(at, name);
                if text.is_empty() {
                    // There is no such thing as an empty bare word, so a blank
                    // name is either the unset sentinel or a genuine empty
                    // string. `none` is only available where the position is
                    // written bare: a quoted position writes `""` even for the
                    // unset value, as `(vehicle_load_magic v "" ...)` does.
                    return Some(if !quoted && node.data == u32::MAX {
                        NONE.to_string()
                    } else {
                        quote("")
                    });
                }
                Some(if quoted {
                    quote(text)
                } else {
                    text.to_string()
                })
            }
        }
    }

    fn type_name(&self, index: u16) -> &str {
        self.section.value_types.name_of(index).unwrap_or("unknown")
    }

    fn script_type_name(&self, index: u16) -> &str {
        self.section
            .script_types
            .name_of(index)
            .unwrap_or("unknown")
    }
}

/// Quote a string literal the way HSC writes one.
///
/// Backslashes in a tag path are literal, not escapes, so this is deliberately
/// not `{:?}` — that would turn `objects\marine` into `objects\\marine`, which
/// is a different path.
fn quote(text: &str) -> String {
    format!("\"{text}\"")
}

/// A real, with a decimal point kept so it stays distinguishable from a short.
///
/// The shortest representation that round-trips, not a fixed number of places:
/// `0.8` is stored as the `f32` nearest to it, and printing that to eight
/// decimals gives `0.80000001`, which is the same number written unreadably.
fn format_real(v: f32) -> String {
    let s = format!("{v}");
    if s.contains(['.', 'e', 'E', 'N', 'i']) {
        s
    } else {
        format!("{s}.0")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expr::ValueTypes;
    use crate::read::Parameter;

    fn types() -> ValueTypes {
        ValueTypes::new(
            [
                "unparsed",
                "special_form",
                "function_name",
                "passthrough",
                "void",
                "boolean",
                "real",
                "short",
                "long",
                "string",
                "ai",
            ]
            .iter()
            .map(|s| s.to_string())
            .collect(),
        )
    }

    fn script_types() -> ValueTypes {
        ValueTypes::new(
            [
                "startup",
                "dormant",
                "continuous",
                "static",
                "command_script",
                "stub",
            ]
            .iter()
            .map(|s| s.to_string())
            .collect(),
        )
    }

    struct Build {
        exprs: Vec<Expression>,
        strings: Vec<u8>,
    }

    impl Build {
        fn new() -> Self {
            Build {
                exprs: Vec::new(),
                strings: vec![0],
            }
        }

        fn intern(&mut self, s: &str) -> u32 {
            let at = self.strings.len() as u32;
            self.strings.extend_from_slice(s.as_bytes());
            self.strings.push(0);
            at
        }

        fn push(
            &mut self,
            ty: ExpressionType,
            value_type: u16,
            line: u16,
            string_offset: u32,
            data: u32,
        ) -> DatumHandle {
            let index = self.exprs.len() as u16;
            let salt = index + 0x100;
            self.exprs.push(Expression {
                salt,
                opcode: 0,
                value_type,
                expression_type: ty,
                next: DatumHandle::NULL,
                string_offset,
                data,
                line,
                tail: 0,
            });
            DatumHandle::new(index, salt)
        }

        fn link(&mut self, from: DatumHandle, to: DatumHandle) {
            self.exprs[from.index()].next = to;
        }

        fn finish(self) -> ScriptSection {
            ScriptSection {
                expressions: self.exprs,
                strings: self.strings,
                value_types: types(),
                script_types: script_types(),
                ..ScriptSection::default()
            }
        }
    }

    /// `(wake 3)` on one line.
    fn wake_call(line: u16) -> (ScriptSection, DatumHandle) {
        let mut b = Build::new();
        let name = b.intern("wake");
        let group = b.push(ExpressionType::Group, 4, line, 0, 0);
        let name_node = b.push(ExpressionType::Expression, 2, line, name, 0);
        let arg = b.push(ExpressionType::Expression, 7, line, 0, 3);
        b.link(name_node, arg);
        b.exprs[group.index()].data = name_node.0;
        (b.finish(), group)
    }

    #[test]
    fn a_call_on_one_line_renders_on_one_line() {
        let (s, root) = wake_call(5);
        let d = Decompiler::new(&s);
        assert_eq!(d.render(root, 0, At::default()).unwrap(), "(wake 3)");
    }

    #[test]
    fn arguments_on_later_lines_are_broken_and_indented() {
        let mut b = Build::new();
        let name = b.intern("begin");
        let inner = b.intern("wake");
        let group = b.push(ExpressionType::Group, 4, 1, 0, 0);
        let name_node = b.push(ExpressionType::Expression, 2, 1, name, 0);

        // Two statements, each on its own line.
        let s1 = b.push(ExpressionType::Group, 4, 2, 0, 0);
        let s1n = b.push(ExpressionType::Expression, 2, 2, inner, 0);
        let s2 = b.push(ExpressionType::Group, 4, 3, 0, 0);
        let s2n = b.push(ExpressionType::Expression, 2, 3, inner, 0);
        b.exprs[s1.index()].data = s1n.0;
        b.exprs[s2.index()].data = s2n.0;
        b.link(name_node, s1);
        b.link(s1, s2);
        b.exprs[group.index()].data = name_node.0;

        let s = b.finish();
        let d = Decompiler::new(&s);
        assert_eq!(
            d.render(group, 0, At::default()).unwrap(),
            "(begin\n\t(wake)\n\t(wake)\n)"
        );
    }

    #[test]
    fn literals_render_by_their_declared_type() {
        let mut b = Build::new();
        let text = b.intern("hello");
        let ai = b.intern("sq_marines");
        let s = {
            b.push(ExpressionType::Expression, 5, 1, 0, 1); // boolean true
            b.push(ExpressionType::Expression, 5, 1, 0, 0); // boolean false
            b.push(ExpressionType::Expression, 7, 1, 0, 0xFFFF); // short -1
            b.push(ExpressionType::Expression, 8, 1, 0, (-3i32) as u32); // long
            b.push(ExpressionType::Expression, 6, 1, 0, 1.5f32.to_bits()); // real
            b.push(ExpressionType::Expression, 9, 1, text, 0); // string
            b.push(ExpressionType::Expression, 10, 1, ai, 4); // ai, named
            b.finish()
        };
        let d = Decompiler::new(&s);
        let got: Vec<String> = (0..7)
            .map(|i| d.literal(&s.expressions[i], At::default()).unwrap())
            .collect();
        assert_eq!(
            got,
            vec![
                "true",
                "false",
                "-1",
                "-3",
                "1.5",
                "\"hello\"",
                "sq_marines"
            ]
        );
    }

    #[test]
    fn a_real_keeps_a_decimal_point() {
        assert_eq!(format_real(1.0), "1.0");
        assert_eq!(format_real(-2.0), "-2.0");
        assert_eq!(format_real(0.5), "0.5");
        assert_eq!(format_real(1.25), "1.25");
    }

    #[test]
    fn an_unset_reference_renders_as_none() {
        let mut b = Build::new();
        b.push(ExpressionType::Expression, 10, 1, 0, u32::MAX);
        let s = b.finish();
        let d = Decompiler::new(&s);
        assert_eq!(d.literal(&s.expressions[0], At::default()).unwrap(), "none");
    }

    #[test]
    fn a_static_script_declares_its_return_type_and_a_dormant_one_does_not() {
        let (mut s, root) = wake_call(2);
        s.scripts.push(Script {
            name: "f_check".into(),
            script_type: 3, // static
            return_type: 5, // boolean
            root,
            parameters: vec![Parameter {
                name: "who".into(),
                value_type: 10,
            }],
        });
        s.scripts.push(Script {
            name: "on_wake".into(),
            script_type: 1, // dormant
            return_type: 4, // void
            root,
            parameters: Vec::new(),
        });

        let d = Decompiler::new(&s);
        assert_eq!(
            d.script(&s.scripts[0]),
            "(script static boolean (f_check (ai who))\n\t(wake 3)\n)"
        );
        assert_eq!(
            d.script(&s.scripts[1]),
            "(script dormant on_wake\n\t(wake 3)\n)"
        );
    }

    #[test]
    fn a_begin_at_a_script_root_does_not_add_a_layer() {
        let mut b = Build::new();
        let begin = b.intern("begin");
        let wake = b.intern("wake");
        let group = b.push(ExpressionType::Group, 4, 1, 0, 0);
        let name_node = b.push(ExpressionType::Expression, 2, 1, begin, 0);
        let s1 = b.push(ExpressionType::Group, 4, 2, 0, 0);
        let s1n = b.push(ExpressionType::Expression, 2, 2, wake, 0);
        b.exprs[s1.index()].data = s1n.0;
        b.link(name_node, s1);
        b.exprs[group.index()].data = name_node.0;

        let mut s = b.finish();
        s.scripts.push(Script {
            name: "boot".into(),
            script_type: 0,
            return_type: 4,
            root: group,
            parameters: Vec::new(),
        });
        let d = Decompiler::new(&s);
        // Not `(script startup boot\n\t(begin\n\t\t(wake)))`.
        assert_eq!(d.script(&s.scripts[0]), "(script startup boot\n\t(wake)\n)");
    }

    #[test]
    fn a_global_renders_with_its_type_and_initializer() {
        let mut b = Build::new();
        let init = b.push(ExpressionType::Expression, 5, 1, 0, 0);
        let mut s = b.finish();
        s.globals.push(Global {
            name: "b_awake".into(),
            value_type: 5,
            initializer: init,
        });
        let d = Decompiler::new(&s);
        assert_eq!(d.global(&s.globals[0]), "(global boolean b_awake false)");
    }

    #[test]
    fn a_cycle_in_the_tree_does_not_recurse_forever() {
        let mut b = Build::new();
        let name = b.intern("begin");
        let group = b.push(ExpressionType::Group, 4, 1, 0, 0);
        let name_node = b.push(ExpressionType::Expression, 2, 1, name, 0);
        b.exprs[group.index()].data = name_node.0;
        // The group's argument is the group itself.
        b.link(name_node, group);
        let s = b.finish();
        let d = Decompiler::new(&s);
        assert!(d
            .render(group, 0, At::default())
            .unwrap()
            .contains("nesting too deep"));
    }
}
