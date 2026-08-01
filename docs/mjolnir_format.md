# The `.mjolnir` Release Archive

**Status:** v1, enforced by the hub's upload scanner (`hub/src/lib/api/scan.ts`).

A `.mjolnir` file is a plain zip with a manifest at the root and IoStore
override containers under `content/`:

```
mjolnir.json          the manifest (schema below)
content/
  MyMod_P.utoc        override container index
  MyMod_P.ucas        override container data
docs/README.md        optional; rendered on the mod page
LICENSE               optional
```

Only **content** releases travel this path — inert data the engine parses.
Anything executable (Lua, DLLs, scripts of any kind) is rejected by the
scanner; those mods ship from the mjolnir-core repository's reviewed and
signed CI releases instead (`docs/hub_architecture.md` §2).

## mjolnir.json

```json
{
  "schema_version": 1,
  "name": "My Texture Pack",
  "version": "1.0.0",
  "type": "content",
  "summary": "Optional one-liner shown on cards.",
  "compat": { "min_build": "2026.06.26.1097863.1" },
  "deps": [{ "slug": "some-framework-mod", "range": ">=2.0.0" }]
}
```

- `version` must equal the version of the hub release it is uploaded to;
  the scanner rejects a mismatch.
- `compat` declares the game builds the release was made against. Chunk IDs
  are per-build, so a container built against one build may point at moved
  or vanished chunks after a game patch.

## What the scanner checks

| Check | Failure |
|---|---|
| Valid zip, decompressed total ≤ 256 MiB | `bad_zip` |
| No `..`, absolute, or drive-letter paths | `path_traversal` |
| `mjolnir.json` present and valid | `no_manifest`, `bad_manifest` |
| Manifest version matches the release | `version_mismatch` |
| Only allowed file kinds (`utoc ucas json md txt png jpg jpeg webp`) | `forbidden_file` |
| Every `.utoc` parses, unencrypted, paired with its `.ucas` | `bad_container`, `encrypted_container`, `orphan_utoc`, `orphan_ucas` |
| At least one container under `content/` | `no_content` |

On a passing scan the hub records every chunk ID the containers claim into
the **conflict index** (`release_chunks`), and the release — plus its mod, if
this was the first release — goes live. On a failing scan the findings are
stored and returned; fix the archive and re-upload to the same release.

## Publishing flow

```
POST /api/v1/mods                          {"slug":"my-pack","name":"My Pack", ...}
POST /api/v1/mods/my-pack/releases         {"version":"1.0.0"}
PUT  /api/v1/releases/{id}/archive         <raw .mjolnir bytes>   (≤ 50 MiB)
POST /api/v1/releases/{id}/complete        → published | rejected + findings
```

All four need a signed-in session (Discord OAuth). Third-party tools can
watch `GET /api/v1/releases/{id}` for status and query
`POST /api/v1/conflicts/check` before installing a set of releases together.

## Building a container

`mjolnir pack` (crates/blam-cli) composes an override container from edited
tags; `docs/iostore_packaging.md` documents the format. Since the
perfect-hash fix (2026-08-01) containers may hold any number of chunks.
