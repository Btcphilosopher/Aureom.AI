# Examples

Two ways to drive WEB3EMU programmatically, both showing the same core
loop (genesis -> transaction -> mempool -> block -> execution -> receipt):

## Rust developer API (section 65)

```bash
cargo run -p web3emu-core --example basic_transfer
cargo run -p web3emu-core --example deploy_and_call_counter
```

Source: `crates/web3emu-core/examples/`.

## CLI + scenario DSL (sections 47-49, 61)

```bash
cargo build --release
./target/release/web3emu --data-dir /tmp/web3emu-demo scenario scenarios/basic_transfer.web3scenario
./target/release/web3emu --data-dir /tmp/web3emu-demo scenario scenarios/counter_lifecycle.web3scenario --contracts-dir contracts
```

See `scenarios/` for the DSL files and `docs/SCENARIOS.md` for the
grammar.
