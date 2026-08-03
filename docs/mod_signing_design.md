# Mod Signing and Attribution: Design

**Status:** shipped. Tag editor 0.3.0 signs; launcher 0.5.3 verifies; hub migration
0005 carries the key registry and per-release attribution. Rollout step 2
(`REQUIRE_SIGNED_UPLOADS`) is not switched on yet.

Who bundled a `.mjolnir`, and how does anyone downstream know its bytes are the bytes
they bundled? Today the answer is "the hub says so": the archive hash is pinned by the
hub's scan record, the download is checked against it, and ownership is a row in a
database. That is integrity against corruption, not authenticity — and it all rests on
trusting the hub. This design adds author signatures so the claim "user U published
these exact bytes as mod S version V" is checkable by anyone holding the archive,
including when the hub itself is the thing you doubt.

## Three different problems, named

1. **Integrity** — did the bytes change between publish and install? *Solved today* for
   the honest-hub case: sha256 recorded at scan, verified at download, containers
   re-hashed on disk by `verify_installed`.
2. **Attribution** — which account bundled release 1.2.0? *Not recorded today.* Only
   `mods.owner_id` exists; if a mod changes hands or an API key leaks, nothing says who
   uploaded which release.
3. **Authenticity** — can the claim in (2) be proven without trusting the hub, and can
   tampering by anyone — including the hub — be detected? *Does not exist today* for
   community mods. `mod_releases.signature` is platform-CI-only (script/native mods),
   verified against one pinned key compiled into the launcher.

Attribution is a database column and lands unconditionally. Authenticity is the rest of
this document.

## What signing does and does not buy

| Threat | Countered by |
|---|---|
| Corruption in transit / storage | sha256 pinning (already shipped) |
| Third party republishes a modified copy | signature: digests don't match, or their key isn't the author's |
| Author's old archive re-uploaded under another slug/version | statement binds slug + version; mismatch rejects |
| Hub (or R2, or a CDN) silently swaps bytes post-publish | signature verifies against the *author's* key, which the hub does not hold |
| Hub silently substitutes the author's key | detectable: launcher pins the fingerprint at first install and warns on change |
| Stolen `mods:write` API key | **not countered** — that key *is* the publish credential; recovery is revoking it and any unrecognized signing keys on the account page |
| Malicious author signing malicious content | **not countered** — a signature proves *who*, never *safe*; the scanner and moderation remain the safety layer |

The last two rows are stated because they are the two things signing is most often
imagined to solve and does not.

## The format

A signed archive carries one extra member at the root: `signature.json`. Everything
else about `.mjolnir` is unchanged, and unsigned archives remain valid during the
transition (see Rollout).

### Envelope

```json
{
  "schema_version": 1,
  "payload_type": "mjolnir-mod-statement-v1",
  "payload": "<base64 of the statement bytes, exactly as signed>",
  "public_key": "<base64, raw 32-byte Ed25519 public key>",
  "signature": "<base64, 64-byte Ed25519 signature>"
}
```

The signature covers `"MJOLNIR-MOD-STATEMENT-V1\n" + payload_bytes`. The domain prefix
means a signing key can never be tricked into producing bytes that verify in some other
context (the platform signature, for instance, covers a bare sha256 hex string — an
author signature must never be confusable with one). Signing the encoded payload bytes
verbatim, rather than "the JSON", removes canonicalization from the problem: the signer
serializes once, and the verifier checks exactly those bytes before parsing them.

### Statement (the decoded payload)

```json
{
  "schema_version": 1,
  "slug": "faster-pistol",
  "version": "1.2.0",
  "author": { "id": "<hub user id>", "username": "devnull9090" },
  "key_fingerprint": "<lowercase hex sha256 of the raw public key>",
  "signed_at": "2026-08-02T21:40:00Z",
  "files": {
    "mjolnir.json": "<sha256 hex>",
    "content/faster-pistol_P.utoc": "<sha256 hex>",
    "content/faster-pistol_P.ucas": "<sha256 hex>",
    "docs/README.md": "<sha256 hex>"
  }
}
```

Decisions worth recording:

