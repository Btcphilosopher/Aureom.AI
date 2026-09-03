//! web3emu-mempool
//!
//! A deterministic mempool (section 18). The mempool is explicitly NOT
//! authoritative state - it only holds candidate transactions until the
//! block engine includes (or the developer discards) them.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use web3emu_state::WorldState;
use web3emu_tx::EmulatorTransaction;
use web3emu_types::{Address, ChainId, Hash256, Nonce, Timestamp};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MempoolConfig {
    pub max_size: usize,
    /// Transactions older than this (relative to submission time) are
    /// dropped by `expire`.
    pub expiry_seconds: u64,
}

impl Default for MempoolConfig {
    fn default() -> Self {
        MempoolConfig {
            max_size: 5000,
            expiry_seconds: 3600,
        }
    }
}

#[derive(Debug, Clone, thiserror::Error, PartialEq, Eq)]
pub enum RejectionReason {
    #[error("wrong chain id: expected {expected}, got {got}")]
    WrongChainId { expected: ChainId, got: ChainId },
    #[error("invalid signature")]
    InvalidSignature,
    #[error("nonce too low: account nonce is {account_nonce}, got {got}")]
    NonceTooLow { account_nonce: Nonce, got: Nonce },
    #[error("duplicate transaction")]
    Duplicate,
    #[error("insufficient balance to cover value + max fee: have {have}, need {need}")]
    InsufficientBalance { have: u128, need: u128 },
    #[error("mempool is full ({0} transactions)")]
    Full(usize),
    #[error("replacement transaction does not increase priority fee")]
    ReplacementUnderpriced,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RejectedEntry {
    pub tx_hash: Hash256,
    pub sender: Address,
    pub reason: String,
    pub at: Timestamp,
}

/// Deterministic mempool keyed by sender then nonce, so per-sender
/// ordering is always exact and duplicate/replacement logic is O(log n).
#[derive(Debug, Clone, Default)]
pub struct Mempool {
    config: MempoolConfig,
    /// sender -> (nonce -> transaction)
    by_sender: BTreeMap<Address, BTreeMap<Nonce, EmulatorTransaction>>,
    by_hash: HashMap<Hash256, (Address, Nonce)>,
    submitted_at: HashMap<Hash256, Timestamp>,
    rejected_log: Vec<RejectedEntry>,
}

impl Mempool {
    pub fn new(config: MempoolConfig) -> Self {
        Mempool {
            config,
            ..Default::default()
        }
    }

    pub fn len(&self) -> usize {
        self.by_hash.len()
    }

    pub fn is_empty(&self) -> bool {
        self.by_hash.is_empty()
    }

    pub fn rejected_log(&self) -> &[RejectedEntry] {
        &self.rejected_log
    }

    fn reject(&mut self, tx: &EmulatorTransaction, reason: RejectionReason, now: Timestamp) -> RejectionReason {
        self.rejected_log.push(RejectedEntry {
            tx_hash: tx.hash,
            sender: tx.sender,
            reason: reason.to_string(),
            at: now,
        });
        reason
    }

    /// Validate and admit a signed transaction against a chain id and a
    /// read-only view of world state. Returns the previous transaction it
    /// replaced, if this was a fee-bump replacement.
    pub fn submit(
        &mut self,
        tx: EmulatorTransaction,
        chain_id: ChainId,
        state: &WorldState,
        now: Timestamp,
    ) -> Result<Option<EmulatorTransaction>, RejectionReason> {
        if tx.chain_id != chain_id {
            let reason = RejectionReason::WrongChainId {
                expected: chain_id,
                got: tx.chain_id,
            };
            return Err(self.reject(&tx, reason, now));
        }
        if tx.verify_signature().is_err() {
            return Err(self.reject(&tx, RejectionReason::InvalidSignature, now));
        }
        if self.by_hash.contains_key(&tx.hash) {
            return Err(self.reject(&tx, RejectionReason::Duplicate, now));
        }
        let account_nonce = state.accounts.nonce_of(&tx.sender);
        if tx.nonce < account_nonce {
            let reason = RejectionReason::NonceTooLow {
                account_nonce,
                got: tx.nonce,
            };
            return Err(self.reject(&tx, reason, now));
        }
        let required = tx.value + tx.max_fee * (tx.gas_limit as u128);
        let available = state.balance_of(&tx.sender);
        if available < required {
            let reason = RejectionReason::InsufficientBalance {
                have: available,
                need: required,
            };
            return Err(self.reject(&tx, reason, now));
        }

        let sender_slots = self.by_sender.entry(tx.sender).or_default();
        if let Some(existing) = sender_slots.get(&tx.nonce) {
            if tx.priority_fee <= existing.priority_fee {
                return Err(self.reject(&tx, RejectionReason::ReplacementUnderpriced, now));
            }
            let replaced = existing.clone();
            self.by_hash.remove(&replaced.hash);
            self.submitted_at.remove(&replaced.hash);
            self.by_hash.insert(tx.hash, (tx.sender, tx.nonce));
            self.submitted_at.insert(tx.hash, now);
            sender_slots.insert(tx.nonce, tx);
            return Ok(Some(replaced));
        }

        if self.by_hash.len() >= self.config.max_size {
            return Err(self.reject(&tx, RejectionReason::Full(self.config.max_size), now));
        }

        self.by_hash.insert(tx.hash, (tx.sender, tx.nonce));
        self.submitted_at.insert(tx.hash, now);
        sender_slots.insert(tx.nonce, tx);
        Ok(None)
    }

