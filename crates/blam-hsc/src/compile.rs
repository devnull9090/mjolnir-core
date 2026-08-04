//! Compile HSC source into the expression tree a scenario carries.
//!
//! The game runs the tree, not the text, so this is what makes an edited script
//! actually do anything. It is the inverse of [`crate::decompile`], and the two
//! are tested against each other over the shipped campaign: compile a source
//! file, decompile the result, and the tokens should come back the same.
//!
//! # What this reproduces, and what it does not
//!
//! The output is **semantically** the tree the engine's own compiler produced,
//! not a byte-for-byte copy of it. Three things are deliberately ours:
//!
//! - **Datum generations.** The shipped arrays use two generation bases per
//!   scenario, an artifact of the engine compiler's datum allocator wrapping
//!   mid-run. A handle only has to agree with its target, so this emits one
//!   base throughout.
//! - **Free slots.** A shipped array is sparse — 56,415 of the campaign's
//!   272,190 slots are fill. This emits a dense array.
//! - **String blob.** The shipped blob repeats strings: 9,168 distinct offsets
//!   across 2,806 distinct strings in `a30`. This interns, so each string is
//!   written once.
//!
//! Everything the engine reads is reproduced: expression types, opcodes, value
//! types, sibling chains, and the rule that a call's first child names it and
//! carries the same opcode.

use std::collections::HashMap;

use crate::corpus::ScriptCorpus;
use crate::expr::{DatumHandle, Expression, ExpressionType, ValueTypes};
use crate::lex::Token;
use crate::parse::{self, Declaration, Form, Spanned, Vocabulary};
use crate::read::{Global, Parameter, Script, ScriptSection};

/// The datum generation this compiler starts counting from.
///
/// Not a cryptographic value: see [`crate::expr::DatumHandle`]. It is the ABA
/// counter a datum handle carries so a stale reference is detectable, and any
/// non-zero base works because a generation is only ever compared against the
/// one on the datum it points at. This is the base the shipped `a30` happens to
/// start from, chosen so a diff against shipped data reads as naturally as it
/// can.
const GENERATION_BASE: u16 = 0xE373;

/// How deep an expression may nest before compilation gives up.
const MAX_DEPTH: u32 = 128;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    /// The output is wrong or incomplete.
    Error,
    /// The output is probably right, but rests on an inference.
    Warning,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Diagnostic {
    pub severity: Severity,
    pub line: u32,
    pub message: String,
}

impl std::fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let kind = match self.severity {
            Severity::Error => "error",
            Severity::Warning => "warning",
        };
        write!(f, "line {}: {kind}: {}", self.line, self.message)
    }
}

/// The result of compiling one or more source files.
#[derive(Debug, Clone)]
pub struct Compiled {
    /// The script section, ready to be written back into a scenario.
    pub section: ScriptSection,
    pub diagnostics: Vec<Diagnostic>,
}

impl Compiled {
    pub fn errors(&self) -> impl Iterator<Item = &Diagnostic> {
        self.diagnostics
            .iter()
            .filter(|d| d.severity == Severity::Error)
    }

    pub fn ok(&self) -> bool {
        self.errors().next().is_none()
    }
}

/// What a name in scope refers to.
enum Resolved {
    /// A parameter or global: a value, so calling it is an error. Which of the
    /// two it is does not change the diagnostic, so neither is carried.
    Value,
    Script {
        index: u16,
        return_type: u16,
        parameters: Vec<u16>,
    },
    Function {
        opcode: u16,
    },
}

pub struct Compiler<'a> {
    corpus: Option<&'a ScriptCorpus>,
    value_types: ValueTypes,
    script_types: ValueTypes,

    expressions: Vec<Expression>,
    strings: Vec<u8>,
    interned: HashMap<String, u32>,
    scripts: Vec<Script>,
    globals: Vec<Global>,
    /// Script name to its index, for resolving calls. A name can be declared
    /// more than once — HSC overloads on arity — so each entry keeps every
    /// index and the arity chooses between them.
    script_index: HashMap<String, Vec<usize>>,
    global_index: HashMap<String, usize>,
    diagnostics: Vec<Diagnostic>,
}

impl<'a> Compiler<'a> {
    /// A compiler for one build, described by its two enums.
    pub fn new(value_types: ValueTypes, script_types: ValueTypes) -> Self {
        Compiler {
            corpus: None,
            value_types,
            script_types,
            // Offset 0 is a NUL so that an empty string interns to 0 and a
            // node with no string reads as empty rather than as whatever
            // happens to be first.
            expressions: Vec::new(),
            strings: vec![0],
            interned: HashMap::new(),
            scripts: Vec::new(),
            globals: Vec::new(),
            script_index: HashMap::new(),
            global_index: HashMap::new(),
            diagnostics: Vec::new(),
        }
    }

