"""
Command-line entry point.

    python -m silicaflux_pv_spectral.main --material SILICON --mode report
    python -m silicaflux_pv_spectral.main --material PEROVSKITE --mode optimise --json-out result.json
    python -m silicaflux_pv_spectral.main --material SILICON --mode sweep --max-sweep-configs 200
    python -m silicaflux_pv_spectral.main --material SILICON --mode optimise --architecture tandem
    python -m silicaflux_pv_spectral.main --material SILICON --plot-dir plots/
"""

from __future__ import annotations

import argparse

from .constants import STC_TEMPERATURE_K
from .engine import generate_simulation_output, optimise
from .graphs import build_graph_data, render_graphs_matplotlib
from .io_utils import write_json
from .materials import MATERIAL_LIBRARY
from .parameter_sweep import parameter_sweep
from .pipeline import run_pipeline
from .spectrum import terrestrial_spectrum


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="silicaflux-pv-spectral", description="SilicaFlux PV spectral optimisation engine")
    parser.add_argument("--material", choices=sorted(MATERIAL_LIBRARY.keys()), default="SILICON")
    parser.add_argument("--mode", choices=["baseline", "optimise", "sweep", "report"], default="report")
    parser.add_argument("--architecture", choices=["single_junction", "tandem"], default="single_junction")
    parser.add_argument("--temperature-c", type=float, default=STC_TEMPERATURE_K - 273.15, help="ambient temperature, degC")
    parser.add_argument("--wind-speed", type=float, default=1.0, help="wind speed, m/s")
    parser.add_argument("--max-sweep-configs", type=int, default=500)
    parser.add_argument("--json-out", type=str, default=None, help="write the result as machine-readable JSON")
    parser.add_argument("--plot-dir", type=str, default=None, help="render the seven spectral graphs (requires matplotlib)")
    return parser


def _print_pipeline_summary(result) -> None:
    print(f"Incident irradiance:      {result.incident_power_w_m2:10.2f} W/m^2")
    print(f"Absorbed power:           {result.absorbed_power_w_m2:10.2f} W/m^2")
    print(f"Delivered electrical power (P_total): {result.spectral_response.p_total_w_m2:10.2f} W/m^2")
    print(f"  UV / Visible / NIR:     {result.spectral_response.p_uv_w_m2:8.2f} / "
          f"{result.spectral_response.p_visible_w_m2:8.2f} / {result.spectral_response.p_nir_w_m2:8.2f} W/m^2")
    print(f"UV power fraction:        {result.spectral_response.uv_power_fraction * 100:9.3f} %")
    print(f"Efficiency:               {result.efficiency * 100:9.3f} %")
    print(f"Cell temperature:         {result.thermal_state.cell_temperature_k - 273.15:9.2f} degC")
    print(f"Optical / Recombination / Thermal loss: {result.optical_loss_w_m2:.2f} / "
          f"{result.recombination_loss_w_m2:.2f} / {result.thermal_loss_w_m2:.2f} W/m^2")
    if result.degradation:
        print(f"Degradation rate:         {result.degradation.degradation_rate_per_year * 100:9.3f} %/yr")
    print(f"Net energy output:        {result.net_energy_output_w_m2:10.2f} W/m^2")


