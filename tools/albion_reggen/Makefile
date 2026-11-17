# RegisterWorks (albion_reggen) -- single-source register generator for SilicaFlux
#
#   make gen        regenerate generated/ from defs/silicaflux_regs.yaml
#   make check      fail if generated/ is stale (no tools needed beyond Python)
#   make validate   validate the definitions, ALP conformance and RTL bindings
#   make test       fast test tier (validation, determinism, cross-language, firmware, lint/synth, simulation)
#   make test-slow  slow tier (RTL mutation suite, differential tests against the real register slaves)
#   make verify     everything above
#
# Tools: python3 (+PyYAML), verilator >= 5.020, yosys, gcc, rustc.  Tests skip what is missing.
PY      ?= python3
DEF     ?= defs/silicaflux_regs.yaml
OUT     ?= generated
REPO    ?= ../..
export PYTHONPATH := $(CURDIR)

.PHONY: gen check validate bind alp test test-slow verify sim clean

gen:
	$(PY) -m albion_reggen generate $(DEF) --out $(OUT)

check:
	$(PY) -m albion_reggen check $(DEF) --out $(OUT)

validate: alp bind
	$(PY) -m albion_reggen validate $(DEF)

alp:
	$(PY) -m albion_reggen alpcheck $(DEF)

bind:
	$(PY) -m albion_reggen bindcheck $(DEF) --repo-root $(REPO)

sim:
	$(PY) -m albion_reggen simulate $(DEF) --work build/sim --cycles 6000

test:
	cd tests && $(PY) -W ignore -m unittest test_validation test_schema test_determinism test_crosslang \
	    test_firmware test_bind_alp test_rtl_quality test_simulation -v

test-slow:
	cd tests && $(PY) -W ignore -m unittest test_mutation test_differential -v

verify: validate check test test-slow

clean:
	rm -rf build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
