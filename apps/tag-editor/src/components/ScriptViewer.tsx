import { useEffect, useMemo, useRef, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";
import type { ScriptDecl, ScriptSourceFile } from "../lib/api";

/**
 * Highlight one line of HSC.
 *
 * Done here rather than with a syntax-highlighting library because HSC is small
 * enough to tokenise in a few rules, and because the two rules that matter are
 * ones a Lisp mode gets wrong: a `;` inside a string is text, not a comment,
 * and a backslash in a tag path is a literal character, not an escape.
 */
type Piece = { text: string; kind: string };

const KEYWORDS = new Set(["script", "global", "cond"]);
const SCRIPT_KINDS = new Set([
  "startup",
  "dormant",
  "continuous",
  "static",
  "command_script",
  "stub",
]);
const CONTROL = new Set([
  "begin",
  "begin_random",
  "begin_count",
  "begin_random_count",
  "if",
  "and",
  "or",
  "not",
  "set",
  "sleep",
  "sleep_until",
  "sleep_forever",
  "wake",
  "branch",
  "inspect",
]);

const CLASS_FOR: Record<string, string> = {
  comment: "text-text-dim italic",
  string: "text-accent-green",
  number: "text-accent-blue",
  keyword: "text-mjolnir-gold font-semibold",
  kind: "text-mjolnir-gold",
  control: "text-accent-blue",
  paren: "text-text-dim",
  bool: "text-accent-blue",
  plain: "text-text-secondary",
};

function highlight(line: string): Piece[] {
  const out: Piece[] = [];
  let i = 0;
  let word = "";

  const flushWord = () => {
    if (!word) return;
    let kind = "plain";
    if (KEYWORDS.has(word)) kind = "keyword";
    else if (SCRIPT_KINDS.has(word)) kind = "kind";
    else if (CONTROL.has(word)) kind = "control";
    else if (word === "true" || word === "false" || word === "none") kind = "bool";
    else if (!Number.isNaN(Number(word))) kind = "number";
    out.push({ text: word, kind });
    word = "";
  };

  while (i < line.length) {
    const c = line[i];
    if (c === ";") {
      flushWord();
      out.push({ text: line.slice(i), kind: "comment" });
      return out;
    }
    if (c === '"') {
      flushWord();
      let j = i + 1;
      while (j < line.length && line[j] !== '"') j += 1;
      out.push({ text: line.slice(i, Math.min(j + 1, line.length)), kind: "string" });
      i = j + 1;
      continue;
    }
    if (c === "(" || c === ")") {
      flushWord();
      out.push({ text: c, kind: "paren" });
      i += 1;
      continue;
    }
    if (/\s/.test(c)) {
      flushWord();
      out.push({ text: c, kind: "plain" });
      i += 1;
      continue;
    }
    word += c;
    i += 1;
  }
  flushWord();
  return out;
}

/** Rows rendered at once. A 4,449-line source file is too much for one pass. */
const WINDOW = 400;

/**
 * Where the outline last sent us.
 *
 * The nonce is what makes clicking the same entry twice scroll again, and it
 * is also why the line is not cleared once we arrive: it stays marked so it is
 * still findable after the scroll settles.
 */
type Target = { line: number; nonce: number };

function SourcePane({ file, target }: { file: ScriptSourceFile; target: Target | null }) {
  const lines = useMemo(() => file.text.split("\n"), [file.text]);
  const [shown, setShown] = useState(WINDOW);
  const rowRef = useRef<HTMLDivElement | null>(null);

  // A new file starts at the top with a fresh budget.
  useEffect(() => {
    setShown(WINDOW);
  }, [file.name]);

  // Jumping past the rendered window has to grow it first, or there is nothing
  // to scroll to; the effect then runs again with the row present.
  useEffect(() => {
    if (target === null) return;
    if (target.line > shown) {
      setShown(Math.min(lines.length, target.line + WINDOW));
      return;
    }
    rowRef.current?.scrollIntoView({ block: "center" });
  }, [target, shown, lines.length]);

  const visible = lines.slice(0, shown);

  return (
    <div className="min-h-0 flex-1 overflow-auto bg-surface-primary">
      <pre className="min-w-max font-mono text-[12px] leading-[1.45]">
        {visible.map((line, n) => {
          const number = n + 1;
          const isTarget = target?.line === number;
          return (
            <div
              key={number}
              ref={isTarget ? rowRef : undefined}
              className={`flex ${isTarget ? "bg-mjolnir-gold/15" : ""}`}
            >
              <span className="sticky left-0 w-14 shrink-0 select-none border-r border-border-subtle bg-surface-primary px-2 text-right text-text-dim">
                {number}
              </span>
              <code className="px-3 whitespace-pre">
                {highlight(line).map((p, k) => (
                  <span key={k} className={CLASS_FOR[p.kind] ?? CLASS_FOR.plain}>
                    {p.text}
                  </span>
                ))}
              </code>
            </div>
          );
        })}
      </pre>
      {shown < lines.length && (
        <div className="border-t border-border-subtle p-3 text-center">
          <button
            type="button"
            onClick={() => setShown((s) => Math.min(lines.length, s + WINDOW * 4))}
            className="border border-border-subtle px-3 py-1 font-mono text-[11px] text-text-secondary hover:bg-surface-hover"
          >
            Show more — {lines.length - shown} of {lines.length} lines remaining
          </button>
        </div>
      )}
    </div>
  );
}

/** Scripts and globals, filterable, each jumping to its declaration. */
function Outline({
  scripts,
  onPick,
}: {
  scripts: ScriptDecl[];
  onPick: (file: string | null, line: number | null) => void;
}) {
  const globals = useEditor((s) => s.scripts?.globals ?? []);
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const matchedScripts = scripts.filter((s) => !q || s.name.toLowerCase().includes(q));
  const matchedGlobals = globals.filter((g) => !q || g.name.toLowerCase().includes(q));

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border-subtle">
      <div className="border-b border-border-subtle p-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter scripts and globals"
          className="w-full border border-border-subtle bg-surface-primary px-2 py-1 font-mono text-[11px] text-text-primary placeholder:text-text-dim"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="px-2 pt-2 font-mono text-[10px] uppercase tracking-wider text-text-dim">
          scripts · {matchedScripts.length}
        </div>
        {matchedScripts.map((s, i) => (
          <button
            key={`${s.name}-${i}`}
            type="button"
            onClick={() => onPick(s.file, s.line)}
            disabled={s.line === null}
            title={
              s.line === null
                ? `${s.name} — no source declares this; it is compiler-generated`
                : `(script ${s.kind}${s.kind === "static" || s.kind === "stub" ? ` ${s.return_type}` : ""} ${s.name}${
                    s.parameters.length ? ` — ${s.parameters.join(", ")}` : ""
                  })`
            }
            className={`block w-full truncate px-2 py-0.5 text-left font-mono text-[11px] ${
              s.line === null
                ? "cursor-default text-text-dim"
                : "text-text-secondary hover:bg-surface-hover"
            }`}
          >
            <span className="text-mjolnir-gold">{s.kind.slice(0, 4)}</span> {s.name}
          </button>
        ))}
        <div className="px-2 pt-3 font-mono text-[10px] uppercase tracking-wider text-text-dim">
          globals · {matchedGlobals.length}
        </div>
        {matchedGlobals.map((g, i) => (
          <button
            key={`${g.name}-${i}`}
            type="button"
            onClick={() => onPick(g.file, g.line)}
            disabled={g.line === null}
            title={g.initializer}
            className={`block w-full truncate px-2 py-0.5 text-left font-mono text-[11px] ${
              g.line === null
                ? "cursor-default text-text-dim"
                : "text-text-secondary hover:bg-surface-hover"
            }`}
          >
            <span className="text-accent-blue">{g.value_type}</span> {g.name}
          </button>
        ))}
      </div>
    </aside>
  );
}

