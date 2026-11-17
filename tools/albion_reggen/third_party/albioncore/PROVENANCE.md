# Vendored AlbionCore files

These files are copied **unmodified** from the AlbionCore 0.1.0 archive of this repository
(`SilicaFlux-main/SilicaFlux2.0/SilicaFlux2.5/albioncore-0.1.0.zip`). `tests/test_bind_alp.py` compares each one,
byte for byte, with the member of that archive (when the archive is present) and with the SHA-256 below.

| File | Archive member | SHA-256 |
|---|---|---|
| `regions.yaml` | `albioncore-0.1.0/tools/albion/config/regions.yaml` | `4d2f842cfc3c478820bcb46357cec43a084010645b4e26ce51bb3a125aa6c87c` |
| `sf_albion_chan_checker.sv` | `albioncore-0.1.0/tests/albion/common/sf_albion_chan_checker.sv` | `25b7c8efc0418acde018257cd4a77a5ac2da3276d963df8824efd93ef097aecd` |
| `sf_albion_link_checker.sv` | `albioncore-0.1.0/tests/albion/common/sf_albion_link_checker.sv` | `9c8ecaff4c53290886c5fd1da5f4090ba14ad4e9d4979938a8fa337db7032bd0` |
| `sf_albion_pkg.sv` | `albioncore-0.1.0/rtl/albion/sf_albion_pkg.sv` | `0126952bb99f2b5d4546d258834f83df9f52c45c5a478d95c4e546e1a7fe25fc` |

Why they are here: the generated register bank is an ALP v1 target and is compiled against `sf_albion_pkg` (the
protocol's types, status codes and legality/region-check functions); the testbench instantiates `sf_albion_link_checker`
so that every ALP rule is asserted on the bank's link in every simulated cycle; `regions.yaml` is the ALP region catalogue
the register map's windows are validated against.

AlbionCore carries no licence file ("add one before publishing"); these copies inherit whatever licence the repository
owner applies to AlbionCore.
