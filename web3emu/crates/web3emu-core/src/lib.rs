//! web3emu-core
//!
//! `EmulatorNetwork` (section 10) ties every other crate together into
//! the core simulation loop (section 87):
//!
//! ```text
//! INPUT -> TRANSACTION -> VALIDATION -> MEMPOOL -> BLOCK -> EXECUTION
//!       -> STATE TRANSITION -> EVENTS -> RECEIPT -> FINAL STATE
//! ```
//!
//! This crate also hosts the scenario/assertion engine (`scenario`
//! module) and deterministic snapshot/replay support.

pub mod scenario;

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use web3emu_account::Account;
use web3emu_block::{BlockBuilder, EmulatorBlock};
use web3emu_execution::{BlockContext, GasSchedule, StateTransitionEngine};
use web3emu_events::EventLog;
use web3emu_mempool::{Mempool, MempoolConfig, RejectionReason};
use web3emu_state::WorldState;
use web3emu_trace::TransactionTrace;
use web3emu_tx::{EmulatorTransaction, TransactionReceipt};
use web3emu_types::{Address, Balance, ChainId, Gas, Hash256, Nonce, Timestamp};
use web3emu_wallet::WalletNetworkView;

/// Deterministic genesis configuration (section 11). The same genesis
/// always produces the same initial state and the same genesis block
/// hash.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenesisConfig {
    pub chain_id: ChainId,
    pub network_name: String,
    pub initial_timestamp: Timestamp,
    pub initial_gas_limit: Gas,
    pub initial_base_fee: u128,
    pub initial_accounts: Vec<(Address, Balance)>,
    pub protocol_version: String,
    pub seed: u64,
}

impl Default for GenesisConfig {
    fn default() -> Self {
        GenesisConfig {
            chain_id: web3emu_types::DEFAULT_CHAIN_ID,
            network_name: "WEB3EMU LOCAL".to_string(),
            initial_timestamp: 0,
            initial_gas_limit: 30_000_000,
            initial_base_fee: 1_000_000_000,
            initial_accounts: vec![],
            protocol_version: web3emu_block::PROTOCOL_VERSION.to_string(),
            seed: 0,
        }
    }
}

/// One action taken against the network, recorded for deterministic
/// replay (section 81).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ReplayAction {
    Submit(EmulatorTransaction),
    Mine,
}

#[derive(Debug, thiserror::Error)]
pub enum NetworkError {
    #[error("rejected by mempool: {0}")]
    Rejected(#[from] RejectionReason),
    #[error("replay diverged: expected state root {expected}, got {got}")]
    ReplayDiverged { expected: String, got: String },
}

pub struct EmulatorNetwork {
    pub network_id: String,
    pub genesis: GenesisConfig,
    pub state: WorldState,
    pub mempool: Mempool,
    pub blocks: Vec<EmulatorBlock>,
    pub transactions: HashMap<Hash256, EmulatorTransaction>,
    pub receipts: HashMap<Hash256, TransactionReceipt>,
    pub traces: HashMap<Hash256, TransactionTrace>,
    /// All logs ever emitted, in emission order - backs `eth_getLogs`.
    pub logs: Vec<EventLog>,
    pub engine: StateTransitionEngine,
    pub gas_limit: Gas,
    pub base_fee: u128,
    pub proposer: Address,
    pub clock: Timestamp,
    replay_log: Vec<ReplayAction>,
}

impl EmulatorNetwork {
    /// Build a fresh network from genesis (section 11): deterministic
    /// state, block 0, empty mempool.
    pub fn genesis(genesis: GenesisConfig) -> Self {
        let mut state = WorldState::new();
        for (address, balance) in &genesis.initial_accounts {
            state.get_or_create_eoa(*address).balance = *balance;
        }
        let proposer = Address::ZERO;
        let genesis_block = BlockBuilder {
            parent_hash: Hash256::ZERO,
            height: 0,
            timestamp: genesis.initial_timestamp,
            proposer,
            gas_limit: genesis.initial_gas_limit,
            base_fee: genesis.initial_base_fee,
        }
        .build(state.state_root(), &[], &[]);

        EmulatorNetwork {
            network_id: "web3emu-local".to_string(),
            gas_limit: genesis.initial_gas_limit,
            base_fee: genesis.initial_base_fee,
            clock: genesis.initial_timestamp,
            proposer,
            state,
            mempool: Mempool::new(MempoolConfig::default()),
            blocks: vec![genesis_block],
            transactions: HashMap::new(),
            receipts: HashMap::new(),
            traces: HashMap::new(),
            logs: Vec::new(),
            engine: StateTransitionEngine::new(GasSchedule::default()),
            replay_log: Vec::new(),
            genesis,
        }
    }

