//! Check the decompiler against the source the scenario shipped with.
//!
//! A scenario carries both the original `.hsc` text and the tree the compiler
//! made of it, which is a rare thing: the decompiler can be graded against the
//! real answer rather than against itself.
//!
//! The two are compared as token sequences, not as text, because three
//! differences are expected and are not defects:
//!
//! - **Comments.** The tree does not store them.
//! - **`cond`.** It is desugared to nested `if` before any node is emitted, so
//!   a script that used it cannot come back as it went in.
//! - **Spelling of literals.** The compiler coerces `-1` to a real where the
//!   context wants one, and the source writes `0` where it means `false`.
//!   [`blam_hsc::lex::Token::means_same`] treats those as agreement.

use std::collections::{BTreeMap, BTreeSet};

use blam_hsc::lex::{self, Token};

/// Every top-level `(script ...)` block in a source file, by script name.
///
/// Blocks are found by balancing parentheses over the token stream rather than
/// by matching text, so a `)` inside a string or a comment cannot end a block
/// early.
///
/// `value_types` is needed to read the header: `(script static void f_a ...)`
/// and `(script dormant f_b ...)` are the same shape, and only knowing that
/// `void` names a type separates the return type from the script name.
///
/// A name maps to a *list* of blocks because HSC overloads on arity: `a30`
/// declares `f_play_cinematic` twice, once taking a cinematic and once taking a
/// cinematic and a point reference. Keying by name alone would silently discard
/// one and then report the other as a mismatch.
pub fn script_blocks(
    src: &str,
    value_types: &BTreeSet<String>,
) -> BTreeMap<String, Vec<Vec<Token>>> {
    let tokens = lex::tokens(src);
    let mut out = BTreeMap::new();
    let mut i = 0usize;

    while i < tokens.len() {
        if tokens[i] != Token::Open || tokens.get(i + 1) != Some(&Token::Word("script".into())) {
            i += 1;
            continue;
        }

        let mut depth = 0i32;
        let mut end = tokens.len() - 1;
        for (j, t) in tokens[i..].iter().enumerate() {
            match t {
                Token::Open => depth += 1,
                Token::Close => depth -= 1,
                _ => {}
            }
            if depth == 0 {
                end = i + j;
                break;
            }
        }
        let block = &tokens[i..=end];
        if let Some(name) = script_name(block, value_types) {
            out.entry(name)
                .or_insert_with(Vec::new)
                .push(block.to_vec());
        }
        i = end + 1;
    }
    out
}

/// The declared name of a `(script ...)` block.
///
/// The header is `(script <type> [<return type>] <name>`, where the name is
/// wrapped in its own list when the script takes parameters. A return type
/// appears only on `static` and `stub` scripts — the other kinds are void by
/// construction and the shipped source omits it. Requiring both that and a
/// known type name is what keeps a script legitimately called `player` from
/// being read as a return type.
fn script_name(block: &[Token], value_types: &BTreeSet<String>) -> Option<String> {
    let i = name_slot(block, value_types)?;
    match block.get(i)? {
        Token::Word(name) => Some(name.clone()),
        // `(script static void (f_a (short n)) ...)`
        Token::Open => match block.get(i + 1)? {
            Token::Word(name) => Some(name.clone()),
            _ => None,
        },
        _ => None,
    }
}

/// How one script's decompilation compared to its source.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Verdict {
    /// The token streams agree.
    Match,
    /// They differ, and the source used `cond`, which cannot survive
    /// compilation.
    DesugaredCond,
    /// They differ for some other reason.
    Differs {
        at: usize,
        kind: Difference,
        source: String,
        ours: String,
    },
    /// The scenario declares this script but no source file defines it.
    NoSource,
}

/// What kind of disagreement was found, so a run reports classes of defect
/// rather than a pile of individual diffs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Difference {
    /// Same text, but one side quoted it and the other did not. The quoted-type
    /// classification is wrong for this value.
    Quoting,
    /// One side wrote `none` where the other wrote an empty string.
    NoneVersusEmpty,
    /// The two sides name different things.
    Other,
}

