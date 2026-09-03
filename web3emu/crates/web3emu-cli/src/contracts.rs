//! Builds the contract registry a scenario's `DEPLOY <label>` statements
//! resolve against: every `.web3` DSL file in `--contracts-dir`
//! (labeled by its file stem), plus two always-available demonstration
//! fixtures, `DemoToken` and `DemoNFT` (sections 27-28), owned by the
//! `Treasury` dev account.

use std::collections::HashMap;
use std::path::Path;
use web3emu_contract::{dsl, nft::NftInit, token::TokenInit, ContractInit};
use web3emu_types::Address;

pub fn build_registry(contracts_dir: &Path, treasury: Address) -> HashMap<String, ContractInit> {
    let mut registry = HashMap::new();

    registry.insert(
        "DemoToken".to_string(),
        ContractInit::Token(TokenInit {
            name: "WEB3EMU Demo Token".to_string(),
            symbol: "W3T".to_string(),
            decimals: 18,
            initial_supply: 1_000_000_000,
            initial_holder: treasury,
            owner: treasury,
        }),
    );
    registry.insert(
        "DemoNFT".to_string(),
        ContractInit::Nft(NftInit {
            name: "WEB3EMU Demo NFT".to_string(),
            symbol: "W3NFT".to_string(),
            owner: treasury,
        }),
    );

    if let Ok(entries) = std::fs::read_dir(contracts_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("web3") {
                continue;
            }
            let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else {
                continue;
            };
            match std::fs::read_to_string(&path).ok().and_then(|src| dsl::compile(&src).ok()) {
                Some(init) => {
                    registry.insert(stem.to_string(), init);
                }
                None => {
                    eprintln!("warning: failed to compile contract DSL file {}", path.display());
                }
            }
        }
    }

    registry
}
