"""RegisterWorks (albion_reggen): single-source register generator for SilicaFlux.

One validated register definition drives every output: SystemVerilog RTL
(an ALP v1 target), C and Rust firmware interfaces, and documentation.
"""

__version__ = "1.0.0"

#: Schema version of the register-definition format accepted by this release.
SCHEMA_VERSION = 1

#: Register-bank architecture version stamped into every generated file.
GENERATOR_NAME = "albion_reggen"
