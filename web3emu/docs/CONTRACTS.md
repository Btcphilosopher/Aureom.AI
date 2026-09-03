# Contracts

WEB3EMU does not implement a general-purpose VM. `web3emu-contract`
ships a small `NativeRuntime` execution backend with three hand-written
contract kinds, plus a narrow DSL that compiles into the first of them.

## Execution model

```rust
pub trait ExecutionBackend: Send + Sync {
    fn call(&self, init: &ContractInit, ctx: &mut CallContext, method: &str, args: &[u8])
        -> Result<CallOutcome, ContractError>;
}
```

`ContractInit` (JSON-encoded, stored as the deployed account's `code`)
is one of `Counter`, `Token`, `Nft`. `NativeRuntime` is the only
implemented backend today; `UnimplementedBackend` exists purely to make
the seam visible - a future `EvmBackend` (wrapping a mature, audited
Rust EVM crate rather than a hand-rolled one) or a richer deterministic
VM (spec section 68 Levels 2-4) would implement the same trait. The core
never assumes `NativeRuntime` specifically - `StateTransitionEngine` is
generic over `Box<dyn ExecutionBackend>`.

Gas: every call spends `gas_costs::BASE_CALL` plus per-operation costs
(`STORAGE_READ`, `STORAGE_WRITE`, `EVENT`) - see `docs/PROTOCOL.md`.

## Level-1 DSL (Counter contracts)

Grammar (exactly the spec's own example, generalized to any field/event
name):

```text
contract <Name>
state:
    <field>: integer
method:
    increment()
method:
    decrement()
method:
    get()
event:
    <EventName>(<field>)
```

**Deliberate limits**, so this stays honestly "Level 1":

- Exactly one `integer` state field.
- Exactly the method names `increment`, `decrement`, `get` - no custom
  method bodies, no arithmetic other than +1/-1, no conditionals.
  `decrement` saturates at zero rather than underflowing.
- No method arguments.
- One event, emitted on every state change, carrying the new value.

Compile with `web3emu_contract::dsl::compile(source)`, or via the CLI:

```bash
web3emu contract deploy contracts/Counter.web3 --from Developer
web3emu tx call --contract <address> --method increment --from Developer
```

## Token (section 27)

`web3emu_contract::token::TokenInit { name, symbol, decimals,
initial_supply, initial_holder, owner }`. Methods: `balanceOf`,
`transfer`, `approve`, `allowance`, `transferFrom`, `mint` (owner only),
`burn` (owner only). Emits `Transfer`/`Approval` events with
zero-padded-address topics. **A SIMULATED TOKEN** - it is a demonstration
fixture, not a real asset, and has no bridge to anything real.

```bash
web3emu contract deploy-token --name "Demo Coin" --symbol DMC --supply 1000000 --from Treasury
web3emu tx call --contract <address> --method transfer --from Treasury --args "address:<to>,u128:250"
```

## NFT (section 28)

`web3emu_contract::nft::NftInit { name, symbol, owner }`. Methods:
`mint` (owner only; takes a recipient and an opaque metadata URI, never
raw image bytes), `ownerOf`, `tokenURI`, `transfer`. Token IDs are
sequential `u64`s assigned at mint time.

```bash
web3emu contract deploy-nft --name "Demo NFT" --symbol DNFT --from Treasury
web3emu tx call --contract <address> --method mint --from Treasury --args "address:<to>,bytes:697066733a2f2f2e2e2e"
```

## Argument encoding

The Token/NFT methods and `tx call --args` use a small positional
encoding (`web3emu_contract::{ArgValue, encode_args, decode_args}`), not
a general ABI:

```text
--args "address:0xabc...,u128:100,bytes:68656c6c6f"
```

Each entry is `kind:value` with `kind` one of `address`, `u128`,
`bytes` (hex, no `0x` prefix required). This is intentionally simple -
if you need real ABI encoding, treat this as the seam to extend.

## Storage

Contract storage is `BTreeMap<Vec<u8>, Vec<u8>>` - deterministic
iteration, arbitrary byte keys/values. Inspect it with `web3emu state
<address> --json` (hex-encoded key/value pairs) or `web3emu trace
<tx-hash>` (per-operation `StorageRead`/`StorageWrite` trace steps).
