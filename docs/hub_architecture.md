# MJOLNIR Hub — Mod Distribution Architecture

**Status:** Partly built. Phase 0 is met, and Phases 1, 2, 2.5 and 3 have shipped — with the
deviations each phase note records. Phase 4 has not started. Section headings note what is live.
**Scope:** How mods are published, verified, delivered, ordered, and de-conflicted; how the
public API is shaped; and where the trust boundary sits between community content and code.

This document was written when the hub was a shell and the launcher installed exactly one
thing — a monolithic modpack zip from R2. That model is now gone. The launcher installs from
two separate, independently signed sources:

- **The runtime bundle** (`runtime/latest`) — UE4SS, the AOB signatures and config tuned for
  this game build, and the UE4SS infrastructure mods. Built by
  [`release-runtime.yml`](../.github/workflows/release-runtime.yml) from inputs pinned in
  [`runtime/ue4ss.lock.json`](../runtime/ue4ss.lock.json).
- **The signed code-mod set** (`mods/latest`) — every MJOLNIR Lua mod, one artifact each, built
  by [`release-mods.yml`](../.github/workflows/release-mods.yml).

Splitting them is what makes the trust story in §2 and §4 real rather than aspirational: the
modpack carried both, so mods arrived by a path the launcher could neither attribute nor
verify.

---

## 1. The load-bearing insight: conflicts are computable

Most mod platforms ask authors to *declare* what their mod conflicts with, then watch that
declaration rot. We do not have to.

[`iostore_packaging.md`](iostore_packaging.md) established that a content mod ships as an
IoStore `_P` override container, and that an override reuses **the identical 12-byte chunk ID**
of the tag it replaces. UE mounts containers by priority; the last mount wins the chunk lookup.

That gives an exact definition:

> Two content mods conflict **iff** their containers claim at least one chunk ID in common.
> Load order decides the winner, deterministically.

Chunk IDs are extractable from the `.utoc` alone — header plus the chunk-ID array, no
decompression, no Oodle. So the hub can parse every uploaded container and store its chunk set,
and "what does this mod conflict with?" becomes a SQL join that is always correct and never
depends on an author telling the truth.

This is the single most valuable thing the platform can offer, and it falls out of work already
done. Everything else in this document is arranged so as not to lose it.

### Hard prerequisite — met

This section long recorded a blocker: the packer's perfect hash was wrong for containers holding
more than one chunk, so a real content mod — a map, a texture pack, a weapon overhaul, all of
them many chunks — silently exposed only one of them. Nothing here worked without it.

**Both defects in that hash are now fixed** (2026-08-01, and 2026-08-02 for a second one that
spilled every chunk at power-of-two chunk counts). `mjolnir pack` implements the engine's
placement for real and refuses to write a container it cannot resolve through the perfect hash
alone, so a container that would silently do nothing in game fails at bake time instead.
Containers may hold any number of chunks. See *A real bug found on the way* and *A second hole in
the same place* in [`iostore_packaging.md`](iostore_packaging.md).

---

## 2. Mod taxonomy, organised by trust

The instinct is to classify mods by what they do (maps, textures, weapons, scripts). That is the
wrong axis for a platform, because it does not tell you who is allowed to publish. Classify by
**what the artifact can execute**:

| Tier | Contains | Can it run code? | Publishing path | Conflict unit |
|---|---|---|---|---|
| **T0 — Content** | IoStore `_P` containers: tags, textures, models, sounds, maps | No. Inert data the engine reads. | Open community upload, automated verification | Chunk ID — exact |
| **T1 — Script** | UE4SS Lua | **Yes** — see below | Source in `mjolnir-core`, PR + review + CI release | Hooked UFunction — heuristic |
| **T2 — Native** | DLLs injected into the game | Yes, arbitrarily | Source in `mjolnir-core`, PR + review + CI release | Process-global — none |

T0 is the overwhelming majority of what people actually want to make, and it is the tier where
we can be genuinely permissive because the blast radius is bounded by the engine's own parser.

### On Lua: it belongs with the DLLs, not with the content

Your instinct to gate native DLLs behind `mjolnir-core` + PR + tagged release is exactly right.
I want to push it one step further and put **Lua on the same side of the line.**

UE4SS exposes stock Lua. Stock Lua has `io`, `os.execute`, and `package.loadlib`. A Lua mod can
therefore write an arbitrary file to disk and load an arbitrary native library — it is a DLL
loader wearing a trenchcoat. Trying to separate "safe Lua" from "unsafe Lua" by scanning for
those names is a game you lose to the first author who writes
`_G[("os")]["exec".."ute"]`. Denylists on a dynamic language do not hold.