    /// Take the build's enums and the function table from a recovered corpus.
    pub fn from_corpus(corpus: &'a ScriptCorpus) -> Self {
        let mut c = Compiler::new(
            ValueTypes::new(corpus.value_types.clone()),
            ValueTypes::new(corpus.script_types.clone()),
        );
        c.corpus = Some(corpus);
        c
    }

    pub fn vocabulary(&self) -> Vocabulary {
        Vocabulary::new(self.value_types.names(), self.script_types.names())
    }

    /// Compile source files into one script section.
    ///
    /// Every file is parsed and every declaration collected before any body is
    /// compiled, so a script may call one declared later or in another file —
    /// which the shipped source does constantly.
    pub fn compile(mut self, files: &[(&str, &str)]) -> Compiled {
        let vocab = self.vocabulary();
        let mut declarations = Vec::new();

        for (name, text) in files {
            let (forms, parse_errors) = parse::parse_recovering(text);
            for e in parse_errors {
                self.error(e.line, format!("{}: {}", name, e.message));
            }
            let (decls, errors) = parse::declarations(&forms, &vocab);
            for e in errors {
                self.error(e.line, format!("{}: {}", name, e.message));
            }
            declarations.extend(decls);
        }

        self.declare(&declarations);
        self.emit_all(&declarations);

        let section = ScriptSection {
            strings: self.strings,
            expressions: self.expressions,
            scripts: self.scripts,
            globals: self.globals,
            source_files: Vec::new(),
            references: Vec::new(),
            value_types: self.value_types,
            script_types: self.script_types,
            // A compiled section has no tag behind it; the shapes come from the
            // scenario it is written into.
            shapes: crate::read::Shapes::default(),
        };
        Compiled {
            section,
            diagnostics: self.diagnostics,
        }
    }

    /// Pass one: reserve a slot for every script and global.
    fn declare(&mut self, declarations: &[Declaration]) {
        for d in declarations {
            match d {
                Declaration::Script {
                    name,
                    kind,
                    return_type,
                    parameters,
                    line,
                    ..
                } => {
                    let Some(script_type) = self.script_types.index_of(kind) else {
                        self.error(*line, format!("`{kind}` is not a script kind"));
                        continue;
                    };
                    let resolved_return = self.value_type(return_type, *line);
                    let resolved_params: Vec<Parameter> = parameters
                        .iter()
                        .map(|p| Parameter {
                            name: p.name.clone(),
                            value_type: self.value_type(&p.value_type, *line),
                        })
                        .collect();
                    let index = self.scripts.len();
                    self.script_index
                        .entry(name.clone())
                        .or_default()
                        .push(index);
                    self.scripts.push(Script {
                        name: name.clone(),
                        script_type,
                        return_type: resolved_return,
                        // Patched once the body is compiled.
                        root: DatumHandle::NULL,
                        parameters: resolved_params,
                    });
                }
                Declaration::Global {
                    name,
                    value_type,
                    line,
                    ..
                } => {
                    if self.global_index.contains_key(name) {
                        self.error(*line, format!("`{name}` is declared more than once"));
                    }
                    let resolved = self.value_type(value_type, *line);
                    self.global_index.insert(name.clone(), self.globals.len());
                    self.globals.push(Global {
                        name: name.clone(),
                        value_type: resolved,
                        initializer: DatumHandle::NULL,
                    });
                }
            }
        }
    }

    /// Pass two: compile every body.
    fn emit_all(&mut self, declarations: &[Declaration]) {
        let mut script_at = 0usize;
        let mut global_at = 0usize;

        for d in declarations {
            match d {
                Declaration::Script {
                    parameters, line, ..
                } => {
                    let index = script_at;
                    script_at += 1;
                    if index >= self.scripts.len() {
                        continue;
                    }
                    let params: Vec<(String, u16)> = parameters
                        .iter()
                        .zip(&self.scripts[index].parameters)
                        .map(|(p, resolved)| (p.name.clone(), resolved.value_type))
                        .collect();
                    let Declaration::Script { body, .. } = d else {
                        unreachable!()
                    };
                    let expected = self.scripts[index].return_type;
                    let root = self.emit_body(body, expected, &params, *line);
                    self.scripts[index].root = root;
                }
                Declaration::Global {
                    initializer, line, ..
                } => {
                    let index = global_at;
                    global_at += 1;
                    if index >= self.globals.len() {
                        continue;
                    }
                    let expected = self.globals[index].value_type;
                    let handle = match initializer {
                        Some(form) => self.emit(form, &[expected], &[], 0),
                        None => {
                            self.error(*line, "a global needs a starting value".into());
                            DatumHandle::NULL
                        }
                    };
                    self.globals[index].initializer = handle;
                }
            }
        }
    }

