-- Author signing keys and per-release attribution.
-- Design: docs/mod_signing_design.md.

-- One key per device, generated where it is used, registered here. The hub
-- never sees a private key; this table is the binding from "this Ed25519 key"
-- to "this account", which is what turns a valid signature into an identity.
CREATE TABLE user_keys (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  -- Raw 32-byte Ed25519 public key, base64.
  public_key TEXT NOT NULL,
  -- Lowercase hex sha256 of the raw key bytes. Globally unique: a key
  -- belongs to exactly one account, ever.
  fingerprint TEXT UNIQUE NOT NULL,
  -- Defaults to the machine name; for telling a desktop from a laptop.
  label TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at TEXT,
  -- Revocation stops future uploads with this key; it does not rewrite the
  -- history of releases it already signed (yanking is for that).
  revoked_at TEXT
);
CREATE INDEX idx_user_keys_user ON user_keys(user_id);

-- Attribution: which account created each release. Set at release creation
-- for every release from now on, signed or not; existing rows stay NULL,
-- which reads honestly as "predates attribution".
ALTER TABLE mod_releases ADD COLUMN published_by TEXT REFERENCES users(id);
-- The registered key whose signature verified at /complete, when one did.
ALTER TABLE mod_releases ADD COLUMN signing_key_id TEXT REFERENCES user_keys(id);
