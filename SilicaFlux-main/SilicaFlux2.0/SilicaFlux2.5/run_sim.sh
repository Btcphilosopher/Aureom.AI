#!/usr/bin/env bash
# shellcheck shell=bash disable=SC2317
#==============================================================================
#  run_sim.sh -- SilicaFlux RTL simulation regression runner
#                (Icarus Verilog: iverilog + vvp)
#------------------------------------------------------------------------------
#  Compiles and executes the SilicaFlux verification suite in a controlled,
#  reproducible way and reports a PASS/FAIL verdict per testbench.
#
#  TEST MATRIX
#    unit         tb_vector_engine  tb_tensor_unit  tb_memory_controller
#                 tb_scheduler      tb_noc_interconnect
#    integration  tb_compute_tile   tb_silicaflux_top
#    (extend by adding names to UNIT_TESTS / INTEGRATION_TESTS below)
#
#  SOURCE LAYOUT (relative to the project root)
#    ./*.sf  ./src/**/*.sf       RTL. Compile order: silicaflux_pkg.sf, other
#                                *_pkg.sf, interfaces (*_if/_intf.sf), then
#                                core modules (all tiers sorted by path).
#    ./tb_*.sf  ./tb/**/tb_*.sf  Testbenches. Top module name == file stem.
#    ./tb/**/<other>.sf          Shared verification code (BFMs, checkers,
#                                scoreboards); compiled into every target.
#
#  BUILD FLOW
#    0. toolchain self-test      iverilog -> vvp round trip with active flags
#    1. shared RTL build         packages + core modules elaborated once
#                                (top = silicaflux_top when declared)
#    2. per target compile       RTL + TB support + one testbench, -s <tb>
#    3. per target simulate      vvp -N ($stop => non-zero), stdin closed,
#                                bounded by a timeout when one is available
#
#  VERDICT (a target PASSES only if every check holds)
#    - iverilog exits 0 (and emits no warnings when SF_WERROR=1)
#    - vvp exits 0 within SF_SIM_TIMEOUT seconds ($fatal/$stop => non-zero)
#    - no failure signature in the simulation log (FAIL/FAILED/ERROR/FATAL/
#      MISMATCH, "Error:", "Assertion failed"); zero-count tallies such as
#      "ERRORS: 0", "MISMATCHES = 0", "10 PASSED / 0 FAILED", "NO ERRORS"
#      are ignored
#    - a pass marker (PASS/PASSED/"All tests passed") is present
#      (disable with SF_REQUIRE_PASS_MARKER=0)
#
#  ARTIFACTS ($SF_BUILD_DIR, default ./sim_build)
#    obj/<tb>.vvp            compiled simulation images
#    filelists/<tb>.f        exact ordered source list used (iverilog -c)
#    logs/<tb>.compile.log   compiler output (first lines: exact command)
#    logs/<tb>.sim.log       simulator output (first lines: exact command)
#    reports/summary.txt     final summary (same as console, no colour)
#    reports/junit.xml       JUnit XML for CI test reporting
#    reports/manifest.txt    tool versions, flags, source digests
#
#  REPRODUCIBILITY
#    Source discovery, compile order, flags, defines, seed and environment
#    (LC_ALL=C, umask 022, closed stdin) are fixed and recorded, and every
#    target is rebuilt from scratch. Note: iverilog embeds host pointer
#    values as labels in .vvp images, so images are not byte-identical
#    between runs; their inputs and simulation behaviour are.
#
#  EXIT STATUS
#    0  all selected targets passed
#    1  one or more targets failed
#    2  usage, environment or harness error (nothing trustworthy was run)
#    130/143  interrupted (SIGINT/SIGTERM)
#
#  ENVIRONMENT OVERRIDES [default]
#    SF_ROOT                 project root                  [script directory]
#    SF_BUILD_DIR            build/log dir, relative       [sim_build]
#    SF_EXT                  source extension              [.sf]
#    SF_SRC_DIRS             RTL dirs (recursive)          [src]
#    SF_TB_DIRS              testbench dirs (recursive)    [tb]
#    SF_INCLUDE_DIRS         extra `include dirs           [include]
#    SF_PRIORITY_FILES       compiled first, in order      [silicaflux_pkg.sf]
#    SF_REQUIRED_FILES       must exist or abort           [silicaflux_pkg.sf]
#    SF_RTL_TOP              shared-build top ("" = auto)  [silicaflux_top]
#    IVERILOG / VVP          tool names or paths           [iverilog / vvp]
#    SF_IVERILOG_FLAGS       compiler flags                [-g2012 -Wall -Wno-timescale]
#    SF_IVERILOG_EXTRA_FLAGS appended compiler flags       []
#    SF_DEFINES              -D macros                     [SIMULATION SILICAFLUX_SIM]
#    SF_VVP_FLAGS            simulator flags               [-N]
#    SF_PLUSARGS             extra +plusargs for vvp       []
#    SF_SEED                 passed as +SF_SEED=<n>        [1]
#    SF_SIM_TIMEOUT          seconds per simulation, 0=off [900]
#    SF_COMPILE_TIMEOUT      seconds per compile, 0=off    [300]
#    SF_KILL_GRACE           SIGKILL grace after timeout   [10]
#    SF_REQUIRE_PASS_MARKER  1 = pass marker mandatory     [1]
#    SF_WERROR               1 = compiler warnings fail    [0]
#    SF_FAIL_REGEX           ERE for failure signatures    [see below]
#    SF_PASS_REGEX           ERE for pass markers          [see below]
#    SF_FAIL_ZERO_FILTER     1 = ignore zero-count tallies [1]
#    SF_TAIL_LINES           log lines shown on failure    [30]
#    SF_JUNIT_FILE           JUnit output path             [<build>/reports/junit.xml]
#    NO_COLOR                disable ANSI colour
#
#  TB CONVENTIONS (recommended)
#    - print "TEST PASSED" on success; use $error/$fatal or print
#      "TEST FAILED"/"ERROR: ..." on failure; always end with $finish
#    - read +SF_SEED=<n> via $value$plusargs for reproducible stimulus
#==============================================================================

if [ -z "${BASH_VERSION:-}" ]; then
  printf '%s\n' "run_sim.sh: bash >= 3.2 is required (run: bash run_sim.sh ...)" >&2
  exit 2
fi
if [ "${BASH_VERSINFO[0]}" -lt 3 ] ||
   { [ "${BASH_VERSINFO[0]}" -eq 3 ] && [ "${BASH_VERSINFO[1]}" -lt 2 ]; }; then
  printf '%s\n' "run_sim.sh: bash >= 3.2 is required (found ${BASH_VERSION})" >&2
  exit 2
fi

set -Eeuo pipefail
umask 022
export LC_ALL=C

#------------------------------------------------------------------------------
# Constants and test matrix
#------------------------------------------------------------------------------
readonly RUNNER_NAME="run_sim.sh"
readonly RUNNER_VERSION="1.0.0"
readonly TAB=$'\t'
readonly NUM_RE='^[0-9]+$'
readonly IDENT_RE='^[A-Za-z_][A-Za-z0-9_]*$'
readonly RULE_HEAVY="========================================================================"
readonly RULE_LIGHT="------------------------------------------------------------------------"
readonly RULE_SUMMARY="===================================="

UNIT_TESTS=(
  tb_vector_engine
  tb_tensor_unit
  tb_memory_controller
  tb_scheduler
  tb_noc_interconnect
)

INTEGRATION_TESTS=(
  tb_compute_tile
  tb_silicaflux_top
)

