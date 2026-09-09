# FOLDTECH iOS

## Working Folding Phone Technology Prototype

Create a new **iOS App in Xcode** named:

```text
FoldTech
```

Use:

```text
Swift
SwiftUI
iOS 17+
```

No external packages are required.

The objective is to create a working prototype of a hypothetical folding iPhone.

This is a **software simulation** of folding-phone technology, not an attempt to access undocumented Apple hardware sensors.

---

# 1. PROJECT STRUCTURE

Create:

```text
FoldTech/
│
├── FoldTechApp.swift
├── ContentView.swift
├── FoldModel.swift
├── FoldPhoneView.swift
├── EngineeringView.swift
└── Info.plist
```

---

# 2. FoldTechApp.swift

```swift
import SwiftUI

@main
struct FoldTechApp: App {

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

Use the modern SwiftUI `App` lifecycle.

---

# 3. FoldModel.swift

Create the central simulation model.

```swift
import SwiftUI
import Foundation

@Observable
final class FoldModel {

    // MARK: - Fold State

    var angle: Double = 180.0

    var isAnimating = false

    // MARK: - Device Parameters

    var deviceWidth: Double = 180
    var deviceHeight: Double = 360

    var hingeWidth: Double = 14

    var batteryCapacity: Double = 4800

    var batteryLevel: Double = 82

    var brightness: Double = 0.65

    var refreshRate: Double = 120

    // MARK: - Environment

    var ambientTemperature: Double = 22

    // MARK: - Computed Device State

    var foldDescription: String {

        switch angle {

        case 170...180:
            return "OPEN"

        case 110..<170:
            return "PARTIAL"

        case 80..<110:
            return "HALF FOLD"

        case 20..<80:
            return "FOLDED"

        default:
            return "CLOSED"
        }
    }

    var displayMode: String {

        switch angle {

        case 150...180:
            return "FULL DISPLAY"

        case 100..<150:
            return "ADAPTIVE"

        case 70..<100:
            return "DUAL PANEL"

        default:
            return "COMPACT"
        }
    }

    var bendRadius: Double {

        let radians = max(angle * .pi / 180, 0.01)

        return max(1.5, hingeWidth / radians)
    }

    var hingeTorque: Double {

        let normalized = abs(90 - angle) / 90

        return 0.35 + normalized * 1.4
    }

    var powerConsumption: Double {

        let displayPower =
            brightness * 3.8

        let refreshPower =
            refreshRate / 120.0 * 1.2

        let foldPower =
            isAnimating ? 1.8 : 0.0

        return displayPower + refreshPower + foldPower + 1.4
    }

    var temperature: Double {

        ambientTemperature +
        powerConsumption * 1.65
    }

    var estimatedBatteryHours: Double {

        guard powerConsumption > 0 else {
            return 0
        }

        return batteryCapacity *
        (batteryLevel / 100.0) /
        (powerConsumption * 1000 / 1000)
    }

    var displayStrain: Double {

        let radius = max(bendRadius, 0.1)

        return min(
            100,
            0.35 / radius * 100
        )
    }

    // MARK: - Controls

    func setAngle(_ newAngle: Double) {

        angle = min(
            180,
            max(0, newAngle)
        )
    }

    func toggleFold() {

        let target: Double

        if angle > 90 {
            target = 30
        } else {
            target = 180
        }

        withAnimation(
            .spring(
                response: 0.55,
                dampingFraction: 0.82
            )
        ) {
            isAnimating = true
            angle = target
        }

        DispatchQueue.main.asyncAfter(
            deadline: .now() + 0.6
        ) {
            self.isAnimating = false
        }
    }
}
```

---

# 4. ContentView.swift

Create the main application.

```swift
import SwiftUI

struct ContentView: View {

    @State private var model = FoldModel()

    @State private var showingEngineering = false

    var body: some View {

        NavigationStack {

            ZStack {

                Color.black
                    .ignoresSafeArea()

                ScrollView {

                    VStack(spacing: 24) {

                        header

                        FoldPhoneView(
                            model: model
                        )
                        .frame(
                            height: 360
                        )

                        foldControl

                        statusPanel

                        actionButtons

                    }
                    .padding()
                }
            }

            .navigationDestination(
                isPresented: $showingEngineering
            ) {

                EngineeringView(
                    model: model
                )
            }
        }

        .preferredColorScheme(.dark)
    }

    // MARK: Header

    private var header: some View {

        VStack(
            alignment: .leading,
            spacing: 6
        ) {

            Text("FOLDTECH")

                .font(
                    .system(
                        size: 32,
                        weight: .bold,
                        design: .rounded
                    )
                )

            Text("FOLDING DEVICE LABORATORY")

                .font(
                    .system(
                        size: 11,
                        weight: .medium,
                        design: .monospaced
                    )
                )
                .foregroundStyle(.secondary)
        }

        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
    }

    // MARK: Fold Control

    private var foldControl: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            HStack {

                Text("FOLD ANGLE")

                    .font(
                        .system(
                            size: 12,
                            weight: .bold,
                            design: .monospaced
                        )
                    )

                Spacer()

                Text(
                    "\(Int(model.angle))°"
                )

                .font(
                    .system(
                        size: 18,
                        weight: .bold,
                        design: .monospaced
                    )
                )
            }

            Slider(
                value: $model.angle,
                in: 0...180
            )
        }
    }

    // MARK: Status

    private var statusPanel: some View {

        VStack(spacing: 12) {

            statusRow(
                "STATE",
                model.foldDescription
            )

            statusRow(
                "DISPLAY",
                model.displayMode
            )

            statusRow(
                "HINGE TORQUE",
                String(
                    format: "%.2f Nm",
                    model.hingeTorque
                )
            )

            statusRow(
                "BEND RADIUS",
                String(
                    format: "%.2f mm",
                    model.bendRadius
                )
            )

            statusRow(
                "TEMPERATURE",
                String(
                    format: "%.1f °C",
                    model.temperature
                )
            )

            statusRow(
                "POWER",
                String(
                    format: "%.1f W",
                    model.powerConsumption
                )
            )

            statusRow(
                "DISPLAY STRAIN",
                String(
                    format: "%.1f%%",
                    model.displayStrain
                )
            )
        }

        .padding()

        .background(
            RoundedRectangle(
                cornerRadius: 20
            )
            .fill(
                Color.white.opacity(0.06)
            )
        )
    }

    private func statusRow(
        _ title: String,
        _ value: String
    ) -> some View {

        HStack {

            Text(title)

                .font(
                    .system(
                        size: 11,
                        weight: .medium,
                        design: .monospaced
                    )
                )
                .foregroundStyle(.secondary)

            Spacer()

            Text(value)

                .font(
                    .system(
                        size: 13,
                        weight: .semibold,
                        design: .monospaced
                    )
                )
        }
    }

    // MARK: Buttons

    private var actionButtons: some View {

        VStack(spacing: 12) {

            Button {

                model.toggleFold()

            } label: {

                Label(
                    model.angle > 90
                    ? "FOLD DEVICE"
                    : "OPEN DEVICE",
                    systemImage:
                        model.angle > 90
                        ? "rectangle.compress.vertical"
                        : "rectangle.expand.vertical"
                )

                .frame(
                    maxWidth: .infinity
                )
            }

            .buttonStyle(
                .borderedProminent
            )

            Button {

                showingEngineering = true

            } label: {

                Label(
                    "ENGINEERING MODE",
                    systemImage: "waveform.path.ecg"
                )

                .frame(
                    maxWidth: .infinity
                )
            }

            .buttonStyle(
                .bordered
            )
        }
    }
}
```

---

# 5. FoldPhoneView.swift

This is the important visual component.

Create a two-panel folding phone.

```swift
import SwiftUI

struct FoldPhoneView: View {

    let model: FoldModel

    var body: some View {

        GeometryReader { geometry in

            ZStack {

                phoneBody(
                    size: geometry.size
                )

                hinge(
                    size: geometry.size
                )
            }

            .frame(
                maxWidth: .infinity,
                maxHeight: .infinity
            )
        }
    }

    // MARK: Phone

    private func phoneBody(
        size: CGSize
    ) -> some View {

        HStack(
            spacing: 0
        ) {

            panel(
                left: true
            )

            panel(
                left: false
            )
        }

        .frame(
            width: min(
                size.width * 0.82,
                330
            ),
            height: 300
        )

        .rotation3DEffect(

            .degrees(
                180 - model.angle
            ),

            axis: (
                x: 0,
                y: 1,
                z: 0
            ),

            perspective: 0.45
        )

        .shadow(
            color: .black.opacity(0.8),
            radius: 25,
            y: 15
        )
    }

    // MARK: Panel

