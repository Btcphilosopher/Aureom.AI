# Testing

## Unit and integration tests

```bash
cargo test --workspace
```

Every crate carries its own unit tests (crypto round-trips, mempool
ordering/replacement, contract method behavior, execution engine
admission/gas checks, RPC dispatch, scenario parsing). `web3emu-core`'s
`tests` module additionally exercises the full core loop end-to-end
(genesis -> transfer -> mine -> receipt), deterministic replay, and
snapshot round-tripping through JSON.

## End-to-end smoke test

```bash
bash tests/smoke_test.sh
```

Builds the release CLI and drives it exactly as a developer would:
`init` -> `accounts` -> `tx send` -> `contract deploy`/`tx call` ->
`mine` -> `scenario` -> `snapshot`/`restore`. This is the fastest way to
confirm a change hasn't broken the actual binary, not just the library
crates.

## Property-style invariants (section 50) and where they're checked

| Invariant | Covered by |
|---|---|
| Conservation - no balance from nowhere | `AccountStore::credit`/`debit` use checked arithmetic and return `Result`; `web3emu-execution`'s fee settlement is proven safe by construction (see `PROTOCOL.md`) rather than swallowing errors. `web3emu-mempool`'s `accepts_and_orders_by_nonce_and_fee` and `web3emu-execution`'s `transfer_moves_balance_and_charges_gas` tests assert exact before/after balances. |
| Nonce monotonicity | `web3emu-account::tests::nonce_increments_deterministically`; `web3emu-execution` only increments a sender's nonce once a transaction is admissible, verified by `insufficient_balance_reverts_with_receipt_not_panic` (nonce stays put on rejection). |
| No double-spend | `web3emu-mempool`'s per-`(sender, nonce)` keying plus the execution engine's balance check immediately before nonce consumption. |
| State determinism | `web3emu-state::tests::same_state_produces_same_root`; `web3emu-core::tests::replay_reproduces_identical_state_root` replays an entire recorded session from genesis and asserts an identical state root. |
| Receipt consistency | Every executed transaction (success or revert) produces exactly one `TransactionReceipt` - see `StateTransitionEngine::apply_transaction`'s single return path and `fail_fast`'s early-rejection receipts. |
| Block consistency | `EmulatorBlock::compute_hash` covers `parent_hash`; `web3emu-core::tests::full_core_loop_transfer_and_mine` checks a mined block's transaction list and hash. |
| Gas cannot exceed limit without failure | `web3emu-execution`'s intrinsic-gas-floor check and per-path `gas > tx.gas_limit` checks (transfer, deployment, contract call via `web3emu-contract`'s `charge`) - see `PROTOCOL.md`. |
| Event consistency | Events are only ever produced as part of a successful `CallOutcome` inside the same state transition that wrote the storage they describe - `web3emu-execution`'s `deploy_and_call_counter_contract` test checks event count and name. |

This project does not (yet) use a generative property-testing framework
(e.g. `proptest`) - the table above is targeted unit/integration
coverage of each named invariant, not exhaustive input-space search. See
`docs/ARCHITECTURE.md`'s roadmap table.

## What is not benchmarked

No load-testing numbers (section 80) are published anywhere in this
repository. Generate your own with `cargo build --release` and your own
harness against `web3emu-core` or the RPC server before trusting any
throughput claim - including ones you might be tempted to write here.