    /// A script body, always wrapped in `begin`.
    ///
    /// Every one of the 6,827 shipped scripts has a `begin` group at its root,
    /// including the single-statement ones, so this wraps unconditionally
    /// rather than trying to be clever about it.
    fn emit_body(
        &mut self,
        body: &[Spanned],
        expected: u16,
        params: &[(String, u16)],
        line: u32,
    ) -> DatumHandle {
        let Some(begin) = self.function_opcode("begin") else {
            self.error(line, "the function table has no `begin`".into());
            return DatumHandle::NULL;
        };
        let start_line = body.first().map(|f| f.line).unwrap_or(line);
        let group = self.alloc(Expression {
            generation: 0,
            opcode: begin,
            value_type: expected,
            expression_type: ExpressionType::Group,
            next: DatumHandle::NULL,
            string_offset: 0,
            data: 0,
            line: start_line as u16,
            tail: 0,
        });
        let begin_string = self.intern("begin");
        let name_type = self.function_name_type();
        let name = self.alloc(Expression {
            generation: 0,
            opcode: begin,
            value_type: name_type,
            expression_type: ExpressionType::Expression,
            next: DatumHandle::NULL,
            string_offset: begin_string,
            data: 0,
            line: start_line as u16,
            tail: 0,
        });
        self.expressions[group.index()].data = name.0;

        let mut prev = name;
        for form in body {
            let child = self.emit(form, &[], params, 1);
            if child.is_null() {
                continue;
            }
            self.expressions[prev.index()].next = child;
            prev = child;
        }
        group
    }

    /// Compile one form, and return the handle of the node it became.
    fn emit(
        &mut self,
        form: &Spanned,
        expected: &[u16],
        params: &[(String, u16)],
        depth: u32,
    ) -> DatumHandle {
        if depth > MAX_DEPTH {
            self.error(form.line, "expression nests too deeply".into());
            return DatumHandle::NULL;
        }
        match &form.form {
            Form::List(items) => self.emit_call(items, form.line, expected, params, depth),
            Form::Atom(token) => self.emit_atom(token, form.line, expected, params),
        }
    }

    fn emit_call(
        &mut self,
        items: &[Spanned],
        line: u32,
        expected: &[u16],
        params: &[(String, u16)],
        depth: u32,
    ) -> DatumHandle {
        let Some(head) = items.first() else {
            self.error(line, "`()` is not an expression".into());
            return DatumHandle::NULL;
        };
        let Some(name) = head.word() else {
            self.error(line, "a call must start with a name".into());
            return DatumHandle::NULL;
        };
        let args = &items[1..];

        // `cond` never reaches the tree: the engine's compiler rewrites it into
        // nested `if` before emitting anything, which is why no opcode exists
        // for it. Doing the same here keeps the two in step.
        if name == "cond" {
            return self.emit_cond(args, line, expected, params, depth);
        }

        let Some(resolved) = self.resolve(name, params, args.len()) else {
            self.error(line, format!("`{name}` is not a known function or script"));
            return DatumHandle::NULL;
        };

        let (opcode, kind, return_type, arg_types) = match resolved {
            Resolved::Function { opcode } => (
                opcode,
                ExpressionType::Group,
                expected
                    .first()
                    .copied()
                    .or_else(|| self.corpus_return(opcode)),
                self.corpus_parameters(opcode, args.len()),
            ),
            Resolved::Script {
                index,
                return_type,
                parameters,
            } => (
                index,
                ExpressionType::ScriptReference,
                Some(return_type),
                parameters.into_iter().map(|t| vec![t]).collect(),
            ),
            // A global or parameter in head position is not a call.
            Resolved::Value => {
                self.error(line, format!("`{name}` is a value, not a function"));
                return DatumHandle::NULL;
            }
        };

        let group = self.alloc(Expression {
            generation: 0,
            opcode,
            value_type: return_type.unwrap_or_else(|| self.void_type()),
            expression_type: kind,
            next: DatumHandle::NULL,
            string_offset: 0,
            data: 0,
            line: line as u16,
            tail: 0,
        });
        // The first child names the callee and carries the same opcode — true
        // of all 65,703 shipped calls without exception.
        let callee_string = self.intern(name);
        let name_type = self.function_name_type();
        let name_node = self.alloc(Expression {
            generation: 0,
            opcode,
            value_type: name_type,
            expression_type: ExpressionType::Expression,
            next: DatumHandle::NULL,
            string_offset: callee_string,
            data: 0,
            line: line as u16,
            tail: 0,
        });
        self.expressions[group.index()].data = name_node.0;

        let mut prev = name_node;
        for (i, arg) in args.iter().enumerate() {
            let want: &[u16] = arg_types.get(i).map(Vec::as_slice).unwrap_or(&[]);
            let child = self.emit(arg, want, params, depth + 1);
            if child.is_null() {
                continue;
            }
            self.expressions[prev.index()].next = child;
            prev = child;
        }
        group
    }

