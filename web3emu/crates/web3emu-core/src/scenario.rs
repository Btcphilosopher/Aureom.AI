//! The scenario/test DSL (sections 47-49) and its assertion engine.
//!
//! Grammar (one statement per line; blank lines and `#` comments
//! ignored):
//!
//! ```text
//! CREATE ACCOUNT <label> BALANCE <amount>
//! DEPLOY <contract-label> FROM <sender-label>
//! CALL <contract-label>.<method> FROM <sender-label>
//! TRANSFER <amount> FROM <sender-label> TO <recipient-label>
//! MINE <n> BLOCKS
//! ASSERT <label> BALANCE <op> <amount>
//! ASSERT <label> NONCE <op> <amount>
//! ASSERT BLOCK HEIGHT <op> <amount>
//! ```
//!
//! `<op>` is one of `== != >= <= > <`.
//!
//! # Deliberate simplifications (see `docs/SCENARIOS.md`)
//!
//! - `CALL` takes no arguments in the text DSL (use the Rust API with
//!   `web3emu_contract::encode_args` for parameterized calls).
//! - `DEPLOY`/`CALL`/`TRANSFER` are each submitted and immediately mined
//!   into their own block, so contract addresses from `DEPLOY` are
//!   available to a later `CALL` in the same scenario without a
//!   separate explicit `MINE` step. An explicit `MINE <n> BLOCKS` mines
//!   `n` *additional* blocks (useful to pad block height for
//!   assertions).

use crate::EmulatorNetwork;
use std::collections::HashMap;
use web3emu_contract::ContractInit;
use web3emu_execution::ContractCallData;
use web3emu_tx::TransactionType;
use web3emu_types::{Address, Balance, BlockHeight, Nonce};
use web3emu_wallet::EmulatorWallet;

// Deliberately small, self-consistent synthetic gas units (see
// `GasSchedule::default` in web3emu-execution) so the toy balances used
// in the section 48 example (Alice with a balance of 10000) can deploy
// and call contracts without needing unrealistically large fixtures.
const DEFAULT_GAS_LIMIT: u64 = 5_000;
const DEFAULT_MAX_FEE: u128 = 1;
const DEFAULT_PRIORITY_FEE: u128 = 0;
/// Plain transfers need even less headroom than contract calls.
const TRANSFER_GAS_LIMIT: u64 = 100;
const TRANSFER_MAX_FEE: u128 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CmpOp {
    Eq,
    Ne,
    Ge,
    Le,
    Gt,
    Lt,
}

impl CmpOp {
    fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "==" => CmpOp::Eq,
            "!=" => CmpOp::Ne,
            ">=" => CmpOp::Ge,
            "<=" => CmpOp::Le,
            ">" => CmpOp::Gt,
            "<" => CmpOp::Lt,
            _ => return None,
        })
    }

    fn eval<T: PartialOrd>(self, lhs: T, rhs: T) -> bool {
        match self {
            CmpOp::Eq => lhs == rhs,
            CmpOp::Ne => lhs != rhs,
            CmpOp::Ge => lhs >= rhs,
            CmpOp::Le => lhs <= rhs,
            CmpOp::Gt => lhs > rhs,
            CmpOp::Lt => lhs < rhs,
        }
    }
}

#[derive(Debug, Clone)]
pub enum ScenarioStep {
    CreateAccount { label: String, balance: Balance },
    Deploy { contract_label: String, from: String },
    Call { contract_label: String, method: String, from: String },
    Transfer { amount: Balance, from: String, to: String },
    Mine { blocks: u64 },
    AssertBalance { label: String, op: CmpOp, value: Balance },
    AssertNonce { label: String, op: CmpOp, value: Nonce },
    AssertBlockHeight { op: CmpOp, value: BlockHeight },
}

