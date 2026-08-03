# MJOLNIR Hub

The mod platform at **[mjolnircore.com](https://mjolnircore.com)** — mod pages, releases,
ratings, comments, moderation, and the open API that third-party tools integrate against.

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
| `src/app` | Routes and pages. `api/v1/[[...route]]` mounts the Hono API; `docs/` renders the guides, notes, tag reference and API reference. |
| `src/lib/api` | The API itself — one module per area (`mods`, `publish`, `account`, `device`, `moderation`, `scan`, …), plus `app.ts` which assembles them. |
| `src/kit` | Community UI (mod cards, ratings, comments, galleries) and the API client, shared with the launcher **as source** through a bundler alias. See [`src/kit/README.md`](src/kit/README.md). |
| `src/generated` | Snapshots built from outside the Next project — the repo's `docs/` and the tag definition corpus. Never edit by hand; `pnpm sync` writes them. |
| `migrations/` | Numbered, forward-only D1 migrations. The schema's only source of truth. |
| `public/openapi.json` | The exported spec, checked in so CI can diff against it. |

## Running it

```bash
pnpm install
pnpm db:migrate      # apply migrations to the local D1
pnpm dev             # syncs docs + tag defs, then starts Next
```

`pnpm dev` runs `pnpm sync` first, which regenerates `src/generated/` from `../docs` and
`../defs`. That is why editing a repo doc shows up on the site without touching this package.

A doc is only published if it is listed in `scripts/sync-docs.mjs` (`ORDER` for notes, `GUIDES`
for guides). Anything else is skipped, and a `[…](that.md)` link pointing at it will 404 — the
script warns about unlisted docs for exactly this reason.

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

Everything CI runs, runnable locally:

```bash
pnpm lint
pnpm typecheck
pnpm openapi:check          # spec matches the code
pnpm conformance:signing    # TS signature verification agrees with the Rust mjolnir-sign crate
```

`conformance:signing` is the one worth understanding. `.mjolnir` archives are signed by the tag
editor in Rust and verified both by the launcher (Rust) and by the hub (TypeScript). The check
generates a fixture from the Rust crate and verifies it with the TypeScript implementation, so
the two cannot drift into disagreeing about what a valid signature is.

## Deploying

```bash
pnpm db:migrate:prod        # apply migrations to the deployed D1 first
pnpm deploy
```

In practice this is done by [`deploy-hub.yml`](../.github/workflows/deploy-hub.yml) rather than
by hand.

## Further reading

- [`../docs/hub_architecture.md`](../docs/hub_architecture.md) — why the platform is shaped this
  way: the trust tiers, the chunk-ID conflict index, the API design, and what has shipped
- [`../docs/mjolnir_format.md`](../docs/mjolnir_format.md) — the archive format the scanner validates
- [`../docs/mod_signing_design.md`](../docs/mod_signing_design.md) — what author signatures do and
  do not defend against