    /// `(cond (test body...) ...)` becomes `(if test (begin body...) <rest>)`.
    fn emit_cond(
        &mut self,
        clauses: &[Spanned],
        line: u32,
        expected: &[u16],
        params: &[(String, u16)],
        depth: u32,
    ) -> DatumHandle {
        let Some((first, rest)) = clauses.split_first() else {
            self.error(line, "`cond` needs at least one clause".into());
            return DatumHandle::NULL;
        };
        let Some(parts) = first.items() else {
            self.error(
                first.line,
                "a `cond` clause is written `(test body…)`".into(),
            );
            return DatumHandle::NULL;
        };
        let Some((test, body)) = parts.split_first() else {
            self.error(first.line, "a `cond` clause needs a test".into());
            return DatumHandle::NULL;
        };

        // Rebuild as `(if <test> (begin <body…>) <cond of the rest>)` and
        // compile that, so there is one emission path rather than two.
        let mut rewritten = vec![
            atom_word("if", first.line),
            test.clone(),
            Spanned {
                form: Form::List(
                    std::iter::once(atom_word("begin", first.line))
                        .chain(body.iter().cloned())
                        .collect(),
                ),
                line: first.line,
            },
        ];
        if !rest.is_empty() {
            rewritten.push(Spanned {
                form: Form::List(
                    std::iter::once(atom_word("cond", rest[0].line))
                        .chain(rest.iter().cloned())
                        .collect(),
                ),
                line: rest[0].line,
            });
        }
        self.emit_call(&rewritten, line, expected, params, depth)
    }

    fn emit_atom(
        &mut self,
        token: &Token,
        line: u32,
        expected: &[u16],
        params: &[(String, u16)],
    ) -> DatumHandle {
        match token {
            Token::Word(w) => {
                // A parameter shadows a global, which shadows everything else:
                // the innermost binding wins, as it does in the engine.
                if let Some((index, value_type)) = params
                    .iter()
                    .position(|(n, _)| n == w)
                    .map(|i| (i as u16, params[i].1))
                {
                    let offset = self.intern(w);
                    return self.alloc(Expression {
                        generation: 0,
                        opcode: value_type,
                        value_type,
                        expression_type: ExpressionType::ParameterReference,
                        next: DatumHandle::NULL,
                        string_offset: offset,
                        data: index as u32,
                        line: line as u16,
                        tail: 0,
                    });
                }
                if let Some(&index) = self.global_index.get(w.as_str()) {
                    let value_type = self.globals[index].value_type;
                    let offset = self.intern(w);
                    return self.alloc(Expression {
                        generation: 0,
                        opcode: value_type,
                        value_type,
                        expression_type: ExpressionType::GlobalsReference,
                        next: DatumHandle::NULL,
                        string_offset: offset,
                        // A globals reference carries its index in `data`, not
                        // in `opcode` — verified across 11,048 shipped nodes.
                        data: index as u32,
                        line: line as u16,
                        tail: 0,
                    });
                }
                self.emit_literal(token, line, expected)
            }
            _ => self.emit_literal(token, line, expected),
        }
    }

    /// A literal, typed by the position it sits in where that is known.
    fn emit_literal(&mut self, token: &Token, line: u32, expected: &[u16]) -> DatumHandle {
        let (value_type, guessed) = self.choose_type(token, expected);
        let type_name = self
            .value_types
            .name_of(value_type)
            .unwrap_or("")
            .to_string();

        let (data, string_offset) = match token {
            Token::Num(n) => match type_name.as_str() {
                "real" => (f32::to_bits(*n as f32), 0),
                "long" => ((*n as i64 as i32) as u32, 0),
                "boolean" => (u32::from(*n != 0.0), 0),
                // `short` and anything else numeric: the engine widens on read.
                _ => ((*n as i64 as i16) as u16 as u32, 0),
            },
            Token::Word(w) if w == "true" => (1, 0),
            Token::Word(w) if w == "false" => (0, 0),
            // `none` is the unset sentinel for a reference-typed position.
            Token::Word(w) if w == "none" => (u32::MAX, 0),
            Token::Word(w) => {
                // A bare word in a value position names something in the
                // scenario: an object, a trigger volume, an enum case.
                let offset = self.intern(w);
                (0, offset)
            }
            Token::Str(s) => {
                let offset = self.intern(s);
                (0, offset)
            }
            Token::Open | Token::Close => (0, 0),
        };

        if guessed {
            self.warn(
                line,
                format!(
                    "nothing here says what type {} should be; compiled as `{}`",
                    token.describe(),
                    if type_name.is_empty() {
                        "void"
                    } else {
                        &type_name
                    }
                ),
            );
        }

        self.alloc(Expression {
            generation: 0,
            opcode: value_type,
            value_type,
            expression_type: ExpressionType::Expression,
            next: DatumHandle::NULL,
            string_offset,
            data,
            line: line as u16,
            tail: 0,
        })
    }

