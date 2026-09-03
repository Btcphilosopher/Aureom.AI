# Scenarios

The scenario/assertion DSL (`web3emu-core::scenario`, spec sections
47-49), run with `web3emu scenario <file> [--contracts-dir DIR]`.

## Grammar

One statement per line; blank lines and `#` comments are ignored.

```text
CREATE ACCOUNT <label> BALANCE <amount>
DEPLOY <contract-label> FROM <sender-label>
CALL <contract-label>.<method> FROM <sender-label>
TRANSFER <amount> FROM <sender-label> TO <recipient-label>
MINE <n> BLOCKS
ASSERT <label> BALANCE <op> <amount>
ASSERT <label> NONCE <op> <amount>
ASSERT BLOCK HEIGHT <op> <amount>
```

`<op>` is one of `== != >= <= > <`.

## The spec's own example, verbatim

```text
CREATE ACCOUNT Alice BALANCE 10000
CREATE ACCOUNT Bob BALANCE 1000
DEPLOY Counter FROM Developer
CALL Counter.increment FROM Alice
TRANSFER 100 FROM Alice TO Bob
MINE 10 BLOCKS
ASSERT Bob BALANCE == 1100
```

This runs as-is given `--contracts-dir contracts` (so `Counter` resolves
to `contracts/Counter.web3`). `scenarios/basic_transfer.web3scenario`
keeps only the `TRANSFER`/`ASSERT` portion so it needs no contract
directory at all; `scenarios/counter_lifecycle.web3scenario` shows the
`DEPLOY`/`CALL` portion on its own.

## Contract labels

`DEPLOY <label> FROM ...` resolves `<label>` against a registry built by
the CLI from two sources:

1. Every `<label>.web3` file in `--contracts-dir` (default `contracts/`),
   compiled with the Level-1 DSL (`docs/CONTRACTS.md`).
2. Two always-available fixtures: `DemoToken` and `DemoNFT`, both owned
   by the `Treasury` dev account.

A later `CALL <label>.<method> FROM ...` refers to the address that
particular `DEPLOY` produced, not the label of a dev account.

## Deliberate simplifications

- **`CALL` takes no arguments in the text DSL.** `Counter.increment`
  needs none; `Token.transfer` or `NFT.mint` do. Use the Rust API
  (`web3emu_contract::encode_args`) or the CLI's `tx call --args` flag
  for parameterized calls outside a scenario file.
- **`DEPLOY`/`CALL`/`TRANSFER` are each submitted and immediately mined
  into their own block.** This is what lets a `CALL` reference a
  contract `DEPLOY`ed two lines earlier without a separate `MINE`
  step in between - the spec's own example relies on exactly this. An
  explicit `MINE <n> BLOCKS` mines `n` *additional* blocks, useful for
  padding block height or letting automatic-mode assertions settle.
- **No contract-storage assertions yet.** `ASSERT` covers balance,
  nonce, and block height (section 49's first three checks). Asserting a
  contract's storage value directly isn't wired into the text DSL -
  check it with `web3emu state <address> --json` after the scenario
  runs, or assert in Rust against `network.get_account(...)`.

## Report

`scenario::run` returns a `ScenarioReport { steps_run,
assertions_checked, assertions_failed, log }`. The CLI prints the log,
a summary line, and every failure message, and exits non-zero if any
assertion failed - safe to use in a shell pipeline or CI step.
