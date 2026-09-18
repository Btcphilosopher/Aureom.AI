ThreeGorgesHydro

Project.toml
name = "ThreeGorgesHydro"
uuid = "7f2b8d7e-3a8c-4c9b-bc51-3f7a3e1c8d21"
authors = ["Hydropower Research"]
version = "0.1.0"

[deps]
CSV = "336ed68f-0bac-5ca0-87d4-7b16caf5d00b"
DataFrames = "a93c6f00-e57d-5684-b7b6-d8193f3a2e7e"
Dates = "ade2ca70-3891-5945-98fb-dc099432e06a"
JuMP = "4076af6c-e467-56ae-b986-b466b2749572"
HiGHS = "87dc4568-4c63-4a98-9c4c-9f4f1a4a9f0c"
Statistics = "10745b16-90b1-5c2f-98f3-4d4d9c1a9b2a"
Random = "9a3f8284-686f-5f34-9a0f-0c1b9a8d7c5e"

[compat]
julia = "1.10"
CSV = "0.10"
DataFrames = "1"
JuMP = "1"
HiGHS = "1"
src/ThreeGorgesHydro.jl
module ThreeGorgesHydro

using CSV
using DataFrames
using Dates
using Statistics
using Random
using JuMP
using HiGHS

include("reservoir.jl")
include("turbines.jl")
include("hydrology.jl")
include("dispatch.jl")
include("economics.jl")
include("forecasting.jl")
include("optimisation.jl")

export Reservoir,
       ReservoirState,
       TurbineFleet,
       turbine_power,
       hydraulic_head,
       storage_from_level,
       level_from_storage,
       reservoir_step,
       generate_inflows,
       load_inflows,
       dispatch_power,
       simulate,
       annual_energy,
       capacity_factor,
       revenue,
       forecast_inflows,
       optimise_dispatch

end
src/reservoir.jl
"""
Three Gorges reservoir model.

All physical calculations use SI units:

volume      m³
flow        m³/s
level       m
time        seconds
power       MW
"""

struct Reservoir

    name::String

    min_level::Float64
    normal_level::Float64
    max_level::Float64

    min_storage::Float64
    normal_storage::Float64
    max_storage::Float64

end


struct ReservoirState

    time::DateTime

    level::Float64
    storage::Float64

    inflow::Float64
    turbine_flow::Float64
    spill::Float64

end


"""
Approximate reservoir storage from water level.

For a production model this should be replaced by
a measured elevation-storage curve.
"""
function storage_from_level(
    r::Reservoir,
    level::Float64
)

    level = clamp(
        level,
        r.min_level,
        r.max_level
    )

    fraction =
        (level - r.min_level) /
        (r.max_level - r.min_level)

    return r.min_storage +
           fraction *
           (r.max_storage - r.min_storage)

end


"""
Approximate reservoir level from storage.
"""
function level_from_storage(
    r::Reservoir,
    storage::Float64
)

    storage = clamp(
        storage,
        r.min_storage,
        r.max_storage
    )

    fraction =
        (storage - r.min_storage) /
        (r.max_storage - r.min_storage)

    return r.min_level +
           fraction *
           (r.max_level - r.min_level)

end


"""
Perform one reservoir mass-balance timestep.

V(t+1) = V(t) + (Qin - Qturbine - Qspill)dt
"""
function reservoir_step(
    r::Reservoir,
    storage::Float64,
    inflow::Float64,
    turbine_flow::Float64,
    spill::Float64,
    dt_seconds::Float64
)

    new_storage =
        storage +
        (
            inflow -
            turbine_flow -
            spill
        ) * dt_seconds

    new_storage = clamp(
        new_storage,
        r.min_storage,
        r.max_storage
    )

    return new_storage

end


"""
Determine whether reservoir level is within
normal operating bounds.
"""
function reservoir_valid(
    r::Reservoir,
    level::Float64
)

    return (
        level >= r.min_level &&
        level <= r.max_level
    )

end
src/turbines.jl
const WATER_DENSITY = 1000.0
const GRAVITY = 9.80665


struct TurbineFleet

    name::String

    units::Int

    unit_capacity_mw::Float64

    max_flow_per_unit::Float64

    efficiency::Float64