export function ScriptViewer() {
  const scripts = useEditor((s) => s.scripts);
  const loading = useEditor((s) => s.scriptsLoading);
  const error = useEditor((s) => s.scriptsError);
  const activeFile = useEditor((s) => s.scriptFile);
  const setScriptFile = useEditor((s) => s.setScriptFile);
  const loadScripts = useEditor((s) => s.loadScripts);
  const exportScript = useEditor((s) => s.exportScript);
  const tag = useEditor((s) => s.tag);
  const setViewMode = useEditor((s) => s.setViewMode);
  const [target, setTarget] = useState<Target | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    void loadScripts();
  }, [loadScripts, tag?.path]);

  if (loading) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
        Reading the scenario's script…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-8 text-center text-sm text-accent-red">
        {error}
      </div>
    );
  }
  if (!scripts) return null;

  const file =
    scripts.source_files.find((f) => f.name === activeFile) ?? scripts.source_files[0];

  async function onExport() {
    if (!file) return;
    const dest = await save({
      defaultPath: `${file.name}.hsc`,
      filters: [{ name: "Blam script", extensions: ["hsc"] }],
    });
    if (!dest) return;
    const bytes = await exportScript(dest, file.name);
    if (bytes !== null) setNote(`Wrote ${bytes.toLocaleString()} bytes to ${dest}`);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-border-subtle px-4 py-2">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[11px] text-text-dim">
            {scripts.scripts.length} scripts · {scripts.globals.length} globals ·{" "}
            {scripts.expressions.toLocaleString()} expressions ·{" "}
            {scripts.references.length} referenced tags
          </span>
          <button
            type="button"
            onClick={() => setViewMode("form")}
            title="Back to the tag's fields"
            className="ml-auto border border-border-subtle px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover"
          >
            Fields
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={!file}
            className="border border-border-subtle px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover disabled:text-text-dim"
          >
            Export .hsc
          </button>
        </div>

        {!scripts.has_source && (
          <p className="mt-2 border-l-2 border-mjolnir-gold/60 bg-mjolnir-gold/5 px-2 py-1 text-[11px] text-text-secondary">
            This scenario ships no script source. What follows was decompiled from the
            compiled expression tree: comments are gone, and any <code>cond</code> in the
            original now reads as nested <code>if</code>.
          </p>
        )}

        <div className="mt-2 flex flex-wrap gap-1">
          {scripts.source_files.map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => {
                setScriptFile(f.name);
                setTarget(null);
              }}
              title={`${f.lines.toLocaleString()} lines · ${f.bytes.toLocaleString()} bytes${
                f.flags.length ? ` · ${f.flags.join(", ")}` : ""
              }`}
              className={`border px-2 py-0.5 font-mono text-[11px] ${
                f.name === file?.name
                  ? "border-mjolnir-gold/60 text-mjolnir-gold"
                  : "border-border-subtle text-text-dim hover:bg-surface-hover"
              }`}
            >
              {f.name}
            </button>
          ))}
        </div>

        {note && <p className="mt-2 font-mono text-[11px] text-accent-green">{note}</p>}
      </header>

      <div className="flex min-h-0 flex-1">
        <Outline
          scripts={scripts.scripts}
          onPick={(f, line) => {
            if (f) setScriptFile(f);
            setTarget(line === null ? null : { line, nonce: Date.now() });
            setNote(null);
          }}
        />
        {file ? (
          <SourcePane file={file} target={target} />
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
            This scenario carries no script.
          </div>
        )}
      </div>
    </div>
  );
}
