//! web3emu-tx
//!
//! The transaction model (section 16), its lifecycle (section 17), and
//! transaction receipts (section 31).

use serde::{Deserialize, Serialize};
use web3emu_crypto::{address_from_public_key, hash, verify, Keypair, Signature};
use web3emu_events::EventLog;
use web3emu_trace::StateDiff;
use web3emu_types::{Address, Balance, ChainId, Gas, Hash256, Nonce, Timestamp};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TransactionType {
    Transfer,
    ContractDeployment,
    ContractCall,
    ContractRead,
    /// Internal, non-user-originated simulation events (e.g. scenario
    /// engine bookkeeping). Never mined into a block.
    InternalSimulation,
}

/// Explicit lifecycle states (section 17). Every transaction the network
/// has ever seen has exactly one current status, and every rejection or
/// failure is a distinct, inspectable state - never a silent drop.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum TxStatus {
    Created,
    Signed,
    Submitted,
    Mempool,
    Validated,
    Included,
    Executed,
    ReceiptCreated,
    Final,
    Rejected(String),
    Failed(String),
}

impl TxStatus {
    pub fn is_terminal(&self) -> bool {
        matches!(self, TxStatus::Final | TxStatus::Rejected(_) | TxStatus::Failed(_))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmulatorTransaction {
    pub hash: Hash256,
    pub chain_id: ChainId,
    pub nonce: Nonce,
    pub sender: Address,
    pub sender_public_key: [u8; 32],
    /// `None` for `ContractDeployment`.
    pub recipient: Option<Address>,
    pub value: Balance,
    pub gas_limit: Gas,
    pub max_fee: u128,
    pub priority_fee: u128,
    pub data: Vec<u8>,
    pub signature: Option<Signature>,
    pub timestamp: Timestamp,
    pub tx_type: TransactionType,
}

#[derive(Debug, thiserror::Error)]
pub enum TxError {
    #[error("transaction is not signed")]
    NotSigned,
    #[error("signature does not match sender")]
    InvalidSignature,
    #[error("sender address does not match public key")]
    SenderMismatch,
}

/// Canonical, hash-only fields used to compute the transaction hash and
/// the signing payload. Excludes `hash` and `signature` themselves.
#[derive(Serialize)]
struct SigningPayload<'a> {
    chain_id: ChainId,
    nonce: Nonce,
    sender: Address,
    sender_public_key: [u8; 32],
    recipient: Option<Address>,
    value: Balance,
    gas_limit: Gas,
    max_fee: u128,
    priority_fee: u128,
    data: &'a [u8],
    timestamp: Timestamp,
    tx_type: TransactionType,
}

impl EmulatorTransaction {
    fn signing_bytes(&self) -> Vec<u8> {
        let payload = SigningPayload {
            chain_id: self.chain_id,
            nonce: self.nonce,
            sender: self.sender,
            sender_public_key: self.sender_public_key,
            recipient: self.recipient,
            value: self.value,
            gas_limit: self.gas_limit,
            max_fee: self.max_fee,
            priority_fee: self.priority_fee,
            data: &self.data,
            timestamp: self.timestamp,
            tx_type: self.tx_type,
        };
        serde_json::to_vec(&payload).expect("signing payload is always serializable")
    }

    /// Build an unsigned transaction. Call `.sign(&keypair)` to sign it,
    /// which also computes the final `hash`.
    #[allow(clippy::too_many_arguments)]
    pub fn new_unsigned(
        chain_id: ChainId,
        nonce: Nonce,
        sender: Address,
        sender_public_key: [u8; 32],
        recipient: Option<Address>,
        value: Balance,
        gas_limit: Gas,
        max_fee: u128,
        priority_fee: u128,
        data: Vec<u8>,
        timestamp: Timestamp,
        tx_type: TransactionType,
    ) -> Self {
        EmulatorTransaction {
            hash: Hash256::ZERO,
            chain_id,
            nonce,
            sender,
            sender_public_key,
            recipient,
            value,
            gas_limit,
            max_fee,
            priority_fee,
            data,
            signature: None,
            timestamp,
            tx_type,
        }
    }

