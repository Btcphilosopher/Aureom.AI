"""SilicaFlux Bitcoin SHA-256 ASIC -- Python tooling package.

Sub-packages:
  reference     Independent Python SHA-256 / Bitcoin-header golden model.
  vectors       Test-vector generation (KATs, randomised, Bitcoin-shaped).
  simulator     Synthetic multi-core mining simulator (Python-side model only).
  benchmarks    Performance modelling (theoretical / RTL-sim-measured).
  optimisation  Design-space exploration sweeps.
  analysis      Area/energy/thermal modelling.

CLI entry points (python -m silicaflux_bitcoin.<name>):
  generate, vectors, simulate, verify, benchmark, explore
"""
