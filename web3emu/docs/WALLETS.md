# Wallets

`web3emu-wallet::EmulatorWallet` manages **SIMULATED ACCOUNTS**. It is a
development convenience, never a real wallet - see `docs/SECURITY.md`.

## Standard development accounts

Every fresh workspace (`web3emu init`) funds seven deterministic
accounts (`STANDARD_DEV_LABELS`):

```text
Alice  Bob  Treasury  Developer  ContractOwner  TestUser01  TestUser02
```

Each is derived by `Keypair::from_label(label)`: the label's SHA-256
digest is the Ed25519 signing key seed. **Same label, same key, every
time, in every workspace** - this is what makes fixtures and scenarios
reproducible, and exactly why these keys must never hold anything real:
anyone who reads this document knows the private key for "Alice." See
`fixtures/dev_accounts.json` for the resulting addresses (chain id
31337) - regenerate with `web3emu accounts` if you ever doubt them.

## Capabilities

```rust
let mut wallet = EmulatorWallet::with_dev_accounts();
wallet.import_test_account("SomeOtherLabel")?;      // deterministic
wallet.create_account("scratch-1", rng_seed)?;       // non-deterministic
wallet.balance_of("Alice", &network)?;
wallet.nonce_of("Alice", &network)?;
let tx = wallet.prepare_transaction("Alice", &network, Some(bob), 100, /* gas */ 100, 1, 0, vec![], 0, TransactionType::Transfer)?;
wallet.switch_network("web3emu-local-02");
```

`prepare_transaction` builds, signs, and returns a transaction in one
call, pulling `chain_id`/`nonce` from anything implementing
`WalletNetworkView` (`EmulatorNetwork` implements it) - submitting it to
a mempool is a separate, explicit step (`network.submit_transaction`).

## What persists across CLI invocations

The CLI (`web3emu` binary) only persists **network state** to disk
(`<data-dir>/state.json`) between separate command invocations, not
wallet state. `web3emu accounts`, `tx send --from <label>`, etc. all
re-derive the seven standard dev accounts fresh on every run - which is
transparent for deterministic labels (`import_test_account`) but means a
non-deterministic `create_account` scratch account made in one CLI
invocation will not exist in the next. Within a single long-running
process (`web3emu start`, or your own Rust program using
`web3emu-core`/`web3emu-wallet` directly), any wallet accounts you create
persist for that process's lifetime.

## Security markers

`web3emu_wallet::DEV_KEY_WARNING` and the account listing's `[SIMULATED
- ...]` suffix exist so no UI built on this crate can present a WEB3EMU
account as anything other than a test fixture. Do not remove or paraphrase
that marker in downstream tooling.