impl Difference {
    fn classify(source: Option<&Token>, ours: Option<&Token>) -> Difference {
        match (source, ours) {
            (Some(Token::Str(a)), Some(Token::Word(b)))
            | (Some(Token::Word(a)), Some(Token::Str(b)))
                if a == b =>
            {
                Difference::Quoting
            }
            (Some(Token::Str(s)), Some(Token::Word(w)))
            | (Some(Token::Word(w)), Some(Token::Str(s)))
                if s.is_empty() && w == "none" =>
            {
                Difference::NoneVersusEmpty
            }
            _ => Difference::Other,
        }
    }
}

/// Grade one decompiled script against every source block declaring that name.
///
/// An overload set is a match if any of its members matches; otherwise the
/// closest one is reported, since that is the one most likely to be the
/// intended counterpart.
pub fn compare(
    candidates: Option<&Vec<Vec<Token>>>,
    decompiled: &str,
    value_types: &BTreeSet<String>,
) -> Verdict {
    let Some(candidates) = candidates else {
        return Verdict::NoSource;
    };
    let got = normalise_header(&lex::tokens(decompiled), value_types);

    let mut best: Option<Verdict> = None;
    for want in candidates {
        let verdict = compare_one(&normalise_header(want, value_types), &got);
        let better = match (&verdict, &best) {
            (Verdict::Match, _) => return Verdict::Match,
            (_, None) => true,
            (Verdict::Differs { at, .. }, Some(Verdict::Differs { at: best_at, .. })) => {
                at > best_at
            }
            (Verdict::DesugaredCond, Some(Verdict::Differs { .. })) => true,
            _ => false,
        };
        if better {
            best = Some(verdict);
        }
    }
    best.unwrap_or(Verdict::NoSource)
}

/// Drop a paren pair that wraps a script name and nothing else.
///
/// A script with no parameters is written both `(script static void f_a ...)`
/// and `(script static void (f_a) ...)`; the tag records no difference between
/// them, so neither should the comparison.
///
/// Only the name slot is touched. Scanning the first few tokens for any
/// `( word )` looks equivalent and is not: a parameterless script whose first
/// statement is a nullary call — `(script static void f_game_save
/// (game_save_no_timeout) …)` — has that shape at the same place, and stripping
/// it there rewrites the body.
fn normalise_header(tokens: &[Token], value_types: &BTreeSet<String>) -> Vec<Token> {
    let Some(i) = name_slot(tokens, value_types) else {
        return tokens.to_vec();
    };
    if tokens.get(i) != Some(&Token::Open)
        || !matches!(tokens.get(i + 1), Some(Token::Word(_)))
        || tokens.get(i + 2) != Some(&Token::Close)
    {
        return tokens.to_vec();
    }
    let mut out = tokens.to_vec();
    out.remove(i + 2);
    out.remove(i);
    out
}

/// The token index where a `(script ...)` block's name begins.
fn name_slot(block: &[Token], value_types: &BTreeSet<String>) -> Option<usize> {
    if block.first() != Some(&Token::Open) || block.get(1) != Some(&Token::Word("script".into())) {
        return None;
    }
    let Token::Word(kind) = block.get(2)? else {
        return None;
    };
    let mut i = 3;
    if matches!(kind.as_str(), "static" | "stub") {
        if let Some(Token::Word(w)) = block.get(i) {
            if value_types.contains(w) {
                i += 1;
            }
        }
    }
    Some(i)
}

fn compare_one(want: &[Token], got: &[Token]) -> Verdict {
    let mismatch = want
        .iter()
        .zip(got)
        .position(|(a, b)| !a.means_same(b))
        .or_else(|| (want.len() != got.len()).then_some(want.len().min(got.len())));

    let Some(at) = mismatch else {
        return Verdict::Match;
    };
    if want.iter().any(|t| *t == Token::Word("cond".into())) {
        return Verdict::DesugaredCond;
    }
    Verdict::Differs {
        at,
        kind: Difference::classify(want.get(at), got.get(at)),
        source: window(want, at),
        ours: window(got, at),
    }
}

