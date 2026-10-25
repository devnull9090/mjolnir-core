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
- A `docs/*.md` file is published only when `hub/scripts/sync-docs.mjs` lists it: add a research note to the `ORDER` array (published at `/docs/notes/<slug>`) or a task-shaped guide to `GUIDES` (`/docs/guides/<slug>`); a doc in neither list is not published, and the sync warns about it. That script regenerates `hub/src/generated/docs.json`; `blog/*.md` is published the same way by `hub/scripts/sync-blog.mjs`. `pnpm sync` runs every sync script, and `pnpm dev` and `pnpm build` run it. Write those files assuming a public audience.
- Give major targets, including `HaloSimulation_tag_release.dll`, a dedicated public page rather than burying them in a session log.
- Preserve prior conclusions when they are disproven: mark them superseded and explain the new evidence instead of silently deleting the history.

## Releases and changelogs

- Every tagged release must have a changelog entry at `changelog/<product>/<version>.md`, written in the same change that bumps the version. `scripts/check-changelog.mjs` runs in every release workflow before anything is packaged or published, and fails the release without one, so a release cannot ship unannounced.
- The entry is the single source: the workflows read it for the GitHub release body and the Discord announcement, the hub renders it at `/changelog/<product>/<version>`, and the launcher shows it in a "What's new" dialog after an update. Never write release notes into a workflow, a Discord payload or a UI string — write the entry and let them read it.
- Products and their tag prefixes live in `changelog/products.json`. Adding a product means adding it there and creating its directory.
- Write for a player, not for us. Lead with what someone can now do, name the visible symptom in a fix, and describe changes in plain language rather than in tag paths, crate names or PR numbers. `changelog/README.md` is the full contract.
- Be honest about a release that does nothing for players: say it is a pipeline or version-bump release in one line. Inventing features for it is worse than a boring entry.
- Say plainly when a release requires manual action — a build existing installs cannot auto-update to, a reinstall, a migration — in the `**Summary:**`, not buried in a bullet.
- Entries are public and indexed. Give each one a descriptive `# Title` naming the change rather than the version, and a `**Summary:**` of 100–160 characters that reads as a complete sentence out of context, since it becomes the page's meta description and the feed entry.
- Backfilling or correcting an entry is a normal change: they are read from the published site, so a correction reaches installs that already have the build.
- Code mods (`mods/*`, and the DLLs built from `native/*`) ship only from `.github/workflows/release-mods.yml` on a `mods-v*` tag. Any luacheck warning fails that release, so run luacheck before tagging. Every `mods/*/mod.json` needs `version`, `summary` and `category`, and the launcher offers a mod as an update only when its `version` differs from the installed one, so bump it in every mod that changed. Native DLLs are built by CI and never committed.

## Validation

- Run the narrowest relevant check after code or documentation changes. For hub changes, run `pnpm lint`, `pnpm typecheck` and a production build before considering the work complete.
- After editing anything under `docs/`, `defs/`, `changelog/` or `blog/`, run `pnpm sync` in `hub/` and commit what it changes under `hub/src/generated/` and `hub/public/`: CI's `pnpm sync:check` fails on a stale snapshot even though the build, which re-runs the sync, succeeds. An API change also needs `pnpm openapi:export`, or `pnpm openapi:check` fails.
- Keep generated analysis output out of source files unless it is intentionally curated and reasonably sized.