end


"""
Total installed generation capacity.
"""
function installed_capacity(
    fleet::TurbineFleet
)

    return fleet.units *
           fleet.unit_capacity_mw

end


"""
Total maximum turbine discharge.
"""
function maximum_flow(
    fleet::TurbineFleet
)

    return fleet.units *
           fleet.max_flow_per_unit

end


"""
Calculate hydraulic head.

head = reservoir elevation - tailwater elevation
"""
function hydraulic_head(
    reservoir_level::Float64,
    tailwater_level::Float64
)

    return max(
        reservoir_level -
        tailwater_level,
        0.0
    )

end


"""
Calculate hydroelectric power.

P = ρgQHη
"""
function turbine_power(
    flow::Float64,
    head::Float64,
    efficiency::Float64
)

    power_w =
        WATER_DENSITY *
        GRAVITY *
        flow *
        head *
        efficiency

    return power_w / 1_000_000.0

end


"""
Calculate power using a turbine fleet.
"""
function fleet_power(
    fleet::TurbineFleet,
    flow::Float64,
    head::Float64
)

    flow =
        min(
            flow,
            maximum_flow(fleet)
        )

    power =
        turbine_power(
            flow,
            head,
            fleet.efficiency
        )

    return min(
        power,
        installed_capacity(fleet)
    )

end


"""
Calculate water required for a desired power output.
"""
function required_flow(
    fleet::TurbineFleet,
    power_mw::Float64,
    head::Float64
)

    if head <= 0
        return Inf
    end

    power_w =
        power_mw * 1_000_000.0

    return power_w /
        (
            WATER_DENSITY *
            GRAVITY *
            head *
            fleet.efficiency
        )

end
src/hydrology.jl
"""
Generate synthetic hourly inflow data.

This is deliberately a synthetic hydrological model.
It is not historical Three Gorges data.
"""

function generate_inflows(
    start_date::DateTime,
    hours::Int;
    mean_flow::Float64 = 14000.0,
    seasonal_amplitude::Float64 = 0.35,
    noise_fraction::Float64 = 0.10,
    scenario::Symbol = :normal,
    seed::Int = 42
)

    Random.seed!(seed)

    timestamps =
        [
            start_date +
            Hour(i - 1)
            for i in 1:hours
        ]

    flows = Float64[]

    scenario_multiplier =
        if scenario == :wet
            1.25
        elseif scenario == :dry
            0.75
        elseif scenario == :flood
            1.50
        elseif scenario == :drought
            0.55
        else
            1.0
        end

    for i in 1:hours

        day =
            (i - 1) / 24.0

        seasonal =
            1.0 +
            seasonal_amplitude *
            sin(
                2π *
                (day - 100.0) /
                365.0
            )

        noise =
            1.0 +
            noise_fraction *
            randn()

        flow =
            mean_flow *
            seasonal *
            scenario_multiplier *
            noise

        push!(
            flows,
            max(flow, 100.0)
        )

    end

    return DataFrame(
        timestamp = timestamps,
        inflow_m3s = flows
    )

end


"""
Load inflow CSV.

Expected columns:

timestamp,inflow_m3s
"""
function load_inflows(
    filename::String
)

    df = CSV.read(
        filename,
        DataFrame
    )

    df.timestamp =
        DateTime.(df.timestamp)

    return df

end
src/dispatch.jl
"""
Determine turbine flow under a simple
reservoir operating strategy.
"""
function dispatch_flow(
    reservoir::Reservoir,
    fleet::TurbineFleet,
    level::Float64,
    inflow::Float64;
    strategy::Symbol = :balanced
)

    max_flow =
        maximum_flow(fleet)

    if strategy == :maximum

        return min(
            inflow,
            max_flow
        )

    elseif strategy == :balanced

        # Attempt to pass normal inflows through
        # the turbines without unnecessary spill.

        return min(
            inflow,
            max_flow
        )

    elseif strategy == :conservative

        # Retain more water in the reservoir.

        return min(
            inflow * 0.75,
            max_flow
        )

    elseif strategy == :flood_protection

        # Increase generation as reservoir level rises.

        if level >
           reservoir.normal_level

            return max_flow
        else
            return min(
                inflow,
                max_flow
            )
        end

    else

        error(
            "Unknown dispatch strategy: $strategy"
        )

    end

