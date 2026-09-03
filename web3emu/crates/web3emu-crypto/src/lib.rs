//! web3emu-crypto
//!
//! Thin, replaceable abstraction over mature cryptographic primitives.
//! WEB3EMU never implements its own cryptography. Hashing is SHA-256
//! (`sha2`, RustCrypto) and signing is Ed25519 (`ed25519-dalek`).
//!
//! These are deliberate choices for a *simulator*: they are NOT the same
//! primitives used by any specific production chain (e.g. Ethereum uses
//! Keccak-256 and secp256k1). See `docs/COMPATIBILITY.md`. The provider
//! is isolated behind this crate so it can be swapped later without
//! touching the rest of the workspace.

use ed25519_dalek::{Signer, SigningKey, Verifier, VerifyingKey};
use rand::RngCore;
use rand_chacha::rand_core::SeedableRng;
use rand_chacha::ChaCha20Rng;
use sha2::{Digest, Sha256};
use web3emu_types::{Address, Hash256};

#[derive(Debug, thiserror::Error)]
pub enum CryptoError {
    #[error("invalid signature encoding")]
    InvalidSignature,
    #[error("invalid public key encoding")]
    InvalidPublicKey,
    #[error("signature verification failed")]
    VerificationFailed,
}

/// SHA-256 over arbitrary bytes. Used for state roots, block hashes and
/// transaction hashes throughout WEB3EMU.
pub fn hash(data: &[u8]) -> Hash256 {
    let digest = Sha256::digest(data);
    Hash256(digest.into())
}

/// Combine two hashes deterministically (used for simple Merkle-style
/// folding of transaction/receipt lists). Not a production trie.
pub fn hash_pair(a: &Hash256, b: &Hash256) -> Hash256 {
    let mut buf = Vec::with_capacity(64);
    buf.extend_from_slice(&a.0);
    buf.extend_from_slice(&b.0);
    hash(&buf)
}

/// Fold an ordered list of hashes into a single root hash. Empty input
/// yields the zero hash. This is intentionally simple (sequential
/// pairwise folding) rather than a balanced Merkle tree - it is
/// deterministic and sufficient for a local simulator's `*_root` fields.
pub fn fold_hashes(hashes: &[Hash256]) -> Hash256 {
    if hashes.is_empty() {
        return Hash256::ZERO;
    }
    let mut acc = hashes[0];
    for h in &hashes[1..] {
        acc = hash_pair(&acc, h);
    }
    acc
}

/// A signing keypair for a simulated account.
///
/// THESE ARE DEVELOPMENT/TEST KEYS. WEB3EMU keys must never be used to
/// hold real value on a real network.
#[derive(Clone)]
pub struct Keypair {
    signing_key: SigningKey,
}

/// A detached Ed25519 signature (64 bytes).
#[derive(Clone, Copy, PartialEq, Eq)]
pub struct Signature(pub [u8; 64]);

impl std::fmt::Debug for Signature {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "0x{}", hex::encode(self.0))
    }
}

impl serde::Serialize for Signature {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&format!("0x{}", hex::encode(self.0)))
    }
}

impl<'de> serde::Deserialize<'de> for Signature {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        let s = s.strip_prefix("0x").unwrap_or(&s);
        let bytes = hex::decode(s).map_err(serde::de::Error::custom)?;
        if bytes.len() != 64 {
            return Err(serde::de::Error::custom("signature must be 64 bytes"));
        }
        let mut out = [0u8; 64];
        out.copy_from_slice(&bytes);
        Ok(Signature(out))
    }
}

impl Keypair {
    /// Deterministically derive a keypair from a 32-byte seed. Same seed
    /// always yields the same keypair - this is how WEB3EMU produces
    /// reproducible development accounts (see `web3emu-wallet`).
    pub fn from_seed(seed: [u8; 32]) -> Self {
        Keypair {
            signing_key: SigningKey::from_bytes(&seed),
        }
    }

    /// Derive a deterministic seed from a human-readable label (e.g.
    /// "Alice") by hashing the label. This is a development convenience,
    /// not a key-derivation standard.
    pub fn from_label(label: &str) -> Self {
        let seed = hash(label.as_bytes());
        Self::from_seed(seed.0)
    }

    /// Generate a random (non-deterministic) keypair, seeded from an
    /// external CSPRNG-backed seed. Useful for one-off scratch accounts.
    pub fn generate_with_rng_seed(rng_seed: u64) -> Self {
        let mut rng = ChaCha20Rng::seed_from_u64(rng_seed);
        let mut seed = [0u8; 32];
        rng.fill_bytes(&mut seed);
        Self::from_seed(seed)
    }

    pub fn public_key_bytes(&self) -> [u8; 32] {
        self.signing_key.verifying_key().to_bytes()
    }

    /// Derive the simulated address from the public key: the last 20
    /// bytes of SHA-256(pubkey).
    pub fn address(&self) -> Address {
        let digest = hash(&self.public_key_bytes());
        let mut out = [0u8; 20];
        out.copy_from_slice(&digest.0[12..32]);
        Address(out)
    }

    pub fn sign(&self, message: &[u8]) -> Signature {
        let sig = self.signing_key.sign(message);
        Signature(sig.to_bytes())
    }
}

/// Derive the simulated address for a raw public key, without needing
/// the private key. Used to validate transaction senders.
pub fn address_from_public_key(public_key: &[u8; 32]) -> Address {
    let digest = hash(public_key);
    let mut out = [0u8; 20];
    out.copy_from_slice(&digest.0[12..32]);
    Address(out)
}

pub fn verify(
    public_key: &[u8; 32],
    message: &[u8],
    signature: &Signature,
) -> Result<(), CryptoError> {
    let vk = VerifyingKey::from_bytes(public_key).map_err(|_| CryptoError::InvalidPublicKey)?;
    let sig = ed25519_dalek::Signature::from_bytes(&signature.0);
    vk.verify(message, &sig)
        .map_err(|_| CryptoError::VerificationFailed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_label_yields_same_keypair() {
        let a = Keypair::from_label("Alice");
        let b = Keypair::from_label("Alice");
        assert_eq!(a.address(), b.address());
        assert_eq!(a.public_key_bytes(), b.public_key_bytes());
    }

    #[test]
    fn different_labels_yield_different_addresses() {
        let a = Keypair::from_label("Alice");
        let b = Keypair::from_label("Bob");
        assert_ne!(a.address(), b.address());
    }

    #[test]
    fn sign_and_verify_round_trip() {
        let kp = Keypair::from_label("Alice");
        let msg = b"hello web3emu";
        let sig = kp.sign(msg);
        assert!(verify(&kp.public_key_bytes(), msg, &sig).is_ok());
    }

    #[test]
    fn tampered_message_fails_verification() {
        let kp = Keypair::from_label("Alice");
        let sig = kp.sign(b"original");
        assert!(verify(&kp.public_key_bytes(), b"tampered", &sig).is_err());
    }
}