So: **T1 and T2 share one pipeline.** Source lives in this repo, changes arrive as pull
requests, a human reads them, CI builds and signs, and the launcher installs only artifacts
whose hash appears in a signed release manifest. The hub never serves a byte of executable
content that a user uploaded.

The cost is real — a Lua author cannot ship in five minutes — and it is the correct trade for a
tool that injects into people's games. Two things make it bearable:

- The barrier only applies to *scripts*. A texture artist, a map maker, a weapon tuner, a
  campaign overhaul — none of them touch it.
- It can be unlocked later. If UE4SS is patched to run mods in a hardened Lua state (`io`,
  `os`, `package`, `loadstring`, `dofile` removed; `require` restricted to a whitelist) plus a
  declared capability manifest, Lua can move to open upload behind that sandbox. That is a real
  project, not a config flag, and it should not block launch.

Say this plainly on the site. "We read every line of code that runs in your game" is a feature,
and it is a sharper differentiator than a faster upload button.

---

## 3. Mods, releases, profiles, collections

The "one modpack" model this section set out to invert is gone; mods and profiles are live, and
collections are not. Four concepts, kept strictly separate:

- **Mod** — the unit of authorship and identity. Has a slug, an owner, a page, a rating.
- **Release** — an immutable, versioned artifact of a mod. Semver, a channel (`stable`/`beta`),
  a changelog, a hash, a signature. Never mutated after publish; only *yanked*.
- **Profile** — a user's **local**, named set of installed releases plus a load order. The
  Mod Organizer 2 model. Switching profiles re-numbers containers; it does not re-download.
- **Collection** — a **shareable** profile published to the hub. It is a *list of references*
  (mod + version range + order), not bytes. Installing a collection resolves each reference
  through the normal release pipeline.

"How do we support many different packs, possibly conflicting?" is answered by this split.
Packs stop being artifacts and become manifests. A curated 40-mod campaign overhaul costs the
hub a few kilobytes of JSON, credits every author, updates when its members update, and can be
forked. Conflicting collections cannot collide because they are never installed simultaneously —
a profile is the active one.

### Load order is free

Mount priority is expressed by container filename. The launcher owns the `pakchunk1000_P` and
up namespace, and reordering a profile is *renaming files*. No repacking, no re-download,
instant. Ordering is deterministic and matches what the engine will actually do, so the
launcher's conflict preview is a prediction it cannot get wrong.

### Later: merge instead of shadow

Two mods editing the same weapon tag currently means one loses entirely. But `blam-tag` and
`blam-defs` can parse that tag into fields. If mod A changes magazine size and mod B changes
reload speed, that is a **soft conflict** — resolvable by a three-way merge against the base
tag, emitting a synthesized container at install time.

Nobody else in this space can do that, because nobody else has a tag parser. Phase 4, but design
the release schema now so a merged container has somewhere to live (it is a local artifact,
attributed to the profile, never uploaded).

---

## 4. The artifact format

A `.mjolnir` file is a zip:

```
mjolnir.json          manifest (schema_version, id, version, type, compat, deps, entrypoints)
content/              *.utoc / *.ucas pairs
docs/README.md        rendered on the mod page
LICENSE
```

`mjolnir.json` carries:

- `schema_version` — so the launcher can refuse futures it does not understand
- `type` — `content` | `script` | `native`
- `compat` — `{ min_build, max_build, verified_builds[] }`
- `deps` — mod slug + semver range
- `provides` / `replaces` — optional soft grouping for variants (e.g. three resolutions of one
  texture pack, mutually exclusive by construction)

### Game build compatibility is not optional

Chunk IDs are **per-build**. HCE ships patches. When the game updates, a container built against
`2026.06.26.1097863.1` may target a chunk ID that has moved or vanished — and the failure mode is
not a clean error, it is a wrong asset or a crash.

The launcher must record the installed build, compare it against `compat`, and refuse to mount
mods that have not been verified against it. The hub should track build compatibility as a
first-class field with community "works for me" signals per build, and mass-flag mods as
`needs-revalidation` the day a patch lands. Getting this wrong turns every game update into a
wave of "the launcher broke my game" reports.

