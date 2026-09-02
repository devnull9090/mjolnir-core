//! Lift the Blam console vocabulary out of the simulation DLL.
//!
//! The scripting corpus (`mjolnir scripting`) only knows the opcodes the
//! campaign calls: 483 of them. The engine's own table is bigger, because the
//! console vocabulary — `cheat_*`, `debug_*`, `player_teleport`, `help`,
//! `script_doc` — is the same table, and nothing in a shipped scenario ever
//! calls a cheat. `HaloSimulation_tag_release.dll` carries that table verbatim:
//! an array of pointers to definitions, one per opcode, each naming the
//! function and listing its parameter types. The globals (`game_speed`,
//! `cheat_deathless_player`) sit in a second array of the same shape.
//!
//! No disassembly is involved. The table is found by name: the string
//! `sleep_until` is referenced by exactly one definition, and that definition
//! by exactly one table slot. Walking outward from the slot while the
//! neighbours still look like definitions gives the whole table, and its
//! extent is checked against the corpus, whose opcodes must land on the same
//! names.

use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use clap::Args;

#[derive(Args)]
pub struct ConsoleArgs {
    /// The simulation DLL, `HaloSimulation_tag_release.dll` under
    /// `Meteorite\Binaries\Win64` of the install.
    #[arg(long)]
    dll: PathBuf,
    /// Recovered scripting corpus. Supplies the value-type names, and the
    /// opcodes it knows are checked against the table read here.
    #[arg(long, default_value = "defs/hce/scripting.json")]
    corpus: PathBuf,
    /// Build string to record, e.g. the one `mjolnir scripting --build` took.
    #[arg(long, default_value = "")]
    build: String,
    /// Where to write the JSON.
    #[arg(long, default_value = "defs/hce/console.json")]
    out: PathBuf,
    /// Also write the same vocabulary as a Lua module, for the console mod.
    #[arg(long)]
    lua: Option<PathBuf>,
    /// Report what would be written, without writing.
    #[arg(long)]
    dry_run: bool,
}

/// One entry of the engine's function table.
///
/// The definition the slot points at, in this build, is:
///
/// | offset | field | notes |
/// |---:|---|---|
/// | `0x00` | `u16` return type | indexes the value-type enum |
/// | `0x08` | `char*` name | |
/// | `0x10` | `u32` flags | 2 for special forms (`begin`, `if`, `sleep_until`) |
/// | `0x18` | parse fn | shared by everything that is not a special form |
/// | `0x20` | evaluate fn | |
/// | `0x28` | `char*` help | null in the release build |
/// | `0x30` | `char*` parameters text | only special forms carry one |
/// | `0x38` | `u16` parameter count | |
/// | `0x3a` | `u16[]` parameter types | value-type enum |
#[derive(Debug, Clone)]
pub struct FunctionEntry {
    pub index: u16,
    pub name: String,
    pub returns: u16,
    pub flags: u32,
    pub parse_rva: u64,
    pub evaluate_rva: u64,
    pub help: Option<String>,
    pub parameters_text: Option<String>,
    pub parameters: Vec<u16>,
}

/// One entry of the globals array: `{ char* name; u16 type; ...; void* storage }`,
/// 24 bytes, stored inline rather than through a pointer.
#[derive(Debug, Clone)]
pub struct GlobalEntry {
    pub index: u16,
    pub name: String,
    pub value_type: u16,
    pub storage_rva: u64,
}

/// The parts of a PE image this needs: section mapping and the image base.
struct Image<'a> {
    bytes: &'a [u8],
    image_base: u64,
    sections: Vec<Section>,
}

#[derive(Debug, Clone)]
struct Section {
    name: String,
    va: u64,
    vsize: u64,
    raw: u64,
    rsize: u64,
}

fn u16_at(b: &[u8], o: usize) -> Option<u16> {
    b.get(o..o + 2).map(|s| u16::from_le_bytes([s[0], s[1]]))
}
fn u32_at(b: &[u8], o: usize) -> Option<u32> {
    b.get(o..o + 4)
        .map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
}
fn u64_at(b: &[u8], o: usize) -> Option<u64> {
    b.get(o..o + 8).map(|s| {
        let mut a = [0u8; 8];
        a.copy_from_slice(s);
        u64::from_le_bytes(a)
    })
}

