//! Deploys the Level-1 DSL Counter contract (section 26) and calls it,
//! using `EmulatorWallet` (section 13) instead of building transactions
//! by hand - the pattern the CLI itself uses internally.
//!
//! Run with: `cargo run -p web3emu-core --example deploy_and_call_counter`

use web3emu_contract::dsl;
use web3emu_core::{EmulatorNetwork, GenesisConfig};
use web3emu_execution::ContractCallData;
use web3emu_tx::{ExecutionStatus, TransactionType};
use web3emu_wallet::EmulatorWallet;

const SOURCE: &str = "
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

fn main() {
    let wallet = EmulatorWallet::with_dev_accounts();
    let developer = wallet.address_of("Developer").unwrap();

    let mut network = EmulatorNetwork::genesis(GenesisConfig {
        initial_accounts: vec![(developer, 1_000_000)],
        ..Default::default()
    });

    let init = dsl::compile(SOURCE).expect("valid Level-1 DSL source");
    let deploy_tx = wallet
        .prepare_transaction(
            "Developer",
            &network,
            None,
            0,
            5_000,
            1,
            0,
            init.encode(),
            network.clock,
            TransactionType::ContractDeployment,
        )
        .unwrap();
    let deploy_hash = deploy_tx.hash;
    network.submit_transaction(deploy_tx).unwrap();
    network.mine_block(10);

    let contract_address = network
        .get_receipt(&deploy_hash)
        .and_then(|r| r.contract_address)
        .expect("deployment succeeded");
    println!("DEPLOYED Counter at {contract_address}");

    for _ in 0..3 {
        let call = ContractCallData {
            method: "increment".to_string(),
            args: vec![],
        };
        let tx = wallet
            .prepare_transaction(
                "Developer",
                &network,
                Some(contract_address),
                0,
                5_000,
                1,
                0,
                call.encode(),
                network.clock,
                TransactionType::ContractCall,
            )
            .unwrap();
        network.submit_transaction(tx).unwrap();
        network.mine_block(10);
    }

    let read = network.engine.simulate_call(
        &network.state,
        contract_address,
        developer,
        "get",
        &[],
        1_000,
        network.block_height(),
        network.clock,
    );
    match read {
        Ok(outcome) => {
            let value = u64::from_be_bytes(outcome.return_data.try_into().unwrap());
            println!("Counter value after 3 increments: {value}");
            assert_eq!(value, 3);
        }
        Err(e) => panic!("read failed: {e}"),
    }

    let receipts_ok = network
        .blocks
        .iter()
        .flat_map(|b| b.transactions.iter())
        .all(|h| matches!(network.get_receipt(h).unwrap().status, ExecutionStatus::Success));
    println!("All transactions succeeded: {receipts_ok}");
}
