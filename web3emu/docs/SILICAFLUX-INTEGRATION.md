# SilicaFlux Web3 integration (recipe, not built)

Section 53 asks for WEB3EMU to supply synthetic state that SilicaFlux
visualizes - blocks, wallets, transactions, contracts, network nodes,
assets, events. SilicaFlux itself is not part of this repository; this
document describes the integration boundary and the rule that makes it
safe: **SilicaFlux (Layer 3) must only ever render what Layer 1/2
actually produced - never invent state of its own** (section 58's
explicit rule, reiterated in `docs/ARCHITECTURE.md`'s layering section).

```text
WEB3EMU CORE  --(JSON-RPC, HTTP)-->  SILICAFLUX
```

## What to poll or subscribe to

WEB3EMU is HTTP/JSON-RPC only today (no WebSocket - see
`docs/ARCHITECTURE.md`'s roadmap), so a SilicaFlux client polls:

| SilicaFlux visual | WEB3EMU source |
|---|---|
| Blocks | `eth_getBlockByNumber("latest")`, then walk backwards by `parentHash`, or poll `eth_blockNumber` and fetch new heights |
| Transactions | `block.transactions` (hashes) -> `eth_getTransactionByHash` / `eth_getTransactionReceipt` per hash |
| Accounts / wallets | `eth_getBalance`, `eth_getTransactionCount` per address of interest (e.g. the dev accounts in `fixtures/dev_accounts.json`) |
| Contracts | `eth_getCode` (non-empty = contract), `web3emu state <addr> --json` via the CLI for full storage |
| Events | `eth_getLogs` filtered by address/event name/block range |
| Network summary | `web3emu_status` (chain id, block height, mempool size) |
| Nodes / liveness | Not applicable yet - WEB3EMU is single-node (see `docs/ARCHITECTURE.md`); render a single node until multi-node simulation exists |

## Minimal poll loop (pseudocode)

```text
loop:
  status = rpc("web3emu_status")
  if status.blockHeight > last_seen_height:
    for h in last_seen_height+1 ..= status.blockHeight:
      block = rpc("eth_getBlockByNumber", [hex(h)])
      render_block(block)
      for tx_hash in block.transactions:
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        render_transaction(receipt)
        for log in receipt.logs:
          render_event(log)
    last_seen_height = status.blockHeight
  sleep(poll_interval)
```

## Design principle carried over from the emulator itself

Section 78's rule applies directly to SilicaFlux: if a transaction was
submitted, show a transaction; if a block was mined, show a block; if
nothing happened, animate nothing. Every value SilicaFlux would render
is already available, unmodified, from the RPC calls above - there is
no reason for a visualization layer to synthesize activity.

As with the Aardvark recipe, everything needed on the WEB3EMU side
already exists; only the SilicaFlux-side client is out of scope for this
repository.
