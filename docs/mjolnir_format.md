# The `.mjolnir` Release Archive

**Status:** v1, enforced by the hub's upload scanner (`hub/src/lib/api/scan.ts`).

A `.mjolnir` file is a plain zip with a manifest at the root and IoStore
override containers under `content/`:

```
mjolnir.json          the manifest (schema below)
changes.json          the declared change list (schema below)
signature.json        optional; the author's signature (see below)
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

## changes.json

The transparency file: what the mod does, declared as data, so the hub and
the launcher can show players the actual edits instead of asking them to
trust a description. The tag editor writes it at export from the same
resolved view its Changes panel shows — the recipe's `(group, tag, field)`
keys with the shipped value beside the modded one:

```json
{
  "schema_version": 1,
  "tags": [
    {
      "group": "weapon",
      "tag": "objects/weapons/pistol/pistol",
      "fields": [
        { "field": "magazines[0].rounds loaded maximum", "before": "12", "value": "24" }
      ]
    }
  ],
  "textures": [{ "path": "characters/weapons/assaultrifle/T_ar_default_D", "bytes": 481203 }],
  "scripts": [{ "group": "scenario", "tag": "levels/a10/a10" }]
}
```

It is a **declaration, not a proof**: the containers remain the bytes that
ship. The hub stores the list at scan time and renders it beside the
*measured* chunk count from the containers themselves, so a release
declaring one tweak while overriding hundreds of chunks is visibly odd.
Absent is a warning (`no_changes` — older editors predate the format);
present-and-invalid is an error (`bad_changes`), because the file is
machine-written and a broken one means tampering or a bug.

## signature.json

An archive may carry an author signature: an envelope whose base64 `payload`
is a statement naming the mod's slug, version, author, signing-key
fingerprint, and the sha256 of **every other member** of the archive, signed
Ed25519 over `"MJOLNIR-MOD-STATEMENT-V1\n" + payload` with a per-device key
registered to the author's hub account. The verifier requires the archive's
member set to exactly equal the statement's — nothing added, nothing removed,
nothing changed — so anyone holding the archive can prove who bundled exactly
these bytes, without asking the hub.

The tag editor writes this automatically. The hub verifies it at upload
(`unsigned` is a warning today, an error once signing is required;
`bad_signature` and `foreign_signature` are always errors), and the launcher
verifies it again at install, refusing an archive whose signature is present
and wrong. Full design, threat model and rollout:
[`mod_signing_design.md`](mod_signing_design.md).

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
| `changes.json`, when present, valid and ≤ 512 KiB | `bad_changes` (absent is the `no_changes` warning) |

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