    pub fn chain_id(&self) -> ChainId {
        self.genesis.chain_id
    }

    pub fn block_height(&self) -> u64 {
        self.blocks.len() as u64 - 1
    }

    pub fn latest_block(&self) -> &EmulatorBlock {
        self.blocks.last().expect("genesis block always present")
    }

    pub fn get_block(&self, height: u64) -> Option<&EmulatorBlock> {
        self.blocks.get(height as usize)
    }

    pub fn get_block_by_hash(&self, hash: &Hash256) -> Option<&EmulatorBlock> {
        self.blocks.iter().find(|b| &b.block_hash == hash)
    }

    pub fn get_account(&self, address: &Address) -> Option<&Account> {
        self.state.get(address)
    }

    pub fn balance_of(&self, address: &Address) -> Balance {
        self.state.balance_of(address)
    }

    pub fn nonce_of(&self, address: &Address) -> Nonce {
        self.state.accounts.nonce_of(address)
    }

    /// Validate and admit a signed transaction into the mempool (section
    /// 18). Does not execute it - call `mine_block` to include it.
    pub fn submit_transaction(&mut self, tx: EmulatorTransaction) -> Result<(), NetworkError> {
        self.transactions.insert(tx.hash, tx.clone());
        self.mempool
            .submit(tx.clone(), self.genesis.chain_id, &self.state, self.clock)?;
        self.replay_log.push(ReplayAction::Submit(tx));
        Ok(())
    }

    /// Mine exactly one block (section 20 MANUAL mode primitive - the
    /// other modes are scheduling policy layered on top of this, see
    /// `web3emu_block::should_produce` and the CLI's `mine`/`start`
    /// loop). Selects up to `max_txs` ready transactions from the
    /// mempool, executes them in order, and appends the resulting block.
    pub fn mine_block(&mut self, max_txs: usize) -> EmulatorBlock {
        self.clock += 1;
        let selected = self.mempool.select_for_block(max_txs, &self.state);

        let parent_hash = self.latest_block().block_hash;
        let height = self.block_height() + 1;
        let ctx = BlockContext {
            height,
            timestamp: self.clock,
            base_fee: self.base_fee,
            proposer: self.proposer,
        };

        let mut receipts = Vec::with_capacity(selected.len());
        let mut tx_hashes = Vec::with_capacity(selected.len());
        let mut log_index: u64 = 0;
        // Block hash is only known once every receipt is final, but
        // receipts want a block hash - we fill in a placeholder and
        // patch every receipt after the block hash is computed, which
        // keeps state transitions themselves independent of the
        // not-yet-known final block hash.
        for tx in &selected {
            self.mempool.remove(&tx.hash);
            let result = self
                .engine
                .apply_transaction(&mut self.state, tx, &ctx, Hash256::ZERO, log_index);
            log_index += result.events.len() as u64;
            self.logs.extend(result.events);
            self.traces.insert(tx.hash, result.trace);
            receipts.push(result.receipt);
            tx_hashes.push(tx.hash);
        }

        let block = BlockBuilder {
            parent_hash,
            height,
            timestamp: self.clock,
            proposer: self.proposer,
            gas_limit: self.gas_limit,
            base_fee: self.base_fee,
        }
        .build(self.state.state_root(), &tx_hashes, &receipts);

        for mut receipt in receipts {
            receipt.block_hash = block.block_hash;
            self.receipts.insert(receipt.transaction_hash, receipt);
        }

        self.blocks.push(block.clone());
        self.replay_log.push(ReplayAction::Mine);
        block
    }

    pub fn mine_blocks(&mut self, n: u64, max_txs_per_block: usize) -> Vec<EmulatorBlock> {
        (0..n).map(|_| self.mine_block(max_txs_per_block)).collect()
    }

