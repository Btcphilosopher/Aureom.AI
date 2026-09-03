#!/usr/bin/env bash
# End-to-end smoke test for the WEB3EMU CLI (section 79 test scenarios,
# exercised through the real binary rather than unit tests). Builds the
# release binary, then runs it through init -> accounts -> transfer ->
# contract deploy/call -> mine -> scenario -> snapshot/restore.
#
# Run from the web3emu/ directory: bash tests/smoke_test.sh

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

cargo build --release -p web3emu-cli
BIN="./target/release/web3emu"
DATA_DIR="$(mktemp -d)"
trap 'rm -rf "$DATA_DIR"' EXIT

echo "== init =="
$BIN --data-dir "$DATA_DIR" init

echo "== accounts =="
$BIN --data-dir "$DATA_DIR" accounts

echo "== transfer =="
$BIN --data-dir "$DATA_DIR" tx send --from Alice --to Bob --value 500

echo "== deploy + call contract =="
$BIN --data-dir "$DATA_DIR" contract deploy contracts/Counter.web3 --from Developer
ADDR=$($BIN --data-dir "$DATA_DIR" contract deploy contracts/Counter.web3 --from Alice | grep -oE '0x[0-9a-f]{40}' | head -1)
$BIN --data-dir "$DATA_DIR" tx call --contract "$ADDR" --method increment --from Developer
$BIN --data-dir "$DATA_DIR" state "$ADDR" --json | grep -q '"kind": "Contract"'

echo "== mine =="
$BIN --data-dir "$DATA_DIR" mine 3

echo "== scenario =="
$BIN --data-dir "$DATA_DIR" scenario scenarios/basic_transfer.web3scenario

echo "== snapshot / restore =="
SNAP="$(mktemp)"
$BIN --data-dir "$DATA_DIR" snapshot --out "$SNAP"
RESTORE_DIR="$(mktemp -d)"
$BIN --data-dir "$RESTORE_DIR" restore "$SNAP"
rm -f "$SNAP"
rm -rf "$RESTORE_DIR"

echo "ALL SMOKE TESTS PASSED"