end


"""
Dispatch power for a particular state.
"""
function dispatch_power(
    reservoir::Reservoir,
    fleet::TurbineFleet,
    level::Float64,
    inflow::Float64;
    tailwater::Float64 = 60.0,
    strategy::Symbol = :balanced
)

    flow =
        dispatch_flow(
            reservoir,
            fleet,
            level,
            inflow,
            strategy = strategy
        )

    head =
        hydraulic_head(
            level,
            tailwater
        )

    power =
        fleet_power(
            fleet,
            flow,
            head
        )

    return (
        flow = flow,
        head = head,
        power = power
    )

end


"""
Run a complete hourly simulation.
"""
function simulate(
    reservoir::Reservoir,
    fleet::TurbineFleet,
    inflows::DataFrame;
    initial_level::Float64 = reservoir.normal_level,
    tailwater::Float64 = 60.0,
    strategy::Symbol = :balanced,
    electricity_price::Float64 = 60.0
)

    n = nrow(inflows)

    timestamps =
        inflows.timestamp

    storage =
        storage_from_level(
            reservoir,
            initial_level
        )

    levels = Float64[]
    storage_values = Float64[]
    turbine_flows = Float64[]
    spill_flows = Float64[]
    heads = Float64[]
    powers = Float64[]
    energies = Float64[]
    revenues = Float64[]

    for i in 1:n

        inflow =
            inflows.inflow_m3s[i]

        level =
            level_from_storage(
                reservoir,
                storage
            )

        dispatch =
            dispatch_power(
                reservoir,
                fleet,
                level,
                inflow,
                tailwater = tailwater,
                strategy = strategy
            )

        turbine_flow =
            dispatch.flow

        head =
            dispatch.head

        power =
            dispatch.power

        spill =
            max(
                0.0,
                inflow -
                turbine_flow
            )

        dt = 3600.0

        storage =
            reservoir_step(
                reservoir,
                storage,
                inflow,
                turbine_flow,
                spill,
                dt
            )

        energy =
            power

        revenue =
            energy *
            electricity_price

        push!(levels, level)
        push!(storage_values, storage)
        push!(turbine_flows, turbine_flow)
        push!(spill_flows, spill)
        push!(heads, head)
        push!(powers, power)
        push!(energies, energy)
        push!(revenues, revenue)

    end

    return DataFrame(
        timestamp = timestamps,
        level_m = levels,
        storage_m3 = storage_values,
        inflow_m3s = inflows.inflow_m3s,
        turbine_flow_m3s = turbine_flows,
        spill_m3s = spill_flows,
        head_m = heads,
        power_mw = powers,
        energy_mwh = energies,
        revenue = revenues
    )

end
src/economics.jl
"""
Total energy generated in MWh.
"""
function annual_energy(
    simulation::DataFrame
)

    return sum(
        simulation.energy_mwh
    )

end


"""
Total energy in GWh.
"""
function annual_energy_gwh(
    simulation::DataFrame
)

    return annual_energy(simulation) /
           1000.0

end


"""
Total energy in TWh.
"""
function annual_energy_twh(
    simulation::DataFrame
)

    return annual_energy(simulation) /
           1_000_000.0

end


"""
Average power.
"""
function average_power(
    simulation::DataFrame
)

    return mean(
        simulation.power_mw
    )

end


"""
Capacity factor.

energy / maximum possible energy
"""
function capacity_factor(
    simulation::DataFrame,
    installed_capacity_mw::Float64
)

    hours =
        nrow(simulation)

    maximum_energy =
        installed_capacity_mw *
        hours

    return sum(
        simulation.energy_mwh
    ) / maximum_energy

end


"""
Total electricity revenue.
"""
function revenue(
    simulation::DataFrame
)

    return sum(
        simulation.revenue
    )

end


"""
Total spilled water volume.
"""
function spilled_water_m3(
    simulation::DataFrame
)

    return sum(
        simulation.spill_m3s
    ) * 3600.0

end


