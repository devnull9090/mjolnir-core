-- A Forge pack remains content in the trust model. Its immutable inventory
-- belongs to the scanned release, so installing an old version gets its own
-- block identities and dimensions rather than the latest listing's.
ALTER TABLE mod_releases ADD COLUMN forge_pack_json TEXT;