    /// Sign the transaction with the given keypair, filling in
    /// `signature` and the final content-addressed `hash`.
    pub fn sign(&mut self, keypair: &Keypair) -> Result<(), TxError> {
        if keypair.address() != self.sender {
            return Err(TxError::SenderMismatch);
        }
        let bytes = self.signing_bytes();
        self.signature = Some(keypair.sign(&bytes));
        self.hash = hash(&bytes);
        Ok(())
    }

    /// Verify the signature and that `sender` really is derived from
    /// `sender_public_key`.
    pub fn verify_signature(&self) -> Result<(), TxError> {
        let signature = self.signature.as_ref().ok_or(TxError::NotSigned)?;
        if address_from_public_key(&self.sender_public_key) != self.sender {
            return Err(TxError::SenderMismatch);
        }
        let bytes = self.signing_bytes();
        verify(&self.sender_public_key, &bytes, signature).map_err(|_| TxError::InvalidSignature)
    }

    /// Recompute what `hash` should be, independent of what is currently
    /// stored - used to detect tampering after deserialization.
    pub fn recompute_hash(&self) -> Hash256 {
        hash(&self.signing_bytes())
    }
}

/// Execution status recorded in the receipt (section 31).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ExecutionStatus {
    Success,
    Reverted { reason: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionReceipt {
    pub transaction_hash: Hash256,
    pub block_hash: Hash256,
    pub block_height: u64,
    pub status: ExecutionStatus,
    pub gas_used: Gas,
    pub effective_gas_price: u128,
    /// Set only for successful `ContractDeployment` transactions.
    pub contract_address: Option<Address>,
    pub logs: Vec<EventLog>,
    /// Wall-clock execution time of the state transition, in
    /// microseconds. Simulator-internal timing, not a network property.
    pub execution_time_micros: u64,
    pub state_changes: StateDiff,
    pub failure_reason: Option<String>,
    /// Raw return value from a contract call/read/deployment, if any.
    /// Not part of the historical spec list in section 31, but needed to
    /// make `eth_call`-style reads and constructor returns useful.
    pub return_data: Vec<u8>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signed_transaction_verifies() {
        let kp = Keypair::from_label("Alice");
        let mut tx = EmulatorTransaction::new_unsigned(
            31337,
            0,
            kp.address(),
            kp.public_key_bytes(),
            Some(Address([2u8; 20])),
            100,
            21000,
            1,
            0,
            vec![],
            0,
            TransactionType::Transfer,
        );
        tx.sign(&kp).unwrap();
        assert!(tx.verify_signature().is_ok());
        assert_eq!(tx.hash, tx.recompute_hash());
    }

    #[test]
    fn tampering_breaks_hash_match() {
        let kp = Keypair::from_label("Alice");
        let mut tx = EmulatorTransaction::new_unsigned(
            31337,
            0,
            kp.address(),
            kp.public_key_bytes(),
            None,
            0,
            21000,
            1,
            0,
            vec![],
            0,
            TransactionType::ContractDeployment,
        );
        tx.sign(&kp).unwrap();
        tx.value = 999;
        assert_ne!(tx.hash, tx.recompute_hash());
        assert!(tx.verify_signature().is_err());
    }

    #[test]
    fn wrong_signer_is_rejected() {
        let alice = Keypair::from_label("Alice");
        let bob = Keypair::from_label("Bob");
        let mut tx = EmulatorTransaction::new_unsigned(
            31337,
            0,
            alice.address(),
            alice.public_key_bytes(),
            Some(Address([2u8; 20])),
            1,
            21000,
            1,
            0,
            vec![],
            0,
            TransactionType::Transfer,
        );
        assert!(tx.sign(&bob).is_err());
    }
}
