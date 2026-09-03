//! web3emu-block
//!
//! The block model (section 19) and block production modes (section 20).
//! The actual scheduling loop (timers, "mine every N ms") lives in
//! `web3emu-core`, which owns the mempool/engine/clock together; this
//! crate defines the shape of a block and the pure logic for deciding
//! *when* one should be produced given a mode and observed conditions.

use serde::{Deserialize, Serialize};
use web3emu_crypto::{fold_hashes, hash};
use web3emu_tx::TransactionReceipt;
use web3emu_types::{Address, BlockHeight, Gas, Hash256, Timestamp};

pub const PROTOCOL_VERSION: &str = "web3emu/0.1";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmulatorBlock {
    pub block_hash: Hash256,
    pub parent_hash: Hash256,
    pub height: BlockHeight,
    pub timestamp: Timestamp,
    pub proposer: Address,
    pub transactions: Vec<Hash256>,
    pub state_root: Hash256,
    pub transaction_root: Hash256,
    pub receipt_root: Hash256,
    pub gas_used: Gas,
    pub gas_limit: Gas,
    pub base_fee: u128,
    /// A deterministic fold of every log's topics in this block. NOT a
    /// production Bloom filter (no false-positive membership test) -
    /// just a fast, deterministic "did anything change" fingerprint. See
    /// `docs/COMPATIBILITY.md`.
    pub logs_digest: Hash256,
    pub protocol_version: String,
}

/// Everything needed to assemble a block once its transactions have all
/// been executed against a mutable `WorldState` (by the caller, usually
/// `web3emu-core`).
pub struct BlockBuilder {
    pub parent_hash: Hash256,
    pub height: BlockHeight,
    pub timestamp: Timestamp,
    pub proposer: Address,
    pub gas_limit: Gas,
    pub base_fee: u128,
}

impl BlockBuilder {
    pub fn build(
        self,
        state_root: Hash256,
        tx_hashes: &[Hash256],
        receipts: &[TransactionReceipt],
    ) -> EmulatorBlock {
        let transaction_root = fold_hashes(tx_hashes);
        let receipt_hashes: Vec<Hash256> = receipts
            .iter()
            .map(|r| hash(serde_json_bytes(r).as_slice()))
            .collect();
        let receipt_root = fold_hashes(&receipt_hashes);
        let gas_used: Gas = receipts.iter().map(|r| r.gas_used).sum();
        let topic_hashes: Vec<Hash256> = receipts
            .iter()
            .flat_map(|r| r.logs.iter().flat_map(|l| l.topics.clone()))
            .collect();
        let logs_digest = fold_hashes(&topic_hashes);

        let mut block = EmulatorBlock {
            block_hash: Hash256::ZERO,
            parent_hash: self.parent_hash,
            height: self.height,
            timestamp: self.timestamp,
            proposer: self.proposer,
            transactions: tx_hashes.to_vec(),
            state_root,
            transaction_root,
            receipt_root,
            gas_used,
            gas_limit: self.gas_limit,
            base_fee: self.base_fee,
            logs_digest,
            protocol_version: PROTOCOL_VERSION.to_string(),
        };
        block.block_hash = block.compute_hash();
        block
    }
}

fn serde_json_bytes<T: Serialize>(value: &T) -> Vec<u8> {
    serde_json::to_vec(value).unwrap_or_default()
}

impl EmulatorBlock {
    /// Recompute the block hash from its own fields (excluding
    /// `block_hash` itself). Used both when producing a block and to
    /// verify one hasn't been tampered with (e.g. after loading a
    /// snapshot).
    pub fn compute_hash(&self) -> Hash256 {
        let mut buf = Vec::new();
        buf.extend_from_slice(&self.parent_hash.0);
        buf.extend_from_slice(&self.height.to_be_bytes());
        buf.extend_from_slice(&self.timestamp.to_be_bytes());
        buf.extend_from_slice(&self.proposer.0);
        buf.extend_from_slice(&self.state_root.0);
        buf.extend_from_slice(&self.transaction_root.0);
        buf.extend_from_slice(&self.receipt_root.0);
        buf.extend_from_slice(&self.gas_used.to_be_bytes());
        buf.extend_from_slice(&self.gas_limit.to_be_bytes());
        buf.extend_from_slice(&self.base_fee.to_be_bytes());
        buf.extend_from_slice(&self.logs_digest.0);
        hash(&buf)
    }
}

/// Block production modes (section 20).
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum BlockProductionMode {
    /// Only mines when explicitly told to (`web3emu mine`).
    Manual,
    /// Mines on a fixed wall-clock interval, regardless of mempool
    /// contents (an empty block is a valid block).
    Automatic { interval_ms: u64 },
    /// Mines as soon as the mempool holds at least one transaction.
    TransactionTriggered,
    /// Mines once the mempool holds at least `size` transactions.
    Batch { size: usize },
}

/// Pure decision function: given the current mode and observed
/// conditions, should a block be produced right now? `elapsed_ms` is
/// time since the last block; `mempool_len` is the current mempool size.
pub fn should_produce(mode: BlockProductionMode, mempool_len: usize, elapsed_ms: u64) -> bool {
    match mode {
        BlockProductionMode::Manual => false,
        BlockProductionMode::Automatic { interval_ms } => elapsed_ms >= interval_ms,
        BlockProductionMode::TransactionTriggered => mempool_len > 0,
        BlockProductionMode::Batch { size } => mempool_len >= size,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_inputs_produce_same_block_hash() {
        let builder = || BlockBuilder {
            parent_hash: Hash256::ZERO,
            height: 1,
            timestamp: 100,
            proposer: Address([1u8; 20]),
            gas_limit: 30_000_000,
            base_fee: 1,
        };
        let b1 = builder().build(Hash256([2u8; 32]), &[], &[]);
        let b2 = builder().build(Hash256([2u8; 32]), &[], &[]);
        assert_eq!(b1.block_hash, b2.block_hash);
    }

    #[test]
    fn different_state_root_changes_hash() {
        let builder = || BlockBuilder {
            parent_hash: Hash256::ZERO,
            height: 1,
            timestamp: 100,
            proposer: Address([1u8; 20]),
            gas_limit: 30_000_000,
            base_fee: 1,
        };
        let b1 = builder().build(Hash256([2u8; 32]), &[], &[]);
        let b2 = builder().build(Hash256([3u8; 32]), &[], &[]);
        assert_ne!(b1.block_hash, b2.block_hash);
    }

    #[test]
    fn production_modes_decide_correctly() {
        assert!(!should_produce(BlockProductionMode::Manual, 5, 10_000));
        assert!(should_produce(
            BlockProductionMode::Automatic { interval_ms: 2000 },
            0,
            2000
        ));
        assert!(!should_produce(
            BlockProductionMode::Automatic { interval_ms: 2000 },
            0,
            1999
        ));
        assert!(should_produce(BlockProductionMode::TransactionTriggered, 1, 0));
        assert!(!should_produce(BlockProductionMode::TransactionTriggered, 0, 0));
        assert!(should_produce(BlockProductionMode::Batch { size: 10 }, 10, 0));
        assert!(!should_produce(BlockProductionMode::Batch { size: 10 }, 9, 0));
    }
}