def main(argv: list[str] | None = None) -> int:
    parser = build_argparser()
    args = parser.parse_args(argv)

    material = MATERIAL_LIBRARY[args.material]
    spectrum = terrestrial_spectrum()
    temperature_k = args.temperature_c + 273.15

    result_for_export = None
    pipeline_for_plots = None

    if args.mode == "baseline":
        pipeline_result = run_pipeline(spectrum, material, ambient_temperature_k=temperature_k, wind_speed_m_s=args.wind_speed)
        print(f"=== SilicaFlux baseline: {material.material_name} ===")
        _print_pipeline_summary(pipeline_result)
        result_for_export = pipeline_result
        pipeline_for_plots = pipeline_result

    elif args.mode == "optimise":
        result = optimise(spectrum, material, temperature=temperature_k, architecture=args.architecture, wind_speed_m_s=args.wind_speed)
        print(f"=== SilicaFlux optimise: {material.material_name} ({args.architecture}) ===")
        print(f"Efficiency:               {result.efficiency * 100:9.3f} %")
        print(f"Predicted energy gain:    {result.predicted_energy_gain:10.2f} W/m^2")
        print(f"UV / Visible / NIR power: {result.uv_power:8.2f} / {result.visible_power:8.2f} / {result.nir_power:8.2f} W/m^2")
        print(f"Optimised parameters:     {result.optimised_parameters}")
        result_for_export = result
        pipeline_for_plots = run_pipeline(spectrum, material, ambient_temperature_k=temperature_k, wind_speed_m_s=args.wind_speed)

    elif args.mode == "sweep":
        sweep_results = parameter_sweep(material, spectrum, max_configs=args.max_sweep_configs)
        print(f"=== SilicaFlux parameter sweep: {material.material_name} ({len(sweep_results)} configurations) ===")
        print(f"{'RANK':>5} {'BANDGAP_eV':>11} {'THICK_nm':>10} {'AR_n':>6} {'UV_RESP':>9} {'EFF_%':>7} {'NET_W/m2':>10}")
        for r in sweep_results[:15]:
            c = r.configuration
            print(f"{r.rank:5d} {c.bandgap_eV:11.4f} {c.thickness_nm:10.0f} {c.ar_index:6.2f} "
                  f"{r.uv_response:9.4f} {r.total_efficiency * 100:7.3f} {r.net_energy_output_w_m2:10.2f}")
        result_for_export = sweep_results
        pipeline_for_plots = run_pipeline(spectrum, material, ambient_temperature_k=temperature_k, wind_speed_m_s=args.wind_speed)

    else:  # report
        output = generate_simulation_output(spectrum, material, temperature=temperature_k, wind_speed_m_s=args.wind_speed)
        print(f"=== SilicaFlux simulation report: {material.material_name} ===")
        print(f"{'':25s} {'BASELINE':>12} {'OPTIMISED':>12}")
        print(f"{'Efficiency (%)':25s} {output.BASELINE_EFFICIENCY * 100:12.3f} {output.OPTIMISED_EFFICIENCY * 100:12.3f}")
        print(f"{'UV response (%)':25s} {output.BASELINE_UV_RESPONSE * 100:12.4f} {output.OPTIMISED_UV_RESPONSE * 100:12.4f}")
        print(f"{'UV power (W/m2)':25s} {output.BASELINE_UV_POWER:12.3f} {output.OPTIMISED_UV_POWER:12.3f}")
        print(f"{'Annual energy (Wh/m2)':25s} {output.ANNUAL_ENERGY_BASELINE:12.0f} {output.ANNUAL_ENERGY_OPTIMISED:12.0f}")
        print(f"\nUV loss:            {output.UV_LOSS:10.2f} W/m^2")
        print(f"Optical loss:       {output.OPTICAL_LOSS:10.2f} W/m^2")
        print(f"Thermal loss:       {output.THERMAL_LOSS:10.2f} W/m^2")
        print(f"Recombination loss: {output.RECOMBINATION_LOSS:10.2f} W/m^2")
        print(f"Degradation loss (lifetime): {output.DEGRADATION_LOSS:10.0f} Wh/m^2")
        result_for_export = output
        pipeline_for_plots = run_pipeline(spectrum, material, ambient_temperature_k=temperature_k, wind_speed_m_s=args.wind_speed)

    if args.json_out:
        write_json(result_for_export, args.json_out)
        print(f"\nWrote {args.json_out}")

    if args.plot_dir and pipeline_for_plots is not None:
        graph_data = build_graph_data(pipeline_for_plots)
        written = render_graphs_matplotlib(graph_data, args.plot_dir)
        if written:
            print(f"\nWrote {len(written)} graphs to {args.plot_dir}")
        else:
            print("\nmatplotlib not installed -- skipped plot rendering")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
