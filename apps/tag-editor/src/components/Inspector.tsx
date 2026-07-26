import { useEditor } from "../stores/editor-store";
import type { FieldView } from "../lib/api";

function typeColor(type: string): string {
  if (type === "block") return "text-accent-blue";
  if (type === "tag reference") return "text-mjolnir-gold";
  if (type.endsWith("enum") || type.endsWith("flags")) return "text-accent-green";
  return "text-text-dim";
}

function FieldRow({ field }: { field: FieldView }) {
  return (
    <tr className="align-top border-b border-border-subtle/50 last:border-0">
      <td className="py-1.5 pr-3 text-right font-mono text-[11px] text-text-dim">
        {field.offset ?? "—"}
      </td>
      <td className="py-1.5 pr-3 text-right font-mono text-[11px] text-text-dim">
        {field.size ?? "—"}
      </td>
      <td className="py-1.5 pr-3">
        <span className="text-sm">
          {field.name || <em className="text-text-dim">unnamed</em>}
        </span>
        {field.block && (
          <span className="ml-2 font-mono text-[10px] text-text-dim">
            {field.block}
            {field.max_count !== null && ` · max ${field.max_count}`}
          </span>
        )}
        {field.options.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {field.options.map((o, i) => (
              <span
                key={`${o}-${i}`}
                className="border border-border-subtle bg-surface-primary px-1 py-px font-mono text-[10px] text-text-secondary"
              >
                {o}
              </span>
            ))}
          </div>
        )}
      </td>
      <td className={`py-1.5 font-mono text-[11px] ${typeColor(field.type)}`}>
        {field.type}
      </td>
    </tr>
  );
}

/** Guerilla-style field inspector for the selected tag. */
export function Inspector() {
  const { tag, tagLoading, selectedTag } = useEditor();

  if (tagLoading) {
    return <Centered>Reading tag…</Centered>;
  }
  if (!tag) {
    return (
      <Centered>
        {selectedTag === null ? "Select a tag to inspect." : "Nothing to show."}
      </Centered>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-border-subtle bg-surface-primary px-6 py-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="font-mono text-lg text-mjolnir-gold">{tag.group}</h1>
          <span className="font-mono text-xs text-text-dim">{tag.four_cc}</span>
          <span className="font-mono text-xs text-text-dim">v{tag.version}</span>
          <span
            className={`ml-auto font-mono text-[11px] ${
              tag.data_exact ? "text-accent-green" : "text-text-dim"
            }`}
            title={
              tag.data_exact
                ? "The value walk consumed the data payload exactly."
                : "Values are not yet readable for this group; the definition is still complete."
            }
          >
            {tag.data_exact ? "values decoded" : "definition only"}
          </span>
        </div>
        <p className="mt-1 truncate font-mono text-[11px] text-text-secondary">
          {tag.path}
        </p>
        <p className="mt-1 font-mono text-[11px] text-text-dim">
          {tag.chunk_size.toLocaleString()} bytes · {tag.data_size.toLocaleString()} bytes of data ·{" "}
          {tag.structs.length} structs
        </p>
      </header>

      <div className="px-6 py-4">
        {tag.structs.map((struct, i) => (
          <section key={`${struct.name}-${i}`} className="mb-8">
            <h2 className="mb-2 flex items-baseline gap-3 font-mono text-sm">
              <span className="text-text-primary">{struct.name || `struct ${i}`}</span>
              {i === 0 && (
                <span className="border border-mjolnir-gold/40 bg-mjolnir-gold/10 px-1.5 text-[10px] uppercase text-mjolnir-gold">
                  root
                </span>
              )}
              <span className="text-[11px] text-text-dim">
                {struct.fields.length} fields
                {struct.size !== null && ` · ${struct.size} B`}
              </span>
            </h2>
            {struct.fields.length === 0 ? (
              <p className="text-xs text-text-dim">No user-visible fields.</p>
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-border-subtle text-[10px] uppercase text-text-dim">
                    <th className="w-14 py-1 pr-3 text-right font-normal">Off</th>
                    <th className="w-12 py-1 pr-3 text-right font-normal">Size</th>
                    <th className="py-1 pr-3 text-left font-normal">Field</th>
                    <th className="w-40 py-1 text-left font-normal">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {struct.fields.map((f, fi) => (
                    <FieldRow key={`${f.name}-${fi}`} field={f} />
                  ))}
                </tbody>
              </table>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
      {children}
    </div>
  );
}
