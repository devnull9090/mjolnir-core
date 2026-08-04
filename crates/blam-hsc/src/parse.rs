//! Parse HSC source into forms and declarations.
//!
//! HSC is S-expression syntax, so the tree is trivial; the work is in the
//! `(script ...)` header, which is genuinely ambiguous at the token level.
//! `(script static void f_a ...)` and `(script dormant f_b ...)` have the same
//! shape, and only knowing that `void` names a type separates the return type
//! from the script name — which is why parsing needs a [`Vocabulary`].

use std::collections::BTreeSet;

use crate::lex::{self, Lexeme, Token};

/// One node of the source tree.
#[derive(Debug, Clone, PartialEq)]
pub enum Form {
    Atom(Token),
    List(Vec<Spanned>),
}

/// A form and the line it started on.
#[derive(Debug, Clone, PartialEq)]
pub struct Spanned {
    pub form: Form,
    pub line: u32,
}

impl Spanned {
    /// The bare word this form is, if it is one.
    pub fn word(&self) -> Option<&str> {
        match &self.form {
            Form::Atom(Token::Word(w)) => Some(w),
            _ => None,
        }
    }

    pub fn items(&self) -> Option<&[Spanned]> {
        match &self.form {
            Form::List(items) => Some(items),
            _ => None,
        }
    }
}

/// The type and script-kind names of the build being compiled for.
///
/// Both come from the tag itself — see [`crate::expr::ValueTypes`] — because
/// they are per-build. Hard-coding them here would make the parser wrong the
/// first time an engine update inserts a type.
#[derive(Debug, Clone, Default)]
pub struct Vocabulary {
    pub value_types: BTreeSet<String>,
    pub script_types: BTreeSet<String>,
}

