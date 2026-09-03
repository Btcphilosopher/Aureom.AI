//! web3emu-execution
//!
//! The state transition engine (section 23) and gas model (section 22) -
//! the heart of WEB3EMU. `StateTransitionEngine::apply_transaction` takes
//! `(previous state, transaction, block context)` and deterministically
//! produces `(new state, receipt, events, trace)`.

use serde::{Deserialize, Serialize};
use web3emu_account::{Account, AccountKind};
use web3emu_contract::{
    CallContext, ContractError, ContractInit, ExecutionBackend, NativeRuntime,
};
use web3emu_crypto::hash;
use web3emu_events::EventLog;
use web3emu_state::WorldState;
use web3emu_trace::{diff_account, TraceStep, TransactionTrace};
use web3emu_tx::{EmulatorTransaction, ExecutionStatus, TransactionReceipt, TransactionType};
use web3emu_types::{Address, BlockHeight, Gas, Hash256, Timestamp};

/// Payload carried in `EmulatorTransaction::data` for `ContractCall` and
/// `ContractRead` transactions. Not a general ABI - a plain,
/// self-describing envelope naming the method and its already-encoded
/// arguments (see `web3emu_contract::{encode_args, decode_args}`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractCallData {
    pub method: String,
    pub args: Vec<u8>,
}

impl ContractCallData {
    pub fn encode(&self) -> Vec<u8> {
        serde_json::to_vec(self).expect("ContractCallData always serializes")
    }