#------------------------------------------------------------------------------
# Configuration (environment overridable)
#------------------------------------------------------------------------------
SF_ROOT="${SF_ROOT:-}"
SF_BUILD_DIR="${SF_BUILD_DIR:-sim_build}"
SF_EXT="${SF_EXT:-.sf}"
SF_SRC_DIRS="${SF_SRC_DIRS:-src}"
SF_TB_DIRS="${SF_TB_DIRS:-tb}"
SF_INCLUDE_DIRS="${SF_INCLUDE_DIRS:-include}"
SF_PRIORITY_FILES="${SF_PRIORITY_FILES:-silicaflux_pkg.sf}"
SF_REQUIRED_FILES="${SF_REQUIRED_FILES:-silicaflux_pkg.sf}"
SF_RTL_TOP="${SF_RTL_TOP-silicaflux_top}"
IVERILOG="${IVERILOG:-iverilog}"
VVP="${VVP:-vvp}"
SF_IVERILOG_FLAGS="${SF_IVERILOG_FLAGS:--g2012 -Wall -Wno-timescale}"
SF_IVERILOG_EXTRA_FLAGS="${SF_IVERILOG_EXTRA_FLAGS:-}"
SF_DEFINES="${SF_DEFINES:-SIMULATION SILICAFLUX_SIM}"
SF_VVP_FLAGS="${SF_VVP_FLAGS:--N}"
SF_PLUSARGS="${SF_PLUSARGS:-}"
SF_SEED="${SF_SEED:-1}"
SF_SIM_TIMEOUT="${SF_SIM_TIMEOUT:-900}"
SF_COMPILE_TIMEOUT="${SF_COMPILE_TIMEOUT:-300}"
SF_KILL_GRACE="${SF_KILL_GRACE:-10}"
SF_REQUIRE_PASS_MARKER="${SF_REQUIRE_PASS_MARKER:-1}"
SF_WERROR="${SF_WERROR:-0}"
SF_FAIL_ZERO_FILTER="${SF_FAIL_ZERO_FILTER:-1}"
SF_TAIL_LINES="${SF_TAIL_LINES:-30}"
SF_JUNIT_FILE="${SF_JUNIT_FILE:-}"

SF_FAIL_REGEX="${SF_FAIL_REGEX:-(^|[^A-Za-z0-9_])(FAIL|FAILS|FAILED|FAILURE|FAILURES|ERROR|ERRORS|FATAL|MISMATCH|MISMATCHES)([^A-Za-z0-9_]|\$)|(^|[^A-Za-z0-9_])(Error|Errors|Fatal|Fail|Failed|Failure|Mismatch)[[:space:]]*:|[Aa]ssertion[[:space:]]+([Ff]ailed|[Vv]iolat)}"
SF_PASS_REGEX="${SF_PASS_REGEX:-(^|[^A-Za-z0-9_])(PASS|PASSED)([^A-Za-z0-9_]|\$)|[Aa]ll[[:space:]]+[Tt]ests[[:space:]]+[Pp]assed|[Tt]est[[:space:]]+[Pp]assed}"

# Tally words whose zero count is NOT a failure ("ERRORS: 0", "0 FAILED").
# Deliberately excludes singular ERROR/FAIL so "ERROR: 0 != 1" still fails.
readonly ZERO_TALLY_RE='([Ee][Rr][Rr][Oo][Rr][Ss]|[Ff][Aa][Ii][Ll][Uu][Rr][Ee][Ss]|[Ff][Aa][Ii][Ll][Ee][Dd]|[Ff][Aa][Ii][Ll][Ss]|[Mm][Ii][Ss][Mm][Aa][Tt][Cc][Hh][Ee][Ss]|([Ee][Rr][Rr][Oo][Rr]|[Ff][Aa][Ii][Ll]|[Mm][Ii][Ss][Mm][Aa][Tt][Cc][Hh])[_ ]?([Cc][Oo][Uu][Nn][Tt]|[Cc][Nn][Tt]|[Tt][Oo][Tt][Aa][Ll]))'

#------------------------------------------------------------------------------
# Runtime state
#------------------------------------------------------------------------------
SEL_ALL=0; SEL_UNIT=0; SEL_INTEG=0
DO_CLEAN=0; KEEP_GOING=0; VERBOSE=0; LIST_ONLY=0; COLOR_MODE=auto
REQ_TESTS=()

SRC_DIRS=(); TB_DIRS=(); INC_DIRS=(); PRIORITY=()
RTL_FILES=(); TBSUP_FILES=(); TB_FILES=()
ORDERED_RTL=(); ORDERED_TBSUP=()
IV_FLAGS=(); IV_INC_ARGS=(); IV_DEF_ARGS=(); VVP_FLAGS_ARR=(); PLUSARGS_ARR=()
SEL_NAMES=(); SEL_SUITES=()

R_NAME=(); R_SUITE=(); R_STATUS=(); R_KIND=(); R_REASON=(); R_TIME=(); R_LOG=()

IVERILOG_BIN=""; VVP_BIN=""; IVERILOG_VERSION=""; VVP_VERSION=""
TIMEOUT_BIN=""; SHARED_TOP=""; FINGERPRINT=""
OBJ_DIR=""; LOG_DIR=""; FLIST_DIR=""; RPT_DIR=""; SELFTEST_DIR=""
LOCK_DIR=""; LOCK_HELD=0
SUMMARY_PRINTED=0

C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_DIM=""; C_RESET=""

#------------------------------------------------------------------------------
# Logging
#------------------------------------------------------------------------------
_log() {
  local lvl=$1 color=$2
  shift 2
  printf '[%5ds] %s%-5s%s %s\n' "$SECONDS" "$color" "$lvl" "$C_RESET" "$*"
}
info()  { _log INFO  "$C_BLUE"   "$@"; }
ok()    { _log OK    "$C_GREEN"  "$@"; }
warn()  { _log WARN  "$C_YELLOW" "$@" >&2; }
error() { _log ERROR "$C_RED"    "$@" >&2; }
die()   { error "$@"; exit 2; }

section() {
  printf '\n%s%s%s\n%s %s%s\n%s%s%s\n' \
    "$C_DIM" "$RULE_LIGHT" "$C_RESET" "$C_BOLD" "$*" "$C_RESET" "$C_DIM" "$RULE_LIGHT" "$C_RESET"
}

banner() {
  printf '%s%s%s\n%s %s%s\n%s%s%s\n' \
    "$C_BOLD" "$RULE_HEAVY" "$C_RESET" "$C_BOLD" "$*" "$C_RESET" "$C_BOLD" "$RULE_HEAVY" "$C_RESET"
}

kv() { printf ' %-16s: %s\n' "$1" "$2"; }

setup_colors() {
  local use=0
  case $COLOR_MODE in
    never) use=0 ;;
    *)
      if [[ -t 1 && -z ${NO_COLOR:-} && ${TERM:-dumb} != dumb ]]; then use=1; fi
      ;;
  esac
  if [[ $use -eq 1 ]]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
  fi
}

show_excerpt() {  # <title> <file> -- prints stdin framed
  local title=$1 file=$2
  printf '%s  ---- %s (%s) ----%s\n' "$C_DIM" "$title" "$file" "$C_RESET"
  sed -e 's/^/  | /'
  printf '%s  ---- end ----%s\n' "$C_DIM" "$C_RESET"
}

show_tail() {  # <file>
  local file=$1
  [[ -s $file ]] || return 0
  grep -v '^#sf# ' "$file" | tail -n "$SF_TAIL_LINES" | show_excerpt "last ${SF_TAIL_LINES} lines" "$file" || true
}

show_compile_diagnostics() {  # <file>
  local file=$1 diag
  [[ -s $file ]] || return 0
  diag=$(grep -v '^#sf# ' "$file" | grep -E -i '(error|sorry|unable|unknown module|syntax)' | head -n "$SF_TAIL_LINES" || true)
  if [[ -n $diag ]]; then
    printf '%s\n' "$diag" | show_excerpt "compiler diagnostics" "$file"
  else
    show_tail "$file"
  fi
}

#------------------------------------------------------------------------------
# Traps
#------------------------------------------------------------------------------
release_lock() {
  if [[ $LOCK_HELD -eq 1 && -n $LOCK_DIR ]]; then
    rm -rf -- "$LOCK_DIR" 2>/dev/null || true
    LOCK_HELD=0
  fi
}

on_exit() { release_lock; }

on_err() {
  local rc=$? line=$1 cmd=$2
  trap - ERR
  printf '%s\n' "[$SECONDS s] INTERNAL ERROR: command '${cmd}' failed (rc=${rc}) at ${RUNNER_NAME}:${line}" >&2
  printf '%s\n' "This is a harness fault, not a test verdict. Aborting." >&2
  exit 2
}