    private func panel(
        left: Bool
    ) -> some View {

        ZStack {

            RoundedRectangle(
                cornerRadius: 24
            )

            .fill(
                LinearGradient(
                    colors: [
                        Color(
                            white: 0.16
                        ),
                        Color(
                            white: 0.05
                        )
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )

            RoundedRectangle(
                cornerRadius: 20
            )

            .stroke(
                Color.white.opacity(0.15),
                lineWidth: 1
            )

            VStack {

                HStack {

                    Circle()
                        .fill(
                            Color.black
                        )
                        .frame(
                            width: 7,
                            height: 7
                        )

                    Spacer()
                }

                Spacer()

                if model.angle > 100 {

                    Text(
                        left
                        ? "FOLDTECH"
                        : "DIGITAL TWIN"
                    )

                    .font(
                        .system(
                            size: 16,
                            weight: .bold,
                            design: .rounded
                        )
                    )
                    .foregroundStyle(
                        .white.opacity(0.8)
                    )
                }

                Spacer()

                HStack {

                    Circle()
                        .fill(
                            Color.white.opacity(0.25)
                        )
                        .frame(
                            width: 8,
                            height: 8
                        )

                    Spacer()

                    Circle()
                        .fill(
                            Color.white.opacity(0.12)
                        )
                        .frame(
                            width: 8,
                            height: 8
                        )
                }
            }

            .padding(18)
        }
    }

    // MARK: Hinge

    private func hinge(
        size: CGSize
    ) -> some View {

        RoundedRectangle(
            cornerRadius: 5
        )

        .fill(
            LinearGradient(
                colors: [
                    .black,
                    .gray.opacity(0.8),
                    .black
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )

        .frame(
            width: 9,
            height: 275
        )

        .shadow(
            color: .black,
            radius: 4
        )
    }
}
```

---

# 6. EngineeringView.swift

Create a proper engineering screen.

```swift
import SwiftUI

struct EngineeringView: View {

    let model: FoldModel

    var body: some View {

        ScrollView {

            VStack(
                alignment: .leading,
                spacing: 20
            ) {

                Text("ENGINEERING")

                    .font(
                        .system(
                            size: 30,
                            weight: .bold,
                            design: .rounded
                        )
                    )

                section(
                    title: "MECHANICAL"
                ) {

                    metric(
                        "Fold Angle",
                        "\(String(format: "%.1f", model.angle))°"
                    )

                    metric(
                        "Hinge Torque",
                        "\(String(format: "%.3f", model.hingeTorque)) Nm"
                    )

                    metric(
                        "Bend Radius",
                        "\(String(format: "%.3f", model.bendRadius)) mm"
                    )
                }

                section(
                    title: "DISPLAY"
                ) {

                    metric(
                        "Display Mode",
                        model.displayMode
                    )

                    metric(
                        "Estimated Strain",
                        "\(String(format: "%.2f", model.displayStrain))%"
                    )
                }

                section(
                    title: "THERMAL"
                ) {

                    metric(
                        "Ambient",
                        "\(String(format: "%.1f", model.ambientTemperature)) °C"
                    )

                    metric(
                        "Device",
                        "\(String(format: "%.1f", model.temperature)) °C"
                    )
                }

                section(
                    title: "POWER"
                ) {

                    metric(
                        "Battery",
                        "\(String(format: "%.0f", model.batteryLevel))%"
                    )

                    metric(
                        "Power",
                        "\(String(format: "%.2f", model.powerConsumption)) W"
                    )

                    metric(
                        "Capacity",
                        "\(String(format: "%.0f", model.batteryCapacity)) Wh"
                    )
                }

                Divider()

                Text(
                    "SIMULATION MODEL"
                )

                .font(
                    .system(
                        size: 11,
                        weight: .bold,
                        design: .monospaced
                    )
                )

                Text(
                    "This prototype uses simplified parametric models for hinge torque, display bend radius, strain, power and thermal behaviour. Values are illustrative and are not measurements of commercial hardware."
                )

                .font(
                    .system(
                        size: 13
                    )
                )

                .foregroundStyle(
                    .secondary
                )
            }

            .padding()
        }

        .navigationTitle(
            "Engineering"
        )
    }

    private func section(
        title: String,
        @ViewBuilder content: () -> some View
    ) -> some View {

        VStack(
            alignment: .leading,
            spacing: 10
        ) {

            Text(title)

                .font(
                    .system(
                        size: 11,
                        weight: .bold,
                        design: .monospaced
                    )
                )
                .foregroundStyle(.secondary)

            VStack(
                spacing: 8,
                content: content
            )

            .padding()

            .background(
                RoundedRectangle(
                    cornerRadius: 16
                )
                .fill(
                    Color.white.opacity(0.05)
                )
            )
        }
    }

    private func metric(
        _ title: String,
        _ value: String
    ) -> some View {

        HStack {

            Text(title)

            Spacer()

            Text(value)

                .font(
                    .system(
                        size: 13,
                        weight: .semibold,
                        design: .monospaced
                    )
                )
        }
    }
}
```

---

# 7. IMPORTANT COMPILER REQUIREMENT

Because `@Observable` is used, add:

```swift
import Observation
```

to `FoldModel.swift`.

The final file begins:

```swift
import SwiftUI
import Foundation
import Observation
```

---

# 8. FIRST WORKING PRODUCT

When the application launches, it should display:

```text
FOLDTECH
FOLDING DEVICE LABORATORY

        ┌───────────┬───────────┐
        │           │           │
        │ FOLDTECH  │ DIGITAL   │
        │           │ TWIN      │
        │           │           │
        │           │           │
        └───────────┴───────────┘

FOLD ANGLE                         180°

──────────────●────────────────────

STATE                         OPEN
DISPLAY                 FULL DISPLAY
HINGE TORQUE                  0.35 Nm
BEND RADIUS                   ...
TEMPERATURE                   ...
POWER                         ...

[ FOLD DEVICE ]

[ ENGINEERING MODE ]
```

Dragging the slider should physically change the fold state.

Pressing **FOLD DEVICE** should animate the device from:

```text
180°
```

to:

```text
30°
```

and pressing it again should return it to:

```text
180°
```

---

# 9. NEXT IMPLEMENTATION STEP

Once this compiles, extend the application with:

### VERSION 2

Add:

```text
interactive drag-to-fold
3D perspective
hinge shadow
display curvature
camera bump
inner/outer display
```

### VERSION 3

Add:

```text
thermal visualisation
battery graph
power graph
fold-cycle counter
```

### VERSION 4

Add:

```text
material selection
hinge selection
display selection
device thickness
battery size
```

### VERSION 5

Add:

```text
design comparison
Monte Carlo
manufacturing tolerances
fold-cycle simulation
```

### VERSION 6

Add:

```text
Metal rendering
advanced 3D geometry
real-time engineering visualisation
```

---

# 10. CORE PRINCIPLE

Do not turn this into a generic settings application.

The **phone itself must remain the hero**.

The user should be able to physically manipulate the virtual device and immediately see:

```text
FOLD
 ↓
HINGE
 ↓
DISPLAY
 ↓
POWER
 ↓
THERMAL
 ↓
UI
```

change together.

The application is therefore a **folding-phone digital prototype**, not merely an information dashboard.

# FINAL AXIOM

**DO NOT BUILD A PHONE APP ABOUT A FOLDING PHONE.**

**BUILD A FOLDING PHONE INSIDE THE APP.**

The angle is the state.

The hinge is the mechanism.

The display is the surface.

The battery is the energy source.

The thermal model is the heat.

The UI responds to the geometry.

And the entire device moves as one computational object.

**FOLDTECH = PHONE × HINGE × DISPLAY × PHYSICS × IOS.**








# FOLD.OS

## Julia Adaptive Folding Phone Intelligence Engine

This is the first functional Julia implementation of FOLD.OS.

Its job is to calculate how a folding phone should behave based on:

* fold angle
* screen configuration
* battery
* temperature
* brightness
* refresh rate
* CPU/GPU workload
* user interaction
* hinge movement
* available display area

The engine produces an **adaptive device policy** which an iOS/Swift layer can consume.

---

# 1. FILE STRUCTURE

Create:

```text
fold-os/
├── Project.toml
├── src/
│   ├── FoldOS.jl
│   ├── types.jl
│   ├── geometry.jl
│   ├── power.jl
│   ├── thermal.jl
│   ├── performance.jl
│   ├── layout.jl
│   ├── hinge.jl
│   ├── policy.jl
│   └── simulation.jl
├── test/
│   └── runtests.jl
└── examples/
    └── simulate_phone.jl
```

For the first version, however, all of the functionality can be placed in a single `FoldOS.jl` file.

---

# 2. FoldOS.jl

```julia
module FoldOS

using LinearAlgebra
using Statistics

export
    FoldDevice,
    DeviceState,
    DevicePolicy,
    update!,
    recommend_policy,
    fold_state,
    display_mode,
    thermal_state,
    power_state,
    simulate,
    run_demo

# ============================================================
# CONSTANTS
# ============================================================

const MIN_ANGLE = 0.0
const MAX_ANGLE = 180.0

const SAFE_TEMP = 38.0
const WARM_TEMP = 42.0
const HOT_TEMP = 47.0
const CRITICAL_TEMP = 52.0

const LOW_BATTERY = 20.0
const CRITICAL_BATTERY = 8.0

# ============================================================
# DEVICE
# ============================================================

mutable struct FoldDevice

    width_mm::Float64
    height_mm::Float64
    thickness_mm::Float64

    hinge_radius_mm::Float64

    battery_capacity_mah::Float64

    display_refresh_max::Float64

    display_brightness_max::Float64

end


# ============================================================
# REAL-TIME DEVICE STATE
# ============================================================

mutable struct DeviceState

    fold_angle::Float64

    fold_velocity::Float64

    battery_percent::Float64

    temperature_c::Float64

    brightness::Float64

    refresh_rate::Float64

    cpu_load::Float64

    gpu_load::Float64

    network_load::Float64

    camera_active::Bool

    gaming::Bool

    video_playback::Bool

    charging::Bool

    user_interacting::Bool

end


# ============================================================
# DEVICE POLICY
# ============================================================

struct DevicePolicy

    layout::Symbol

    display_panels::Int

    refresh_rate::Float64

    brightness::Float64

    thermal_mode::Symbol

    performance_mode::Symbol

    animation_scale::Float64

    gpu_quality::Float64

    background_activity::Float64

    haptic_intensity::Float64

    transition_speed::Float64

    reason::String

end


# ============================================================
# CLAMPING
# ============================================================

function clamp_angle(angle)

    return clamp(
        Float64(angle),
        MIN_ANGLE,
        MAX_ANGLE
    )

end


# ============================================================
# FOLD STATE
# ============================================================

function fold_state(angle)

    angle = clamp_angle(angle)

    if angle >= 165

        return :open

    elseif angle >= 115

        return :partial

    elseif angle >= 75

        return :tabletop

    elseif angle >= 20

        return :folded

    else

        return :closed

    end

end


# ============================================================
# DISPLAY MODE
# ============================================================

function display_mode(angle)

    state = fold_state(angle)

    if state == :open

        return :full_display

    elseif state == :partial

        return :adaptive_split

    elseif state == :tabletop

        return :dual_panel

    elseif state == :folded

        return :compact

    else

        return :cover_display

    end

end


# ============================================================
# DISPLAY GEOMETRY
# ============================================================

function display_geometry(device::FoldDevice,
                          angle)

    θ = deg2rad(
        clamp_angle(angle)
    )

    panel_width = device.width_mm / 2

    effective_width =
        panel_width +
        panel_width * abs(cos(θ))

    effective_height =
        device.height_mm

    visible_area =
        effective_width *
        effective_height

    return (
        width = effective_width,
        height = effective_height,
        area = visible_area
    )

end


# ============================================================
# BEND RADIUS
# ============================================================

function bend_radius(device::FoldDevice,
                     angle)

    θ = deg2rad(
        clamp_angle(angle)
    )

    if θ < 0.001

        return device.hinge_radius_mm

    end

    radius =
        device.hinge_radius_mm /
        max(sin(θ / 2), 0.05)

    return max(
        radius,
        device.hinge_radius_mm
    )

end


# ============================================================
# DISPLAY STRAIN
# ============================================================

function display_strain(device::FoldDevice,
                        angle)

    radius =
        bend_radius(
            device,
            angle
        )

    neutral_distance =
        0.05

    strain =
        neutral_distance /
        max(radius, 0.1)

    return strain

end


# ============================================================
# HINGE TORQUE
# ============================================================

function hinge_torque(device::FoldDevice,
                      state::DeviceState)

    angle_factor =
        abs(
            90.0 -
            state.fold_angle
        ) / 90.0

    velocity_factor =
        abs(
            state.fold_velocity
        ) / 180.0

    base_torque =
        0.30 +
        angle_factor * 1.20

    dynamic_torque =
        velocity_factor * 0.25

    return base_torque +
           dynamic_torque

end


# ============================================================
# POWER MODEL
# ============================================================

function estimate_power(
    state::DeviceState
)

    base_power = 0.8

    display_power =
        2.0 *
        state.brightness

    refresh_power =
        0.8 *
        state.refresh_rate /
        120.0

    cpu_power =
        2.5 *
        state.cpu_load

    gpu_power =
        3.0 *
        state.gpu_load

    network_power =
        0.7 *
        state.network_load

    camera_power =
        state.camera_active ?
        1.8 :
        0.0

    gaming_power =
        state.gaming ?
        2.5 :
        0.0

    video_power =
        state.video_playback ?
        1.2 :
        0.0

    charging_overhead =
        state.charging ?
        0.5 :
        0.0

    total =
        base_power +
        display_power +
        refresh_power +
        cpu_power +
        gpu_power +
        network_power +
        camera_power +
        gaming_power +
        video_power +
        charging_overhead

    return total

end


# ============================================================
# THERMAL MODEL
# ============================================================

function estimate_temperature(
    state::DeviceState
)

    power =
        estimate_power(state)

    ambient = 22.0

    thermal_resistance = 2.2

    temperature =
        ambient +
        power *
        thermal_resistance

    return temperature

end


# ============================================================
# THERMAL STATE
# ============================================================

function thermal_state(
    temperature
)

    if temperature < SAFE_TEMP

        return :normal

    elseif temperature < WARM_TEMP

        return :warm

    elseif temperature < HOT_TEMP

        return :hot

    elseif temperature < CRITICAL_TEMP

        return :critical

    else

        return :emergency

    end

end


# ============================================================
# POWER STATE
# ============================================================

function power_state(
    battery
)

    if battery > 50

        return :healthy

    elseif battery > LOW_BATTERY

        return :normal

    elseif battery > CRITICAL_BATTERY

        return :low

    else

        return :critical

    end

end


# ============================================================
# PERFORMANCE POLICY
# ============================================================

function performance_policy(
    state::DeviceState
)

    thermal =
        thermal_state(
            state.temperature_c
        )

    battery =
        power_state(
            state.battery_percent
        )

    if thermal == :emergency

        return :emergency

    elseif thermal == :critical

        return :thermal_throttle

    elseif battery == :critical

        return :battery_saver

    elseif battery == :low

        return :power_efficient

    elseif state.gaming

        return :high_performance

    elseif state.video_playback

        return :media

    else

        return :balanced

    end

end


# ============================================================
# ANIMATION POLICY
# ============================================================

function animation_scale_for(
    state::DeviceState
)

    thermal =
        thermal_state(
            state.temperature_c
        )

    battery =
        power_state(
            state.battery_percent
        )

    if thermal in (:critical, :emergency)

        return 0.35

    elseif battery == :critical

        return 0.40

    elseif battery == :low

        return 0.70

    else

        return 1.0

    end

end


# ============================================================
# LAYOUT POLICY
# ============================================================

function layout_policy(
    state::DeviceState
)

    return display_mode(
        state.fold_angle
    )

end


# ============================================================
# REFRESH POLICY
# ============================================================

function refresh_policy(
    device::FoldDevice,
    state::DeviceState
)

    thermal =
        thermal_state(
            state.temperature_c
        )

    battery =
        power_state(
            state.battery_percent
        )

    maximum =
        device.display_refresh_max

    if thermal == :emergency

        return 60.0

    elseif thermal == :critical

        return min(
            maximum,
            80.0
        )

    elseif battery == :critical

        return 60.0

    elseif battery == :low

        return min(
            maximum,
            90.0
        )

    elseif state.gaming

        return maximum

    else

        return min(
            maximum,
            state.refresh_rate
        )

    end

end


# ============================================================
# BRIGHTNESS POLICY
# ============================================================

function brightness_policy(
    state::DeviceState
)

    thermal =
        thermal_state(
            state.temperature_c
        )

    battery =
        power_state(
            state.battery_percent
        )

    brightness =
        state.brightness

    if thermal == :emergency

        return min(
            brightness,
            0.35
        )

    elseif thermal == :critical

        return min(
            brightness,
            0.55
        )

    elseif battery == :critical

        return min(
            brightness,
            0.45
        )

    else

        return brightness

    end

end


# ============================================================
# COMPLETE POLICY
# ============================================================

function recommend_policy(
    device::FoldDevice,
    state::DeviceState
)

    layout =
        layout_policy(state)

    thermal =
        thermal_state(
            state.temperature_c
        )

    performance =
        performance_policy(state)

    refresh =
        refresh_policy(
            device,
            state
        )

    brightness =
        brightness_policy(state)

    animations =
        animation_scale_for(state)

    panels =
        layout in
        (:full_display, :adaptive_split,
         :dual_panel) ?
        2 :
        1

    gpu_quality =
        performance == :high_performance ?
        1.0 :
        performance == :balanced ?
        0.85 :
        performance == :media ?
        0.75 :
        0.55

    background =
        performance in
        (:thermal_throttle,
         :battery_saver,
         :emergency) ?
        0.25 :
        1.0

    haptics =
        thermal in
        (:critical, :emergency) ?
        0.4 :
        1.0

    transition =
        animations

    reason =
        string(
            "layout=",
            layout,
            ", thermal=",
            thermal,
            ", performance=",
            performance,
            ", battery=",
            power_state(
                state.battery_percent
            )
        )

    return DevicePolicy(

        layout,
        panels,
        refresh,
        brightness,
        thermal,
        performance,
        animations,
        gpu_quality,
        background,
        haptics,
        transition,
        reason
    )

end


# ============================================================
# REAL-TIME UPDATE
# ============================================================

function update!(
    device::FoldDevice,
    state::DeviceState
)

    state.fold_angle =
        clamp_angle(
            state.fold_angle
        )

    # Recalculate thermal state
    calculated_temperature =
        estimate_temperature(state)

    # Smooth thermal response
    state.temperature_c =
        0.85 * state.temperature_c +
        0.15 * calculated_temperature

    # Obtain recommended policy
    policy =
        recommend_policy(
            device,
            state
        )

    return policy

end


# ============================================================
# SIMULATION
# ============================================================

function simulate(
    device::FoldDevice,
    state::DeviceState;
    duration = 10.0,
    dt = 0.1
)

    timestamps = Float64[]

    angles = Float64[]
    temperatures = Float64[]
    powers = Float64[]
    batteries = Float64[]
    hinge_torques = Float64[]

    t = 0.0

    while t <= duration

        policy =
            update!(
                device,
                state
            )

        power =
            estimate_power(state)

        torque =
            hinge_torque(
                device,
                state
            )

        push!(
            timestamps,
            t
        )

        push!(
            angles,
            state.fold_angle
        )

        push!(
            temperatures,
            state.temperature_c
        )

        push!(
            powers,
            power
        )

        push!(
            batteries,
            state.battery_percent
        )

        push!(
            hinge_torques,
            torque
        )

        # Battery consumption approximation
        battery_delta =
            power *
            dt /
            (device.battery_capacity_mah * 3.8)

        state.battery_percent =
            max(
                0.0,
                state.battery_percent -
                battery_delta * 100
            )

        t += dt

    end

    return (

        time = timestamps,

        angle = angles,

        temperature = temperatures,

        power = powers,

        battery = batteries,

        hinge_torque = hinge_torques

    )

end


# ============================================================
# DEMONSTRATION
# ============================================================

function run_demo()

    device =
        FoldDevice(

            75.0,

            160.0,

            6.5,

            3.5,

            4800.0,

            120.0,

            1.0

        )

    state =
        DeviceState(

            180.0,   # fold angle

            0.0,     # velocity

            82.0,    # battery

            25.0,    # temperature

            0.70,    # brightness

            120.0,   # refresh

            0.35,    # CPU

            0.20,    # GPU

            0.30,    # network

            false,   # camera

            false,   # gaming

            false,   # video

            false,   # charging

            true     # interaction

        )

    println()
    println("======================================")
    println("          FOLD.OS")
    println("  ADAPTIVE FOLDING PHONE ENGINE")
    println("======================================")
    println()

    for angle in
        [180.0, 150.0, 120.0,
         90.0, 60.0, 30.0]

        state.fold_angle = angle

        policy =
            update!(
                device,
                state
            )

        geometry =
            display_geometry(
                device,
                angle
            )

        strain =
            display_strain(
                device,
                angle
            )

        println(
            "ANGLE: ",
            angle,
            "°"
        )

        println(
            "STATE: ",
            fold_state(angle)
        )

        println(
            "DISPLAY: ",
            policy.layout
        )

        println(
            "PANELS: ",
            policy.display_panels
        )

        println(
            "BEND RADIUS: ",
            round(
                bend_radius(
                    device,
                    angle
                ),
                digits=3
            ),
            " mm"
        )

        println(
            "STRAIN: ",
            round(
                strain * 100,
                digits=3
            ),
            "%"
        )

        println(
            "TEMPERATURE: ",
            round(
                state.temperature_c,
                digits=2
            ),
            " °C"
        )

        println(
            "POWER: ",
            round(
                estimate_power(state),
                digits=2
            ),
            " W"
        )

        println(
            "PERFORMANCE: ",
            policy.performance_mode
        )

        println(
            "REFRESH: ",
            policy.refresh_rate,
            " Hz"
        )

        println(
            "======================================"
        )

    end

    return nothing

end

end
```

---

# 3. RUN IT

From the Julia terminal:

```julia
include("src/FoldOS.jl")

using .FoldOS

FoldOS.run_demo()
```

The engine will produce output resembling:

```text
======================================
          FOLD.OS
  ADAPTIVE FOLDING PHONE ENGINE
======================================

ANGLE: 180.0°
STATE: open
DISPLAY: full_display
PANELS: 2
BEND RADIUS: ...
STRAIN: ...
TEMPERATURE: ... °C
POWER: ... W
PERFORMANCE: balanced
REFRESH: 120.0 Hz

======================================

ANGLE: 90.0°
STATE: tabletop
DISPLAY: dual_panel
PANELS: 2
...

ANGLE: 30.0°
STATE: folded
DISPLAY: compact
PANELS: 1
...
```

---

# 4. THE IMPORTANT PART: ADAPTIVE DEVICE POLICY

FOLD.OS is not merely calculating the fold angle.

It is making decisions.

For example:

```text
FOLD ANGLE
    ↓
DISPLAY CONFIGURATION
    ↓
POWER DEMAND
    ↓
THERMAL STATE
    ↓
BATTERY STATE
    ↓
PERFORMANCE POLICY
    ↓
DISPLAY REFRESH
    ↓
ANIMATION QUALITY
    ↓
GPU QUALITY
    ↓
BACKGROUND ACTIVITY
```

This gives the iOS host something useful to consume.

---

# 5. SWIFT BRIDGE CONTRACT

The eventual Swift layer should receive a compact state structure.

Conceptually:

```text
FoldOSState
```

containing:

```text
foldAngle
foldState
displayMode
displayPanels
displayWidth
displayHeight
bendRadius
displayStrain
temperature
power
battery
refreshRate
brightness
performanceMode
animationScale
gpuQuality
backgroundActivity
```

SwiftUI can then make decisions based on this state.

For example:

```swift
switch foldState {

case "open":
    showExpandedInterface()

case "tabletop":
    showDualPanelInterface()

case "folded":
    showCompactInterface()

case "closed":
    showCoverInterface()

default:
    showAdaptiveInterface()
}
```

---

# 6. BETTER FOLDING EXPERIENCE

The most important feature to add next is **predictive folding**.

Instead of waiting for the user to finish folding:

```text
ANGLE
  ↓
CURRENT STATE
```

FOLD.OS should estimate:

```text
ANGLE
VELOCITY
ACCELERATION
  ↓
PREDICTED ANGLE
  ↓
PREDICTED DISPLAY STATE
  ↓
PREPARE UI
```

For example, if:

```text
angle = 142°
velocity = -60°/s
```

the engine can predict that the user is folding toward the tabletop state.

The iOS layer can prepare the alternate layout before the physical transition finishes.

---

# 7. ADD THIS PREDICTION FUNCTION

Add:

```julia
function predict_angle(
    state::DeviceState,
    horizon::Float64 = 0.15
)

    predicted =
        state.fold_angle +
        state.fold_velocity *
        horizon

    return clamp(
        predicted,
        MIN_ANGLE,
        MAX_ANGLE
    )

end
```

Then:

```julia
predicted =
    predict_angle(state)

predicted_mode =
    display_mode(predicted)
```

Now FOLD.OS can anticipate the user's next state.

---

# 8. HYSTERESIS

Do not allow the interface to constantly switch states around a boundary.

For example:

```text
89°
91°
89°
91°
89°
```

should not cause:

```text
TABLETOP
PARTIAL
TABLETOP
PARTIAL
TABLETOP
```

Create hysteresis.

```julia
mutable struct LayoutController

    current_mode::Symbol

end
```

Then require a meaningful threshold before changing mode.

This prevents UI flicker during real-world folding.

---

# 9. FOLD VELOCITY

Add:

```julia
function update_fold_velocity!(
    state::DeviceState,
    previous_angle::Float64,
    dt::Float64
)

    state.fold_velocity =
        (state.fold_angle -
         previous_angle) /
        max(dt, 0.0001)

end
```

Now FOLD.OS understands:

```text
opening
closing
stationary
fast folding
slow folding
```

---

# 10. PREDICTIVE UI POLICY

Add:

```julia
function predicted_policy(
    device::FoldDevice,
    state::DeviceState
)

    predicted =
        predict_angle(state)

    predicted_layout =
        display_mode(predicted)

    current_layout =
        display_mode(
            state.fold_angle
        )

    return (
        current = current_layout,
        predicted = predicted_layout,
        predicted_angle = predicted
    )

end
```

This is the beginning of a proper **fold-aware operating intelligence layer**.

---

# 11. THE BIGGER FOLD.OS ARCHITECTURE

Eventually:

```text
                    FOLD.OS
                       │
          ┌────────────┼────────────┐
          │            │            │
       HINGE        DISPLAY       DEVICE
       ENGINE        ENGINE       ENGINE
          │            │            │
          └────────────┼────────────┘
                       │
                STATE ESTIMATOR
                       │
             PREDICTION ENGINE
                       │
          ┌────────────┼────────────┐
          │            │            │
        POWER        THERMAL      BATTERY
          │            │            │
          └────────────┼────────────┘
                       │
                 POLICY ENGINE
                       │
          ┌────────────┼────────────┐
          │            │            │
         UI          GPU          HAPTICS
       POLICY       POLICY        POLICY
          │            │            │
          └────────────┼────────────┘
                       │
                  SWIFT / iOS
```

---

# 12. WHAT THIS ACTUALLY IMPROVES

FOLD.OS should ultimately make the phone better at:

### Faster transitions

Predict the next display configuration.

### Less UI flicker

Use hysteresis around fold thresholds.

### Better battery life

Reduce refresh/GPU/background activity when necessary.

### Better thermal behaviour

Adapt performance before overheating.

### Better animations

Scale animation complexity according to device state.

### Better multitasking

Move applications between panels according to available geometry.

### Better gaming

Prioritise GPU and refresh rate when battery/thermal conditions allow.

### Better media

Optimise the interface for tabletop mode.

### Better camera use

Adapt camera controls when the device is partially folded.

### Better accessibility

Use larger/simpler layouts when the available display geometry changes.

---

# 13. IMPORTANT BOUNDARY

FOLD.OS is an **adaptive software engine**.

It does not claim access to undocumented folding-phone hardware.

On a real iOS product, the native Swift layer would supply whatever hardware state Apple exposes to the application, and FOLD.OS would calculate the resulting policy.

The Julia engine can therefore be developed and tested today using:

```text
SIMULATED HINGE
SIMULATED DISPLAY
SIMULATED BATTERY
SIMULATED THERMAL STATE
SIMULATED PERFORMANCE
```

and later connected to whatever legitimate device APIs are available.

iOS also restricts arbitrary continuous background execution, so FOLD.OS should not be designed around a permanently running background Julia process. Instead, keep the real-time policy engine attached to active application sessions and use Apple's permitted background-task mechanisms for appropriate deferred work.

---

# 14. FINAL PRINCIPLE

**FOLD.OS SHOULD NOT CONTROL THE PHONE BY CONSTANTLY RUNNING MORE SOFTWARE.**

It should make the phone **more intelligent about when and how software runs**.

The fold becomes an input.

The hinge becomes a sensor.

The display becomes a dynamic surface.

The battery becomes a constraint.

Temperature becomes a constraint.

Performance becomes a resource.

The user becomes the signal.

FOLD.OS observes all of them and calculates:

**WHAT SHOULD THE PHONE DO NEXT?**

That is the beginning of a real adaptive folding-device software architecture.


















# FOLD.OS 2.0

## Julia Engineering & Adaptive Device Core

### `julia/src/FoldOS.jl`

```julia
module FoldOS

using LinearAlgebra
using Statistics
using Random
using Dates

export
    DeviceGeometry,
    HingeParameters,
    ThermalParameters,
    BatteryParameters,
    DisplayParameters,
    DeviceParameters,
    FoldState,
    DisplayGeometry,
    DisplayHealth,
    PowerState,
    ThermalState,
    ReliabilityState,
    FoldPrediction,
    DeviceState,
    DevicePolicy,
    FoldSimulation,
    clamp_angle,
    classify_fold,
    fold_kinematics,
    hinge_torque,
    display_geometry,
    display_health,
    thermal_step,
    battery_step,
    power_estimate,
    performance_policy,
    predict_fold,
    recommend_policy,
    step!,
    simulate,
    simulate_fold_cycle,
    monte_carlo,
    device_report


# ============================================================
# CONSTANTS
# ============================================================

const DEG2RAD = π / 180.0
const RAD2DEG = 180.0 / π

const DEFAULT_AMBIENT_C = 22.0

const OPEN_ENTER_DEG = 165.0
const OPEN_EXIT_DEG = 158.0

const PARTIAL_ENTER_DEG = 115.0
const PARTIAL_EXIT_DEG = 108.0

const TABLETOP_ENTER_DEG = 82.0
const TABLETOP_EXIT_DEG = 72.0

const FOLDED_ENTER_DEG = 20.0
const FOLDED_EXIT_DEG = 28.0

const THERMAL_WARM_C = 38.0
const THERMAL_HOT_C = 43.0
const THERMAL_CRITICAL_C = 50.0

const BATTERY_LOW_PERCENT = 20.0
const BATTERY_CRITICAL_PERCENT = 8.0


# ============================================================
# UTILITY
# ============================================================

clamp_angle(x) = clamp(Float64(x), 0.0, 180.0)

deg2rad(x) = x * DEG2RAD
rad2deg(x) = x * RAD2DEG

safe_div(a, b, fallback = 0.0) =
    abs(b) < eps(Float64) ? fallback : a / b


# ============================================================
# DEVICE GEOMETRY
# ============================================================

"""
Parametric physical geometry of the foldable device.

All dimensions are SI-compatible engineering quantities,
except where explicitly named otherwise.
"""
struct DeviceGeometry
    panel_width_mm::Float64
    panel_height_mm::Float64
    panel_thickness_mm::Float64
    hinge_width_mm::Float64
    hinge_radius_mm::Float64
    minimum_bend_radius_mm::Float64
end

DeviceGeometry(;
    panel_width_mm = 75.0,
    panel_height_mm = 160.0,
    panel_thickness_mm = 6.5,
    hinge_width_mm = 7.0,
    hinge_radius_mm = 3.5,
    minimum_bend_radius_mm = 1.5
) = DeviceGeometry(
    panel_width_mm,
    panel_height_mm,
    panel_thickness_mm,
    hinge_width_mm,
    hinge_radius_mm,
    minimum_bend_radius_mm
)


# ============================================================
# HINGE MODEL
# ============================================================

struct HingeParameters
    inertia::Float64
    damping::Float64
    friction::Float64
    stiffness::Float64
    detent_strength::Float64
    maximum_torque_nm::Float64
end

HingeParameters(;
    inertia = 0.002,
    damping = 0.0008,
    friction = 0.025,
    stiffness = 0.08,
    detent_strength = 0.04,
    maximum_torque_nm = 0.50
) = HingeParameters(
    inertia,
    damping,
    friction,
    stiffness,
    detent_strength,
    maximum_torque_nm
)


# ============================================================
# DISPLAY MODEL
# ============================================================

struct DisplayParameters
    neutral_axis_mm::Float64
    nominal_strain_limit::Float64
    hinge_exclusion_mm::Float64
end

DisplayParameters(;
    neutral_axis_mm = 0.05,
    nominal_strain_limit = 0.005,
    hinge_exclusion_mm = 7.0
) = DisplayParameters(
    neutral_axis_mm,
    nominal_strain_limit,
    hinge_exclusion_mm
)


# ============================================================
# BATTERY MODEL
# ============================================================

struct BatteryParameters
    capacity_mAh::Float64
    nominal_voltage_v::Float64
    maximum_charge_percent::Float64
    minimum_operating_percent::Float64
end

BatteryParameters(;
    capacity_mAh = 4800.0,
    nominal_voltage_v = 3.85,
    maximum_charge_percent = 100.0,
    minimum_operating_percent = 1.0
) = BatteryParameters(
    capacity_mAh,
    nominal_voltage_v,
    maximum_charge_percent,
    minimum_operating_percent
)

battery_capacity_wh(b::BatteryParameters) =
    b.capacity_mAh * b.nominal_voltage_v / 1000.0


# ============================================================
# THERMAL MODEL
# ============================================================

"""
First-order lumped thermal model.

R: thermal resistance, K/W
C: thermal capacitance, J/K
"""
struct ThermalParameters
    thermal_resistance_k_w::Float64
    thermal_capacitance_j_k::Float64
end

ThermalParameters(;
    thermal_resistance_k_w = 2.5,
    thermal_capacitance_j_k = 1200.0
) = ThermalParameters(
    thermal_resistance_k_w,
    thermal_capacitance_j_k
)


# ============================================================
# COMPLETE DEVICE PARAMETERS
# ============================================================

struct DeviceParameters
    geometry::DeviceGeometry
    hinge::HingeParameters
    display::DisplayParameters
    battery::BatteryParameters
    thermal::ThermalParameters
end

DeviceParameters(;
    geometry = DeviceGeometry(),
    hinge = HingeParameters(),
    display = DisplayParameters(),
    battery = BatteryParameters(),
    thermal = ThermalParameters()
) = DeviceParameters(
    geometry,
    hinge,
    display,
    battery,
    thermal
)


# ============================================================
# FOLD STATE
# ============================================================

struct FoldState
    angle_deg::Float64
    angular_velocity_deg_s::Float64
    angular_acceleration_deg_s2::Float64
    state::Symbol
    direction::Symbol
    stable::Bool
end


function classify_fold(angle::Real)

    a = clamp_angle(angle)

    if a >= OPEN_ENTER_DEG
        return :open
    elseif a >= PARTIAL_ENTER_DEG
        return :partial
    elseif a >= TABLETOP_ENTER_DEG
        return :tabletop
    elseif a >= FOLDED_ENTER_DEG
        return :folded
    else
        return :closed
    end
end


function fold_direction(velocity)

    if velocity > 0.1
        return :opening
    elseif velocity < -0.1
        return :closing
    else
        return :stationary
    end

end


function fold_state(
    angle,
    velocity = 0.0,
    acceleration = 0.0
)

    a = clamp_angle(angle)

    FoldState(
        a,
        velocity,
        acceleration,
        classify_fold(a),
        fold_direction(velocity),
        abs(velocity) < 0.25
    )
end


# ============================================================
# KINEMATICS
# ============================================================

function fold_kinematics(
    angle_deg,
    velocity_deg_s,
    acceleration_deg_s2,
    dt
)

    new_velocity =
        velocity_deg_s +
        acceleration_deg_s2 * dt

    new_angle =
        clamp_angle(
            angle_deg +
            velocity_deg_s * dt +
            0.5 * acceleration_deg_s2 * dt^2
        )

    fold_state(
        new_angle,
        new_velocity,
        acceleration_deg_s2
    )

end


# ============================================================
# HINGE TORQUE
# ============================================================

function hinge_torque(
    state::FoldState,
    p::HingeParameters
)

    θ = deg2rad(state.angle_deg)
    ω = deg2rad(state.angular_velocity_deg_s)

    elastic =
        p.stiffness * sin(θ)

    damping =
        p.damping * ω

    friction =
        p.friction * sign(ω)

    detent =
        p.detent_strength *
        sin(4.0 * θ)

    τ =
        elastic +
        damping +
        friction +
        detent

    clamp(abs(τ), 0.0, p.maximum_torque_nm)

end


# ============================================================
# DISPLAY GEOMETRY
# ============================================================

function display_geometry(
    state::FoldState,
    geometry::DeviceGeometry
)

    θ = deg2rad(state.angle_deg)

    panel_width =
        geometry.panel_width_mm

    height =
        geometry.panel_height_mm

    projected_width =
        panel_width +
        panel_width * abs(cos(θ))

    projected_area =
        panel_width *
        height *
        (1.0 + abs(cos(θ)))

    active_panels =
        state.state == :closed ||
        state.state == :folded ? 1 : 2

    DisplayGeometry(
        active_panels,
        projected_area,
        geometry.hinge_width_mm,
        projected_width,
        height,
        [
            state.angle_deg / 2.0,
            -state.angle_deg / 2.0
        ]
    )

end


struct DisplayGeometry
    active_panels::Int
    visible_area_mm2::Float64
    hinge_exclusion_mm::Float64
    usable_width_mm::Float64
    usable_height_mm::Float64
    panel_angle_deg::Vector{Float64}
end


# ============================================================
# BEND RADIUS / DISPLAY HEALTH
# ============================================================

function bend_radius(
    angle_deg,
    hinge_radius_mm
)

    θ = deg2rad(angle_deg)

    denominator =
        max(abs(sin(θ / 2.0)), 0.05)

    max(
        hinge_radius_mm,
        hinge_radius_mm / denominator
    )

end


struct DisplayHealth
    bend_radius_mm::Float64
    estimated_strain::Float64
    strain_limit::Float64
    safety_margin::Float64
    status::Symbol
end


function display_health(
    state::FoldState,
    p::DeviceParameters
)

    radius =
        bend_radius(
            state.angle_deg,
            p.geometry.hinge_radius_mm
        )

    strain =
        p.display.neutral_axis_mm /
        radius

    margin =
        safe_div(
            p.display.nominal_strain_limit - strain,
            p.display.nominal_strain_limit
        )

    status =
        strain >= p.display.nominal_strain_limit ? :warning :
        strain >= 0.8 * p.display.nominal_strain_limit ? :caution :
        :safe

    DisplayHealth(
        radius,
        strain,
        p.display.nominal_strain_limit,
        margin,
        status
    )

end


# ============================================================
# POWER MODEL
# ============================================================

function power_estimate(
    brightness,
    refresh_rate,
    cpu_load,
    gpu_load,
    network_load;
    camera = false,
    gaming = false,
    video = false,
    ai_load = 0.0,
    charging = false
)

    base = 0.8

    display =
        2.0 * clamp(brightness, 0, 1)

    refresh =
        0.8 *
        clamp(refresh_rate / 120.0, 0, 1)

    cpu =
        2.5 * clamp(cpu_load, 0, 1)

    gpu =
        3.0 * clamp(gpu_load, 0, 1)

    network =
        0.7 * clamp(network_load, 0, 1)

    camera_power =
        camera ? 1.8 : 0.0

    gaming_power =
        gaming ? 2.5 : 0.0

    video_power =
        video ? 1.2 : 0.0

    ai_power =
        2.0 * clamp(ai_load, 0, 1)

    charging_overhead =
        charging ? 0.5 : 0.0

    base +
    display +
    refresh +
    cpu +
    gpu +
    network +
    camera_power +
    gaming_power +
    video_power +
    ai_power +
    charging_overhead

end


# ============================================================
# THERMAL ENGINE
# ============================================================

struct ThermalState
    temperature_c::Float64
    heat_generation_w::Float64
    thermal_state::Symbol
end


function classify_thermal(temp)

    if temp >= THERMAL_CRITICAL_C
        :critical
    elseif temp >= THERMAL_HOT_C
        :hot
    elseif temp >= THERMAL_WARM_C
        :warm
    else
        :normal
    end

end


function thermal_step(
    temperature_c,
    power_w,
    ambient_c,
    p::ThermalParameters,
    dt
)

    heat_in =
        power_w

    heat_out =
        (temperature_c - ambient_c) /
        p.thermal_resistance_k_w

    dTdt =
        (heat_in - heat_out) /
        p.thermal_capacitance_j_k

    new_temperature =
        temperature_c +
        dTdt * dt

    ThermalState(
        new_temperature,
        power_w,
        classify_thermal(new_temperature)
    )

end


# ============================================================
# BATTERY
# ============================================================

struct PowerState
    power_w::Float64
    energy_remaining_Wh::Float64
    battery_percent::Float64
    estimated_runtime_h::Float64
end


function battery_step(
    energy_remaining_Wh,
    power_w,
    battery::BatteryParameters,
    dt
)

    dt_hours =
        dt / 3600.0

    consumed =
        power_w *
        dt_hours

    remaining =
        max(
            0.0,
            energy_remaining_Wh -
            consumed
        )

    capacity =
        battery_capacity_wh(battery)

    percent =
        100.0 *
        safe_div(
            remaining,
            capacity
        )

    runtime =
        power_w > 0.001 ?
        remaining / power_w :
        Inf

    PowerState(
        power_w,
        remaining,
        percent,
        runtime
    )

end


# ============================================================
# PERFORMANCE GOVERNOR
# ============================================================

function performance_policy(
    battery_percent,
    thermal_state,
    workload
)

    if thermal_state == :critical
        return :critical

    elseif thermal_state == :hot
        return :thermal_limited

    elseif battery_percent <= BATTERY_CRITICAL_PERCENT
        return :critical

    elseif battery_percent <= BATTERY_LOW_PERCENT
        return :power_efficient

    elseif workload == :gaming
        return :maximum_performance

    else
        return :balanced
    end

end


function refresh_policy(
    performance_mode
)

    Dict(
        :maximum_performance => 120.0,
        :balanced => 90.0,
        :power_efficient => 60.0,
        :thermal_limited => 60.0,
        :critical => 30.0
    )[performance_mode]

end


function animation_policy(
    performance_mode
)

    Dict(
        :maximum_performance => 1.0,
        :balanced => 1.0,
        :power_efficient => 0.75,
        :thermal_limited => 0.50,
        :critical => 0.25
    )[performance_mode]

end


# ============================================================
# PREDICTION
# ============================================================

struct FoldPrediction
    current_angle_deg::Float64
    predicted_angle_deg::Float64
    predicted_state::Symbol
    confidence::Float64
    horizon_s::Float64
end


function predict_fold(
    state::FoldState;
    horizon_s = 0.15
)

    predicted =
        clamp_angle(
            state.angle_deg +
            state.angular_velocity_deg_s *
            horizon_s +
            0.5 *
            state.angular_acceleration_deg_s2 *
            horizon_s^2
        )

    predicted_state =
        classify_fold(predicted)

    velocity_confidence =
        clamp(
            1.0 -
            abs(state.angular_acceleration_deg_s2) /
            500.0,
            0.0,
            1.0
        )

    stability_confidence =
        state.stable ? 1.0 : 0.75

    confidence =
        velocity_confidence *
        stability_confidence

    FoldPrediction(
        state.angle_deg,
        predicted,
        predicted_state,
        confidence,
        horizon_s
    )

end


# ============================================================
# DEVICE STATE
# ============================================================

mutable struct DeviceState

    fold::FoldState

    battery_percent::Float64
    energy_remaining_Wh::Float64

    temperature_c::Float64

    brightness::Float64
    refresh_rate::Float64

    cpu_load::Float64
    gpu_load::Float64
    network_load::Float64
    ai_load::Float64

    camera_active::Bool
    gaming::Bool
    video_playback::Bool
    charging::Bool
    user_interacting::Bool

    fold_cycles::Int

end


function initial_state(
    p::DeviceParameters;
    battery_percent = 100.0,
    temperature_c = DEFAULT_AMBIENT_C
)

    energy =
        battery_capacity_wh(
            p.battery
        ) *
        battery_percent / 100.0

    DeviceState(
        fold_state(180.0),
        battery_percent,
        energy,
        temperature_c,
        0.70,
        120.0,
        0.20,
        0.15,
        0.20,
        0.0,
        false,
        false,
        false,
        false,
        false,
        0
    )

end


# ============================================================
# DEVICE POLICY
# ============================================================

struct DevicePolicy

    layout_mode::Symbol
    display_panels::Int

    refresh_rate::Float64
    brightness::Float64

    performance_mode::Symbol
    thermal_mode::Symbol

    animation_scale::Float64

    gpu_quality::Float64
    background_activity::Float64

    haptic_intensity::Float64
    transition_speed::Float64

    reason::String
end


function layout_for_fold(state)

    Dict(
        :open => :fullscreen,
        :partial => :split,
        :tabletop => :tabletop,
        :folded => :compact,
        :closed => :cover
    )[state.state]

end


function recommend_policy(
    state::DeviceState,
    p::DeviceParameters
)

    thermal =
        classify_thermal(
            state.temperature_c
        )

    workload =
        state.gaming ? :gaming :
        state.camera_active ? :camera :
        state.video_playback ? :video :
        :normal

    performance =
        performance_policy(
            state.battery_percent,
            thermal,
            workload
        )

    refresh =
        refresh_policy(
            performance
        )

    brightness =
        performance == :critical ?
        min(state.brightness, 0.35) :
        performance == :power_efficient ?
        min(state.brightness, 0.60) :
        state.brightness

    layout =
        layout_for_fold(
            state.fold
        )

    panels =
        layout in (:fullscreen, :split, :tabletop) ?
        2 : 1

    animation =
        animation_policy(
            performance
        )

    gpu_quality =
        performance == :maximum_performance ? 1.0 :
        performance == :balanced ? 0.85 :
        performance == :power_efficient ? 0.65 :
        performance == :thermal_limited ? 0.45 :
        0.25

    background =
        performance == :critical ? 0.10 :
        performance == :power_efficient ? 0.50 :
        1.0

    haptics =
        performance == :critical ? 0.40 : 1.0

    transition =
        state.fold.direction == :closing ||
        state.fold.direction == :opening ?
        1.0 : 0.75

    reason =
        "layout=$(layout), thermal=$(thermal), performance=$(performance)"

    DevicePolicy(
        layout,
        panels,
        refresh,
        brightness,
        performance,
        thermal,
        animation,
        gpu_quality,
        background,
        haptics,
        transition,
        reason
    )

end


# ============================================================
# REAL-TIME STEP
# ============================================================

function step!(
    state::DeviceState,
    p::DeviceParameters,
    dt::Float64;
    ambient_c = DEFAULT_AMBIENT_C
)

    # --------------------------------------------------------
    # POWER
    # --------------------------------------------------------

    power =
        power_estimate(
            state.brightness,
            state.refresh_rate,
            state.cpu_load,
            state.gpu_load,
            state.network_load;
            camera = state.camera_active,
            gaming = state.gaming,
            video = state.video_playback,
            ai_load = state.ai_load,
            charging = state.charging
        )

    # --------------------------------------------------------
    # THERMAL
    # --------------------------------------------------------

    thermal =
        thermal_step(
            state.temperature_c,
            power,
            ambient_c,
            p.thermal,
            dt
        )

    state.temperature_c =
        thermal.temperature_c

    # --------------------------------------------------------
    # BATTERY
    # --------------------------------------------------------

    battery =
        battery_step(
            state.energy_remaining_Wh,
            power,
            p.battery,
            dt
        )

    state.energy_remaining_Wh =
        battery.energy_remaining_Wh

    state.battery_percent =
        battery.battery_percent

    # --------------------------------------------------------
    # PREDICTIVE FOLD STATE
    # --------------------------------------------------------

    policy =
        recommend_policy(
            state,
            p
        )

    # --------------------------------------------------------
    # ADAPT RUNTIME PARAMETERS
    # --------------------------------------------------------

    state.refresh_rate =
        min(
            state.refresh_rate,
            policy.refresh_rate
        )

    state.brightness =
        min(
            state.brightness,
            policy.brightness
        )

    policy

end


# ============================================================
# SIMULATION RESULT
# ============================================================

struct FoldSimulation

    time_s::Vector{Float64}

    angle_deg::Vector{Float64}
    velocity_deg_s::Vector{Float64}

    torque_nm::Vector{Float64}

    temperature_c::Vector{Float64}

    power_w::Vector{Float64}
    battery_percent::Vector{Float64}

    fold_state::Vector{Symbol}
    policy::Vector{Symbol}

end


# ============================================================
# FULL SIMULATION
# ============================================================

function simulate(
    p::DeviceParameters;
    duration_s = 60.0,
    dt = 0.05,
    initial_angle = 180.0,
    initial_velocity = 0.0,
    target_angle = 90.0,
    acceleration = -30.0
)

    state =
        initial_state(p)

    state.fold =
        fold_state(
            initial_angle,
            initial_velocity
        )

    n =
        Int(floor(duration_s / dt)) + 1

    time = zeros(n)
    angles = zeros(n)
    velocities = zeros(n)
    torque = zeros(n)
    temperature = zeros(n)
    power = zeros(n)
    battery = zeros(n)

    states =
        Vector{Symbol}(undef, n)

    policies =
        Vector{Symbol}(undef, n)

    for i in 1:n

        t = (i - 1) * dt

        time[i] = t

        current =
            state.fold.angle_deg

        error =
            target_angle -
            current

        commanded_acceleration =
            abs(error) < 2.0 ?
            0.0 :
            sign(error) *
            abs(acceleration)

        new_fold =
            fold_kinematics(
                current,
                state.fold.angular_velocity_deg_s,
                commanded_acceleration,
                dt
            )

        # Prevent overshoot of target.
        if (
            (target_angle < initial_angle &&
             new_fold.angle_deg <= target_angle) ||
            (target_angle > initial_angle &&
             new_fold.angle_deg >= target_angle)
        )

            new_fold =
                fold_state(
                    target_angle,
                    0.0,
                    0.0
                )
        end

        state.fold =
            new_fold

        policy =
            step!(
                state,
                p,
                dt
            )

        τ =
            hinge_torque(
                state.fold,
                p.hinge
            )

        power_now =
            power_estimate(
                state.brightness,
                state.refresh_rate,
                state.cpu_load,
                state.gpu_load,
                state.network_load;
                camera = state.camera_active,
                gaming = state.gaming,
                video = state.video_playback,
                ai_load = state.ai_load
            )

        angles[i] =
            state.fold.angle_deg

        velocities[i] =
            state.fold.angular_velocity_deg_s

        torque[i] =
            τ

        temperature[i] =
            state.temperature_c

        power[i] =
            power_now

        battery[i] =
            state.battery_percent

        states[i] =
            state.fold.state

        policies[i] =
            policy.performance_mode

    end

    FoldSimulation(
        time,
        angles,
        velocities,
        torque,
        temperature,
        power,
        battery,
        states,
        policies
    )

end


# ============================================================
# FOLD CYCLE
# ============================================================

function simulate_fold_cycle(
    p::DeviceParameters;
    dt = 0.05
)

    open =
        simulate(
            p;
            duration_s = 3.0,
            dt = dt,
            initial_angle = 0.0,
            initial_velocity = 0.0,
            target_angle = 180.0,
            acceleration = 90.0
        )

    close =
        simulate(
            p;
            duration_s = 3.0,
            dt = dt,
            initial_angle = 180.0,
            initial_velocity = 0.0,
            target_angle = 0.0,
            acceleration = -90.0
        )

    (
        opening = open,
        closing = close
    )

end


# ============================================================
# RELIABILITY
# ============================================================

struct ReliabilityState

    fold_cycles::Int

    maximum_strain::Float64
    maximum_temperature_c::Float64
    maximum_torque_nm::Float64

    cumulative_damage::Float64

    hinge_health::Float64
    display_health::Float64
    thermal_health::Float64

end


function reliability_from_cycle(
    simulation::FoldSimulation,
    p::DeviceParameters,
    cycles::Int
)

    maximum_temperature =
        maximum(
            simulation.temperature_c
        )

    maximum_torque =
        maximum(
            simulation.torque_nm
        )

    maximum_strain =
        maximum(
            [
                p.display.neutral_axis_mm /
                bend_radius(
                    a,
                    p.geometry.hinge_radius_mm
                )
                for a in simulation.angle_deg
            ]
        )

    strain_ratio =
        safe_div(
            maximum_strain,
            p.display.nominal_strain_limit
        )

    temperature_ratio =
        safe_div(
            maximum_temperature,
            THERMAL_CRITICAL_C
        )

    damage_per_cycle =
        strain_ratio^2 +
        0.25 * temperature_ratio^2

    cumulative_damage =
        cycles *
        damage_per_cycle *
        1e-6

    hinge_health =
        clamp(
            1.0 -
            cumulative_damage,
            0.0,
            1.0
        )

    display_health =
        clamp(
            1.0 -
            cumulative_damage *
            1.25,
            0.0,
            1.0
        )

    thermal_health =
        clamp(
            1.0 -
            max(0.0,
                temperature_ratio - 0.6),
            0.0,
            1.0
        )

    ReliabilityState(
        cycles,
        maximum_strain,
        maximum_temperature,
        maximum_torque,
        cumulative_damage,
        hinge_health,
        display_health,
        thermal_health
    )

end


# ============================================================
# MONTE CARLO
# ============================================================

function monte_carlo(
    p::DeviceParameters;
    samples = 1000,
    seed = 42,
    cycles = 100_000
)

    rng =
        MersenneTwister(seed)

    hinge_health =
        zeros(samples)

    display_health =
        zeros(samples)

    thermal_health =
        zeros(samples)

    for i in 1:samples

        hinge_scale =
            1.0 +
            0.05 *
            randn(rng)

        thermal_scale =
            1.0 +
            0.10 *
            randn(rng)

        strain_scale =
            1.0 +
            0.08 *
            randn(rng)

        hinge =
            HingeParameters(
                inertia =
                    p.hinge.inertia *
                    hinge_scale,
                damping =
                    p.hinge.damping *
                    hinge_scale,
                friction =
                    p.hinge.friction *
                    hinge_scale,
                stiffness =
                    p.hinge.stiffness *
                    hinge_scale,
                detent_strength =
                    p.hinge.detent_strength,
                maximum_torque_nm =
                    p.hinge.maximum_torque_nm
            )

        display =
            DisplayParameters(
                neutral_axis_mm =
                    p.display.neutral_axis_mm *
                    strain_scale,
                nominal_strain_limit =
                    p.display.nominal_strain_limit,
                hinge_exclusion_mm =
                    p.display.hinge_exclusion_mm
            )

        thermal =
            ThermalParameters(
                thermal_resistance_k_w =
                    p.thermal.thermal_resistance_k_w *
                    thermal_scale,
                thermal_capacitance_j_k =
                    p.thermal.thermal_capacitance_j_k
            )

        params =
            DeviceParameters(
                geometry = p.geometry,
                hinge = hinge,
                display = display,
                battery = p.battery,
                thermal = thermal
            )

        simulation =
            simulate_fold_cycle(
                params
            )

        opening =
            simulation.opening

        reliability =
            reliability_from_cycle(
                opening,
                params,
                cycles
            )

        hinge_health[i] =
            reliability.hinge_health

        display_health[i] =
            reliability.display_health

        thermal_health[i] =
            reliability.thermal_health

    end

    (
        hinge_mean = mean(hinge_health),
        hinge_std = std(hinge_health),

        display_mean = mean(display_health),
        display_std = std(display_health),

        thermal_mean = mean(thermal_health),
        thermal_std = std(thermal_health),

        hinge_p05 = quantile(hinge_health, 0.05),
        hinge_p95 = quantile(hinge_health, 0.95),

        display_p05 = quantile(display_health, 0.05),
        display_p95 = quantile(display_health, 0.95),

        thermal_p05 = quantile(thermal_health, 0.05),
        thermal_p95 = quantile(thermal_health, 0.95)
    )

end


# ============================================================
# REPORT
# ============================================================

function device_report(
    state::DeviceState,
    p::DeviceParameters
)

    display =
        display_geometry(
            state.fold,
            p.geometry
        )

    health =
        display_health(
            state.fold,
            p
        )

    torque =
        hinge_torque(
            state.fold,
            p.hinge
        )

    prediction =
        predict_fold(
            state.fold
        )

    policy =
        recommend_policy(
            state,
            p
        )

    power =
        power_estimate(
            state.brightness,
            state.refresh_rate,
            state.cpu_load,
            state.gpu_load,
            state.network_load;
            camera = state.camera_active,
            gaming = state.gaming,
            video = state.video_playback,
            ai_load = state.ai_load
        )

    Dict(
        :timestamp => now(),

        :fold_angle_deg =>
            state.fold.angle_deg,

        :fold_state =>
            state.fold.state,

        :fold_velocity_deg_s =>
            state.fold.angular_velocity_deg_s,

        :fold_direction =>
            state.fold.direction,

        :hinge_torque_nm =>
            torque,

        :display_area_mm2 =>
            display.visible_area_mm2,

        :display_panels =>
            display.active_panels,

        :bend_radius_mm =>
            health.bend_radius_mm,

        :display_strain =>
            health.estimated_strain,

        :display_status =>
            health.status,

        :temperature_c =>
            state.temperature_c,

        :battery_percent =>
            state.battery_percent,

        :energy_remaining_Wh =>
            state.energy_remaining_Wh,

        :power_w =>
            power,

        :predicted_angle_deg =>
            prediction.predicted_angle_deg,

        :predicted_state =>
            prediction.predicted_state,

        :prediction_confidence =>
            prediction.confidence,

        :layout_mode =>
            policy.layout_mode,

        :performance_mode =>
            policy.performance_mode,

        :refresh_rate =>
            policy.refresh_rate,

        :animation_scale =>
            policy.animation_scale
    )

end


# ============================================================
# DEMO
# ============================================================

function demo()

    params =
        DeviceParameters()

    state =
        initial_state(
            params;
            battery_percent = 82.0,
            temperature_c = 25.0
        )

    println()
    println("==========================================")
    println(" FOLD.OS 2.0")
    println(" Julia Engineering Core")
    println("==========================================")

    println()
    println(
        "Battery capacity: ",
        round(
            battery_capacity_wh(
                params.battery
            ),
            digits = 2
        ),
        " Wh"
    )

    for angle in
        [180.0, 150.0, 120.0, 90.0, 60.0, 30.0, 0.0]

        state.fold =
            fold_state(
                angle
            )

        report =
            device_report(
                state,
                params
            )

        println()
        println(
            "ANGLE       : ",
            round(angle, digits = 1),
            "°"
        )

        println(
            "STATE       : ",
            report[:fold_state]
        )

        println(
            "LAYOUT      : ",
            report[:layout_mode]
        )

        println(
            "PANELS      : ",
            report[:display_panels]
        )

        println(
            "BEND RADIUS : ",
            round(
                report[:bend_radius_mm],
                digits = 3
            ),
            " mm"
        )

        println(
            "STRAIN      : ",
            round(
                report[:display_strain] * 100,
                digits = 4
            ),
            "%"
        )

        println(
            "HINGE       : ",
            round(
                report[:hinge_torque_nm],
                digits = 4
            ),
            " Nm"
        )

        println(
            "POWER       : ",
            round(
                report[:power_w],
                digits = 2
            ),
            " W"
        )

        println(
            "TEMPERATURE : ",
            round(
                report[:temperature_c],
                digits = 2
            ),
            " °C"
        )

        println(
            "PREDICTION  : ",
            report[:predicted_state],
            " (",
            round(
                report[:prediction_confidence] * 100,
                digits = 1
            ),
            "%)"
        )

    end

    println()
    println("==========================================")

    state

end


end # module FoldOS
```

---

# 2. JULIA PROJECT FILE

Create:

### `julia/Project.toml`

```toml
name = "FoldOS"
uuid = "9c9d2d42-5b3f-4e0c-b6f7-6f2f2d4a0011"
authors = ["FOLD.OS Engineering"]
version = "2.0.0"

[deps]
LinearAlgebra = "37e2e46d-f7c4-5c2a-8e5d-9f7f0f5d0a2b"
Random = "9a3f8284-686f-5f34-9a76-9d2b4f3e6c11"
Statistics = "10745b16-90b9-5f8f-8f7b-3e3e3e3e3e3e"
Dates = "ade2ca70-3891-5945-98fb-dc099432e06a"

[compat]
julia = "1.10"
```

For the first version, deliberately keep the engineering core dependent only on Julia's standard library. This makes the reference simulator portable and easy to validate before introducing larger numerical dependencies.

---

# 3. TEST SUITE

Create:

### `julia/test/runtests.jl`

```julia
using Test

include("../src/FoldOS.jl")

using .FoldOS


@testset "FOLD.OS 2.0" begin

    params =
        DeviceParameters()

    @testset "Angle" begin

        @test clamp_angle(-10) == 0.0
        @test clamp_angle(90) == 90.0
        @test clamp_angle(200) == 180.0

    end


    @testset "Fold states" begin

        @test classify_fold(180) == :open
        @test classify_fold(140) == :partial
        @test classify_fold(90) == :tabletop
        @test classify_fold(60) == :folded
        @test classify_fold(0) == :closed

    end


    @testset "Battery" begin

        capacity =
            battery_capacity_wh(
                params.battery
            )

        @test capacity > 0
        @test capacity ≈
            params.battery.capacity_mAh *
            params.battery.nominal_voltage_v /
            1000
    end


    @testset "Display geometry" begin

        state =
            fold_state(180)

        geometry =
            display_geometry(
                state,
                params.geometry
            )

        @test geometry.active_panels == 2
        @test geometry.visible_area_mm2 > 0

    end


    @testset "Thermal" begin

        thermal =
            thermal_step(
                25.0,
                5.0,
                22.0,
                params.thermal,
                1.0
            )

        @test thermal.temperature_c > 25.0

    end


    @testset "Prediction" begin

        state =
            fold_state(
                120.0,
                -30.0,
                0.0
            )

        prediction =
            predict_fold(
                state;
                horizon_s = 1.0
            )

        @test prediction.predicted_angle_deg < 120.0

    end


    @testset "Power" begin

        power =
            power_estimate(
                0.7,
                120.0,
                0.5,
                0.5,
                0.3
            )

        @test power > 0
    end


    @testset "Simulation" begin

        result =
            simulate(
                params;
                duration_s = 2.0,
                dt = 0.1,
                initial_angle = 180.0,
                target_angle = 90.0
            )

        @test length(result.time_s) > 1
        @test length(result.angle_deg) ==
              length(result.time_s)

        @test all(
            0.0 .<= result.angle_deg .<= 180.0
        )

    end

end
```

---

# 4. DEMO PROGRAM

Create:

### `julia/examples/basic_simulation.jl`

```julia
include("../src/FoldOS.jl")

using .FoldOS

params =
    DeviceParameters()

state =
    initial_state(
        params;
        battery_percent = 82.0,
        temperature_c = 25.0
    )

println("FOLD.OS 2.0")
println("-----------")

println(
    "Battery: ",
    battery_capacity_wh(params.battery),
    " Wh"
)

println()

for angle in
    [180.0, 150.0, 120.0, 90.0, 60.0, 30.0, 0.0]

    state.fold =
        fold_state(angle)

    report =
        device_report(
            state,
            params
        )

    println(
        "angle=",
        round(angle, digits=1),
        "°",
        " state=",
        report[:fold_state],
        " layout=",
        report[:layout_mode],
        " temp=",
        round(
            report[:temperature_c],
            digits=1
        ),
        "°C"
    )

end
```

Run:

```bash
cd fold-os-2/julia

julia --project=. examples/basic_simulation.jl
```

Then:

```bash
julia --project=. test/runtests.jl
```

---

# 5. WHAT THIS ENGINE NOW DOES

The Julia engine has a complete state pipeline:

```text
                     DEVICE
                       │
                       ▼
                  FOLD STATE
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          HINGE     DISPLAY    PREDICTION
             │         │         │
             ▼         ▼         ▼
          TORQUE     STRAIN    NEXT STATE
             │         │         │
             └─────────┼─────────┘
                       ▼
                 POWER ENGINE
                       │
                       ▼
                THERMAL ENGINE
                       │
                       ▼
              PERFORMANCE GOVERNOR
                       │
                       ▼
                 POLICY ENGINE
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
           LAYOUT   ANIMATION  HAPTICS
```

This is the core computational architecture that the Swift side consumes.

---

# 6. IMPORTANT NEXT ENGINEERING STEP

The current code intentionally has **reference models rather than pretending to be calibrated hardware physics**.

The next version should replace the simplified components individually:

```text
V2.1
│
├── Differential-equation hinge dynamics
├── proper rigid-body kinematics
├── thermal RC network
├── battery electrochemical approximation
├── sensor noise model
├── Kalman state estimator
├── hysteretic policy controller
├── fold-cycle fatigue model
├── manufacturing tolerance model
└── benchmark suite
```

The architecture should remain unchanged.

Only the models underneath it become more sophisticated.

---

# 7. JULIA → SWIFT CONTRACT

The Julia core should eventually expose one canonical state object equivalent to:

```text
FoldOSState
│
├── fold
│   ├── angle
│   ├── velocity
│   ├── acceleration
│   └── state
│
├── hinge
│   └── torque
│
├── display
│   ├── panels
│   ├── area
│   ├── bend_radius
│   └── strain
│
├── thermal
│   ├── temperature
│   └── state
│
├── battery
│   ├── percent
│   ├── energy
│   └── runtime
│
├── performance
│   ├── CPU
│   ├── GPU
│   └── refresh
│
├── prediction
│   ├── next_angle
│   ├── next_state
│   └── confidence
│
└── policy
    ├── layout
    ├── animation
    ├── GPU quality
    ├── background activity
    └── haptics
```

Swift/SwiftUI/Metal should **consume this state**, not independently recreate the physics.

---

# 8. FINAL DESIGN RULE

The most important architectural rule is:

```text
                FOLD.OS PHYSICAL STATE
                         │
                         ▼
                 JULIA ENGINE
                         │
                         ▼
                POLICY / DECISION
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            SWIFT      METAL      HAPTICS
              │          │          │
              └──────────┼──────────┘
                         ▼
                       iOS
```

There should never be a separate “fake” fold state inside the renderer.

There should never be a separate “fake” temperature inside the UI.

There should never be a separate “fake” battery model inside SwiftUI.

**Julia owns the device model.**

Swift owns application/runtime orchestration.

Metal owns rendering.

SwiftUI owns presentation.

Apple system frameworks own their respective public system integrations.

That gives FOLD.OS a coherent computational centre rather than a collection of disconnected animations.







module FoldOS

using Dates
using Random
using Statistics
using LinearAlgebra
using JSON3

# ============================================================
# FOLD.OS 2.0
# Adaptive Foldable Device Engineering Core
#
# Julia is authoritative for:
#   physical state
#   simulation state
#   engineering calculations
#   prediction
#   policy inputs
#
# No value here should be interpreted as hardware-certified
# without calibration/measurement.
# ============================================================


# ============================================================
# 0. CONSTANTS
# ============================================================

const DEG2RAD = π / 180.0
const RAD2DEG = 180.0 / π

const NOMINAL_BATTERY_VOLTAGE = 3.85
const STANDARD_AMBIENT_C = 22.0

const DEFAULT_DT = 0.01
const DEFAULT_PREDICTION_HORIZON = 0.50

const MIN_FOLD_ANGLE_DEG = 0.0
const MAX_FOLD_ANGLE_DEG = 180.0

const TABLETOP_ENTER_DEG = 90.0
const TABLETOP_EXIT_DEG = 96.0

const CLOSED_ENTER_DEG = 8.0
const CLOSED_EXIT_DEG = 14.0

const OPEN_ENTER_DEG = 174.0
const OPEN_EXIT_DEG = 166.0


# ============================================================
# 1. ENUMERATION-LIKE SYMBOLS
# ============================================================

const DEVICE_BOOK = :book
const DEVICE_CLAMSHELL = :clamshell
const DEVICE_DUAL_FOLD = :dual_fold
const DEVICE_TRI_FOLD = :tri_fold
const DEVICE_EXPERIMENTAL = :experimental

const STATE_OPEN = :open
const STATE_PARTIAL = :partial
const STATE_TABLETOP = :tabletop
const STATE_FOLDED = :folded
const STATE_CLOSED = :closed

const DIR_OPENING = :opening
const DIR_CLOSING = :closing
const DIR_STATIONARY = :stationary

const LAYOUT_FULLSCREEN = :fullscreen
const LAYOUT_SPLIT = :split
const LAYOUT_DUAL_PANEL = :dual_panel
const LAYOUT_TABLETOP = :tabletop
const LAYOUT_COMPACT = :compact
const LAYOUT_COVER = :cover
const LAYOUT_CONTROL_SURFACE = :control_surface

const POLICY_MAXIMUM = :maximum_performance
const POLICY_BALANCED = :balanced
const POLICY_POWER_EFFICIENT = :power_efficient
const POLICY_THERMAL_LIMITED = :thermal_limited
const POLICY_CRITICAL = :critical

const THERMAL_COOL = :cool
const THERMAL_NORMAL = :normal
const THERMAL_WARM = :warm
const THERMAL_HOT = :hot
const THERMAL_CRITICAL = :critical

const SOURCE_THEORETICAL = :theoretical
const SOURCE_USER_DEFINED = :user_defined
const SOURCE_CALIBRATED = :calibrated
const SOURCE_MEASURED = :measured
const SOURCE_UNKNOWN = :unknown

const FIDELITY_VISUAL = 0
const FIDELITY_KINEMATIC = 1
const FIDELITY_ENGINEERING = 2
const FIDELITY_CALIBRATED = 3
const FIDELITY_HARDWARE_VALIDATED = 4


# ============================================================
# 2. PARAMETER METADATA
# ============================================================

struct ParameterMetadata
    name::String
    unit::String
    description::String
    source::Symbol
    confidence::Symbol
end


# ============================================================
# 3. DEVICE GEOMETRY
# ============================================================

struct DeviceGeometry
    panel_width_mm::Float64
    panel_height_mm::Float64
    panel_thickness_mm::Float64
    hinge_width_mm::Float64
    hinge_radius_mm::Float64
    min_bend_radius_mm::Float64
    panel_count::Int
end


function default_book_geometry()
    DeviceGeometry(
        140.0,
        210.0,
        5.0,
        4.0,
        2.5,
        1.5,
        2
    )
end


# ============================================================
# 4. HINGE PARAMETERS
# ============================================================

struct HingeParameters
    inertia::Float64
    damping::Float64
    friction::Float64
    stiffness::Float64
    detent_strength::Float64
    max_torque::Float64
end


function default_hinge()
    HingeParameters(
        0.0025,
        0.015,
        0.025,
        0.08,
        0.12,
        0.80
    )
end


# ============================================================
# 5. FOLD STATE
# ============================================================

struct FoldState
    angle_deg::Float64
    angular_velocity_deg_s::Float64
    angular_acceleration_deg_s2::Float64
    state::Symbol
    direction::Symbol
    stable::Bool
end


function initial_fold_state()
    FoldState(
        180.0,
        0.0,
        0.0,
        STATE_OPEN,
        DIR_STATIONARY,
        true
    )
end


# ============================================================
# 6. DISPLAY GEOMETRY
# ============================================================

struct DisplayGeometry
    active_panels::Int
    visible_area_mm2::Float64
    hinge_exclusion_mm::Float64
    usable_width_mm::Float64
    usable_height_mm::Float64
    panel_angle_deg::Vector{Float64}
end


# ============================================================
# 7. DISPLAY HEALTH
# ============================================================

struct DisplayHealth
    estimated_strain::Float64
    strain_limit::Float64
    bend_radius_mm::Float64
    safety_margin::Float64
    status::Symbol
end


# ============================================================
# 8. BATTERY
# ============================================================

struct BatteryState
    capacity_Wh::Float64
    energy_remaining_Wh::Float64
    battery_percent::Float64
    voltage::Float64
    charging::Bool
end


function battery_from_mAh(
    capacity_mAh::Float64;
    voltage::Float64=NOMINAL_BATTERY_VOLTAGE
)

    capacity_Wh = capacity_mAh * voltage / 1000.0

    BatteryState(
        capacity_Wh,
        capacity_Wh,
        100.0,
        voltage,
        false
    )
end


# ============================================================
# 9. POWER
# ============================================================

struct PowerState
    power_w::Float64
    energy_remaining_Wh::Float64
    battery_percent::Float64
    estimated_runtime_h::Float64
end


# ============================================================
# 10. THERMAL
# ============================================================

struct ThermalParameters
    thermal_resistance_K_W::Float64
    thermal_capacitance_J_K::Float64
end


function default_thermal_parameters()
    ThermalParameters(
        5.0,
        180.0
    )
end


mutable struct ThermalState
    temperature_c::Float64
    ambient_c::Float64
    status::Symbol
end


function initial_thermal_state(
    ambient_c::Float64=STANDARD_AMBIENT_C
)

    ThermalState(
        ambient_c,
        ambient_c,
        THERMAL_NORMAL
    )
end


# ============================================================
# 11. PERFORMANCE
# ============================================================

struct PerformanceState
    cpu_budget::Float64
    gpu_budget::Float64
    refresh_rate_hz::Float64
    animation_quality::Float64
    ai_budget::Float64
    policy::Symbol
end


# ============================================================
# 12. PREDICTION
# ============================================================

struct FoldPrediction
    current_angle::Float64
    predicted_angle::Float64
    predicted_state::Symbol
    confidence::Float64
    horizon_s::Float64
end


# ============================================================
# 13. RELIABILITY
# ============================================================

mutable struct ReliabilityState
    fold_cycles::Int
    maximum_strain::Float64
    maximum_temperature::Float64
    average_temperature::Float64
    maximum_torque::Float64
    hinge_health::Float64
    display_health::Float64
    thermal_health::Float64
end


function initial_reliability()
    ReliabilityState(
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        100.0,
        100.0,
        100.0
    )
end


# ============================================================
# 14. CALIBRATION
# ============================================================

struct CalibrationProfile
    angle_offset::Float64
    angle_scale::Float64
    torque_scale::Float64
    thermal_resistance::Float64
    thermal_capacitance::Float64
    battery_capacity_Wh::Float64
end


function nominal_calibration(
    battery_capacity_Wh::Float64
)

    CalibrationProfile(
        0.0,
        1.0,
        1.0,
        5.0,
        180.0,
        battery_capacity_Wh
    )
end


# ============================================================
# 15. EVENT SYSTEM
# ============================================================

abstract type FoldEvent end

struct FoldStarted <: FoldEvent
    timestamp::DateTime
    angle_deg::Float64
end

struct FoldProgress <: FoldEvent
    timestamp::DateTime
    angle_deg::Float64
end

struct FoldDetentReached <: FoldEvent
    timestamp::DateTime
    angle_deg::Float64
end

struct FoldCompleted <: FoldEvent
    timestamp::DateTime
    angle_deg::Float64
    state::Symbol
end

struct ThermalWarning <: FoldEvent
    timestamp::DateTime
    temperature_c::Float64
end

struct BatteryWarning <: FoldEvent
    timestamp::DateTime
    battery_percent::Float64
end

struct LayoutChanged <: FoldEvent
    timestamp::DateTime
    layout::Symbol
end

struct PolicyChanged <: FoldEvent
    timestamp::DateTime
    policy::Symbol
end


# ============================================================
# 16. DEVICE STATE
# ============================================================

mutable struct DeviceState
    fold::FoldState
    display::DisplayGeometry
    display_health::DisplayHealth
    battery::BatteryState
    power::PowerState
    thermal::ThermalState
    performance::PerformanceState
    prediction::FoldPrediction
    reliability::ReliabilityState
    layout::Symbol
    workload::Symbol
    fidelity_level::Int
    timestamp::DateTime
end


# ============================================================
# 17. ANGLE UTILITIES
# ============================================================

function clamp_angle(angle::Real)

    clamp(
        Float64(angle),
        MIN_FOLD_ANGLE_DEG,
        MAX_FOLD_ANGLE_DEG
    )
end


function angle_to_radians(angle_deg::Real)

    Float64(angle_deg) * DEG2RAD
end


# ============================================================
# 18. HYSTERESIS STATE MACHINE
# ============================================================

function fold_state(
    angle_deg::Real;
    previous_state::Symbol=STATE_OPEN
)

    angle = clamp_angle(angle_deg)

    if previous_state == STATE_OPEN

        if angle <= OPEN_EXIT_DEG
            return STATE_PARTIAL
        else
            return STATE_OPEN
        end

    elseif previous_state == STATE_PARTIAL

        if angle >= OPEN_ENTER_DEG
            return STATE_OPEN

        elseif angle <= CLOSED_ENTER_DEG
            return STATE_CLOSED

        elseif angle <= TABLETOP_ENTER_DEG
            return STATE_TABLETOP

        else
            return STATE_PARTIAL
        end

    elseif previous_state == STATE_TABLETOP

        if angle >= TABLETOP_EXIT_DEG
            return STATE_PARTIAL

        elseif angle <= CLOSED_ENTER_DEG
            return STATE_CLOSED

        else
            return STATE_TABLETOP
        end

    elseif previous_state == STATE_CLOSED

        if angle >= CLOSED_EXIT_DEG
            return STATE_FOLDED

        else
            return STATE_CLOSED
        end

    elseif previous_state == STATE_FOLDED

        if angle >= TABLETOP_EXIT_DEG
            return STATE_PARTIAL

        elseif angle <= CLOSED_ENTER_DEG
            return STATE_CLOSED

        else
            return STATE_FOLDED
        end

    end

    return STATE_PARTIAL
end


# ============================================================
# 19. DIRECTION
# ============================================================

function fold_direction(
    velocity_deg_s::Real;
    threshold::Float64=0.05
)

    velocity = Float64(velocity_deg_s)

    if velocity > threshold
        return DIR_OPENING

    elseif velocity < -threshold
        return DIR_CLOSING

    else
        return DIR_STATIONARY
    end
end


# ============================================================
# 20. KINEMATICS
# ============================================================

function kinematic_step(
    state::FoldState,
    acceleration_deg_s2::Float64,
    dt::Float64
)

    new_velocity =
        state.angular_velocity_deg_s +
        acceleration_deg_s2 * dt

    new_angle =
        state.angle_deg +
        new_velocity * dt

    new_angle = clamp_angle(new_angle)

    if new_angle == 0.0 || new_angle == 180.0
        new_velocity = 0.0
    end

    new_direction =
        fold_direction(new_velocity)

    new_state =
        fold_state(
            new_angle,
            previous_state=state.state
        )

    FoldState(
        new_angle,
        new_velocity,
        acceleration_deg_s2,
        new_state,
        new_direction,
        abs(new_velocity) < 0.05
    )
end


# ============================================================
# 21. HINGE TORQUE MODEL
# ============================================================

function detent_torque(
    angle_deg::Float64,
    parameters::HingeParameters
)

    detents = (
        0.0,
        45.0,
        90.0,
        120.0,
        180.0
    )

    nearest =
        minimum(abs(angle_deg - d) for d in detents)

    if nearest < 5.0

        return parameters.detent_strength *
               sin(nearest * DEG2RAD)

    end

    return 0.0
end


function hinge_torque(
    fold::FoldState,
    parameters::HingeParameters
)

    velocity_rad_s =
        fold.angular_velocity_deg_s * DEG2RAD

    acceleration_rad_s2 =
        fold.angular_acceleration_deg_s2 * DEG2RAD

    inertial =
        parameters.inertia *
        acceleration_rad_s2

    damping =
        parameters.damping *
        velocity_rad_s

    friction =
        parameters.friction *
        sign(velocity_rad_s)

    detent =
        detent_torque(
            fold.angle_deg,
            parameters
        )

    raw =
        inertial +
        damping +
        friction +
        detent

    clamp(
        raw,
        -parameters.max_torque,
        parameters.max_torque
    )
end


# ============================================================
# 22. HINGE ENERGY
# ============================================================

function hinge_energy(
    torque_nm::Float64,
    angular_velocity_deg_s::Float64,
    dt::Float64
)

    angular_velocity_rad_s =
        angular_velocity_deg_s * DEG2RAD

    power_w =
        abs(torque_nm * angular_velocity_rad_s)

    power_w * dt
end


# ============================================================
# 23. DISPLAY GEOMETRY
# ============================================================

function calculate_display_geometry(
    geometry::DeviceGeometry,
    angle_deg::Float64
)

    angle = clamp_angle(angle_deg)

    θ = angle * DEG2RAD

    width = geometry.panel_width_mm
    height = geometry.panel_height_mm

    # Projection of two panels into a planar effective width.
    projected_width =
        width +
        width * cos(θ)

    visible_area =
        geometry.panel_width_mm *
        geometry.panel_height_mm *
        geometry.panel_count

    # When nearly closed, the internal display is treated
    # as physically inaccessible.
    active_panels =
        angle < CLOSED_EXIT_DEG ?
        1 :
        geometry.panel_count

    usable_width =
        active_panels == 1 ?
        width :
        max(
            width,
            projected_width
        )

    usable_height = height

    hinge_exclusion =
        geometry.hinge_width_mm

    panel_angles =
        if geometry.panel_count == 2
            [angle / 2.0, -angle / 2.0]
        else
            fill(
                angle / geometry.panel_count,
                geometry.panel_count
            )
        end

    DisplayGeometry(
        active_panels,
        visible_area,
        hinge_exclusion,
        usable_width,
        usable_height,
        panel_angles
    )
end


# ============================================================
# 24. DISPLAY STRAIN
# ============================================================

function display_strain(
    geometry::DeviceGeometry,
    angle_deg::Float64
)

    # Simplified conceptual bending model.
    #
    # This is not a manufacturer material model.
    # A calibrated device requires measured neutral-axis
    # location and actual material properties.

    bend_radius =
        max(
            geometry.min_bend_radius_mm,
            geometry.hinge_radius_mm +
            geometry.panel_thickness_mm / 2
        )

    neutral_axis_distance =
        geometry.panel_thickness_mm / 2

    strain =
        neutral_axis_distance /
        bend_radius

    # Folding angle influences effective deformation.
    fold_factor =
        (180.0 - clamp_angle(angle_deg)) / 180.0

    strain * fold_factor
end


function calculate_display_health(
    geometry::DeviceGeometry,
    angle_deg::Float64;
    strain_limit::Float64=0.02
)

    radius =
        max(
            geometry.min_bend_radius_mm,
            geometry.hinge_radius_mm +
            geometry.panel_thickness_mm / 2
        )

    strain =
        display_strain(
            geometry,
            angle_deg
        )

    margin =
        1.0 -
        strain / strain_limit

    status =
        if margin > 0.50
            :safe
        elseif margin > 0.20
            :caution
        elseif margin > 0.0
            :warning
        else
            :critical
        end

    DisplayHealth(
        strain,
        strain_limit,
        radius,
        margin,
        status
    )
end


# ============================================================
# 25. THERMAL MODEL
# ============================================================

function thermal_status(
    temperature_c::Float64
)

    if temperature_c < 28.0
        THERMAL_COOL

    elseif temperature_c < 38.0
        THERMAL_NORMAL

    elseif temperature_c < 45.0
        THERMAL_WARM

    elseif temperature_c < 52.0
        THERMAL_HOT

    else
        THERMAL_CRITICAL
    end
end


function thermal_step!(
    state::ThermalState,
    power_w::Float64,
    parameters::ThermalParameters,
    dt::Float64
)

    R = parameters.thermal_resistance_K_W
    C = parameters.thermal_capacitance_J_K

    heat_loss =
        (state.temperature_c - state.ambient_c) / R

    dTdt =
        (power_w - heat_loss) / C

    state.temperature_c += dTdt * dt

    state.status =
        thermal_status(
            state.temperature_c
        )

    state
end


# ============================================================
# 26. BATTERY ENGINE
# ============================================================

function battery_step!(
    battery::BatteryState,
    power_w::Float64,
    dt::Float64
)

    if battery.charging
        return battery
    end

    energy_used_Wh =
        power_w * dt / 3600.0

    battery.energy_remaining_Wh =
        max(
            0.0,
            battery.energy_remaining_Wh -
            energy_used_Wh
        )

    battery.battery_percent =
        100.0 *
        battery.energy_remaining_Wh /
        battery.capacity_Wh

    battery
end


function battery_runtime(
    battery::BatteryState,
    power_w::Float64
)

    if power_w <= 0.0
        return Inf
    end

    battery.energy_remaining_Wh /
    power_w
end


# ============================================================
# 27. PERFORMANCE GOVERNOR
# ============================================================

function performance_policy(
    battery_percent::Float64,
    temperature_c::Float64,
    workload::Symbol
)

    if temperature_c >= 52.0
        return POLICY_CRITICAL

    elseif temperature_c >= 45.0
        return POLICY_THERMAL_LIMITED

    elseif battery_percent <= 10.0
        return POLICY_CRITICAL

    elseif battery_percent <= 25.0
        return POLICY_POWER_EFFICIENT

    elseif workload == :gaming ||
           workload == :rendering

        return POLICY_MAXIMUM

    else
        return POLICY_BALANCED
    end
end


function calculate_performance(
    battery_percent::Float64,
    temperature_c::Float64,
    workload::Symbol
)

    policy =
        performance_policy(
            battery_percent,
            temperature_c,
            workload
        )

    if policy == POLICY_MAXIMUM

        PerformanceState(
            1.0,
            1.0,
            120.0,
            1.0,
            1.0,
            policy
        )

    elseif policy == POLICY_BALANCED

        PerformanceState(
            0.80,
            0.80,
            90.0,
            0.85,
            0.75,
            policy
        )

    elseif policy == POLICY_POWER_EFFICIENT

        PerformanceState(
            0.55,
            0.50,
            60.0,
            0.60,
            0.40,
            policy
        )

    elseif policy == POLICY_THERMAL_LIMITED

        PerformanceState(
            0.35,
            0.30,
            45.0,
            0.40,
            0.25,
            policy
        )

    else

        PerformanceState(
            0.15,
            0.10,
            30.0,
            0.20,
            0.10,
            policy
        )
    end
end


# ============================================================
# 28. FOLD PREDICTION
# ============================================================

function predict_angle(
    angle_deg::Float64,
    velocity_deg_s::Float64,
    acceleration_deg_s2::Float64,
    horizon_s::Float64
)

    predicted =
        angle_deg +
        velocity_deg_s * horizon_s +
        0.5 *
        acceleration_deg_s2 *
        horizon_s^2

    clamp_angle(predicted)
end


function prediction_confidence(
    velocity_deg_s::Float64,
    acceleration_deg_s2::Float64
)

    motion_strength =
        abs(velocity_deg_s) +
        0.1 * abs(acceleration_deg_s2)

    confidence =
        1.0 -
        exp(-motion_strength / 5.0)

    clamp(
        confidence,
        0.0,
        1.0
    )
end


function predict_fold(
    fold::FoldState;
    horizon_s::Float64=DEFAULT_PREDICTION_HORIZON
)

    predicted_angle =
        predict_angle(
            fold.angle_deg,
            fold.angular_velocity_deg_s,
            fold.angular_acceleration_deg_s2,
            horizon_s
        )

    predicted_state =
        fold_state(
            predicted_angle,
            previous_state=fold.state
        )

    confidence =
        prediction_confidence(
            fold.angular_velocity_deg_s,
            fold.angular_acceleration_deg_s2
        )

    FoldPrediction(
        fold.angle_deg,
        predicted_angle,
        predicted_state,
        confidence,
        horizon_s
    )
end


# ============================================================
# 29. LAYOUT ENGINE
# ============================================================

function layout_for_fold(
    fold_state::Symbol,
    angle_deg::Float64,
    application::Symbol
)

    if fold_state == STATE_CLOSED
        return LAYOUT_COVER

    elseif fold_state == STATE_TABLETOP

        if application == :camera ||
           application == :video ||
           application == :gaming

            return LAYOUT_TABLETOP

        else
            return LAYOUT_SPLIT
        end

    elseif angle_deg >= 165.0
        return LAYOUT_FULLSCREEN

    elseif angle_deg <= 45.0
        return LAYOUT_COMPACT

    else
        return LAYOUT_DUAL_PANEL
    end
end


# ============================================================
# 30. POLICY ENGINE
# ============================================================

struct FoldPolicy
    layout::Symbol
    performance::Symbol
    rendering_quality::Float64
    animation_quality::Float64
    haptic_enabled::Bool
    ai_enabled::Bool
    active_panels::Int
end


function calculate_policy(
    fold::FoldState,
    prediction::FoldPrediction,
    display::DisplayGeometry,
    battery::BatteryState,
    thermal::ThermalState,
    performance::PerformanceState,
    application::Symbol
)

    layout =
        layout_for_fold(
            fold.state,
            fold.angle_deg,
            application
        )

    # Prepare for predicted state when confidence
    # is sufficiently high.
    if prediction.confidence > 0.65

        predicted_layout =
            layout_for_fold(
                prediction.predicted_state,
                prediction.predicted_angle,
                application
            )

        if predicted_layout != layout
            layout = predicted_layout
        end
    end

    rendering_quality =
        min(
            performance.gpu_budget,
            display.active_panels == 2 ? 1.0 : 0.8
        )

    animation_quality =
        performance.animation_quality

    FoldPolicy(
        layout,
        performance.policy,
        rendering_quality,
        animation_quality,
        true,
        performance.ai_budget > 0.2,
        display.active_panels
    )
end


# ============================================================
# 31. RELIABILITY
# ============================================================

function update_reliability!(
    reliability::ReliabilityState,
    fold::FoldState,
    display_health::DisplayHealth,
    thermal::ThermalState,
    torque_nm::Float64
)

    reliability.maximum_strain =
        max(
            reliability.maximum_strain,
            display_health.estimated_strain
        )

    reliability.maximum_temperature =
        max(
            reliability.maximum_temperature,
            thermal.temperature_c
        )

    reliability.maximum_torque =
        max(
            reliability.maximum_torque,
            abs(torque_nm)
        )

    # Conservative conceptual degradation model.
    # Must be replaced by calibrated fatigue data for hardware.

    strain_penalty =
        display_health.estimated_strain *
        0.05

    temperature_penalty =
        max(
            0.0,
            thermal.temperature_c - 35.0
        ) * 0.005

    reliability.display_health =
        clamp(
            reliability.display_health -
            strain_penalty,
            0.0,
            100.0
        )

    reliability.thermal_health =
        clamp(
            reliability.thermal_health -
            temperature_penalty,
            0.0,
            100.0
        )

    reliability.hinge_health =
        clamp(
            100.0 -
            reliability.fold_cycles *
            0.000005,
            0.0,
            100.0
        )

    reliability
end


function complete_fold_cycle!(
    reliability::ReliabilityState
)

    reliability.fold_cycles += 1

    reliability.hinge_health =
        clamp(
            100.0 -
            reliability.fold_cycles *
            0.000005,
            0.0,
            100.0
        )

    reliability
end


# ============================================================
# 32. POWER MODEL
# ============================================================

function calculate_power(
    fold::FoldState,
    workload::Symbol,
    performance::PerformanceState
)

    base_power = 1.5

    display_power =
        fold.state == STATE_CLOSED ?
        0.8 :
        2.0

    workload_power =
        if workload == :idle
            0.5
        elseif workload == :camera
            2.5
        elseif workload == :video
            3.5
        elseif workload == :gaming
            6.5
        elseif workload == :rendering
            8.0
        elseif workload == :navigation
            2.8
        else
            2.0
        end

    cpu_power =
        2.0 * performance.cpu_budget

    gpu_power =
        3.0 * performance.gpu_budget

    base_power +
    display_power +
    workload_power +
    cpu_power +
    gpu_power
end


# ============================================================
# 33. COMPLETE DEVICE STEP
# ============================================================

function update_device!(
    device::DeviceState,
    geometry::DeviceGeometry,
    hinge_parameters::HingeParameters,
    thermal_parameters::ThermalParameters,
    acceleration_deg_s2::Float64,
    dt::Float64;
    application::Symbol=:system
)

    previous_state =
        device.fold.state

    # ----------------------------
    # KINEMATICS
    # ----------------------------

    device.fold =
        kinematic_step(
            device.fold,
            acceleration_deg_s2,
            dt
        )

    # ----------------------------
    # DISPLAY
    # ----------------------------

    device.display =
        calculate_display_geometry(
            geometry,
            device.fold.angle_deg
        )

    device.display_health =
        calculate_display_health(
            geometry,
            device.fold.angle_deg
        )

    # ----------------------------
    # HINGE
    # ----------------------------

    torque =
        hinge_torque(
            device.fold,
            hinge_parameters
        )

    # ----------------------------
    # PERFORMANCE
    # ----------------------------

    device.performance =
        calculate_performance(
            device.battery.battery_percent,
            device.thermal.temperature_c,
            device.workload
        )

    # ----------------------------
    # POWER
    # ----------------------------

    power =
        calculate_power(
            device.fold,
            device.workload,
            device.performance
        )

    device.power =
        PowerState(
            power,
            device.battery.energy_remaining_Wh,
            device.battery.battery_percent,
            battery_runtime(
                device.battery,
                power
            )
        )

    # ----------------------------
    # THERMAL
    # ----------------------------

    thermal_step!(
        device.thermal,
        power,
        thermal_parameters,
        dt
    )

    # ----------------------------
    # BATTERY
    # ----------------------------

    battery_step!(
        device.battery,
        power,
        dt
    )

    device.power =
        PowerState(
            power,
            device.battery.energy_remaining_Wh,
            device.battery.battery_percent,
            battery_runtime(
                device.battery,
                power
            )
        )

    # ----------------------------
    # PREDICTION
    # ----------------------------

    device.prediction =
        predict_fold(
            device.fold
        )

    # ----------------------------
    # POLICY
    # ----------------------------

    policy =
        calculate_policy(
            device.fold,
            device.prediction,
            device.display,
            device.battery,
            device.thermal,
            device.performance,
            application
        )

    device.layout =
        policy.layout

    # ----------------------------
    # RELIABILITY
    # ----------------------------

    update_reliability!(
        device.reliability,
        device.fold,
        device.display_health,
        device.thermal,
        torque
    )

    # ----------------------------
    # CYCLE DETECTION
    # ----------------------------

    if previous_state == STATE_OPEN &&
       device.fold.state == STATE_CLOSED

        complete_fold_cycle!(
            device.reliability
        )
    end

    device.timestamp =
        now()

    device
end


# ============================================================
# 34. DEVICE CONSTRUCTOR
# ============================================================

function create_device(;
    geometry::DeviceGeometry=default_book_geometry(),
    battery_mAh::Float64=4500.0,
    ambient_c::Float64=STANDARD_AMBIENT_C,
    workload::Symbol=:idle,
    fidelity_level::Int=FIDELITY_ENGINEERING
)

    fold =
        initial_fold_state()

    display =
        calculate_display_geometry(
            geometry,
            fold.angle_deg
        )

    display_health =
        calculate_display_health(
            geometry,
            fold.angle_deg
        )

    battery =
        battery_from_mAh(
            battery_mAh
        )

    thermal =
        initial_thermal_state(
            ambient_c
        )

    performance =
        calculate_performance(
            battery.battery_percent,
            thermal.temperature_c,
            workload
        )

    prediction =
        predict_fold(
            fold
        )

    power_w =
        calculate_power(
            fold,
            workload,
            performance
        )

    power =
        PowerState(
            power_w,
            battery.energy_remaining_Wh,
            battery.battery_percent,
            battery_runtime(
                battery,
                power_w
            )
        )

    DeviceState(
        fold,
        display,
        display_health,
        battery,
        power,
        thermal,
        performance,
        prediction,
        initial_reliability(),
        LAYOUT_FULLSCREEN,
        workload,
        fidelity_level,
        now()
    )
end


# ============================================================
# 35. SIMULATION RECORD
# ============================================================

struct TelemetrySample
    timestamp::DateTime
    time_s::Float64
    angle_deg::Float64
    velocity_deg_s::Float64
    acceleration_deg_s2::Float64
    state::Symbol
    torque_nm::Float64
    strain::Float64
    temperature_c::Float64
    power_w::Float64
    battery_percent::Float64
    runtime_h::Float64
    layout::Symbol
    policy::Symbol
    prediction_angle_deg::Float64
    prediction_confidence::Float64
end


# ============================================================
# 36. TELEMETRY
# ============================================================

function telemetry(
    device::DeviceState,
    hinge_parameters::HingeParameters,
    time_s::Float64
)

    torque =
        hinge_torque(
            device.fold,
            hinge_parameters
        )

    TelemetrySample(
        device.timestamp,
        time_s,
        device.fold.angle_deg,
        device.fold.angular_velocity_deg_s,
        device.fold.angular_acceleration_deg_s2,
        device.fold.state,
        torque,
        device.display_health.estimated_strain,
        device.thermal.temperature_c,
        device.power.power_w,
        device.battery.battery_percent,
        device.power.estimated_runtime_h,
        device.layout,
        device.performance.policy,
        device.prediction.predicted_angle,
        device.prediction.confidence
    )
end


# ============================================================
# 37. SCENARIO ENGINE
# ============================================================

struct Scenario
    name::Symbol
    duration_s::Float64
    workload::Symbol
    acceleration_function::Function
end


function normal_day()

    Scenario(
        :normal_day,
        60.0,
        :idle,
        t -> 0.0
    )
end


function rapid_fold_scenario()

    Scenario(
        :rapid_fold,
        5.0,
        :camera,
        t -> begin
            if t < 1.0
                -100.0
            elseif t < 1.5
                0.0
            else
                0.0
            end
        end
    )
end


function gaming_scenario()

    Scenario(
        :gaming,
        300.0,
        :gaming,
        t -> 0.0
    )
end


# ============================================================
# 38. SIMULATION ENGINE
# ============================================================

function simulate!(
    device::DeviceState,
    scenario::Scenario,
    geometry::DeviceGeometry,
    hinge_parameters::HingeParameters,
    thermal_parameters::ThermalParameters;
    dt::Float64=DEFAULT_DT
)

    device.workload =
        scenario.workload

    samples =
        TelemetrySample[]

    steps =
        Int(ceil(
            scenario.duration_s / dt
        ))

    for i in 0:steps

        t =
            i * dt

        acceleration =
            scenario.acceleration_function(t)

        update_device!(
            device,
            geometry,
            hinge_parameters,
            thermal_parameters,
            acceleration,
            dt;
            application=scenario.workload
        )

        push!(
            samples,
            telemetry(
                device,
                hinge_parameters,
                t
            )
        )
    end

    samples
end


# ============================================================
# 39. TARGET ANGLE SIMULATION
# ============================================================

function simulate_fold_to!(
    device::DeviceState,
    target_angle::Float64,
    geometry::DeviceGeometry,
    hinge_parameters::HingeParameters,
    thermal_parameters::ThermalParameters;
    speed_deg_s::Float64=60.0,
    dt::Float64=DEFAULT_DT
)

    target =
        clamp_angle(target_angle)

    samples =
        TelemetrySample[]

    t = 0.0

    while abs(device.fold.angle_deg - target) > 0.1

        direction =
            sign(target - device.fold.angle_deg)

        desired_velocity =
            direction * speed_deg_s

        velocity_error =
            desired_velocity -
            device.fold.angular_velocity_deg_s

        acceleration =
            velocity_error / max(dt, 1e-6)

        acceleration =
            clamp(
                acceleration,
                -500.0,
                500.0
            )

        update_device!(
            device,
            geometry,
            hinge_parameters,
            thermal_parameters,
            acceleration,
            dt
        )

        push!(
            samples,
            telemetry(
                device,
                hinge_parameters,
                t
            )
        )

        t += dt

        if t > 30.0
            break
        end
    end

    samples
end


# ============================================================
# 40. MONTE CARLO
# ============================================================

struct MonteCarloResult
    samples::Int
    mean_max_strain::Float64
    median_max_strain::Float64
    std_max_strain::Float64
    p05_max_strain::Float64
    p95_max_strain::Float64
    failure_probability::Float64
end


function monte_carlo(
    n::Int,
    base_geometry::DeviceGeometry;
    seed::Int=42,
    strain_limit::Float64=0.02
)

    Random.seed!(seed)

    strains =
        Float64[]

    for _ in 1:n

        thickness =
            base_geometry.panel_thickness_mm *
            (1.0 + 0.05 * randn())

        radius =
            base_geometry.min_bend_radius_mm *
            (1.0 + 0.10 * randn())

        radius =
            max(radius, 0.2)

        test_geometry =
            DeviceGeometry(
                base_geometry.panel_width_mm,
                base_geometry.panel_height_mm,
                thickness,
                base_geometry.hinge_width_mm,
                base_geometry.hinge_radius_mm,
                radius,
                base_geometry.panel_count
            )

        strain =
            display_strain(
                test_geometry,
                0.0
            )

        push!(
            strains,
            strain
        )
    end

    MonteCarloResult(
        n,
        mean(strains),
        median(strains),
        std(strains),
        quantile(strains, 0.05),
        quantile(strains, 0.95),
        mean(strains .> strain_limit)
    )
end


# ============================================================
# 41. SENSOR ESTIMATOR
# ============================================================

mutable struct StateEstimator
    filtered_angle_deg::Float64
    filtered_velocity_deg_s::Float64
    confidence::Float64
    alpha::Float64
end


function StateEstimator(
    initial_angle::Float64=180.0;
    alpha::Float64=0.20
)

    StateEstimator(
        initial_angle,
        0.0,
        1.0,
        alpha
    )
end


function update_estimator!(
    estimator::StateEstimator,
    measured_angle_deg::Float64,
    dt::Float64
)

    previous =
        estimator.filtered_angle_deg

    estimator.filtered_angle_deg =
        estimator.alpha *
        measured_angle_deg +
        (1.0 - estimator.alpha) *
        previous

    estimator.filtered_velocity_deg_s =
        (
            estimator.filtered_angle_deg -
            previous
        ) / dt

    error =
        abs(
            measured_angle_deg -
            estimator.filtered_angle_deg
        )

    estimator.confidence =
        exp(-error / 10.0)

    estimator
end


# ============================================================
# 42. USER INTENT ENGINE
# ============================================================

struct IntentPrediction
    mode::Symbol
    action::Symbol
    confidence::Float64
end


function predict_intent(
    device::DeviceState;
    application::Symbol=:system
)

    angle =
        device.fold.angle_deg

    velocity =
        device.fold.angular_velocity_deg_s

    if application == :camera &&
       abs(angle - 90.0) < 15.0

        return IntentPrediction(
            :tabletop_camera,
            :move_controls_to_lower_panel,
            0.87
        )
    end

    if device.fold.state == STATE_CLOSED

        return IntentPrediction(
            :cover_mode,
            :activate_cover_display,
            0.95
        )
    end

    if velocity < -30.0

        return IntentPrediction(
            :closing,
            :prepare_cover_display,
            0.80
        )
    end

    if velocity > 30.0

        return IntentPrediction(
            :opening,
            :prepare_internal_display,
            0.80
        )
    end

    IntentPrediction(
        :unknown,
        :none,
        0.20
    )
end


# ============================================================
# 43. SERIALISATION
# ============================================================

function symbol_string(x)
    String(x)
end


function device_dict(device::DeviceState)

    Dict(
        "timestamp" =>
            string(device.timestamp),

        "fold" => Dict(
            "angle_deg" =>
                device.fold.angle_deg,

            "angular_velocity_deg_s" =>
                device.fold.angular_velocity_deg_s,

            "angular_acceleration_deg_s2" =>
                device.fold.angular_acceleration_deg_s2,

            "state" =>
                symbol_string(device.fold.state),

            "direction" =>
                symbol_string(device.fold.direction),

            "stable" =>
                device.fold.stable
        ),

        "display" => Dict(
            "active_panels" =>
                device.display.active_panels,

            "visible_area_mm2" =>
                device.display.visible_area_mm2,

            "usable_width_mm" =>
                device.display.usable_width_mm,

            "usable_height_mm" =>
                device.display.usable_height_mm,

            "panel_angle_deg" =>
                device.display.panel_angle_deg
        ),

        "display_health" => Dict(
            "estimated_strain" =>
                device.display_health.estimated_strain,

            "strain_limit" =>
                device.display_health.strain_limit,

            "bend_radius_mm" =>
                device.display_health.bend_radius_mm,

            "safety_margin" =>
                device.display_health.safety_margin,

            "status" =>
                symbol_string(
                    device.display_health.status
                )
        ),

        "battery" => Dict(
            "capacity_Wh" =>
                device.battery.capacity_Wh,

            "energy_remaining_Wh" =>
                device.battery.energy_remaining_Wh,

            "battery_percent" =>
                device.battery.battery_percent,

            "voltage" =>
                device.battery.voltage
        ),

        "power" => Dict(
            "power_w" =>
                device.power.power_w,

            "energy_remaining_Wh" =>
                device.power.energy_remaining_Wh,

            "battery_percent" =>
                device.power.battery_percent,

            "estimated_runtime_h" =>
                device.power.estimated_runtime_h
        ),

        "thermal" => Dict(
            "temperature_c" =>
                device.thermal.temperature_c,

            "ambient_c" =>
                device.thermal.ambient_c,

            "status" =>
                symbol_string(
                    device.thermal.status
                )
        ),

        "performance" => Dict(
            "cpu_budget" =>
                device.performance.cpu_budget,

            "gpu_budget" =>
                device.performance.gpu_budget,

            "refresh_rate_hz" =>
                device.performance.refresh_rate_hz,

            "animation_quality" =>
                device.performance.animation_quality,

            "ai_budget" =>
                device.performance.ai_budget,

            "policy" =>
                symbol_string(
                    device.performance.policy
                )
        ),

        "prediction" => Dict(
            "current_angle" =>
                device.prediction.current_angle,

            "predicted_angle" =>
                device.prediction.predicted_angle,

            "predicted_state" =>
                symbol_string(
                    device.prediction.predicted_state
                ),

            "confidence" =>
                device.prediction.confidence,

            "horizon_s" =>
                device.prediction.horizon_s
        ),

        "layout" =>
            symbol_string(device.layout),

        "workload" =>
            symbol_string(device.workload),

        "fidelity_level" =>
            device.fidelity_level,

        "reliability" => Dict(
            "fold_cycles" =>
                device.reliability.fold_cycles,

            "maximum_strain" =>
                device.reliability.maximum_strain,

            "maximum_temperature" =>
                device.reliability.maximum_temperature,

            "maximum_torque" =>
                device.reliability.maximum_torque,

            "hinge_health" =>
                device.reliability.hinge_health,

            "display_health" =>
                device.reliability.display_health,

            "thermal_health" =>
                device.reliability.thermal_health
        )
    )
end


function device_json(
    device::DeviceState
)

    JSON3.write(
        device_dict(device)
    )
end


# ============================================================
# 44. TELEMETRY CSV EXPORT
# ============================================================

function telemetry_header()

    [
        "timestamp",
        "time_s",
        "angle_deg",
        "velocity_deg_s",
        "acceleration_deg_s2",
        "state",
        "torque_nm",
        "strain",
        "temperature_c",
        "power_w",
        "battery_percent",
        "runtime_h",
        "layout",
        "policy",
        "prediction_angle_deg",
        "prediction_confidence"
    ]
end


function telemetry_row(
    sample::TelemetrySample
)

    [
        string(sample.timestamp),
        sample.time_s,
        sample.angle_deg,
        sample.velocity_deg_s,
        sample.acceleration_deg_s2,
        string(sample.state),
        sample.torque_nm,
        sample.strain,
        sample.temperature_c,
        sample.power_w,
        sample.battery_percent,
        sample.runtime_h,
        string(sample.layout),
        string(sample.policy),
        sample.prediction_angle_deg,
        sample.prediction_confidence
    ]
end


function write_telemetry_csv(
    path::String,
    samples::Vector{TelemetrySample}
)

    open(path, "w") do io

        println(
            io,
            join(
                telemetry_header(),
                ","
            )
        )

        for sample in samples

            row =
                telemetry_row(sample)

            println(
                io,
                join(
                    string.(row),
                    ","
                )
            )
        end
    end

    path
end


# ============================================================
# 45. ENGINEERING SUMMARY
# ============================================================

function engineering_summary(
    device::DeviceState
)

    println()
    println("==========================================")
    println(" FOLD.OS 2.0 ENGINEERING CORE")
    println("==========================================")

    println(
        "ANGLE        : ",
        round(device.fold.angle_deg, digits=2),
        "°"
    )

    println(
        "VELOCITY     : ",
        round(
            device.fold.angular_velocity_deg_s,
            digits=2
        ),
        "°/s"
    )

    println(
        "STATE        : ",
        uppercase(
            String(device.fold.state)
        )
    )

    println(
        "TORQUE       : ",
        round(
            hinge_torque(
                device.fold,
                default_hinge()
            ),
            digits=4
        ),
        " Nm"
    )

    println(
        "STRAIN       : ",
        round(
            device.display_health.estimated_strain,
            digits=6
        )
    )

    println(
        "TEMP         : ",
        round(
            device.thermal.temperature_c,
            digits=2
        ),
        " °C"
    )

    println(
        "POWER        : ",
        round(
            device.power.power_w,
            digits=2
        ),
        " W"
    )

    println(
        "BATTERY      : ",
        round(
            device.battery.battery_percent,
            digits=2
        ),
        "%"
    )

    println(
        "LAYOUT       : ",
        uppercase(
            String(device.layout)
        )
    )

    println(
        "PERFORMANCE  : ",
        uppercase(
            String(device.performance.policy)
        )
    )

    println(
        "PREDICTED    : ",
        round(
            device.prediction.predicted_angle,
            digits=2
        ),
        "°"
    )

    println(
        "CONFIDENCE   : ",
        round(
            device.prediction.confidence * 100,
            digits=1
        ),
        "%"
    )

    println(
        "HINGE HEALTH  : ",
        round(
            device.reliability.hinge_health,
            digits=2
        ),
        "%"
    )

    println(
        "DISPLAY HEALTH: ",
        round(
            device.reliability.display_health,
            digits=2
        ),
        "%"
    )

    println(
        "THERMAL       : ",
        uppercase(
            String(device.thermal.status)
        )
    )

    println(
        "FIDELITY      : LEVEL ",
        device.fidelity_level
    )

    println("==========================================")
    println()
end


# ============================================================
# 46. ACCEPTANCE TEST
# ============================================================

function acceptance_test()

    geometry =
        default_book_geometry()

    hinge =
        default_hinge()

    thermal =
        default_thermal_parameters()

    device =
        create_device(
            geometry=geometry,
            battery_mAh=4500.0,
            workload=:camera
        )

    # Start open.
    @assert device.fold.state == STATE_OPEN

    # Move toward tabletop.
    samples =
        simulate_fold_to!(
            device,
            90.0,
            geometry,
            hinge,
            thermal
        )

    @assert abs(
        device.fold.angle_deg - 90.0
    ) < 1.0

    @assert device.fold.state == STATE_TABLETOP ||
           device.fold.state == STATE_PARTIAL

    # Policy should have prepared a tabletop layout.
    device.prediction =
        predict_fold(device.fold)

    policy =
        calculate_policy(
            device.fold,
            device.prediction,
            device.display,
            device.battery,
            device.thermal,
            device.performance,
            :camera
        )

    @assert policy.layout == LAYOUT_TABLETOP ||
           policy.layout == LAYOUT_SPLIT

    # Close.
    samples2 =
        simulate_fold_to!(
            device,
            0.0,
            geometry,
            hinge,
            thermal
        )

    @assert device.fold.angle_deg <= 1.0
    @assert device.fold.state == STATE_CLOSED

    println(
        "FOLD.OS acceptance test: PASS"
    )

    return true
end


# ============================================================
# 47. PUBLIC API
# ============================================================

export DeviceGeometry
export HingeParameters
export FoldState
export DisplayGeometry
export DisplayHealth
export BatteryState
export PowerState
export ThermalParameters
export ThermalState
export PerformanceState
export FoldPrediction
export ReliabilityState
export CalibrationProfile
export DeviceState
export TelemetrySample
export StateEstimator
export IntentPrediction
export Scenario

export default_book_geometry
export default_hinge
export default_thermal_parameters

export create_device
export clamp_angle
export fold_state
export kinematic_step
export hinge_torque
export hinge_energy
export calculate_display_geometry
export calculate_display_health
export display_strain
export thermal_step!
export battery_step!
export calculate_performance
export predict_fold
export predict_intent
export layout_for_fold
export calculate_policy
export update_device!
export simulate!
export simulate_fold_to!
export monte_carlo
export device_json
export write_telemetry_csv
export engineering_summary
export acceptance_test

end # module FoldOS





julia/examples/basic_simulation.jl
include("../src/FoldOS.jl")

using .FoldOS

geometry = default_book_geometry()
hinge = default_hinge()
thermal = default_thermal_parameters()

device = create_device(
    geometry=geometry,
    battery_mAh=4500.0,
    workload=:camera
)

engineering_summary(device)

println("Opening state:")
println(device_json(device))

println()
println("Simulating fold to tabletop...")

samples = simulate_fold_to!(
    device,
    90.0,
    geometry,
    hinge,
    thermal;
    speed_deg_s=70.0
)

engineering_summary(device)

println("Samples generated: ", length(samples))

write_telemetry_csv(
    "fold_tabletop.csv",
    samples
)

println("Telemetry written to fold_tabletop.csv")

println()
println("Intent prediction:")

intent = predict_intent(
    device;
    application=:camera
)

println("Mode       : ", intent.mode)
println("Action     : ", intent.action)
println(
    "Confidence : ",
    round(intent.confidence * 100, digits=1),
    "%"
)
julia/examples/fold_cycle.jl

This one exercises the physical state machine repeatedly.

include("../src/FoldOS.jl")

using .FoldOS

geometry = default_book_geometry()
hinge = default_hinge()
thermal = default_thermal_parameters()

device = create_device(
    geometry=geometry,
    battery_mAh=4500.0,
    workload=:idle
)

for cycle in 1:100

    simulate_fold_to!(
        device,
        0.0,
        geometry,
        hinge,
        thermal
    )

    simulate_fold_to!(
        device,
        180.0,
        geometry,
        hinge,
        thermal
    )

    device.reliability.fold_cycles += 1

    if cycle % 10 == 0

        println(
            "Cycle ",
            cycle,
            " | Hinge health = ",
            round(
                device.reliability.hinge_health,
                digits=3
            ),
            "% | Display health = ",
            round(
                device.reliability.display_health,
                digits=3
            ),
            "%"
        )

    end
end

engineering_summary(device)
julia/examples/thermal_simulation.jl

This demonstrates why the thermal model is dynamic rather than simply temperature = ambient + power × constant.

include("../src/FoldOS.jl")

using .FoldOS

geometry = default_book_geometry()
hinge = default_hinge()
thermal_parameters = default_thermal_parameters()

device = create_device(
    geometry=geometry,
    battery_mAh=4500.0,
    workload=:gaming
)

samples = simulate!(
    device,
    gaming_scenario(),
    geometry,
    hinge,
    thermal_parameters;
    dt=0.1
)

println()
println("THERMAL SIMULATION")
println("==================")

for i in 1:100:length(samples)

    sample = samples[i]

    println(
        "t=",
        round(sample.time_s, digits=1),
        "s ",
        "T=",
        round(sample.temperature_c, digits=2),
        "°C ",
        "P=",
        round(sample.power_w, digits=2),
        "W ",
        "Battery=",
        round(sample.battery_percent, digits=2),
        "%"
    )
end

engineering_summary(device)
julia/examples/monte_carlo.jl
include("../src/FoldOS.jl")

using .FoldOS

geometry =
    default_book_geometry()

result =
    monte_carlo(
        100_000,
        geometry;
        seed=2026
    )

println()
println("FOLD.OS MONTE CARLO")
println("===================")

println(
    "Samples           : ",
    result.samples
)

println(
    "Mean strain       : ",
    result.mean_max_strain
)

println(
    "Median strain     : ",
    result.median_max_strain
)

println(
    "Std deviation     : ",
    result.std_max_strain
)

println(
    "5th percentile    : ",
    result.p05_max_strain
)

println(
    "95th percentile   : ",
    result.p95_max_strain
)

println(
    "Failure probability: ",
    result.failure_probability
)
The important part

This gives you the actual computational spine of FOLD.OS rather than merely a collection of UI concepts:

                   FOLD.OS JULIA CORE

                       DEVICE
                          │
                          ▼
                    FoldState
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          HINGE        DISPLAY      SENSOR
             │            │            │
             ▼            ▼            ▼
          TORQUE        STRAIN     ESTIMATOR
             │            │            │
             └────────────┼────────────┘
                          ▼
                     PHYSICAL STATE
                          │
            ┌─────────────┼──────────────┐
            ▼             ▼              ▼
         THERMAL        POWER       PREDICTION
            │             │              │
            └─────────────┼──────────────┘
                          ▼
                   PERFORMANCE
                          │
                          ▼
                      POLICY
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
        LAYOUT         RENDERING         HAPTICS
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                    SWIFT / iOS
One particularly important design choice

The Julia core does not have separate notions of:

UI angle
Metal angle
Swift angle
physics angle

There is one:

device.fold.angle_deg

Everything derives from it.

So, for example, when the device is at 91.4°:

device.fold.angle_deg