    /// Drop transactions submitted longer than `config.expiry_seconds`
    /// ago (relative to `now`). Returns the dropped hashes.
    pub fn expire(&mut self, now: Timestamp) -> Vec<Hash256> {
        let expiry = self.config.expiry_seconds;
        let expired: Vec<Hash256> = self
            .submitted_at
            .iter()
            .filter(|(_, &t)| now.saturating_sub(t) > expiry)
            .map(|(h, _)| *h)
            .collect();
        for hash in &expired {
            self.remove(hash);
        }
        expired
    }

    pub fn remove(&mut self, hash: &Hash256) -> Option<EmulatorTransaction> {
        let (sender, nonce) = self.by_hash.remove(hash)?;
        self.submitted_at.remove(hash);
        let slots = self.by_sender.get_mut(&sender)?;
        let tx = slots.remove(&nonce);
        if slots.is_empty() {
            self.by_sender.remove(&sender);
        }
        tx
    }

    /// Select transactions ready for inclusion in the next block, in a
    /// deterministic order: at each round, pick the still-eligible
    /// sender whose next transaction (by nonce order) offers the highest
    /// priority fee, ties broken by transaction hash for reproducibility.
    /// Never mutates `state` - callers apply nonce/balance effects when
    /// they actually execute the block.
    pub fn select_for_block(&self, max_count: usize, state: &WorldState) -> Vec<EmulatorTransaction> {
        let mut next_nonce: HashMap<Address, Nonce> = self
            .by_sender
            .keys()
            .map(|addr| (*addr, state.accounts.nonce_of(addr)))
            .collect();

        let mut selected = Vec::new();
        while selected.len() < max_count {
            let mut best: Option<&EmulatorTransaction> = None;
            for (sender, slots) in &self.by_sender {
                let want = *next_nonce.get(sender).unwrap_or(&0);
                if let Some(tx) = slots.get(&want) {
                    let better = match best {
                        None => true,
                        Some(b) => {
                            (tx.priority_fee, tx.hash.0) > (b.priority_fee, b.hash.0)
                        }
                    };
                    if better {
                        best = Some(tx);
                    }
                }
            }
            match best {
                Some(tx) => {
                    let sender = tx.sender;
                    let nonce = tx.nonce;
                    selected.push(tx.clone());
                    next_nonce.insert(sender, nonce + 1);
                }
                None => break,
            }
        }
        selected
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use web3emu_crypto::Keypair;
    use web3emu_tx::TransactionType;

    fn make_tx(kp: &Keypair, nonce: Nonce, priority_fee: u128, to: Address) -> EmulatorTransaction {
        let mut tx = EmulatorTransaction::new_unsigned(
            31337,
            nonce,
            kp.address(),
            kp.public_key_bytes(),
            Some(to),
            10,
            21000,
            1,
            priority_fee,
            vec![],
            0,
            TransactionType::Transfer,
        );
        tx.sign(kp).unwrap();
        tx
    }

    #[test]
    fn rejects_insufficient_balance() {
        let kp = Keypair::from_label("Alice");
        let state = WorldState::new();
        let mut mp = Mempool::new(MempoolConfig::default());
        let tx = make_tx(&kp, 0, 1, Address([9u8; 20]));
        let err = mp.submit(tx, 31337, &state, 0).unwrap_err();
        assert!(matches!(err, RejectionReason::InsufficientBalance { .. }));
    }

    #[test]
    fn accepts_and_orders_by_nonce_and_fee() {
        let kp = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(kp.address()).balance = 1_000_000;
        let mut mp = Mempool::new(MempoolConfig::default());
        let bob = Address([9u8; 20]);
        mp.submit(make_tx(&kp, 0, 5, bob), 31337, &state, 0).unwrap();
        mp.submit(make_tx(&kp, 1, 5, bob), 31337, &state, 0).unwrap();
        assert_eq!(mp.len(), 2);
        let selected = mp.select_for_block(10, &state);
        assert_eq!(selected.len(), 2);
        assert_eq!(selected[0].nonce, 0);
        assert_eq!(selected[1].nonce, 1);
    }

    #[test]
    fn replacement_requires_higher_fee() {
        let kp = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(kp.address()).balance = 1_000_000;
        let mut mp = Mempool::new(MempoolConfig::default());
        let bob = Address([9u8; 20]);
        mp.submit(make_tx(&kp, 0, 5, bob), 31337, &state, 0).unwrap();
        let low = make_tx(&kp, 0, 4, bob);
        assert!(mp.submit(low, 31337, &state, 0).is_err());
        let high = make_tx(&kp, 0, 10, bob);
        let replaced = mp.submit(high, 31337, &state, 0).unwrap();
        assert!(replaced.is_some());
        assert_eq!(mp.len(), 1);
    }

    #[test]
    fn duplicate_is_rejected() {
        let kp = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(kp.address()).balance = 1_000_000;
        let mut mp = Mempool::new(MempoolConfig::default());
        let tx = make_tx(&kp, 0, 5, Address([9u8; 20]));
        mp.submit(tx.clone(), 31337, &state, 0).unwrap();
        assert!(matches!(
            mp.submit(tx, 31337, &state, 0).unwrap_err(),
            RejectionReason::Duplicate
        ));
    }

    #[test]
    fn expiry_drops_old_transactions() {
        let kp = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(kp.address()).balance = 1_000_000;
        let mut mp = Mempool::new(MempoolConfig {
            max_size: 10,
            expiry_seconds: 100,
        });
        mp.submit(make_tx(&kp, 0, 5, Address([9u8; 20])), 31337, &state, 0)
            .unwrap();
        assert!(mp.expire(50).is_empty());
        let dropped = mp.expire(500);
        assert_eq!(dropped.len(), 1);
        assert!(mp.is_empty());
    }
}
