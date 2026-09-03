//! `web3emu` - the WEB3EMU developer CLI (section 61).
//!
//! # SIMULATION / DEVELOPMENT ONLY
//!
//! Every network, account and balance this CLI touches is local and
//! synthetic. Nothing here holds, moves, or represents real value.

mod contracts;
mod workspace;

use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use web3emu_contract::{encode_args, ArgValue};
use web3emu_core::EmulatorNetwork;
use web3emu_execution::ContractCallData;
use web3emu_tx::{ExecutionStatus, TransactionType};
use web3emu_types::Address;
use web3emu_wallet::EmulatorWallet;
use workspace::Paths;

// See web3emu_execution::GasSchedule::default for why these units are
// small - they are our own synthetic scale, not modeled on any real
// network's gas costs.
const CALL_GAS_LIMIT: u64 = 5_000;
const CALL_MAX_FEE: u128 = 1;
const CALL_PRIORITY_FEE: u128 = 0;
const TRANSFER_GAS_LIMIT: u64 = 100;
const TRANSFER_MAX_FEE: u128 = 1;

#[derive(Parser)]
#[command(
    name = "web3emu",
    version,
    about = "WEB3EMU - a local, deterministic Web3 integration emulator. SIMULATION / DEVELOPMENT ONLY."
)]
struct Cli {
    /// Workspace directory holding web3emu.yaml and state.json.
    #[arg(long, global = true, default_value = workspace::DEFAULT_DATA_DIR)]
    data_dir: PathBuf,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Create a fresh local workspace (genesis + funded dev accounts).
    Init {
        #[arg(long)]
        chain_id: Option<u64>,
    },
    /// Run the local JSON-RPC server in the foreground until interrupted.
    Start {
        #[arg(long)]
        host: Option<String>,
        #[arg(long)]
        port: Option<u16>,
        /// Mine a block automatically every N milliseconds while
        /// running (BlockProductionMode::Automatic, section 20). Omit
        /// for manual mining only (via RPC's `web3emu_mine` or a
        /// separate `web3emu mine` call - note the latter won't see
        /// transactions submitted to the running server; see
        /// docs/ARCHITECTURE.md).
        #[arg(long)]
        mine_interval_ms: Option<u64>,
    },
    /// Explain why there is no background daemon to stop yet.
    Stop,
    /// Delete the workspace and reinitialize from genesis.
    Reset,
    /// Print a one-line network summary.
    Status {
        #[arg(long)]
        json: bool,
    },
    /// List the standard development accounts and their balances.
    Accounts,
    /// Mine one or more blocks now.
    Mine {
        #[arg(default_value_t = 1)]
        count: u64,
    },
    /// Submit and inspect transactions.
    Tx {
        #[command(subcommand)]
        action: TxCommand,
    },
    /// Deploy contracts.
    Contract {
        #[command(subcommand)]
        action: ContractCommand,
    },
    /// Inspect a block by height ("latest" or a number).
    Block {
        height: String,
        #[arg(long)]
        json: bool,
    },
    /// Inspect an account by address or dev-account label.
    State {
        address: String,
        #[arg(long)]
        json: bool,
    },
    /// Save the current state to a snapshot file.
    Snapshot {
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Load a snapshot file as the active workspace state.
    Restore { path: PathBuf },
    /// Run a scenario DSL file (section 47-49).
    Scenario {
        path: PathBuf,
        #[arg(long, default_value = "contracts")]
        contracts_dir: PathBuf,
    },
    /// Print the execution trace for a transaction (section 32).
    Trace { hash: String },
}

#[derive(Subcommand)]
enum TxCommand {
    /// Submit a native-asset transfer and mine it immediately.
    Send {
        #[arg(long)]
        from: String,
        #[arg(long)]
        to: String,
        #[arg(long, default_value_t = 0)]
        value: u128,
    },
    /// Call a deployed contract's method and mine it immediately.
    Call {
        #[arg(long)]
        contract: String,
        #[arg(long)]
        method: String,
        #[arg(long)]
        from: String,
        /// Comma-separated positional args: `address:0x..`, `u128:123`,
        /// or `bytes:68656c6c6f` (hex).
        #[arg(long)]
        args: Option<String>,
        #[arg(long, default_value_t = 0)]
        value: u128,
    },
    /// Show a transaction and its receipt.
    Get { hash: String },
}

#[derive(Subcommand)]
enum ContractCommand {
    /// Deploy a Level-1 DSL contract from a `.web3` source file.
    Deploy {
        file: PathBuf,
        #[arg(long)]
        from: String,
    },
    /// Deploy a demonstration ERC20-style token (section 27).
    DeployToken {
        #[arg(long)]
        name: String,
        #[arg(long)]
        symbol: String,
        #[arg(long, default_value_t = 18)]
        decimals: u8,
        #[arg(long)]
        supply: u128,
        #[arg(long)]
        from: String,
    },
    /// Deploy a demonstration NFT contract (section 28).
    DeployNft {
        #[arg(long)]
        name: String,
        #[arg(long)]
        symbol: String,
        #[arg(long)]
        from: String,
    },
}

fn resolve_address(wallet: &EmulatorWallet, s: &str) -> Result<Address, String> {
    if let Ok(a) = wallet.address_of(s) {
        return Ok(a);
    }
    s.parse::<Address>().map_err(|_| format!("'{s}' is not a known dev-account label or a valid 0x-address"))
}

fn parse_call_args(s: &str) -> Result<Vec<ArgValue>, String> {
    s.split(',')
        .filter(|part| !part.trim().is_empty())
        .map(|part| {
            let (kind, value) = part.split_once(':').ok_or_else(|| format!("bad arg '{part}', expected kind:value"))?;
            match kind {
                "address" => value.parse::<Address>().map(ArgValue::Address).map_err(|e| e.to_string()),
                "u128" => value.parse::<u128>().map(ArgValue::U128).map_err(|e| e.to_string()),
                "bytes" => hex::decode(value.strip_prefix("0x").unwrap_or(value))
                    .map(ArgValue::Bytes)
                    .map_err(|e| e.to_string()),
                other => Err(format!("unknown arg kind '{other}'")),
            }
        })
        .collect()
}

fn print_json<T: serde::Serialize>(value: &T) {
    println!("{}", serde_json::to_string_pretty(value).unwrap());
}

fn main() {
    let cli = Cli::parse();
    if let Err(e) = run(cli) {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

fn run(cli: Cli) -> Result<(), String> {
    let paths = Paths::new(&cli.data_dir);

    match cli.command {
        Command::Init { chain_id } => {
            let mut cfg = workspace::load_config(&paths);
            if let Some(id) = chain_id {
                cfg.network.chain_id = id;
            }
            let network = workspace::init(&cli.data_dir, cfg).map_err(|e| e.to_string())?;
            println!(
                "LOCAL WEB3 NETWORK INITIALIZED (SIMULATION / DEVELOPMENT ONLY)\nCHAIN ID: {}\nBLOCK: {}\nSTATE: CONSISTENT\nWorkspace: {}",
                network.chain_id(),
                network.block_height(),
                cli.data_dir.display()
            );
            Ok(())
        }

        Command::Reset => {
            if cli.data_dir.exists() {
                std::fs::remove_dir_all(&cli.data_dir).map_err(|e| e.to_string())?;
            }
            let cfg = workspace::Config::default();
            workspace::init(&cli.data_dir, cfg).map_err(|e| e.to_string())?;
            println!("Workspace reset to genesis at {}", cli.data_dir.display());
            Ok(())
        }

        Command::Start { host, port, mine_interval_ms } => {
            let mut network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let cfg = workspace::load_config(&paths);
            let host = host.unwrap_or(cfg.rpc.host);
            let port = port.unwrap_or(cfg.rpc.port);
            network.gas_limit = cfg.network.gas_limit;
            network.base_fee = cfg.network.base_fee;
            println!(
                "LOCAL WEB3 NETWORK ONLINE (SIMULATION / DEVELOPMENT ONLY)\nCHAIN ID: {}\nBLOCK: {}\nSTATE: CONSISTENT\nRPC: http://{host}:{port}",
                network.chain_id(),
                network.block_height()
            );
            let shared = Arc::new(Mutex::new(network));

            if let Some(interval) = mine_interval_ms {
                let miner = Arc::clone(&shared);
                let save_paths = Paths::new(&cli.data_dir);
                std::thread::spawn(move || loop {
                    std::thread::sleep(std::time::Duration::from_millis(interval));
                    if let Ok(mut net) = miner.lock() {
                        net.mine_block(usize::MAX);
                        let _ = workspace::save(&save_paths, &net);
                    }
                });
            }

            web3emu_rpc::serve(&host, port, shared).map_err(|e| e.to_string())
        }

        Command::Stop => {
            println!(
                "`web3emu start` runs in the foreground - stop it with Ctrl+C.\nBackground daemon mode (a separate `stop`/`status` process pair) is not implemented yet; see docs/ARCHITECTURE.md roadmap."
            );
            Ok(())
        }

        Command::Status { json } => {
            let network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            if json {
                print_json(&serde_json::json!({
                    "networkId": network.network_id,
                    "chainId": network.chain_id(),
                    "blockHeight": network.block_height(),
                    "mempoolSize": network.mempool.len(),
                    "simulation": true,
                }));
            } else {
                println!(
                    "WEB3EMU LOCAL NETWORK\nBLOCK {:0>9}\nCHAIN ID {}\nSTATE CONSISTENT (SIMULATION)",
                    network.block_height(),
                    network.chain_id()
                );
            }
            Ok(())
        }

        Command::Accounts => {
            let network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let wallet = EmulatorWallet::with_dev_accounts();
            println!("{:<16} {:<44} {:>18} {:>8}", "LABEL", "ADDRESS", "BALANCE", "NONCE");
            for account in wallet.accounts() {
                let addr = account.address();
                println!(
                    "{:<16} {:<44} {:>18} {:>8}  [SIMULATED - {}]",
                    account.label,
                    addr.to_string(),
                    network.balance_of(&addr),
                    network.nonce_of(&addr),
                    web3emu_wallet::DEV_KEY_WARNING
                );
            }
            Ok(())
        }

        Command::Mine { count } => {
            let mut network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let blocks = network.mine_blocks(count, usize::MAX);
            workspace::save(&paths, &network).map_err(|e| e.to_string())?;
            for b in &blocks {
                println!("Mined block {} (hash {})", b.height, b.block_hash);
            }
            Ok(())
        }

        Command::Tx { action } => run_tx(&cli.data_dir, &paths, action),
        Command::Contract { action } => run_contract(&cli.data_dir, &paths, action),

        Command::Block { height, json } => {
            let network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let h = if height == "latest" {
                network.block_height()
            } else {
                height.parse::<u64>().map_err(|_| "height must be a number or 'latest'".to_string())?
            };
            match network.get_block(h) {
                Some(b) if json => {
                    print_json(b);
                    Ok(())
                }
                Some(b) => {
                    println!(
                        "BLOCK {}\nHASH {}\nPARENT {}\nTIMESTAMP {}\nPROPOSER {}\nTRANSACTIONS {}\nGAS USED {}/{}\nSTATE ROOT {}",
                        b.height, b.block_hash, b.parent_hash, b.timestamp, b.proposer,
                        b.transactions.len(), b.gas_used, b.gas_limit, b.state_root
                    );
                    Ok(())
                }
                None => Err(format!("no block at height {h}")),
            }
        }

        Command::State { address, json } => {
            let network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let wallet = EmulatorWallet::with_dev_accounts();
            let addr = resolve_address(&wallet, &address)?;
            match network.get_account(&addr) {
                Some(account) if json => {
                    print_json(account);
                    Ok(())
                }
                Some(account) => {
                    println!(
                        "ADDRESS {}\nKIND {:?}\nBALANCE {}\nNONCE {}\nSTORAGE ENTRIES {}",
                        account.address, account.kind, account.balance, account.nonce, account.storage.len()
                    );
                    Ok(())
                }
                None => {
                    println!("ADDRESS {addr}\nBALANCE 0\nNONCE 0\n(account has never been touched)");
                    Ok(())
                }
            }
        }

        Command::Snapshot { out } => {
            let network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let out_path = out.unwrap_or_else(|| PathBuf::from("web3emu-snapshot.json"));
            let snapshot = network.snapshot();
            std::fs::write(&out_path, serde_json::to_string_pretty(&snapshot).unwrap())
                .map_err(|e| e.to_string())?;
            println!("Snapshot written to {}", out_path.display());
            Ok(())
        }

        Command::Restore { path } => {
            let raw = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
            let snapshot: web3emu_core::NetworkSnapshot =
                serde_json::from_str(&raw).map_err(|e| e.to_string())?;
            let network = EmulatorNetwork::restore(snapshot);
            std::fs::create_dir_all(&cli.data_dir).map_err(|e| e.to_string())?;
            workspace::save(&paths, &network).map_err(|e| e.to_string())?;
            println!(
                "Restored workspace from {} (block height {})",
                path.display(),
                network.block_height()
            );
            Ok(())
        }

        Command::Scenario { path, contracts_dir } => {
            let source = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
            let steps = web3emu_core::scenario::parse(&source).map_err(|e| e.to_string())?;
            let mut network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let mut wallet = EmulatorWallet::with_dev_accounts();
            let treasury = wallet.address_of("Treasury").expect("standard dev accounts always include Treasury");
            let registry = contracts::build_registry(&contracts_dir, treasury);

            let report = web3emu_core::scenario::run(&mut network, &mut wallet, &registry, &steps)
                .map_err(|e| e.to_string())?;
            for line in &report.log {
                println!("{line}");
            }
            println!(
                "\n{} steps run, {} assertions checked, {} failed.",
                report.steps_run,
                report.assertions_checked,
                report.assertions_failed.len()
            );
            for failure in &report.assertions_failed {
                println!("  FAILED: {failure}");
            }
            workspace::save(&paths, &network).map_err(|e| e.to_string())?;
            if report.passed() {
                Ok(())
            } else {
                Err(format!("{} assertion(s) failed", report.assertions_failed.len()))
            }
        }

        Command::Trace { hash } => {
            let network = workspace::load(&cli.data_dir).map_err(|e| e.to_string())?;
            let h: web3emu_types::Hash256 = hash.parse().map_err(|_| "invalid transaction hash".to_string())?;
            match network.get_trace(&h) {
                Some(trace) => {
                    for (i, step) in trace.steps.iter().enumerate() {
                        println!("{i:>3}  {step:?}");
                    }
                    Ok(())
                }
                None => Err(format!("no trace recorded for {hash}")),
            }
        }
    }
}

fn run_tx(data_dir: &std::path::Path, paths: &Paths, action: TxCommand) -> Result<(), String> {
    match action {
        TxCommand::Send { from, to, value } => {
            let mut network = workspace::load(data_dir).map_err(|e| e.to_string())?;
            let mut wallet = EmulatorWallet::with_dev_accounts();
            if wallet.import_test_account(&from).is_err() { /* already a standard label, fine */ }
            let recipient = resolve_address(&wallet, &to)?;
            let tx = wallet
                .prepare_transaction(
                    &from,
                    &network,
                    Some(recipient),
                    value,
                    TRANSFER_GAS_LIMIT,
                    TRANSFER_MAX_FEE,
                    0,
                    vec![],
                    network.clock,
                    TransactionType::Transfer,
                )
                .map_err(|e| e.to_string())?;
            let hash = tx.hash;
            network.submit_transaction(tx).map_err(|e| e.to_string())?;
            network.mine_block(1);
            workspace::save(paths, &network).map_err(|e| e.to_string())?;
            print_receipt(&network, &hash);
            Ok(())
        }
        TxCommand::Call { contract, method, from, args, value } => {
            let mut network = workspace::load(data_dir).map_err(|e| e.to_string())?;
            let mut wallet = EmulatorWallet::with_dev_accounts();
            if wallet.import_test_account(&from).is_err() {}
            let contract_addr = resolve_address(&wallet, &contract)?;
            let parsed_args = args.map(|s| parse_call_args(&s)).transpose()?.unwrap_or_default();
            let call_data = ContractCallData {
                method,
                args: encode_args(&parsed_args),
            };
            let tx = wallet
                .prepare_transaction(
                    &from,
                    &network,
                    Some(contract_addr),
                    value,
                    CALL_GAS_LIMIT,
                    CALL_MAX_FEE,
                    CALL_PRIORITY_FEE,
                    call_data.encode(),
                    network.clock,
                    TransactionType::ContractCall,
                )
                .map_err(|e| e.to_string())?;
            let hash = tx.hash;
            network.submit_transaction(tx).map_err(|e| e.to_string())?;
            network.mine_block(1);
            workspace::save(paths, &network).map_err(|e| e.to_string())?;
            print_receipt(&network, &hash);
            Ok(())
        }
        TxCommand::Get { hash } => {
            let network = workspace::load(data_dir).map_err(|e| e.to_string())?;
            let h: web3emu_types::Hash256 = hash.parse().map_err(|_| "invalid transaction hash".to_string())?;
            let tx = network.get_transaction(&h).ok_or_else(|| "unknown transaction".to_string())?;
            print_json(tx);
            if let Some(receipt) = network.get_receipt(&h) {
                print_json(receipt);
            }
            Ok(())
        }
    }
}

fn run_contract(data_dir: &std::path::Path, paths: &Paths, action: ContractCommand) -> Result<(), String> {
    let (init, from) = match action {
        ContractCommand::Deploy { file, from } => {
            let source = std::fs::read_to_string(&file).map_err(|e| e.to_string())?;
            let init = web3emu_contract::dsl::compile(&source).map_err(|e| e.to_string())?;
            (init, from)
        }
        ContractCommand::DeployToken { name, symbol, decimals, supply, from } => {
            let wallet = EmulatorWallet::with_dev_accounts();
            let owner = resolve_address(&wallet, &from)?;
            let init = web3emu_contract::ContractInit::Token(web3emu_contract::token::TokenInit {
                name,
                symbol,
                decimals,
                initial_supply: supply,
                initial_holder: owner,
                owner,
            });
            (init, from)
        }
        ContractCommand::DeployNft { name, symbol, from } => {
            let wallet = EmulatorWallet::with_dev_accounts();
            let owner = resolve_address(&wallet, &from)?;
            let init = web3emu_contract::ContractInit::Nft(web3emu_contract::nft::NftInit { name, symbol, owner });
            (init, from)
        }
    };

    let mut network = workspace::load(data_dir).map_err(|e| e.to_string())?;
    let mut wallet = EmulatorWallet::with_dev_accounts();
    if wallet.import_test_account(&from).is_err() {}
    let tx = wallet
        .prepare_transaction(
            &from,
            &network,
            None,
            0,
            CALL_GAS_LIMIT,
            CALL_MAX_FEE,
            CALL_PRIORITY_FEE,
            init.encode(),
            network.clock,
            TransactionType::ContractDeployment,
        )
        .map_err(|e| e.to_string())?;
    let hash = tx.hash;
    network.submit_transaction(tx).map_err(|e| e.to_string())?;
    network.mine_block(1);
    workspace::save(paths, &network).map_err(|e| e.to_string())?;

    let receipt = network.get_receipt(&hash).expect("just-mined tx has a receipt");
    match (&receipt.status, receipt.contract_address) {
        (ExecutionStatus::Success, Some(addr)) => {
            println!("Deployed {} at {addr} (tx {hash})", init.kind_name());
            Ok(())
        }
        (ExecutionStatus::Reverted { reason }, _) => Err(format!("deployment reverted: {reason}")),
        _ => Err("deployment did not produce a contract address".to_string()),
    }
}

fn print_receipt(network: &EmulatorNetwork, hash: &web3emu_types::Hash256) {
    match network.get_receipt(hash) {
        Some(r) => {
            println!(
                "TX {hash}\nSTATUS {:?}\nGAS USED {}\nBLOCK {}",
                r.status, r.gas_used, r.block_height
            );
            if !r.return_data.is_empty() {
                println!("RETURN DATA 0x{}", hex::encode(&r.return_data));
            }
            for log in &r.logs {
                println!("  EVENT {} from {}", log.event_name, log.contract);
            }
        }
        None => println!("TX {hash} submitted but not yet mined"),
    }
}