#[derive(Debug, thiserror::Error)]
pub enum ScenarioError {
    #[error("line {line}: {message}")]
    Parse { line: usize, message: String },
    #[error("unknown account label '{0}'")]
    UnknownAccount(String),
    #[error("unknown contract label '{0}' (not deployed, or not in the contract registry)")]
    UnknownContract(String),
    #[error("network error: {0}")]
    Network(#[from] crate::NetworkError),
    #[error(transparent)]
    Wallet(#[from] web3emu_wallet::WalletError),
}

pub fn parse(source: &str) -> Result<Vec<ScenarioStep>, ScenarioError> {
    let mut steps = Vec::new();
    for (idx, raw_line) in source.lines().enumerate() {
        let line_no = idx + 1;
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let tokens: Vec<&str> = line.split_whitespace().collect();
        let err = |msg: &str| ScenarioError::Parse {
            line: line_no,
            message: msg.to_string(),
        };

        match tokens.as_slice() {
            ["CREATE", "ACCOUNT", label, "BALANCE", amount] => {
                steps.push(ScenarioStep::CreateAccount {
                    label: label.to_string(),
                    balance: amount.parse().map_err(|_| err("invalid balance"))?,
                });
            }
            ["DEPLOY", label, "FROM", sender] => {
                steps.push(ScenarioStep::Deploy {
                    contract_label: label.to_string(),
                    from: sender.to_string(),
                });
            }
            ["CALL", target, "FROM", sender] => {
                let (contract_label, method) = target
                    .split_once('.')
                    .ok_or_else(|| err("expected <ContractLabel>.<method>"))?;
                steps.push(ScenarioStep::Call {
                    contract_label: contract_label.to_string(),
                    method: method.to_string(),
                    from: sender.to_string(),
                });
            }
            ["TRANSFER", amount, "FROM", from, "TO", to] => {
                steps.push(ScenarioStep::Transfer {
                    amount: amount.parse().map_err(|_| err("invalid amount"))?,
                    from: from.to_string(),
                    to: to.to_string(),
                });
            }
            ["MINE", n, block_word] if block_word.eq_ignore_ascii_case("blocks") || block_word.eq_ignore_ascii_case("block") => {
                steps.push(ScenarioStep::Mine {
                    blocks: n.parse().map_err(|_| err("invalid block count"))?,
                });
            }
            ["ASSERT", "BLOCK", "HEIGHT", op, value] => {
                steps.push(ScenarioStep::AssertBlockHeight {
                    op: CmpOp::parse(op).ok_or_else(|| err("invalid comparison operator"))?,
                    value: value.parse().map_err(|_| err("invalid block height"))?,
                });
            }
            ["ASSERT", label, "BALANCE", op, value] => {
                steps.push(ScenarioStep::AssertBalance {
                    label: label.to_string(),
                    op: CmpOp::parse(op).ok_or_else(|| err("invalid comparison operator"))?,
                    value: value.parse().map_err(|_| err("invalid balance"))?,
                });
            }
            ["ASSERT", label, "NONCE", op, value] => {
                steps.push(ScenarioStep::AssertNonce {
                    label: label.to_string(),
                    op: CmpOp::parse(op).ok_or_else(|| err("invalid comparison operator"))?,
                    value: value.parse().map_err(|_| err("invalid nonce"))?,
                });
            }
            _ => return Err(err("unrecognized statement")),
        }
    }
    Ok(steps)
}

#[derive(Debug, Clone)]
pub struct ScenarioReport {
    pub steps_run: usize,
    pub assertions_checked: usize,
    pub assertions_failed: Vec<String>,
    pub log: Vec<String>,
}

impl ScenarioReport {
    pub fn passed(&self) -> bool {
        self.assertions_failed.is_empty()
    }
}

/// Run a parsed scenario against a live network and wallet, using
/// `contract_registry` to resolve `DEPLOY <label>` statements to a
/// `ContractInit` (the CLI populates this from `contracts/*.web3` DSL
/// files and built-in Token/NFT constructors - see `docs/SCENARIOS.md`).
pub fn run(
    network: &mut EmulatorNetwork,
    wallet: &mut EmulatorWallet,
    contract_registry: &HashMap<String, ContractInit>,
    steps: &[ScenarioStep],
) -> Result<ScenarioReport, ScenarioError> {
    let mut deployed: HashMap<String, Address> = HashMap::new();
    let mut log = Vec::new();
    let mut assertions_checked = 0;
    let mut assertions_failed = Vec::new();

    let resolve_address = |wallet: &EmulatorWallet, deployed: &HashMap<String, Address>, label: &str| {
        wallet
            .address_of(label)
            .ok()
            .or_else(|| deployed.get(label).copied())
            .ok_or_else(|| ScenarioError::UnknownAccount(label.to_string()))
    };

    for step in steps {
        match step {
            ScenarioStep::CreateAccount { label, balance } => {
                let address = match wallet.import_test_account(label) {
                    Ok(a) => a,
                    Err(_) => wallet.address_of(label)?,
                };
                network.state.get_or_create_eoa(address).balance = *balance;
                log.push(format!("CREATE ACCOUNT {label} BALANCE {balance} -> {address}"));
            }
            ScenarioStep::Deploy { contract_label, from } => {
                let init = contract_registry
                    .get(contract_label)
                    .cloned()
                    .ok_or_else(|| ScenarioError::UnknownContract(contract_label.clone()))?;
                let tx = wallet.prepare_transaction(
                    from,
                    network,
                    None,
                    0,
                    DEFAULT_GAS_LIMIT,
                    DEFAULT_MAX_FEE,
                    DEFAULT_PRIORITY_FEE,
                    init.encode(),
                    network.clock,
                    TransactionType::ContractDeployment,
                )?;
                let tx_hash = tx.hash;
                network.submit_transaction(tx)?;
                network.mine_block(1);
                let receipt = network
                    .get_receipt(&tx_hash)
                    .expect("just-mined transaction has a receipt");
                let address = receipt
                    .contract_address
                    .ok_or_else(|| ScenarioError::UnknownContract(contract_label.clone()))?;
                deployed.insert(contract_label.clone(), address);
                log.push(format!("DEPLOY {contract_label} FROM {from} -> {address}"));
            }
            ScenarioStep::Call { contract_label, method, from } => {
                let address = *deployed
                    .get(contract_label)
                    .ok_or_else(|| ScenarioError::UnknownContract(contract_label.clone()))?;
                let call_data = ContractCallData {
                    method: method.clone(),
                    args: vec![],
                };
                let tx = wallet.prepare_transaction(
                    from,
                    network,
                    Some(address),
                    0,
                    DEFAULT_GAS_LIMIT,
                    DEFAULT_MAX_FEE,
                    DEFAULT_PRIORITY_FEE,
                    call_data.encode(),
                    network.clock,
                    TransactionType::ContractCall,
                )?;
                network.submit_transaction(tx)?;
                network.mine_block(1);
                log.push(format!("CALL {contract_label}.{method} FROM {from}"));
            }
            ScenarioStep::Transfer { amount, from, to } => {
                let recipient = resolve_address(wallet, &deployed, to)?;
                let tx = wallet.prepare_transaction(
                    from,
                    network,
                    Some(recipient),
                    *amount,
                    TRANSFER_GAS_LIMIT,
                    TRANSFER_MAX_FEE,
                    0,
                    vec![],
                    network.clock,
                    TransactionType::Transfer,
                )?;
                network.submit_transaction(tx)?;
                network.mine_block(1);
                log.push(format!("TRANSFER {amount} FROM {from} TO {to}"));
            }
            ScenarioStep::Mine { blocks } => {
                network.mine_blocks(*blocks, usize::MAX);
                log.push(format!("MINE {blocks} BLOCKS"));
            }
            ScenarioStep::AssertBalance { label, op, value } => {
                assertions_checked += 1;
                let address = resolve_address(wallet, &deployed, label)?;
                let actual = network.balance_of(&address);
                if !op.eval(actual, *value) {
                    assertions_failed.push(format!(
                        "ASSERT {label} BALANCE {op:?} {value}: actual balance is {actual}"
                    ));
                }
            }
            ScenarioStep::AssertNonce { label, op, value } => {
                assertions_checked += 1;
                let address = resolve_address(wallet, &deployed, label)?;
                let actual = network.nonce_of(&address);
                if !op.eval(actual, *value) {
                    assertions_failed.push(format!(
                        "ASSERT {label} NONCE {op:?} {value}: actual nonce is {actual}"
                    ));
                }
            }
            ScenarioStep::AssertBlockHeight { op, value } => {
                assertions_checked += 1;
                let actual = network.block_height();
                if !op.eval(actual, *value) {
                    assertions_failed.push(format!(
                        "ASSERT BLOCK HEIGHT {op:?} {value}: actual height is {actual}"
                    ));
                }
            }
        }
    }

    Ok(ScenarioReport {
        steps_run: steps.len(),
        assertions_checked,
        assertions_failed,
        log,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::GenesisConfig;

    const SPEC_EXAMPLE: &str = "
        CREATE ACCOUNT Alice BALANCE 10000
        CREATE ACCOUNT Bob BALANCE 1000
        TRANSFER 100 FROM Alice TO Bob
        MINE 10 BLOCKS
        ASSERT Bob BALANCE == 1100
    ";

    #[test]
    fn spec_example_scenario_passes() {
        let mut network = EmulatorNetwork::genesis(GenesisConfig::default());
        let mut wallet = EmulatorWallet::new();
        let steps = parse(SPEC_EXAMPLE).unwrap();
        let report = run(&mut network, &mut wallet, &HashMap::new(), &steps).unwrap();
        assert!(report.passed(), "assertions failed: {:?}", report.assertions_failed);
        assert_eq!(network.block_height(), 11); // 1 TRANSFER block + 10 MINE blocks
    }

    #[test]
    fn deploy_and_call_counter_scenario() {
        let mut network = EmulatorNetwork::genesis(GenesisConfig::default());
        let mut wallet = EmulatorWallet::new();
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
        let init = web3emu_contract::dsl::compile(source).unwrap();
        let mut registry = HashMap::new();
        registry.insert("Counter".to_string(), init);

        let dsl_source = "
            CREATE ACCOUNT Developer BALANCE 1000000
            DEPLOY Counter FROM Developer
            CALL Counter.increment FROM Developer
            CALL Counter.increment FROM Developer
        ";
        let steps = parse(dsl_source).unwrap();
        let report = run(&mut network, &mut wallet, &registry, &steps).unwrap();
        assert!(report.passed());
        assert_eq!(report.steps_run, 4);
    }

    #[test]
    fn failing_assertion_is_reported_not_panicked() {
        let mut network = EmulatorNetwork::genesis(GenesisConfig::default());
        let mut wallet = EmulatorWallet::new();
        let steps = parse("
            CREATE ACCOUNT Alice BALANCE 100
            ASSERT Alice BALANCE == 999
        ")
        .unwrap();
        let report = run(&mut network, &mut wallet, &HashMap::new(), &steps).unwrap();
        assert!(!report.passed());
        assert_eq!(report.assertions_failed.len(), 1);
    }
}
