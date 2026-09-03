//! web3emu-trace
//!
//! Execution tracing (section 32) and state diffs (section 33) - the
//! "most important debugging feature" of the emulator, per the spec.

use serde::{Deserialize, Serialize};
use web3emu_account::Account;
use web3emu_types::{Address, Balance, Nonce};

/// One step of a transaction's execution, in the order the state
/// transition engine performed it. Mirrors the pipeline diagram in
/// section 32 (account validation -> balance check -> contract call ->
/// storage read/write -> event -> state update).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TraceStep {
    AccountValidation { address: Address, ok: bool, detail: String },
    BalanceCheck { address: Address, required: Balance, available: Balance, ok: bool },
    NonceCheck { address: Address, expected: Nonce, got: Nonce, ok: bool },
    ContractCall { contract: Address, method: String },
    StorageRead { contract: Address, key: Vec<u8>, value: Option<Vec<u8>> },
    StorageWrite { contract: Address, key: Vec<u8>, old_value: Option<Vec<u8>>, new_value: Vec<u8> },
    Event { contract: Address, event_name: String },
    StateUpdate { detail: String },
    Note(String),
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TransactionTrace {
    pub steps: Vec<TraceStep>,
}

impl TransactionTrace {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push(&mut self, step: TraceStep) {
        self.steps.push(step);
    }
}

/// A field-by-field difference between two states for a single account
/// (section 33). `None` before = account did not exist yet; `None` after
/// = account still doesn't exist (should not normally occur since we
/// only diff touched accounts).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AccountDiff {
    pub address: Address,
    pub balance_before: Option<Balance>,
    pub balance_after: Option<Balance>,
    pub nonce_before: Option<Nonce>,
    pub nonce_after: Option<Nonce>,
    pub storage_changes: Vec<StorageChange>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StorageChange {
    pub key: Vec<u8>,
    pub old_value: Option<Vec<u8>>,
    pub new_value: Option<Vec<u8>>,
}

/// The full diff produced by one transaction's execution.
pub type StateDiff = Vec<AccountDiff>;

/// Compare an account's state before and after execution and produce a
/// diff, or `None` if nothing changed.
pub fn diff_account(
    address: Address,
    before: Option<&Account>,
    after: Option<&Account>,
) -> Option<AccountDiff> {
    let unchanged = before.map(|a| a.balance) == after.map(|a| a.balance)
        && before.map(|a| a.nonce) == after.map(|a| a.nonce)
        && before.map(|a| &a.storage) == after.map(|a| &a.storage);
    if unchanged {
        return None;
    }

    let mut storage_changes = Vec::new();
    let before_storage = before.map(|a| &a.storage);
    let after_storage = after.map(|a| &a.storage);
    let mut keys: std::collections::BTreeSet<&Vec<u8>> = std::collections::BTreeSet::new();
    if let Some(s) = before_storage {
        keys.extend(s.keys());
    }
    if let Some(s) = after_storage {
        keys.extend(s.keys());
    }
    for key in keys {
        let b = before_storage.and_then(|s| s.get(key)).cloned();
        let a = after_storage.and_then(|s| s.get(key)).cloned();
        if b != a {
            storage_changes.push(StorageChange {
                key: key.clone(),
                old_value: b,
                new_value: a,
            });
        }
    }

    Some(AccountDiff {
        address,
        balance_before: before.map(|a| a.balance),
        balance_after: after.map(|a| a.balance),
        nonce_before: before.map(|a| a.nonce),
        nonce_after: after.map(|a| a.nonce),
        storage_changes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use web3emu_account::Account;

    #[test]
    fn diff_detects_balance_change() {
        let addr = Address([1u8; 20]);
        let before = Account::new_eoa(addr, 100);
        let mut after = before.clone();
        after.balance = 50;
        let d = diff_account(addr, Some(&before), Some(&after)).unwrap();
        assert_eq!(d.balance_before, Some(100));
        assert_eq!(d.balance_after, Some(50));
    }

    #[test]
    fn no_diff_when_unchanged() {
        let addr = Address([1u8; 20]);
        let a = Account::new_eoa(addr, 100);
        let b = a.clone();
        assert!(diff_account(addr, Some(&a), Some(&b)).is_none());
    }
}
