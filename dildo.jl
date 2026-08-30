```julia
# ================================================================
# VIBRACORE
# Industrial Precision Vibration Machine
#
# Julia digital twin + closed-loop vibration controller
#
# Model:
#   Motor -> eccentric rotating mass -> vibrating platform
#
# Features:
#   - Mechanical vibration model
#   - Motor dynamics
#   - Frequency control
#   - Amplitude control
#   - PID feedback
#   - Accelerometer simulation
#   - Sensor noise
#   - Resonance detection
#   - Temperature model
#   - Bearing/wear model
#   - Emergency limits
#   - Automatic frequency sweep
#   - Performance telemetry
#
# This is a simulation/control prototype.
# Real machinery requires certified safety hardware,
# interlocks and validated motion-control systems.
# ================================================================

using Random
using Statistics
using Printf

Random.seed!(1234)

# ================================================================
# MACHINE PARAMETERS
# ================================================================

struct MachineConfig

    mass_kg::Float64

    eccentric_mass_kg::Float64
    eccentric_radius_m::Float64

    damping_Ns_m::Float64
    stiffness_N_m::Float64

    motor_inertia::Float64
    motor_max_torque_Nm::Float64

    max_frequency_Hz::Float64
    max_acceleration_g::Float64

    ambient_temperature_C::Float64
end


const MACHINE = MachineConfig(

    120.0,       # machine/platform mass

    2.5,         # eccentric mass
    0.035,       # eccentric radius

    850.0,       # damping

    180_000.0,   # stiffness

    0.015,       # motor inertia

    18.0,        # maximum motor torque

    80.0,        # maximum frequency

    12.0,        # maximum acceleration

    22.0         # ambient temperature
)

# ================================================================
# MACHINE STATE
# ================================================================

mutable struct MachineState

    # Mechanical state

    displacement_m::Float64
    velocity_mps::Float64
    acceleration_mps2::Float64

    # Motor

    motor_speed_rad_s::Float64
    motor_frequency_Hz::Float64
    motor_torque_Nm::Float64

    # Vibration

    vibration_amplitude_mm::Float64
    vibration_frequency_Hz::Float64
    acceleration_rms_g::Float64
    acceleration_peak_g::Float64

    # Sensors

    measured_amplitude_mm::Float64
    measured_frequency_Hz::Float64
    measured_acceleration_g::Float64

    # Thermal

    motor_temperature_C::Float64
    bearing_temperature_C::Float64

    # Condition

    bearing_wear_pct::Float64
    machine_health_pct::Float64

    # Controller

    target_frequency_Hz::Float64
    target_amplitude_mm::Float64

    integral_error::Float64
    previous_error::Float64

    emergency_stop::Bool
end


function create_machine()

    return MachineState(

        0.0,
        0.0,
        0.0,

        0.0,
        0.0,
        0.0,

        0.0,
        0.0,
        0.0,
        0.0,

        0.0,
        0.0,
        0.0,

        22.0,
        22.0,

        0.0,
        100.0,

        0.0,
        0.0,

        0.0,
        0.0,

        false
    )
end

# ================================================================
# NATURAL FREQUENCY
# ================================================================

function natural_frequency(
    config::MachineConfig
)

    ωn =
        sqrt(
            config.stiffness_N_m /
            config.mass_kg
        )

    return ωn / (2π)
end

# ================================================================
# DAMPING RATIO
# ================================================================

function damping_ratio(
    config::MachineConfig
)

    critical =
        2.0 *
        sqrt(
            config.stiffness_N_m *
            config.mass_kg
        )

    return (
        config.damping_Ns_m /
        critical
    )
end

# ================================================================
# ECCENTRIC FORCE
# ================================================================

function eccentric_force(
    config::MachineConfig,
    ω::Float64
)

    return (
        config.eccentric_mass_kg *
        config.eccentric_radius_m *
        ω^2
    )
end

# ================================================================
# THEORETICAL VIBRATION RESPONSE
#
# Forced vibration:
#
#       F0
# X = --------------------------
#     sqrt((k-mω²)²+(cω)²)
#
# ================================================================

function vibration_amplitude(
    config::MachineConfig,
    frequency_Hz::Float64
)

    ω =
        2π *
        frequency_Hz

    force =
        eccentric_force(
            config,
            ω
        )

    denominator =
        sqrt(
            (
                config.stiffness_N_m -
                config.mass_kg * ω^2
            )^2
            +
            (
                config.damping_Ns_m *
                ω
            )^2
        )

    displacement =
        force /
        denominator

    return displacement
end

# ================================================================
# MACHINE DYNAMICS
# ================================================================

function mechanical_step!(
    state::MachineState,
    config::MachineConfig,
    dt::Float64
)

    if state.emergency_stop

        state.motor_torque_Nm = 0.0

        state.motor_speed_rad_s *=
            exp(-8.0 * dt)

        return
    end

    ω =
        state.motor_speed_rad_s

    # Excitation force

    F =
        eccentric_force(
            config,
            ω
        )

    # Spring force

    spring_force =
        -config.stiffness_N_m *
        state.displacement_m

    # Damping force

    damping_force =
        -config.damping_Ns_m *
        state.velocity_mps

    # Net force

    net_force =
        F +
        spring_force +
        damping_force

    state.acceleration_mps2 =
        net_force /
        config.mass_kg

    state.velocity_mps +=
        state.acceleration_mps2 *
        dt

    state.displacement_m +=
        state.velocity_mps *
        dt

end

# ================================================================
# MOTOR MODEL
# ================================================================

function motor_step!(
    state::MachineState,
    config::MachineConfig,
    dt::Float64
)

    if state.emergency_stop

        state.motor_torque_Nm = 0.0

        return
    end

    target_ω =
        2π *
        state.target_frequency_Hz

    speed_error =
        target_ω -
        state.motor_speed_rad_s

    # Simple motor speed controller

    kp = 1.8
    ki = 0.8

    torque =
        kp *
        speed_error

    torque =
        clamp(
            torque,
            -config.motor_max_torque_Nm,
            config.motor_max_torque_Nm
        )

    state.motor_torque_Nm =
        torque

    motor_acceleration =
        (
            torque -
            0.025 *
            state.motor_speed_rad_s
        ) /
        config.motor_inertia

    state.motor_speed_rad_s +=
        motor_acceleration *
        dt

    state.motor_speed_rad_s =
        max(
            state.motor_speed_rad_s,
            0.0
        )

    state.motor_frequency_Hz =
        state.motor_speed_rad_s /
        (2π)
end

# ================================================================
# SENSOR MODEL
# ================================================================

function sensor_update!(
    state::MachineState,
    config::MachineConfig
)

    frequency =
        state.motor_frequency_Hz

    theoretical =
        vibration_amplitude(
            config,
            frequency
        )

    # Add small sensor noise

    amplitude_noise =
        randn() *
        0.005

    frequency_noise =
        randn() *
        0.01

    acceleration =
        (
            theoretical *
            (2π * frequency)^2
        )

    acceleration_g =
        acceleration /
        9.80665

    acceleration_noise =
        randn() *
        0.03

    state.vibration_amplitude_mm =
        theoretical *
        1000.0

    state.vibration_frequency_Hz =
        frequency

    state.measured_amplitude_mm =
        max(
            0.0,
            state.vibration_amplitude_mm +
            amplitude_noise
        )

    state.measured_frequency_Hz =
        max(
            0.0,
            frequency +
            frequency_noise
        )

    state.acceleration_peak_g =
        abs(
            acceleration_g
        )

    state.acceleration_rms_g =
        state.acceleration_peak_g /
        sqrt(2)

    state.measured_acceleration_g =
        max(
            0.0,
            state.acceleration_rms_g +
            acceleration_noise
        )
end

# ================================================================
# CLOSED LOOP AMPLITUDE CONTROLLER
# ================================================================

function amplitude_controller!(
    state::MachineState,
    dt::Float64
)

    error =
        state.target_amplitude_mm -
        state.measured_amplitude_mm

    state.integral_error +=
        error * dt

    # Anti-windup

    state.integral_error =
        clamp(
            state.integral_error,
            -20.0,
            20.0
        )

    derivative =
        (
            error -
            state.previous_error
        ) / dt

    kp = 3.0
    ki = 0.25
    kd = 0.05

    correction =
        kp * error +
        ki * state.integral_error +
        kd * derivative

    state.target_frequency_Hz +=
        correction * 0.01

    state.target_frequency_Hz =
        clamp(
            state.target_frequency_Hz,
            1.0,
            MACHINE.max_frequency_Hz
        )

    state.previous_error =
        error
end

# ================================================================
# THERMAL MODEL
# ================================================================

function thermal_model!(
    state::MachineState,
    config::MachineConfig,
    dt::Float64
)

    motor_power =
        abs(
            state.motor_torque_Nm *
            state.motor_speed_rad_s
        )

    heating =
        motor_power *
        0.0008

    cooling =
        (
            state.motor_temperature_C -
            config.ambient_temperature_C
        ) *
        0.01

    state.motor_temperature_C +=
        (
            heating -
            cooling
        ) * dt

    bearing_heating =
        0.0005 *
        state.motor_speed_rad_s^2

    bearing_cooling =
        (
            state.bearing_temperature_C -
            config.ambient_temperature_C
        ) *
        0.012

    state.bearing_temperature_C +=
        (
            bearing_heating -
            bearing_cooling
        ) * dt
end

# ================================================================
# BEARING WEAR
# ================================================================

function wear_model!(
    state::MachineState,
    dt::Float64
)

    vibration_factor =
        state.acceleration_rms_g /
        5.0

    thermal_factor =
        max(
            0.0,
            (
                state.bearing_temperature_C -
                40.0
            ) / 50.0
        )

    speed_factor =
        state.motor_frequency_Hz /
        50.0

    wear_rate =
        0.000001 *
        (
            1.0 +
            vibration_factor +
            thermal_factor +
            speed_factor
        )

    state.bearing_wear_pct +=
        wear_rate * dt

    state.bearing_wear_pct =
        min(
            100.0,
            state.bearing_wear_pct
        )

    state.machine_health_pct =
        100.0 -
        state.bearing_wear_pct
end

# ================================================================
# RESONANCE DETECTION
# ================================================================

function resonance_check(
    state::MachineState,
    config::MachineConfig
)

    fn =
        natural_frequency(
            config
        )

    difference =
        abs(
            state.motor_frequency_Hz -
            fn
        )

    if difference <
       0.75

        return true
    end

    return false
end

# ================================================================
# SAFETY SYSTEM
# ================================================================

function safety_check!(
    state::MachineState,
    config::MachineConfig
)

    if state.measured_acceleration_g >
       config.max_acceleration_g

        state.emergency_stop =
            true

        println(
            "!!! EMERGENCY STOP: " *
            "ACCELERATION LIMIT !!!"
        )
    end

    if state.motor_temperature_C >
       95.0

        state.emergency_stop =
            true

        println(
            "!!! EMERGENCY STOP: " *
            "MOTOR OVERHEAT !!!"
        )
    end

    if state.bearing_temperature_C >
       90.0

        state.emergency_stop =
            true

        println(
            "!!! EMERGENCY STOP: " *
            "BEARING OVERHEAT !!!"
        )
    end
end

# ================================================================
# TELEMETRY
# ================================================================

function print_telemetry(
    state::MachineState,
    time::Float64
)

    @printf(
        "t=%6.2fs | f=%6.2f Hz | " *
        "A=%7.3f mm | RMS=%6.3f g | " *
        "Motor=%6.1f°C | Bearing=%6.1f°C | " *
        "Wear=%6.3f%%\n",

        time,

        state.motor_frequency_Hz,

        state.measured_amplitude_mm,

        state.measured_acceleration_g,

        state.motor_temperature_C,

        state.bearing_temperature_C,

        state.bearing_wear_pct
    )
end

# ================================================================
# FREQUENCY SWEEP
# ================================================================

function frequency_sweep(
    config::MachineConfig
)

    println()
    println(
        "================================================"
    )

    println(
        " AUTOMATIC RESONANCE / RESPONSE SWEEP"
    )

    println(
        "================================================"
    )

    fn =
        natural_frequency(
            config
        )

    println(
        "Natural frequency ≈ ",
        round(
            fn,
            digits=3
        ),
        " Hz"
    )

    println()

    for frequency in
        1.0:1.0:60.0

        amplitude =
            vibration_amplitude(
                config,
                frequency
            )

        acceleration =
            amplitude *
            (
                2π *
                frequency
            )^2

        acceleration_g =
            acceleration /
            9.80665

        @printf(
            "%6.1f Hz | %9.4f mm | %7.3f g\n",
            frequency,
            amplitude * 1000,
            acceleration_g
        )
    end
end

# ================================================================
# MAIN SIMULATION
# ================================================================

function simulate_machine!(
    state::MachineState,
    config::MachineConfig;

    duration_s = 20.0,
    dt = 0.001,

    target_frequency = 25.0,
    target_amplitude_mm = 2.0

)

    state.target_frequency_Hz =
        target_frequency

    state.target_amplitude_mm =
        target_amplitude_mm

    println()
    println(
        "================================================"
    )

    println(
        " VIBRACORE INDUSTRIAL DIGITAL TWIN"
    )

    println(
        "================================================"
    )

    println(
        "Machine mass: ",
        config.mass_kg,
        " kg"
    )

    println(
        "Target frequency: ",
        target_frequency,
        " Hz"
    )

    println(
        "Target amplitude: ",
        target_amplitude_mm,
        " mm"
    )

    println(
        "Natural frequency: ",
        round(
            natural_frequency(config),
            digits=3
        ),
        " Hz"
    )

    println(
        "Damping ratio: ",
        round(
            damping_ratio(config),
            digits=4
        )
    )

    println(
        "================================================"
    )

    steps =
        Int(
            duration_s /
            dt
        )

    telemetry_interval =
        Int(
            0.25 /
            dt
        )

    for step in 1:steps

        time =
            step * dt

        # --------------------------------------------------------
        # 1. Motor dynamics
        # --------------------------------------------------------

        motor_step!(
            state,
            config,
            dt
        )

        # --------------------------------------------------------
        # 2. Mechanical dynamics
        # --------------------------------------------------------

        mechanical_step!(
            state,
            config,
            dt
        )

        # --------------------------------------------------------
        # 3. Sensors
        # --------------------------------------------------------

        sensor_update!(
            state,
            config
        )

        # --------------------------------------------------------
        # 4. Closed-loop controller
        # --------------------------------------------------------

        amplitude_controller!(
            state,
            dt
        )

        # --------------------------------------------------------
        # 5. Thermal system
        # --------------------------------------------------------

        thermal_model!(
            state,
            config,
            dt
        )

        # --------------------------------------------------------
        # 6. Wear model
        # --------------------------------------------------------

        wear_model!(
            state,
            dt
        )

        # --------------------------------------------------------
        # 7. Resonance protection
        # --------------------------------------------------------

        if resonance_check(
            state,
            config
        )

            # Back away from resonance

            state.target_frequency_Hz +=
                0.02

        end

        # --------------------------------------------------------
        # 8. Safety
        # --------------------------------------------------------

        safety_check!(
            state,
            config
        )

        # --------------------------------------------------------
        # 9. Telemetry
        # --------------------------------------------------------

        if mod(
            step,
            telemetry_interval
        ) == 0

            print_telemetry(
                state,
                time
            )
        end

        if state.emergency_stop

            println()
            println(
                "SIMULATION HALTED"
            )

            break
        end
    end

    println()
    println(
        "================================================"
    )

    println(
        " FINAL MACHINE CONDITION"
    )

    println(
        "================================================"
    )

    println(
        "Frequency: ",
        round(
            state.motor_frequency_Hz,
            digits=3
        ),
        " Hz"
    )

    println(
        "Amplitude: ",
        round(
            state.measured_amplitude_mm,
            digits=4
        ),
        " mm"
    )

    println(
        "Acceleration RMS: ",
        round(
            state.measured_acceleration_g,
            digits=4
        ),
        " g"
    )

    println(
        "Motor temperature: ",
        round(
            state.motor_temperature_C,
            digits=2
        ),
        " °C"
    )

    println(
        "Bearing temperature: ",
        round(
            state.bearing_temperature_C,
            digits=2
        ),
        " °C"
    )

    println(
        "Bearing wear: ",
        round(
            state.bearing_wear_pct,
            digits=5
        ),
        "%"
    )

    println(
        "Machine health: ",
        round(
            state.machine_health_pct,
            digits=3
        ),
        "%"
    )

    println(
        "Emergency stop: ",
        state.emergency_stop
    )

    println(
        "================================================"
    )
end

# ================================================================
# RUN
# ================================================================

machine =
    create_machine()

# First inspect the mechanical response

frequency_sweep(
    MACHINE
)

# Then run closed-loop machine

simulate_machine!(
    machine,
    MACHINE;

    duration_s = 20.0,

    dt = 0.001,

    target_frequency = 25.0,

    target_amplitude_mm = 2.0
)
```

