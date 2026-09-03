# Protocol

Everything here is defined by WEB3EMU itself - none of it is a claim of
compatibility with a specific production network's protocol. See
`COMPATIBILITY.md` for an explicit compatibility matrix.

## Genesis

`GenesisConfig` (`web3emu-core`) fixes: `chain_id`, `network_name`,
`initial_timestamp`, `initial_gas_limit`, `initial_base_fee`,
`initial_accounts` (address/balance pairs), `protocol_version`, and a
`seed`. `EmulatorNetwork::genesis(config)` is a pure function of its
input - the same `GenesisConfig` always produces the same genesis block
hash and state root. The CLI's `web3emu init` builds a `GenesisConfig`
funding the seven standard dev accounts (see `WALLETS.md`) with
1,000,000,000 units each.

## Accounts

`Account { address, kind, nonce, balance, code, storage, metadata }`
(`web3emu-account`). `kind` is `ExternallyControlled` or `Contract`.
`storage` is a `BTreeMap<Vec<u8>, Vec<u8>>` - deterministic iteration
order, arbitrary keys/values. On the wire (JSON snapshots, `--json`
inspect output) both `storage` and `code` are hex-encoded, since JSON
object keys must be strings.

## Transactions

`EmulatorTransaction` (`web3emu-tx`): `hash`, `chain_id`, `nonce`,
`sender` (+ `sender_public_key`), `recipient` (`None` for deployments),
`value`, `gas_limit`, `max_fee`, `priority_fee`, `data`, `signature`,
`timestamp`, `tx_type`. Five transaction types: `Transfer`,
`ContractDeployment`, `ContractCall`, `ContractRead`,
`InternalSimulation` (never mined - used by the scenario engine's
fixture-setup steps). The hash and signature both cover the same
canonical JSON-serialized payload (excluding `hash`/`signature`
themselves); signing without matching `sender` fails, and any field
mutation after signing is detectable via
`EmulatorTransaction::recompute_hash`.

### Lifecycle

```text
CREATED -> SIGNED -> SUBMITTED -> MEMPOOL -> VALIDATED -> INCLUDED
        -> EXECUTED -> RECEIPT_CREATED -> FINAL
```
with explicit `Rejected(reason)` / `Failed(reason)` terminal states
(`web3emu_tx::TxStatus`) - a transaction is never silently dropped.

## Mempool

`web3emu-mempool::Mempool` keys transactions by `(sender, nonce)`.
Admission checks, in order: chain id, signature, duplicate hash, nonce
not below the account's current nonce, and balance covering
`value + gas_limit * max_fee` (the worst-case reservation, not the
eventual actual cost). A resubmission at the same `(sender, nonce)` only
replaces the pending one if its `priority_fee` is strictly higher.
`select_for_block` deterministically picks, round by round, the highest
`priority_fee` transaction whose nonce is next-in-line for its sender
(ties broken by transaction hash) - never mutating the state it reads.

## Blocks

`EmulatorBlock` (`web3emu-block`): `block_hash`, `parent_hash`, `height`,
`timestamp`, `proposer`, `transactions` (hashes only - bodies live in
`EmulatorNetwork.transactions`), `state_root`, `transaction_root`,
`receipt_root`, `gas_used`, `gas_limit`, `base_fee`, `logs_digest`,
`protocol_version`. `transaction_root`/`receipt_root`/`logs_digest` are
sequential SHA-256 folds over the block's contents (`fold_hashes`) - a
simple, deterministic, but **not** a production Merkle-Patricia trie or
Bloom filter (no membership-test guarantees). `block_hash` is a SHA-256
over every other field.

Block production modes (`web3emu_block::BlockProductionMode`): `Manual`
(`web3emu mine`), `Automatic { interval_ms }` (`web3emu start
--mine-interval-ms`), `TransactionTriggered`, `Batch { size }`. Only
`Manual`/`Automatic` are currently wired into the CLI; the other two are
implemented as pure decision logic (`should_produce`) ready for a caller
to drive.

## State root

`WorldState::state_root()` (`web3emu-state`) folds a per-account content
hash (address, nonce, balance, code hash, storage root) over every
account in address order. Deterministic, cheap, and enough to detect any
divergence between two states byte-for-byte - not intended to be
trie-compatible with a production network.

## Gas model

`GasSchedule` (`web3emu-execution`): `intrinsic` (charged on every
admitted transaction), `transfer`, `contract_deployment_base` +
`contract_deployment_per_byte`. Contract calls additionally spend
per-operation costs defined in `web3emu_contract::gas_costs`
(`BASE_CALL`, `STORAGE_READ`, `STORAGE_WRITE`, `EVENT`). These are all
small, self-consistent synthetic units chosen so a handful of
transactions don't require unrealistically large toy balances - they are
**not** modeled on any real network's gas costs. A transaction whose
`gas_limit` can't cover its intrinsic cost is rejected before execution;
one that runs out of gas mid-execution reverts and is charged its full
`gas_limit` (mirroring common Web3 "reverts still cost gas" semantics).
`effective_gas_price = min(max_fee, base_fee + priority_fee)`; the fee is
debited from the sender and credited to the block's `proposer` (no
base-fee burn in the current model).

## State transition

`StateTransitionEngine::apply_transaction` (`web3emu-execution`) is the
single place a transaction becomes new state. Order of operations:
signature check -> nonce check -> balance check -> intrinsic-gas check
-> (nonce consumed) -> type-specific execution -> fee settlement -> event
attachment -> state diff -> receipt + trace. Every check produces a
`TraceStep`; every rejection produces an explicit `Reverted` receipt, not
a silent no-op or a panic.
