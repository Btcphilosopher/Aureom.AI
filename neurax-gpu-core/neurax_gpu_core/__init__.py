"""
NEURAX GPU CORE
================

A production-grade, modular simulation platform modelling the full design,
behaviour and optimisation of a modern GPU accelerator: compute cores,
memory hierarchy, scheduling/execution pipelines, thermal and power
constraints, silicon layout trade-offs and workload-specific performance
behaviour.

This is a GPU architecture R&D and performance simulation engine, not a
graphics renderer. No performance numbers are hard-coded: TFLOPS, latency,
bandwidth, thermal and power figures all emerge from the interaction of the
subsystems in ``core.engine.SimulationEngine``.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
