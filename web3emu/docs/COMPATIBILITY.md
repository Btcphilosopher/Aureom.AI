# Compatibility

WEB3EMU is best described as an **Ethereum-inspired local JSON-RPC
interface**, not an Ethereum-compatible one. This document exists so
that claim is never a guess - every deviation below is deliberate and
tested against, not accidental.

## Cryptography

| Primitive | Common production choice | WEB3EMU | Why |
|---|---|---|---|
| Hashing | Keccak-256 | SHA-256 (`sha2`, RustCrypto) | Mature, widely audited crate; no reason to match a different hash for a simulator that doesn't need trie compatibility. |
| Signatures | secp256k1 (ECDSA) | Ed25519 (`ed25519-dalek`) | Simpler, faster, and equally mature for a local dev tool; addresses are still 20 bytes so tooling expecting that shape works. |
| Address derivation | `keccak256(pubkey)[12:]` | `sha256(pubkey)[12:]` | Same shape (last 20 bytes of a hash), different hash - see above. |

If you need byte-identical addresses/signatures to a real network, this
is not that tool. `web3emu-crypto` isolates the provider specifically so
it could be swapped later without touching the rest of the workspace.

## State / block structure

| Concept | Common production choice | WEB3EMU | Why |
|---|---|---|---|
| State root | Merkle-Patricia trie | Sequential SHA-256 fold over sorted accounts | Deterministic and sufficient to detect divergence; a real trie buys nothing for a single in-memory process with no light-client proofs to serve. |
| Logs bloom | Bloom filter (probabilistic membership) | Sequential hash fold ("logs digest") | Same rationale - no false-positive membership test is needed locally when you can just filter the log list directly. |

## JSON-RPC

See `docs/RPC.md` for the full method table. Two deliberate deviations
worth calling out specifically:

- **`eth_sendRawTransaction`** expects `0x` + hex of the transaction's
  JSON encoding, not an RLP-encoded production transaction.
- **`eth_call` / `eth_estimateGas`** expect `data` to be `0x` + hex of a
  JSON `{"method", "args"}` envelope (`web3emu_execution::ContractCallData`),
  not ABI-encoded calldata - WEB3EMU does not implement ABI encoding (see
  `docs/CONTRACTS.md`'s note on `ArgValue`).

Everything else in the method table behaves the way its production
counterpart's documentation describes, within the stated limits (e.g.
only the `"latest"` block tag is meaningful for balance/nonce lookups).

## Contracts

There is no EVM. `web3emu-contract`'s `NativeRuntime` runs three
hand-written contract kinds (Level-1 DSL Counter, Token, NFT) - see
`docs/CONTRACTS.md`. Real Solidity/Vyper bytecode cannot be deployed
here. `ExecutionBackend` is the seam for an eventual EVM-backed
implementation (wrapping a mature, audited crate, never a hand-rolled
one) - not implemented in this build.

## Gas

Gas units are WEB3EMU's own small synthetic scale, not calibrated to
match any real network's costs (see `docs/PROTOCOL.md`). Do not use
WEB3EMU gas numbers to estimate real-network transaction costs.

## The bottom line

> "Ethereum compatible" is never claimed anywhere in this repository.
> Where the vocabulary is borrowed (JSON-RPC method names, `chainId`,
> gas), it is because the concepts transfer usefully to application
> development - not because the implementation is compatible.