    pub fn get_receipt(&self, hash: &Hash256) -> Option<&TransactionReceipt> {
        self.receipts.get(hash)
    }

    pub fn get_trace(&self, hash: &Hash256) -> Option<&TransactionTrace> {
        self.traces.get(hash)
    }

    pub fn get_transaction(&self, hash: &Hash256) -> Option<&EmulatorTransaction> {
        self.transactions.get(hash)
    }

    pub fn logs_matching(&self, filter: &web3emu_events::EventFilter) -> Vec<&EventLog> {
        self.logs.iter().filter(|l| filter.matches(l)).collect()
    }

    /// A conceptual fork (section 46): a fully independent deep clone of
    /// the network that can diverge freely. Cheap because state is
    /// in-memory; there is no shared backing store to copy-on-write.
    pub fn fork(&self) -> EmulatorNetwork {
        EmulatorNetwork {
            network_id: format!("{}-fork", self.network_id),
            genesis: self.genesis.clone(),
            state: self.state.clone(),
            mempool: self.mempool.clone(),
            blocks: self.blocks.clone(),
            transactions: self.transactions.clone(),
            receipts: self.receipts.clone(),
            traces: self.traces.clone(),
            logs: self.logs.clone(),
            engine: StateTransitionEngine::new(self.engine.gas_schedule),
            gas_limit: self.gas_limit,
            base_fee: self.base_fee,
            proposer: self.proposer,
            clock: self.clock,
            replay_log: self.replay_log.clone(),
        }
    }

    /// Export everything needed to deterministically reproduce this
    /// network's exact history from genesis (section 81).
    pub fn export_replay(&self) -> ReplayRecord {
        ReplayRecord {
            genesis: self.genesis.clone(),
            actions: self.replay_log.clone(),
            max_txs_per_block: usize::MAX,
        }
    }

    /// Re-run a recorded genesis + action sequence from scratch and
    /// return the resulting network. Compare `.latest_block().state_root`
    /// against the original to confirm determinism.
    pub fn replay(record: ReplayRecord) -> Result<Self, NetworkError> {
        let mut network = EmulatorNetwork::genesis(record.genesis);
        for action in record.actions {
            match action {
                ReplayAction::Submit(tx) => {
                    // Replays re-derive mempool admission; a transaction
                    // that was valid originally is valid again given the
                    // same deterministic state.
                    let _ = network.submit_transaction(tx);
                }
                ReplayAction::Mine => {
                    network.mine_block(record.max_txs_per_block);
                }
            }
        }
        Ok(network)
    }

    // ---- snapshots (section 45) -----------------------------------------

    pub fn snapshot(&self) -> NetworkSnapshot {
        NetworkSnapshot {
            network_id: self.network_id.clone(),
            genesis: self.genesis.clone(),
            state: self.state.clone(),
            blocks: self.blocks.clone(),
            transactions: self.transactions.clone(),
            receipts: self.receipts.clone(),
            traces: self.traces.clone(),
            logs: self.logs.clone(),
            gas_schedule: self.engine.gas_schedule,
            gas_limit: self.gas_limit,
            base_fee: self.base_fee,
            proposer: self.proposer,
            clock: self.clock,
            replay_log: self.replay_log.clone(),
        }
    }

