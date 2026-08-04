//! Tokenise HSC source.
//!
//! Shared by everything that reads script text: the compiler, and the check
//! that grades the decompiler against the source a scenario shipped with.
//!
//! HSC is S-expression syntax with two traps worth naming. A `;` starts a
//! comment, but only outside a string — and the shipped dialogue lines are full
//! of semicolons, so treating one as a comment silently swallows the rest of
//! the line. Tag paths use backslashes and are *not* escape sequences:
//! `"objects\characters\marine"` is four literal backslashes' worth of path,
//! not an escape for `\c`.

/// One token of HSC.
#[derive(Debug, Clone, PartialEq)]
pub enum Token {
    Open,
    Close,
    /// A quoted string, with the quotes removed and no escape processing.
    Str(String),
    /// A numeric literal. Kept as `f64` so `-1` and `-1.0` compare equal, which
    /// matters because the compiler coerces between them freely.
    Num(f64),
    /// Anything else: a function name, a script name, an enum case, `true`.
    Word(String),
}

impl Token {
    /// A short rendering for diagnostics.
    pub fn describe(&self) -> String {
        match self {
            Token::Open => "(".into(),
            Token::Close => ")".into(),
            Token::Str(s) => format!("{s:?}"),
            Token::Num(n) => n.to_string(),
            Token::Word(w) => w.clone(),
        }
    }

    /// Whether two tokens mean the same thing to the compiler.
    ///
    /// The shipped source writes `0` for `false` and `1` for `true` in boolean
    /// positions, and the compiler accepts both, so they are the same token as
    /// far as meaning goes.
    pub fn means_same(&self, other: &Token) -> bool {
        if self == other {
            return true;
        }
        match (self.as_bool(), other.as_bool()) {
            (Some(a), Some(b)) => a == b,
            _ => false,
        }
    }

    /// This token read as a boolean, if it can be.
    fn as_bool(&self) -> Option<bool> {
        match self {
            Token::Word(w) if w == "true" => Some(true),
            Token::Word(w) if w == "false" => Some(false),
            Token::Num(n) if *n == 1.0 => Some(true),
            Token::Num(n) if *n == 0.0 => Some(false),
            _ => None,
        }
    }
}

/// A token and the source line it appeared on, 1-based.
#[derive(Debug, Clone, PartialEq)]
pub struct Lexeme {
    pub token: Token,
    pub line: u32,
}

/// Split HSC source into tokens, dropping comments.
pub fn tokenize(src: &str) -> Vec<Lexeme> {
    let mut out = Vec::new();
    let mut chars = src.chars().peekable();
    let mut word = String::new();
    let mut word_line = 1u32;
    let mut line = 1u32;

    while let Some(c) = chars.next() {
        match c {
            ';' => {
                flush(&mut word, word_line, &mut out);
                for c in chars.by_ref() {
                    if c == '\n' {
                        line += 1;
                        break;
                    }
                }
            }
            '"' => {
                flush(&mut word, word_line, &mut out);
                let start = line;
                let mut s = String::new();
                for c in chars.by_ref() {
                    if c == '"' {
                        break;
                    }
                    if c == '\n' {
                        line += 1;
                    }
                    s.push(c);
                }
                out.push(Lexeme {
                    token: Token::Str(s),
                    line: start,
                });
            }
            '(' | ')' => {
                flush(&mut word, word_line, &mut out);
                out.push(Lexeme {
                    token: if c == '(' { Token::Open } else { Token::Close },
                    line,
                });
            }
            c if c.is_whitespace() => {
                flush(&mut word, word_line, &mut out);
                if c == '\n' {
                    line += 1;
                }
            }
            c => {
                if word.is_empty() {
                    word_line = line;
                }
                word.push(c);
            }
        }
    }
    flush(&mut word, word_line, &mut out);
    out
}

fn flush(word: &mut String, line: u32, out: &mut Vec<Lexeme>) {
    if word.is_empty() {
        return;
    }
    // A bare word that parses as a number is a numeric literal. Tag paths and
    // names never do, so this cannot misread one.
    let token = match word.parse::<f64>() {
        Ok(n) => Token::Num(n),
        Err(_) => Token::Word(word.clone()),
    };
    word.clear();
    out.push(Lexeme { token, line });
}

/// Just the tokens, for callers that do not care where they came from.
pub fn tokens(src: &str) -> Vec<Token> {
    tokenize(src).into_iter().map(|l| l.token).collect()
}

