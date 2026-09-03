# Security

## The one rule

**WEB3EMU is simulation and development infrastructure. It must never be
pointed at real funds, real custody, or production networks.** There is
no code path in this repository that connects to a real blockchain, and
none should ever be added without renaming and re-scoping the entire
project - a "simulator" that can touch real value is not a simulator.

## Development keys

Every account WEB3EMU produces is either:

- **Deterministic** (`Keypair::from_label`): the private key is the
  SHA-256 digest of a plain-text label such as `"Alice"`. Anyone who
  reads this repository, or `docs/WALLETS.md`, knows every deterministic
  dev account's private key. This is the point - it's what makes
  fixtures and scenarios reproducible - and exactly why these keys must
  never hold anything real.
- **Locally generated** (`Keypair::generate_with_rng_seed`): still not
  produced or stored with any production key-management practice
  (no hardware-backed storage, no encryption at rest - `web3emu
  snapshot` writes account state, including any locally-generated
  key material an application chose to persist alongside it, as plain
  JSON).

`web3emu_wallet::DEV_KEY_WARNING` and the `[SIMULATED - ...]` marker on
every `web3emu accounts` row exist so this is never ambiguous in a UI
built on top of this crate.

## What "SIMULATION / DEVELOPMENT ONLY" means in practice

- No real-money settlement, anywhere.
- No claim of production security properties (the crypto choices in
  `docs/COMPATIBILITY.md` are picked for clarity and speed, not audited
  for adversarial production use).
- No claim of production consensus (single-node only today - see
  `docs/ARCHITECTURE.md`'s roadmap).
- Failures are never hidden: an invalid transaction gets an explicit
  `Rejected`/`Reverted` status, never a silent drop or a fabricated
  success.
- State is never mutated outside the state transition engine - a
  visualization layer (explorer, SilicaFlux, etc.) can only ever show
  what the protocol layer actually did.

## Network exposure

`web3emu start` binds to `127.0.0.1` by default and has **no
authentication** - anyone who can reach the bound host/port can submit
transactions, mine blocks, and read all state. This is appropriate for a
local development tool and would be a serious problem anywhere else. Do
not bind it to `0.0.0.0` or a public interface, and do not put a WEB3EMU
RPC endpoint on a network you don't fully trust.

## Reporting issues

This is a local developer tool, not a service handling third-party data
or funds - there is no bug-bounty program. If you find a case where
WEB3EMU claims determinism, conservation, or an explicit failure state
and doesn't deliver it, that's a correctness bug against `docs/TESTING.md`'s
invariant table; file it as such.