on_signal() {
  local sig=$1 code=$2
  trap - INT TERM ERR
  printf '\n' >&2
  warn "received SIG${sig}; aborting regression"
  if [[ ${#R_NAME[@]} -gt 0 && $SUMMARY_PRINTED -eq 0 ]]; then
    print_summary || true
  fi
  exit "$code"
}

trap 'on_err "$LINENO" "$BASH_COMMAND"' ERR
trap on_exit EXIT
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM

#------------------------------------------------------------------------------
# CLI
#------------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: ${RUNNER_NAME} [options]

SilicaFlux RTL regression runner (Icarus Verilog).

Selection (may be combined; default with no selection: --all):
  -a, --all               run the full regression suite (unit + integration)
  -u, --unit              run unit testbenches only
  -i, --integration       run integration testbenches only
  -t, --test <name>       run one testbench; repeatable. Accepts tb_scheduler,
                          scheduler, tb_scheduler.sf or tb/tb_scheduler.sf

Execution:
  -k, --keep-going        continue after failures (full regression report)
      --fail-fast         stop at the first failure (default)
      --timeout <sec>     per-simulation wall-clock limit, 0 = none
                          (default: ${SF_SIM_TIMEOUT})
  -c, --clean             remove build artifacts and logs; on its own, clean
                          and exit, otherwise clean before running
  -l, --list              list targets and resolved sources, then exit
  -v, --verbose           stream compiler/simulator output to the console
      --no-color          disable ANSI colour
  -h, --help              show this help

Unit:        ${UNIT_TESTS[*]-}
Integration: ${INTEGRATION_TESTS[*]-}

Exit status: 0 all passed, 1 any failure, 2 usage/environment error.
Environment overrides are documented in the header of this script.
EOF
}

usage_error() {
  printf '%s: %s\n' "$RUNNER_NAME" "$*" >&2
  printf '%s\n' "Try '${RUNNER_NAME} --help' for usage." >&2
  exit 2
}

parse_args() {
  local opt optval
  while [[ $# -gt 0 ]]; do
    case $1 in
      --*=*)
        opt=${1%%=*}; optval=${1#*=}
        shift
        set -- "$opt" "$optval" "$@"
        continue
        ;;
      -a|--all)          SEL_ALL=1 ;;
      -u|--unit)         SEL_UNIT=1 ;;
      -i|--integration)  SEL_INTEG=1 ;;
      -t|--test)
        [[ $# -ge 2 && -n $2 && $2 != -* ]] || usage_error "--test requires a testbench name"
        REQ_TESTS+=("$2")
        shift
        ;;
      -k|--keep-going)   KEEP_GOING=1 ;;
      --fail-fast)       KEEP_GOING=0 ;;
      --timeout)
        [[ $# -ge 2 && $2 =~ $NUM_RE ]] || usage_error "--timeout requires a non-negative integer (seconds)"
        SF_SIM_TIMEOUT=$2
        shift
        ;;
      -c|--clean)        DO_CLEAN=1 ;;
      -l|--list)         LIST_ONLY=1 ;;
      -v|--verbose)      VERBOSE=1 ;;
      --no-color|--no-colour) COLOR_MODE=never ;;
      -h|--help)         usage; exit 0 ;;
      --)
        shift
        [[ $# -eq 0 ]] || usage_error "unexpected argument: '$1'"
        break
        ;;
      -*)                usage_error "unknown option: '$1'" ;;
      *)                 usage_error "unexpected argument: '$1' (did you mean --test $1 ?)" ;;
    esac
    shift
  done
}