impl Vocabulary {
    pub fn new(value_types: &[String], script_types: &[String]) -> Self {
        Vocabulary {
            value_types: value_types.iter().cloned().collect(),
            script_types: script_types.iter().cloned().collect(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub line: u32,
    pub message: String,
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

/// Parse a whole source file into top-level forms, stopping at the first error.
pub fn parse(src: &str) -> Result<Vec<Spanned>, ParseError> {
    let lexemes = lex::tokenize(src);
    let mut pos = 0usize;
    let mut out = Vec::new();
    while pos < lexemes.len() {
        out.push(parse_form(&lexemes, &mut pos)?);
    }
    Ok(out)
}

/// Parse, keeping going past a stray `)`.
///
/// Worth the extra path because the shipped source needs it: `a30` has one
/// extra `)` at line 2030, which closes `mission_obj` early. Giving up there
/// would throw away the other 500-odd scripts in the file over one typo, and an
/// editor that reported a single error and no outline for a 4,449-line file
/// would be useless.
///
/// A `(` that is never closed still ends the parse — there is nothing after it
/// to recover to.
pub fn parse_recovering(src: &str) -> (Vec<Spanned>, Vec<ParseError>) {
    let lexemes = lex::tokenize(src);
    let mut pos = 0usize;
    let mut out = Vec::new();
    let mut errors = Vec::new();

    while pos < lexemes.len() {
        if lexemes[pos].token == Token::Close {
            errors.push(ParseError {
                line: lexemes[pos].line,
                message: "unmatched `)`".into(),
            });
            pos += 1;
            continue;
        }
        match parse_form(&lexemes, &mut pos) {
            Ok(form) => out.push(form),
            Err(e) => {
                errors.push(e);
                break;
            }
        }
    }
    (out, errors)
}

fn parse_form(lexemes: &[Lexeme], pos: &mut usize) -> Result<Spanned, ParseError> {
    let l = &lexemes[*pos];
    match &l.token {
        Token::Close => Err(ParseError {
            line: l.line,
            message: "unmatched `)`".into(),
        }),
        Token::Open => {
            let line = l.line;
            *pos += 1;
            let mut items = Vec::new();
            loop {
                let Some(next) = lexemes.get(*pos) else {
                    return Err(ParseError {
                        line,
                        message: "`(` is never closed".into(),
                    });
                };
                if next.token == Token::Close {
                    *pos += 1;
                    return Ok(Spanned {
                        form: Form::List(items),
                        line,
                    });
                }
                items.push(parse_form(lexemes, pos)?);
            }
        }
        token => {
            let out = Spanned {
                form: Form::Atom(token.clone()),
                line: l.line,
            };
            *pos += 1;
            Ok(out)
        }
    }
}

/// A parameter of a script: `(short delay)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Parameter {
    pub value_type: String,
    pub name: String,
}

/// A top-level declaration.
#[derive(Debug, Clone, PartialEq)]
pub enum Declaration {
    Script {
        name: String,
        /// `startup`, `dormant`, `static`, …
        kind: String,
        /// Omitted in the source for every kind but `static` and `stub`, where
        /// it defaults to `void`.
        return_type: String,
        parameters: Vec<Parameter>,
        body: Vec<Spanned>,
        line: u32,
    },
    Global {
        name: String,
        value_type: String,
        initializer: Option<Spanned>,
        line: u32,
    },
}

impl Declaration {
    pub fn name(&self) -> &str {
        match self {
            Declaration::Script { name, .. } | Declaration::Global { name, .. } => name,
        }
    }

    pub fn line(&self) -> u32 {
        match self {
            Declaration::Script { line, .. } | Declaration::Global { line, .. } => *line,
        }
    }
}

/// Read the declarations out of a parsed file.
///
/// A top-level form that is neither a script nor a global is reported rather
/// than skipped: HSC has no other top-level form, so one is a typo worth
/// surfacing.
pub fn declarations(forms: &[Spanned], vocab: &Vocabulary) -> (Vec<Declaration>, Vec<ParseError>) {
    let mut out = Vec::new();
    let mut errors = Vec::new();

    for form in forms {
        let Some(items) = form.items() else {
            errors.push(ParseError {
                line: form.line,
                message: format!(
                    "expected a `(script ...)` or `(global ...)` declaration, found {}",
                    describe(form)
                ),
            });
            continue;
        };
        match items.first().and_then(Spanned::word) {
            Some("script") => match script(items, form.line, vocab) {
                Ok(d) => out.push(d),
                Err(e) => errors.push(e),
            },
            Some("global") => match global(items, form.line) {
                Ok(d) => out.push(d),
                Err(e) => errors.push(e),
            },
            other => errors.push(ParseError {
                line: form.line,
                message: match other {
                    Some(w) => format!("`{w}` is not a top-level declaration"),
                    None => "expected `script` or `global`".into(),
                },
            }),
        }
    }
    (out, errors)
}

fn describe(form: &Spanned) -> String {
    match &form.form {
        Form::List(_) => "a list".into(),
        Form::Atom(t) => t.describe(),
    }
}

fn script(items: &[Spanned], line: u32, vocab: &Vocabulary) -> Result<Declaration, ParseError> {
    let err = |message: String| ParseError { line, message };

    let kind = items
        .get(1)
        .and_then(Spanned::word)
        .ok_or_else(|| err("a script needs a kind, such as `dormant`".into()))?
        .to_string();
    if !vocab.script_types.is_empty() && !vocab.script_types.contains(&kind) {
        return Err(err(format!("`{kind}` is not a script kind")));
    }

    // Only `static` and `stub` declare a return type; for the rest the source
    // omits it and the type is void.
    let mut at = 2usize;
    let mut return_type = "void".to_string();
    if matches!(kind.as_str(), "static" | "stub") {
        if let Some(w) = items.get(at).and_then(Spanned::word) {
            if vocab.value_types.contains(w) {
                return_type = w.to_string();
                at += 1;
            }
        }
    }

    let header = items
        .get(at)
        .ok_or_else(|| err("a script needs a name".into()))?;
    at += 1;

    let (name, parameters) = match &header.form {
        Form::Atom(Token::Word(w)) => (w.clone(), Vec::new()),
        // `(f_a (short delay) (ai who))`, and also the bare `(f_a)` some
        // parameterless scripts are written with.
        Form::List(parts) => {
            let name = parts
                .first()
                .and_then(Spanned::word)
                .ok_or_else(|| err("a script's name list must start with its name".into()))?
                .to_string();
            let mut parameters = Vec::new();
            for p in &parts[1..] {
                let fields = p.items().ok_or_else(|| ParseError {
                    line: p.line,
                    message: "a parameter is written `(type name)`".into(),
                })?;
                let (Some(ty), Some(pname)) = (
                    fields.first().and_then(Spanned::word),
                    fields.get(1).and_then(Spanned::word),
                ) else {
                    return Err(ParseError {
                        line: p.line,
                        message: "a parameter is written `(type name)`".into(),
                    });
                };
                if !vocab.value_types.is_empty() && !vocab.value_types.contains(ty) {
                    return Err(ParseError {
                        line: p.line,
                        message: format!("`{ty}` is not a value type"),
                    });
                }
                parameters.push(Parameter {
                    value_type: ty.to_string(),
                    name: pname.to_string(),
                });
            }
            (name, parameters)
        }
        _ => return Err(err("a script needs a name".into())),
    };

    Ok(Declaration::Script {
        name,
        kind,
        return_type,
        parameters,
        body: items[at..].to_vec(),
        line,
    })
}

fn global(items: &[Spanned], line: u32) -> Result<Declaration, ParseError> {
    let err = |message: String| ParseError { line, message };
    let value_type = items
        .get(1)
        .and_then(Spanned::word)
        .ok_or_else(|| err("a global is written `(global type name value)`".into()))?
        .to_string();
    let name = items
        .get(2)
        .and_then(Spanned::word)
        .ok_or_else(|| err("a global needs a name".into()))?
        .to_string();
    Ok(Declaration::Global {
        name,
        value_type,
        initializer: items.get(3).cloned(),
        line,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vocab() -> Vocabulary {
        Vocabulary::new(
            &["void", "boolean", "short", "real", "ai", "string", "player"].map(String::from),
            &["startup", "dormant", "static", "command_script", "stub"].map(String::from),
        )
    }

    fn decls(src: &str) -> (Vec<Declaration>, Vec<ParseError>) {
        let forms = parse(src).expect("should parse");
        declarations(&forms, &vocab())
    }

    #[test]
    fn nested_lists_carry_the_line_they_started_on() {
        let forms = parse("(a\n  (b c)\n)").unwrap();
        assert_eq!(forms.len(), 1);
        let items = forms[0].items().unwrap();
        assert_eq!(forms[0].line, 1);
        assert_eq!(items[1].line, 2);
        assert_eq!(items[1].items().unwrap()[0].word(), Some("b"));
    }

    #[test]
    fn an_unclosed_paren_is_an_error_not_a_hang() {
        let e = parse("(a (b").unwrap_err();
        assert!(e.message.contains("never closed"), "{}", e.message);
    }

    #[test]
    fn a_stray_close_paren_is_reported_with_its_line() {
        let e = parse("(a)\n\n)").unwrap_err();
        assert_eq!(e.line, 3);
        assert!(e.message.contains("unmatched"));
    }

    #[test]
    fn a_static_script_return_type_is_read_and_a_dormant_one_defaults_to_void() {
        let (d, errs) =
            decls("(script static boolean f_a (wake x))\n(script dormant f_b (wake y))");
        assert!(errs.is_empty(), "{errs:?}");
        match &d[0] {
            Declaration::Script {
                name,
                kind,
                return_type,
                ..
            } => {
                assert_eq!(
                    (name.as_str(), kind.as_str(), return_type.as_str()),
                    ("f_a", "static", "boolean")
                );
            }
            other => panic!("{other:?}"),
        }
        match &d[1] {
            Declaration::Script {
                name, return_type, ..
            } => assert_eq!((name.as_str(), return_type.as_str()), ("f_b", "void")),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn a_script_named_like_a_type_is_not_read_as_a_return_type() {
        // `player` is a value type, but a dormant script never declares one.
        let (d, errs) = decls("(script dormant player (wake x))");
        assert!(errs.is_empty(), "{errs:?}");
        assert_eq!(d[0].name(), "player");
    }

    #[test]
    fn parameters_are_read_with_their_types() {
        let (d, errs) = decls("(script static void (f_a (short delay) (ai who)) (wake x))");
        assert!(errs.is_empty(), "{errs:?}");
        match &d[0] {
            Declaration::Script {
                name, parameters, ..
            } => {
                assert_eq!(name, "f_a");
                assert_eq!(
                    parameters,
                    &[
                        Parameter {
                            value_type: "short".into(),
                            name: "delay".into()
                        },
                        Parameter {
                            value_type: "ai".into(),
                            name: "who".into()
                        },
                    ]
                );
            }
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn a_parameterless_name_may_still_be_wrapped_in_parens() {
        let (d, errs) = decls("(script static void (f_a) (wake x))");
        assert!(errs.is_empty(), "{errs:?}");
        assert_eq!(d[0].name(), "f_a");
    }

    #[test]
    fn a_global_is_read_with_its_type_and_initializer() {
        let (d, errs) = decls("(global boolean b_awake false)");
        assert!(errs.is_empty(), "{errs:?}");
        match &d[0] {
            Declaration::Global {
                name,
                value_type,
                initializer,
                ..
            } => {
                assert_eq!((name.as_str(), value_type.as_str()), ("b_awake", "boolean"));
                assert_eq!(
                    initializer.as_ref().unwrap().form,
                    Form::Atom(Token::Word("false".into()))
                );
            }
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn an_unknown_script_kind_is_reported_against_its_line() {
        let (_, errs) = decls("\n\n(script sideways f_a (wake x))");
        assert_eq!(errs.len(), 1);
        assert_eq!(errs[0].line, 3);
        assert!(errs[0].message.contains("not a script kind"));
    }

    #[test]
    fn a_stray_top_level_form_is_reported_rather_than_ignored() {
        let (d, errs) = decls("(wake x)");
        assert!(d.is_empty());
        assert_eq!(errs.len(), 1);
        assert!(errs[0].message.contains("not a top-level declaration"));
    }

    #[test]
    fn comments_do_not_become_forms() {
        let (d, errs) = decls("; (script dormant ghost)\n(script dormant real_one (wake x))");
        assert!(errs.is_empty(), "{errs:?}");
        assert_eq!(d.len(), 1);
        assert_eq!(d[0].name(), "real_one");
    }
}