    pub fn decode(data: &[u8]) -> Result<Self, ExecutionError> {
        serde_json::from_slice(data).map_err(|e| ExecutionError::Malformed(e.to_string()))
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct GasSchedule {
    /// Charged on every transaction, before any type-specific cost.
    pub intrinsic: Gas,
    pub transfer: Gas,
    pub contract_deployment_base: Gas,
    pub contract_deployment_per_byte: Gas,
}

impl Default for GasSchedule {
    fn default() -> Self {
        // These are small, self-consistent synthetic units - NOT modeled
        // on any real network's gas costs (see docs/COMPATIBILITY.md).
        // Chosen so a handful of transactions don't require unrealistic
        // toy account balances in scenarios and examples.
        GasSchedule {
            intrinsic: 21,
            transfer: 0,
            contract_deployment_base: 100,
            contract_deployment_per_byte: 1,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct BlockContext {
    pub height: BlockHeight,
    pub timestamp: Timestamp,
    pub base_fee: u128,
    pub proposer: Address,
}

#[derive(Debug, thiserror::Error)]
pub enum ExecutionError {
    #[error("malformed transaction data: {0}")]
    Malformed(String),
}

pub struct ExecutionResult {
    pub receipt: TransactionReceipt,
    pub trace: TransactionTrace,
    pub events: Vec<EventLog>,
}

pub struct StateTransitionEngine {
    backend: Box<dyn ExecutionBackend>,
    pub gas_schedule: GasSchedule,
}

impl Default for StateTransitionEngine {
    fn default() -> Self {
        StateTransitionEngine {
            backend: Box::new(NativeRuntime),
            gas_schedule: GasSchedule::default(),
        }
    }
}

impl StateTransitionEngine {
    pub fn new(gas_schedule: GasSchedule) -> Self {
        StateTransitionEngine {
            backend: Box::new(NativeRuntime),
            gas_schedule,
        }
    }

    pub fn with_backend(backend: Box<dyn ExecutionBackend>, gas_schedule: GasSchedule) -> Self {
        StateTransitionEngine {
            backend,
            gas_schedule,
        }
    }

    /// Deterministically derive a fresh contract address from the
    /// deploying sender and their nonce at deployment time. Not intended
    /// to match any specific production network's derivation scheme.
    pub fn derive_contract_address(sender: &Address, nonce: u64) -> Address {
        let mut buf = Vec::with_capacity(28);
        buf.extend_from_slice(&sender.0);
        buf.extend_from_slice(&nonce.to_be_bytes());
        let digest = hash(&buf);
        let mut out = [0u8; 20];
        out.copy_from_slice(&digest.0[12..32]);
        Address(out)
    }

    /// Apply one transaction to `state`, mutating it in place, and
    /// return the receipt/trace/events produced. `block_hash` is passed
    /// in because the block engine computes it only after all
    /// transactions in the block have been executed (it depends on the
    /// resulting receipt/state roots) - see `web3emu-block`.
    pub fn apply_transaction(
        &self,
        state: &mut WorldState,
        tx: &EmulatorTransaction,
        ctx: &BlockContext,
        block_hash: Hash256,
        log_index_start: u64,
    ) -> ExecutionResult {
        let started = std::time::Instant::now();
        let mut trace = TransactionTrace::new();

        let sender_before = state.get(&tx.sender).cloned();

        // --- signature check -------------------------------------------------
        let sig_ok = tx.verify_signature().is_ok();
        trace.push(TraceStep::AccountValidation {
            address: tx.sender,
            ok: sig_ok,
            detail: if sig_ok {
                "signature valid".into()
            } else {
                "signature invalid".into()
            },
        });
        if !sig_ok {
            return self.fail_fast(
                state,
                tx,
                ctx,
                block_hash,
                trace,
                started,
                "invalid signature",
                sender_before,
            );
        }

        // --- nonce check --------------------------------------------------
        let expected_nonce = state.accounts.nonce_of(&tx.sender);
        let nonce_ok = tx.nonce == expected_nonce;
        trace.push(TraceStep::NonceCheck {
            address: tx.sender,
            expected: expected_nonce,
            got: tx.nonce,
            ok: nonce_ok,
        });
        if !nonce_ok {
            return self.fail_fast(
                state,
                tx,
                ctx,
                block_hash,
                trace,
                started,
                "nonce mismatch",
                sender_before,
            );
        }

        // --- balance check (value + max possible fee) ---------------------
        let max_cost = tx.value + tx.gas_limit as u128 * tx.max_fee;
        let available = state.balance_of(&tx.sender);
        let balance_ok = available >= max_cost;
        trace.push(TraceStep::BalanceCheck {
            address: tx.sender,
            required: max_cost,
            available,
            ok: balance_ok,
        });
        if !balance_ok {
            return self.fail_fast(
                state,
                tx,
                ctx,
                block_hash,
                trace,
                started,
                "insufficient balance",
                sender_before,
            );
        }

        // A transaction that can never cover its own intrinsic cost is
        // rejected before it starts, the same way the other admission
        // checks above are - not executed-and-charged-anyway.
        if tx.gas_limit < self.gas_schedule.intrinsic {
            return self.fail_fast(
                state,
                tx,
                ctx,
                block_hash,
                trace,
                started,
                "gas limit is below the intrinsic gas cost",
                sender_before,
            );
        }

        // Transaction is admissible: consume the nonce regardless of what
        // happens next (mirrors common Web3 semantics: reverts still cost
        // gas and consume a nonce).
        state.accounts.increment_nonce(&tx.sender).ok();

        let effective_gas_price = ctx.base_fee.saturating_add(tx.priority_fee).min(tx.max_fee);

        let outcome = match tx.tx_type {
            TransactionType::Transfer => self.execute_transfer(state, tx),
            TransactionType::ContractDeployment => self.execute_deployment(state, tx, &mut trace),
            TransactionType::ContractCall => {
                self.execute_call(state, tx, ctx, &mut trace, false)
            }
            TransactionType::ContractRead => {
                self.execute_call(state, tx, ctx, &mut trace, true)
            }
            TransactionType::InternalSimulation => Ok(Applied {
                gas_used: 0,
                contract_address: None,
                raw_events: vec![],
                return_data: vec![],
            }),
        };

        let (status, gas_used, contract_address, raw_events, return_data, failure_reason) =
            match outcome {
                Ok(applied) => (
                    ExecutionStatus::Success,
                    applied.gas_used,
                    applied.contract_address,
                    applied.raw_events,
                    applied.return_data,
                    None,
                ),
                Err(reason) => (
                    ExecutionStatus::Reverted {
                        reason: reason.clone(),
                    },
                    tx.gas_limit, // revert charges the full gas limit, matching common Web3 semantics
                    None,
                    vec![],
                    vec![],
                    Some(reason),
                ),
            };

        trace.push(TraceStep::StateUpdate {
            detail: format!("gas_used={gas_used}, status={status:?}"),
        });

        // --- fee settlement -------------------------------------------------
        // Safe by construction: the balance check above reserved
        // `gas_limit * max_fee`, and `gas_used <= gas_limit` while
        // `effective_gas_price <= max_fee`, so `fee` never exceeds what
        // was reserved. A failure here means an engine invariant broke,
        // not a user error - so it is not swallowed.
        let fee = gas_used as u128 * effective_gas_price;
        state
            .accounts
            .debit(&tx.sender, fee)
            .expect("gas fee must not exceed the balance reserved for it at admission time");
        state.accounts.credit(&ctx.proposer, fee).ok();

        let events: Vec<EventLog> = raw_events
            .into_iter()
            .enumerate()
            .map(|(i, raw)| EventLog {
                contract: contract_address.unwrap_or(tx.recipient.unwrap_or(Address::ZERO)),
                event_name: raw.event_name,
                topics: raw.topics,
                data: raw.data,
                block: ctx.height,
                transaction: tx.hash,
                log_index: log_index_start + i as u64,
            })
            .collect();
        for e in &events {
            trace.push(TraceStep::Event {
                contract: e.contract,
                event_name: e.event_name.clone(),
            });
        }

        let mut state_changes = Vec::new();
        if let Some(d) = diff_account(tx.sender, sender_before.as_ref(), state.get(&tx.sender)) {
            state_changes.push(d);
        }
        if let Some(recipient) = tx.recipient.or(contract_address) {
            if recipient != tx.sender {
                // best-effort: we did not snapshot recipient "before", so
                // this diff only captures the field values, not a
                // before/after comparison across this call. Callers that
                // need precise per-account before/after should snapshot
                // via `WorldState::checkpoint` prior to calling.
                if let Some(after) = state.get(&recipient) {
                    state_changes.push(web3emu_trace::AccountDiff {
                        address: recipient,
                        balance_before: None,
                        balance_after: Some(after.balance),
                        nonce_before: None,
                        nonce_after: Some(after.nonce),
                        storage_changes: vec![],
                    });
                }
            }
        }

        let receipt = TransactionReceipt {
            transaction_hash: tx.hash,
            block_hash,
            block_height: ctx.height,
            status,
            gas_used,
            effective_gas_price,
            contract_address,
            logs: events.clone(),
            execution_time_micros: started.elapsed().as_micros() as u64,
            state_changes,
            failure_reason,
            return_data,
        };

        ExecutionResult {
            receipt,
            trace,
            events,
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn fail_fast(
        &self,
        state: &mut WorldState,
        tx: &EmulatorTransaction,
        ctx: &BlockContext,
        block_hash: Hash256,
        mut trace: TransactionTrace,
        started: std::time::Instant,
        reason: &str,
        sender_before: Option<Account>,
    ) -> ExecutionResult {
        trace.push(TraceStep::Note(format!("transaction rejected before execution: {reason}")));
        let state_changes = diff_account(tx.sender, sender_before.as_ref(), state.get(&tx.sender))
            .into_iter()
            .collect();
        let receipt = TransactionReceipt {
            transaction_hash: tx.hash,
            block_hash,
            block_height: ctx.height,
            status: ExecutionStatus::Reverted {
                reason: reason.to_string(),
            },
            gas_used: 0,
            effective_gas_price: 0,
            contract_address: None,
            logs: vec![],
            execution_time_micros: started.elapsed().as_micros() as u64,
            state_changes,
            failure_reason: Some(reason.to_string()),
            return_data: vec![],
        };
        ExecutionResult {
            receipt,
            trace,
            events: vec![],
        }
    }

    fn execute_transfer(&self, state: &mut WorldState, tx: &EmulatorTransaction) -> Result<Applied, String> {
        let recipient = tx.recipient.ok_or_else(|| "transfer requires a recipient".to_string())?;
        let gas = self.gas_schedule.intrinsic + self.gas_schedule.transfer;
        if gas > tx.gas_limit {
            return Err("out of gas: transfer exceeds gas limit".to_string());
        }
        state
            .accounts
            .debit(&tx.sender, tx.value)
            .map_err(|e| e.to_string())?;
        state
            .accounts
            .credit(&recipient, tx.value)
            .map_err(|e| e.to_string())?;
        Ok(Applied {
            gas_used: gas,
            contract_address: None,
            raw_events: vec![],
            return_data: vec![],
        })
    }

    fn execute_deployment(
        &self,
        state: &mut WorldState,
        tx: &EmulatorTransaction,
        trace: &mut TransactionTrace,
    ) -> Result<Applied, String> {
        let init = ContractInit::decode(&tx.data).map_err(|e| e.to_string())?;

        let gas = self.gas_schedule.intrinsic
            + self.gas_schedule.contract_deployment_base
            + self.gas_schedule.contract_deployment_per_byte * tx.data.len() as Gas;
        if gas > tx.gas_limit {
            return Err("out of gas: contract deployment exceeds gas limit".to_string());
        }

        let address = Self::derive_contract_address(&tx.sender, tx.nonce);
        let mut account = Account::new_contract(address, tx.data.clone());
        if let ContractInit::Token(t) = &init {
            web3emu_contract::token::initialize(t, &mut account.storage);
        }
        if tx.value > 0 {
            state.accounts.debit(&tx.sender, tx.value).map_err(|e| e.to_string())?;
            account.balance = tx.value;
        }
        state.insert(account);
        trace.push(TraceStep::ContractCall {
            contract: address,
            method: format!("<deploy:{}>", init.kind_name()),
        });
        Ok(Applied {
            gas_used: gas,
            contract_address: Some(address),
            raw_events: vec![],
            return_data: address.0.to_vec(),
        })
    }

    fn execute_call(
        &self,
        state: &mut WorldState,
        tx: &EmulatorTransaction,
        ctx: &BlockContext,
        trace: &mut TransactionTrace,
        read_only: bool,
    ) -> Result<Applied, String> {
        let recipient = tx.recipient.ok_or_else(|| "contract call requires a recipient".to_string())?;
        let call_data = ContractCallData::decode(&tx.data).map_err(|e| e.to_string())?;
        trace.push(TraceStep::ContractCall {
            contract: recipient,
            method: call_data.method.clone(),
        });

        // Read-only calls execute against a scratch copy of state so no
        // storage mutation, balance transfer, or event persists.
        let mut scratch;
        let working_state: &mut WorldState = if read_only {
            scratch = state.checkpoint();
            &mut scratch
        } else {
            state
        };

        let account = working_state
            .get_mut(&recipient)
            .filter(|a| a.kind == AccountKind::Contract)
            .ok_or_else(|| "recipient is not a contract".to_string())?;
        let init = ContractInit::decode(account.code.as_deref().unwrap_or_default())
            .map_err(|e| e.to_string())?;

        let mut call_ctx = CallContext {
            contract_address: recipient,
            caller: tx.sender,
            storage: &mut account.storage,
            block: ctx.height,
            timestamp: ctx.timestamp,
            gas_limit: tx.gas_limit.saturating_sub(self.gas_schedule.intrinsic),
        };

        let call_result = self
            .backend
            .call(&init, &mut call_ctx, &call_data.method, &call_data.args)
            .map_err(map_contract_error)?;

        if !read_only && tx.value > 0 {
            working_state.accounts.debit(&tx.sender, tx.value).map_err(|e| e.to_string())?;
            working_state.accounts.credit(&recipient, tx.value).map_err(|e| e.to_string())?;
        }

        Ok(Applied {
            gas_used: self.gas_schedule.intrinsic + call_result.gas_used,
            contract_address: None,
            raw_events: if read_only { vec![] } else { call_result.events },
            return_data: call_result.return_data,
        })
    }
}

impl StateTransitionEngine {
    /// Execute a contract call against a read-only checkpoint of `state`
    /// without requiring a signed transaction, a nonce, or any fee
    /// accounting - the moral equivalent of `eth_call`/`eth_estimateGas`
    /// (section 34). Nothing here is ever persisted.
    pub fn simulate_call(
        &self,
        state: &WorldState,
        contract: Address,
        caller: Address,
        method: &str,
        args: &[u8],
        gas_limit: Gas,
        block: BlockHeight,
        timestamp: Timestamp,
    ) -> Result<web3emu_contract::CallOutcome, String> {
        let mut scratch = state.checkpoint();
        let account = scratch
            .get_mut(&contract)
            .filter(|a| a.kind == AccountKind::Contract)
            .ok_or_else(|| "target is not a contract".to_string())?;
        let init = ContractInit::decode(account.code.as_deref().unwrap_or_default())
            .map_err(|e| e.to_string())?;
        let mut call_ctx = CallContext {
            contract_address: contract,
            caller,
            storage: &mut account.storage,
            block,
            timestamp,
            gas_limit,
        };
        self.backend
            .call(&init, &mut call_ctx, method, args)
            .map_err(map_contract_error)
    }
}

struct Applied {
    gas_used: Gas,
    contract_address: Option<Address>,
    raw_events: Vec<web3emu_contract::RawEvent>,
    return_data: Vec<u8>,
}

fn map_contract_error(e: ContractError) -> String {
    e.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use web3emu_contract::{dsl, encode_args};
    use web3emu_crypto::Keypair;

    fn ctx() -> BlockContext {
        BlockContext {
            height: 1,
            timestamp: 0,
            base_fee: 1,
            proposer: Address([250u8; 20]),
        }
    }

    #[test]
    fn transfer_moves_balance_and_charges_gas() {
        let engine = StateTransitionEngine::default();
        let alice = Keypair::from_label("Alice");
        let bob = Address([2u8; 20]);
        let mut state = WorldState::new();
        state.get_or_create_eoa(alice.address()).balance = 1_000_000;

        let mut tx = EmulatorTransaction::new_unsigned(
            31337,
            0,
            alice.address(),
            alice.public_key_bytes(),
            Some(bob),
            1000,
            50_000,
            2,
            1,
            vec![],
            0,
            TransactionType::Transfer,
        );
        tx.sign(&alice).unwrap();

        let result = engine.apply_transaction(&mut state, &tx, &ctx(), Hash256::ZERO, 0);
        assert_eq!(result.receipt.status, ExecutionStatus::Success);
        assert_eq!(state.balance_of(&bob), 1000);
        assert_eq!(state.accounts.nonce_of(&alice.address()), 1);
        assert!(state.balance_of(&alice.address()) < 1_000_000 - 1000); // gas was charged
    }

    #[test]
    fn deploy_and_call_counter_contract() {
        let engine = StateTransitionEngine::default();
        let alice = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(alice.address()).balance = 10_000_000;

        let source = "
            contract Counter
            state:
                value: integer
            method:
                increment()
            method:
                get()
            event:
                CounterChanged(value)
        ";
        let init = dsl::compile(source).unwrap();

        let mut deploy_tx = EmulatorTransaction::new_unsigned(
            31337,
            0,
            alice.address(),
            alice.public_key_bytes(),
            None,
            0,
            200_000,
            2,
            1,
            init.encode(),
            0,
            TransactionType::ContractDeployment,
        );
        deploy_tx.sign(&alice).unwrap();
        let deploy_result = engine.apply_transaction(&mut state, &deploy_tx, &ctx(), Hash256::ZERO, 0);
        assert_eq!(deploy_result.receipt.status, ExecutionStatus::Success);
        let contract_addr = deploy_result.receipt.contract_address.unwrap();

        let call_data = ContractCallData {
            method: "increment".into(),
            args: encode_args(&[]),
        };
        let mut call_tx = EmulatorTransaction::new_unsigned(
            31337,
            1,
            alice.address(),
            alice.public_key_bytes(),
            Some(contract_addr),
            0,
            100_000,
            2,
            1,
            call_data.encode(),
            0,
            TransactionType::ContractCall,
        );
        call_tx.sign(&alice).unwrap();
        let call_result = engine.apply_transaction(&mut state, &call_tx, &ctx(), Hash256::ZERO, 0);
        assert_eq!(call_result.receipt.status, ExecutionStatus::Success);
        assert_eq!(call_result.events.len(), 1);
        assert_eq!(call_result.events[0].event_name, "CounterChanged");
    }

    #[test]
    fn insufficient_balance_reverts_with_receipt_not_panic() {
        let engine = StateTransitionEngine::default();
        let alice = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(alice.address()).balance = 10;

        let mut tx = EmulatorTransaction::new_unsigned(
            31337,
            0,
            alice.address(),
            alice.public_key_bytes(),
            Some(Address([2u8; 20])),
            1000,
            21000,
            1,
            0,
            vec![],
            0,
            TransactionType::Transfer,
        );
        tx.sign(&alice).unwrap();
        let result = engine.apply_transaction(&mut state, &tx, &ctx(), Hash256::ZERO, 0);
        assert!(matches!(result.receipt.status, ExecutionStatus::Reverted { .. }));
        assert_eq!(result.receipt.gas_used, 0);
        // nonce not consumed since the tx never became admissible
        assert_eq!(state.accounts.nonce_of(&alice.address()), 0);
    }

    #[test]
    fn contract_read_does_not_mutate_state() {
        let engine = StateTransitionEngine::default();
        let alice = Keypair::from_label("Alice");
        let mut state = WorldState::new();
        state.get_or_create_eoa(alice.address()).balance = 10_000_000;

        let source = "
            contract Counter
            state:
                value: integer
            method:
                increment()
            method:
                get()
            event:
                CounterChanged(value)
        ";
        let init = dsl::compile(source).unwrap();
        let mut deploy_tx = EmulatorTransaction::new_unsigned(
            31337, 0, alice.address(), alice.public_key_bytes(), None, 0, 200_000, 2, 1,
            init.encode(), 0, TransactionType::ContractDeployment,
        );
        deploy_tx.sign(&alice).unwrap();
        let deploy_result = engine.apply_transaction(&mut state, &deploy_tx, &ctx(), Hash256::ZERO, 0);
        let contract_addr = deploy_result.receipt.contract_address.unwrap();

        let root_before = state.state_root();
        let read_data = ContractCallData { method: "get".into(), args: vec![] }.encode();
        let mut read_tx = EmulatorTransaction::new_unsigned(
            31337, 1, alice.address(), alice.public_key_bytes(), Some(contract_addr), 0,
            100_000, 2, 1, read_data, 0, TransactionType::ContractRead,
        );
        read_tx.sign(&alice).unwrap();
        let read_result = engine.apply_transaction(&mut state, &read_tx, &ctx(), Hash256::ZERO, 0);
        assert_eq!(read_result.receipt.status, ExecutionStatus::Success);
        // nonce still increments (the read tx was "admitted"), but no
        // contract storage mutation occurred - state root differs only by
        // the fee/nonce bookkeeping, not by a leftover counter write. We
        // can't compare full roots directly here (fee changes them too),
        // so we assert directly on storage instead.
        assert!(state.get(&contract_addr).unwrap().storage.is_empty());
        let _ = root_before;
    }
}
