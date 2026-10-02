//! Blueprint (Kismet) bytecode in a cooked function export: finding the
//! script, walking it statement by statement, and printing it.
//!
//! A `UFunction` export is its property block, `UStruct` data (super, children,
//! child properties), the two script sizes, the script, and a 12-byte tail
//! (function flags, event graph function, event graph call offset). The script
//! is serialized smaller than it lives in memory: an object reference is 4
//! bytes on disk and 8 in memory, a name 8 and 12, a property path
//! (`count, names, owner`) 4+8n+4 and 8. Jump targets and ubergraph entry points
//! are *in-memory* offsets, so the walker tracks both.
//!
//! Opcodes follow UE 5.5's `EExprToken`. Only what cooked Blueprints use is
//! decoded; anything else stops the walk with an error rather than guessing.

use std::ops::Range;

/// The bytes after a function's script: `FunctionFlags`, `EventGraphFunction`,
/// `EventGraphCallOffset` (functions without `FUNC_Net`, which is every
/// Blueprint function seen so far).
pub const FUNCTION_TAIL: usize = 12;

pub const EX_LOCAL_FINAL_FUNCTION: u8 = 0x46;
pub const EX_INT_CONST: u8 = 0x1d;
pub const EX_POP_EXECUTION_FLOW: u8 = 0x4d;
pub const EX_END_OF_SCRIPT: u8 = 0x53;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("script ends early at {0:#x}")]
    Eof(usize),
    #[error("unknown opcode {op:#04x} at {at:#x}")]
    Opcode { op: u8, at: usize },
    #[error("no script found in this export")]
    NoScript,
}

/// One top-level statement.
#[derive(Debug, Clone)]
pub struct Stmt {
    /// In-memory offset: what jumps and entry points refer to.
    pub offset: u32,
    /// Bytes within the script.
    pub range: Range<usize>,
    pub text: String,
}

/// A function export's script.
#[derive(Debug, Clone)]
pub struct Script {
    /// Where the script starts within the export; the two size words sit in
    /// the 8 bytes before it.
    pub start: usize,
    /// One past its last byte (the export's length minus [`FUNCTION_TAIL`]).
    pub end: usize,
    /// In-memory size: the last statement (`EX_EndOfScript`)'s offset plus 1.
    pub memory_size: u32,
    pub stmts: Vec<Stmt>,
}

/// How object references and names print.
pub trait Names {
    fn name(&self, index: u32, number: u32) -> String;
    fn object(&self, index: i32) -> String;
}

/// Plain numbers, when nothing better is at hand.
pub struct Raw;

impl Names for Raw {
    fn name(&self, index: u32, number: u32) -> String {
        format!("n{index}_{number}")
    }
    fn object(&self, index: i32) -> String {
        format!("o{index}")
    }
}

/// Find and walk the script of a function export. The script is where the
/// on-disk size word before it matches the distance to the tail, the walk
/// ends exactly there on `EX_EndOfScript`, and the in-memory size word
/// matches the walk.
pub fn script(export: &[u8], names: &dyn Names) -> Result<Script, Error> {
    if export.len() < FUNCTION_TAIL + 9 {
        return Err(Error::NoScript);
    }
    let end = export.len() - FUNCTION_TAIL;
    for start in 8..end {
        let disk = u32::from_le_bytes(export[start - 4..start].try_into().unwrap()) as usize;
        if disk != end - start {
            continue;
        }
        let memory = u32::from_le_bytes(export[start - 8..start - 4].try_into().unwrap());
        let Ok(stmts) = walk(&export[start..end], names) else {
            continue;
        };
        let Some(last) = stmts.last() else { continue };
        if last.range.end == end - start
            && export[start + last.range.start] == EX_END_OF_SCRIPT
            && last.offset + 1 == memory
        {
            return Ok(Script {
                start,
                end,
                memory_size: memory,
                stmts,
            });
        }
    }
    Err(Error::NoScript)
}

/// Walk a script to its `EX_EndOfScript`.
pub fn walk(script: &[u8], names: &dyn Names) -> Result<Vec<Stmt>, Error> {
    let mut r = Walker {
        b: script,
        at: 0,
        mem: 0,
        names,
    };
    let mut out = Vec::new();
    loop {
        let (at, mem) = (r.at, r.mem);
        let text = r.expr()?;
        let done = script[at] == EX_END_OF_SCRIPT;
        out.push(Stmt {
            offset: mem,
            range: at..r.at,
            text,
        });
        if done {
            return Ok(out);
        }
    }
}