impl<'a> Image<'a> {
    fn parse(bytes: &'a [u8]) -> Result<Self> {
        if bytes.get(0..2) != Some(b"MZ") {
            bail!("not a PE image (no MZ header)");
        }
        let pe = u32_at(bytes, 0x3c).context("truncated DOS header")? as usize;
        if bytes.get(pe..pe + 4) != Some(b"PE\0\0") {
            bail!("not a PE image (no PE signature)");
        }
        let nsec = u16_at(bytes, pe + 6).context("truncated file header")? as usize;
        let opt_size = u16_at(bytes, pe + 20).context("truncated file header")? as usize;
        let opt = pe + 24;
        let magic = u16_at(bytes, opt).context("truncated optional header")?;
        if magic != 0x20b {
            bail!("not a PE32+ image (magic 0x{magic:x}); the simulation DLL is 64-bit");
        }
        let image_base = u64_at(bytes, opt + 24).context("truncated optional header")?;
        let mut sections = Vec::with_capacity(nsec);
        for i in 0..nsec {
            let s = opt + opt_size + i * 40;
            let name = bytes
                .get(s..s + 8)
                .context("truncated section table")?
                .iter()
                .take_while(|&&c| c != 0)
                .map(|&c| c as char)
                .collect();
            sections.push(Section {
                name,
                vsize: u32_at(bytes, s + 8).context("truncated section")? as u64,
                va: u32_at(bytes, s + 12).context("truncated section")? as u64,
                rsize: u32_at(bytes, s + 16).context("truncated section")? as u64,
                raw: u32_at(bytes, s + 20).context("truncated section")? as u64,
            });
        }
        Ok(Image {
            bytes,
            image_base,
            sections,
        })
    }

    /// File offset of a virtual address, if it is backed by file data.
    fn offset_of_va(&self, va: u64) -> Option<usize> {
        let rva = va.checked_sub(self.image_base)?;
        self.sections
            .iter()
            .find(|s| rva >= s.va && rva < s.va + s.vsize.min(s.rsize))
            .map(|s| (s.raw + (rva - s.va)) as usize)
    }

    fn va_of_offset(&self, off: usize) -> Option<u64> {
        let off = off as u64;
        self.sections
            .iter()
            .find(|s| off >= s.raw && off < s.raw + s.rsize)
            .map(|s| self.image_base + s.va + (off - s.raw))
    }

    fn section_of_va(&self, va: u64) -> Option<&Section> {
        let rva = va.checked_sub(self.image_base)?;
        self.sections
            .iter()
            .find(|s| rva >= s.va && rva < s.va + s.vsize)
    }

    /// A NUL-terminated printable string at a virtual address.
    fn cstr_at_va(&self, va: u64) -> Option<String> {
        if va == 0 {
            return None;
        }
        let o = self.offset_of_va(va)?;
        let tail = &self.bytes[o..self.bytes.len().min(o + 256)];
        let len = tail.iter().position(|&c| c == 0)?;
        let s = &tail[..len];
        if s.is_empty() || !s.iter().all(|&c| (0x20..0x7f).contains(&c)) {
            return None;
        }
        Some(String::from_utf8_lossy(s).into_owned())
    }

    /// File offset of the string `\0name\0`, which is how a pooled literal sits.
    fn find_literal(&self, name: &str) -> Option<usize> {
        let mut needle = Vec::with_capacity(name.len() + 2);
        needle.push(0);
        needle.extend_from_slice(name.as_bytes());
        needle.push(0);
        find_all(self.bytes, &needle).first().map(|&o| o + 1)
    }

    /// File offsets holding the 8-byte little-endian value.
    fn find_pointer(&self, va: u64) -> Vec<usize> {
        find_all(self.bytes, &va.to_le_bytes())
    }
}

fn find_all(hay: &[u8], needle: &[u8]) -> Vec<usize> {
    let mut out = Vec::new();
    if needle.is_empty() || hay.len() < needle.len() {
        return out;
    }
    let first = needle[0];
    let mut i = 0;
    while i + needle.len() <= hay.len() {
        match hay[i..].iter().position(|&c| c == first) {
            Some(p) => {
                i += p;
                if i + needle.len() <= hay.len() && &hay[i..i + needle.len()] == needle {
                    out.push(i);
                }
                i += 1;
            }
            None => break,
        }
    }
    out
}

/// A function name: `sleep_until`, but also `+`, `!=` and `<=`.
fn is_function_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 128
        && s.chars()
            .all(|c| c.is_ascii_graphic() && c != '"' && c != '(' && c != ')')
}

/// A global name, which is always an identifier.
fn is_identifier(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_lowercase() || c == '_')
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

