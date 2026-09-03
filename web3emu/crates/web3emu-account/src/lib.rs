//! web3emu-account
//!
//! The account model (section 12 of the WEB3EMU spec). Deliberately
//! generic so it can back both externally-controlled accounts (EOAs) and
//! contract accounts, and so future execution backends are not locked
//! into one storage shape.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use web3emu_types::{Address, Balance, Nonce};

/// Whether an account is a plain wallet ("externally controlled") or a
/// deployed contract.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AccountKind {
    ExternallyControlled,
    Contract,
}

/// Generic account key-value storage. Deterministic iteration order
/// (`BTreeMap`) matters: it feeds the state root calculation.
pub type Storage = BTreeMap<Vec<u8>, Vec<u8>>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account {
    pub address: Address,
    pub kind: AccountKind,
    pub nonce: Nonce,
    pub balance: Balance,
    /// Present only for `AccountKind::Contract`. Interpreted by
    /// `web3emu-contract` - this crate treats it as opaque bytes.
    #[serde(with = "code_serde")]
    pub code: Option<Vec<u8>>,
    #[serde(with = "storage_serde")]
    pub storage: Storage,
    /// Free-form developer-facing labels, e.g. `{"label": "Alice"}`.
    /// Never consulted by consensus-relevant logic.
    pub metadata: BTreeMap<String, String>,
}

impl Account {
    pub fn new_eoa(address: Address, balance: Balance) -> Self {
        Account {
            address,
            kind: AccountKind::ExternallyControlled,
            nonce: 0,
            balance,
            code: None,
            storage: Storage::new(),
            metadata: BTreeMap::new(),
        }
    }

    pub fn new_contract(address: Address, code: Vec<u8>) -> Self {
        Account {
            address,
            kind: AccountKind::Contract,
            nonce: 0,
            balance: 0,
            code: Some(code),
            storage: Storage::new(),
            metadata: BTreeMap::new(),
        }
    }

    pub fn is_contract(&self) -> bool {
        matches!(self.kind, AccountKind::Contract)
    }

    pub fn with_metadata(mut self, key: &str, value: &str) -> Self {
        self.metadata.insert(key.to_string(), value.to_string());
        self
    }
}

/// `Storage` keys and values are arbitrary bytes, but JSON object keys
/// must be strings - so on the wire (snapshots, `web3emu state --json`,
/// etc.) storage is hex-encoded key/value pairs rather than a native
/// JSON object. In-memory (`Account.storage`), it stays a plain
/// `BTreeMap<Vec<u8>, Vec<u8>>` for cheap, deterministic iteration.
mod storage_serde {
    use super::Storage;
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    pub fn serialize<S>(map: &Storage, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let entries: Vec<(String, String)> =
            map.iter().map(|(k, v)| (hex::encode(k), hex::encode(v))).collect();
        entries.serialize(serializer)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Storage, D::Error>
    where
        D: Deserializer<'de>,
    {
        let entries = Vec::<(String, String)>::deserialize(deserializer)?;
        let mut map = Storage::new();
        for (k, v) in entries {
            let key = hex::decode(k).map_err(serde::de::Error::custom)?;
            let value = hex::decode(v).map_err(serde::de::Error::custom)?;
            map.insert(key, value);
        }
        Ok(map)
    }
}

/// Same rationale as `storage_serde`: renders contract code as a `0x..`
/// hex string on the wire instead of a JSON array of byte numbers.
mod code_serde {
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S>(code: &Option<Vec<u8>>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match code {
            Some(bytes) => serializer.serialize_str(&format!("0x{}", hex::encode(bytes))),
            None => serializer.serialize_none(),
        }
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Option<Vec<u8>>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let opt = Option::<String>::deserialize(deserializer)?;
        opt.map(|s| hex::decode(s.strip_prefix("0x").unwrap_or(&s)).map_err(serde::de::Error::custom))
            .transpose()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum AccountError {
    #[error("account {0} not found")]
    NotFound(Address),
    #[error("account {0} already exists")]
    AlreadyExists(Address),
    #[error("insufficient balance for {0}: have {have}, need {need}", have = .1, need = .2)]
    InsufficientBalance(Address, Balance, Balance),
    #[error("balance overflow for {0}")]
    BalanceOverflow(Address),
    #[error("nonce overflow for {0}")]
    NonceOverflow(Address),
}

/// Deterministic account store. `BTreeMap` keeps address ordering stable,
/// which matters for anything that folds account state into a root hash.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AccountStore {
    accounts: BTreeMap<Address, Account>,
}

impl AccountStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(&mut self, account: Account) {
        self.accounts.insert(account.address, account);
    }

