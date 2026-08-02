# @mjolnir/hub-kit

Everything that knows the shape of the MJOLNIR Hub API, shared by the two
surfaces that talk to it:

- `hub/` — the website at mjolnircore.com
- `apps/launcher/` — the Tauri desktop launcher

Ratings, reviews, comments, galleries, mod cards, release lists and the report
flow exist once, here, and both apps render the same components against the
same client.

## Why it lives inside the website

It is shared code, so `packages/hub-kit` at the repository root is the obvious
home — and that is where it started. It does not work. OpenNext sets
`NEXT_PRIVATE_OUTPUT_TRACE_ROOT` to the Next.js project directory before
building, which pins Turbopack's resolution root to `hub/`; anything above that
fails with `Module not found`, and raising `outputFileTracingRoot` to the
repository instead moves the standalone output to a path OpenNext then cannot
find.

Vite has no such constraint. So the kit sits inside the app with the strict
bundler, and the app with the flexible one reaches in:

| App | Wiring |
| --- | --- |
| hub | ordinary local source; `@mjolnir/hub-kit` is a tsconfig path |
| launcher | `resolve.alias` + `server.fs.allow` in `vite.config.ts`, `paths` in `tsconfig.json`, `@source` in `src/index.css` |

Consumed as **source**, never as a published package: the two apps have
separate lockfiles and separate CI jobs (`deploy-hub.yml`,
`release-launcher.yml`), each running `pnpm install --frozen-lockfile` in its
own directory, and a workspace would make one app's install depend on the
other's lockfile for no benefit. There is no build step and no `dist/` — both
apps typecheck this source as part of their own `tsc`, so a break surfaces in
whichever app you are working in, immediately.

The launcher also aliases `react` and `react-dom` to its own copies, because
these files sit outside its root and cannot resolve them by walking up. That
alias is what guarantees a single React instance in the bundle.

## Theming

Components never use an app's Tailwind colour names — the website calls its
gold `--color-gold` and the launcher calls it `--color-mjolnir-gold`. They
style against the `--mj-*` variables declared in `ui/theme.css`, and each app
re-points those at its own palette after importing it.

## The client

`createHubClient({ baseUrl, token, transport })` returns a typed client for the
whole v1 API. The transport is injectable because the two callers reach the API
very differently:

- **Website** — same-origin `fetch`, Discord cookie session.
- **Launcher** — a Tauri command. The webview holds no credential; the paired
  API key lives in Rust and is attached there, so a compromised page cannot
  read it.

`types.ts` mirrors `hub/src/lib/api/schemas.ts`, which stays the single source
of truth: those zod schemas generate `hub/public/openapi.json`.

## No `"use client"` here

These files carry no directives: Vite has no concept of them and warns. The
website adds the boundary in `src/app/components/HubKit.tsx`, which re-exports
what the app router needs as client components.
