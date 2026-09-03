# RPC

`web3emu start` runs a JSON-RPC 2.0 HTTP server (default
`http://127.0.0.1:8545`, configurable via `web3emu.yaml`'s `rpc` section
or `--host`/`--port`). Single requests and batch (array) requests are
both supported, per JSON-RPC 2.0.

```bash
curl -s -X POST http://127.0.0.1:8545 \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}'
```

Call `web3emu_compatibility` (or see `docs/COMPATIBILITY.md`) for the
authoritative, in-band list of every implemented method and exactly how
faithful it is.

## Method reference

| Method | Params | Notes |
|---|---|---|
| `eth_chainId` | `[]` | |
| `eth_blockNumber` | `[]` | |
| `eth_getBalance` | `[address, blockTag]` | only `blockTag: "latest"` is meaningful |
| `eth_getTransactionCount` | `[address, blockTag]` | only `"latest"` |
| `eth_getBlockByNumber` | `[blockTag]` | `blockTag` is `"latest"` or `0x`-hex height |
| `eth_getBlockByHash` | `[hash]` | |
| `eth_getTransactionByHash` | `[hash]` | |
| `eth_getTransactionReceipt` | `[hash]` | |
| `eth_sendRawTransaction` | `[hexEncodedTx]` | **deviates**: payload is `0x` + hex of the transaction's JSON encoding, not RLP |
| `eth_call` | `[{to, from?, data}]` | **deviates**: `data` is `0x` + hex of a JSON `{"method": "...", "args": "<hex>"}` envelope, not ABI-encoded calldata |
| `eth_estimateGas` | `[{to, from?, data}]` | same calldata convention as `eth_call` |
| `eth_getCode` | `[address]` | |
| `eth_getStorageAt` | `[address, hexKey]` | |
| `eth_getLogs` | `[{address?, eventName?, fromBlock?, toBlock?}]` | filters supported: address, event name, block range - no topic-pattern matching yet |
| `web3emu_mine` | `[n]` | non-standard: mine `n` blocks now, return them |
| `web3emu_status` | `[]` | non-standard: network summary |
| `web3emu_compatibility` | `[]` | non-standard: this table, machine-readable |

## Errors

Standard JSON-RPC error codes: `-32700` parse error, `-32600` invalid
request, `-32601` method not found, `-32602` invalid params, `-32603`
internal error. Errors are always structured (`{code, message}`), never
a bare string or a dropped connection.

## Building an `eth_call` / `eth_sendRawTransaction` payload

```rust
let call = web3emu_execution::ContractCallData {
    method: "balanceOf".into(),
    args: web3emu_contract::encode_args(&[web3emu_contract::ArgValue::Address(addr)]),
};
let data_hex = format!("0x{}", hex::encode(serde_json::to_vec(&call).unwrap()));
```

The CLI's `tx call`/`contract deploy*` subcommands build these payloads
for you - use `--json` output on `tx get` to see the exact shapes.