"""
Simple operating cost model.
"""
function operating_cost(
    simulation::DataFrame;
    variable_cost_gbp_mwh::Float64 = 2.0,
    fixed_cost_gbp_year::Float64 = 0.0
)

    energy =
        annual_energy(
            simulation
        )

    return energy *
           variable_cost_gbp_mwh +
           fixed_cost_gbp_year

end


"""
Net revenue.
"""
function net_revenue(
    simulation::DataFrame;
    variable_cost_gbp_mwh::Float64 = 2.0,
    fixed_cost_gbp_year::Float64 = 0.0
)

    return revenue(simulation) -
           operating_cost(
               simulation,
               variable_cost_gbp_mwh =
                   variable_cost_gbp_mwh,
               fixed_cost_gbp_year =
                   fixed_cost_gbp_year
           )

end
src/forecasting.jl
"""
Simple moving-average inflow forecast.

This is intentionally basic.
It can later be replaced with ARIMA,
machine learning or hydrological forecasts.
"""
function forecast_inflows(
    inflows::DataFrame;
    window::Int = 168,
    horizon::Int = 24
)

    n =
        nrow(inflows)

    start =
        max(
            1,
            n - window + 1
        )

    recent =
        inflows.inflow_m3s[start:n]

    prediction =
        mean(recent)

    timestamps =
        [
            inflows.timestamp[end] +
            Hour(i)
            for i in 1:horizon
        ]

    return DataFrame(
        timestamp = timestamps,
        forecast_inflow_m3s =
            fill(
                prediction,
                horizon
            )
    )

end


"""
Seasonal mean forecast.
"""
function seasonal_forecast(
    timestamp::DateTime;
    mean_flow::Float64 = 14000.0
)

    day =
        dayofyear(timestamp)

    seasonal =
        1.0 +
        0.35 *
        sin(
            2π *
            (day - 100) /
            365
        )

    return mean_flow *
           seasonal

end
src/optimisation.jl
"""
Optimise hourly turbine generation.

Objective:

maximise electricity-market revenue.

Constraints:

- turbine capacity
- reservoir storage
- water balance
- maximum spill
"""

function optimise_dispatch(
    reservoir::Reservoir,
    fleet::TurbineFleet,
    inflows::DataFrame;
    prices::Vector{Float64},
    initial_level::Float64 =
        reservoir.normal_level,
    tailwater::Float64 = 60.0
)

    n =
        nrow(inflows)

    if length(prices) != n
        error(
            "Price vector must have the same length as inflow data."
        )
    end

    initial_storage =
        storage_from_level(
            reservoir,
            initial_level
        )

    max_flow =
        maximum_flow(fleet)

    model =
        Model(HiGHS.Optimizer)

    set_silent(model)

    @variable(
        model,
        0 <= turbine_flow[1:n] <= max_flow
    )

    @variable(
        model,
        reservoir.min_storage <=
        storage[1:n] <=
        reservoir.max_storage
    )

    @variable(
        model,
        spill[1:n] >= 0
    )

    # Reservoir balance

    @constraint(
        model,
        storage[1] ==
        initial_storage +
        (
            inflows.inflow_m3s[1] -
            turbine_flow[1] -
            spill[1]
        ) * 3600.0
    )

    for t in 2:n

        @constraint(
            model,
            storage[t] ==
            storage[t-1] +
            (
                inflows.inflow_m3s[t] -
                turbine_flow[t] -
                spill[t]
            ) * 3600.0
        )

    end

    # Convert flow to approximate power.

    # For optimisation we use normal reservoir
    # head as a linearised approximation.
    head =
        reservoir.normal_level -
        tailwater

    efficiency =
        fleet.efficiency

    power_per_flow =
        WATER_DENSITY *
        GRAVITY *
        head *
        efficiency /
        1_000_000.0

    @expression(
        model,
        power[t=1:n],
        turbine_flow[t] *
        power_per_flow
    )

    @objective(
        model,
        Max,
        sum(
            prices[t] *
            power[t]
            for t in 1:n
        )
    )

    optimize!(model)

    if !is_solved_and_feasible(model)
        error(
            "Optimisation failed."
        )
    end

    flows =
        value.(turbine_flow)

    storages =
        value.(storage)

    spills =
        value.(spill)

    powers =
        flows .* power_per_flow

    return DataFrame(
        timestamp = inflows.timestamp,
        inflow_m3s =
            inflows.inflow_m3s,
        turbine_flow_m3s =
            flows,
        storage_m3 =
            storages,
        spill_m3s =
            spills,
        power_mw =
            powers,
        price =
            prices,
        revenue =
            powers .* prices
    )

