# MJOLNIR Core Copilot Instructions

## Reverse Engineering

- Treat reverse-engineering claims as evidence-based research. Label each material claim as `Verified`, `Observed`, `Hypothesis`, or `Unverified`.
- Record the source artifact, game build or file hash when available, tool or command, and enough reproduction detail for another contributor to check the result.
- Do not present embedded strings, imports, class names, placeholder paths, or unexecuted code as proof that a feature is reachable at runtime.
- Keep experiments narrowly scoped and reversible. Do not redistribute proprietary game binaries, symbols, keys, decrypted assets, or other copyrighted game content.

## Documentation

- Update documentation in the same change whenever reverse engineering establishes, refutes, or materially changes a finding.
- Use `docs/` for investigation logs, raw observations, reproduction steps, and working notes.
- Use `hub/src/app/docs/` for curated public documentation. Promote only findings whose evidence level is explicit, and link back to the relevant repository research note when practical.
- `docs/*.md` is published verbatim under `/docs/notes/<slug>`. Add a note to the `ORDER` array in `hub/scripts/sync-docs.mjs` to publish it; that script regenerates `hub/src/generated/docs.json` on every `pnpm dev` and `pnpm build`. Write those files assuming a public audience.
- Give major targets, including `HaloSimulation_tag_release.dll`, a dedicated public page rather than burying them in a session log.
- Preserve prior conclusions when they are disproven: mark them superseded and explain the new evidence instead of silently deleting the history.

## Validation

- Run the narrowest relevant check after code or documentation changes. For hub changes, run lint and a production build before considering the work complete.
- Keep generated analysis output out of source files unless it is intentionally curated and reasonably sized.