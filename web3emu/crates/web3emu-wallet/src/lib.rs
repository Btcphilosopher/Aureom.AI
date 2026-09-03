//! web3emu-wallet
//!
//! A development wallet emulator (section 13). Every account it manages
//! is a deterministic or locally-generated test key.
//!
//! # SIMULATED ACCOUNT / NEVER USE IN PRODUCTION
//!
//! Nothing produced by this crate is suitable for holding real value.
//! Deterministic accounts (`import_test_account`) are derived from a
//! public label by hashing it - anyone who knows the label knows the
//! private key. See `docs/WALLETS.md` and `docs/SECURITY.md`.

use std::collections::BTreeMap;
use web3emu_crypto::Keypair;
use web3emu_tx::{EmulatorTransaction, TransactionType};
use web3emu_types::{Address, Balance, ChainId, Gas, Nonce, Timestamp};

pub const DEV_KEY_WARNING: &str =
    "SIMULATED ACCOUNT - deterministic development key. NEVER USE IN PRODUCTION.";

/// The standard set of named development accounts (section 14).
pub const STANDARD_DEV_LABELS: &[&str] = &[
    "Alice",
    "Bob",
    "Treasury",
    "Developer",
    "ContractOwner",
    "TestUser01",
    "TestUser02",
];

/// Read-only view of network state a wallet needs to answer "what's my
/// balance / nonce" without owning the network itself. Implemented by
/// `web3emu-core::EmulatorNetwork`. Keeping this as a trait avoids a
/// wallet -> core -> wallet dependency cycle.
pub trait WalletNetworkView {
    fn balance_of(&self, address: &Address) -> Balance;
    fn nonce_of(&self, address: &Address) -> Nonce;
    fn chain_id(&self) -> ChainId;
}

#[derive(Debug, thiserror::Error)]
pub enum WalletError {
    #[error("unknown account label '{0}'")]
    UnknownAccount(String),
    #[error("account label '{0}' already exists")]
    AlreadyExists(String),
    #[error(transparent)]
    Tx(#[from] web3emu_tx::TxError),
}

/// A locally-managed simulated account: a label, its keypair, and a
/// clear marker that this is a test fixture, never a production wallet.
#[derive(Clone)]
pub struct WalletAccount {
    pub label: String,
    pub keypair: Keypair,
    pub is_deterministic: bool,
}

impl WalletAccount {
    pub fn address(&self) -> Address {
        self.keypair.address()
    }
}

pub struct EmulatorWallet {
    accounts: BTreeMap<String, WalletAccount>,
    pub active_network_id: String,
}

impl Default for EmulatorWallet {
    fn default() -> Self {
        Self::new()
    }
}

impl EmulatorWallet {
    pub fn new() -> Self {
        EmulatorWallet {
            accounts: BTreeMap::new(),
            active_network_id: "web3emu-local".to_string(),
        }
    }

    /// Convenience constructor preloading the standard labeled
    /// development accounts (section 14).
    pub fn with_dev_accounts() -> Self {
        let mut wallet = Self::new();
        for label in STANDARD_DEV_LABELS {
            wallet.import_test_account(label).ok();
        }
        wallet
    }

    /// Deterministically derive and register an account from a label.
    /// Same label always yields the same address - this is what makes
    /// scenarios and fixtures reproducible.
    pub fn import_test_account(&mut self, label: &str) -> Result<Address, WalletError> {
        if self.accounts.contains_key(label) {
            return Err(WalletError::AlreadyExists(label.to_string()));
        }
        let keypair = Keypair::from_label(label);
        let address = keypair.address();
        self.accounts.insert(
            label.to_string(),
            WalletAccount {
                label: label.to_string(),
                keypair,
                is_deterministic: true,
            },
        );
        Ok(address)
    }

    /// Create a fresh, non-deterministic scratch account seeded from an
    /// external random source (e.g. the network's configured RNG seed
    /// combined with a counter - callers control reproducibility).
    pub fn create_account(&mut self, label: &str, rng_seed: u64) -> Result<Address, WalletError> {
        if self.accounts.contains_key(label) {
            return Err(WalletError::AlreadyExists(label.to_string()));
        }
        let keypair = Keypair::generate_with_rng_seed(rng_seed);
        let address = keypair.address();
        self.accounts.insert(
            label.to_string(),
            WalletAccount {
                label: label.to_string(),
                keypair,
                is_deterministic: false,
            },
        );
        Ok(address)
    }