    /// Pick the type for a literal, and say whether it was a guess.
    ///
    /// The position proposes and the token disposes. Taking the position's most
    /// common type on its own gets real cases wrong: the corpus says `set`
    /// usually takes a `boolean`, so `(set s_music_trigger 30)` compiled 30 to
    /// `true`, and it says `<` usually takes a `short`, so `0.6` compiled to
    /// `0`. A literal cannot be a type that cannot hold it, so the candidates
    /// are tried in order of how often the position uses them and the first one
    /// that actually fits wins.
    fn choose_type(&self, token: &Token, expected: &[u16]) -> (u16, bool) {
        for candidate in expected {
            let name = self.value_types.name_of(*candidate).unwrap_or("");
            if fits(name, token) {
                return (*candidate, false);
            }
        }
        // Nothing the position is known to take can hold this value, so fall
        // back to what the token itself says it is.
        match self.infer_type(token) {
            Some(t) => (t, false),
            // A bare name with no usable type: keep it rendering as a name
            // rather than as a number, which is what a numeric type would do.
            None => (
                self.value_types
                    .index_of("string_id")
                    .or_else(|| self.value_types.index_of("string"))
                    .unwrap_or_else(|| self.void_type()),
                true,
            ),
        }
    }

    /// The type a literal is when nothing else says.
    fn infer_type(&self, token: &Token) -> Option<u16> {
        match token {
            Token::Num(n) if n.fract() != 0.0 => self.value_types.index_of("real"),
            Token::Num(n) if *n >= i16::MIN as f64 && *n <= i16::MAX as f64 => {
                self.value_types.index_of("short")
            }
            Token::Num(_) => self.value_types.index_of("long"),
            Token::Word(w) if w == "true" || w == "false" => self.value_types.index_of("boolean"),
            Token::Str(_) => self.value_types.index_of("string"),
            _ => None,
        }
    }

    fn resolve(&self, name: &str, params: &[(String, u16)], arity: usize) -> Option<Resolved> {
        if params.iter().any(|(n, _)| n == name) || self.global_index.contains_key(name) {
            return Some(Resolved::Value);
        }
        if let Some(candidates) = self.script_index.get(name) {
            // Overloads differ only in arity, so that is what picks between
            // them; with no exact match the first declaration stands in.
            let pick = candidates
                .iter()
                .find(|i| self.scripts[**i].parameters.len() == arity)
                .or_else(|| candidates.first())?;
            let s = &self.scripts[*pick];
            return Some(Resolved::Script {
                index: *pick as u16,
                return_type: s.return_type,
                parameters: s.parameters.iter().map(|p| p.value_type).collect(),
            });
        }
        self.function_opcode(name)
            .map(|opcode| Resolved::Function { opcode })
    }

    fn function_opcode(&self, name: &str) -> Option<u16> {
        self.corpus?.by_name(name).map(|(opcode, _)| opcode)
    }

    /// The type this function is most often seen returning.
    fn corpus_return(&self, opcode: u16) -> Option<u16> {
        let f = self.corpus?.functions.get(&opcode)?;
        let best = f.returns.iter().max_by_key(|(_, n)| **n)?.0;
        self.value_types.index_of(best)
    }

    /// The type most often seen at each argument position.
    ///
    /// A variadic function like `begin` has no meaningful type past the
    /// positions the corpus models, so those come back as `None` and the
    /// literal falls back to inferring from its own syntax.
    fn corpus_parameters(&self, opcode: u16, arity: usize) -> Vec<Vec<u16>> {
        let Some(f) = self.corpus.and_then(|c| c.functions.get(&opcode)) else {
            return vec![Vec::new(); arity];
        };
        (0..arity)
            .map(|i| {
                let Some(p) = f.parameters.get(i) else {
                    return Vec::new();
                };
                // Every type this position has been seen holding, commonest
                // first, so a rarer but compatible one is still reachable.
                let mut by_count: Vec<(&String, &u32)> = p.types.iter().collect();
                by_count.sort_by_key(|(name, n)| (std::cmp::Reverse(**n), (*name).clone()));
                by_count
                    .into_iter()
                    .filter_map(|(name, _)| self.value_types.index_of(name))
                    .collect()
            })
            .collect()
    }

    fn value_type(&mut self, name: &str, line: u32) -> u16 {
        match self.value_types.index_of(name) {
            Some(i) => i,
            None => {
                self.error(line, format!("`{name}` is not a value type"));
                0
            }
        }
    }

    fn function_name_type(&self) -> u16 {
        self.value_types.function_name().unwrap_or(2)
    }

    fn void_type(&self) -> u16 {
        self.value_types.index_of("void").unwrap_or(4)
    }