/// Read a function definition at a virtual address, or `None` if the bytes
/// there do not look like one.
fn read_function(img: &Image, def_va: u64, type_count: usize) -> Option<FunctionEntry> {
    let sec = img.section_of_va(def_va)?;
    if !(sec.name == ".rdata" || sec.name == ".data") {
        return None;
    }
    let o = img.offset_of_va(def_va)?;
    let b = img.bytes;
    let returns = u16_at(b, o)?;
    let name = img.cstr_at_va(u64_at(b, o + 8)?)?;
    if !is_function_name(&name) || returns as usize >= type_count {
        return None;
    }
    let flags = u32_at(b, o + 16)?;
    let parse = u64_at(b, o + 24)?;
    let evaluate = u64_at(b, o + 32)?;
    // `cond` has no evaluator of its own (the parser rewrites it into `if`),
    // so a null pointer is allowed; a non-null one must land in code.
    let in_code = |va: u64| {
        va == 0
            || img
                .section_of_va(va)
                .map(|s| s.name == ".text")
                .unwrap_or(false)
    };
    if !in_code(parse) || !in_code(evaluate) {
        return None;
    }
    let help = img.cstr_at_va(u64_at(b, o + 40)?);
    let parameters_text = img.cstr_at_va(u64_at(b, o + 48)?);
    let count = u16_at(b, o + 56)? as usize;
    if count > 32 {
        return None;
    }
    let mut parameters = Vec::with_capacity(count);
    for i in 0..count {
        let t = u16_at(b, o + 58 + 2 * i)?;
        if t as usize >= type_count {
            return None;
        }
        parameters.push(t);
    }
    Some(FunctionEntry {
        index: 0,
        name,
        returns,
        flags,
        parse_rva: parse.saturating_sub(img.image_base),
        evaluate_rva: evaluate.saturating_sub(img.image_base),
        help,
        parameters_text,
        parameters,
    })
}

/// Walk the pointer table outward from one known slot.
fn read_function_table(img: &Image, type_count: usize) -> Result<(u64, Vec<FunctionEntry>)> {
    let anchor = "sleep_until";
    let str_off = img.find_literal(anchor).with_context(|| {
        format!("the DLL has no `{anchor}` literal; is this the simulation DLL?")
    })?;
    let str_va = img
        .va_of_offset(str_off)
        .context("literal outside any section")?;
    let name_refs = img.find_pointer(str_va);
    let def_off = match name_refs.as_slice() {
        [r] => r
            .checked_sub(8)
            .context("definition before start of file")?,
        [] => bail!("nothing points at `{anchor}`"),
        many => bail!(
            "`{anchor}` is referenced {} times; the layout has changed",
            many.len()
        ),
    };
    let def_va = img
        .va_of_offset(def_off)
        .context("definition outside any section")?;
    read_function(img, def_va, type_count).with_context(|| {
        format!("the definition of `{anchor}` does not have the expected layout")
    })?;
    let slot_refs = img.find_pointer(def_va);
    let slot = match slot_refs.as_slice() {
        [s] => *s,
        [] => bail!("no table slot points at the `{anchor}` definition"),
        many => bail!("{} slots point at `{anchor}`", many.len()),
    };

    let slot_ok = |off: usize| -> bool {
        u64_at(img.bytes, off)
            .and_then(|va| read_function(img, va, type_count))
            .is_some()
    };
    let mut lo = slot;
    while lo >= 8 && slot_ok(lo - 8) {
        lo -= 8;
    }
    let mut hi = slot;
    while slot_ok(hi + 8) {
        hi += 8;
    }
    let table_va = img.va_of_offset(lo).context("table outside any section")?;
    let mut out = Vec::with_capacity((hi - lo) / 8 + 1);
    for (i, off) in (lo..=hi).step_by(8).enumerate() {
        let va = u64_at(img.bytes, off).unwrap();
        let mut f = read_function(img, va, type_count).unwrap();
        f.index = i as u16;
        out.push(f);
    }
    Ok((table_va - img.image_base, out))
}

fn read_global(img: &Image, off: usize, type_count: usize) -> Option<GlobalEntry> {
    let b = img.bytes;
    let name = img.cstr_at_va(u64_at(b, off)?)?;
    if !is_identifier(&name) {
        return None;
    }
    let value_type = u16_at(b, off + 8)?;
    if value_type as usize >= type_count {
        return None;
    }
    let storage = u64_at(b, off + 16)?;
    if storage != 0 && img.section_of_va(storage).is_none() {
        return None;
    }
    Some(GlobalEntry {
        index: 0,
        name,
        value_type,
        storage_rva: storage.checked_sub(img.image_base).unwrap_or(0),
    })
}