- **Members are digested, not the zip.** Zip bytes vary with compression level, entry
  order and library version; signing contents means a re-zip (by a mirror, or the hub)
  cannot break a valid signature, while any change to any member is caught and named.
  The whole-zip sha256 the hub records remains the *transport* pin; this is the
  *authorship* pin. They are complementary.
- **Set equality, not subset.** The verifier requires the archive's member set (minus
  `signature.json` itself) to exactly equal `files`. Otherwise an attacker appends a
  member and the signature still "verifies". Duplicate member paths in the zip are
  rejected outright — extractors disagree about them, which is exactly the ambiguity an
  attacker wants.
- **The fingerprint is inside the signed payload.** The envelope's `public_key` is
  what's cryptographically checked, but the payload binds which key the author *meant*,
  so swapping the envelope key for another one that happens to verify is impossible
  (verify first, then require `fingerprint(public_key) == payload.key_fingerprint`).
- **`author` may be null.** Signing works fully offline — export signs even with no hub
  account configured. When the editor knows the account (it has an API key), it embeds
  the identity so the archive is self-describing; the hub independently enforces the
  key→account binding either way.
- **`signed_at` is informational.** There is no trusted timestamp; nothing may depend
  on it.
- **`slug` + `version` bind the context.** A signed archive cannot be replayed as a
  different mod or a different version: the hub checks both against the release being
  published, and the launcher checks both against the release it asked for.

### Verification algorithm (identical semantics in TS and Rust)

1. Parse the envelope; base64-decode payload, public_key (must be 32 bytes),
   signature (must be 64 bytes) — strict decoding, no whitespace forgiveness.
2. Ed25519 `verify_strict` of `prefix || payload_bytes` against `public_key`.
   Crypto first, parsing after: never parse unauthenticated bytes into business logic.
3. Parse the payload; require `schema_version == 1`.
4. Require `fingerprint(public_key) == key_fingerprint`.
5. Require `slug` and `version` to match the expected release.
6. Require member-set equality and per-member sha256 equality.
7. *(Hub only)* Require the fingerprint to belong to a registered, unrevoked key of
   the **authenticated uploader**, and `author.id` (when present) to equal the
   uploader's id. The archive says who signed; the registry says whose key that is;
   the session says who is uploading. All three must agree.

One shared Rust implementation (`crates/mjolnir-sign`) serves the tag editor, the
launcher and the CLI; the hub mirrors it in a self-contained `signing.ts` (Workers
WebCrypto, importing the raw key by wrapping it in the fixed 12-byte SPKI prefix, the
same import path `codesync.ts` already uses).

## Keys

**One key per device, generated where it is used, never exported.** The tag editor
generates an Ed25519 key on first use and stores the seed via Windows DPAPI
(`CryptProtectData`, user scope) in the MJOLNIR config directory. A copied blob is
useless on another machine or account, which removes the entire "user mishandles a key
file" class. There is deliberately no export: a second machine gets its *own* key,
registered alongside the first — the same model as SSH keys on GitHub, and the reason
that model works is that private keys never travel.

**Registry.** `user_keys` on the hub: id, user, raw public key, fingerprint (unique),
label (defaults to the machine name), created / last-used / revoked timestamps.
Registration happens through the editor using the already-configured `mods:write` API
key; the account page lists every key with its label and dates, and revocation is one
click there. Tradeoff, stated: a stolen `mods:write` key could register a signing key.
It could also simply publish, so this does not widen the blast radius — but the key
list's visibility is the recovery path either way. A browser-approval registration flow
(like device pairing) is the future hardening if it ever matters.

**Revocation.** A revoked key fails registration checks for *future* uploads. Already-
published releases keep their at-publish verification; the API exposes the key's
current state so clients can tell "signed, key since revoked" from "signed, key good",
and the launcher warns on the former at install time. History is not rewritten by a
revocation — that is what yanking a release is for.

**Fingerprint** = lowercase hex sha256 of the raw 32-byte public key. Shown truncated
to 16 chars in UIs, stored and compared in full.

## Hub enforcement

- **Migration 0005**: `user_keys` as above; `mod_releases` gains `published_by`
  (set from the authenticated user at *release creation* — this is the attribution
  column and applies to every release, signed or not) and `signing_key_id` (set at
  `/complete` when a signature verifies).