    /// Append a datum, stamping the generation its index implies.
    fn alloc(&mut self, mut e: Expression) -> DatumHandle {
        let index = self.expressions.len();
        // Wider than a datum array can address means the handle would alias, so
        // stop rather than emit a tree that resolves to the wrong nodes.
        if index > u16::MAX as usize {
            if self.expressions.len() == u16::MAX as usize + 1 {
                self.error(
                    e.line as u32,
                    "more than 65,535 expressions; a datum handle cannot address them".into(),
                );
            }
            return DatumHandle::NULL;
        }
        let generation = GENERATION_BASE.wrapping_add(index as u16);
        e.generation = if generation == 0 { 1 } else { generation };
        self.expressions.push(e);
        DatumHandle::new(index as u16, e.generation)
    }

    /// Add a string to the blob, reusing one already there.
    fn intern(&mut self, text: &str) -> u32 {
        if text.is_empty() {
            return 0;
        }
        if let Some(&at) = self.interned.get(text) {
            return at;
        }
        let at = self.strings.len() as u32;
        self.strings.extend_from_slice(text.as_bytes());
        self.strings.push(0);
        self.interned.insert(text.to_string(), at);
        at
    }

    fn error(&mut self, line: u32, message: String) {
        self.diagnostics.push(Diagnostic {
            severity: Severity::Error,
            line,
            message,
        });
    }

    fn warn(&mut self, line: u32, message: String) {
        self.diagnostics.push(Diagnostic {
            severity: Severity::Warning,
            line,
            message,
        });
    }
}

/// Whether a value of this type could be written as this token.
///
/// This is the check that stops a position's most common type from being
/// forced onto a literal that cannot be one. It is deliberately about what the
/// *syntax* can express, not about what the engine would coerce at runtime —
/// the engine will happily widen a short to a real, but a source token with a
/// decimal point was never a short to begin with.
fn fits(type_name: &str, token: &Token) -> bool {
    match token {
        Token::Num(n) => match type_name {
            "real" => true,
            "boolean" => *n == 0.0 || *n == 1.0,
            "short" => n.fract() == 0.0 && *n >= i16::MIN as f64 && *n <= i16::MAX as f64,
            "long" => n.fract() == 0.0 && *n >= i32::MIN as f64 && *n <= i32::MAX as f64,
            // A bare number is not a name, a string, or nothing.
            _ => false,
        },
        Token::Str(_) => !matches!(
            type_name,
            "void" | "unparsed" | "boolean" | "short" | "long" | "real"
        ),
        Token::Word(w) if w == "true" || w == "false" => type_name == "boolean",
        // `none` is the unset value of any type that can be a reference.
        Token::Word(w) if w == "none" => !matches!(
            type_name,
            "void" | "unparsed" | "boolean" | "short" | "long" | "real"
        ),
        // Any other bare word names something, so it needs a type that carries
        // a name rather than a number.
        Token::Word(_) => !matches!(
            type_name,
            "void" | "unparsed" | "boolean" | "short" | "long" | "real" | ""
        ),
        Token::Open | Token::Close => false,
    }
}