/// A few tokens either side of a mismatch, so the report shows context rather
/// than a bare index.
fn window(tokens: &[Token], at: usize) -> String {
    let start = at.saturating_sub(4);
    let end = (at + 5).min(tokens.len());
    tokens[start..end]
        .iter()
        .map(Token::describe)
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn types() -> BTreeSet<String> {
        ["void", "boolean", "short", "ai", "player"]
            .iter()
            .map(|s| s.to_string())
            .collect()
    }

    #[test]
    fn a_script_block_is_found_by_balancing_parens() {
        let src = r#"
; leading comment
(script static void (f_a (short n))
	(print ")not the end")
)
(script dormant f_b
	(wake f_a)
)
"#;
        let blocks = script_blocks(src, &types());
        assert_eq!(blocks.keys().collect::<Vec<_>>(), vec!["f_a", "f_b"]);
        // The `)` inside the string did not end the first block early.
        assert!(blocks["f_a"][0].contains(&Token::Str(")not the end".into())));
    }

    #[test]
    fn an_overload_set_keeps_every_block_and_matches_any_of_them() {
        let blocks = script_blocks(
            "(script static void (f_c (short n)) (wake x))\
             (script static void (f_c (short n) (ai who)) (wake y))",
            &types(),
        );
        assert_eq!(blocks["f_c"].len(), 2);
        assert_eq!(
            compare(
                blocks.get("f_c"),
                "(script static void (f_c (short n) (ai who))\n\t(wake y)\n)",
                &types(),
            ),
            Verdict::Match
        );
    }

    #[test]
    fn a_name_wrapped_in_its_own_parens_is_the_same_script() {
        let blocks = script_blocks("(script static void (f_d) (wake x))", &types());
        assert_eq!(
            compare(
                blocks.get("f_d"),
                "(script static void f_d\n\t(wake x)\n)",
                &types()
            ),
            Verdict::Match
        );
    }

    #[test]
    fn a_matching_decompilation_is_a_match() {
        let blocks = script_blocks("(script dormant f_b (wake f_a))", &types());
        assert_eq!(
            compare(
                blocks.get("f_b"),
                "(script dormant f_b\n\t(wake f_a)\n)",
                &types()
            ),
            Verdict::Match
        );
    }

    #[test]
    fn a_coerced_literal_still_matches() {
        let blocks = script_blocks("(script dormant f_b (sleep -1) (ai_berserk x 0))", &types());
        assert_eq!(
            compare(
                blocks.get("f_b"),
                "(script dormant f_b (sleep -1.0) (ai_berserk x false))",
                &types(),
            ),
            Verdict::Match
        );
    }

    #[test]
    fn a_source_using_cond_is_reported_as_desugared_rather_than_wrong() {
        let blocks = script_blocks("(script dormant f_b (cond ((= a b) (wake x))))", &types());
        assert_eq!(
            compare(
                blocks.get("f_b"),
                "(script dormant f_b (if (= a b) (wake x)))",
                &types(),
            ),
            Verdict::DesugaredCond
        );
    }

    #[test]
    fn a_real_difference_reports_where() {
        let blocks = script_blocks("(script dormant f_b (wake f_a))", &types());
        match compare(
            blocks.get("f_b"),
            "(script dormant f_b (wake f_c))",
            &types(),
        ) {
            Verdict::Differs { source, ours, .. } => {
                assert!(source.contains("f_a"));
                assert!(ours.contains("f_c"));
            }
            other => panic!("expected a difference, got {other:?}"),
        }
    }

    #[test]
    fn a_truncated_decompilation_is_not_a_match() {
        let blocks = script_blocks("(script dormant f_b (wake f_a) (wake f_c))", &types());
        assert!(matches!(
            compare(
                blocks.get("f_b"),
                "(script dormant f_b (wake f_a))",
                &types()
            ),
            Verdict::Differs { .. }
        ));
    }

    #[test]
    fn a_script_declared_with_no_source_is_reported_as_such() {
        assert_eq!(
            compare(None, "(script dormant f_b)", &types()),
            Verdict::NoSource
        );
    }

    #[test]
    fn a_parameterised_header_yields_the_script_name_not_the_type() {
        let blocks = script_blocks(
            "(script static void (f_a (short n) (ai who)) (wake x))",
            &types(),
        );
        assert_eq!(blocks.keys().collect::<Vec<_>>(), vec!["f_a"]);
    }
}
