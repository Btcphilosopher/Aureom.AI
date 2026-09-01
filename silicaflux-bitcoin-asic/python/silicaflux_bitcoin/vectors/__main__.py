"""Allows `python -m silicaflux_bitcoin.vectors` (section 38 CLI command)
to run this package directly, since python/silicaflux_bitcoin/vectors/ is
also the section-37 subpackage holding the vector-generation logic."""
from .generate_vectors import main

if __name__ == "__main__":
    import sys
    sys.exit(main())