end
data/inflow.csv

A small example dataset:

timestamp,inflow_m3s
2026-01-01T00:00:00,11000
2026-01-01T01:00:00,11100
2026-01-01T02:00:00,10900
2026-01-01T03:00:00,11200
2026-01-01T04:00:00,11400
2026-01-01T05:00:00,11600
2026-01-01T06:00:00,11800
2026-01-01T07:00:00,11700
2026-01-01T08:00:00,11900
2026-01-01T09:00:00,12100
2026-01-01T10:00:00,12000
2026-01-01T11:00:00,12200
2026-01-01T12:00:00,12400
2026-01-01T13:00:00,12300
2026-01-01T14:00:00,12500
2026-01-01T15:00:00,12600
2026-01-01T16:00:00,12500
2026-01-01T17:00:00,12300
2026-01-01T18:00:00,12100
2026-01-01T19:00:00,11900
2026-01-01T20:00:00,11700
2026-01-01T21:00:00,11500
2026-01-01T22:00:00,11300
2026-01-01T23:00:00,11200
data/reservoir_levels.csv
level_m,storage_m3
145,22000000000
150,26000000000
155,30000000000
160,34000000000
165,38000000000
170,42000000000
175,45000000000
data/electricity_prices.csv
timestamp,price_gbp_mwh
2026-01-01T00:00:00,55
2026-01-01T01:00:00,52
2026-01-01T02:00:00,50
2026-01-01T03:00:00,49
2026-01-01T04:00:00,50
2026-01-01T05:00:00,54
2026-01-01T06:00:00,65
2026-01-01T07:00:00,78
2026-01-01T08:00:00,90
2026-01-01T09:00:00,85
2026-01-01T10:00:00,80
2026-01-01T11:00:00,76
2026-01-01T12:00:00,72
2026-01-01T13:00:00,70
2026-01-01T14:00:00,74
2026-01-01T15:00:00,82
2026-01-01T16:00:00,95
2026-01-01T17:00:00,110
2026-01-01T18:00:00,120
2026-01-01T19:00:00,105
2026-01-01T20:00:00,90
2026-01-01T21:00:00,78
2026-01-01T22:00:00,68
2026-01-01T23:00:00,60
examples/three_gorges_simulation.jl
using Pkg

# Activate project relative to this file.
Pkg.activate(
    joinpath(
        @__DIR__,
        ".."
    )
)

using ThreeGorgesHydro
using CSV
using DataFrames
using Dates
using Statistics

println()
println("==============================================")
println(" THREE GORGES HYDROELECTRIC SIMULATOR")
println("==============================================")
println()

# ------------------------------------------------
# Reservoir
# ------------------------------------------------

reservoir =
    Reservoir(
        "Three Gorges Reservoir",

        145.0,          # minimum operating level
        175.0,          # normal maximum level
        175.0,

        22.0e9,        # minimum storage
        45.0e9,        # normal storage
        45.0e9
    )

# ------------------------------------------------
# Generating fleet
# ------------------------------------------------

fleet =
    TurbineFleet(
        "Three Gorges Generating Fleet",

        34,             # configurable unit count
        700.0,          # MW/unit
        6000.0,         # m³/s/unit
        0.92            # efficiency
    )

println(
    "Installed capacity: ",
    installed_capacity(fleet),
    " MW"
)

println(
    "Maximum turbine flow: ",
    maximum_flow(fleet),
    " m³/s"
)

# ------------------------------------------------
# Generate one year of synthetic hydrology
# ------------------------------------------------

println()
println(
    "Generating synthetic hydrology..."
)

inflows =
    generate_inflows(
        DateTime(2026, 1, 1),
        8760,
        mean_flow = 14000.0,
        scenario = :normal,
        seed = 123
    )

