//! Author signatures for `.mjolnir` archives.
//!
//! A signed archive carries a `signature.json` at its root: an envelope
//! holding a base64 statement (slug, version, author, per-member sha256
//! digests) and an Ed25519 signature over those exact payload bytes, domain-
//! prefixed so a mod-statement signature can never verify in any other
//! context. The full design, including what this does and does not defend
//! against, is `docs/mod_signing_design.md`.
//!
//! This crate is the one Rust implementation of both sides — the tag editor
//! signs with it, the launcher and CLI verify with it — and the hub mirrors
//! the same algorithm in TypeScript. Verification order is deliberate:
//! crypto first, parsing second, business checks last. Unauthenticated bytes
//! are never parsed into decisions.

use std::collections::BTreeMap;

use base64::Engine;
use ed25519_dalek::{Signer as _, SigningKey, Verifier as _, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// The archive member the envelope lives in. Excluded from `files` digests.
pub const SIGNATURE_MEMBER: &str = "signature.json";

pub const PAYLOAD_TYPE: &str = "mjolnir-mod-statement-v1";

/// Domain separation: the signature covers this prefix plus the payload
/// bytes, so a signing key cannot be tricked into producing bytes that mean
/// something in another protocol (the platform release signature, for one,
/// covers a bare sha256 hex string).
const DOMAIN_PREFIX: &[u8] = b"MJOLNIR-MOD-STATEMENT-V1\n";

#[derive(Clone, Serialize, Deserialize, PartialEq, Debug)]
pub struct Author {
    pub id: String,
    pub username: String,
}

/// The signed claim: this author, this key, published exactly these bytes as
/// this mod at this version.
#[derive(Debug, Serialize, Deserialize)]
pub struct Statement {
    pub schema_version: u32,
    pub slug: String,
    pub version: String,
    /// Absent when the archive was signed offline; the hub binds the key to
    /// an account through its registry either way.
    pub author: Option<Author>,
    /// Fingerprint of the signing key, inside the signed bytes so the
    /// envelope's key cannot be substituted.
    pub key_fingerprint: String,
    /// Informational; there is no trusted clock.
    pub signed_at: String,
    /// Member path → lowercase hex sha256. A BTreeMap so serialization is
    /// deterministic.
    pub files: BTreeMap<String, String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Envelope {
    pub schema_version: u32,
    pub payload_type: String,
    /// Base64 of the statement bytes, exactly as signed.
    pub payload: String,
    /// Base64 raw 32-byte Ed25519 public key.
    pub public_key: String,
    /// Base64 64-byte Ed25519 signature over prefix + payload bytes.
    pub signature: String,
}

/// Lowercase hex sha256 of the raw public key. Shown truncated in UIs,
/// stored and compared in full.
pub fn fingerprint(public_key: &[u8; 32]) -> String {
    hex::encode(Sha256::digest(public_key))
}

fn sha256_hex(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn b64(bytes: &[u8]) -> String {
    base64::engine::general_purpose::STANDARD.encode(bytes)
}

fn unb64(text: &str, what: &str) -> Result<Vec<u8>, String> {
    base64::engine::general_purpose::STANDARD
        .decode(text.trim())
        .map_err(|_| format!("signature envelope: {what} is not valid base64"))
}

/// Digest archive members into the `files` map, rejecting duplicates —
/// extractors disagree about duplicate zip paths, which is exactly the
/// ambiguity an attacker wants.
fn digest_members(members: &[(String, &[u8])]) -> Result<BTreeMap<String, String>, String> {
    let mut files = BTreeMap::new();
    for (path, bytes) in members {
        if path == SIGNATURE_MEMBER {
            continue;
        }
        if files.insert(path.clone(), sha256_hex(bytes)).is_some() {
            return Err(format!("duplicate archive member {path:?}"));
        }
    }
    Ok(files)
}

/// A signing identity, built from a 32-byte seed the caller keeps safe.
pub struct SigningIdentity {
    key: SigningKey,
}

impl SigningIdentity {
    pub fn from_seed(seed: &[u8; 32]) -> SigningIdentity {
        SigningIdentity {
            key: SigningKey::from_bytes(seed),
        }
    }

    pub fn public_key(&self) -> [u8; 32] {
        self.key.verifying_key().to_bytes()
    }

    pub fn fingerprint(&self) -> String {
        fingerprint(&self.public_key())
    }

    /// Sign archive members into an envelope, returned as pretty JSON ready
    /// to be written as the `signature.json` member.
    pub fn sign_members(
        &self,
        slug: &str,
        version: &str,
        author: Option<Author>,
        signed_at: &str,
        members: &[(String, &[u8])],
    ) -> Result<String, String> {
        let statement = Statement {
            schema_version: 1,
            slug: slug.to_string(),
            version: version.to_string(),
            author,
            key_fingerprint: self.fingerprint(),
            signed_at: signed_at.to_string(),
            files: digest_members(members)?,
        };
        let payload = serde_json::to_vec(&statement).map_err(|e| e.to_string())?;
        let mut message = DOMAIN_PREFIX.to_vec();
        message.extend_from_slice(&payload);
        let signature = self.key.sign(&message);
        let envelope = Envelope {
            schema_version: 1,
            payload_type: PAYLOAD_TYPE.to_string(),
            payload: b64(&payload),
            public_key: b64(&self.public_key()),
            signature: b64(&signature.to_bytes()),
        };
        serde_json::to_string_pretty(&envelope).map_err(|e| e.to_string())
    }
}

/// A verified signature: the statement, plus the fingerprint of the key that
/// actually verified it. Callers bind the fingerprint to an identity through
/// the hub's key registry; this crate proves only "this key signed exactly
/// these bytes".
#[derive(Debug)]
pub struct Verified {
    pub statement: Statement,
    pub fingerprint: String,
}

/// Verify an envelope against archive members and the release it is expected
/// to describe. See the design doc for the algorithm; the order here is the
/// contract.
pub fn verify_members(
    envelope_json: &[u8],
    expected_slug: &str,
    expected_version: &str,
    members: &[(String, &[u8])],
) -> Result<Verified, String> {
    let envelope: Envelope = serde_json::from_slice(envelope_json)
        .map_err(|_| "signature envelope does not parse".to_string())?;
    if envelope.schema_version != 1 || envelope.payload_type != PAYLOAD_TYPE {
        return Err(format!(
            "unsupported signature envelope ({} v{})",
            envelope.payload_type, envelope.schema_version
        ));
    }

    let payload = unb64(&envelope.payload, "payload")?;
    let public_key: [u8; 32] = unb64(&envelope.public_key, "public_key")?
        .try_into()
        .map_err(|_| "signature envelope: public_key is not 32 bytes".to_string())?;
    let signature: [u8; 64] = unb64(&envelope.signature, "signature")?
        .try_into()
        .map_err(|_| "signature envelope: signature is not 64 bytes".to_string())?;

    // Crypto before parsing: nothing downstream sees unauthenticated bytes.
    let verifying = VerifyingKey::from_bytes(&public_key)
        .map_err(|_| "signature envelope: public_key is not a valid Ed25519 key".to_string())?;
    let mut message = DOMAIN_PREFIX.to_vec();
    message.extend_from_slice(&payload);
    verifying
        .verify(&message, &ed25519_dalek::Signature::from_bytes(&signature))
        .map_err(|_| "signature does not verify".to_string())?;

    let statement: Statement = serde_json::from_slice(&payload)
        .map_err(|_| "signed statement does not parse".to_string())?;
    if statement.schema_version != 1 {
        return Err(format!(
            "unsupported statement schema {}",
            statement.schema_version
        ));
    }
    let fp = fingerprint(&public_key);
    if statement.key_fingerprint != fp {
        return Err("statement names a different key than the one that signed it".to_string());
    }
    if statement.slug != expected_slug || statement.version != expected_version {
        return Err(format!(
            "signature is for {} {}, not {} {}",
            statement.slug, statement.version, expected_slug, expected_version
        ));
    }

    let actual = digest_members(members)?;
    for (path, want) in &statement.files {
        match actual.get(path) {
            None => {
                return Err(format!(
                    "signed member {path:?} is missing from the archive"
                ))
            }
            Some(got) if got != want => {
                return Err(format!(
                    "archive member {path:?} does not match its signature"
                ))
            }
            Some(_) => {}
        }
    }
    for path in actual.keys() {
        if !statement.files.contains_key(path) {
            return Err(format!(
                "archive member {path:?} is not covered by the signature"
            ));
        }
    }

    Ok(Verified {
        statement,
        fingerprint: fp,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity() -> SigningIdentity {
        SigningIdentity::from_seed(&[7u8; 32])
    }

    fn members() -> Vec<(String, Vec<u8>)> {
        vec![
            ("mjolnir.json".to_string(), br#"{"name":"x"}"#.to_vec()),
            ("content/x_P.utoc".to_string(), vec![1, 2, 3]),
            ("content/x_P.ucas".to_string(), vec![4, 5, 6]),
        ]
    }

    fn as_refs(m: &[(String, Vec<u8>)]) -> Vec<(String, &[u8])> {
        m.iter().map(|(p, b)| (p.clone(), b.as_slice())).collect()
    }

    fn signed() -> String {
        identity()
            .sign_members(
                "faster-pistol",
                "1.2.0",
                Some(Author {
                    id: "u1".into(),
                    username: "will".into(),
                }),
                "2026-08-02T00:00:00Z",
                &as_refs(&members()),
            )
            .unwrap()
    }

    #[test]
    fn a_signed_archive_verifies_and_names_its_author() {
        let v = verify_members(
            signed().as_bytes(),
            "faster-pistol",
            "1.2.0",
            &as_refs(&members()),
        )
        .unwrap();
        assert_eq!(v.fingerprint, identity().fingerprint());
        assert_eq!(v.statement.author.unwrap().username, "will");
        assert_eq!(v.statement.files.len(), 3);
    }

    #[test]
    fn changing_any_member_byte_fails() {
        let mut m = members();
        m[1].1[0] ^= 0xFF;
        let err = verify_members(signed().as_bytes(), "faster-pistol", "1.2.0", &as_refs(&m))
            .unwrap_err();
        assert!(err.contains("does not match its signature"), "{err}");
    }

    #[test]
    fn adding_a_member_fails_set_equality() {
        let mut m = members();
        m.push(("content/extra_P.pak".to_string(), vec![9]));
        let err = verify_members(signed().as_bytes(), "faster-pistol", "1.2.0", &as_refs(&m))
            .unwrap_err();
        assert!(err.contains("not covered by the signature"), "{err}");
    }

    #[test]
    fn removing_a_member_fails() {
        let mut m = members();
        m.pop();
        let err = verify_members(signed().as_bytes(), "faster-pistol", "1.2.0", &as_refs(&m))
            .unwrap_err();
        assert!(err.contains("missing from the archive"), "{err}");
    }

    #[test]
    fn the_signature_member_itself_is_ignored_in_both_directions() {
        let mut m = members();
        m.push((SIGNATURE_MEMBER.to_string(), b"whatever".to_vec()));
        verify_members(signed().as_bytes(), "faster-pistol", "1.2.0", &as_refs(&m)).unwrap();
    }

    #[test]
    fn a_replayed_signature_fails_on_slug_or_version() {
        let err = verify_members(
            signed().as_bytes(),
            "other-mod",
            "1.2.0",
            &as_refs(&members()),
        )
        .unwrap_err();
        assert!(err.contains("is for faster-pistol"), "{err}");
        let err = verify_members(
            signed().as_bytes(),
            "faster-pistol",
            "9.9.9",
            &as_refs(&members()),
        )
        .unwrap_err();
        assert!(err.contains("not faster-pistol 9.9.9"), "{err}");
    }

    #[test]
    fn tampering_with_the_payload_breaks_the_signature() {
        let mut envelope: Envelope = serde_json::from_str(&signed()).unwrap();
        let mut payload = base64::engine::general_purpose::STANDARD
            .decode(&envelope.payload)
            .unwrap();
        let at = payload.len() / 2;
        payload[at] ^= 0x01;
        envelope.payload = b64(&payload);
        let text = serde_json::to_string(&envelope).unwrap();
        let err = verify_members(
            text.as_bytes(),
            "faster-pistol",
            "1.2.0",
            &as_refs(&members()),
        )
        .unwrap_err();
        assert!(err.contains("does not verify"), "{err}");
    }

    #[test]
    fn swapping_the_envelope_key_fails_even_with_a_valid_signature() {
        // A second identity signs the same statement bytes; splicing its key
        // and signature into the original envelope must trip the in-payload
        // fingerprint check.
        let original = signed();
        let envelope: Envelope = serde_json::from_str(&original).unwrap();
        let payload = base64::engine::general_purpose::STANDARD
            .decode(&envelope.payload)
            .unwrap();
        let other = SigningIdentity::from_seed(&[9u8; 32]);
        let mut message = DOMAIN_PREFIX.to_vec();
        message.extend_from_slice(&payload);
        let forged = Envelope {
            public_key: b64(&other.public_key()),
            signature: b64(&other.key.sign(&message).to_bytes()),
            ..envelope
        };
        let text = serde_json::to_string(&forged).unwrap();
        let err = verify_members(
            text.as_bytes(),
            "faster-pistol",
            "1.2.0",
            &as_refs(&members()),
        )
        .unwrap_err();
        assert!(err.contains("different key"), "{err}");
    }

    #[test]
    fn duplicate_members_are_rejected_outright() {
        let mut m = members();
        m.push(m[0].clone());
        let err = verify_members(signed().as_bytes(), "faster-pistol", "1.2.0", &as_refs(&m))
            .unwrap_err();
        assert!(err.contains("duplicate"), "{err}");
    }
}