has_selection() {
  [[ $SEL_ALL -eq 1 || $SEL_UNIT -eq 1 || $SEL_INTEG -eq 1 || ${#REQ_TESTS[@]} -gt 0 ]]
}

#------------------------------------------------------------------------------
# Helpers
#------------------------------------------------------------------------------
split_words() {  # <string> -> one word per line (no globbing)
  local -a w=()
  read -r -a w <<< "$1" || true
  if [[ ${#w[@]} -gt 0 ]]; then printf '%s\n' "${w[@]}"; fi
}

norm_dir() {  # strip leading ./ and trailing /
  local d=$1
  while [[ $d == ./* ]]; do d=${d#./}; done
  while [[ $d == */ && $d != / ]]; do d=${d%/}; done
  [[ -n $d ]] || d=.
  printf '%s' "$d"
}

in_list() {  # <needle> <items...>
  local needle=$1 x
  shift
  for x in "$@"; do
    [[ $x == "$needle" ]] && return 0
  done
  return 1
}

upper() { printf '%s' "$1" | tr '[:lower:]' '[:upper:]'; }

utc_now() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

quote_cmd() {
  local out="" a q
  for a in "$@"; do
    printf -v q '%q' "$a"
    out="${out}${out:+ }${q}"
  done
  printf '%s' "$out"
}

validate_config() {
  local v
  for v in SF_SIM_TIMEOUT SF_COMPILE_TIMEOUT SF_KILL_GRACE SF_TAIL_LINES SF_SEED; do
    [[ ${!v} =~ $NUM_RE ]] || die "$v must be a non-negative integer (got '${!v}')"
  done
  for v in SF_REQUIRE_PASS_MARKER SF_WERROR SF_FAIL_ZERO_FILTER; do
    [[ ${!v} == 0 || ${!v} == 1 ]] || die "$v must be 0 or 1 (got '${!v}')"
  done
  [[ $SF_EXT == .* && $SF_EXT != *[/[:space:]]* ]] || die "SF_EXT must look like '.sf' (got '$SF_EXT')"
  if [[ -n $SF_RTL_TOP && ! $SF_RTL_TOP =~ $IDENT_RE ]]; then
    die "SF_RTL_TOP is not a valid module identifier: '$SF_RTL_TOP'"
  fi

  SF_BUILD_DIR=$(norm_dir "$SF_BUILD_DIR")
  case $SF_BUILD_DIR in
    .|/*|..|../*|*/..|*/../*|*[[:space:]]*)
      die "SF_BUILD_DIR must be a relative path inside the project without '..' or spaces (got '$SF_BUILD_DIR')"
      ;;
  esac
}

resolve_root() {
  local script_dir
  script_dir=$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
  if [[ -z $SF_ROOT ]]; then SF_ROOT=$script_dir; fi
  [[ -d $SF_ROOT ]] || die "project root does not exist: $SF_ROOT"
  cd -P -- "$SF_ROOT" || die "cannot enter project root: $SF_ROOT"
  SF_ROOT=$(pwd -P)

  OBJ_DIR="$SF_BUILD_DIR/obj"
  LOG_DIR="$SF_BUILD_DIR/logs"
  FLIST_DIR="$SF_BUILD_DIR/filelists"
  RPT_DIR="$SF_BUILD_DIR/reports"
  SELFTEST_DIR="$SF_BUILD_DIR/selftest"
  [[ -n $SF_JUNIT_FILE ]] || SF_JUNIT_FILE="$RPT_DIR/junit.xml"

  local d
  while IFS= read -r d; do SRC_DIRS+=("$(norm_dir "$d")"); done < <(split_words "$SF_SRC_DIRS")
  while IFS= read -r d; do TB_DIRS+=("$(norm_dir "$d")"); done < <(split_words "$SF_TB_DIRS")
  while IFS= read -r d; do PRIORITY+=("$d"); done < <(split_words "$SF_PRIORITY_FILES")
}

#------------------------------------------------------------------------------
# Locking (prevents concurrent runs clobbering one build directory)
#------------------------------------------------------------------------------
acquire_lock() {
  local parent base pid
  parent=$(dirname -- "$SF_BUILD_DIR")
  base=$(basename -- "$SF_BUILD_DIR")
  LOCK_DIR="$parent/.${base}.lock"
  if mkdir -- "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    LOCK_HELD=1
    return 0
  fi
  pid=$(cat -- "$LOCK_DIR/pid" 2>/dev/null || true)
  if [[ -n $pid ]] && kill -0 "$pid" 2>/dev/null; then
    die "another ${RUNNER_NAME} run (pid ${pid}) is using '${SF_BUILD_DIR}' (lock: ${LOCK_DIR})"
  fi
  warn "removing stale lock ${LOCK_DIR} (owner pid '${pid:-?}' not running)"
  rm -rf -- "$LOCK_DIR"
  mkdir -- "$LOCK_DIR" 2>/dev/null || die "cannot acquire lock ${LOCK_DIR}"
  printf '%s\n' "$$" > "$LOCK_DIR/pid"
  LOCK_HELD=1
}

#------------------------------------------------------------------------------
# Clean
#------------------------------------------------------------------------------
do_clean() {
  local f removed=0
  section "CLEAN"
  if [[ -e $SF_BUILD_DIR ]]; then
    rm -rf -- "$SF_BUILD_DIR"
    info "removed build directory: ${SF_BUILD_DIR}/"
    removed=$((removed + 1))
  fi
  # Stray artifacts from manual runs or testbench waveform dumps in the root.
  for f in ./*.vvp ./tb_*.vcd ./tb_*.fst ./tb_*.lxt ./tb_*.lxt2; do
    if [[ -f $f ]]; then
      rm -f -- "$f"
      info "removed ${f#./}"
      removed=$((removed + 1))
    fi
  done
  if [[ $removed -eq 0 ]]; then info "nothing to clean"; fi
}

#------------------------------------------------------------------------------
# Toolchain
#------------------------------------------------------------------------------
detect_tools() {
  local ver_re='version[[:space:]]+([0-9]+)\.([0-9]+)' iv_mm="" vvp_mm=""

  IVERILOG_BIN=$(command -v -- "$IVERILOG" 2>/dev/null || true)
  [[ -n $IVERILOG_BIN ]] || die "Icarus Verilog compiler not found: '${IVERILOG}' is not in PATH. Install iverilog >= 11 (apt: iverilog, brew: icarus-verilog) or set IVERILOG=/path/to/iverilog"
  VVP_BIN=$(command -v -- "$VVP" 2>/dev/null || true)
  [[ -n $VVP_BIN ]] || die "Icarus Verilog runtime not found: '${VVP}' is not in PATH. It ships with iverilog; or set VVP=/path/to/vvp"

  IVERILOG_VERSION=$("$IVERILOG_BIN" -V 2>&1 </dev/null | head -n 1 || true)
  VVP_VERSION=$("$VVP_BIN" -V 2>&1 </dev/null | head -n 1 || true)
  [[ -n $IVERILOG_VERSION ]] || die "'${IVERILOG_BIN} -V' produced no output; broken installation?"
  [[ -n $VVP_VERSION ]] || die "'${VVP_BIN} -V' produced no output; broken installation?"

  if [[ $IVERILOG_VERSION =~ $ver_re ]]; then
    iv_mm="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
    if [[ ${BASH_REMATCH[1]} -lt 11 ]]; then
      warn "iverilog ${iv_mm} detected; SystemVerilog packages need >= 11 for reliable results"
    fi
  else
    warn "could not parse iverilog version from: ${IVERILOG_VERSION}"
  fi
  if [[ $VVP_VERSION =~ $ver_re ]]; then
    vvp_mm="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
  fi
  if [[ -n $iv_mm && -n $vvp_mm && $iv_mm != "$vvp_mm" ]]; then
    warn "iverilog (${iv_mm}) and vvp (${vvp_mm}) versions differ; compiled images may not load"
  fi

  local c
  TIMEOUT_BIN=""
  for c in timeout gtimeout; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -k 1 5 true >/dev/null 2>&1; then
      TIMEOUT_BIN=$(command -v "$c")
      break
    fi
  done
  if [[ -z $TIMEOUT_BIN ]] && [[ $SF_SIM_TIMEOUT -gt 0 || $SF_COMPILE_TIMEOUT -gt 0 ]]; then
    warn "no GNU-compatible 'timeout' found (Linux: coreutils, macOS: brew install coreutils); hung simulations will NOT be terminated"
  fi
}

build_tool_args() {
  local w d
  while IFS= read -r w; do IV_FLAGS+=("$w"); done < <(split_words "$SF_IVERILOG_FLAGS")
  while IFS= read -r w; do IV_FLAGS+=("$w"); done < <(split_words "$SF_IVERILOG_EXTRA_FLAGS")
  while IFS= read -r w; do IV_DEF_ARGS+=("-D$w"); done < <(split_words "$SF_DEFINES")
  while IFS= read -r w; do VVP_FLAGS_ARR+=("$w"); done < <(split_words "$SF_VVP_FLAGS")
  while IFS= read -r w; do
    [[ $w == +* ]] || die "SF_PLUSARGS entries must start with '+' (got '$w')"
    PLUSARGS_ARR+=("$w")
  done < <(split_words "$SF_PLUSARGS")

  # Include search path: root, source dirs, testbench dirs, explicit extras.
  local -a cand=(.)
  cand+=(${SRC_DIRS[@]+"${SRC_DIRS[@]}"})
  cand+=(${TB_DIRS[@]+"${TB_DIRS[@]}"})
  while IFS= read -r d; do cand+=("$(norm_dir "$d")"); done < <(split_words "$SF_INCLUDE_DIRS")
  for d in "${cand[@]}"; do
    if [[ -d $d ]] && ! in_list "$d" ${INC_DIRS[@]+"${INC_DIRS[@]}"}; then
      INC_DIRS+=("$d")
      IV_INC_ARGS+=("-I$d")
    fi
  done
}

run_bounded() {  # <limit-seconds> <cmd...>
  local limit=$1
  shift
  if [[ -n $TIMEOUT_BIN && $limit -gt 0 ]]; then
    "$TIMEOUT_BIN" -k "$SF_KILL_GRACE" "$limit" "$@"
  else
    "$@"
  fi
}

run_logged() {  # <logfile> <cmd...> ; returns the command's exit status
  local log=$1 rc=0
  shift
  if [[ $VERBOSE -eq 1 ]]; then
    "$@" </dev/null 2>&1 | tee -a "$log" || rc=${PIPESTATUS[0]}
  else
    # Subshell keeps the redirection off the parent shell, so signal traps
    # that fire while waiting still report to the console, not the log.
    ( "$@" ) </dev/null >>"$log" 2>&1 || rc=$?
  fi
  return "$rc"
}

toolchain_selftest() {
  local src="$SELFTEST_DIR/sf_toolchain_probe${SF_EXT}" obj="$SELFTEST_DIR/sf_toolchain_probe.vvp"
  local log="$SELFTEST_DIR/selftest.log" rc=0
  mkdir -p -- "$SELFTEST_DIR"
  rm -f -- "$obj" "$log"
  cat > "$src" <<'EOF'
module sf_toolchain_probe;
  reg [7:0] v;
  initial begin
    v = 8'hA5;
    if (v !== 8'hA5) $display("SF_TOOLCHAIN_BAD");
    else             $display("SF_TOOLCHAIN_OK");
    $finish;
  end
endmodule
EOF
  run_logged "$log" run_bounded 60 "$IVERILOG_BIN" ${IV_FLAGS[@]+"${IV_FLAGS[@]}"} \
    -s sf_toolchain_probe -o "$obj" "$src" || rc=$?
  if [[ $rc -ne 0 ]]; then
    show_tail "$log"
    die "toolchain self-test: iverilog failed (rc=${rc}) with flags '${IV_FLAGS[*]-}'. Check SF_IVERILOG_FLAGS / installation."
  fi
  run_logged "$log" run_bounded 60 "$VVP_BIN" ${VVP_FLAGS_ARR[@]+"${VVP_FLAGS_ARR[@]}"} "$obj" || rc=$?
  if [[ $rc -ne 0 ]] || ! grep -q 'SF_TOOLCHAIN_OK' "$log"; then
    show_tail "$log"
    die "toolchain self-test: vvp failed (rc=${rc}) with flags '${VVP_FLAGS_ARR[*]-}'. Check SF_VVP_FLAGS / installation."
  fi
}

#------------------------------------------------------------------------------
# Source discovery and ordering
#------------------------------------------------------------------------------
is_under_tb_dir() {
  local f=$1 d
  for d in ${TB_DIRS[@]+"${TB_DIRS[@]}"}; do
    [[ $d == . ]] && continue
    [[ $f == "$d"/* ]] && return 0
  done
  return 1
}

list_source_files() {
  local d
  find . -maxdepth 1 -type f -name "*${SF_EXT}"
  for d in ${SRC_DIRS[@]+"${SRC_DIRS[@]}"} ${TB_DIRS[@]+"${TB_DIRS[@]}"}; do
    if [[ -d $d ]]; then
      find "$d" -type f -name "*${SF_EXT}" ! -path '*/.*' ! -path "${SF_BUILD_DIR}/*" ! -path "./${SF_BUILD_DIR}/*"
    fi
  done
}

order_sources() {  # <paths...> -> stdout, dependency-safe deterministic order
  local f base tier sub i p
  for f in "$@"; do
    base=${f##*/}
    tier=3; sub=0; i=0
    for p in ${PRIORITY[@]+"${PRIORITY[@]}"}; do
      if [[ $base == "$p" ]]; then tier=0; sub=$i; break; fi
      i=$((i + 1))
    done
    if [[ $tier -ne 0 ]]; then
      case $base in
        *_pkg"$SF_EXT"|*_package"$SF_EXT")                    tier=1 ;;
        *_if"$SF_EXT"|*_intf"$SF_EXT"|*_interface"$SF_EXT")    tier=2 ;;
        *)                                                     tier=3 ;;
      esac
    fi
    printf '%d\t%04d\t%s\n' "$tier" "$sub" "$f"
  done | sort -t "$TAB" -k1,1n -k2,2n -k3,3 | cut -f3-
}

discover_sources() {
  local f base dups d n req
  local -a found=()

  while IFS= read -r f; do
    [[ -n $f ]] && found+=("$f")
  done < <(list_source_files | sed -e 's#^\./##' | sort -u)

  RTL_FILES=(); TBSUP_FILES=(); TB_FILES=()
  for f in ${found[@]+"${found[@]}"}; do
    base=${f##*/}
    if [[ $base == tb_*"$SF_EXT" ]]; then
      TB_FILES+=("$f")
    elif is_under_tb_dir "$f"; then
      TBSUP_FILES+=("$f")
    else
      RTL_FILES+=("$f")
    fi
  done

  [[ ${#RTL_FILES[@]} -gt 0 ]] || die "no RTL sources (*${SF_EXT}) found in ./ or: ${SRC_DIRS[*]-}"

  # Testbench names must resolve to exactly one file.
  dups=$(printf '%s\n' ${TB_FILES[@]+"${TB_FILES[@]}"} | sed -e 's#.*/##' | sort | uniq -d || true)
  if [[ -n $dups ]]; then
    for d in $dups; do
      error "ambiguous testbench '${d}' found in multiple locations:"
      for f in "${TB_FILES[@]}"; do [[ ${f##*/} == "$d" ]] && error "    $f"; done
    done
    die "remove or rename duplicate testbench sources"
  fi

  # Required files must exist exactly once among RTL sources.
  while IFS= read -r req; do
    n=0
    for f in "${RTL_FILES[@]}"; do [[ ${f##*/} == "$req" ]] && n=$((n + 1)); done
    if [[ $n -eq 0 ]]; then
      die "required source '${req}' not found in ./ or ${SRC_DIRS[*]-} (set SF_REQUIRED_FILES to change)"
    elif [[ $n -gt 1 ]]; then
      die "required source '${req}' found ${n} times; it must be unique"
    fi
  done < <(split_words "$SF_REQUIRED_FILES")

  # Same basename in several RTL locations is legal but often a stale copy.
  dups=$(printf '%s\n' "${RTL_FILES[@]}" ${TBSUP_FILES[@]+"${TBSUP_FILES[@]}"} | sed -e 's#.*/##' | sort | uniq -d || true)
  if [[ -n $dups ]]; then
    for d in $dups; do
      if in_list "$d" ${PRIORITY[@]+"${PRIORITY[@]}"}; then
        die "priority source '${d}' exists in multiple locations; compile order would be ambiguous"
      fi
      warn "source basename '${d}' appears in multiple directories (stale copy?)"
    done
  fi

  ORDERED_RTL=(); ORDERED_TBSUP=()
  while IFS= read -r f; do ORDERED_RTL+=("$f"); done < <(order_sources "${RTL_FILES[@]}")
  while IFS= read -r f; do ORDERED_TBSUP+=("$f"); done < <(order_sources ${TBSUP_FILES[@]+"${TBSUP_FILES[@]}"})
}

find_tb_source() {  # <tb-name> -> path or empty
  local name=$1 f
  for f in ${TB_FILES[@]+"${TB_FILES[@]}"}; do
    if [[ ${f##*/} == "${name}${SF_EXT}" ]]; then
      printf '%s' "$f"
      return 0
    fi
  done
  return 0
}

module_declared() {  # <module> <files...>
  local name=$1
  shift
  grep -E -q "^[[:space:]]*(module|macromodule)[[:space:]]+((automatic|static)[[:space:]]+)?${name}([^A-Za-z0-9_\$]|\$)" "$@" 2>/dev/null
}

normalize_test_name() {
  local n=${1##*/}
  n=${n%"$SF_EXT"}
  case $n in
    tb_*) ;;
    *) n="tb_${n}" ;;
  esac
  printf '%s' "$n"
}

suite_of() {
  if in_list "$1" ${UNIT_TESTS[@]+"${UNIT_TESTS[@]}"}; then printf 'unit'
  elif in_list "$1" ${INTEGRATION_TESTS[@]+"${INTEGRATION_TESTS[@]}"}; then printf 'integration'
  else printf 'adhoc'
  fi
}

add_selection() {  # <name> <suite>
  if ! in_list "$1" ${SEL_NAMES[@]+"${SEL_NAMES[@]}"}; then
    SEL_NAMES+=("$1")
    SEL_SUITES+=("$2")
  fi
}

resolve_selection() {
  local t raw
  if [[ $SEL_ALL -eq 1 || $SEL_UNIT -eq 1 ]]; then
    for t in ${UNIT_TESTS[@]+"${UNIT_TESTS[@]}"}; do add_selection "$t" unit; done
  fi
  if [[ $SEL_ALL -eq 1 || $SEL_INTEG -eq 1 ]]; then
    for t in ${INTEGRATION_TESTS[@]+"${INTEGRATION_TESTS[@]}"}; do add_selection "$t" integration; done
  fi
  for raw in ${REQ_TESTS[@]+"${REQ_TESTS[@]}"}; do
    t=$(normalize_test_name "$raw")
    [[ $t =~ $IDENT_RE ]] || usage_error "invalid testbench name: '$raw'"
    if [[ $(suite_of "$t") == adhoc && -z $(find_tb_source "$t") ]]; then
      usage_error "unknown testbench '${raw}' (no ${t}${SF_EXT} in ./ or ${TB_DIRS[*]-}); see --list"
    fi
    add_selection "$t" "$(suite_of "$t")"
  done
  [[ ${#SEL_NAMES[@]} -gt 0 ]] || usage_error "no testbenches selected"
}

list_targets() {
  local t src
  local -a all=(${UNIT_TESTS[@]+"${UNIT_TESTS[@]}"} ${INTEGRATION_TESTS[@]+"${INTEGRATION_TESTS[@]}"})
  for src in ${TB_FILES[@]+"${TB_FILES[@]}"}; do
    t=${src##*/}; t=${t%"$SF_EXT"}
    in_list "$t" ${all[@]+"${all[@]}"} || all+=("$t")
  done
  printf 'SilicaFlux simulation targets (root: %s)\n\n' "$SF_ROOT"
  printf '  %-12s %-26s %s\n' SUITE TEST SOURCE
  printf '  %-12s %-26s %s\n' ----- ---- ------
  for t in ${all[@]+"${all[@]}"}; do
    src=$(find_tb_source "$t")
    printf '  %-12s %-26s %s\n' "$(suite_of "$t")" "$t" "${src:-MISSING}"
  done
  printf '\n  RTL sources (compile order): %d\n' "${#ORDERED_RTL[@]}"
  for src in "${ORDERED_RTL[@]}"; do printf '    %s\n' "$src"; done
  if [[ ${#ORDERED_TBSUP[@]} -gt 0 ]]; then
    printf '  TB support sources: %d\n' "${#ORDERED_TBSUP[@]}"
    for src in "${ORDERED_TBSUP[@]}"; do printf '    %s\n' "$src"; done
  fi
}

#------------------------------------------------------------------------------
# Reproducibility manifest
#------------------------------------------------------------------------------
hash_files() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"
  else cksum "$@"
  fi
}

hash_algo() {
  if command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1; then
    printf 'sha256'
  else
    printf 'cksum'
  fi
}

write_manifest() {
  local m="$RPT_DIR/manifest.txt" digests
  local -a all=("${ORDERED_RTL[@]}")
  all+=(${ORDERED_TBSUP[@]+"${ORDERED_TBSUP[@]}"})
  all+=(${TB_FILES[@]+"${TB_FILES[@]}"})
  digests=$(hash_files "${all[@]}")
  FINGERPRINT="$(hash_algo):$(printf '%s\n' "$digests" | hash_files | cut -c1-16)"
  {
    printf 'runner           : %s %s\n' "$RUNNER_NAME" "$RUNNER_VERSION"
    printf 'generated_utc    : %s\n' "$(utc_now)"
    printf 'host             : %s\n' "$(uname -srm 2>/dev/null || printf unknown)"
    printf 'bash             : %s\n' "$BASH_VERSION"
    printf 'iverilog         : %s [%s]\n' "$IVERILOG_VERSION" "$IVERILOG_BIN"
    printf 'vvp              : %s [%s]\n' "$VVP_VERSION" "$VVP_BIN"
    printf 'iverilog_flags   : %s\n' "${IV_FLAGS[*]-}"
    printf 'defines          : %s\n' "${IV_DEF_ARGS[*]-}"
    printf 'include_dirs     : %s\n' "${INC_DIRS[*]-}"
    printf 'vvp_flags        : %s\n' "${VVP_FLAGS_ARR[*]-}"
    printf 'plusargs         : +SF_SEED=%s %s\n' "$SF_SEED" "${PLUSARGS_ARR[*]-}"
    printf 'shared_rtl_top   : %s\n' "${SHARED_TOP:-<auto>}"
    printf 'IVERILOG_DUMPER  : %s\n' "${IVERILOG_DUMPER:-<unset>}"
    printf 'fingerprint      : %s\n' "$FINGERPRINT"
    printf '\n# sources (%s)\n%s\n' "$(hash_algo)" "$digests"
  } > "$m"
}

#------------------------------------------------------------------------------
# Compile / simulate / evaluate
#------------------------------------------------------------------------------
write_filelist() {  # <out> <files...>
  local out=$1
  shift
  {
    printf '# SilicaFlux ordered source list -- generated by %s, do not edit\n' "$RUNNER_NAME"
    printf '%s\n' "$@"
  } > "$out"
}

compile_design() {  # <top|""> <filelist> <out.vvp> <log>
  local top=$1 flist=$2 out=$3 log=$4 rc=0
  local -a cmd=("$IVERILOG_BIN")
  cmd+=(${IV_FLAGS[@]+"${IV_FLAGS[@]}"})
  cmd+=(${IV_INC_ARGS[@]+"${IV_INC_ARGS[@]}"})
  cmd+=(${IV_DEF_ARGS[@]+"${IV_DEF_ARGS[@]}"})
  if [[ -n $top ]]; then cmd+=(-s "$top"); fi
  cmd+=(-o "$out" -c "$flist")
  {
    printf '#sf# command : %s\n' "$(quote_cmd "${cmd[@]}")"
    printf '#sf# cwd     : %s\n' "$SF_ROOT"
    printf '#sf# started : %s\n' "$(utc_now)"
  } > "$log"
  run_logged "$log" run_bounded "$SF_COMPILE_TIMEOUT" "${cmd[@]}" || rc=$?
  printf '#sf# exit    : %d\n' "$rc" >> "$log"
  return "$rc"
}

simulate_design() {  # <tb> <obj> <log>
  local tb=$1 obj=$2 log=$3 rc=0 limit="none"
  local -a cmd=("$VVP_BIN")
  if [[ -n $TIMEOUT_BIN && $SF_SIM_TIMEOUT -gt 0 ]]; then limit="${SF_SIM_TIMEOUT}s"; fi
  cmd+=(${VVP_FLAGS_ARR[@]+"${VVP_FLAGS_ARR[@]}"})
  cmd+=("$obj" "+SF_SEED=${SF_SEED}" "+SF_TEST=${tb}")
  cmd+=(${PLUSARGS_ARR[@]+"${PLUSARGS_ARR[@]}"})
  {
    printf '#sf# command : %s\n' "$(quote_cmd "${cmd[@]}")"
    printf '#sf# cwd     : %s\n' "$SF_ROOT"
    printf '#sf# timeout : %s\n' "$limit"
    printf '#sf# started : %s\n' "$(utc_now)"
  } > "$log"
  run_logged "$log" run_bounded "$SF_SIM_TIMEOUT" "${cmd[@]}" || rc=$?
  printf '#sf# exit    : %d\n' "$rc" >> "$log"
  return "$rc"
}

count_warnings() {  # <compile-log>
  local n
  n=$(grep -v '^#sf# ' "$1" 2>/dev/null | grep -c -E '(^|[^A-Za-z0-9_])([Ww]arning|sorry):' || true)
  printf '%s' "${n:-0}"
}

scan_view() {  # <log> -> log text with runner headers blanked (line numbers kept)
  local log=$1
  if [[ $SF_FAIL_ZERO_FILTER -eq 1 ]]; then
    sed -E \
      -e 's/^#sf# .*$//' \
      -e 's/^/ /' -e 's/$/ /' \
      -e "s#${ZERO_TALLY_RE}[[:space:]]*[:=][[:space:]]*0+([^0-9A-Za-z_.'])# \\4#g" \
      -e "s#([,/|;(][[:space:]]*)0+[[:space:]]+${ZERO_TALLY_RE}([^:A-Za-z0-9_])#\\1 \\5#g" \
      -e "s#[Nn][Oo][[:space:]]+${ZERO_TALLY_RE}([^A-Za-z0-9_])# \\4#g" \
      "$log"
  else
    sed -e 's/^#sf# .*$//' "$log"
  fi
}

first_failure() {  # <log> -> "LINE: text" of first failure signature, or empty
  local log=$1 n
  [[ -s $log ]] || return 0
  n=$(scan_view "$log" | grep -n -E -- "$SF_FAIL_REGEX" | head -n 1 | cut -d: -f1 || true)
  if [[ -n $n ]]; then
    printf '%s: %s' "$n" "$(sed -n "${n}p" "$log" | cut -c1-160)"
  fi
}

has_pass_marker() {  # <log> ; grep -c reads all input (no SIGPIPE under pipefail)
  local n
  n=$(sed -e 's/^#sf# .*$//' "$1" | grep -E -c -- "$SF_PASS_REGEX" || true)
  [[ ${n:-0} -gt 0 ]]
}

finish_time() {  # <log> -> simulation time of $finish, if reported
  # shellcheck disable=SC2016
  grep -E '\$finish called at' "$1" 2>/dev/null | tail -n 1 | sed -E 's/.*called at //' || true
}

record_result() {  # <name> <suite> <PASS|FAIL|SKIP> <kind> <reason> <seconds> <log>
  R_NAME+=("$1"); R_SUITE+=("$2"); R_STATUS+=("$3"); R_KIND+=("$4")
  R_REASON+=("$5"); R_TIME+=("$6"); R_LOG+=("$7")
  case $3 in
    PASS) ok "${C_GREEN}PASS${C_RESET} ${1} (${6}s)${5:+ -- $5}" ;;
    FAIL) error "${C_RED}FAIL${C_RESET} ${1} (${6}s) -- ${5}" ;;
    *) : ;;
  esac
}

build_shared_rtl() {  # sets SHARED_OK
  local flist="$FLIST_DIR/rtl_shared.f" obj="$OBJ_DIR/silicaflux_rtl.vvp"
  local log="$LOG_DIR/rtl_shared.compile.log" rc=0 t0=$SECONDS nw reason
  SHARED_OK=1
  section "[0/${#SEL_NAMES[@]}] BUILD :: shared RTL (packages + core modules)"
  rm -f -- "$obj" "$log"
  write_filelist "$flist" "${ORDERED_RTL[@]}"
  info "sources : ${#ORDERED_RTL[@]} RTL file(s), first: ${ORDERED_RTL[0]}"
  info "top     : ${SHARED_TOP:-<auto: all uninstantiated modules>}"

  compile_design "$SHARED_TOP" "$flist" "$obj" "$log" || rc=$?
  nw=$(count_warnings "$log")
  reason=""
  if [[ $rc -eq 124 || $rc -eq 137 ]] && [[ -n $TIMEOUT_BIN && $SF_COMPILE_TIMEOUT -gt 0 ]]; then
    reason="shared RTL compile timed out after ${SF_COMPILE_TIMEOUT}s"
  elif [[ $rc -ne 0 ]]; then
    reason="shared RTL compile failed (iverilog rc=${rc})"
  elif [[ $SF_WERROR -eq 1 && $nw -gt 0 ]]; then
    reason="shared RTL build produced ${nw} warning(s) with SF_WERROR=1"
  fi
  if [[ -n $reason ]]; then
    SHARED_OK=0
    show_compile_diagnostics "$log"
    record_result "rtl_shared_build" build FAIL compile "$reason" "$((SECONDS - t0))" "$log"
    return 0
  fi
  [[ $nw -eq 0 ]] || warn "shared RTL: ${nw} compiler warning(s) -> ${log}"
  ok "shared RTL elaborated (${#ORDERED_RTL[@]} files, $((SECONDS - t0))s) -> ${obj}"
}

run_target() {  # <idx> <total> <tb> <suite> ; sets LAST_STATUS
  local idx=$1 total=$2 tb=$3 suite=$4
  local src clog slog obj flist rc=0 t0=$SECONDS nw sig ftime reason kind
  local -a files=()
  LAST_STATUS=FAIL
  clog="$LOG_DIR/${tb}.compile.log"; slog="$LOG_DIR/${tb}.sim.log"
  obj="$OBJ_DIR/${tb}.vvp";          flist="$FLIST_DIR/${tb}.f"
  rm -f -- "$obj" "$clog" "$slog" "$flist"

  section "[${idx}/${total}] $(upper "$suite") :: ${tb}"

  src=$(find_tb_source "$tb")
  if [[ -z $src ]]; then
    record_result "$tb" "$suite" FAIL missing \
      "testbench source ${tb}${SF_EXT} not found in ./ or ${TB_DIRS[*]-}" "$((SECONDS - t0))" "-"
    return 0
  fi
  if ! module_declared "$tb" "$src"; then
    warn "no 'module ${tb}' declaration found in ${src}; '-s ${tb}' may fail"
  fi

  files=("${ORDERED_RTL[@]}")
  files+=(${ORDERED_TBSUP[@]+"${ORDERED_TBSUP[@]}"})
  files+=("$src")
  write_filelist "$flist" "${files[@]}"

  # ---- compile -------------------------------------------------------------
  info "compile : ${src} (top=${tb}, ${#files[@]} sources)"
  compile_design "$tb" "$flist" "$obj" "$clog" || rc=$?
  nw=$(count_warnings "$clog")
  if [[ $rc -ne 0 ]]; then
    if [[ $rc -eq 124 || $rc -eq 137 ]] && [[ -n $TIMEOUT_BIN && $SF_COMPILE_TIMEOUT -gt 0 ]]; then
      reason="compile timed out after ${SF_COMPILE_TIMEOUT}s"
    else
      reason="compile failed (iverilog rc=${rc})"
    fi
    show_compile_diagnostics "$clog"
    record_result "$tb" "$suite" FAIL compile "${reason} -> ${clog}" "$((SECONDS - t0))" "$clog"
    return 0
  fi
  if [[ $nw -gt 0 ]]; then
    if [[ $SF_WERROR -eq 1 ]]; then
      show_compile_diagnostics "$clog"
      record_result "$tb" "$suite" FAIL compile "${nw} compiler warning(s) with SF_WERROR=1 -> ${clog}" "$((SECONDS - t0))" "$clog"
      return 0
    fi
    warn "${nw} compiler warning(s) -> ${clog}"
  fi
  if [[ ! -s $obj ]]; then
    record_result "$tb" "$suite" FAIL compile "iverilog returned 0 but produced no image ${obj}" "$((SECONDS - t0))" "$clog"
    return 0
  fi

  # ---- simulate ------------------------------------------------------------
  info "simulate: ${obj} (+SF_SEED=${SF_SEED})"
  rc=0
  simulate_design "$tb" "$obj" "$slog" || rc=$?
  sig=$(first_failure "$slog")
  kind=""; reason=""
  if [[ $rc -eq 124 || $rc -eq 137 ]] && [[ -n $TIMEOUT_BIN && $SF_SIM_TIMEOUT -gt 0 ]]; then
    kind=timeout
    reason="simulation exceeded ${SF_SIM_TIMEOUT}s wall clock (hang or missing \$finish)"
  elif [[ $rc -gt 128 ]]; then
    kind=runtime
    reason="vvp terminated by signal $((rc - 128))"
  elif [[ $rc -ne 0 ]]; then
    kind=runtime
    reason="vvp exited with rc=${rc} (\$fatal/\$stop or runtime error)"
  elif [[ -n $sig ]]; then
    kind=signature
    reason="failure signature in output"
  elif [[ $SF_REQUIRE_PASS_MARKER -eq 1 ]] && ! has_pass_marker "$slog"; then
    kind=no-pass-marker
    reason="simulation ended without a pass marker (expected e.g. 'TEST PASSED')"
  fi

  if [[ -n $kind ]]; then
    [[ -z $sig ]] || reason="${reason}; first at line ${sig}"
    [[ $VERBOSE -eq 1 ]] || show_tail "$slog"
    record_result "$tb" "$suite" FAIL "$kind" "${reason} -> ${slog}" "$((SECONDS - t0))" "$slog"
    return 0
  fi

  ftime=$(finish_time "$slog")
  LAST_STATUS=PASS
  record_result "$tb" "$suite" PASS pass "${ftime:+\$finish @ ${ftime}}" "$((SECONDS - t0))" "$slog"
}

#------------------------------------------------------------------------------
# Reporting
#------------------------------------------------------------------------------
render_summary() {  # <use-colour 0|1>
  local color=$1 i n=${#R_NAME[@]} p=0 f=0 s=0 w=24 st cs ce
  for ((i = 0; i < n; i++)); do
    [[ ${#R_NAME[i]} -lt $w ]] || w=$((${#R_NAME[i]} + 2))
    case ${R_STATUS[i]} in PASS) p=$((p + 1)) ;; FAIL) f=$((f + 1)) ;; *) s=$((s + 1)) ;; esac
  done
  printf '%s\n%s\n%s\n' "$RULE_SUMMARY" "SILICAFLUX SIMULATION SUMMARY" "$RULE_SUMMARY"
  for ((i = 0; i < n; i++)); do
    st=${R_STATUS[i]}; cs=""; ce=""
    if [[ $color -eq 1 ]]; then
      case $st in PASS) cs=$C_GREEN ;; FAIL) cs=$C_RED ;; *) cs=$C_YELLOW ;; esac
      ce=$C_RESET
    fi
    printf "TEST: %-${w}s RESULT: %s%s%s\n" "${R_NAME[i]}" "$cs" "$st" "$ce"
  done
  printf '%s\n' "$RULE_SUMMARY"
  if [[ $s -gt 0 ]]; then
    printf 'TOTAL: %d PASSED / %d FAILED / %d SKIPPED\n' "$p" "$f" "$s"
  else
    printf 'TOTAL: %d PASSED / %d FAILED\n' "$p" "$f"
  fi
  printf '%s\n' "$RULE_SUMMARY"
}

render_details() {
  local i n=${#R_NAME[@]}
  printf 'RESULT DETAILS\n'
  printf '  %-24s %-12s %-5s %6s  %s\n' TEST SUITE RES TIME NOTE
  for ((i = 0; i < n; i++)); do
    printf '  %-24s %-12s %-5s %5ss  %s\n' "${R_NAME[i]}" "${R_SUITE[i]}" "${R_STATUS[i]}" \
      "${R_TIME[i]}" "${R_REASON[i]:-${R_LOG[i]}}"
  done
}

xml_escape() {
  printf '%s' "$1" | tr -d '\000-\010\013\014\016-\037' |
    sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'
}

write_junit() {
  local i n=${#R_NAME[@]} p=0 f=0 s=0 total_t=0 body
  mkdir -p -- "$(dirname -- "$SF_JUNIT_FILE")"
  for ((i = 0; i < n; i++)); do
    case ${R_STATUS[i]} in PASS) p=$((p + 1)) ;; FAIL) f=$((f + 1)) ;; *) s=$((s + 1)) ;; esac
    total_t=$((total_t + R_TIME[i]))
  done
  {
    printf '<?xml version="1.0" encoding="UTF-8"?>\n'
    printf '<testsuites name="silicaflux-sim" tests="%d" failures="%d" errors="0" skipped="%d" time="%d">\n' \
      "$n" "$f" "$s" "$total_t"
    printf '  <testsuite name="silicaflux-sim" tests="%d" failures="%d" errors="0" skipped="%d" time="%d" timestamp="%s" hostname="%s">\n' \
      "$n" "$f" "$s" "$total_t" "$(date -u '+%Y-%m-%dT%H:%M:%S')" "$(xml_escape "$(uname -n 2>/dev/null || printf unknown)")"
    printf '    <properties>\n'
    printf '      <property name="iverilog" value="%s"/>\n' "$(xml_escape "$IVERILOG_VERSION")"
    printf '      <property name="vvp" value="%s"/>\n' "$(xml_escape "$VVP_VERSION")"
    printf '      <property name="seed" value="%s"/>\n' "$SF_SEED"
    printf '      <property name="fingerprint" value="%s"/>\n' "$(xml_escape "$FINGERPRINT")"
    printf '    </properties>\n'
    for ((i = 0; i < n; i++)); do
      printf '    <testcase classname="silicaflux.%s" name="%s" time="%d">\n' \
        "$(xml_escape "${R_SUITE[i]}")" "$(xml_escape "${R_NAME[i]}")" "${R_TIME[i]}"
      case ${R_STATUS[i]} in
        FAIL)
          body=""
          if [[ ${R_LOG[i]} != "-" && -s ${R_LOG[i]} ]]; then
            body=$(grep -v '^#sf# ' "${R_LOG[i]}" | tail -n 50 || true)
          fi
          printf '      <failure type="%s" message="%s">%s</failure>\n' \
            "$(xml_escape "${R_KIND[i]}")" "$(xml_escape "${R_REASON[i]}")" "$(xml_escape "$body")"
          ;;
        SKIP)
          printf '      <skipped message="%s"/>\n' "$(xml_escape "${R_REASON[i]}")"
          ;;
      esac
      printf '      <system-out>log: %s</system-out>\n' "$(xml_escape "${R_LOG[i]}")"
      printf '    </testcase>\n'
    done
    printf '  </testsuite>\n</testsuites>\n'
  } > "$SF_JUNIT_FILE"
}

print_summary() {
  SUMMARY_PRINTED=1
  printf '\n'
  render_details
  printf '\n'
  render_summary 1
  if [[ -d $RPT_DIR ]]; then
    { render_details; printf '\n'; render_summary 0; } > "$RPT_DIR/summary.txt" 2>/dev/null || true
    write_junit 2>/dev/null || warn "could not write JUnit report ${SF_JUNIT_FILE}"
    printf 'Reports: %s/summary.txt  %s  %s/manifest.txt\n' "$RPT_DIR" "$SF_JUNIT_FILE" "$RPT_DIR"
    printf 'Logs   : %s/\n' "$LOG_DIR"
  fi
}

print_header() {
  local nu=0 ni=0 na=0 i
  for ((i = 0; i < ${#SEL_SUITES[@]}; i++)); do
    case ${SEL_SUITES[i]} in unit) nu=$((nu + 1)) ;; integration) ni=$((ni + 1)) ;; *) na=$((na + 1)) ;; esac
  done
  banner "SILICAFLUX RTL REGRESSION :: ${RUNNER_NAME} v${RUNNER_VERSION}"
  kv "started (UTC)" "$(utc_now)"
  kv "host" "$(uname -srm 2>/dev/null || printf unknown)"
  kv "root" "$SF_ROOT"
  kv "build dir" "${SF_BUILD_DIR}/"
  kv "iverilog" "${IVERILOG_VERSION} [${IVERILOG_BIN}]"
  kv "vvp" "${VVP_VERSION} [${VVP_BIN}]"
  kv "compile flags" "${IV_FLAGS[*]-} ${IV_DEF_ARGS[*]-}"
  kv "include dirs" "${INC_DIRS[*]-}"
  kv "vvp flags" "${VVP_FLAGS_ARR[*]-} +SF_SEED=${SF_SEED}${PLUSARGS_ARR[*]:+ ${PLUSARGS_ARR[*]}}"
  if [[ -n $TIMEOUT_BIN ]]; then
    kv "timeouts" "compile ${SF_COMPILE_TIMEOUT}s, sim ${SF_SIM_TIMEOUT}s (0 = off) via ${TIMEOUT_BIN}"
  else
    kv "timeouts" "unavailable (no GNU timeout)"
  fi
  kv "mode" "$( [[ $KEEP_GOING -eq 1 ]] && printf 'keep-going (full regression)' || printf 'fail-fast')"
  kv "verdict" "rc==0, no failure signature$( [[ $SF_REQUIRE_PASS_MARKER -eq 1 ]] && printf ', pass marker required')$( [[ $SF_WERROR -eq 1 ]] && printf ', warnings are errors')"
  kv "sources" "${#ORDERED_RTL[@]} RTL, ${#ORDERED_TBSUP[@]} TB support, ${#TB_FILES[@]} testbench(es)"
  kv "fingerprint" "$FINGERPRINT"
  kv "selected" "${#SEL_NAMES[@]} (unit ${nu}, integration ${ni}$( [[ $na -gt 0 ]] && printf ', adhoc %d' "$na"))"
  printf '%s%s%s\n' "$C_BOLD" "$RULE_HEAVY" "$C_RESET"
  printf ' %-4s %-12s %-24s %s\n' "#" SUITE TEST SOURCE
  for ((i = 0; i < ${#SEL_NAMES[@]}; i++)); do
    local src
    src=$(find_tb_source "${SEL_NAMES[i]}")
    printf ' %-4s %-12s %-24s %s\n' "$((i + 1))" "${SEL_SUITES[i]}" "${SEL_NAMES[i]}" "${src:-MISSING}"
  done
}

#------------------------------------------------------------------------------
# Main
#------------------------------------------------------------------------------
main() {
  local i n stop=0 any_fail=0

  parse_args "$@"
  setup_colors
  validate_config
  resolve_root

  if [[ $LIST_ONLY -eq 1 ]]; then
    discover_sources
    list_targets
    exit 0
  fi

  acquire_lock

  if [[ $DO_CLEAN -eq 1 ]]; then
    do_clean
    if ! has_selection; then
      exit 0
    fi
  fi
  has_selection || SEL_ALL=1

  detect_tools
  build_tool_args
  discover_sources
  resolve_selection

  mkdir -p -- "$OBJ_DIR" "$LOG_DIR" "$FLIST_DIR" "$RPT_DIR"
  rm -f -- "$RPT_DIR/summary.txt" "$SF_JUNIT_FILE"
  toolchain_selftest

  SHARED_TOP=""
  if [[ -n $SF_RTL_TOP ]]; then
    if module_declared "$SF_RTL_TOP" "${ORDERED_RTL[@]}"; then
      SHARED_TOP=$SF_RTL_TOP
    else
      warn "shared RTL top '${SF_RTL_TOP}' not declared in RTL; elaborating all root modules"
    fi
  fi

  write_manifest
  print_header

  build_shared_rtl
  if [[ $SHARED_OK -eq 0 ]]; then
    any_fail=1
    if [[ $KEEP_GOING -eq 1 ]]; then
      warn "shared RTL build failed; continuing per-target builds (--keep-going)"
    else
      stop=1
      error "shared RTL build failed; aborting (use --keep-going to attempt per-target builds)"
    fi
  fi

  n=${#SEL_NAMES[@]}
  for ((i = 0; i < n; i++)); do
    if [[ $stop -eq 1 ]]; then
      record_result "${SEL_NAMES[i]}" "${SEL_SUITES[i]}" SKIP skipped \
        "not run: fail-fast stop after earlier failure (use --keep-going)" 0 "-"
      continue
    fi
    LAST_STATUS=FAIL
    run_target "$((i + 1))" "$n" "${SEL_NAMES[i]}" "${SEL_SUITES[i]}"
    if [[ $LAST_STATUS != PASS ]]; then
      any_fail=1
      if [[ $KEEP_GOING -eq 0 ]]; then
        stop=1
        warn "stopping after first failure (fail-fast); use --keep-going for a full regression"
      fi
    fi
  done

  print_summary

  if [[ $any_fail -ne 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