/// Walk the inline globals array outward from `game_speed`.
fn read_globals(img: &Image, type_count: usize) -> Result<(u64, Vec<GlobalEntry>)> {
    let anchor = "game_speed";
    let str_off = img
        .find_literal(anchor)
        .with_context(|| format!("the DLL has no `{anchor}` literal"))?;
    let str_va = img
        .va_of_offset(str_off)
        .context("literal outside any section")?;
    let refs: Vec<usize> = img
        .find_pointer(str_va)
        .into_iter()
        .filter(|&o| read_global(img, o, type_count).is_some())
        .collect();
    let slot = match refs.as_slice() {
        [s] => *s,
        [] => bail!("no globals entry names `{anchor}`"),
        many => bail!("{} globals entries name `{anchor}`", many.len()),
    };
    const STRIDE: usize = 24;
    let mut lo = slot;
    while lo >= STRIDE && read_global(img, lo - STRIDE, type_count).is_some() {
        lo -= STRIDE;
    }
    let mut hi = slot;
    while read_global(img, hi + STRIDE, type_count).is_some() {
        hi += STRIDE;
    }
    let table_va = img
        .va_of_offset(lo)
        .context("globals outside any section")?;
    let mut out = Vec::new();
    for (i, off) in (lo..=hi).step_by(STRIDE).enumerate() {
        let mut g = read_global(img, off, type_count).unwrap();
        g.index = i as u16;
        out.push(g);
    }
    Ok((table_va - img.image_base, out))
}

fn lua_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// The evaluator the release build substitutes for functions it compiled out.
///
/// 425 functions — every `cheat_*`, the havok and render debugging, `map_info`,
/// `script_recompile` — point at one tiny routine that returns void without
/// looking at its arguments. The engine's own `help` skips functions whose
/// evaluator is that routine, which is how it can be told apart: it is by far
/// the most shared evaluator in the table.
fn stub_evaluator(functions: &[FunctionEntry]) -> u64 {
    let mut counts: BTreeMap<u64, u32> = BTreeMap::new();
    for f in functions {
        *counts.entry(f.evaluate_rva).or_default() += 1;
    }
    counts
        .into_iter()
        .max_by_key(|&(_, n)| n)
        .map(|(rva, _)| rva)
        .unwrap_or(0)
}

fn write_lua(
    path: &PathBuf,
    build: &str,
    types: &[String],
    functions: &[FunctionEntry],
    globals: &[GlobalEntry],
    stub: u64,
) -> Result<()> {
    let mut s = String::new();
    s.push_str("-- Generated by `mjolnir console`. Do not edit.\n");
    s.push_str(&format!("-- build: {build}\n"));
    s.push_str("return {\n");
    s.push_str("  functions = {\n");
    for f in functions {
        let params: Vec<String> = f
            .parameters
            .iter()
            .map(|&t| lua_string(&types[t as usize]))
            .collect();
        s.push_str(&format!(
            "    [{}] = {{ index = {}, returns = {}, flags = {}, params = {{ {} }}{}{} }},\n",
            lua_string(&f.name),
            f.index,
            lua_string(&types[f.returns as usize]),
            f.flags,
            params.join(", "),
            f.parameters_text
                .as_ref()
                .map(|t| format!(", text = {}", lua_string(t)))
                .unwrap_or_default(),
            if f.evaluate_rva == stub {
                ", stub = true"
            } else {
                ""
            }
        ));
    }
    s.push_str("  },\n  globals = {\n");
    for g in globals {
        s.push_str(&format!(
            "    [{}] = {{ index = {}, type = {}{} }},\n",
            lua_string(&g.name),
            g.index,
            lua_string(&types[g.value_type as usize]),
            if g.storage_rva == 0 {
                ", dead = true"
            } else {
                ""
            }
        ));
    }
    s.push_str("  },\n}\n");
    std::fs::write(path, s).with_context(|| format!("cannot write {}", path.display()))
}