    pub fn account(&self, label: &str) -> Result<&WalletAccount, WalletError> {
        self.accounts
            .get(label)
            .ok_or_else(|| WalletError::UnknownAccount(label.to_string()))
    }

    pub fn address_of(&self, label: &str) -> Result<Address, WalletError> {
        Ok(self.account(label)?.address())
    }

    pub fn accounts(&self) -> impl Iterator<Item = &WalletAccount> {
        self.accounts.values()
    }

    pub fn balance_of(&self, label: &str, view: &impl WalletNetworkView) -> Result<Balance, WalletError> {
        Ok(view.balance_of(&self.address_of(label)?))
    }

    pub fn nonce_of(&self, label: &str, view: &impl WalletNetworkView) -> Result<Nonce, WalletError> {
        Ok(view.nonce_of(&self.address_of(label)?))
    }

    pub fn switch_network(&mut self, network_id: &str) {
        self.active_network_id = network_id.to_string();
    }

    /// Build and sign a transaction on behalf of a managed account,
    /// pulling `chain_id` and the current `nonce` from `view`. This is
    /// the wallet's "generate signing request + sign" flow (section 13)
    /// collapsed into one call for convenience; submitting the result to
    /// the network's mempool is the caller's (or `web3emu-core`'s) job.
    #[allow(clippy::too_many_arguments)]
    pub fn prepare_transaction(
        &self,
        label: &str,
        view: &impl WalletNetworkView,
        recipient: Option<Address>,
        value: Balance,
        gas_limit: Gas,
        max_fee: u128,
        priority_fee: u128,
        data: Vec<u8>,
        timestamp: Timestamp,
        tx_type: TransactionType,
    ) -> Result<EmulatorTransaction, WalletError> {
        let account = self.account(label)?;
        let nonce = view.nonce_of(&account.address());
        let mut tx = EmulatorTransaction::new_unsigned(
            view.chain_id(),
            nonce,
            account.address(),
            account.keypair.public_key_bytes(),
            recipient,
            value,
            gas_limit,
            max_fee,
            priority_fee,
            data,
            timestamp,
            tx_type,
        );
        tx.sign(&account.keypair)?;
        Ok(tx)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct FakeView {
        balance: Balance,
        nonce: Nonce,
        chain_id: ChainId,
    }
    impl WalletNetworkView for FakeView {
        fn balance_of(&self, _address: &Address) -> Balance {
            self.balance
        }
        fn nonce_of(&self, _address: &Address) -> Nonce {
            self.nonce
        }
        fn chain_id(&self) -> ChainId {
            self.chain_id
        }
    }

    #[test]
    fn dev_accounts_are_deterministic_across_wallets() {
        let a = EmulatorWallet::with_dev_accounts();
        let b = EmulatorWallet::with_dev_accounts();
        for label in STANDARD_DEV_LABELS {
            assert_eq!(a.address_of(label).unwrap(), b.address_of(label).unwrap());
        }
    }

    #[test]
    fn prepare_transaction_signs_correctly() {
        let mut wallet = EmulatorWallet::new();
        wallet.import_test_account("Alice").unwrap();
        let view = FakeView {
            balance: 1_000_000,
            nonce: 3,
            chain_id: 31337,
        };
        let tx = wallet
            .prepare_transaction(
                "Alice",
                &view,
                Some(Address([9u8; 20])),
                100,
                21000,
                1,
                0,
                vec![],
                0,
                TransactionType::Transfer,
            )
            .unwrap();
        assert_eq!(tx.nonce, 3);
        assert_eq!(tx.chain_id, 31337);
        assert!(tx.verify_signature().is_ok());
    }

    #[test]
    fn unknown_label_errors_cleanly() {
        let wallet = EmulatorWallet::new();
        assert!(wallet.address_of("Nobody").is_err());
    }
}
