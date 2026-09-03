//! web3emu-state
//!
//! The canonical world state (section 23-24): an in-memory account store
//! plus a deterministic state root. Documented explicitly (see
//! `docs/PROTOCOL.md`): this is NOT a production Merkle-Patricia trie. It
//! is a simple, deterministic, sequential hash fold over sorted account
//! data - enough to detect divergence and support snapshots/diffs, not
//! intended to be trie-compatible with any specific production network.

use serde::{Deserialize, Serialize};
use web3emu_account::{Account, AccountError, AccountStore};
use web3emu_crypto::{fold_hashes, hash};
use web3emu_types::{Address, Balance, Hash256};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct WorldState {
    pub accounts: AccountStore,
}

impl WorldState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Deterministic state root: fold per-account hashes, in address
    /// order (BTreeMap already guarantees this).
    pub fn state_root(&self) -> Hash256 {
        let account_hashes: Vec<Hash256> = self
            .accounts
            .iter()
            .map(|(_, account)| account_hash(account))
            .collect();
        fold_hashes(&account_hashes)
    }

    pub fn balance_of(&self, address: &Address) -> Balance {
        self.accounts.balance_of(address)
    }

    pub fn get(&self, address: &Address) -> Option<&Account> {
        self.accounts.get(address)
    }

    pub fn get_mut(&mut self, address: &Address) -> Option<&mut Account> {
        self.accounts.get_mut(address)
    }

    pub fn get_or_create_eoa(&mut self, address: Address) -> &mut Account {
        self.accounts.get_or_create_eoa(address)
    }

    pub fn insert(&mut self, account: Account) {
        self.accounts.insert(account);
    }

    /// Full deep clone, used to snapshot state before speculative
    /// execution (e.g. `eth_call`, forks) without touching canonical
    /// state.
    pub fn checkpoint(&self) -> WorldState {
        self.clone()
    }
}

/// Deterministic per-account content hash, folded into the state root.
fn account_hash(account: &Account) -> Hash256 {
    let mut buf = Vec::new();
    buf.extend_from_slice(&account.address.0);
    buf.extend_from_slice(&account.nonce.to_be_bytes());
    buf.extend_from_slice(&account.balance.to_be_bytes());
    if let Some(code) = &account.code {
        buf.extend_from_slice(&hash(code).0);
    }
    buf.extend_from_slice(&storage_root(account).0);
    hash(&buf)
}

/// Storage is a `BTreeMap`, so iteration order is already canonical.
fn storage_root(account: &Account) -> Hash256 {
    let entry_hashes: Vec<Hash256> = account
        .storage
        .iter()
        .map(|(k, v)| {
            let mut buf = Vec::with_capacity(k.len() + v.len());
            buf.extend_from_slice(k);
            buf.extend_from_slice(v);
            hash(&buf)
        })
        .collect();
    fold_hashes(&entry_hashes)
}

pub type StateResult<T> = Result<T, AccountError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_state_produces_same_root() {
        let mut a = WorldState::new();
        let mut b = WorldState::new();
        let addr = Address([5u8; 20]);
        a.get_or_create_eoa(addr).balance = 500;
        b.get_or_create_eoa(addr).balance = 500;
        assert_eq!(a.state_root(), b.state_root());
    }

    #[test]
    fn different_balances_produce_different_roots() {
        let mut a = WorldState::new();
        let mut b = WorldState::new();
        let addr = Address([5u8; 20]);
        a.get_or_create_eoa(addr).balance = 500;
        b.get_or_create_eoa(addr).balance = 501;
        assert_ne!(a.state_root(), b.state_root());
    }

    #[test]
    fn empty_state_has_zero_root() {
        let s = WorldState::new();
        assert_eq!(s.state_root(), Hash256::ZERO);
    }
}
