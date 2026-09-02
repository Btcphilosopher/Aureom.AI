"""
Run SILICAFLUX.PV.SPECTRAL.OPTIMISE end to end for silicon: baseline vs
optimised comparison, a small parameter sweep, and the ML surrogate's
recommendation -- demonstrating that all three converge on the same
answer (a UV-transparent encapsulant is the single highest-leverage change
for a conventionally-encapsulated silicon module's UV response).

    python examples/optimise_and_compare.py
"""

import itertools

from silicaflux_pv_spectral import MATERIAL_LIBRARY, SILICAFLUX, generate_simulation_output, terrestrial_spectrum
from silicaflux_pv_spectral.ml_optimiser import ml_optimise
from silicaflux_pv_spectral.parameter_sweep import SweepConfiguration, parameter_sweep


def main() -> None:
    material = MATERIAL_LIBRARY["SILICON"]
    spectrum = terrestrial_spectrum()

    print("### SILICAFLUX.PV.SPECTRAL.OPTIMISE ###")
    result = SILICAFLUX.PV.SPECTRAL.OPTIMISE(spectrum, material)
    print(f"Optimised parameters: {result.optimised_parameters}")
    print(f"Efficiency: {result.efficiency * 100:.3f} %   Predicted energy gain: {result.predicted_energy_gain:.2f} W/m^2\n")

    print("### Baseline vs optimised simulation report ###")
    report = generate_simulation_output(spectrum, material)
    print(f"UV power fraction: {report.BASELINE_UV_RESPONSE * 100:.4f} % -> {report.OPTIMISED_UV_RESPONSE * 100:.4f} %")
    print(f"Annual energy:     {report.ANNUAL_ENERGY_BASELINE:.0f} -> {report.ANNUAL_ENERGY_OPTIMISED:.0f} Wh/m^2\n")

    print("### Parameter sweep (top 5 of the ranked table) ###")
    sweep_results = parameter_sweep(material, spectrum, max_configs=300)
    for r in sweep_results[:5]:
        print(f"  rank {r.rank}: {r.configuration}  net={r.net_energy_output_w_m2:.2f} W/m^2")
    print()

    print("### ML surrogate recommendation (validated against real physics) ###")
    configs = [
        SweepConfiguration(*combo)
        for combo in itertools.product(
            [0.95 * material.bandgap_eV, material.bandgap_eV, 1.1 * material.bandgap_eV],
            [material.thickness_nm, material.thickness_nm * 2],
            [1.3, 1.6, 1.9],
            [1.0], [298.15], [0.0],
        )
    ]
    ml_result = ml_optimise(material, spectrum, configs)
    print(f"Recommended configuration: {ml_result.recommended_configuration}")
    print(f"Validated net energy: {ml_result.recommended_net_energy_w_m2:.2f} W/m^2 "
          f"(ML pick accepted: {ml_result.ml_recommendation_accepted})")
    top_features = sorted(ml_result.feature_importance.items(), key=lambda kv: -abs(kv[1]))[:3]
    print(f"Top 3 features by |standardised coefficient|: {top_features}")


if __name__ == "__main__":
    main()