    pub fn restore(snapshot: NetworkSnapshot) -> Self {
        EmulatorNetwork {
            network_id: snapshot.network_id,
            genesis: snapshot.genesis,
            state: snapshot.state,
            mempool: Mempool::new(MempoolConfig::default()),
            blocks: snapshot.blocks,
            transactions: snapshot.transactions,
            receipts: snapshot.receipts,
            traces: snapshot.traces,
            logs: snapshot.logs,
            engine: StateTransitionEngine::new(snapshot.gas_schedule),
            gas_limit: snapshot.gas_limit,
            base_fee: snapshot.base_fee,
            proposer: snapshot.proposer,
            clock: snapshot.clock,
            replay_log: snapshot.replay_log,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkSnapshot {
    pub network_id: String,
    pub genesis: GenesisConfig,
    pub state: WorldState,
    pub blocks: Vec<EmulatorBlock>,
    pub transactions: HashMap<Hash256, EmulatorTransaction>,
    pub receipts: HashMap<Hash256, TransactionReceipt>,
    pub traces: HashMap<Hash256, TransactionTrace>,
    pub logs: Vec<EventLog>,
    pub gas_schedule: GasSchedule,
    pub gas_limit: Gas,
    pub base_fee: u128,
    pub proposer: Address,
    pub clock: Timestamp,
    replay_log: Vec<ReplayAction>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayRecord {
    pub genesis: GenesisConfig,
    pub actions: Vec<ReplayAction>,
    #[serde(default = "default_max_txs")]
    pub max_txs_per_block: usize,
}

fn default_max_txs() -> usize {
    usize::MAX
}

/// Lets `web3emu-wallet` query network state without depending on this
/// crate.
impl WalletNetworkView for EmulatorNetwork {
    fn balance_of(&self, address: &Address) -> Balance {
        self.state.balance_of(address)
    }
    fn nonce_of(&self, address: &Address) -> Nonce {
        self.state.accounts.nonce_of(address)
    }
    fn chain_id(&self) -> ChainId {
        self.genesis.chain_id
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use web3emu_crypto::Keypair;
    use web3emu_tx::{ExecutionStatus, TransactionType};

    fn make_network() -> (EmulatorNetwork, Keypair) {
        let alice = Keypair::from_label("Alice");
        let genesis = GenesisConfig {
            initial_accounts: vec![(alice.address(), 1_000_000)],
            ..Default::default()
        };
        (EmulatorNetwork::genesis(genesis), alice)
    }

    #[test]
    fn genesis_block_is_deterministic() {
        let (net_a, _) = make_network();
        let (net_b, _) = make_network();
        assert_eq!(net_a.latest_block().block_hash, net_b.latest_block().block_hash);
        assert_eq!(net_a.block_height(), 0);
    }

    #[test]
    fn full_core_loop_transfer_and_mine() {
        let (mut net, alice) = make_network();
        let bob = Address([9u8; 20]);
        let mut tx = EmulatorTransaction::new_unsigned(
            net.chain_id(),
            0,
            alice.address(),
            alice.public_key_bytes(),
            Some(bob),
            1000,
            21000,
            2,
            1,
            vec![],
            0,
            TransactionType::Transfer,
        );
        tx.sign(&alice).unwrap();
        net.submit_transaction(tx.clone()).unwrap();
        assert_eq!(net.mempool.len(), 1);

        let block = net.mine_block(10);
        assert_eq!(net.mempool.len(), 0);
        assert_eq!(block.transactions, vec![tx.hash]);
        assert_eq!(net.balance_of(&bob), 1000);

        let receipt = net.get_receipt(&tx.hash).unwrap();
        assert_eq!(receipt.status, ExecutionStatus::Success);
        assert_eq!(receipt.block_hash, block.block_hash);
    }

    #[test]
    fn replay_reproduces_identical_state_root() {
        let (mut net, alice) = make_network();
        let bob = Address([9u8; 20]);
        for i in 0..3 {
            let mut tx = EmulatorTransaction::new_unsigned(
                net.chain_id(),
                i,
                alice.address(),
                alice.public_key_bytes(),
                Some(bob),
                10,
                21000,
                2,
                1,
                vec![],
                0,
                TransactionType::Transfer,
            );
            tx.sign(&alice).unwrap();
            net.submit_transaction(tx).unwrap();
            net.mine_block(10);
        }
        let original_root = net.state.state_root();
        let record = net.export_replay();
        let replayed = EmulatorNetwork::replay(record).unwrap();
        assert_eq!(replayed.state.state_root(), original_root);
        assert_eq!(replayed.block_height(), net.block_height());
    }

    #[test]
    fn snapshot_round_trips_through_json() {
        let (mut net, alice) = make_network();
        net.mine_block(10);
        let snap = net.snapshot();
        let json = serde_json::to_string(&snap).unwrap();
        let restored_snap: NetworkSnapshot = serde_json::from_str(&json).unwrap();
        let restored = EmulatorNetwork::restore(restored_snap);
        assert_eq!(restored.state.state_root(), net.state.state_root());
        assert_eq!(restored.balance_of(&alice.address()), net.balance_of(&alice.address()));
    }
}
