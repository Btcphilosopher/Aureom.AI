//! Local, on-disk workspace for the CLI: a config file (section 62) plus
//! a persisted snapshot (section 45) so state survives between separate
//! `web3emu` invocations. There is no background daemon - each command
//! loads state, does its work, and (for state-changing commands) saves
//! it back before exiting. `web3emu start` is the exception: it holds
//! the loaded state for as long as the RPC server runs.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use web3emu_core::{EmulatorNetwork, GenesisConfig, NetworkSnapshot};
use web3emu_wallet::{EmulatorWallet, STANDARD_DEV_LABELS};

pub const DEFAULT_DATA_DIR: &str = ".web3emu";
/// Development accounts are funded generously so scenarios and manual
/// testing rarely run into gas/balance friction (section 14). This is a
/// SIMULATED balance with no real value.
pub const DEV_ACCOUNT_FUNDING: u128 = 1_000_000_000;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkSection {
    pub chain_id: u64,
    pub block_time: u64,
    pub gas_limit: u64,
    pub base_fee: u128,
}

impl Default for NetworkSection {
    fn default() -> Self {
        NetworkSection {
            chain_id: web3emu_types::DEFAULT_CHAIN_ID,
            block_time: 2,
            gas_limit: 30_000_000,
            base_fee: 1_000_000_000,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimulationSection {
    pub seed: u64,
    pub mode: String,
}

impl Default for SimulationSection {
    fn default() -> Self {
        SimulationSection {
            seed: 48291,
            mode: "deterministic".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcSection {
    pub host: String,
    pub port: u16,
}

impl Default for RpcSection {
    fn default() -> Self {
        RpcSection {
            host: "127.0.0.1".to_string(),
            port: 8545,
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub network: NetworkSection,
    #[serde(default)]
    pub simulation: SimulationSection,
    #[serde(default)]
    pub rpc: RpcSection,
}

pub struct Paths {
    pub dir: PathBuf,
}

impl Paths {
    pub fn new(dir: &Path) -> Self {
        Paths { dir: dir.to_path_buf() }
    }
    pub fn config_path(&self) -> PathBuf {
        self.dir.join("web3emu.yaml")
    }
    pub fn state_path(&self) -> PathBuf {
        self.dir.join("state.json")
    }
}

pub fn load_config(paths: &Paths) -> Config {
    fs::read_to_string(paths.config_path())
        .ok()
        .and_then(|s| serde_yaml::from_str(&s).ok())
        .unwrap_or_default()
}

fn genesis_from_config(cfg: &Config) -> GenesisConfig {
    let wallet = EmulatorWallet::with_dev_accounts();
    let initial_accounts = STANDARD_DEV_LABELS
        .iter()
        .filter_map(|label| wallet.address_of(label).ok())
        .map(|addr| (addr, DEV_ACCOUNT_FUNDING))
        .collect();
    GenesisConfig {
        chain_id: cfg.network.chain_id,
        network_name: "WEB3EMU LOCAL".to_string(),
        initial_timestamp: 0,
        initial_gas_limit: cfg.network.gas_limit,
        initial_base_fee: cfg.network.base_fee,
        initial_accounts,
        protocol_version: web3emu_block::PROTOCOL_VERSION.to_string(),
        seed: cfg.simulation.seed,
    }
}

/// Initialize a fresh workspace: write `web3emu.yaml`, build genesis
/// (funding every standard dev account), and persist the initial state.
/// Overwrites any existing workspace at `dir`.
pub fn init(dir: &Path, cfg: Config) -> std::io::Result<EmulatorNetwork> {
    fs::create_dir_all(dir)?;
    let paths = Paths::new(dir);
    fs::write(paths.config_path(), serde_yaml::to_string(&cfg).unwrap())?;
    let network = EmulatorNetwork::genesis(genesis_from_config(&cfg));
    save(&paths, &network)?;
    Ok(network)
}

pub fn save(paths: &Paths, network: &EmulatorNetwork) -> std::io::Result<()> {
    let snapshot = network.snapshot();
    let json = serde_json::to_string_pretty(&snapshot).expect("snapshot is always serializable");
    fs::write(paths.state_path(), json)
}

/// Load the workspace's persisted state, auto-initializing with default
/// configuration if none exists yet.
pub fn load(dir: &Path) -> std::io::Result<EmulatorNetwork> {
    let paths = Paths::new(dir);
    if let Ok(raw) = fs::read_to_string(paths.state_path()) {
        let snapshot: NetworkSnapshot =
            serde_json::from_str(&raw).map_err(std::io::Error::other)?;
        return Ok(EmulatorNetwork::restore(snapshot));
    }
    eprintln!(
        "No workspace found at {} - initializing with default configuration (run `web3emu init` to customize first).",
        dir.display()
    );
    init(dir, load_config(&paths))
}