println(
    "Hours simulated: ",
    nrow(inflows)
)

# ------------------------------------------------
# Run physical simulation
# ------------------------------------------------

println()
println("Running reservoir simulation...")

result =
    simulate(
        reservoir,
        fleet,
        inflows,
        initial_level = 165.0,
        tailwater = 60.0,
        strategy = :balanced,
        electricity_price = 60.0
    )

# ------------------------------------------------
# Results
# ------------------------------------------------

energy_twh =
    annual_energy_twh(result)

energy_gwh =
    annual_energy_gwh(result)

cf =
    capacity_factor(
        result,
        installed_capacity(fleet)
    )

total_revenue =
    revenue(result)

spilled =
    spilled_water_m3(result)

println()
println("==============================================")
println(" SIMULATION RESULTS")
println("==============================================")

println(
    "Energy generated: ",
    round(energy_gwh, digits=2),
    " GWh"
)

println(
    "Energy generated: ",
    round(energy_twh, digits=4),
    " TWh"
)

println(
    "Average power: ",
    round(
        average_power(result),
        digits=2
    ),
    " MW"
)

println(
    "Capacity factor: ",
    round(
        cf * 100,
        digits=2
    ),
    "%"
)

println(
    "Revenue: £",
    round(
        total_revenue,
        digits=2
    )
)

println(
    "Spilled water: ",
    round(
        spilled / 1e9,
        digits=3
    ),
    " billion m³"
)

println()

# ------------------------------------------------
# Forecast next 24 hours
# ------------------------------------------------

forecast =
    forecast_inflows(
        inflows,
        window = 168,
        horizon = 24
    )

println(
    "Next 24-hour average forecast inflow: ",
    round(
        mean(
            forecast.forecast_inflow_m3s
        ),
        digits=2
    ),
    " m³/s"
)

# ------------------------------------------------
# Save result
# ------------------------------------------------

mkpath(
    joinpath(
        @__DIR__,
        "..",
        "output"
    )
)

CSV.write(
    joinpath(
        @__DIR__,
        "..",
        "output",
        "simulation_result.csv"
    ),
    result
)

println()
println(
    "Simulation saved to output/simulation_result.csv"
)

println()
println("Complete.")
test/runtests.jl
using Test
using Pkg

Pkg.activate(
    joinpath(
        @__DIR__,
        ".."
    )
)

using ThreeGorgesHydro
using Dates
using DataFrames

@testset "Three Gorges Hydro" begin

    reservoir =
        Reservoir(
            "Test Reservoir",
            145.0,
            175.0,
            175.0,
            20e9,
            40e9,
            45e9
        )

    fleet =
        TurbineFleet(
            "Test Fleet",
            34,
            700.0,
            6000.0,
            0.92
        )

    @test installed_capacity(fleet) == 23800.0

    @test maximum_flow(fleet) ==
          204000.0

    @test hydraulic_head(
        175.0,
        60.0
    ) == 115.0

    power =
        turbine_power(
            1000.0,
            100.0,
            0.9
        )

    @test power > 0

    storage =
        storage_from_level(
            reservoir,
            160.0
        )

    level =
        level_from_storage(
            reservoir,
            storage
        )

    @test isapprox(
        level,
        160.0,
        atol=1e-8
    )

    inflows =
        generate_inflows(
            DateTime(2026, 1, 1),
            48,
            seed = 42
        )

    @test nrow(inflows) == 48

    @test all(
        inflows.inflow_m3s .> 0
    )

    result =
        simulate(
            reservoir,
            fleet,
            inflows,
            initial_level = 165.0
        )

    @test nrow(result) == 48

    @test all(
        result.power_mw .>= 0
    )

    @test annual_energy(result) > 0

    @test capacity_factor(
        result,
        installed_capacity(fleet)
    ) >= 0

end

println()
println("All Three Gorges Hydro tests passed.")
Run it

From inside three_gorges_hydro:

julia --project=. -e 'using Pkg; Pkg.instantiate()'

Then:

julia --project=. examples/three_gorges_simulation.jl

And tests:

julia --project=. test/runtests.jl

