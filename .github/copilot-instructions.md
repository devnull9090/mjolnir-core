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

## Releases and changelogs

- Every tagged release must have a changelog entry at `changelog/<product>/<version>.md`, written in the same change that bumps the version. `scripts/check-changelog.mjs` runs first in every release workflow and fails the release without one, so a release cannot ship unannounced.
- The entry is the single source: the workflows read it for the GitHub release body and the Discord announcement, the hub renders it at `/changelog/<product>/<version>`, and the launcher shows it in a "What's new" dialog after an update. Never write release notes into a workflow, a Discord payload or a UI string — write the entry and let them read it.
- Products and their tag prefixes live in `changelog/products.json`. Adding a product means adding it there and creating its directory.
- Write for a player, not for us. Lead with what someone can now do, name the visible symptom in a fix, and describe changes in plain language rather than in tag paths, crate names or PR numbers. `changelog/README.md` is the full contract.
- Be honest about a release that does nothing for players: say it is a pipeline or version-bump release in one line. Inventing features for it is worse than a boring entry.
- Say plainly when a release requires manual action — a build existing installs cannot auto-update to, a reinstall, a migration — in the `**Summary:**`, not buried in a bullet.
- Entries are public and indexed. Give each one a descriptive `# Title` naming the change rather than the version, and a `**Summary:**` of 100–160 characters that reads as a complete sentence out of context, since it becomes the page's meta description and the feed entry.
- Backfilling or correcting an entry is a normal change: they are read from the published site, so a correction reaches installs that already have the build.

## Validation

- Run the narrowest relevant check after code or documentation changes. For hub changes, run lint and a production build before considering the work complete.
- Keep generated analysis output out of source files unless it is intentionally curated and reasonably sized.