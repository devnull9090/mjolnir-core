# @mjolnir/hub-kit

Everything that knows the shape of the MJOLNIR Hub API, shared by the surfaces
that talk to it:

- `hub/` — the website at mjolnircore.com
- `apps/launcher/` — the Tauri desktop launcher
- `apps/tag-editor/` — the Tauri tag editor, for `changelog.ts` and
  `ui/WhatsNew.tsx` only

Ratings, reviews, comments, galleries, mod cards, release lists and the report
flow exist once, here, and every app renders the same components against the
same client.

`changelog.ts` and `ui/WhatsNew.tsx` are the same idea for release notes: the
entries are authored once in the repository's `changelog/` directory, published
by the hub at `/api/changelog`, and rendered by one dialog wherever an update
lands. Its `transport` is injectable for the same reason the client's is — see
below.

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
| tag editor | the same three, added for the changelog dialog |

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

## Uploads

`ui/FileDrop.tsx` holds the parts every upload surface needs, so no page grows
its own: `<FileDropzone>` (drag, click, paste-safe, and a document-level guard
so a near-miss drop cannot navigate the page away), `useFileStaging` (the
chosen files, their object-URL previews, and the revoking of those previews),
and `<StagedFileRow>` (thumbnail, size, description field, progress, remove).

A surface declares what it takes as a `FileRules` — an `accept` string, byte
ceilings per MIME prefix, a file count — and the zone applies it to dropped
files as well as picked ones, which the browser does not.

`ui/MediaUploader.tsx` composes those into the gallery submission flow and is
what both the mod page and the owner's manage page mount; the release archive
takes only the dropzone. Progress comes from the client's optional
`onProgress`, which the browser transport serves over `XMLHttpRequest` because
`fetch` still cannot report bytes sent — a transport that cannot measure it
just never calls back, and the bar stays indeterminate.

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

The consequence for the website: **server components and route handlers must
not import the `@mjolnir/hub-kit` barrel.** It re-exports every component here,
so pulling it into a Server Component drags `useState` in with it and fails the
build. Import the module instead — `@mjolnir/hub-kit/changelog`,
`@mjolnir/hub-kit/ui/format` — which the `@mjolnir/hub-kit/*` tsconfig path
already resolves.
