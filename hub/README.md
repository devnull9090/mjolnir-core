# MJOLNIR Hub

The mod and multiplayer platform at **[mjolnircore.com](https://mjolnircore.com)** — mod and
map pages, releases, ratings, comments, moderation, the public games list and match history, the
blog and changelogs, and the open API that third-party tools integrate against.

Next.js on **Cloudflare Workers** via OpenNext, with D1 for data and R2 for archives and media.
The API is a [Hono](https://hono.dev) app mounted under a Next catch-all route
(`src/app/api/v1/[[...route]]/route.ts`), which is what lets one set of Zod schemas produce
request validation, response types and the OpenAPI document at once.

> **Next.js version note:** this repo pins a Next release whose APIs and conventions differ from
> what most references describe. Read the relevant guide in `node_modules/next/dist/docs/` before
> writing app code.

## Layout

| Path | What it is |
|---|---|
| `src/app` | Routes and pages (mods, maps, games, matches, players, tools, blog, changelog, download, moderation, …). `api/v1/[[...route]]` mounts the Hono API, beside plain route handlers for `api/changelog`, `api/releases/latest` and `api/tools/latest`; `docs/` renders the guides, notes, tag and console references, research pages and the API reference. |
| `src/lib/api` | The API itself — one module per area (`publish`, `community`, `account`, `device`, `moderation`, `maps`, `lobby`, `matches`, `players`, `crashes`, `benches`, `scan`, …), plus `app.ts`, which assembles them and serves the mod listing and detail routes itself. |
| `src/kit` | Community UI (mod cards, ratings, comments, galleries) and the API client, shared with the launcher (and, for the changelog dialog, the tag editor) **as source** through a bundler alias. See [`src/kit/README.md`](src/kit/README.md). |
| `src/generated` | Snapshots built from outside the Next project — the repo's `docs/`, `changelog/` and `blog/`, the tag definition corpus and the Blam console reference. Never edit by hand; `pnpm sync` writes them, along with the search indexes and doc images under `public/`. |
| `migrations/` | Numbered, forward-only D1 migrations. The schema's only source of truth. |
| `public/openapi.json` | The exported spec, checked in so CI can diff against it. |

## Running it

```bash
pnpm install
pnpm db:migrate      # apply migrations to the local D1
pnpm dev             # syncs docs, defs, changelog and blog, then starts Next
```

Discord sign-in needs `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` and `JWT_SECRET`: copy
`.dev.vars.example` to `.dev.vars` (git-ignored) and fill them in. In production they are GitHub
Actions secrets that `deploy-hub.yml` uploads to the Worker. Settings that are not secret are
`vars` in `wrangler.jsonc`: `SITE_URL`, `REQUIRE_SIGNED_UPLOADS` (on, so an upload must carry an
author signature) and `SUPER_ADMIN_DISCORD_ID` (the account seated as admin at sign-in).

`pnpm dev` runs `pnpm sync` first, which regenerates `src/generated/` from `../docs`, `../defs`,
`../changelog` and `../blog`. That is why editing a repo doc shows up on the site without
touching this package.

A doc is only published if it is listed in `scripts/sync-docs.mjs` (`ORDER` for notes, `GUIDES`
for guides). Anything else is skipped, and the script warns about unlisted docs. A relative link
in a published doc goes to the note or guide route when its target is published, and to the file
on GitHub otherwise (`resolveHref` in `src/app/docs/_components/Markdown.tsx`), so a link to an
unlisted doc leaves the site rather than 404ing.

To exercise the Workers runtime rather than the Next dev server — bindings, the real R2 and D1
behaviour — build and preview:

```bash
pnpm preview         # opennextjs build, then wrangler dev
```

## The API

Open by design: reads need no authentication, CORS is `*`, and the spec is generated from the
implementation rather than written alongside it.

- **[`/docs/api`](https://mjolnircore.com/docs/api)** — the reference, rendered with Scalar
- **[`/api/v1/openapi.json`](https://mjolnircore.com/api/v1/openapi.json)** — the spec itself

**After any API change, re-export the spec:**

```bash
pnpm openapi:export
```

CI runs `pnpm openapi:check`, which re-exports and then `git diff --exit-code`s
`public/openapi.json`. A change that skips the export fails the build — that check is the whole
reason the published spec can be trusted.

Auth comes in three shapes, described in full in
[`../docs/hub_architecture.md`](../docs/hub_architecture.md) §7:

- **Humans** — Discord OAuth → short-lived JWT in an `HttpOnly` cookie.
- **Tools** — API keys, `Authorization: Bearer mjc_…`, hash-stored, scoped and revocable.
- **Desktop clients** — device pairing, a supervised way of minting one of those keys. Approval
  needs a cookie session, so a key can never mint another key.

## Checks

CI (the `hub` job in [`ci.yml`](../.github/workflows/ci.yml)) runs these, and each runs locally:

```bash
pnpm lint
pnpm typecheck
pnpm openapi:check          # spec matches the code
pnpm sync:check             # committed sync output matches what pnpm sync writes
```

Two more run locally only:

```bash
pnpm test                   # match chat and bench routes against every migration, in memory
pnpm conformance:signing    # TS signature verification agrees with the Rust mjolnir-sign crate (needs cargo)
```

`conformance:signing` is the one worth understanding. `.mjolnir` archives are signed in Rust, by
the tag editor and by `mjolnir map pack --sign`, and verified both by the launcher (Rust) and by
the hub (TypeScript). The check generates a fixture from the Rust crate and verifies it with the
TypeScript implementation, so the two cannot drift into disagreeing about what a valid signature
is.

## Deploying

```bash
pnpm db:migrate:prod        # apply migrations to the deployed D1 first
pnpm deploy
```

[`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) runs the deploy on every push to `main`
that touches `hub/**` or a source the build snapshots into the site (`docs/**` among them; the
workflow's `paths` lists them all), or when run by hand, and uploads the Discord and JWT secrets.
It does not apply migrations: run `pnpm db:migrate:prod` yourself before a change that needs a
new one reaches `main`.

## Further reading

- [`../docs/hub_architecture.md`](../docs/hub_architecture.md) — why the platform is shaped this
  way: the trust tiers, the chunk-ID conflict index, the API design, and what has shipped
- [`../docs/mjolnir_format.md`](../docs/mjolnir_format.md) — the archive format the scanner validates
- [`../docs/mod_signing_design.md`](../docs/mod_signing_design.md) — what author signatures do and
  do not defend against