Content is not the only thing a patch invalidates. UE4SS finds engine internals by AOB scan, and
those patterns are per-build too. On 2026-08-01 a game update moved the binary layout and one
signature stopped resolving; UE4SS retried 1476 times and then killed the process. The failure
mode is a hard crash with the reason buried in `ue4ss/UE4SS.log`, which no user will read.

The mitigation is a discipline, documented in
[`signatures/README.md`](https://github.com/devnull9090/mjolnir-core/blob/main/signatures/README.md):
never bake a RIP-relative displacement or a TLS slot index into a pattern — wildcard it and
decode it at runtime, so the instruction *shape* is the anchor rather than build-specific
offsets. Every signature that followed that rule survived the update; the one that did not was
the one that broke. Worth surfacing "UE4SS failed to inject" as a first-class launcher state
rather than leaving it to the log.

### Ship deltas, not assets

A `_P` container derived from a base-game tag contains Halo asset data. Redistributing that is a
DMCA surface, and it is also wasteful — a 4 KB field edit should not ship as a 40 MB container.

Prefer **deltas against the user's own installed base chunk**: the archive carries a patch, the
launcher reads the base chunk from the game the user already owns, applies it, and packs the
result locally. Smaller downloads, and the hub is distributing a diff rather than Microsoft's
art. Wholly original content (new textures, new models) ships whole, as it should.

This constrains the packer — it needs an "apply patch to base chunk, then pack" path — so it
belongs in the design now rather than as a retrofit.

### Signing *(live)*

CI signs each release manifest with an Ed25519 key; the launcher pins the public key
(`keys/mod-signing.pub`, compiled into the binary) and refuses to install from a manifest whose
signature is missing or does not verify. This means a compromised R2 bucket cannot ship a
malicious payload, which matters more once the launcher installs things automatically.

That claim was false for most of the bucket until 2026-08-01. The code-mod manifest was signed,
but the modpack's was not — so the largest and most privileged artifact we shipped, a DLL
injected into the game process, was the *least* verified thing in the pipeline. It was also
manually assembled and uploaded, with no CI provenance at all. The runtime bundle that replaced
it is signed with the same key and checked by the same code
([`hub::verify_signature`](../apps/launcher/src-tauri/src/hub.rs)).

Two rules the signing story depends on, both learned the hard way:

- **Sign the manifest, not just the files.** The manifest names the hashes everything else is
  checked against, so per-file hashes in an unsigned manifest attest to nothing — whoever
  controls the bucket controls both.
- **Never publish only to `latest/`.** The modpack did, so each upload destroyed its
  predecessor. When a game update broke an AOB signature, the last UE4SS build known to work was
  recoverable only because a copy still happened to be in the bucket. Every release now writes a
  versioned path first, and upstream inputs are vendored into `runtime/vendor/` under immutable
  keys rather than fetched from a tag that moves.

---

## 5. Upload pipeline

Workers cap request bodies well below mod sizes, so bytes must never transit the Worker.

```
1. POST /v1/mods/{slug}/releases        → 201 { release_id, upload: { presigned multipart } }
2. Client PUTs parts directly to R2     (never touches the Worker)
3. POST /v1/releases/{id}/complete      → Worker finalizes, verifies size + sha256, enqueues
4. Cloudflare Queue → scan consumer     → parses, checks, publishes or rejects
5. GET  /v1/releases/{id}               → status: pending | published | rejected
```

The scanner runs **`ue-iostore` compiled to WASM** inside the Queue consumer. It is pure Rust,
enumerating chunk IDs needs only the TOC header and the chunk-ID array, and Oodle is not
required for that path — so it should compile clean. Reusing the exact parser the launcher and
CLI use means the hub's verdict and the game's behaviour cannot disagree.

The scanner checks: zip structure and decompressed-size ratio (zip-bomb guard); no path
traversal; **no executable bytes in a `content` release** (this is what keeps T0 open); TOC
parses; chunk IDs extracted and written to `release_chunks`; manifest validates; declared
compat plausible.

Screenshots take a parallel path — direct to R2, then re-encoded server-side to strip EXIF and
guarantee the bytes really are the image type claimed. Serve all user media from a **separate
origin** (`media.mjolnircore.com`) so a file that lies about its content type cannot execute
against a hub session.

---

## 6. Data model

**Done.** `schema.sql` is gone, replaced by numbered, forward-only `wrangler d1 migrations` in
[`hub/migrations/`](../hub/migrations) — through `0006_device_scopes.sql` at the time of
writing. Apply them with `pnpm db:migrate` locally, `pnpm db:migrate:prod` against the deployed
database.

New and changed tables, abbreviated. The migrations are the authority; this is the shape they
were aiming at:

| Table | Purpose | Notes |
|---|---|---|
| `users` | Discord OAuth identity | + `banned_at`, `trust_level` |
| `api_keys` | Third-party tool auth | store hash only, scopes, `expires_at` |
| `mods` | Mod identity + page | + `type`, `license`, `status`, `nsfw` |
| `mod_authors` | Co-authorship | `(mod_id, user_id, role)` |
| `mod_releases` | Immutable versions | + `sha256`, `signature`, `channel`, `build_min/max`, `yanked_at` |
| `release_artifacts` | Files within a release | `kind`, `path`, `sha256` |
| **`release_chunks`** | **`(release_id, chunk_id BLOB(12))`** | **the conflict index** |
| `release_deps` | Dependencies | slug + semver range |
| `media` | Screenshots | `alt_text NOT NULL`, `position`, dimensions |
| `ratings` | 1–5, one per user per mod | `UNIQUE(mod_id, user_id)` |
| `comments` | Threaded discussion | `parent_id`, `deleted_at`, markdown source |
| `reports` | User flags | feeds the moderation queue |
| `collections` / `collection_items` | Shareable profiles | references, not bytes |
| `release_scans` | Automated verdicts | findings JSON, for appeals |
| `audit_log` | Moderator actions | append-only |

Two details worth fixing now rather than later:

- **Rank by Wilson lower bound, not mean.** A single 5★ must not outrank two hundred 4.8★
  ratings. Store the raw scores, compute the bound in a rollup.
- **Download counts belong in Analytics Engine, not D1.** A counter row per download will
  contend badly. Write events to Analytics Engine, roll up into D1 hourly.

---

## 7. The public API

"Fully open" should mean: unauthenticated reads, CORS `*`, cursor pagination, stable versioned
paths, and a spec that cannot drift from the implementation.

### Spec-first, generated from code

Hand-written OpenAPI rots within two sprints. Mount the API as a **Hono app under a Next.js
catch-all** (`hub/src/app/api/v1/[[...route]]/route.ts`) using `@hono/zod-openapi`. One Zod
schema per payload gives you request validation, response types, and the OpenAPI 3.1 document
from the same source. Hono runs natively on Workers, which OpenNext already targets.

- `GET /api/v1/openapi.json` — the generated spec, also checked in at `hub/public/openapi.json`
- [`/docs/api`](https://mjolnircore.com/docs/api) — Scalar rendering it
- CI: `pnpm openapi:check` regenerates and `git diff --exit-code`s, so an API change that skips
  the export fails the build

### Surface

**Shipped**, and the spec above is the authority — this table is a map, not a contract. `auth`
means an API key or a session cookie; everything else is public and CORS-open.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/v1/health` | |
| `GET` | `/v1/mods` | list, filter, search, cursor paginate |
| `GET` | `/v1/mods/{slug}` | |
| `GET` | `/v1/mods/{slug}/releases` | newest first |
| `GET` | `/v1/releases/{id}` | status and scan findings |
| `GET` | `/v1/releases/{id}/download` | 302 to R2, counts the download |
| `GET` | `/v1/releases/{id}/conflicts` | ← the chunk-ID join |
| `POST` | `/v1/conflicts/check` | body: `[release_ids]` → conflict matrix + suggested order |
| `GET` | `/v1/mods/{slug}/media` · `/comments` · `/ratings` | |
| `GET` | `/v1/media/{id}` | serves the image |
| `POST` | `/v1/mods` | auth — create a mod |
| `POST` | `/v1/mods/{slug}/releases` | auth — create a pending release |
| `PUT` | `/v1/releases/{id}/archive` | auth — upload the `.mjolnir` |
| `POST` | `/v1/releases/{id}/complete` | auth — scan, then publish or reject |
| `POST` `DELETE` | `/v1/mods/{slug}/media` · `/v1/media/{id}` | auth — `alt_text` required |
| `PUT` | `/v1/mods/{slug}/ratings/me` | auth |
| `POST` `DELETE` | `/v1/mods/{slug}/comments` · `/v1/comments/{id}` | auth |
| `POST` | `/v1/reports` | auth |
| `GET` | `/v1/releases/{id}/changes` | declared change list + measured chunk count |
| `GET` `POST` | `/v1/moderation/reports`, `/v1/moderation/reports/{id}` | moderators |
| `GET` `POST` | `/v1/moderation/mods`, `/v1/moderation/mods/{slug}` | moderators — hidden-mod queue |
| `POST` | `/v1/releases/{id}/yank` | moderators |
| `GET` `POST` `DELETE` | `/v1/account/api-keys`, `/v1/account/signing-keys` | auth — and `/{id}` to revoke |
| `GET` | `/v1/account/me` | auth |
| `POST` | `/v1/code-mods/sync` | auth — mirrors the signed code-mod set onto hub pages |

Upload is a **direct `PUT` of the archive** rather than the presigned R2 URL this section
originally called for. The Worker has to hold the bytes anyway to scan them, and a 50 MB cap
(`MAX_ARCHIVE_BYTES`) keeps that affordable; presigning becomes worth it when archives outgrow
that, and the three-step create → upload → complete shape is already the one that would survive
the change.

**Not built:** `GET /v1/collections/{slug}` (Phase 4) and `GET /v1/builds`.

`POST /v1/conflicts/check` is the endpoint third-party managers will actually integrate against,
and it is the reason to publish a spec at all. Make it good.

### Auth

- **Humans:** Discord OAuth → short-lived JWT in an `HttpOnly; Secure; SameSite=Lax` cookie.
- **Tools:** API keys, `Authorization: Bearer mjc_...`, hash stored, scoped
  (`mods:read`, `mods:write`, `ratings:write`, `comments:write`), revocable, rate-limited per key.
- **Desktop clients:** device pairing (below), which is just a supervised way of minting one of
  those keys — with the scopes the client asked for, shown to the user before they approve.
- **Public reads:** no auth, IP rate-limited at the Cloudflare edge.

Discord gives role sync for free — a `moderator` role in the guild can map to hub moderation
rights, so there is no second permission system to maintain.

#### Device pairing

Desktop clients have no browser session and must never see a Discord password, so they pair the
way a TV app does:

```
POST /v1/auth/device/start                 { client_name, scopes? } → { device_code, user_code, verification_url, scopes, … }
    ← client shows user_code, opens verification_url in the real browser
POST /v1/auth/device/approve               session-only; mints the key
POST /v1/auth/device/token                 poll; the first post-approval poll carries the key
GET  /v1/auth/device/pending/{user_code}   what the approval page names before you commit
```

Rules that make it safe rather than merely convenient:

- The **device code** is long, never displayed, and stored only as a SHA-256 — like an API key.
  The **user code** is short and stored plainly, because a human types it and it dies in ten
  minutes.
- **Approval requires a cookie session.** A key cannot pair another device, so a stolen key
  cannot mint more keys. This is also why there is no launcher→editor "hand-off": the launcher
  holds a key, and a key cannot mint another one. Each app pairs for itself.
- **A client asks for the scopes it needs.** The launcher rates and comments; the tag editor
  also asks for `mods:write`, because it publishes. Omitting `scopes` yields
  `mods:read ratings:write comments:write` — what pairing granted before scopes were
  requestable, so older launchers keep working. Keys last 180 days, or 90 if they can publish.
- The scopes asked for are recorded at handshake time and are exactly what approval mints, so
  `/link` can list them before the user commits. Granting `mods:write` to a desktop app is a
  real widening over the original design; it is worth it because the flow it replaces was
  pasting a hand-minted key, which produces a broader key with no expiry that also travels
  through the clipboard.
- The key is stored between approval and collection (`device_codes.granted_key`) and the
  delivering poll deletes the row in the same breath, which is what makes delivery exactly-once.
  An approval nobody ever collects has its key revoked by the cleanup pass.
- The only attack this flow has is talking someone into approving a code they did not generate.
  `/link` therefore names the client, lists what it is asking for, and says in as many words to
  deny codes that arrived from someone else — with a sharper warning when publishing is on the
  list, because that is the approval worth being sure about. That warning is part of the design.

Revocation is ordinary: the pairing shows up under *Account → API keys* like any other key.

### One implementation of the community UI

Ratings, reviews, comments, galleries, mod cards and release lists exist once, in
`hub/src/kit`, and both the website and the launcher render them. The package is consumed as
**source** through a bundler alias rather than as a published package, because the two apps have
separate lockfiles and separate CI jobs; see `hub/src/kit/README.md`.

Shared components style against a `--mj-*` variable contract that each app maps onto its own
palette, and the API client takes an injectable transport. That transport is the interesting
part: in the browser it is same-origin `fetch` with the session cookie, and in the launcher it is
a Tauri command that attaches the paired key **in Rust**. The webview never holds a credential.

---

## 8. Phasing

**Phase 0 — Foundations** *(prerequisite for everything)* — **done**
The multi-chunk perfect hash in `ue-iostore` is fixed (§1). `schema.sql` is gone, replaced by
numbered `wrangler d1` migrations. Discord OAuth runs end to end, `/api/v1/mods` is D1-backed,
and the API is a Hono + zod-openapi app whose spec is published at `/api/v1/openapi.json` and
guarded by a CI drift check (`pnpm openapi:check`).

**Phase 1 — Content mods, end to end** — **done**
`.mjolnir` format and manifest schema ([the spec](mjolnir_format.md)). R2 upload + a scanner
that populates `release_chunks` and `release_scans`. Mod pages with screenshots (alt text
required), ratings, threaded comments. The launcher installs per mod, keeps profiles, and drives
load order from real chunk-ID conflicts.

One deviation from the plan above, deliberate and marked in the code: the scanner is TypeScript
running **synchronously inside `POST /releases/{id}/complete`**, not a Queue consumer with
`ue-iostore` on WASM. It reads the chunk IDs straight out of the `.utoc` header, which needs no
decompression, so the Rust reader is not required to do the job. The contract a Queue consumer
would keep — findings to `release_scans`, chunks to `release_chunks` — is already what it writes,
so moving it later is a change of host, not of design.

**Phase 2 — The open API** — **done**
API keys and scopes, `POST /v1/conflicts/check`, the spec rendered at `/docs/api`, rate limiting,
CORS, cursor pagination, and the moderation queue with reports and an audit log. Still missing
from this phase: the "worked integration example" alongside the spec.

Publishing stays unmoderated, and reporting is the brake that makes that safe: once three
distinct accounts hold open reports against one mod (or its releases), it is automatically
hidden — delisted, page 404s, downloads stop — until a moderator restores or removes it from
the hidden-mod queue. The flip is audit-logged as `mod_auto_hidden`. Transparency is the other
half of the same bargain: every release carries its declared change list (`changes.json`,
`mjolnir_format.md`), stored at scan time and rendered on the mod page and in the launcher as
"what this mod does", beside the chunk count measured from the containers themselves.

**Phase 2.5 — The launcher as a first-class client** *(done)*
The launcher browses the hub with every filter the API offers (search, category, type, sort,
cursor pages), shows a mod's real page inside the app — screenshots, description, releases,
ratings, reviews, comments — and installs, updates, enables, disables or removes any of it per
profile. Version updates are a hub query per installed mod, not a guess from a cached listing.
Integrity is checked twice: the archive hash at download, and a re-hash of every cached container
against what was recorded at install. Any release signature that is present must verify against
the pinned key or the install is refused. Device pairing gives the launcher an identity, so
rating and commenting work from the desktop.

**Phase 3 — Code mods** *(done)*
`mods/` restructured for community contribution: contributor guide, PR template, a CI job that
builds and signs Lua and native mods into per-mod release artifacts, and a launcher path that
installs only hash-matched signed builds. Publish the review criteria so the bar is legible.

The launcher's "signed" badge is a claim about bytes, not about a directory name: it records a
digest of each mod's file tree at install and re-checks it, so a folder carrying a signed mod's
name but different contents reads as `modified` rather than `signed`. The runtime that hosts
these mods was split out and signed at the same time (§4, Signing).

Still open from this phase: the review criteria are not published, and §9's second open question
— who reviews — is unanswered.

**Phase 4 — The differentiators**
Collections. Delta/patch content mods against the user's own install. Field-level tag merging
for soft conflicts. Per-build compatibility signals and automatic revalidation on game patches.

---

## 9. Open questions

1. **Does the game mount extra containers by priority on the current build?** `iostore_packaging.md`
   lists this as verified for a single `_P` container. Ordering *between* several `_P` containers
   is the assumption load order rests on, and it should be tested with three deliberately
   conflicting containers before Phase 1 UI is built.
2. **Where does moderation capacity come from?** Every code mod needs a human reviewer. One
   person is a bottleneck and a bus factor; the process should name at least two from the start.
3. **What is the policy on mods that redistribute base-game assets wholesale?** The delta
   approach reduces the surface but does not remove it, and the answer should be written down
   before the first takedown request rather than after.
