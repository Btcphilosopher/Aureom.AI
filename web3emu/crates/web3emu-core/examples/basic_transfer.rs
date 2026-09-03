//! The developer API (section 65) equivalent of `scenarios/basic_transfer.web3scenario`.
//!
//! Run with: `cargo run -p web3emu-core --example basic_transfer`

use web3emu_core::{EmulatorNetwork, GenesisConfig};
use web3emu_crypto::Keypair;
use web3emu_tx::{EmulatorTransaction, ExecutionStatus, TransactionType};

fn main() {
    let alice = Keypair::from_label("Alice");
    let bob = Keypair::from_label("Bob");

    let genesis = GenesisConfig {
        initial_accounts: vec![(alice.address(), 10_000), (bob.address(), 1_000)],
        ..Default::default()
    };
    let mut network = EmulatorNetwork::genesis(genesis);
    println!("LOCAL WEB3 NETWORK ONLINE (SIMULATION / DEVELOPMENT ONLY)");
    println!("chain_id={} block={}", network.chain_id(), network.block_height());

    let mut tx = EmulatorTransaction::new_unsigned(
        network.chain_id(),
        network.nonce_of(&alice.address()),
        alice.address(),
        alice.public_key_bytes(),
        Some(bob.address()),
        100,
        100,
        1,
        0,
        vec![],
        network.clock,
        TransactionType::Transfer,
    );
    tx.sign(&alice).expect("Alice signs her own transaction");

    network.submit_transaction(tx.clone()).expect("valid transfer is admitted to the mempool");
    println!("TRANSACTION SUBMITTED {}", tx.hash);

    let block = network.mine_block(10);
    println!("BLOCK CREATED height={} hash={}", block.height, block.block_hash);

    let receipt = network.get_receipt(&tx.hash).expect("mined transaction has a receipt");
    assert_eq!(receipt.status, ExecutionStatus::Success);
    println!("RECEIPT status={:?} gas_used={}", receipt.status, receipt.gas_used);
    println!("Bob's balance is now {}", network.balance_of(&bob.address()));
}
