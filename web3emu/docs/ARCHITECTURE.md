# Architecture

## The three-layer model

```text
LAYER 1 - PROTOCOL        the simulated Web3 state itself
LAYER 2 - INTEGRATION      RPC, wallet, contracts, developer APIs
LAYER 3 - VISUALISATION    explorer, console, external visualizers (SilicaFlux, Aardvark)
```

Layer 3 is always a *read-only consumer* of Layers 1-2. Nothing outside
`web3emu-core`/`web3emu-execution` is ever allowed to mutate canonical
state - a visualizer that "shows" activity that never happened through
the real pipeline would violate the emulator's core promise
(inspectable, reproducible state).

## The core loop

Every crate in this repository ultimately exists to run this loop
(`web3emu-core::EmulatorNetwork::{submit_transaction, mine_block}`):

```text
INPUT -> TRANSACTION -> VALIDATION -> MEMPOOL -> BLOCK -> EXECUTION
      -> STATE TRANSITION -> EVENTS -> RECEIPT -> FINAL STATE
```

## Crate map

```text
web3emu-types        primitives: Address, Hash256, ChainId, Balance, Gas, Nonce...
web3emu-crypto       SHA-256 hashing, Ed25519 signing, address derivation (replaceable)
web3emu-account      Account model (EOA / Contract), AccountStore
web3emu-state        WorldState, deterministic state root
web3emu-tx           EmulatorTransaction, TxStatus lifecycle, TransactionReceipt
web3emu-events       EventLog, EventFilter (eth_getLogs-style)
web3emu-trace        TransactionTrace, AccountDiff / StateDiff
web3emu-mempool      validation, nonce/fee ordering, expiry, replacement, rejection log
web3emu-block        EmulatorBlock, BlockBuilder, BlockProductionMode
web3emu-contract     ContractRuntime trait, NativeRuntime, Level-1 DSL, Token, NFT
web3emu-execution    StateTransitionEngine, GasSchedule, ExecutionBackend
web3emu-wallet       EmulatorWallet, deterministic dev accounts
web3emu-network      single-node latency/packet-loss/chaos impairment model
web3emu-rpc          JSON-RPC 2.0 server (subset of eth_* + web3emu_* methods)
web3emu-core         EmulatorNetwork orchestrator, scenario/assertion DSL, snapshots, replay
web3emu-cli          the `web3emu` binary
```

Dependency direction is strictly downward - `web3emu-core` depends on
everything above; nothing above depends back on `web3emu-core`. Wallet
and network state views are expressed as traits (`WalletNetworkView`) so
`web3emu-wallet` never needs to depend on `web3emu-core`.

## What's implemented vs. roadmap

This build completes Phases 1-23 of the spec's 35-phase plan (repository
scaffold through deterministic replay), plus JSON-RPC, the wallet
emulator, and the CLI (Phases 18-20). Everything above is real,
deterministic, and tested - not stubbed.

Deliberately **not** implemented in this pass (Phases 24-35), and not
faked:

| Area | Status | Why |
|---|---|---|
| Multi-node simulation (§40, §70-71) | Not built | `web3emu-network` models single-node impairment (latency/loss/chaos) only; multi-process peer state, divergence detection, and partitions are real distributed-systems work deserving their own design pass. |
| Chain reorganization (§72) | Not built | Needs multi-node/fork-choice machinery above. `EmulatorNetwork::fork()` gives you independent forks to compare by hand today. |
| WebSocket subscriptions (§37) | Not built | `web3emu-rpc` is HTTP/JSON-RPC only; `eth_getLogs` and polling `eth_blockNumber` cover the same data today. |
| Finality model (§73) | Not built | Every block is immediately final in the current single-node model; a PROPOSED/CONFIRMED/FINAL state machine only means something once multi-node consensus exists. |
| Background daemon (`stop`/`status` as separate processes) | Not built | `web3emu start` is a foreground process; see `docs/SECURITY.md` and the CLI's `stop` command output. |
| TypeScript console/explorer/wallet apps (§54-58, Phase 28-29) | Not built | See `apps/README.md`. The RPC surface they'd consume already exists. |
| EVM-compatible execution backend (§69, Level 5) | Not built | `ExecutionBackend` is defined and `NativeRuntime` implements it; an `EvmBackend` should wrap a mature, audited Rust EVM crate rather than a hand-rolled one - out of scope here. |
| RHINOQUANT export (§75) | Not built | `web3emu snapshot`/`--json` output on every inspect command already gives a machine-readable feed a downstream tool could consume. |
| Property-testing framework (proptest-style, §50) | Partial | The invariants in §50 (conservation, nonce monotonicity, determinism, receipt/block consistency) are each covered by targeted unit/integration tests (see `docs/TESTING.md`), not by a generative property-test harness. |
| Load-testing harness (§80) | Not built | No fabricated benchmark numbers are published anywhere in this repository, per the spec's own rule against that. |

If you build on top of this and need one of the above, start from the
seam already in place (`ExecutionBackend`, `WalletNetworkView`,
`web3emu-network`'s `NetworkSimulator`) rather than bypassing it.
