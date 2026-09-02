"""
Run a baseline pipeline evaluation for every material in the library and
print a one-line summary of each -- a quick tour of the design space.

    python examples/baseline_report.py
"""

from silicaflux_pv_spectral import MATERIAL_LIBRARY, run_pipeline, terrestrial_spectrum


def main() -> None:
    spectrum = terrestrial_spectrum()
    print(f"Terrestrial spectrum: {spectrum.total_irradiance_w_m2:.1f} W/m^2 total "
          f"({spectrum.in_band('UV'):.1f} W/m^2 UV, {spectrum.in_band('VISIBLE'):.1f} W/m^2 visible, "
          f"{spectrum.in_band('NIR'):.1f} W/m^2 NIR)\n")

    header = f"{'MATERIAL':22s} {'EFF %':>8s} {'UV RESP %':>10s} {'UV POWER':>10s} {'NET W/m2':>10s}"
    print(header)
    print("-" * len(header))
    for name, material in MATERIAL_LIBRARY.items():
        result = run_pipeline(spectrum, material)
        print(
            f"{name:22s} {result.efficiency * 100:8.3f} "
            f"{result.spectral_response.uv_power_fraction * 100:10.4f} "
            f"{result.spectral_response.p_uv_w_m2:10.3f} {result.net_energy_output_w_m2:10.2f}"
        )


if __name__ == "__main__":
    main()