/// The strings a source file writes only in quotes, and the ones it writes only
/// bare.
///
/// Which value types are written quoted is not recorded anywhere in the tag, so
/// it is recovered by asking how the source that produced the tree wrote the
/// strings the tree references.
///
/// A string written **both** ways is deliberately in neither set. `easy` is the
/// case that forces this: it is a bare `game_difficulty` case in
/// `(= (game_difficulty_get_real) easy)` and a quoted `string` in
/// `(print "easy")`, a few tokens apart. Counting it for both types made each
/// look like the other, so ambiguous strings teach nothing and are dropped.
pub fn literal_forms(src: &str) -> LiteralForms {
    let mut quoted = std::collections::BTreeSet::new();
    let mut bare = std::collections::BTreeSet::new();
    for l in tokenize(src) {
        match l.token {
            Token::Str(s) => {
                quoted.insert(s);
            }
            Token::Word(w) => {
                bare.insert(w);
            }
            _ => {}
        }
    }
    let ambiguous: Vec<String> = quoted.intersection(&bare).cloned().collect();
    for a in ambiguous {
        quoted.remove(&a);
        bare.remove(&a);
    }
    LiteralForms { quoted, bare }
}

/// How a source file writes each string it mentions.
#[derive(Debug, Clone, Default)]
pub struct LiteralForms {
    /// Written only in quotes.
    pub quoted: std::collections::BTreeSet<String>,
    /// Written only bare.
    pub bare: std::collections::BTreeSet<String>,
}

impl LiteralForms {
    /// Fold another file's evidence in, dropping anything the two disagree on.
    pub fn merge(&mut self, other: LiteralForms) {
        self.quoted.extend(other.quoted);
        self.bare.extend(other.bare);
        let ambiguous: Vec<String> = self.quoted.intersection(&self.bare).cloned().collect();
        for a in ambiguous {
            self.quoted.remove(&a);
            self.bare.remove(&a);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(src: &str) -> Vec<Token> {
        tokens(src)
    }

    #[test]
    fn a_semicolon_inside_a_string_is_not_a_comment() {
        assert_eq!(
            words(r#"(print "chief; wake up") ; a real comment"#),
            vec![
                Token::Open,
                Token::Word("print".into()),
                Token::Str("chief; wake up".into()),
                Token::Close
            ]
        );
    }

    #[test]
    fn a_backslash_in_a_tag_path_is_not_an_escape() {
        assert_eq!(
            words(r#""objects\characters\marine""#),
            vec![Token::Str(r"objects\characters\marine".into())]
        );
    }

    #[test]
    fn numbers_are_parsed_and_names_are_not() {
        assert_eq!(words("-1"), vec![Token::Num(-1.0)]);
        assert_eq!(words("-1.0"), vec![Token::Num(-1.0)]);
        assert_eq!(words("1e3"), vec![Token::Num(1000.0)]);
        assert_eq!(words("sq_marines"), vec![Token::Word("sq_marines".into())]);
        // A name that starts with a digit is still a name.
        assert_eq!(words("13_script"), vec![Token::Word("13_script".into())]);
    }

    #[test]
    fn a_zero_means_the_same_as_false() {
        assert!(Token::Num(0.0).means_same(&Token::Word("false".into())));
        assert!(Token::Word("true".into()).means_same(&Token::Num(1.0)));
        assert!(!Token::Num(2.0).means_same(&Token::Word("true".into())));
        assert!(!Token::Word("a".into()).means_same(&Token::Word("b".into())));
    }

    #[test]
    fn lines_are_counted_through_comments_and_strings() {
        let src = "(a\n; comment\n(b)\n\"two\nlines\"\nc)";
        let lex = tokenize(src);
        let by_name = |n: &str| {
            lex.iter()
                .find(|l| l.token == Token::Word(n.into()))
                .map(|l| l.line)
        };
        assert_eq!(by_name("a"), Some(1));
        assert_eq!(by_name("b"), Some(3));
        assert_eq!(by_name("c"), Some(6));
    }

    #[test]
    fn literals_are_split_by_how_the_source_writes_them() {
        let f = literal_forms(r#"(damage_new "levels/a15/boom" fl_flag)"#);
        assert!(f.quoted.contains("levels/a15/boom"));
        assert!(f.bare.contains("fl_flag"));
        assert!(f.bare.contains("damage_new"));
    }

    #[test]
    fn a_string_written_both_ways_teaches_nothing() {
        // The real case: `easy` is a bare difficulty and a quoted string.
        let f = literal_forms(r#"(= (game_difficulty_get_real) easy) (print "easy")"#);
        assert!(!f.quoted.contains("easy"));
        assert!(!f.bare.contains("easy"));
        assert!(f.bare.contains("game_difficulty_get_real"));
    }

    #[test]
    fn merging_files_drops_what_they_disagree_on() {
        let mut a = literal_forms(r#"(print "easy") (wake only_quoted_elsewhere)"#);
        a.merge(literal_forms("(= d easy)"));
        assert!(!a.quoted.contains("easy"));
        assert!(!a.bare.contains("easy"));
        assert!(a.bare.contains("only_quoted_elsewhere"));
    }

    #[test]
    fn an_unterminated_string_does_not_hang() {
        assert_eq!(
            words(r#"(print "oops"#),
            vec![
                Token::Open,
                Token::Word("print".into()),
                Token::Str("oops".into())
            ]
        );
    }
}
