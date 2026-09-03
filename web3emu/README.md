# WEB3EMU

**A hard, deterministic, lightweight local Web3 integration emulator.**

WEB3EMU is a local sandbox that behaves *sufficiently* like a Web3
network for application development, wallet testing, transaction
simulation, smart-contract interaction and visualization - without real
funds, public networks, real wallets, or external RPC providers.

> ## SIMULATION / DEVELOPMENT ONLY
> Every account, key, balance and network here is synthetic. Nothing in
> this repository holds, moves or represents real value, and nothing
> here should ever be pointed at production infrastructure. See
> [`docs/SECURITY.md`](docs/SECURITY.md).

## What this is (and isn't)

WEB3EMU implements the core Web3 simulation loop end-to-end:

```text
account -> transaction -> mempool -> block -> execution
        -> state transition -> events -> receipt -> final state
```

with deterministic genesis, gas accounting, a small contract runtime
(Counter DSL, Token, NFT), execution tracing, state diffs, JSON-RPC, a
scenario/assertion DSL, and snapshot/replay support.

It is **not** a full Ethereum client, a production blockchain, or a
cryptocurrency. Where it borrows Web3 vocabulary (JSON-RPC method names,
`chainId`, gas), it deliberately does not claim compatibility it hasn't
earned - see [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## Quick start

```bash
cargo build --release
./target/release/web3emu init
./target/release/web3emu start
# in another shell:
./target/release/web3emu accounts
./target/release/web3emu tx send --from Alice --to Bob --value 500
./target/release/web3emu scenario scenarios/basic_transfer.web3scenario
```

`web3emu start` prints:

```text
LOCAL WEB3 NETWORK ONLINE (SIMULATION / DEVELOPMENT ONLY)
CHAIN ID: 31337
BLOCK: 0
STATE: CONSISTENT
RPC: http://127.0.0.1:8545
```

## Repository layout

```text
web3emu/
  crates/         Rust workspace (see docs/ARCHITECTURE.md)
  apps/           Non-Rust developer tooling (see apps/README.md - not yet built)
  scenarios/      Example scenario DSL files
  fixtures/       Deterministic dev-account fixtures
  contracts/      Example Level-1 DSL contract source files
  tests/          End-to-end smoke test
  docs/           Full documentation set
  examples/       Runnable Rust + CLI examples
```

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - crate map, layering, what's implemented vs roadmap
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) - genesis, accounts, transactions, state root, gas model, blocks
- [`docs/RPC.md`](docs/RPC.md) - JSON-RPC surface
- [`docs/CONTRACTS.md`](docs/CONTRACTS.md) - the Level-1 DSL, Token, NFT, execution backend
- [`docs/WALLETS.md`](docs/WALLETS.md) - the wallet emulator and dev accounts
- [`docs/SCENARIOS.md`](docs/SCENARIOS.md) - scenario/assertion DSL grammar
- [`docs/TESTING.md`](docs/TESTING.md) - how to run and extend the test suite
- [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) - exactly what is and isn't Web3-compatible
- [`docs/SECURITY.md`](docs/SECURITY.md) - the simulation boundary and key handling
- [`docs/AARDVARK-INTEGRATION.md`](docs/AARDVARK-INTEGRATION.md) - artwork tokenization integration recipe
- [`docs/SILICAFLUX-INTEGRATION.md`](docs/SILICAFLUX-INTEGRATION.md) - visualization integration recipe

## License

MIT (see individual crate manifests).