pub fn run(a: ConsoleArgs) -> Result<()> {
    let corpus = blam_hsc::ScriptCorpus::load(&a.corpus).with_context(|| {
        format!(
            "cannot read {}. Run `mjolnir scripting` against an installed game to generate it.",
            a.corpus.display()
        )
    })?;
    let types = corpus.value_types.clone();
    let bytes =
        std::fs::read(&a.dll).with_context(|| format!("cannot read {}", a.dll.display()))?;
    let img = Image::parse(&bytes)?;

    let (function_table_rva, functions) = read_function_table(&img, types.len())?;
    let (globals_rva, globals) = read_globals(&img, types.len())?;

    // The corpus names opcodes by observation; the table names them by
    // position. Every opcode the corpus knows must land on the same name here,
    // or the table walk started in the wrong place.
    let mut agree = 0u32;
    let mut disagree = Vec::new();
    for (opcode, def) in &corpus.functions {
        match functions.get(*opcode as usize) {
            Some(f) if f.name == def.name => agree += 1,
            Some(f) => disagree.push(format!(
                "0x{opcode:04x} corpus {} table {}",
                def.name, f.name
            )),
            None => disagree.push(format!("0x{opcode:04x} corpus {} beyond table", def.name)),
        }
    }
    if !disagree.is_empty() {
        for d in disagree.iter().take(10) {
            eprintln!("  {d}");
        }
        bail!(
            "{} corpus opcode(s) disagree with the table ({agree} agree; the walk found {} entries ending at `{}`); not writing",
            disagree.len(),
            functions.len(),
            functions.last().map(|f| f.name.as_str()).unwrap_or("")
        );
    }

    let mut flag_counts: BTreeMap<u32, u32> = BTreeMap::new();
    for f in &functions {
        *flag_counts.entry(f.flags).or_default() += 1;
    }
    let stub = stub_evaluator(&functions);
    let stubbed = functions.iter().filter(|f| f.evaluate_rva == stub).count();
    let dead_globals = globals.iter().filter(|g| g.storage_rva == 0).count();
    println!("  image base      0x{:x}", img.image_base);
    println!(
        "  function table  rva 0x{function_table_rva:x}, {} entries",
        functions.len()
    );
    println!(
        "  corpus agrees   {agree} of {} opcodes",
        corpus.functions.len()
    );
    println!(
        "  with help text  {}",
        functions.iter().filter(|f| f.help.is_some()).count()
    );
    println!(
        "  flags           {}",
        flag_counts
            .iter()
            .map(|(k, v)| format!("{k}:{v}"))
            .collect::<Vec<_>>()
            .join(" ")
    );
    println!("  stub evaluator  rva 0x{stub:x}, shared by {stubbed} functions (compiled out of this build)");
    println!(
        "  globals         rva 0x{globals_rva:x}, {} entries, {dead_globals} without storage",
        globals.len()
    );

    if a.dry_run {
        println!("\ndry run: nothing written");
        return Ok(());
    }

    let json = serde_json::json!({
        "generator": format!("mjolnir {}", env!("CARGO_PKG_VERSION")),
        "build": a.build,
        "dll": a.dll.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
        "dll_size": bytes.len(),
        "image_base": format!("0x{:x}", img.image_base),
        "function_table_rva": format!("0x{function_table_rva:x}"),
        "globals_rva": format!("0x{globals_rva:x}"),
        "value_types": types,
        "functions": functions.iter().map(|f| serde_json::json!({
            "index": f.index,
            "name": f.name,
            "returns": types[f.returns as usize],
            "flags": f.flags,
            "parameters": f.parameters.iter().map(|&t| types[t as usize].clone()).collect::<Vec<_>>(),
            "parameters_text": f.parameters_text,
            "help": f.help,
            "parse_rva": format!("0x{:x}", f.parse_rva),
            "evaluate_rva": format!("0x{:x}", f.evaluate_rva),
            "stub": f.evaluate_rva == stub,
        })).collect::<Vec<_>>(),
        "globals": globals.iter().map(|g| serde_json::json!({
            "index": g.index,
            "name": g.name,
            "type": types[g.value_type as usize],
            "storage_rva": format!("0x{:x}", g.storage_rva),
            "dead": g.storage_rva == 0,
        })).collect::<Vec<_>>(),
    });
    let text = serde_json::to_string_pretty(&json)?;
    std::fs::write(&a.out, text).with_context(|| format!("cannot write {}", a.out.display()))?;
    let size = std::fs::metadata(&a.out).map(|m| m.len()).unwrap_or(0);
    println!(
        "\nwrote {} ({:.1} KiB)",
        a.out.display(),
        size as f64 / 1024.0
    );
    if let Some(lua) = &a.lua {
        write_lua(lua, &a.build, &types, &functions, &globals, stub)?;
        println!("wrote {}", lua.display());
    }
    Ok(())
}
