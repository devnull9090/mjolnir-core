//! Emit a signed fixture, so the hub's TypeScript verifier can be checked
//! against this crate.
//!
//! The two implementations must agree byte for byte: the editor signs with
//! this one and the hub accepts or rejects with the other, so a divergence
//! (a different domain prefix, a different digest, a mis-wrapped key) would
//! mean nobody can publish. Run it through `hub/scripts/verify-fixture.mts`.

use std::collections::BTreeMap;

use base64::Engine;
use mjolnir_sign::{Author, SigningIdentity};

fn main() {
    // A fixed seed keeps the fixture reproducible.
    let identity = SigningIdentity::from_seed(&[7u8; 32]);
    let members: Vec<(String, Vec<u8>)> = vec![
        (
            "mjolnir.json".into(),
            br#"{"schema_version":1,"name":"Fixture","version":"1.2.0","type":"content"}"#.to_vec(),
        ),
        ("content/fixture_P.utoc".into(), vec![1, 2, 3, 4, 5]),
        ("content/fixture_P.ucas".into(), vec![9, 8, 7]),
    ];
    let refs: Vec<(String, &[u8])> = members
        .iter()
        .map(|(n, b)| (n.clone(), b.as_slice()))
        .collect();

    let envelope = identity
        .sign_members(
            "fixture-mod",
            "1.2.0",
            Some(Author {
                id: "u-fixture".into(),
                username: "fixture".into(),
            }),
            "2026-08-03T00:00:00Z",
            &refs,
        )
        .expect("sign");

    let encoded: BTreeMap<String, String> = members
        .iter()
        .map(|(n, b)| {
            (
                n.clone(),
                base64::engine::general_purpose::STANDARD.encode(b),
            )
        })
        .collect();

    println!(
        "{}",
        serde_json::json!({
            "slug": "fixture-mod",
            "version": "1.2.0",
            "fingerprint": identity.fingerprint(),
            "envelope": envelope,
            "members": encoded,
        })
    );
}