    pub fn get(&self, address: &Address) -> Option<&Account> {
        self.accounts.get(address)
    }

    pub fn get_mut(&mut self, address: &Address) -> Option<&mut Account> {
        self.accounts.get_mut(address)
    }

    pub fn contains(&self, address: &Address) -> bool {
        self.accounts.contains_key(address)
    }

    pub fn len(&self) -> usize {
        self.accounts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.accounts.is_empty()
    }

    pub fn iter(&self) -> impl Iterator<Item = (&Address, &Account)> {
        self.accounts.iter()
    }

    /// Get-or-create: returns a fresh zero-balance EOA if the address has
    /// never been seen before. Mirrors how most Web3 networks treat
    /// implicit account creation on first credit.
    pub fn get_or_create_eoa(&mut self, address: Address) -> &mut Account {
        self.accounts
            .entry(address)
            .or_insert_with(|| Account::new_eoa(address, 0))
    }

    pub fn balance_of(&self, address: &Address) -> Balance {
        self.accounts.get(address).map(|a| a.balance).unwrap_or(0)
    }

    pub fn nonce_of(&self, address: &Address) -> Nonce {
        self.accounts.get(address).map(|a| a.nonce).unwrap_or(0)
    }

    pub fn credit(&mut self, address: &Address, amount: Balance) -> Result<(), AccountError> {
        let account = self.get_or_create_eoa(*address);
        account.balance = account
            .balance
            .checked_add(amount)
            .ok_or(AccountError::BalanceOverflow(*address))?;
        Ok(())
    }

    pub fn debit(&mut self, address: &Address, amount: Balance) -> Result<(), AccountError> {
        let account = self
            .accounts
            .get_mut(address)
            .ok_or(AccountError::NotFound(*address))?;
        if account.balance < amount {
            return Err(AccountError::InsufficientBalance(
                *address,
                account.balance,
                amount,
            ));
        }
        account.balance -= amount;
        Ok(())
    }

    pub fn increment_nonce(&mut self, address: &Address) -> Result<(), AccountError> {
        let account = self.get_or_create_eoa(*address);
        account.nonce = account
            .nonce
            .checked_add(1)
            .ok_or(AccountError::NonceOverflow(*address))?;
        Ok(())
    }

    pub fn accounts(&self) -> &BTreeMap<Address, Account> {
        &self.accounts
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn credit_and_debit_round_trip() {
        let mut store = AccountStore::new();
        let addr = Address([1u8; 20]);
        store.credit(&addr, 1000).unwrap();
        assert_eq!(store.balance_of(&addr), 1000);
        store.debit(&addr, 400).unwrap();
        assert_eq!(store.balance_of(&addr), 600);
    }

    #[test]
    fn debit_beyond_balance_fails() {
        let mut store = AccountStore::new();
        let addr = Address([1u8; 20]);
        store.credit(&addr, 100).unwrap();
        assert!(store.debit(&addr, 200).is_err());
    }

    #[test]
    fn nonce_increments_deterministically() {
        let mut store = AccountStore::new();
        let addr = Address([2u8; 20]);
        for i in 0..5 {
            assert_eq!(store.nonce_of(&addr), i);
            store.increment_nonce(&addr).unwrap();
        }
    }
}