/// The in-memory size of a run of whole statements (for code moved or
/// appended): walks it the same way.
pub fn memory_len(code: &[u8]) -> Result<u32, Error> {
    let mut r = Walker {
        b: code,
        at: 0,
        mem: 0,
        names: &Raw,
    };
    while r.at < code.len() {
        r.expr()?;
    }
    Ok(r.mem)
}

struct Walker<'a> {
    b: &'a [u8],
    at: usize,
    mem: u32,
    names: &'a dyn Names,
}

impl Walker<'_> {
    fn take(&mut self, n: usize, mem: u32) -> Result<&[u8], Error> {
        let s = self
            .b
            .get(self.at..self.at + n)
            .ok_or(Error::Eof(self.at))?;
        self.at += n;
        self.mem += mem;
        Ok(s)
    }
    fn u8(&mut self) -> Result<u8, Error> {
        Ok(self.take(1, 1)?[0])
    }
    fn u16(&mut self) -> Result<u16, Error> {
        Ok(u16::from_le_bytes(self.take(2, 2)?.try_into().unwrap()))
    }
    fn u32(&mut self) -> Result<u32, Error> {
        Ok(u32::from_le_bytes(self.take(4, 4)?.try_into().unwrap()))
    }
    fn i32(&mut self) -> Result<i32, Error> {
        Ok(self.u32()? as i32)
    }
    fn f32(&mut self) -> Result<f32, Error> {
        Ok(f32::from_bits(self.u32()?))
    }
    fn f64(&mut self) -> Result<f64, Error> {
        Ok(f64::from_le_bytes(self.take(8, 8)?.try_into().unwrap()))
    }
    fn i64(&mut self) -> Result<i64, Error> {
        Ok(i64::from_le_bytes(self.take(8, 8)?.try_into().unwrap()))
    }
    /// An `FScriptName`: 8 bytes on disk, 12 in memory.
    fn name(&mut self) -> Result<String, Error> {
        let b = self.take(8, 12)?;
        let index = u32::from_le_bytes(b[..4].try_into().unwrap());
        let number = u32::from_le_bytes(b[4..].try_into().unwrap());
        Ok(self.names.name(index, number))
    }
    /// An object pointer: 4 bytes on disk, 8 in memory.
    fn obj(&mut self) -> Result<String, Error> {
        let v = i32::from_le_bytes(self.take(4, 8)?.try_into().unwrap());
        Ok(self.names.object(v))
    }
    /// A property path (`TFieldPath`): count, names, owner on disk; one
    /// pointer in memory.
    fn prop(&mut self) -> Result<String, Error> {
        let n = i32::from_le_bytes(self.take(4, 0)?.try_into().unwrap());
        if !(0..=16).contains(&n) {
            return Err(Error::Opcode { op: 0, at: self.at });
        }
        let mut parts = Vec::new();
        for _ in 0..n {
            let b = self.take(8, 0)?;
            let index = u32::from_le_bytes(b[..4].try_into().unwrap());
            let number = u32::from_le_bytes(b[4..].try_into().unwrap());
            parts.push(self.names.name(index, number));
        }
        self.take(4, 8)?;
        Ok(if parts.is_empty() {
            "null".into()
        } else {
            parts.join(".")
        })
    }
    fn cstr(&mut self, wide: bool) -> Result<String, Error> {
        let unit = if wide { 2 } else { 1 };
        let mut end = self.at;
        loop {
            let c = self.b.get(end..end + unit).ok_or(Error::Eof(end))?;
            if c.iter().all(|&x| x == 0) {
                break;
            }
            end += unit;
        }
        let n = end + unit - self.at;
        let s = self.take(n, n as u32)?;
        let body = &s[..s.len() - unit];
        Ok(if wide {
            let units: Vec<u16> = body
                .chunks(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            String::from_utf16_lossy(&units)
        } else {
            body.iter().map(|&c| c as char).collect()
        })
    }
    /// Expressions up to (and consuming) the terminator opcode.
    fn until(&mut self, end: u8) -> Result<Vec<String>, Error> {
        let mut out = Vec::new();
        loop {
            if *self.b.get(self.at).ok_or(Error::Eof(self.at))? == end {
                self.u8()?;
                return Ok(out);
            }
            out.push(self.expr()?);
        }
    }

    fn expr(&mut self) -> Result<String, Error> {
        let at = self.at;
        let op = self.u8()?;
        Ok(match op {
            0x00 => format!("local:{}", self.prop()?),
            0x01 => format!("inst:{}", self.prop()?),
            0x02 => format!("default:{}", self.prop()?),
            0x04 => format!("return {}", self.expr()?),
            0x06 => format!("jump {}", self.u32()?),
            0x07 => {
                let t = self.u32()?;
                format!("jumpifnot {t} ({})", self.expr()?)
            }
            0x09 => {
                self.u16()?;
                self.u8()?;
                format!("assert {}", self.expr()?)
            }
            0x0b => "nothing".into(),
            0x0c => format!("nothing_i32 {}", self.i32()?),
            0x0f => {
                self.prop()?;
                let a = self.expr()?;
                format!("let {a} = {}", self.expr()?)
            }
            0x11 => {
                let p = self.prop()?;
                format!("bitfield {p} = {}", self.u8()?)
            }
            0x12 | 0x19 | 0x1a => {
                let o = self.expr()?;
                self.u32()?;
                self.prop()?;
                format!("{o}->{}", self.expr()?)
            }
            0x13 => {
                let c = self.obj()?;
                format!("metacast<{c}>({})", self.expr()?)
            }
            0x14 | 0x43 | 0x44 | 0x5c | 0x5f | 0x60 | 0x62 | 0x6b => {
                let a = self.expr()?;
                let b = self.expr()?;
                let what = match op {
                    0x14 => "letbool",
                    0x43 => "letmcd",
                    0x44 => "letdelegate",
                    0x5c => "addmcd",
                    0x5f => "letobj",
                    0x60 => "letweak",
                    0x62 => "removemcd",
                    _ => "arrayget",
                };
                format!("{what} {a} = {b}")
            }
            0x15 => "endparm".into(),
            0x17 => "self".into(),
            0x18 => {
                self.u32()?;
                format!("skip {}", self.expr()?)
            }
            0x1b | 0x45 => {
                let n = self.name()?;
                format!("{n}({})", self.until(0x16)?.join(", "))
            }
            0x1c | 0x46 | 0x63 | 0x68 => {
                let f = self.obj()?;
                format!("{f}({})", self.until(0x16)?.join(", "))
            }
            0x1d => self.i32()?.to_string(),
            0x1e => self.f32()?.to_string(),
            0x1f => format!("{:?}", self.cstr(false)?),
            0x34 => format!("u{:?}", self.cstr(true)?),
            0x20 => format!("obj {}", self.obj()?),
            0x21 => format!("name {}", self.name()?),
            0x22 | 0x23 => format!("vec({}, {}, {})", self.f64()?, self.f64()?, self.f64()?),
            0x41 => format!("vec3f({}, {}, {})", self.f32()?, self.f32()?, self.f32()?),
            0x2b => {
                for _ in 0..10 {
                    self.f64()?;
                }
                "transform".into()
            }
            0x24 => format!("byte {}", self.u8()?),
            0x25 => "0".into(),
            0x26 => "1".into(),
            0x27 => "true".into(),
            0x28 => "false".into(),
            0x29 => match self.u8()? {
                0 => "text\"\"".into(),
                1 => {
                    let a = self.expr()?;
                    let b = self.expr()?;
                    format!("loctext({a}, {b}, {})", self.expr()?)
                }
                2 | 3 => format!("text {}", self.expr()?),
                4 => {
                    let o = self.obj()?;
                    let a = self.expr()?;
                    format!("stringtable({o}, {a}, {})", self.expr()?)
                }
                _ => "text none".into(),
            },
            0x2a => "noobject".into(),
            0x2c => self.u8()?.to_string(),
            0x2d => "nointerface".into(),
            0x2e | 0x52 | 0x54 | 0x55 => {
                let c = self.obj()?;
                format!("cast<{c}>({})", self.expr()?)
            }
            0x2f => {
                let s = self.obj()?;
                self.i32()?;
                format!("struct<{s}>({})", self.until(0x30)?.join(", "))
            }
            0x31 => {
                let a = self.expr()?;
                format!("setarray {a} = [{}]", self.until(0x32)?.join(", "))
            }
            0x39 => {
                let a = self.expr()?;
                self.i32()?;
                format!("setset {a} = [{}]", self.until(0x3a)?.join(", "))
            }
            0x3b => {
                let a = self.expr()?;
                self.i32()?;
                format!("setmap {a} = [{}]", self.until(0x3c)?.join(", "))
            }
            0x3d => {
                self.prop()?;
                self.i32()?;
                format!("setconst[{}]", self.until(0x3e)?.join(", "))
            }
            0x3f => {
                self.prop()?;
                self.prop()?;
                self.i32()?;
                format!("mapconst[{}]", self.until(0x40)?.join(", "))
            }
            0x65 => {
                self.prop()?;
                self.i32()?;
                format!("arrayconst[{}]", self.until(0x66)?.join(", "))
            }
            0x35 | 0x36 => self.i64()?.to_string(),
            0x37 => self.f64()?.to_string(),
            0x38 => {
                let k = self.u8()?;
                format!("cast{k}({})", self.expr()?)
            }
            0x42 => {
                let p = self.prop()?;
                format!("{}.{p}", self.expr()?)
            }
            0x48 => format!("out:{}", self.prop()?),
            0x4b => format!("delegate {}", self.name()?),
            0x4c => format!("push {}", self.u32()?),
            0x4d => "pop".into(),
            0x4e => format!("computedjump {}", self.expr()?),
            0x4f => format!("popifnot {}", self.expr()?),
            0x50 | 0x5a | 0x5e => "trace".into(),
            0x51 => format!("interface {}", self.expr()?),
            0x53 => "end".into(),
            0x5b => format!("skipoffset {}", self.u32()?),
            0x5d => format!("clearmcd {}", self.expr()?),
            0x61 => {
                let n = self.name()?;
                let a = self.expr()?;
                format!("bind {n} {a} {}", self.expr()?)
            }
            0x64 => {
                let p = self.prop()?;
                format!("letpersistent {p} = {}", self.expr()?)
            }
            0x67 => format!("softobject {}", self.expr()?),
            0x69 => {
                let n = self.u16()?;
                self.u32()?;
                let index = self.expr()?;
                let mut cases = Vec::new();
                for _ in 0..n {
                    let k = self.expr()?;
                    self.u32()?;
                    cases.push(format!("{k}: {}", self.expr()?));
                }
                format!(
                    "switch {index} {{{}; default: {}}}",
                    cases.join("; "),
                    self.expr()?
                )
            }
            0x6c => format!("sparse:{}", self.prop()?),
            0x6d => format!("fieldpath {}", self.expr()?),
            0x33 => format!("propconst:{}", self.prop()?),
            _ => return Err(Error::Opcode { op, at }),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The Remix button's click stub from CU4's WBP_MainMenu: store the
    /// button on the ubergraph frame, then enter the ubergraph at 5439.
    const CLICK_STUB: &str = "000100000000000000000000000001000000cc00000000000000390000000000000001000000010000000800000094000800000000000000c90000000000000000e9ffffff24000000300000006401000000a60000001600000026000000000100000039000000000000001200000046260000001d3f15000016040b53000000080000000000000000";

    fn bytes(hex: &str) -> Vec<u8> {
        (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect()
    }

    #[test]
    fn finds_and_walks_a_click_stub() {
        let b = bytes(CLICK_STUB);
        let s = script(&b, &Raw).expect("script");
        assert_eq!(s.memory_size, 36);
        assert_eq!(s.end, b.len() - FUNCTION_TAIL);
        let texts: Vec<&str> = s.stmts.iter().map(|x| x.text.as_str()).collect();
        assert_eq!(
            texts,
            [
                "letpersistent n166_22 = local:n57_0",
                "o38(5439)",
                "return nothing",
                "end"
            ]
        );
        assert_eq!(
            s.stmts.iter().map(|x| x.offset).collect::<Vec<_>>(),
            [0, 18, 33, 35]
        );
    }

    #[test]
    fn memory_len_counts_pointers_wide() {
        // EX_LocalFinalFunction(obj, int 7) EX_EndFunctionParms: 1+8+5+1.
        let code = [0x46, 1, 0, 0, 0, 0x1d, 7, 0, 0, 0, 0x16];
        assert_eq!(memory_len(&code).unwrap(), 15);
    }
}