fn atom_word(w: &str, line: u32) -> Spanned {
    Spanned {
        form: Form::Atom(Token::Word(w.to_string())),
        line,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::corpus::{FunctionDef, ParameterDef};
    use crate::Decompiler;
    use std::collections::BTreeMap;

    fn types() -> Vec<String> {
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
        .collect()
    }

    fn function(name: &str, returns: &str, params: &[&str]) -> FunctionDef {
        FunctionDef {
            name: name.to_string(),
            returns: BTreeMap::from([(returns.to_string(), 10)]),
            min_args: params.len(),
            max_args: params.len(),
            parameters: params
                .iter()
                .map(|t| ParameterDef {
                    types: BTreeMap::from([(t.to_string(), 10)]),
                    always_present: true,
                    quoted: None,
                    quoting: Default::default(),
                })
                .collect(),
            call_sites: 10,
            scenarios: 1,
        }
    }

    fn corpus() -> ScriptCorpus {
        ScriptCorpus {
            value_types: types(),
            script_types: [
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
            functions: BTreeMap::from([
                (0, function("begin", "void", &[])),
                (4, function("if", "void", &["boolean", "void", "void"])),
                (6, function("set", "void", &["boolean", "boolean"])),
                (16, function("=", "boolean", &["short", "short"])),
                (26, function("wake", "void", &["script"])),
                (49, function("print", "void", &["string"])),
                (100, function("sleep", "void", &["short"])),
                (200, function("ai_place", "void", &["ai"])),
                (300, function("unit_get_health", "real", &["unit"])),
            ]),
            ..ScriptCorpus::default()
        }
    }

    fn compile(src: &str) -> Compiled {
        let corpus = corpus();
        Compiler::from_corpus(&corpus).compile(&[("test", src)])
    }

    /// Compile, then decompile, and return the text.
    fn round_trip(src: &str) -> (String, Vec<Diagnostic>) {
        let c = compile(src);
        let d = Decompiler::new(&c.section);
        (d.scenario(), c.diagnostics)
    }

    #[test]
    fn a_script_compiles_to_a_begin_rooted_tree() {
        let c = compile("(script dormant on_wake (sleep 3))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        assert_eq!(c.section.scripts.len(), 1);
        let root = c.section.get(c.section.scripts[0].root).unwrap();
        assert_eq!(root.expression_type, ExpressionType::Group);
        assert_eq!(c.section.callee_name(root), Some("begin"));
    }

    #[test]
    fn a_calls_first_child_names_it_and_shares_its_opcode() {
        let c = compile("(script dormant on_wake (sleep 3))");
        let sleep = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| c.section.callee_name(e) == Some("sleep"))
            .unwrap();
        let name = c.section.get(sleep.first_child().unwrap()).unwrap();
        assert_eq!(name.opcode, sleep.opcode);
        assert_eq!(name.value_type, 2); // function_name
        assert_eq!(c.section.string_at(name.string_offset), "sleep");
    }

    #[test]
    fn a_literal_takes_the_type_of_the_position_it_sits_in() {
        // `unit_get_health` returns a real, `sleep` takes a short; the literal
        // 1 in each position must be typed differently.
        let c = compile("(script dormant f (sleep 1))");
        let arg = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| e.expression_type == ExpressionType::Expression && e.value_type == 7)
            .expect("a short literal");
        assert_eq!(arg.data, 1);
    }

    #[test]
    fn a_global_reference_carries_its_index_in_data() {
        let c = compile("(global boolean b_awake false)\n(script dormant f (set b_awake true))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        let g = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| e.expression_type == ExpressionType::GlobalsReference)
            .unwrap();
        assert_eq!(g.data, 0);
        assert_eq!(c.section.string_at(g.string_offset), "b_awake");
        assert_eq!(g.value_type, 5); // boolean
    }

    #[test]
    fn a_parameter_reference_carries_its_index_and_declared_type() {
        let c = compile("(script static void (f (short delay) (ai who)) (sleep delay))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        let p = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| e.expression_type == ExpressionType::ParameterReference)
            .unwrap();
        assert_eq!(p.data, 0);
        assert_eq!(p.value_type, 7); // short
        assert_eq!(c.section.string_at(p.string_offset), "delay");
    }

    #[test]
    fn a_parameter_shadows_a_global_of_the_same_name() {
        let c =
            compile("(global short delay 0)\n(script static void (f (short delay)) (sleep delay))");
        let kinds: Vec<_> = c
            .section
            .live()
            .map(|(_, e)| e.expression_type)
            .filter(|t| {
                matches!(
                    t,
                    ExpressionType::ParameterReference | ExpressionType::GlobalsReference
                )
            })
            .collect();
        assert_eq!(kinds, vec![ExpressionType::ParameterReference]);
    }

    #[test]
    fn a_call_to_another_script_is_a_script_reference_not_a_function() {
        let c = compile("(script static void helper (sleep 1))\n(script dormant f (helper))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        let r = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| e.expression_type == ExpressionType::ScriptReference)
            .unwrap();
        assert_eq!(r.opcode, 0); // index of `helper`
        assert_eq!(c.section.callee_name(r), Some("helper"));
    }

    #[test]
    fn a_script_may_call_one_declared_later() {
        let c = compile("(script dormant f (helper))\n(script static void helper (sleep 1))");
        assert!(c.ok(), "{:?}", c.diagnostics);
    }

    #[test]
    fn an_overload_is_chosen_by_how_many_arguments_the_call_passes() {
        let c = compile(
            "(script static void (h (short a)) (sleep a))\n\
             (script static void (h (short a) (ai b)) (sleep a))\n\
             (script dormant f (h 1 sq_marines))",
        );
        assert!(c.ok(), "{:?}", c.diagnostics);
        let r = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| e.expression_type == ExpressionType::ScriptReference)
            .unwrap();
        assert_eq!(r.opcode, 1, "the two-parameter overload");
    }

    #[test]
    fn an_unknown_name_is_an_error_naming_the_line() {
        let c = compile("(script dormant f\n\t(no_such_function 1))");
        assert!(!c.ok());
        let e = c.errors().next().unwrap();
        assert_eq!(e.line, 2);
        assert!(e.message.contains("no_such_function"), "{}", e.message);
    }

    #[test]
    fn strings_are_interned_so_a_repeat_costs_nothing() {
        let c = compile("(script dormant f (print \"hi\") (print \"hi\"))");
        let offsets: Vec<u32> = c
            .section
            .live()
            .map(|(_, e)| e)
            .filter(|e| c.section.string_at(e.string_offset) == "hi")
            .map(|e| e.string_offset)
            .collect();
        assert_eq!(offsets.len(), 2);
        assert_eq!(offsets[0], offsets[1]);
    }

    #[test]
    fn every_handle_resolves_against_the_generation_it_was_given() {
        let c = compile("(script dormant f (if (= 1 2) (sleep 1) (sleep 2)))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        for (_, e) in c.section.live() {
            if let Some(child) = e.first_child() {
                assert!(
                    c.section.get(child).is_some(),
                    "child {child} does not resolve"
                );
            }
            if !e.next.is_null() {
                assert!(
                    c.section.get(e.next).is_some(),
                    "next {} does not resolve",
                    e.next
                );
            }
        }
    }

    #[test]
    fn cond_is_rewritten_into_nested_if_as_the_engine_does() {
        let c = compile("(script dormant f (cond ((= 1 2) (sleep 1)) ((= 3 4) (sleep 2))))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        // No opcode exists for `cond`, so none may appear.
        assert!(c
            .section
            .live()
            .all(|(_, e)| c.section.callee_name(e) != Some("cond")));
        let ifs = c
            .section
            .live()
            .filter(|(_, e)| c.section.callee_name(e) == Some("if"))
            .count();
        assert_eq!(ifs, 2);
    }

    #[test]
    fn a_compiled_script_decompiles_back_to_what_went_in() {
        let src = "(script dormant on_wake\n\t(sleep 3)\n\t(print \"awake\")\n)";
        let (out, diags) = round_trip(src);
        assert!(
            !diags.iter().any(|d| d.severity == Severity::Error),
            "{diags:?}"
        );
        let want = crate::lex::tokens(src);
        let got = crate::lex::tokens(&out);
        assert!(
            want.iter().zip(&got).all(|(a, b)| a.means_same(b)) && want.len() == got.len(),
            "\n in: {src}\nout: {out}"
        );
    }

    #[test]
    fn a_global_and_its_initializer_survive_a_round_trip() {
        let (out, _) = round_trip("(global short s_count 3)");
        assert!(out.contains("(global short s_count 3)"), "{out}");
    }

    /// The value type of the first literal argument of the first call in the
    /// body, by name.
    fn first_literal_type(c: &Compiled) -> &str {
        let e = c
            .section
            .live()
            .map(|(_, e)| e)
            .filter(|e| e.expression_type == ExpressionType::Expression)
            .find(|e| e.value_type != 2)
            .expect("a literal");
        c.section.value_types.name_of(e.value_type).unwrap()
    }

    #[test]
    fn a_number_with_a_fraction_is_never_compiled_as_a_short() {
        // `=` is most often seen taking shorts, but 0.6 is not one. Taking the
        // position's commonest type on its own compiled this to 0.
        let c = compile("(script dormant f (= 0.6 1))");
        assert_eq!(first_literal_type(&c), "real");
    }

    #[test]
    fn a_number_that_is_not_zero_or_one_is_never_compiled_as_a_boolean() {
        // `set` is most often seen taking booleans; 30 is not one.
        let c = compile("(script dormant f (set 30 1))");
        assert_eq!(first_literal_type(&c), "short");
    }

    #[test]
    fn a_bare_name_is_never_compiled_as_a_number() {
        // `sleep` takes a short, but a name cannot be one — compiling it as a
        // short renders it back as `0`, losing the name entirely.
        let c = compile("(script dormant f (sleep some_marker))");
        assert_ne!(first_literal_type(&c), "short");
        let e = c
            .section
            .live()
            .map(|(_, e)| e)
            .find(|e| c.section.string_at(e.string_offset) == "some_marker")
            .expect("the name survives");
        assert_ne!(e.string_offset, 0);
    }

    #[test]
    fn a_position_that_fits_still_wins() {
        // The rule must not throw away a correct type: `sleep` takes a short
        // and 3 is one.
        let c = compile("(script dormant f (sleep 3))");
        assert_eq!(first_literal_type(&c), "short");
    }

    #[test]
    fn what_a_type_can_hold_is_checked_against_the_token() {
        assert!(fits("short", &Token::Num(3.0)));
        assert!(!fits("short", &Token::Num(3.5)));
        assert!(!fits("short", &Token::Num(40000.0)));
        assert!(fits("real", &Token::Num(3.5)));
        assert!(fits("boolean", &Token::Num(1.0)));
        assert!(!fits("boolean", &Token::Num(30.0)));
        assert!(fits("boolean", &Token::Word("true".into())));
        assert!(!fits("short", &Token::Word("marker".into())));
        assert!(fits("ai", &Token::Word("sq_marines".into())));
        assert!(fits("ai", &Token::Word("none".into())));
        assert!(!fits("short", &Token::Word("none".into())));
        assert!(fits("string", &Token::Str("hi".into())));
        assert!(!fits("real", &Token::Str("hi".into())));
    }

    #[test]
    fn an_untypeable_literal_warns_rather_than_failing_silently() {
        // `begin` models no argument types, so a bare name in it has nothing
        // to take a type from.
        let c = compile("(script dormant f (begin some_name))");
        assert!(c.ok(), "{:?}", c.diagnostics);
        assert!(c
            .diagnostics
            .iter()
            .any(|d| d.severity == Severity::Warning && d.message.contains("nothing here says")));
    }
}
