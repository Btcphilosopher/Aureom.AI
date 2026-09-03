//! web3emu-types
//!
//! Canonical primitive types shared across every WEB3EMU crate.
//!
//! WEB3EMU IS A LOCAL SIMULATION / DEVELOPMENT TOOL. Nothing in this crate
//! (or in WEB3EMU as a whole) is intended for production custody, real
//! funds, or real network compatibility. See `docs/SECURITY.md`.

use serde::Serialize;
use std::fmt;
use std::str::FromStr;

/// A 20-byte simulated account address, derived from a public key.
///
/// NOTE: this is a SIMULATED address space. It is not guaranteed to be
/// derived the same way as any specific production network's addresses
/// unless a compatibility document says otherwise (see COMPATIBILITY.md).
#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Address(pub [u8; 20]);

impl Address {
    pub const ZERO: Address = Address([0u8; 20]);

    pub fn from_slice(bytes: &[u8]) -> Result<Self, TypeError> {
        if bytes.len() != 20 {
            return Err(TypeError::InvalidLength {
                expected: 20,
                got: bytes.len(),
            });
        }
        let mut out = [0u8; 20];
        out.copy_from_slice(bytes);
        Ok(Address(out))
    }
}

impl fmt::Debug for Address {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self)
    }
}

impl fmt::Display for Address {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "0x{}", hex::encode(self.0))
    }
}

impl FromStr for Address {
    type Err = TypeError;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let s = s.strip_prefix("0x").unwrap_or(s);
        let bytes = hex::decode(s).map_err(|_| TypeError::InvalidHex)?;
        Address::from_slice(&bytes)
    }
}

impl Serialize for Address {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

/// A 32-byte hash: transaction hashes, block hashes, state roots, storage
/// keys, and log topics all share this representation.
#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Default)]
pub struct Hash256(pub [u8; 32]);

impl Hash256 {
    pub const ZERO: Hash256 = Hash256([0u8; 32]);

    pub fn from_slice(bytes: &[u8]) -> Result<Self, TypeError> {
        if bytes.len() != 32 {
            return Err(TypeError::InvalidLength {
                expected: 32,
                got: bytes.len(),
            });
        }
        let mut out = [0u8; 32];
        out.copy_from_slice(bytes);
        Ok(Hash256(out))
    }
}

impl fmt::Debug for Hash256 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self)
    }
}

impl fmt::Display for Hash256 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "0x{}", hex::encode(self.0))
    }
}

impl FromStr for Hash256 {
    type Err = TypeError;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let s = s.strip_prefix("0x").unwrap_or(s);
        let bytes = hex::decode(s).map_err(|_| TypeError::InvalidHex)?;
        Hash256::from_slice(&bytes)
    }
}

impl serde::Serialize for Hash256 {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> serde::Deserialize<'de> for Hash256 {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        Hash256::from_str(&s).map_err(serde::de::Error::custom)
    }
}

impl<'de> serde::Deserialize<'de> for Address {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        Address::from_str(&s).map_err(serde::de::Error::custom)
    }
}

/// Simulated chain identifier. Default local chain id is 31337, matching
/// the convention used by common local Web3 development tools.
pub type ChainId = u64;

pub const DEFAULT_CHAIN_ID: ChainId = 31337;

/// Simulated native-asset balance. u128 is large enough for any test
/// fixture and avoids overflow bugs common with u64 "wei"-style math.
pub type Balance = u128;

/// Account transaction counter.
pub type Nonce = u64;

/// Block height (0 = genesis).
pub type BlockHeight = u64;

/// Gas is a synthetic accounting unit, not a real-network gas value unless
/// a scenario explicitly configures it to mirror one.
pub type Gas = u64;

/// Unix timestamp, seconds.
pub type Timestamp = u64;

#[derive(Debug, thiserror::Error)]
pub enum TypeError {
    #[error("invalid length: expected {expected}, got {got}")]
    InvalidLength { expected: usize, got: usize },
    #[error("invalid hex encoding")]
    InvalidHex,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn address_round_trips_through_hex() {
        let addr = Address([7u8; 20]);
        let s = addr.to_string();
        let parsed: Address = s.parse().unwrap();
        assert_eq!(addr, parsed);
    }

    #[test]
    fn hash_round_trips_through_hex() {
        let h = Hash256([9u8; 32]);
        let s = h.to_string();
        let parsed: Hash256 = s.parse().unwrap();
        assert_eq!(h, parsed);
    }
}
