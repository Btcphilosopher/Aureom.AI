# apps/ (not yet built)

The spec calls for three TypeScript developer-tooling apps layered on
top of the Rust core over JSON-RPC (section 8-9, Phases 28-29):

- **console/** - a developer console: submit transactions, watch events,
  drive the wallet emulator.
- **explorer/** - a lightweight Web3 explorer (section 54): network,
  blocks, transactions, accounts, contracts, events, mempool, state
  screens, each backed directly by `web3emu-rpc` (`eth_getBlockByNumber`,
  `eth_getLogs`, `web3emu_status`, etc.) - never inventing state the RPC
  server doesn't already have (section 58's "never create fake state
  independently" rule).
- **wallet/** - a browser-based wallet simulator implementing a
  provider-style interface (`connect()`, `accounts()`, `chainId()`,
  `signTransaction()`, `sendTransaction()`, `switchNetwork()` - section
  38) over the same JSON-RPC surface.

None of these exist yet in this repository. This is a deliberate scope
cut for the current build (see `docs/ARCHITECTURE.md`'s roadmap section)
rather than a stub implementation - shipping a fake explorer would
violate the "never fake state" rule the spec itself calls out. The Rust
core (`web3emu-core` + `web3emu-rpc`) is complete enough that any of
these three can be built as an ordinary JSON-RPC client against
`web3emu start` without further backend changes.
