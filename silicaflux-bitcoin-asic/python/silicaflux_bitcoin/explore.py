"""python -m silicaflux_bitcoin.explore -- thin CLI entry point, section 38.
See python/silicaflux_bitcoin/optimisation/design_space_explore.py for
the actual sweep/synthesis logic."""
from silicaflux_bitcoin.optimisation.design_space_explore import main

if __name__ == "__main__":
    import sys
    sys.exit(main())