- **`/complete`** (where the async work fits, since `scanArchive` is sync and stays
  untouched): after the scan passes, if `signature.json` is present, run the
  verification algorithm. New finding codes:
  - `bad_signature` (error) — structurally or cryptographically invalid, digest
    mismatch, slug/version mismatch: the archive is not what its signature claims.
  - `foreign_signature` (error) — cryptographically valid but the key is not a
    registered, unrevoked key of the uploader, or `author.id` names someone else.
    Valid crypto with the wrong identity is worse than no signature; it never
    downgrades to a warning.
  - `unsigned` (warning) — no `signature.json`. Becomes an error when the
    `REQUIRE_SIGNED_UPLOADS` environment flag is set, which is the whole rollout
    switch.
- **API**: `GET /account/me` (the editor needs its own identity for the statement);
  `GET/POST/DELETE /account/signing-keys`; `ReleaseStatus` gains `published_by`,
  `signer_fingerprint`, `signer_key_revoked` (all optional — additive, non-breaking).
  Spec-first as always; `openapi.json` regenerates or CI fails the drift check.
- **UI**: the account keys page gains a signing-keys section; release rows on mod
  pages show "published by U · signed <fingerprint>" or an unsigned badge.

## Launcher behavior

At install, after the existing hash check and before anything is materialized:

- `signature.json` present → verify with `mjolnir-sign` against the slug and version
  the launcher asked for. **Present-and-invalid refuses the install**, same philosophy
  as the platform signature today: a wrong signature is impersonation evidence, not an
  inconvenience.
- Valid → record `signer_fingerprint` and `published_by` in `InstalledHubMod`
  (serde-defaulted, so existing state files load).
- **Pin on first use.** On update, a fingerprint different from the recorded one
  produces a loud warning — not a refusal, because an author with a second machine is
  legitimate and common. The warning distinguishes "new key, same registered author
  per the hub" (soft: verify on the mod page if surprised) from "key registered to a
  different account" (hard refuse). Under an honest hub the soft case is the multi-
  device author; under a compromised hub the pin is what turns silent substitution
  into something every updating installer notices. Detectability is the goal; the pin
  cannot *prevent* what it detects.
- **Downgrade warning.** A previously-signed mod arriving unsigned warns — quiet
  disappearance of a signature is exactly what tampering looks like.
- Unsigned (never signed) → installs normally during the transition, recorded as
  unsigned.

## Tag editor behavior

- First export or publish generates the device key (silently — there is nothing to
  ask; a key with no registration has no authority) and signs every archive from then
  on. Signing is local and needs no account.
- Publish auto-registers the key when an API key is configured and the fingerprint is
  not yet on the account, and embeds `author` from `/account/me` (cached). The publish
  panel shows the device key line: fingerprint, registered-or-not, and the label it
  registered under.
- The panel links to the account page for revocation; the editor itself never deletes
  keys.

## Rollout

1. Everything above ships dark: attribution recorded on every new release,
   signatures verified when present, `unsigned` a warning. Existing releases are
   untouched (their `published_by` stays null — honest "predates attribution").
2. Once the editor release with signing is the one people actually have,
   set `REQUIRE_SIGNED_UPLOADS` — new publishes must be signed. No flag day for
   existing content.
3. Deferred, deliberately:
   - **Transparency log** — an append-only public log of publish statements is the
     real endgame against hub compromise; the signed statement designed here is
     exactly what such a log records, so nothing about this design blocks it.
   - **CLI signing** — `mjolnir-sign` is CLI-ready, but key storage there means
     DPAPI-less key files; not worth the footgun until someone needs it.
   - **Browser-approved key registration** — hardening if API-key theft ever proves
     to be a real pattern.

## The elephant, acknowledged

A signature is non-repudiation, and today's archives contain game-derived bytes: this
design creates cryptographic proof that a named person distributed them. That is worth
being conscious of, and it is one more reason the Phase-4 direction matters — when the
hub ships *recipes* (`edits.json`, no game data), the author signs purely their own
work. The format here carries over unchanged: `files` digests whatever the archive
holds, whether that is baked containers today or a bare recipe later.
