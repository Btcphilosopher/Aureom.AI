AppleHomeIntelligence/
├── Swift/
│   ├── HomeState.swift
│   ├── HomePolicy.swift
│   ├── JuliaClient.swift
│   ├── HomeController.swift
│   └── HomeDashboard.swift
│
└── Julia/
    ├── Project.toml
    ├── HomeEnergyModel.jl
    ├── Optimizer.jl
    └── Server.jl
    
    
    
    1. Julia project
# Julia/Project.toml

name = "AppleHomeIntelligence"
uuid = "b6a1e9d2-8c2f-4b41-9a7c-123456789abc"
authors = ["Apple Home Intelligence"]
version = "0.1.0"

[deps]
HTTP = "cd3eb016-35fb-5094-929b-558a96fad6f3"
JSON3 = "0f8b85d8-6d8b-5c6f-9e2a-5a9e6c7e4f3b"
JuMP = "4076af6c-e467-56ae-b986-b466b2749572"
HiGHS = "87dc4568-4c63-4d18-9f7d-8e7a5e3e4b1c"

Install the actual packages with:
using Pkg
Pkg.activate(".")
Pkg.instantiate()

2. Julia thermal model
# Julia/HomeEnergyModel.jl

module HomeEnergyModel

export ThermalParameters, next_temperature

struct ThermalParameters
    heat_loss::Float64
    heating_gain::Float64
end

"""
Calculate the next indoor temperature.

This is deliberately a simple model for the prototype.
The parameters should eventually be learned from real
temperature/heating measurements.
"""
function next_temperature(
    current_temperature::Float64,
    outside_temperature::Float64,
    heating_power_kw::Float64,
    parameters::ThermalParameters
)
    return current_temperature +
           parameters.heat_loss *
           (outside_temperature - current_temperature) +
           parameters.heating_gain *
           heating_power_kw
end

end

3. Julia optimisation engine
# Julia/Optimizer.jl

module HomeOptimizer

using JuMP
using HiGHS

export HeatingInput, HeatingResult, optimize_heating

struct HeatingInput
    initial_temperature::Float64
    outside_temperature::Vector{Float64}
    electricity_price::Vector{Float64}
    target_temperature::Vector{Float64}
    occupied::Vector{Bool}
end

struct HeatingResult
    heating_kw::Vector{Float64}
    predicted_temperature::Vector{Float64}
    energy_cost::Float64
end

function optimize_heating(input::HeatingInput)

    n = length(input.outside_temperature)

    @assert length(input.electricity_price) == n
    @assert length(input.target_temperature) == n
    @assert length(input.occupied) == n

    model = Model(HiGHS.Optimizer)

    set_silent(model)

    # Maximum heating-system output.
    max_heating_kw = 5.0

    # Simplified thermal coefficients.
    heat_loss = 0.08
    heating_gain = 0.35

    @variable(model, 0 <= heating[1:n] <= max_heating_kw)

    @variable(
        model,
        5 <= temperature[1:n+1] <= 30
    )

    @variable(model, discomfort[1:n] >= 0)

    # Initial condition.
    @constraint(
        model,
        temperature[1] == input.initial_temperature
    )

    for t in 1:n

        # Building thermal dynamics.
        @constraint(
            model,
            temperature[t + 1] ==
                temperature[t] +
                heat_loss *
                (input.outside_temperature[t] -
                 temperature[t]) +
                heating_gain *
                heating[t]
        )

        # Absolute temperature error.
        @constraint(
            model,
            discomfort[t] >=
                input.target_temperature[t] -
                temperature[t + 1]
        )

        @constraint(
            model,
            discomfort[t] >=
                temperature[t + 1] -
                input.target_temperature[t]
        )
    end

    # Occupied rooms have greater comfort priority.
    comfort_weight = [
        input.occupied[t] ? 10.0 : 2.0
        for t in 1:n
    ]

    # Minimise:
    #
    # electricity cost
    # +
    # temperature discomfort
    #
    @objective(
        model,
        Min,
        sum(
            input.electricity_price[t] *
            heating[t]
            for t in 1:n
        )
        +
        sum(
            comfort_weight[t] *
            discomfort[t]
            for t in 1:n
        )
    )

    optimize!(model)

    if !is_solved_and_feasible(model)
        error("Optimisation failed")
    end

    heating_result = value.(heating)
    temperature_result = value.(temperature)

    energy_cost = sum(
        input.electricity_price[t] *
        heating_result[t]
        for t in 1:n
    )

    return HeatingResult(
        heating_result,
        temperature_result,
        energy_cost
    )
end

end

4. Julia local API
# Julia/Server.jl

using HTTP
using JSON3

include("HomeEnergyModel.jl")
include("Optimizer.jl")

using .HomeOptimizer

const HOST = "127.0.0.1"
const PORT = 8080

function json_response(status, data)

    return HTTP.Response(
        status,
        [
            "Content-Type" => "application/json"
        ],
        JSON3.write(data)
    )
end

function optimize_endpoint(request)

    if request.method != "POST"
        return json_response(
            405,
            (; error = "POST required")
        )
    end

    try

        payload =
            JSON3.read(String(request.body))

        input = HeatingInput(
            Float64(payload.initial_temperature),

            Float64.(
                payload.outside_temperature
            ),

            Float64.(
                payload.electricity_price
            ),

            Float64.(
                payload.target_temperature
            ),

            Bool.(
                payload.occupied
            )
        )

        result =
            optimize_heating(input)

        response = (
            heating_kw =
                result.heating_kw,

            predicted_temperature =
                result.predicted_temperature,

            energy_cost =
                result.energy_cost
        )

        return json_response(
            200,
            response
        )

    catch error

        @error "Optimisation request failed" exception = error

        return json_response(
            400,
            (; error = "Invalid optimisation request")
        )
    end
end

println(
    "Apple Home Intelligence Julia service"
)

println(
    "Listening on http://$HOST:$PORT"
)

HTTP.serve(
    optimize_endpoint,
    HOST,
    PORT
)

Run it with:
cd Julia
julia --project=. Server.jl

You now have a local optimisation server.
5. Swift data model
Create a new SwiftUI application and add:
// HomeState.swift

import Foundation

struct RoomState: Identifiable, Codable, Sendable {

    let id: UUID
    let name: String

    var temperature: Double
    var targetTemperature: Double

    var occupied: Bool
    var heatingEnabled: Bool
}

struct EnergyState: Codable, Sendable {

    var gridPowerKW: Double
    var solarPowerKW: Double
    var batteryPercent: Double?

    var electricityPrice: Double
}

struct HomeState: Codable, Sendable {

    var timestamp: Date

    var rooms: [RoomState]

    var energy: EnergyState
}

struct HeatingRecommendation:
    Codable,
    Sendable
{

    let heatingKW: [Double]

    let predictedTemperature: [Double]

    let energyCost: Double

    enum CodingKeys: String, CodingKey {
        case heatingKW = "heating_kw"
        case predictedTemperature =
            "predicted_temperature"
        case energyCost = "energy_cost"
    }
}

6. Swift Julia client
// JuliaClient.swift

import Foundation

actor JuliaClient {

    private let endpoint =
        URL(string:
            "http://127.0.0.1:8080"
        )!

    func optimize(
        home: HomeState
    ) async throws -> HeatingRecommendation {

        guard let room = home.rooms.first else {
            throw JuliaError.noRooms
        }

        let hours = 24

        let outsideTemperature =
            makeOutsideForecast(hours: hours)

        let prices =
            makePriceForecast(hours: hours)

        let targets =
            Array(
                repeating:
                    room.targetTemperature,
                count: hours
            )

        let occupied =
            Array(
                repeating:
                    room.occupied,
                count: hours
            )

        let requestBody: [String: Any] = [

            "initial_temperature":
                room.temperature,

            "outside_temperature":
                outsideTemperature,

            "electricity_price":
                prices,

            "target_temperature":
                targets,

            "occupied":
                occupied
        ]

        let body =
            try JSONSerialization.data(
                withJSONObject:
                    requestBody
            )

        let url =
            endpoint.appendingPathComponent(
                "optimize"
            )

        var request =
            URLRequest(url: url)

        request.httpMethod = "POST"

        request.setValue(
            "application/json",
            forHTTPHeaderField:
                "Content-Type"
        )

        request.httpBody = body

        let (data, response) =
            try await URLSession.shared.data(
                for: request
            )

        guard
            let httpResponse =
                response as? HTTPURLResponse,
            (200..<300).contains(
                httpResponse.statusCode
            )
        else {
            throw JuliaError.serverError
        }

        return try JSONDecoder().decode(
            HeatingRecommendation.self,
            from: data
        )
    }

    private func makeOutsideForecast(
        hours: Int
    ) -> [Double] {

        (0..<hours).map { hour in

            let radians =
                Double(hour) / 24.0 *
                2.0 * .pi

            return 8.0 +
                4.0 *
                sin(radians)
        }
    }

    private func makePriceForecast(
        hours: Int
    ) -> [Double] {

        (0..<hours).map { hour in

            switch hour {

            case 7...9:
                return 0.28

            case 16...20:
                return 0.30

            default:
                return 0.14
            }
        }
    }
}

enum JuliaError: Error {

    case noRooms
    case serverError
}

7. Swift policy engine
This is important.
Julia does not directly control the house.
Julia makes a recommendation.
Swift decides whether that recommendation is permitted.
// HomePolicy.swift

import Foundation

struct HomePolicy {

    let maximumHeatingKW: Double
    let minimumTemperature: Double
    let maximumTemperature: Double

    func validate(
        recommendation:
            HeatingRecommendation,
        room:
            RoomState
    ) -> Bool {

        guard
            room.heatingEnabled
        else {
            return false
        }

        for power in recommendation.heatingKW {

            guard
                power.isFinite,
                power >= 0,
                power <= maximumHeatingKW
            else {
                return false
            }
        }

        for temperature
            in recommendation.predictedTemperature {

            guard
                temperature.isFinite,
                temperature >= minimumTemperature,
                temperature <= maximumTemperature
            else {
                return false
            }
        }

        return true
    }
}

8. Swift home controller
// HomeController.swift

import Foundation
import Observation

@MainActor
@Observable
final class HomeController {

    var home: HomeState

    var recommendation:
        HeatingRecommendation?

    var isOptimising = false

    var lastError: String?

    private let julia =
        JuliaClient()

    private let policy =
        HomePolicy(
            maximumHeatingKW: 5.0,
            minimumTemperature: 5.0,
            maximumTemperature: 30.0
        )

    init() {

        home = HomeState(

            timestamp: Date(),

            rooms: [

                RoomState(
                    id: UUID(),
                    name: "Living Room",
                    temperature: 18.2,
                    targetTemperature: 20.0,
                    occupied: true,
                    heatingEnabled: true
                ),

                RoomState(
                    id: UUID(),
                    name: "Bedroom",
                    temperature: 17.1,
                    targetTemperature: 18.0,
                    occupied: false,
                    heatingEnabled: true
                ),

                RoomState(
                    id: UUID(),
                    name: "Office",
                    temperature: 18.8,
                    targetTemperature: 20.0,
                    occupied: true,
                    heatingEnabled: true
                )
            ],

            energy: EnergyState(
                gridPowerKW: 1.8,
                solarPowerKW: 0.0,
                batteryPercent: 64.0,
                electricityPrice: 0.14
            )
        )
    }

    func optimiseHome() async {

        guard
            let room = home.rooms.first
        else {
            return
        }

        isOptimising = true
        lastError = nil

        defer {
            isOptimising = false
        }

        do {

            let result =
                try await julia.optimize(
                    home: home
                )

            guard
                policy.validate(
                    recommendation: result,
                    room: room
                )
            else {

                lastError =
                    "Julia recommendation rejected by home policy."

                return
            }

            recommendation = result

        } catch {

            lastError =
                error.localizedDescription
        }
    }
}

9. SwiftUI dashboard
// HomeDashboard.swift

import SwiftUI

struct HomeDashboard:
    View
{

    @State
    private var controller =
        HomeController()

    var body: some View {

        NavigationStack {

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 20
                ) {

                    header

                    energyCard

                    rooms

                    intelligenceCard
                }
                .padding()
            }

            .navigationTitle(
                "Home Intelligence"
            )
        }
    }

    private var header: some View {

        VStack(
            alignment: .leading,
            spacing: 4
        ) {

            Text("Good afternoon")
                .font(.largeTitle)
                .bold()

            Text(
                "Your home is operating normally."
            )
            .foregroundStyle(.secondary)
        }
    }

    private var energyCard: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Label(
                "Energy",
                systemImage:
                    "bolt.fill"
            )
            .font(.headline)

            HStack {

                VStack(
                    alignment: .leading
                ) {

                    Text(
                        "\(controller.home.energy.gridPowerKW, specifier: "%.1f") kW"
                    )
                    .font(.title2)
                    .bold()

                    Text("Grid consumption")
                        .foregroundStyle(
                            .secondary
                        )
                }

                Spacer()

                VStack(
                    alignment: .leading
                ) {

                    Text(
                        "\(controller.home.energy.electricityPrice, specifier: "%.2f") £/kWh"
                    )
                    .font(.title2)
                    .bold()

                    Text("Current price")
                        .foregroundStyle(
                            .secondary
                        )
                }
            }
        }
        .padding()
        .background(
            .thinMaterial,
            in: RoundedRectangle(
                cornerRadius: 20
            )
        )
    }

    private var rooms: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("Rooms")
                .font(.title2)
                .bold()

            ForEach(
                controller.home.rooms
            ) { room in

                HStack {

                    VStack(
                        alignment: .leading
                    ) {

                        Text(room.name)
                            .font(.headline)

                        Text(
                            room.occupied
                            ? "Occupied"
                            : "Unoccupied"
                        )
                        .foregroundStyle(
                            .secondary
                        )
                    }

                    Spacer()

                    Text(
                        "\(room.temperature, specifier: "%.1f")°"
                    )
                    .font(.title3)
                    .bold()

                    Image(
                        systemName:
                            room.heatingEnabled
                            ? "flame.fill"
                            : "flame"
                    )
                }

                Divider()
            }
        }
    }

    private var intelligenceCard: some View {

        VStack(
            alignment: .leading,
            spacing: 15
        ) {

            Label(
                "Home Intelligence",
                systemImage:
                    "brain.head.profile"
            )
            .font(.headline)

            if let result =
                controller.recommendation {

                Text(
                    "Optimised heating schedule calculated."
                )

                Text(
                    "Estimated optimisation cost: £\(result.energyCost, specifier: "%.2f")"
                )
                .foregroundStyle(
                    .secondary
                )

            } else {

                Text(
                    "Julia can calculate a predictive heating schedule for your home."
                )
                .foregroundStyle(
                    .secondary
                )
            }

            Button {

                Task {
                    await controller
                        .optimiseHome()
                }

            } label: {

                if controller.isOptimising {

                    ProgressView()

                } else {

                    Label(
                        "Optimise Home",
                        systemImage:
                            "wand.and.stars"
                    )
                }
            }
            .buttonStyle(.borderedProminent)

            if let error =
                controller.lastError {

                Text(error)
                    .foregroundStyle(.red)
                    .font(.footnote)
            }
        }

        .padding()

        .background(
            .thinMaterial,
            in: RoundedRectangle(
                cornerRadius: 20
            )
        )
    }
}

#Preview {

    HomeDashboard()
}

10. App entry point
// AppleHomeIntelligenceApp.swift

import SwiftUI

@main
struct AppleHomeIntelligenceApp:
    App {

    var body: some Scene {

        WindowGroup {

            HomeDashboard()
        }
    }
}










Project structure
AppleSmartHome/
│
├── SwiftHomeLayer/
│   ├── SmartHomeApp.swift
│   ├── HomeManager.swift
│   ├── AccessoryManager.swift
│   ├── ServiceManager.swift
│   ├── CharacteristicManager.swift
│   ├── HomeModel.swift
│   ├── HomeJSON.swift
│   ├── CommandRouter.swift
│   └── Permissions.swift
│
└── JuliaEngine/
    ├── Project.toml
    ├── src/
    │   ├── SmartHome.jl
    │   ├── Types.jl
    │   ├── State.jl
    │   ├── Optimizer.jl
    │   └── Policy.jl
    └── test/
        └── runtests.jl

Swift side
SmartHomeApp.swift
import SwiftUI

@main
struct SmartHomeApp: App {

    @StateObject private var homeManager = HomeManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(homeManager)
        }
    }
}

HomeManager.swift
This is the central Swift controller.
import Foundation
import HomeKit
import Combine

@MainActor
final class HomeManager: NSObject,
                         ObservableObject,
                         HMHomeManagerDelegate {

    private let homeKitManager = HMHomeManager()

    @Published var homes: [HMHome] = []
    @Published var accessories: [HMAccessory] = []
    @Published var isReady = false

    override init() {
        super.init()

        homeKitManager.delegate = self
    }

    func homeManagerDidUpdateHomes(_ manager: HMHomeManager) {

        homes = manager.homes

        refreshAccessories()

        isReady = true
    }

    private func refreshAccessories() {

        var result: [HMAccessory] = []

        for home in homes {
            result.append(contentsOf: home.accessories)
        }

        accessories = result
    }

    func primaryHome() -> HMHome? {
        homeKitManager.primaryHome
    }

    func allHomes() -> [HMHome] {
        homeKitManager.homes
    }

    func allAccessories() -> [HMAccessory] {

        homes.flatMap {
            $0.accessories
        }
    }

    func accessory(
        identifier: UUID
    ) -> HMAccessory? {

        allAccessories().first {
            $0.uniqueIdentifier == identifier
        }
    }
}

AccessoryManager.swift
This provides the abstraction above raw HomeKit.
import Foundation
import HomeKit

@MainActor
final class AccessoryManager: NSObject {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
        super.init()
    }

    func discoverAccessories() -> [HomeAccessory] {

        var result: [HomeAccessory] = []

        for home in homeManager.allHomes() {

            for accessory in home.accessories {

                let item = HomeAccessory(
                    id: accessory.uniqueIdentifier,
                    name: accessory.name,
                    room: accessory.room?.name,
                    category: accessory.category.categoryType,
                    isReachable: accessory.isReachable,
                    services: accessory.services.map {
                        HomeService(
                            id: $0.uniqueIdentifier,
                            name: $0.name,
                            type: $0.serviceType,
                            characteristics: $0.characteristics.map {
                                HomeCharacteristic(
                                    id: $0.uniqueIdentifier,
                                    name: $0.localizedDescription,
                                    type: $0.characteristicType,
                                    value: $0.value
                                )
                            }
                        )
                    }
                )

                result.append(item)
            }
        }

        return result
    }
}

HomeModel.swift
This is extremely important.
The Julia layer should not know anything about HomeKit's internal object model.
Instead, Swift converts HomeKit into a portable model.
import Foundation

struct HomeCharacteristic: Codable {

    let id: UUID
    let name: String
    let type: String
    let value: AnyCodable?
}

struct HomeService: Codable {

    let id: UUID
    let name: String
    let type: String

    let characteristics:
        [HomeCharacteristic]
}

struct HomeAccessory: Codable {

    let id: UUID
    let name: String
    let room: String?

    let category: String
    let isReachable: Bool

    let services:
        [HomeService]
}

struct HomeSnapshot: Codable {

    let timestamp: Date

    let accessories:
        [HomeAccessory]
}

Because HomeKit values are heterogeneous, we need a JSON-compatible value wrapper.
AnyCodable.swift
import Foundation

enum AnyCodable: Codable {

    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {

        let container =
            try decoder.singleValueContainer()

        if container.decodeNil() {
            self = .null
            return
        }

        if let value =
            try? container.decode(Bool.self) {

            self = .bool(value)
            return
        }

        if let value =
            try? container.decode(Int.self) {

            self = .int(value)
            return
        }

        if let value =
            try? container.decode(Double.self) {

            self = .double(value)
            return
        }

        if let value =
            try? container.decode(String.self) {

            self = .string(value)
            return
        }

        throw DecodingError.dataCorruptedError(
            in: container,
            debugDescription: "Unsupported value"
        )
    }

    func encode(to encoder: Encoder) throws {

        var container =
            encoder.singleValueContainer()

        switch self {

        case .string(let value):
            try container.encode(value)

        case .int(let value):
            try container.encode(value)

        case .double(let value):
            try container.encode(value)

        case .bool(let value):
            try container.encode(value)

        case .null:
            try container.encodeNil()
        }
    }
}

HomeJSON.swift
Swift converts the HomeKit state into a JSON document.
import Foundation

struct HomeJSON {

    static func encode(
        snapshot: HomeSnapshot
    ) throws -> Data {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        encoder.outputFormatting = [
            .prettyPrinted,
            .sortedKeys
        ]

        return try encoder.encode(snapshot)
    }
}

Creating a snapshot
Add this to HomeManager.swift:
extension HomeManager {

    func snapshot() -> HomeSnapshot {

        let manager =
            AccessoryManager(homeManager: self)

        return HomeSnapshot(
            timestamp: Date(),
            accessories:
                manager.discoverAccessories()
        )
    }
}

Now the entire Apple home can be represented by:
let state = homeManager.snapshot()

and:
let json = try HomeJSON.encode(
    snapshot: state
)

Reading HomeKit characteristics
The next layer needs to translate HomeKit values safely.
CharacteristicManager.swift
import Foundation
import HomeKit

@MainActor
final class CharacteristicManager {

    func read(
        _ characteristic: HMCharacteristic
    ) async throws -> AnyCodable {

        let value =
            try await characteristic.readValue()

        return convert(value)
    }

    private func convert(
        _ value: Any?
    ) -> AnyCodable {

        guard let value else {
            return .null
        }

        if let value = value as? Bool {
            return .bool(value)
        }

        if let value = value as? Int {
            return .int(value)
        }

        if let value = value as? Double {
            return .double(value)
        }

        if let value = value as? Float {
            return .double(Double(value))
        }

        if let value = value as? String {
            return .string(value)
        }

        return .null
    }
}

Writing to HomeKit
extension CharacteristicManager {

    func write(
        _ value: Any,
        to characteristic: HMCharacteristic
    ) async throws {

        try await characteristic.writeValue(value)
    }
}

This deliberately keeps writing behind one interface.
That becomes important later because Julia might produce:
{
    "device": "living-room-heating",
    "characteristic": "target-temperature",
    "value": 20.5
}

but only Swift actually executes it.
CommandRouter.swift
This is the bridge back from Julia to Apple Home.
import Foundation
import HomeKit

struct HomeCommand: Codable {

    let accessoryID: UUID
    let serviceID: UUID
    let characteristicID: UUID

    let value: AnyCodable
}

@MainActor
final class CommandRouter {

    private let homeManager: HomeManager
    private let characteristicManager =
        CharacteristicManager()

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func execute(
        _ command: HomeCommand
    ) async throws {

        guard
            let accessory =
                homeManager.accessory(
                    identifier: command.accessoryID
                )
        else {
            throw HomeCommandError
                .accessoryNotFound
        }

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.uniqueIdentifier ==
                        command.serviceID
                    }
                )
        else {
            throw HomeCommandError
                .serviceNotFound
        }

        guard
            let characteristic =
                service.characteristics.first(
                    where: {
                        $0.uniqueIdentifier ==
                        command.characteristicID
                    }
                )
        else {
            throw HomeCommandError
                .characteristicNotFound
        }

        let value =
            homeKitValue(
                command.value
            )

        try await characteristicManager.write(
            value,
            to: characteristic
        )
    }

    private func homeKitValue(
        _ value: AnyCodable
    ) -> Any {

        switch value {

        case .bool(let value):
            return value

        case .int(let value):
            return value

        case .double(let value):
            return value

        case .string(let value):
            return value

        case .null:
            return NSNull()
        }
    }
}

enum HomeCommandError: Error {

    case accessoryNotFound
    case serviceNotFound
    case characteristicNotFound
}

Permissions
Apple's permission boundary should remain entirely Swift-side.
Permissions.swift
import Foundation
import HomeKit

@MainActor
final class HomePermissions {

    private let manager =
        HMHomeManager()

    var homes: [HMHome] {
        manager.homes
    }

    var canReadHome: Bool {
        !manager.homes.isEmpty
    }

    func requestAccess() {
        _ = manager
    }
}

Your application's Info.plist must also contain the appropriate HomeKit usage description:
NSHomeKitUsageDescription

For example:
Northbridge Smart Home needs access to your home to monitor and control compatible accessories.

Julia begins here
The Julia side should receive ordinary data, not HomeKit objects.
That makes it portable and testable.
Project.toml
name = "SmartHome"
uuid = "7b7e4a10-8c7c-4e3c-91a7-000000000001"
authors = ["Northbridge"]
version = "0.1.0"

[deps]
JSON3 = "0f8b85d8-7f2f-4f9f-8e3f-7e0f8c7e0001"
StructTypes = "856f2bd8-1eba-4b8a-8b3c-5e6f7a8b9c0d"

Types.jl
module Types

export Characteristic
export Service
export Accessory
export HomeState
export Command

struct Characteristic
    id::String
    name::String
    type::String
    value::Any
end

struct Service
    id::String
    name::String
    type::String
    characteristics::Vector{Characteristic}
end

struct Accessory
    id::String
    name::String
    room::Union{String,Nothing}
    category::String
    reachable::Bool
    services::Vector{Service}
end

struct HomeState
    timestamp::String
    accessories::Vector{Accessory}
end

struct Command
    accessory_id::String
    service_id::String
    characteristic_id::String
    value::Any
end

end

State.jl
This turns the JSON coming from Swift into the Julia model.
module State

using JSON3

include("Types.jl")

using .Types

export parse_home

function parse_characteristic(c)

    return Characteristic(
        string(c.id),
        string(c.name),
        string(c.type),
        c.value
    )
end


function parse_service(s)

    characteristics =
        Characteristic[
            parse_characteristic(c)
            for c in s.characteristics
        ]

    return Service(
        string(s.id),
        string(s.name),
        string(s.type),
        characteristics
    )
end


function parse_accessory(a)

    services =
        Service[
            parse_service(s)
            for s in a.services
        ]

    room =
        a.room === nothing ?
        nothing :
        string(a.room)

    return Accessory(
        string(a.id),
        string(a.name),
        room,
        string(a.category),
        Bool(a.isReachable),
        services
    )
end


function parse_home(json)

    data = JSON3.read(json)

    accessories =
        Accessory[
            parse_accessory(a)
            for a in data.accessories
        ]

    return HomeState(
        string(data.timestamp),
        accessories
    )
end

end

Basic Julia home-state API
SmartHome.jl
module SmartHome

include("Types.jl")
include("State.jl")

using .Types
using .State

export load_home
export list_rooms
export list_devices
export find_device

function load_home(json::AbstractString)

    return parse_home(json)

end


function list_rooms(
    home::HomeState
)

    rooms = Set{String}()

    for accessory in home.accessories

        if accessory.room !== nothing
            push!(rooms, accessory.room)
        end

    end

    return sort(collect(rooms))
end


function list_devices(
    home::HomeState
)

    return [
        accessory.name
        for accessory in home.accessories
    ]

end


function find_device(
    home::HomeState,
    name::AbstractString
)

    for accessory in home.accessories

        if lowercase(accessory.name) ==
           lowercase(name)

            return accessory
        end
    end

    return nothing
end

end

First optimisation layer
For Layer 1, Julia shouldn't yet attempt heating, energy or security optimisation. Those belong to Layers 2–7.
Instead, Layer 1's Julia responsibility is the whole-home operating model:
HomeKit
   ↓
Normalisation
   ↓
HomeState
   ↓
Validation
   ↓
Device capability map
   ↓
Optimisation-ready representation

So add:
Optimizer.jl
module Optimizer

using ..Types

export reachable_devices
export unavailable_devices
export device_capabilities


function reachable_devices(
    home::HomeState
)

    return [
        a for a in home.accessories
        if a.reachable
    ]

end


function unavailable_devices(
    home::HomeState
)

    return [
        a for a in home.accessories
        if !a.reachable
    ]

end


function device_capabilities(
    accessory::Accessory
)

    capabilities = String[]

    for service in accessory.services

        for characteristic in service.characteristics

            push!(
                capabilities,
                characteristic.type
            )

        end

    end

    return unique(capabilities)

end

end

Policy generation
The first Julia policy engine can now determine what the home is capable of doing without actually making decisions about heating, energy, etc.
Policy.jl
module Policy

using ..Types
using ..Optimizer

export build_home_policy


function build_home_policy(
    home::HomeState
)

    policy = Dict{String,Any}()

    policy["timestamp"] =
        home.timestamp

    policy["device_count"] =
        length(home.accessories)

    policy["reachable_devices"] =
        length(reachable_devices(home))

    policy["unavailable_devices"] =
        length(unavailable_devices(home))

    devices = Dict{String,Any}()

    for accessory in home.accessories

        devices[accessory.id] = Dict(
            "name" => accessory.name,
            "room" => accessory.room,
            "reachable" => accessory.reachable,
            "capabilities" =>
                device_capabilities(accessory)
        )

    end

    policy["devices"] = devices

    return policy

end

end

The complete Julia entry point
Replace SmartHome.jl with:
module SmartHome

include("Types.jl")
include("State.jl")
include("Optimizer.jl")
include("Policy.jl")

using .Types
using .State
using .Optimizer
using .Policy

export load_home
export analyse_home


function load_home(
    json::AbstractString
)

    return parse_home(json)

end


function analyse_home(
    json::AbstractString
)

    home =
        parse_home(json)

    return build_home_policy(home)

end

end

Now Julia can take the complete Swift representation:
home =
    SmartHome.load_home(json)

analysis =
    SmartHome.analyse_home(json)

The communication contract
This is the key part of the entire system.
Swift produces something like:
{
  "accessories": [
    {
      "id": "A1",
      "name": "Living Room Lamp",
      "room": "Living Room",
      "category": "Lightbulb",
      "isReachable": true,
      "services": [
        {
          "id": "S1",
          "name": "Light",
          "type": "public.hap.service.lightbulb",
          "characteristics": [
            {
              "id": "C1",
              "name": "Power State",
              "type": "public.hap.characteristic.on",
              "value": true
            }
          ]
        }
      ]
    }
  ]
}

Julia returns an analysis such as:
{
  "device_count": 1,
  "reachable_devices": 1,
  "unavailable_devices": 0,
  "devices": {
    "A1": {
      "name": "Living Room Lamp",
      "room": "Living Room",
      "reachable": true,
      "capabilities": [
        "public.hap.characteristic.on"
      ]
    }
  }
}

And eventually the optimisation engine returns commands:
{
  "commands": [
    {
      "accessoryID": "A1",
      "serviceID": "S1",
      "characteristicID": "C1",
      "value": false
    }
  ]
}








Architecture
              APPLE HOME / HOMEKIT
                       │
                       ▼
              ┌─────────────────┐
              │ Swift Sensors    │
              │                 │
              │ Temperature     │
              │ Humidity        │
              │ Thermostats     │
              │ Heating valves  │
              │ Occupancy       │
              └────────┬────────┘
                       │
                       ▼
                  HomeState
                       │
                       ▼
              ┌─────────────────┐
              │ Julia Heating   │
              │                 │
              │ Thermal model   │
              │ State estimator  │
              │ Temperature     │
              │ prediction      │
              │ Optimisation    │
              └────────┬────────┘
                       │
                       ▼
                 HeatingPolicy
                       │
                       ▼
              ┌─────────────────┐
              │ Swift Command   │
              │ Router          │
              └────────┬────────┘
                       │
                       ▼
                 HomeKit HVAC

Swift: heating data model
Create:
HeatingModel.swift
import Foundation

struct HeatingZone: Codable {

    let id: UUID
    let name: String
    let room: String

    let currentTemperature: Double?
    let targetTemperature: Double?

    let heatingActive: Bool
    let humidity: Double?

    let occupancyDetected: Bool
}

A complete snapshot becomes:
struct HeatingSnapshot: Codable {

    let timestamp: Date

    let outdoorTemperature: Double?

    let zones: [HeatingZone]
}

Swift: reading heating characteristics
Create:
HeatingManager.swift
import Foundation
import HomeKit

@MainActor
final class HeatingManager {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func discoverHeatingZones()
        -> [HMAccessory] {

        var result: [HMAccessory] = []

        for home in homeManager.allHomes() {

            for accessory in home.accessories {

                for service in accessory.services {

                    if isHeatingService(service) {
                        result.append(accessory)
                        break
                    }
                }
            }
        }

        return result
    }

    private func isHeatingService(
        _ service: HMService
    ) -> Bool {

        return service.serviceType ==
            HMServiceTypeThermostat ||
            service.serviceType ==
            HMServiceTypeHeaterCooler
    }
}

This deliberately discovers both thermostats and heater/cooler devices.
Finding temperature
Add:
extension HeatingManager {

    func temperatureCharacteristic(
        from service: HMService
    ) -> HMCharacteristic? {

        service.characteristics.first {
            $0.characteristicType ==
            HMCharacteristicTypeCurrentTemperature
        }
    }
}

And target temperature:
extension HeatingManager {

    func targetTemperatureCharacteristic(
        from service: HMService
    ) -> HMCharacteristic? {

        service.characteristics.first {
            $0.characteristicType ==
            HMCharacteristicTypeTargetTemperature
        }
    }
}

Reading a zone
extension HeatingManager {

    func readZone(
        accessory: HMAccessory
    ) async throws -> HeatingZone? {

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.serviceType ==
                        HMServiceTypeThermostat
                    }
                )
        else {
            return nil
        }

        let current =
            temperatureCharacteristic(
                from: service
            )

        let target =
            targetTemperatureCharacteristic(
                from: service
            )

        let currentValue =
            current?.value as? Double

        let targetValue =
            target?.value as? Double

        return HeatingZone(
            id: accessory.uniqueIdentifier,
            name: accessory.name,
            room: accessory.room?.name ?? "Unknown",
            currentTemperature: currentValue,
            targetTemperature: targetValue,
            heatingActive: false,
            humidity: nil,
            occupancyDetected: false
        )
    }
}

In production, the heatingActive, humidity and occupancy fields should similarly be populated from their relevant HomeKit services.
Building the complete heating snapshot
extension HeatingManager {

    func snapshot() async
        throws -> HeatingSnapshot {

        var zones: [HeatingZone] = []

        for accessory in discoverHeatingZones() {

            if let zone =
                try await readZone(
                    accessory: accessory
                ) {

                zones.append(zone)
            }
        }

        return HeatingSnapshot(
            timestamp: Date(),
            outdoorTemperature: nil,
            zones: zones
        )
    }
}

Now Swift has reduced Apple Home's complex object model to:
HeatingSnapshot
       │
       ├── Living Room
       │      ├── 19.2°C
       │      ├── target 20°C
       │      └── heating on
       │
       ├── Bedroom
       │      ├── 17.8°C
       │      ├── target 18°C
       │      └── heating off
       │
       └── Kitchen
              ├── 18.9°C
              └── target 19°C

Julia thermal model
Now we move into the interesting part.
A simple room model is:
\[
T_{t+1}=T_t+\alpha(T_{outside}-T_t)+\beta H_t
\]
where:
- \(T_t\) = room temperature
- \(T_{outside}\) = outdoor temperature
- \(\alpha\) = heat-loss coefficient
- \(H_t\) = heating input
- \(\beta\) = heating effectiveness
This is deliberately simple initially. We can later replace it with a learned model.
HeatingTypes.jl
module HeatingTypes

export ThermalZone
export HeatingState
export HeatingAction
export HeatingPolicy

struct ThermalZone

    id::String
    room::String

    temperature::Float64
    target::Float64

    outdoor_temperature::Float64

    heating_power::Float64

    thermal_loss::Float64
    thermal_gain::Float64

end


struct HeatingState

    timestamp::String
    zones::Vector{ThermalZone}

end


struct HeatingAction

    zone_id::String
    target_temperature::Float64

end


struct HeatingPolicy

    actions::Vector{HeatingAction}

end

end

Temperature prediction
ThermalModel.jl
module ThermalModel

using ..HeatingTypes

export predict_temperature
export predict_horizon


function predict_temperature(
    zone::ThermalZone,
    heating::Float64,
    dt::Float64 = 1.0
)

    heat_loss =
        zone.thermal_loss *
        (zone.outdoor_temperature -
         zone.temperature)

    heat_gain =
        zone.thermal_gain *
        heating

    return zone.temperature +
           dt *
           (heat_loss + heat_gain)

end


function predict_horizon(
    zone::ThermalZone,
    heating_schedule::Vector{Float64};
    dt::Float64 = 1.0
)

    temperatures =
        Float64[]

    temperature =
        zone.temperature

    for heating in heating_schedule

        heat_loss =
            zone.thermal_loss *
            (zone.outdoor_temperature -
             temperature)

        heat_gain =
            zone.thermal_gain *
            heating

        temperature +=
            dt *
            (heat_loss + heat_gain)

        push!(
            temperatures,
            temperature
        )
    end

    return temperatures

end

end

Example
Suppose:
zone = ThermalZone(
    "living-room",
    "Living Room",
    18.0,
    20.0,
    5.0,
    1.0,
    0.08,
    0.5
)

We can predict:
predict_temperature(
    zone,
    1.0
)

The engine now has a mathematical representation of the building.
Heating optimisation
The first optimisation objective should be:
minimise

energy consumption
+
comfort penalty
+
temperature oscillation

Rather than simply:
"turn heating on whenever temperature < target"

That distinction is important.
HeatingOptimizer.jl
module HeatingOptimizer

using ..HeatingTypes
using ..ThermalModel

export optimise_zone


function comfort_cost(
    temperature::Float64,
    target::Float64
)

    error =
        temperature - target

    return error^2

end


function optimise_zone(
    zone::ThermalZone,
    horizon::Int = 24
)

    best_cost =
        Inf

    best_schedule =
        zeros(horizon)

    # Candidate heating levels.
    candidates =
        [0.0, 0.25, 0.5, 0.75, 1.0]

    # Greedy receding-horizon optimisation.
    for heating in candidates

        schedule =
            fill(heating, horizon)

        temperatures =
            predict_horizon(
                zone,
                schedule
            )

        energy_cost =
            sum(schedule)

        comfort_cost_total =
            sum(
                comfort_cost(
                    temperatures[i],
                    zone.target
                )
                for i in eachindex(
                    temperatures
                )
            )

        total_cost =
            energy_cost +
            10.0 *
            comfort_cost_total

        if total_cost < best_cost

            best_cost =
                total_cost

            best_schedule =
                schedule
        end
    end

    return best_schedule

end

end

This is intentionally a first-generation optimiser. The later version should use proper model-predictive control rather than the simple candidate search.
Occupancy-aware heating
The next important feature is that the target shouldn't always be fixed.
For example:
function effective_target(
    occupied::Bool,
    preferred::Float64,
    setback::Float64
)

    if occupied
        return preferred
    else
        return setback
    end

end

So:
Occupied:
20.5°C

Temporarily empty:
18.0°C

Overnight:
17.0°C

Julia determines those policies.
Swift simply executes them.
Predictive heating policy
Create:
HeatingPolicy.jl
module HeatingPolicy

using ..HeatingTypes
using ..HeatingOptimizer

export create_policy


function create_policy(
    zones::Vector{ThermalZone}
)

    actions =
        HeatingAction[]

    for zone in zones

        schedule =
            optimise_zone(zone, 24)

        first_action =
            schedule[1]

        target =
            zone.target

        if first_action <= 0.0
            target =
                min(
                    target,
                    zone.temperature
                )
        end

        push!(
            actions,
            HeatingAction(
                zone.id,
                target
            )
        )
    end

    return HeatingPolicy(
        actions
    )

end

end

Julia's output
Eventually Julia produces something conceptually like:
{
  "actions": [
    {
      "zone_id": "living-room",
      "target_temperature": 20.5
    },
    {
      "zone_id": "bedroom",
      "target_temperature": 17.5
    },
    {
      "zone_id": "kitchen",
      "target_temperature": 19.0
    }
  ]
}





3. Energy management
Now we extend the architecture so Julia becomes the home's energy optimisation engine, while Swift remains the Apple/HomeKit execution layer.
The fundamental distinction is:
Swift
- Reads electricity/energy sensors.
- Reads supported solar, battery and appliance states.
- Reads/writes supported HomeKit controls.
- Provides the current physical state of the house.
- Executes Julia's approved commands.
Julia
- Forecasts household electricity demand.
- Forecasts solar generation.
- Models battery state.
- Incorporates electricity prices.
- Calculates flexible-load schedules.
- Coordinates heating, batteries, EV charging and appliances.
- Minimises cost while respecting comfort and device constraints.
Overall architecture
                         APPLE HOME
                             │
                             ▼
                    ┌──────────────────┐
                    │  Swift Energy    │
                    │     Layer        │
                    │                  │
                    │ Power sensors    │
                    │ Solar            │
                    │ Battery          │
                    │ EV               │
                    │ Appliances       │
                    │ Heating          │
                    └────────┬─────────┘
                             │
                         EnergyState
                             │
                             ▼
                    ┌──────────────────┐
                    │  Julia Energy    │
                    │     Engine       │
                    │                  │
                    │ Demand forecast  │
                    │ Solar forecast   │
                    │ Price forecast   │
                    │ Battery model    │
                    │ Load scheduling  │
                    │ Optimisation     │
                    └────────┬─────────┘
                             │
                       EnergyPolicy
                             │
                             ▼
                    ┌──────────────────┐
                    │ Swift Validator  │
                    │ + CommandRouter  │
                    └────────┬─────────┘
                             │
                             ▼
                    Apple Home devices

The important architectural decision is that energy management does not replace #2.
It sits above it:
                WHOLE-HOME ENERGY OPTIMISER
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Heating         Battery          EV
          │              │              │
          ▼              ▼              ▼
       Appliance       Solar          Lighting
       scheduling

1. Swift energy model
Create:
EnergyModel.swift
import Foundation

struct EnergyMeasurement: Codable {

    let timestamp: Date

    /// Instantaneous household power in watts.
    let householdPower: Double?

    /// Grid import/export in watts.
    /// Positive = import.
    /// Negative = export.
    let gridPower: Double?

    /// Solar generation in watts.
    let solarPower: Double?

    /// Battery power in watts.
    /// Positive = discharge.
    /// Negative = charge.
    let batteryPower: Double?

    /// Battery state of charge, 0...1.
    let batteryStateOfCharge: Double?
}

2. Energy devices
We want Julia to understand flexible loads.
struct EnergyDevice: Codable {

    let id: UUID
    let name: String
    let room: String?

    let powerWatts: Double?
    let isOn: Bool

    let flexible: Bool

    let minimumRuntimeMinutes: Int?
    let maximumRuntimeMinutes: Int?

    let earliestStart: Date?
    let latestFinish: Date?
}

This distinction is important:
Fixed load
    refrigerator
    networking
    security system

Flexible load
    washing machine
    dishwasher
    EV
    immersion heater
    heat pump
    battery

Julia should concentrate optimisation on flexible loads.
3. Complete energy state
EnergyState.swift
struct EnergyState: Codable {

    let timestamp: Date

    let measurement:
        EnergyMeasurement

    let devices:
        [EnergyDevice]
}

This becomes the input to Julia.
4. Swift energy manager
EnergyManager.swift
import Foundation
import HomeKit

@MainActor
final class EnergyManager {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func discoverEnergyDevices()
        -> [HMAccessory] {

        var devices: [HMAccessory] = []

        for home in homeManager.allHomes() {

            for accessory in home.accessories {

                if containsEnergyService(
                    accessory
                ) {
                    devices.append(accessory)
                }
            }
        }

        return devices
    }

    private func containsEnergyService(
        _ accessory: HMAccessory
    ) -> Bool {

        for service in accessory.services {

            let type =
                service.serviceType

            if type ==
                HMServiceTypeLightbulb ||
               type ==
                HMServiceTypeSwitch ||
               type ==
                HMServiceTypeOutlet ||
               type ==
                HMServiceTypeThermostat {

                return true
            }
        }

        return false
    }
}

The exact available energy characteristics will depend on the accessory ecosystem. Therefore the abstraction should remain capability-based rather than assuming every HomeKit device exposes a power meter.
5. Energy capability model
Add:
enum EnergyCapability: String, Codable {

    case powerMeasurement
    case energyMeasurement

    case solarGeneration
    case batteryStorage

    case switchableLoad
    case thermostat

    case evCharging
}

And:
struct DeviceEnergyCapability: Codable {

    let deviceID: UUID

    let capabilities:
        [EnergyCapability]
}

This gives Julia a clean capability map.
6. Electricity prices
Julia needs a price curve.
Swift can pass prices into the engine regardless of their eventual source.
struct ElectricityPrice: Codable {

    let timestamp: Date

    /// Price in currency per kWh.
    let pricePerKWh: Double
}

Then:
struct EnergyPriceForecast: Codable {

    let prices:
        [ElectricityPrice]
}

For example:
14:00   £0.21/kWh
15:00   £0.19/kWh
16:00   £0.17/kWh
17:00   £0.24/kWh
18:00   £0.31/kWh
19:00   £0.34/kWh
20:00   £0.28/kWh
21:00   £0.22/kWh

7. Julia begins
Create:
EnergyTypes.jl
module EnergyTypes

export EnergyMeasurement
export EnergyDevice
export EnergyState
export ElectricityPrice
export EnergyForecast
export EnergyAction
export EnergyPolicy


struct EnergyMeasurement

    timestamp::String

    household_power::Float64
    grid_power::Float64

    solar_power::Float64
    battery_power::Float64

    battery_soc::Float64

end


struct EnergyDevice

    id::String
    name::String

    power_watts::Float64

    is_on::Bool
    flexible::Bool

    minimum_runtime::Int
    maximum_runtime::Int

end


struct EnergyState

    timestamp::String

    measurement::EnergyMeasurement

    devices::Vector{EnergyDevice}

end


struct ElectricityPrice

    timestamp::String

    price_per_kwh::Float64

end


struct EnergyForecast

    demand_kw::Vector{Float64}
    solar_kw::Vector{Float64}
    prices::Vector{Float64}

end


struct EnergyAction

    device_id::String
    start_slot::Int
    duration_slots::Int

end


struct EnergyPolicy

    actions::Vector{EnergyAction}

end

end

8. Demand forecasting
The first version should be deliberately understandable.
DemandForecast.jl
module DemandForecast

export moving_average
export forecast_demand


function moving_average(
    values::Vector{Float64},
    window::Int
)

    n = length(values)

    if n < window
        return mean(values)
    end

    return mean(
        values[end-window+1:end]
    )

end


function forecast_demand(
    historical_demand::Vector{Float64},
    horizon::Int;
    window::Int = 24
)

    baseline =
        moving_average(
            historical_demand,
            window
        )

    return fill(
        baseline,
        horizon
    )

end

end

This is only the baseline model.
Eventually this becomes:
historical demand
       +
temperature
       +
occupancy
       +
day of week
       +
time of day
       +
heating state
       +
EV state
       ↓
machine-learning forecast

9. Solar forecasting
SolarForecast.jl
module SolarForecast

export forecast_solar


function forecast_solar(
    historical_solar::Vector{Float64},
    horizon::Int
)

    if isempty(historical_solar)

        return zeros(horizon)

    end

    maximum_solar =
        maximum(historical_solar)

    forecast =
        zeros(horizon)

    for t in 1:horizon

        # Simple bell-shaped daylight model.
        phase =
            (t - 1) /
            max(horizon - 1, 1)

        daylight =
            sin(pi * phase)

        forecast[t] =
            max(
                0.0,
                maximum_solar *
                daylight
            )

    end

    return forecast

end

end

Later we can replace this with a proper solar model using:
latitude
longitude
date
time
cloud forecast
panel orientation
panel efficiency
historical generation

10. Net-energy calculation
Now Julia can calculate whether the house has a surplus or deficit.
EnergyBalance.jl
module EnergyBalance

export net_power
export grid_import
export solar_surplus


function net_power(
    demand_kw::Float64,
    solar_kw::Float64
)

    return demand_kw - solar_kw

end


function grid_import(
    demand_kw::Float64,
    solar_kw::Float64
)

    return max(
        0.0,
        demand_kw - solar_kw
    )

end


function solar_surplus(
    demand_kw::Float64,
    solar_kw::Float64
)

    return max(
        0.0,
        solar_kw - demand_kw
    )

end

end

So:
Demand       Solar       Result

2 kW         1 kW        1 kW import

2 kW         2 kW        0 kW grid

2 kW         4 kW        2 kW surplus

11. Battery model
Now introduce storage.
Battery.jl
module Battery

export battery_charge
export battery_discharge
export next_soc


function battery_charge(
    soc::Float64,
    power_kw::Float64,
    efficiency::Float64,
    capacity_kwh::Float64,
    dt_hours::Float64
)

    energy =
        power_kw *
        dt_hours *
        efficiency

    return min(
        1.0,
        soc +
        energy / capacity_kwh
    )

end


function battery_discharge(
    soc::Float64,
    power_kw::Float64,
    efficiency::Float64,
    capacity_kwh::Float64,
    dt_hours::Float64
)

    energy =
        power_kw *
        dt_hours /
        efficiency

    return max(
        0.0,
        soc -
        energy / capacity_kwh
    )

end


function next_soc(
    soc::Float64,
    power_kw::Float64,
    efficiency::Float64,
    capacity_kwh::Float64,
    dt_hours::Float64
)

    if power_kw < 0

        return battery_charge(
            soc,
            abs(power_kw),
            efficiency,
            capacity_kwh,
            dt_hours
        )

    else

        return battery_discharge(
            soc,
            power_kw,
            efficiency,
            capacity_kwh,
            dt_hours
        )

    end

end

end

12. The central energy optimisation
Now we can create the first actual energy optimiser.
The objective is:
\[
J =
\text{electricity cost}
+
\lambda_1\text{grid import}
+
\lambda_2\text{comfort penalty}
+
\lambda_3\text{battery degradation}
\]
The first implementation can focus on flexible loads.
EnergyOptimizer.jl
module EnergyOptimizer

using ..EnergyTypes

export optimise_load


function optimise_load(
    demand_kw::Vector{Float64},
    solar_kw::Vector{Float64},
    prices::Vector{Float64},
    duration_slots::Int
)

    horizon =
        length(demand_kw)

    best_slot = 1

    best_cost = Inf

    for start in 1:
        horizon - duration_slots + 1

        cost = 0.0

        for t in start:
            start + duration_slots - 1

            net =
                demand_kw[t] -
                solar_kw[t]

            cost +=
                max(0.0, net) *
                prices[t]

        end

        if cost < best_cost

            best_cost = cost
            best_slot = start

        end
    end

    return best_slot

end

end

13. Example
Imagine the dishwasher needs two hours.
Julia receives:
Hour       Demand    Solar    Price

17:00      4.0       0.5      £0.31
18:00      4.5       0.2      £0.34
19:00      3.5       0.1      £0.29
20:00      3.0       0.0      £0.23
21:00      2.5       0.0      £0.18
22:00      2.0       0.0      £0.16

Instead of:
RUN DISHWASHER NOW

the Julia optimiser can determine:
Optimal window:
21:00–23:00

14. Solar-aware scheduling
But price isn't the only variable.
Suppose tomorrow looks like:
09:00   2 kW solar
10:00   3 kW solar
11:00   4 kW solar
12:00   5 kW solar
13:00   5 kW solar

Julia might decide:
EV charging
        ↓
11:00–15:00

rather than:
EV charging
        ↓
03:00–07:00

even if overnight electricity is relatively cheap.
That is the beginning of whole-home energy coordination.
15. Flexible-load model
Add:
FlexibleLoads.jl
module FlexibleLoads

using ..EnergyTypes
using ..EnergyOptimizer

export schedule_device


function schedule_device(
    device::EnergyDevice,
    demand_kw::Vector{Float64},
    solar_kw::Vector{Float64},
    prices::Vector{Float64}
)

    start =
        optimise_load(
            demand_kw,
            solar_kw,
            prices,
            device.minimum_runtime
        )

    return EnergyAction(
        device.id,
        start,
        device.minimum_runtime
    )

end

end

16. Whole-home energy policy
EnergyPolicy.jl
module EnergyPolicy

using ..EnergyTypes
using ..FlexibleLoads

export create_energy_policy


function create_energy_policy(
    state::EnergyState,
    demand_kw::Vector{Float64},
    solar_kw::Vector{Float64},
    prices::Vector{Float64}
)

    actions =
        EnergyAction[]

    for device in state.devices

        if device.flexible

            action =
                schedule_device(
                    device,
                    demand_kw,
                    solar_kw,
                    prices
                )

            push!(
                actions,
                action
            )

        end

    end

    return EnergyPolicy(
        actions
    )

end

end

17. Combining heating and energy
This is where #2 and #3 become substantially more powerful together.
The heating engine from the previous layer might say:
Heat house:
06:00–08:00
18:00–22:00

The energy optimiser now says:
Electricity expensive:
18:00–20:00

So instead of blindly following the heating schedule, the system can ask:
Can the house be pre-heated before 18:00?

For example:
16:00    £0.16/kWh
17:00    £0.18/kWh
18:00    £0.32/kWh
19:00    £0.35/kWh
20:00    £0.31/kWh

Julia can decide:
16:30
Heat building to 20.7°C

18:00
Reduce heating power

18:00–20:00
Allow building thermal inertia to carry load

20:00
Resume normal heating

That is much closer to an actual home energy management system.
18. Energy policy output
Julia should return something like:
{
  "timestamp": "2026-10-08T14:00:00Z",
  "actions": [
    {
      "device_id": "dishwasher-01",
      "start_slot": 8,
      "duration_slots": 2
    },
    {
      "device_id": "ev-01",
      "start_slot": 10,
      "duration_slots": 4
    }
  ],
  "battery": {
    "charge": true,
    "target_soc": 0.90
  },
  "heating": {
    "preheat": true,
    "target_temperature": 20.5
  }
}

Swift receives this as a proposal, not an unrestricted command.
19. Swift command validation
Create:
EnergyCommandValidator.swift
import Foundation

@MainActor
final class EnergyCommandValidator {

    func validate(
        device: EnergyDevice,
        action: EnergyAction
    ) -> Bool {

        guard device.isReachable else {
            return false
        }

        guard device.flexible else {
            return false
        }

        guard action.durationSlots > 0 else {
            return false
        }

        if let maximum =
            device.maximumRuntimeMinutes {

            let requested =
                action.durationSlots * 60

            if requested > maximum {
                return false
            }
        }

        return true
    }
}

The principle remains:
Julia suggests
      ↓
Swift validates
      ↓
HomeKit executes







The key idea is:
Don't program every automation. Learn recurring household states and generate policies for them.

For example, instead of the user explicitly creating:
06:30 → lights on
06:35 → heating on
07:00 → kitchen lights
07:15 → heating off

Julia can learn:
Weekday morning routine
≈ 06:25–07:40

and predict it tomorrow.
1. Event model
Create:
AutomationEvent.swift
import Foundation

enum HomeEventType: String, Codable {

    case accessoryChanged
    case temperatureChanged
    case occupancyChanged

    case doorOpened
    case doorClosed

    case lightChanged
    case heatingChanged

    case applianceStarted
    case applianceFinished

    case userAction
}

struct AutomationEvent: Codable {

    let id: UUID
    let timestamp: Date

    let type: HomeEventType

    let accessoryID: UUID?

    let room: String?

    let value: AnyCodable?

    let source: String
}

Now everything happening in the home becomes an event.
For example:
{
    "type": "doorOpened",
    "room": "Front Door",
    "timestamp": "...",
    "source": "HomeKit"
}

or:
{
    "type": "temperatureChanged",
    "room": "Living Room",
    "value": 19.4
}

2. Event stream
Create:
EventStore.swift
import Foundation

@MainActor
final class EventStore: ObservableObject {

    @Published private(set) var events:
        [AutomationEvent] = []

    private let maximumEvents = 10_000

    func append(
        _ event: AutomationEvent
    ) {

        events.append(event)

        if events.count > maximumEvents {

            events.removeFirst(
                events.count -
                maximumEvents
            )
        }
    }

    func recent(
        count: Int = 100
    ) -> [AutomationEvent] {

        Array(
            events.suffix(count)
        )
    }

    func clear() {
        events.removeAll()
    }
}

For a real implementation, this should eventually become persistent storage rather than an in-memory array.
3. Household context
Julia needs more than individual events.
It needs to understand the state of the household.
ContextModel.swift
import Foundation

struct HouseholdContext: Codable {

    let timestamp: Date

    let hour: Int
    let minute: Int

    let weekday: Int

    let occupantsPresent: Bool

    let roomsOccupied: [String]

    let homeMode: String

    let heatingActive: Bool

    let lightsOn: Int

    let appliancesRunning: Int
}

This gives Julia a compact representation:
14:32
Thursday
Home
Living room occupied
Kitchen occupied
Heating off
4 lights on
1 appliance running

4. Context extraction
ContextEngine.swift
import Foundation

@MainActor
final class ContextEngine {

    func createContext(
        date: Date = Date(),
        occupantsPresent: Bool,
        roomsOccupied: [String],
        heatingActive: Bool,
        lightsOn: Int,
        appliancesRunning: Int
    ) -> HouseholdContext {

        let calendar =
            Calendar.current

        return HouseholdContext(
            timestamp: date,

            hour:
                calendar.component(
                    .hour,
                    from: date
                ),

            minute:
                calendar.component(
                    .minute,
                    from: date
                ),

            weekday:
                calendar.component(
                    .weekday,
                    from: date
                ),

            occupantsPresent:
                occupantsPresent,

            roomsOccupied:
                roomsOccupied,

            homeMode:
                occupantsPresent
                    ? "occupied"
                    : "away",

            heatingActive:
                heatingActive,

            lightsOn:
                lightsOn,

            appliancesRunning:
                appliancesRunning
        )
    }
}

5. Julia's representation
Create:
AutomationTypes.jl
module AutomationTypes

export Event
export Context
export Routine
export Prediction
export AutomationAction
export AutomationPolicy


struct Event

    timestamp::DateTime

    event_type::String

    accessory_id::Union{String,Nothing}

    room::Union{String,Nothing}

    value::Any

end


struct Context

    timestamp::DateTime

    hour::Int
    minute::Int

    weekday::Int

    occupants_present::Bool

    rooms_occupied::Vector{String}

    home_mode::String

    heating_active::Bool

    lights_on::Int

    appliances_running::Int

end


struct Routine

    name::String

    weekday::Int

    approximate_start_minute::Int

    probability::Float64

    duration_minutes::Int

end


struct Prediction

    routine::String

    probability::Float64

    expected_start::DateTime

end


struct AutomationAction

    action_type::String

    device_id::String

    value::Any

end


struct AutomationPolicy

    prediction::Prediction

    actions::Vector{AutomationAction}

end

end

6. Learning routines
The first useful predictive model is surprisingly simple.
Given historical events, find repeated temporal patterns.
RoutineLearning.jl
module RoutineLearning

using Dates
using Statistics
using ..AutomationTypes

export learn_routines


function minute_of_day(
    t::DateTime
)

    return hour(t) * 60 + minute(t)

end


function learn_routines(
    events::Vector{Event};
    minimum_occurrences::Int = 3
)

    groups =
        Dict{Tuple{String,Int},Vector{Int}}()

    for event in events

        weekday =
            dayofweek(event.timestamp)

        minute =
            minute_of_day(
                event.timestamp
            )

        key =
            (
                event.event_type,
                weekday
            )

        if !haskey(groups, key)

            groups[key] =
                Int[]
        end

        push!(
            groups[key],
            minute
        )
    end

    routines =
        Routine[]

    total_days =
        7

    for ((event_type, weekday), times)
        in groups

        if length(times) <
           minimum_occurrences

            continue
        end

        average_time =
            round(
                Int,
                mean(times)
            )

        probability =
            min(
                1.0,
                length(times) /
                total_days
            )

        push!(
            routines,
            Routine(
                event_type,
                weekday,
                average_time,
                probability,
                30
            )
        )
    end

    return routines

end

end

This isn't yet machine learning in the fashionable sense.
It is behavioural inference.
And that is useful because household routines often have strong temporal structure.
7. Better routine prediction
We now want to answer:
Given what has happened historically, what is likely to happen next?

Create:
Prediction.jl
module Prediction

using Dates
using ..AutomationTypes

export predict_next_event


function predict_next_event(
    context::Context,
    routines::Vector{Routine}
)

    best =
        nothing

    best_probability =
        0.0

    current_minute =
        context.hour * 60 +
        context.minute

    for routine in routines

        if routine.weekday !=
           context.weekday

            continue
        end

        distance =
            routine.approximate_start_minute -
            current_minute

        if distance < 0 ||
           distance > 120

            continue
        end

        if routine.probability >
           best_probability

            best =
                routine

            best_probability =
                routine.probability
        end
    end

    if best === nothing
        return nothing
    end

    predicted_time =
        DateTime(
            year(context.timestamp),
            month(context.timestamp),
            day(context.timestamp)
        ) +
        Minute(
            best.approximate_start_minute
        )

    return Prediction(
        best.name,
        best.probability,
        predicted_time
    )

end

end

8. Context makes prediction much better
Pure time-of-day prediction isn't enough.
For example:
Every weekday:
07:00 → kitchen lights

But today:
06:55
Nobody is home.

The automation should probably not run.
So the prediction should incorporate:
time
+
weekday
+
occupancy
+
recent events
+
home mode
+
weather
+
heating state
+
energy price
+
previous routine

This is where #4 starts consuming #2 and #3.
9. Context-aware prediction
ContextPrediction.jl
module ContextPrediction

using ..AutomationTypes

export prediction_score


function prediction_score(
    routine::Routine,
    context::Context
)

    score =
        routine.probability

    # Occupancy adjustment.
    if context.home_mode == "away"

        score *= 0.1

    end

    # Evening routines become less likely
    # during working hours, etc.
    current =
        context.hour * 60 +
        context.minute

    distance =
        abs(
            routine.approximate_start_minute -
            current
        )

    time_factor =
        exp(
            -distance / 60
        )

    score *= time_factor

    return clamp(
        score,
        0.0,
        1.0
    )

end

end

Now Julia isn't simply asking:
"Does this usually happen?"

It asks:
"How likely is it to happen under today's circumstances?"

10. Predictive automation policy
The system should never immediately execute every prediction.
Instead:
Prediction
     ↓
Confidence
     ↓
Policy
     ↓
Safety constraints
     ↓
Energy constraints
     ↓
Execute

Create:
AutomationPolicy.jl
module AutomationPolicy

using ..AutomationTypes
using ..ContextPrediction

export generate_policy


function generate_policy(
    context::Context,
    routines::Vector{Routine},
    prediction::Prediction,
    actions::Vector{AutomationAction};
    threshold::Float64 = 0.80
)

    routine =
        nothing

    for r in routines

        if r.name ==
           prediction.routine

            routine = r
            break

        end

    end

    routine === nothing &&
        return nothing

    score =
        prediction_score(
            routine,
            context
        )

    if score < threshold

        return nothing
    end

    return AutomationPolicy(
        prediction,
        actions
    )

end

end

11. Example: morning routine
Suppose Julia has learned:
Weekdays

06:28
Bedroom occupancy detected

06:32
Bathroom light activated

06:37
Kitchen occupancy

06:40
Kitchen lights

06:43
Heating increases

07:15
Kitchen becomes empty

07:30
House becomes unoccupied

It can construct:
                    06:25
                      │
                predict waking
                      │
                      ▼
              bedroom context
                      │
                      ▼
              bathroom lighting
                      │
                      ▼
              kitchen prediction
                      │
                      ▼
             preheat kitchen
                      │
                      ▼
              morning routine
                      │
                      ▼
                 07:30
                 AWAY MODE

Notice that the system isn't just replaying yesterday.
It is predicting the next state.
12. Swift automation commands
Create:
AutomationCommand.swift
import Foundation

struct AutomationCommand: Codable {

    let id: UUID

    let actionType: String

    let accessoryID: UUID

    let characteristicID: UUID

    let value: AnyCodable

    let confidence: Double

    let reason: String
}

Example:
{
    "actionType": "setTemperature",
    "accessoryID": "...",
    "characteristicID": "...",
    "value": 20.5,
    "confidence": 0.91,
    "reason": "Predicted weekday morning routine"
}

13. Swift safety layer
Predictive automation needs a stronger safety system than ordinary device control.
AutomationValidator.swift
import Foundation

@MainActor
final class AutomationValidator {

    func validate(
        command: AutomationCommand
    ) -> Bool {

        guard
            command.confidence >= 0.80
        else {
            return false
        }

        guard
            !command.actionType.isEmpty
        else {
            return false
        }

        return true
    }
}

In the finished system, this becomes much more sophisticated.
14. User-controlled autonomy
A crucial design feature should be automation confidence levels.
Level 0
Never automate.

Level 1
Suggest automation.

Level 2
Automate reversible actions.

Level 3
Automate routine actions.

Level 4
Fully autonomous within user-defined boundaries.

For example:
Lighting
    Level 4

Heating
    Level 3

Dishwasher
    Level 2

Door locks
    Level 1

Security system
    Level 1

Julia therefore isn't given unlimited authority.
15. Learned preferences
The system should also learn from user corrections.
For example:
Julia:
"Turn living-room lights on at 18:15."

User:
OFF

That should become a training event:
{
    "type": "automationRejected",
    "automation": "living-room-evening-light",
    "timestamp": "..."
}

Then:
preference_score -= 0.1

Conversely:
Julia automation executed
User didn't intervene
Repeated 40 times

The confidence can rise.
16. Preference model
PreferenceModel.jl
module PreferenceModel

export update_preference
export preference_confidence


function update_preference(
    confidence::Float64,
    accepted::Bool
)

    learning_rate = 0.05

    if accepted

        confidence +=
            learning_rate *
            (1.0 - confidence)

    else

        confidence -=
            learning_rate *
            confidence

    end

    return clamp(
        confidence,
        0.0,
        1.0
    )

end


function preference_confidence(
    observations::Int,
    acceptances::Int
)

    if observations == 0
        return 0.0
    end

    return acceptances /
           observations

end

end

This creates a simple online-learning mechanism.
17. The important interaction with #3
Predictive automation can now make energy-aware decisions.
Suppose Julia predicts:
18:00
User likely arrives home

Layer #2 says:
Heating required:
20.5°C

Layer #3 says:
Electricity price at 18:00:
high

The automation engine can therefore schedule:
17:15
Begin pre-heating

17:45
Reach 20.5°C

18:00
Occupant arrives

18:00–20:00
Maintain temperature economically

So the system isn't simply:
predicting behaviour

It is optimising the house around predicted behaviour.
18. Full #4 data flow
                     HOMEKIT
                        │
                        ▼
                 Swift Event Store
                        │
                        ▼
                  Event history
                        │
                        ▼
              ┌─────────────────┐
              │ Julia Behaviour  │
              │ Learner          │
              └────────┬────────┘
                       │
                 learned routines
                       │
                       ▼
              ┌─────────────────┐
              │ Context Engine   │
              │                 │
              │ time             │
              │ day              │
              │ occupancy        │
              │ weather          │
              │ energy           │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Prediction      │
              │ Engine          │
              └────────┬────────┘
                       │
                 probability
                       │
                       ▼
              ┌─────────────────┐
              │ Policy Engine   │
              │                 │
              │ heating         │
              │ lighting        │
              │ appliances      │
              │ energy          │
              └────────┬────────┘
                       │
                 proposed actions
                       │
                       ▼
              ┌─────────────────┐
              │ Swift Validator │
              └────────┬────────┘
                       │
                       ▼
                    HomeKit
                    
                    
                    
                    
                    
                    
                    
                    
                    // ============================================================
// #5 LIGHTING INTELLIGENCE
// Swift / HomeKit Layer
// ============================================================

// ------------------------------------------------------------
// LightingModel.swift
// ------------------------------------------------------------

import Foundation
import HomeKit

struct LightingZone: Codable {
    let id: UUID
    let name: String
    let room: String

    let isOn: Bool
    let brightness: Double?
    let hue: Double?
    let saturation: Double?

    let occupancyDetected: Bool
    let daylightLux: Double?
}

struct LightingSnapshot: Codable {
    let timestamp: Date
    let sunrise: Date?
    let sunset: Date?
    let zones: [LightingZone]
}


// ------------------------------------------------------------
// LightingManager.swift
// ------------------------------------------------------------

@MainActor
final class LightingManager {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func discoverLightingAccessories() -> [HMAccessory] {

        var result: [HMAccessory] = []

        for home in homeManager.allHomes() {
            for accessory in home.accessories {

                if accessory.services.contains(where: {
                    $0.serviceType == HMServiceTypeLightbulb
                }) {
                    result.append(accessory)
                }
            }
        }

        return result
    }

    func lightingService(
        for accessory: HMAccessory
    ) -> HMService? {

        accessory.services.first {
            $0.serviceType == HMServiceTypeLightbulb
        }
    }

    func characteristic(
        _ type: String,
        from service: HMService
    ) -> HMCharacteristic? {

        service.characteristics.first {
            $0.characteristicType == type
        }
    }

    func readZone(
        accessory: HMAccessory
    ) async throws -> LightingZone? {

        guard let service =
            lightingService(for: accessory)
        else {
            return nil
        }

        let power =
            characteristic(
                HMCharacteristicTypePowerState,
                from: service
            )

        let brightness =
            characteristic(
                HMCharacteristicTypeBrightness,
                from: service
            )

        let hue =
            characteristic(
                HMCharacteristicTypeHue,
                from: service
            )

        let saturation =
            characteristic(
                HMCharacteristicTypeSaturation,
                from: service
            )

        return LightingZone(
            id: accessory.uniqueIdentifier,
            name: accessory.name,
            room: accessory.room?.name ?? "Unknown",

            isOn:
                power?.value as? Bool ?? false,

            brightness:
                brightness?.value as? Double,

            hue:
                hue?.value as? Double,

            saturation:
                saturation?.value as? Double,

            occupancyDetected: false,
            daylightLux: nil
        )
    }

    func snapshot() async throws -> LightingSnapshot {

        var zones: [LightingZone] = []

        for accessory in
            discoverLightingAccessories() {

            if let zone =
                try await readZone(
                    accessory: accessory
                ) {
                zones.append(zone)
            }
        }

        return LightingSnapshot(
            timestamp: Date(),
            sunrise: nil,
            sunset: nil,
            zones: zones
        )
    }
}


// ------------------------------------------------------------
// LightingCommand.swift
// ------------------------------------------------------------

struct LightingCommand: Codable {

    let accessoryID: UUID

    let power: Bool?
    let brightness: Double?
    let hue: Double?
    let saturation: Double?

    let transitionSeconds: Double
}


// ------------------------------------------------------------
// LightingCommandRouter.swift
// ------------------------------------------------------------

@MainActor
final class LightingCommandRouter {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func execute(
        _ command: LightingCommand
    ) async throws {

        guard
            let accessory =
                homeManager.accessory(
                    identifier: command.accessoryID
                )
        else {
            throw LightingError.accessoryNotFound
        }

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.serviceType ==
                        HMServiceTypeLightbulb
                    }
                )
        else {
            throw LightingError.serviceNotFound
        }

        if let power = command.power {

            guard
                let characteristic =
                    service.characteristics.first(
                        where: {
                            $0.characteristicType ==
                            HMCharacteristicTypePowerState
                        }
                    )
            else {
                throw LightingError.characteristicNotFound
            }

            try await characteristic.writeValue(power)
        }

        if let brightness =
            command.brightness {

            guard
                let characteristic =
                    service.characteristics.first(
                        where: {
                            $0.characteristicType ==
                            HMCharacteristicTypeBrightness
                        }
                    )
            else {
                throw LightingError.characteristicNotFound
            }

            let value =
                min(
                    100.0,
                    max(0.0, brightness)
                )

            try await characteristic.writeValue(
                value
            )
        }

        if let hue = command.hue {

            guard
                let characteristic =
                    service.characteristics.first(
                        where: {
                            $0.characteristicType ==
                            HMCharacteristicTypeHue
                        }
                    )
            else {
                throw LightingError.characteristicNotFound
            }

            try await characteristic.writeValue(
                hue
            )
        }

        if let saturation =
            command.saturation {

            guard
                let characteristic =
                    service.characteristics.first(
                        where: {
                            $0.characteristicType ==
                            HMCharacteristicTypeSaturation
                        }
                    )
            else {
                throw LightingError.characteristicNotFound
            }

            try await characteristic.writeValue(
                saturation
            )
        }
    }
}


enum LightingError: Error {
    case accessoryNotFound
    case serviceNotFound
    case characteristicNotFound
}


// ------------------------------------------------------------
// LightingValidator.swift
// ------------------------------------------------------------

struct LightingValidator {

    static func validate(
        _ command: LightingCommand
    ) -> Bool {

        if let brightness =
            command.brightness {

            guard
                brightness >= 0,
                brightness <= 100
            else {
                return false
            }
        }

        if let hue = command.hue {

            guard
                hue >= 0,
                hue <= 360
            else {
                return false
            }
        }

        if let saturation =
            command.saturation {

            guard
                saturation >= 0,
                saturation <= 100
            else {
                return false
            }
        }

        guard
            command.transitionSeconds >= 0,
            command.transitionSeconds <= 300
        else {
            return false
        }

        return true
    }
}










# ============================================================
# #5 LIGHTING INTELLIGENCE
# Julia Optimisation Layer
# ============================================================

module LightingIntelligence

using Dates
using Statistics

# ------------------------------------------------------------
# Types.jl
# ------------------------------------------------------------

export LightingZone
export LightingState
export DaylightState
export OccupancyState
export LightingPolicy
export LightingAction


struct LightingZone

    id::String
    name::String
    room::String

    is_on::Bool
    brightness::Float64

    hue::Float64
    saturation::Float64

    occupancy::Bool
    daylight_lux::Float64

end


struct LightingState

    timestamp::DateTime

    zones::Vector{LightingZone}

end


struct DaylightState

    solar_elevation::Float64
    daylight_lux::Float64

    sunrise::Union{DateTime,Nothing}
    sunset::Union{DateTime,Nothing}

end


struct OccupancyState

    occupied_rooms::Vector{String}

    home_occupied::Bool

end


struct LightingAction

    zone_id::String

    power::Bool

    brightness::Float64

    hue::Float64
    saturation::Float64

    transition_seconds::Float64

end


struct LightingPolicy

    actions::Vector{LightingAction}

end


# ------------------------------------------------------------
# DaylightModel.jl
# ------------------------------------------------------------

export estimate_daylight
export daylight_factor


function daylight_factor(
    solar_elevation::Float64
)

    if solar_elevation <= 0
        return 0.0
    end

    return clamp(
        sin(
            deg2rad(
                solar_elevation
            )
        ),
        0.0,
        1.0
    )

end


function estimate_daylight(
    solar_elevation::Float64,
    outdoor_lux::Float64 = 10000.0
)

    factor =
        daylight_factor(
            solar_elevation
        )

    return outdoor_lux * factor

end


function estimate_daylight(
    timestamp::DateTime,
    sunrise::DateTime,
    sunset::DateTime
)

    if timestamp <= sunrise ||
       timestamp >= sunset

        return 0.0
    end

    total =
        Dates.value(
            sunset - sunrise
        ) / 1000 / 60

    elapsed =
        Dates.value(
            timestamp - sunrise
        ) / 1000 / 60

    phase =
        elapsed / total

    # Approximate solar curve.
    return 10000.0 *
           max(
               0.0,
               sin(pi * phase)
           )

end


# ------------------------------------------------------------
# CircadianModel.jl
# ------------------------------------------------------------

export preferred_brightness
export preferred_colour_temperature


function preferred_brightness(
    hour::Int,
    daylight_lux::Float64,
    occupied::Bool
)

    if !occupied
        return 0.0
    end

    # Strong daylight means less artificial light.
    daylight_reduction =
        clamp(
            daylight_lux / 1000.0,
            0.0,
            0.75
        )

    if hour >= 6 &&
       hour < 10

        base = 70.0

    elseif hour >= 10 &&
           hour < 17

        base = 60.0

    elseif hour >= 17 &&
           hour < 22

        base = 55.0

    else

        base = 25.0

    end

    return clamp(
        base *
        (1.0 - daylight_reduction),
        5.0,
        100.0
    )

end


function preferred_colour_temperature(
    hour::Int
)

    if hour >= 6 &&
       hour < 12

        return 4000.0

    elseif hour >= 12 &&
           hour < 18

        return 4200.0

    elseif hour >= 18 &&
           hour < 22

        return 3000.0

    else

        return 2200.0
    end

end


# ------------------------------------------------------------
# HueConversion.jl
# ------------------------------------------------------------

export colour_temperature_to_hue


function colour_temperature_to_hue(
    kelvin::Float64
)

    # Approximate warm/cool mapping.
    # HomeKit hue is 0...360.
    #
    # Warm white → approximately 30°
    # Neutral white → approximately 50°
    # Cool white → approximately 200°

    if kelvin <= 2500
        return 25.0

    elseif kelvin <= 3000
        return 30.0

    elseif kelvin <= 3500
        return 40.0

    elseif kelvin <= 4500
        return 55.0

    else
        return 180.0
    end

end


# ------------------------------------------------------------
# OccupancyModel.jl
# ------------------------------------------------------------

export room_is_active
export occupancy_weight


function room_is_active(
    room::String,
    occupancy::OccupancyState
)

    return room in
           occupancy.occupied_rooms

end


function occupancy_weight(
    occupied::Bool
)

    return occupied ? 1.0 : 0.0

end


# ------------------------------------------------------------
# LightingObjective.jl
# ------------------------------------------------------------

export lighting_cost


function lighting_cost(
    brightness::Float64,
    desired::Float64,
    daylight_lux::Float64,
    power_weight::Float64 = 0.01,
    comfort_weight::Float64 = 1.0
)

    comfort_error =
        (brightness - desired)^2

    energy_cost =
        brightness *
        power_weight

    # Artificial light is less valuable
    # when daylight is already abundant.
    daylight_penalty =
        daylight_lux > 500.0 ?
        brightness * 0.05 :
        0.0

    return comfort_weight *
           comfort_error +
           energy_cost +
           daylight_penalty

end


# ------------------------------------------------------------
# LightingOptimizer.jl
# ------------------------------------------------------------

export optimise_brightness


function optimise_brightness(
    zone::LightingZone,
    hour::Int,
    daylight_lux::Float64,
    occupied::Bool
)

    desired =
        preferred_brightness(
            hour,
            daylight_lux,
            occupied
        )

    candidates =
        collect(
            0.0:5.0:100.0
        )

    best =
        candidates[1]

    best_cost =
        Inf

    for brightness in candidates

        cost =
            lighting_cost(
                brightness,
                desired,
                daylight_lux
            )

        if cost < best_cost

            best_cost = cost
            best = brightness

        end
    end

    return best

end


# ------------------------------------------------------------
# LightingPolicy.jl
# ------------------------------------------------------------

export create_lighting_policy


function create_lighting_policy(
    state::LightingState,
    occupancy::OccupancyState,
    daylight::DaylightState
)

    actions =
        LightingAction[]

    current_hour =
        hour(state.timestamp)

    for zone in state.zones

        occupied =
            room_is_active(
                zone.room,
                occupancy
            )

        brightness =
            optimise_brightness(
                zone,
                current_hour,
                daylight.daylight_lux,
                occupied
            )

        temperature =
            preferred_colour_temperature(
                current_hour
            )

        hue =
            colour_temperature_to_hue(
                temperature
            )

        saturation =
            20.0

        power =
            brightness > 1.0 &&
            occupied

        transition =
            power ? 3.0 : 5.0

        push!(
            actions,
            LightingAction(
                zone.id,
                power,
                brightness,
                hue,
                saturation,
                transition
            )
        )
    end

    return LightingPolicy(
        actions
    )

end


# ------------------------------------------------------------
# PredictiveLighting.jl
# ------------------------------------------------------------

export predict_lighting


function predict_lighting(
    state::LightingState,
    occupancy_forecast::Vector{Bool},
    daylight_forecast::Vector{Float64},
    hours::Vector{Int}
)

    predictions =
        Vector{LightingPolicy}()

    for i in eachindex(hours)

        occupied_rooms =
            occupancy_forecast[i] ?
            [z.room for z in state.zones] :
            String[]

        occupancy =
            OccupancyState(
                occupied_rooms,
                occupancy_forecast[i]
            )

        daylight =
            DaylightState(
                daylight_forecast[i] > 100 ?
                    30.0 :
                    -5.0,

                daylight_forecast[i],

                nothing,
                nothing
            )

        policy =
            create_lighting_policy(
                state,
                occupancy,
                daylight
            )

        push!(
            predictions,
            policy
        )
    end

    return predictions

end


# ------------------------------------------------------------
# Scene optimisation
# ------------------------------------------------------------

export scene_cost
export optimise_scene


function scene_cost(
    zones::Vector{LightingZone},
    brightnesses::Vector{Float64},
    daylight_lux::Float64,
    hour::Int
)

    total = 0.0

    for i in eachindex(zones)

        zone =
            zones[i]

        desired =
            preferred_brightness(
                hour,
                daylight_lux,
                zone.occupancy
            )

        total +=
            lighting_cost(
                brightnesses[i],
                desired,
                daylight_lux
            )
    end

    return total

end


function optimise_scene(
    state::LightingState,
    occupancy::OccupancyState,
    daylight::DaylightState
)

    brightnesses =
        Float64[]

    for zone in state.zones

        occupied =
            room_is_active(
                zone.room,
                occupancy
            )

        value =
            optimise_brightness(
                zone,
                hour(state.timestamp),
                daylight.daylight_lux,
                occupied
            )

        push!(
            brightnesses,
            value
        )
    end

    return brightnesses

end


# ------------------------------------------------------------
# AdaptivePreferences.jl
# ------------------------------------------------------------

export update_preference


function update_preference(
    current::Float64,
    observed_brightness::Float64,
    learning_rate::Float64 = 0.05
)

    return current +
           learning_rate *
           (
               observed_brightness -
               current
           )

end


# ------------------------------------------------------------
# Energy-aware lighting
# ------------------------------------------------------------

export energy_adjusted_brightness


function energy_adjusted_brightness(
    desired_brightness::Float64,
    electricity_price::Float64,
    battery_soc::Float64,
    solar_surplus_kw::Float64
)

    brightness =
        desired_brightness

    # During expensive periods, modestly reduce
    # unnecessary artificial lighting.
    if electricity_price > 0.30

        brightness *= 0.90

    end

    # Cheap solar energy permits normal lighting.
    if solar_surplus_kw > 1.0

        brightness =
            desired_brightness

    end

    # Do not aggressively dim occupied rooms.
    if battery_soc < 0.10

        brightness *= 0.95

    end

    return clamp(
        brightness,
        0.0,
        100.0
    )

end


# ------------------------------------------------------------
# Main lighting intelligence function
# ------------------------------------------------------------

export optimise_lighting


function optimise_lighting(
    state::LightingState,
    occupancy::OccupancyState,
    daylight::DaylightState;
    electricity_price::Float64 = 0.25,
    battery_soc::Float64 = 0.50,
    solar_surplus_kw::Float64 = 0.0
)

    actions =
        LightingAction[]

    current_hour =
        hour(state.timestamp)

    for zone in state.zones

        occupied =
            room_is_active(
                zone.room,
                occupancy
            )

        base_brightness =
            optimise_brightness(
                zone,
                current_hour,
                daylight.daylight_lux,
                occupied
            )

        brightness =
            energy_adjusted_brightness(
                base_brightness,
                electricity_price,
                battery_soc,
                solar_surplus_kw
            )

        colour_temperature =
            preferred_colour_temperature(
                current_hour
            )

        hue =
            colour_temperature_to_hue(
                colour_temperature
            )

        power =
            occupied &&
            brightness > 1.0

        push!(
            actions,
            LightingAction(
                zone.id,
                power,
                brightness,
                hue,
                20.0,
                3.0
            )
        )
    end

    return LightingPolicy(
        actions
    )

end

end




# ============================================================
# Example Julia usage
# ============================================================

using Dates

include("LightingIntelligence.jl")

using .LightingIntelligence

zones = LightingZone[
    LightingZone(
        "living-room-light",
        "Living Room Light",
        "Living Room",
        true,
        80.0,
        0.0,
        0.0,
        true,
        250.0
    ),

    LightingZone(
        "kitchen-light",
        "Kitchen Light",
        "Kitchen",
        false,
        0.0,
        0.0,
        0.0,
        true,
        120.0
    ),

    LightingZone(
        "bedroom-light",
        "Bedroom Light",
        "Bedroom",
        false,
        0.0,
        0.0,
        0.0,
        false,
        80.0
    )
]

state = LightingState(
    DateTime(2026, 10, 8, 19, 30),
    zones
)

occupancy = OccupancyState(
    [
        "Living Room",
        "Kitchen"
    ],
    true
)

daylight = DaylightState(
    -4.0,
    50.0,
    nothing,
    nothing
)

policy =
    optimise_lighting(
        state,
        occupancy,
        daylight;
        electricity_price = 0.31,
        battery_soc = 0.42,
        solar_surplus_kw = 0.0
    )

for action in policy.actions

    println(
        action.zone_id,
        " → ",
        action.power,
        " / ",
        action.brightness,
        "%"
    )

end





// ============================================================
// Swift → Julia JSON bridge
// ============================================================

import Foundation

struct LightingJSONBridge {

    static func encode(
        _ snapshot: LightingSnapshot
    ) throws -> Data {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        encoder.outputFormatting = [
            .sortedKeys
        ]

        return try encoder.encode(
            snapshot
        )
    }

    static func decodeCommands(
        _ data: Data
    ) throws -> [LightingCommand] {

        let decoder = JSONDecoder()

        return try decoder.decode(
            [LightingCommand].self,
            from: data
        )
    }
}



# ============================================================
# Julia policy JSON output
# ============================================================

using JSON3

function policy_to_json(
    policy::LightingPolicy
)

    actions = [
        Dict(
            "zone_id" =>
                action.zone_id,

            "power" =>
                action.power,

            "brightness" =>
                action.brightness,

            "hue" =>
                action.hue,

            "saturation" =>
                action.saturation,

            "transition_seconds" =>
                action.transition_seconds
        )
        for action in policy.actions
    ]

    return JSON3.write(
        Dict(
            "actions" => actions
        )
    )

end




// ============================================================
// #6 HOME SECURITY
// Swift / HomeKit Security Layer
// ============================================================

// ------------------------------------------------------------
// SecurityModel.swift
// ------------------------------------------------------------

import Foundation
import HomeKit

enum SecurityEventType: String, Codable {
    case doorOpened
    case doorClosed
    case windowOpened
    case windowClosed
    case motionDetected
    case occupancyDetected
    case smokeDetected
    case carbonMonoxideDetected
    case waterLeakDetected
    case alarmTriggered
    case lockLocked
    case lockUnlocked
    case unknown
}

struct SecuritySensor: Codable {
    let id: UUID
    let name: String
    let room: String
    let type: SecurityEventType

    let triggered: Bool
    let reachable: Bool

    let timestamp: Date
}

struct SecurityEvent: Codable {
    let id: UUID
    let timestamp: Date

    let sensorID: UUID
    let room: String
    let type: SecurityEventType

    let triggered: Bool
    let source: String
}

struct SecuritySnapshot: Codable {
    let timestamp: Date

    let homeOccupied: Bool
    let homeMode: String

    let sensors: [SecuritySensor]
    let recentEvents: [SecurityEvent]
}




// ------------------------------------------------------------
// SecurityManager.swift
// ------------------------------------------------------------

import Foundation
import HomeKit

@MainActor
final class SecurityManager {

    private let homeManager: HomeManager

    private(set) var events:
        [SecurityEvent] = []

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    // --------------------------------------------------------
    // Discovery
    // --------------------------------------------------------

    func discoverSecurityAccessories()
        -> [HMAccessory] {

        var accessories: [HMAccessory] = []

        for home in homeManager.allHomes() {

            for accessory in home.accessories {

                let relevant =
                    accessory.services.contains {
                        service in

                        switch service.serviceType {

                        case HMServiceTypeMotionSensor,
                             HMServiceTypeContactSensor,
                             HMServiceTypeOccupancySensor,
                             HMServiceTypeSmokeSensor,
                             HMServiceTypeCarbonMonoxideSensor,
                             HMServiceTypeLeakSensor,
                             HMServiceTypeSecuritySystem,
                             HMServiceTypeLockMechanism:

                            return true

                        default:
                            return false
                        }
                    }

                if relevant {
                    accessories.append(accessory)
                }
            }
        }

        return accessories
    }

    // --------------------------------------------------------
    // Service → Security event type
    // --------------------------------------------------------

    func eventType(
        for service: HMService
    ) -> SecurityEventType {

        switch service.serviceType {

        case HMServiceTypeMotionSensor:
            return .motionDetected

        case HMServiceTypeOccupancySensor:
            return .occupancyDetected

        case HMServiceTypeContactSensor:
            return .doorOpened

        case HMServiceTypeSmokeSensor:
            return .smokeDetected

        case HMServiceTypeCarbonMonoxideSensor:
            return .carbonMonoxideDetected

        case HMServiceTypeLeakSensor:
            return .waterLeakDetected

        case HMServiceTypeLockMechanism:
            return .lockUnlocked

        case HMServiceTypeSecuritySystem:
            return .alarmTriggered

        default:
            return .unknown
        }
    }

    // --------------------------------------------------------
    // Triggered state
    // --------------------------------------------------------

    func triggeredCharacteristic(
        for service: HMService
    ) -> HMCharacteristic? {

        switch service.serviceType {

        case HMServiceTypeMotionSensor,
             HMServiceTypeOccupancySensor:

            return service.characteristics.first {
                $0.characteristicType ==
                HMCharacteristicTypeStatusActive
            }

        case HMServiceTypeContactSensor:

            return service.characteristics.first {
                $0.characteristicType ==
                HMCharacteristicTypeContactState
            }

        case HMServiceTypeSmokeSensor:

            return service.characteristics.first {
                $0.characteristicType ==
                HMCharacteristicTypeSmokeDetected
            }

        case HMServiceTypeCarbonMonoxideSensor:

            return service.characteristics.first {
                $0.characteristicType ==
                HMCharacteristicTypeCarbonMonoxideDetected
            }

        case HMServiceTypeLeakSensor:

            return service.characteristics.first {
                $0.characteristicType ==
                HMCharacteristicTypeLeakDetected
            }

        default:
            return nil
        }
    }

    // --------------------------------------------------------
    // Read sensor
    // --------------------------------------------------------

    func readSensor(
        accessory: HMAccessory
    ) async throws -> SecuritySensor? {

        guard
            let service =
                accessory.services.first(
                    where: {
                        [
                            HMServiceTypeMotionSensor,
                            HMServiceTypeContactSensor,
                            HMServiceTypeOccupancySensor,
                            HMServiceTypeSmokeSensor,
                            HMServiceTypeCarbonMonoxideSensor,
                            HMServiceTypeLeakSensor
                        ]
                        .contains($0.serviceType)
                    }
                )
        else {
            return nil
        }

        let characteristic =
            triggeredCharacteristic(
                for: service
            )

        let rawValue =
            characteristic?.value

        let triggered =
            parseTriggeredValue(
                rawValue,
                serviceType: service.serviceType
            )

        return SecuritySensor(
            id: accessory.uniqueIdentifier,
            name: accessory.name,
            room: accessory.room?.name ?? "Unknown",
            type: eventType(
                for: service
            ),
            triggered: triggered,
            reachable: accessory.isReachable,
            timestamp: Date()
        )
    }

    // --------------------------------------------------------
    // Convert HomeKit values
    // --------------------------------------------------------

    private func parseTriggeredValue(
        _ value: Any?,
        serviceType: String
    ) -> Bool {

        if let value = value as? Bool {
            return value
        }

        if let value = value as? NSNumber {

            if serviceType ==
                HMServiceTypeContactSensor {

                return value.intValue != 0
            }

            return value.intValue != 0
        }

        return false
    }

    // --------------------------------------------------------
    // Record event
    // --------------------------------------------------------

    func record(
        sensor: SecuritySensor
    ) {

        let event =
            SecurityEvent(
                id: UUID(),
                timestamp: sensor.timestamp,
                sensorID: sensor.id,
                room: sensor.room,
                type: sensor.type,
                triggered: sensor.triggered,
                source: "HomeKit"
            )

        events.append(event)

        if events.count > 10_000 {
            events.removeFirst(
                events.count - 10_000
            )
        }
    }

    // --------------------------------------------------------
    // Snapshot
    // --------------------------------------------------------

    func snapshot(
        homeOccupied: Bool,
        homeMode: String
    ) async throws
        -> SecuritySnapshot {

        var sensors: [SecuritySensor] = []

        for accessory
            in discoverSecurityAccessories() {

            if let sensor =
                try await readSensor(
                    accessory: accessory
                ) {

                sensors.append(sensor)

                if sensor.triggered {
                    record(sensor: sensor)
                }
            }
        }

        return SecuritySnapshot(
            timestamp: Date(),
            homeOccupied: homeOccupied,
            homeMode: homeMode,
            sensors: sensors,
            recentEvents:
                Array(
                    events.suffix(500)
                )
        )
    }
}





// ------------------------------------------------------------
// SecurityCommand.swift
// ------------------------------------------------------------

import Foundation

enum SecurityCommandType: String, Codable {
    case lock
    case unlock
    case arm
    case disarm
    case noAction
}

struct SecurityCommand: Codable {

    let id: UUID

    let type: SecurityCommandType

    let accessoryID: UUID

    let confidence: Double

    let reason: String
}



// ------------------------------------------------------------
// SecurityCommandRouter.swift
// ------------------------------------------------------------

import Foundation
import HomeKit

@MainActor
final class SecurityCommandRouter {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func execute(
        _ command: SecurityCommand
    ) async throws {

        guard
            command.type != .noAction
        else {
            return
        }

        guard
            let accessory =
                homeManager.accessory(
                    identifier:
                        command.accessoryID
                )
        else {
            throw SecurityCommandError
                .accessoryNotFound
        }

        switch command.type {

        case .lock:
            try await setLock(
                accessory,
                locked: true
            )

        case .unlock:
            try await setLock(
                accessory,
                locked: false
            )

        case .arm:
            try await setSecuritySystem(
                accessory,
                armed: true
            )

        case .disarm:
            try await setSecuritySystem(
                accessory,
                armed: false
            )

        case .noAction:
            break
        }
    }

    // --------------------------------------------------------
    // Lock
    // --------------------------------------------------------

    private func setLock(
        _ accessory: HMAccessory,
        locked: Bool
    ) async throws {

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.serviceType ==
                        HMServiceTypeLockMechanism
                    }
                )
        else {
            throw SecurityCommandError
                .serviceNotFound
        }

        guard
            let characteristic =
                service.characteristics.first(
                    where: {
                        $0.characteristicType ==
                        HMCharacteristicTypeLockTargetState
                    }
                )
        else {
            throw SecurityCommandError
                .characteristicNotFound
        }

        let value =
            locked
            ? HMCharacteristicValueLockPhysicalControlsEnabled
            : HMCharacteristicValueLockPhysicalControlsDisabled

        // Production implementations should use the
        // target-state constants supplied by HomeKit.
        try await characteristic.writeValue(
            value
        )
    }

    // --------------------------------------------------------
    // Security system
    // --------------------------------------------------------

    private func setSecuritySystem(
        _ accessory: HMAccessory,
        armed: Bool
    ) async throws {

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.serviceType ==
                        HMServiceTypeSecuritySystem
                    }
                )
        else {
            throw SecurityCommandError
                .serviceNotFound
        }

        guard
            let characteristic =
                service.characteristics.first(
                    where: {
                        $0.characteristicType ==
                        HMCharacteristicTypeSecuritySystemTargetState
                    }
                )
        else {
            throw SecurityCommandError
                .characteristicNotFound
        }

        let state =
            armed ? 0 : 3

        try await characteristic.writeValue(
            state
        )
    }
}

enum SecurityCommandError: Error {
    case accessoryNotFound
    case serviceNotFound
    case characteristicNotFound
}




// ------------------------------------------------------------
// SecurityValidator.swift
// ------------------------------------------------------------

struct SecurityValidator {

    static func validate(
        _ command: SecurityCommand,
        homeOccupied: Bool,
        homeMode: String
    ) -> Bool {

        guard
            command.confidence >= 0.90
        else {
            return false
        }

        switch command.type {

        case .unlock:

            // Never allow autonomous unlocking
            // merely because Julia predicts arrival.
            return false

        case .disarm:

            // Disarming is always explicit.
            return false

        case .lock:

            return true

        case .arm:

            return !homeOccupied

        case .noAction:

            return true
        }
    }
}


// ============================================================
// #6 HOME SECURITY
// Julia Intelligence Layer
// ============================================================

module HomeSecurity

using Dates
using Statistics

export SecuritySensor
export SecurityEvent
export SecurityState
export SecurityContext
export Anomaly
export SecurityAction
export SecurityPolicy


# ------------------------------------------------------------
# SecurityTypes.jl
# ------------------------------------------------------------

struct SecuritySensor

    id::String
    name::String
    room::String

    sensor_type::String

    triggered::Bool
    reachable::Bool

    timestamp::DateTime

end


struct SecurityEvent

    id::String
    timestamp::DateTime

    sensor_id::String
    room::String
    event_type::String

    triggered::Bool
    source::String

end


struct SecurityState

    timestamp::DateTime

    home_occupied::Bool
    home_mode::String

    sensors::Vector{SecuritySensor}
    events::Vector{SecurityEvent}

end


struct SecurityContext

    hour::Int
    weekday::Int

    home_occupied::Bool

    expected_rooms::Vector{String}

end


struct Anomaly

    score::Float64

    sensor_id::String
    room::String

    event_type::String

    explanation::String

end


struct SecurityAction

    action_type::String
    sensor_id::String

    confidence::Float64
    reason::String

end


struct SecurityPolicy

    anomalies::Vector{Anomaly}
    actions::Vector{SecurityAction}

end


# ------------------------------------------------------------
# Event statistics
# ------------------------------------------------------------

export event_frequency


function event_frequency(
    events::Vector{SecurityEvent},
    sensor_id::String
)

    matching =
        filter(
            e -> e.sensor_id == sensor_id,
            events
        )

    return length(matching)

end


function events_in_hour(
    events::Vector{SecurityEvent},
    sensor_id::String,
    hour_value::Int
)

    matching =
        filter(
            e ->
                e.sensor_id == sensor_id &&
                hour(e.timestamp) == hour_value,
            events
        )

    return length(matching)

end


# ------------------------------------------------------------
# Behavioural baseline
# ------------------------------------------------------------

export expected_event_probability


function expected_event_probability(
    event::SecurityEvent,
    historical::Vector{SecurityEvent}
)

    if isempty(historical)
        return 0.0
    end

    same_sensor =
        filter(
            e ->
                e.sensor_id == event.sensor_id,
            historical
        )

    if isempty(same_sensor)
        return 0.0
    end

    same_hour =
        filter(
            e ->
                hour(e.timestamp) ==
                hour(event.timestamp),
            same_sensor
        )

    return clamp(
        length(same_hour) /
        length(same_sensor),
        0.0,
        1.0
    )

end


# ------------------------------------------------------------
# Anomaly detection
# ------------------------------------------------------------

export anomaly_score


function anomaly_score(
    event::SecurityEvent,
    state::SecurityState
)

    probability =
        expected_event_probability(
            event,
            state.events
        )

    score =
        1.0 - probability

    # Events while nobody is home are
    # inherently more interesting.
    if !state.home_occupied

        if event.event_type in (
            "motionDetected",
            "occupancyDetected",
            "doorOpened",
            "windowOpened"
        )

            score += 0.30
        end
    end

    # Safety-critical sensors get priority.
    if event.event_type in (
        "smokeDetected",
        "carbonMonoxideDetected",
        "waterLeakDetected",
        "alarmTriggered"
    )

        score += 0.50
    end

    return clamp(
        score,
        0.0,
        1.0
    )

end


# ------------------------------------------------------------
# Explain anomaly
# ------------------------------------------------------------

export explain_anomaly


function explain_anomaly(
    event::SecurityEvent,
    state::SecurityState,
    score::Float64
)

    reasons = String[]

    if !state.home_occupied
        push!(
            reasons,
            "home is unoccupied"
        )
    end

    probability =
        expected_event_probability(
            event,
            state.events
        )

    if probability < 0.10
        push!(
            reasons,
            "event is unusual for this time"
        )
    end

    if event.event_type in (
        "smokeDetected",
        "carbonMonoxideDetected",
        "waterLeakDetected"
    )

        push!(
            reasons,
            "safety-critical sensor triggered"
        )
    end

    if isempty(reasons)
        return "No significant anomaly detected."
    end

    return join(
        reasons,
        "; "
    )

end


# ------------------------------------------------------------
# Detect anomalies
# ------------------------------------------------------------

export detect_anomalies


function detect_anomalies(
    state::SecurityState;
    threshold::Float64 = 0.70
)

    anomalies =
        Anomaly[]

    for event in state.events

        score =
            anomaly_score(
                event,
                state
            )

        if score >= threshold

            push!(
                anomalies,
                Anomaly(
                    score,
                    event.sensor_id,
                    event.room,
                    event.event_type,
                    explain_anomaly(
                        event,
                        state,
                        score
                    )
                )
            )
        end
    end

    return anomalies

end


# ------------------------------------------------------------
# Sensor health
# ------------------------------------------------------------

export sensor_health_score


function sensor_health_score(
    sensor::SecuritySensor
)

    return sensor.reachable ?
        1.0 :
        0.0

end


# ------------------------------------------------------------
# Security state classifier
# ------------------------------------------------------------

export classify_home_state


function classify_home_state(
    state::SecurityState
)

    if !state.home_occupied
        return :away
    end

    active =
        count(
            s -> s.triggered,
            state.sensors
        )

    if active == 0
        return :quiet
    end

    return :active

end


# ------------------------------------------------------------
# Threat classification
# ------------------------------------------------------------

export threat_level


function threat_level(
    anomaly::Anomaly
)

    if anomaly.event_type in (
        "smokeDetected",
        "carbonMonoxideDetected",
        "waterLeakDetected"
    )

        return :critical

    elseif anomaly.score >= 0.90

        return :high

    elseif anomaly.score >= 0.70

        return :medium

    else

        return :low
    end

end


# ------------------------------------------------------------
# Security policy
# ------------------------------------------------------------

export create_security_policy


function create_security_policy(
    state::SecurityState
)

    anomalies =
        detect_anomalies(
            state
        )

    actions =
        SecurityAction[]

    for anomaly in anomalies

        level =
            threat_level(
                anomaly
            )

        # ----------------------------------------------------
        # Safety events
        # ----------------------------------------------------

        if level == :critical

            push!(
                actions,
                SecurityAction(
                    "alert",
                    anomaly.sensor_id,
                    1.0,
                    anomaly.explanation
                )
            )

        # ----------------------------------------------------
        # High confidence intrusion-like event
        # ----------------------------------------------------

        elseif level == :high

            push!(
                actions,
                SecurityAction(
                    "alert",
                    anomaly.sensor_id,
                    anomaly.score,
                    anomaly.explanation
                )
            )

        # ----------------------------------------------------
        # Medium confidence event
        # ----------------------------------------------------

        elseif level == :medium

            push!(
                actions,
                SecurityAction(
                    "notify",
                    anomaly.sensor_id,
                    anomaly.score,
                    anomaly.explanation
                )
            )
        end
    end

    return SecurityPolicy(
        anomalies,
        actions
    )

end


# ------------------------------------------------------------
# Predictive security
# ------------------------------------------------------------

export predict_security_state


function predict_security_state(
    state::SecurityState,
    expected_rooms::Vector{String}
)

    context =
        SecurityContext(
            hour(state.timestamp),
            dayofweek(state.timestamp),
            state.home_occupied,
            expected_rooms
        )

    unexpected_rooms =
        setdiff(
            [
                s.room
                for s in state.sensors
                if s.triggered
            ],
            context.expected_rooms
        )

    actions =
        SecurityAction[]

    for room in unexpected_rooms

        sensor =
            findfirst(
                s ->
                    s.room == room &&
                    s.triggered,
                state.sensors
            )

        if sensor !== nothing

            push!(
                actions,
                SecurityAction(
                    "notify",
                    state.sensors[sensor].id,
                    0.85,
                    "Activity detected in an unexpected room."
                )
            )
        end
    end

    return actions

end


# ------------------------------------------------------------
# Adaptive household model
# ------------------------------------------------------------

export learn_household_pattern


function learn_household_pattern(
    events::Vector{SecurityEvent}
)

    pattern =
        Dict{String,Vector{Int}}()

    for event in events

        if !haskey(
            pattern,
            event.room
        )

            pattern[event.room] =
                Int[]
        end

        push!(
            pattern[event.room],
            hour(event.timestamp)
        )
    end

    return pattern

end


# ------------------------------------------------------------
# False-positive reduction
# ------------------------------------------------------------

export false_positive_probability


function false_positive_probability(
    event::SecurityEvent,
    historical::Vector{SecurityEvent}
)

    matching =
        filter(
            e ->
                e.sensor_id == event.sensor_id &&
                e.event_type == event.event_type,
            historical
        )

    if length(matching) < 5
        return 0.0
    end

    hour_matches =
        count(
            e ->
                abs(
                    hour(e.timestamp) -
                    hour(event.timestamp)
                ) <= 1,
            matching
        )

    return clamp(
        hour_matches /
        length(matching),
        0.0,
        1.0
    )

end


# ------------------------------------------------------------
# Final security engine
# ------------------------------------------------------------

export analyse_security


function analyse_security(
    state::SecurityState
)

    anomalies =
        detect_anomalies(
            state;
            threshold = 0.65
        )

    actions =
        SecurityAction[]

    for anomaly in anomalies

        false_positive =
            false_positive_probability(
                SecurityEvent(
                    string(uuid4()),
                    state.timestamp,
                    anomaly.sensor_id,
                    anomaly.room,
                    anomaly.event_type,
                    true,
                    "Julia"
                ),
                state.events
            )

        adjusted_score =
            anomaly.score *
            (1.0 - 0.5 * false_positive)

        if adjusted_score >= 0.90

            push!(
                actions,
                SecurityAction(
                    "alert",
                    anomaly.sensor_id,
                    adjusted_score,
                    anomaly.explanation
                )
            )

        elseif adjusted_score >= 0.70

            push!(
                actions,
                SecurityAction(
                    "notify",
                    anomaly.sensor_id,
                    adjusted_score,
                    anomaly.explanation
                )
            )
        end
    end

    return SecurityPolicy(
        anomalies,
        actions
    )

end

end



# ============================================================
# JSON interface
# ============================================================

using JSON3
using Dates

function security_policy_to_json(
    policy::SecurityPolicy
)

    actions = [
        Dict(
            "action_type" =>
                action.action_type,

            "sensor_id" =>
                action.sensor_id,

            "confidence" =>
                action.confidence,

            "reason" =>
                action.reason
        )
        for action in policy.actions
    ]

    anomalies = [
        Dict(
            "score" =>
                anomaly.score,

            "sensor_id" =>
                anomaly.sensor_id,

            "room" =>
                anomaly.room,

            "event_type" =>
                anomaly.event_type,

            "explanation" =>
                anomaly.explanation
        )
        for anomaly in policy.anomalies
    ]

    return JSON3.write(
        Dict(
            "actions" => actions,
            "anomalies" => anomalies
        )
    )

end



// ============================================================
// Swift security event JSON bridge
// ============================================================

import Foundation

struct SecurityJSONBridge {

    static func encode(
        _ snapshot: SecuritySnapshot
    ) throws -> Data {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        encoder.outputFormatting = [
            .sortedKeys
        ]

        return try encoder.encode(
            snapshot
        )
    }
}




// ============================================================
// Example
// ============================================================

using Dates

include("HomeSecurity.jl")

using .HomeSecurity

events = SecurityEvent[
    SecurityEvent(
        "1",
        DateTime(2026, 10, 8, 18, 00),
        "front-door",
        "Hall",
        "doorOpened",
        true,
        "HomeKit"
    ),

    SecurityEvent(
        "2",
        DateTime(2026, 10, 8, 18, 01),
        "hall-motion",
        "Hall",
        "motionDetected",
        true,
        "HomeKit"
    )
]

sensors = SecuritySensor[
    SecuritySensor(
        "front-door",
        "Front Door",
        "Hall",
        "doorOpened",
        true,
        true,
        DateTime(2026, 10, 8, 18, 01)
    ),

    SecuritySensor(
        "hall-motion",
        "Hall Motion",
        "Hall",
        "motionDetected",
        true,
        true,
        DateTime(2026, 10, 8, 18, 01)
    )
]

state =
    SecurityState(
        DateTime(2026, 10, 8, 18, 01),
        false,
        "away",
        sensors,
        events
    )

policy =
    analyse_security(
        state
    )

println(
    security_policy_to_json(
        policy
    )
)




// ============================================================
// #7 APPLIANCE SCHEDULING
// Swift / HomeKit Execution Layer
// ============================================================

import Foundation
import HomeKit

// ------------------------------------------------------------
// ApplianceModel.swift
// ------------------------------------------------------------

enum ApplianceType: String, Codable {
    case dishwasher
    case washingMachine
    case tumbleDryer
    case oven
    case kettle
    case waterHeater
    case EVCharger
    case generic
}

struct ApplianceDevice: Codable {
    let id: UUID
    let name: String
    let room: String
    let type: ApplianceType

    let isOn: Bool
    let isReachable: Bool

    let powerWatts: Double?
    let energyKWh: Double?

    let flexible: Bool
    let minimumRuntimeMinutes: Int
    let maximumRuntimeMinutes: Int

    let earliestStart: Date?
    let latestFinish: Date?
}

struct ApplianceSnapshot: Codable {
    let timestamp: Date
    let devices: [ApplianceDevice]
}


// ------------------------------------------------------------
// ApplianceManager.swift
// ------------------------------------------------------------

@MainActor
final class ApplianceManager {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    // --------------------------------------------------------
    // Discovery
    // --------------------------------------------------------

    func discoverAppliances()
        -> [HMAccessory] {

        var result: [HMAccessory] = []

        for home in homeManager.allHomes() {

            for accessory in home.accessories {

                let hasSwitch =
                    accessory.services.contains {
                        $0.serviceType ==
                        HMServiceTypeSwitch
                    }

                let hasOutlet =
                    accessory.services.contains {
                        $0.serviceType ==
                        HMServiceTypeOutlet
                    }

                if hasSwitch || hasOutlet {
                    result.append(accessory)
                }
            }
        }

        return result
    }

    // --------------------------------------------------------
    // Appliance classification
    // --------------------------------------------------------

    func applianceType(
        for accessory: HMAccessory
    ) -> ApplianceType {

        let name =
            accessory.name.lowercased()

        if name.contains("dishwasher") {
            return .dishwasher
        }

        if name.contains("washing") ||
           name.contains("washer") {

            return .washingMachine
        }

        if name.contains("dryer") {
            return .tumbleDryer
        }

        if name.contains("oven") {
            return .oven
        }

        if name.contains("kettle") {
            return .kettle
        }

        if name.contains("water") &&
           name.contains("heater") {

            return .waterHeater
        }

        if name.contains("ev") ||
           name.contains("charger") {

            return .EVCharger
        }

        return .generic
    }

    // --------------------------------------------------------
    // Switch state
    // --------------------------------------------------------

    func powerCharacteristic(
        for service: HMService
    ) -> HMCharacteristic? {

        service.characteristics.first {
            $0.characteristicType ==
            HMCharacteristicTypePowerState
        }
    }

    // --------------------------------------------------------
    // Read appliance
    // --------------------------------------------------------

    func readAppliance(
        accessory: HMAccessory
    ) async throws -> ApplianceDevice? {

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.serviceType ==
                        HMServiceTypeSwitch ||
                        $0.serviceType ==
                        HMServiceTypeOutlet
                    }
                )
        else {
            return nil
        }

        let power =
            powerCharacteristic(
                for: service
            )

        let isOn =
            power?.value as? Bool ?? false

        return ApplianceDevice(
            id: accessory.uniqueIdentifier,
            name: accessory.name,
            room: accessory.room?.name ?? "Unknown",

            type:
                applianceType(
                    for: accessory
                ),

            isOn: isOn,
            isReachable:
                accessory.isReachable,

            powerWatts: nil,
            energyKWh: nil,

            flexible:
                applianceType(
                    for: accessory
                ) != .oven,

            minimumRuntimeMinutes:
                30,

            maximumRuntimeMinutes:
                180,

            earliestStart: nil,
            latestFinish: nil
        )
    }

    // --------------------------------------------------------
    // Snapshot
    // --------------------------------------------------------

    func snapshot()
        async throws
        -> ApplianceSnapshot {

        var devices:
            [ApplianceDevice] = []

        for accessory
            in discoverAppliances() {

            if let device =
                try await readAppliance(
                    accessory: accessory
                ) {

                devices.append(device)
            }
        }

        return ApplianceSnapshot(
            timestamp: Date(),
            devices: devices
        )
    }
}


// ------------------------------------------------------------
// ApplianceCommand.swift
// ------------------------------------------------------------

struct ApplianceCommand: Codable {

    let id: UUID
    let accessoryID: UUID

    let power: Bool

    let scheduledStart: Date?
    let scheduledFinish: Date?

    let reason: String
}


// ------------------------------------------------------------
// ApplianceCommandRouter.swift
// ------------------------------------------------------------

@MainActor
final class ApplianceCommandRouter {

    private let homeManager: HomeManager

    init(homeManager: HomeManager) {
        self.homeManager = homeManager
    }

    func execute(
        _ command: ApplianceCommand
    ) async throws {

        guard
            let accessory =
                homeManager.accessory(
                    identifier:
                        command.accessoryID
                )
        else {
            throw ApplianceError
                .accessoryNotFound
        }

        guard
            let service =
                accessory.services.first(
                    where: {
                        $0.serviceType ==
                        HMServiceTypeSwitch ||
                        $0.serviceType ==
                        HMServiceTypeOutlet
                    }
                )
        else {
            throw ApplianceError
                .serviceNotFound
        }

        guard
            let characteristic =
                service.characteristics.first(
                    where: {
                        $0.characteristicType ==
                        HMCharacteristicTypePowerState
                    }
                )
        else {
            throw ApplianceError
                .characteristicNotFound
        }

        try await characteristic.writeValue(
            command.power
        )
    }
}


enum ApplianceError: Error {
    case accessoryNotFound
    case serviceNotFound
    case characteristicNotFound
}


// ------------------------------------------------------------
// ApplianceValidator.swift
// ------------------------------------------------------------

struct ApplianceValidator {

    static func validate(
        _ command: ApplianceCommand,
        device: ApplianceDevice
    ) -> Bool {

        guard device.isReachable else {
            return false
        }

        guard device.flexible else {
            return false
        }

        if let start =
            command.scheduledStart,
           let finish =
            command.scheduledFinish {

            guard finish > start else {
                return false
            }

            let minutes =
                finish.timeIntervalSince(
                    start
                ) / 60.0

            guard
                minutes >=
                    Double(
                        device.minimumRuntimeMinutes
                    ),
                minutes <=
                    Double(
                        device.maximumRuntimeMinutes
                    )
            else {
                return false
            }
        }

        return true
    }
}




// ============================================================
// #7 APPLIANCE SCHEDULING
// Julia Optimisation Layer
// ============================================================

module ApplianceScheduling

using Dates
using Statistics

export Appliance
export ApplianceState
export ElectricityPrice
export ApplianceSchedule
export ApplianceAction
export AppliancePolicy


# ------------------------------------------------------------
# ApplianceTypes.jl
# ------------------------------------------------------------

struct Appliance

    id::String
    name::String
    room::String
    appliance_type::String

    is_on::Bool
    reachable::Bool

    power_kw::Float64
    energy_kwh::Float64

    flexible::Bool

    runtime_minutes::Int

    earliest_start::Int
    latest_finish::Int

end


struct ApplianceState

    timestamp::DateTime

    appliances::Vector{Appliance}

end


struct ElectricityPrice

    timestamp::DateTime
    price_per_kwh::Float64

end


struct ApplianceSchedule

    appliance_id::String

    start_minute::Int
    finish_minute::Int

    expected_energy_kwh::Float64
    expected_cost::Float64

end


struct ApplianceAction

    appliance_id::String

    action_type::String

    scheduled_start::Int
    scheduled_finish::Int

    reason::String

end


struct AppliancePolicy

    schedules::Vector{ApplianceSchedule}
    actions::Vector{ApplianceAction}

end


# ------------------------------------------------------------
# Time helpers
# ------------------------------------------------------------

export minute_of_day


function minute_of_day(
    timestamp::DateTime
)

    return hour(timestamp) * 60 +
           minute(timestamp)

end


function minutes_to_datetime(
    base::DateTime,
    minute::Int
)

    midnight =
        DateTime(
            year(base),
            month(base),
            day(base)
        )

    return midnight +
           Minute(minute)

end


# ------------------------------------------------------------
# Price model
# ------------------------------------------------------------

export price_at


function price_at(
    prices::Vector{ElectricityPrice},
    minute::Int
)

    if isempty(prices)
        return 0.25
    end

    best =
        prices[1]

    best_distance =
        typemax(Int)

    for price in prices

        m =
            minute_of_day(
                price.timestamp
            )

        distance =
            abs(m - minute)

        if distance < best_distance

            best_distance =
                distance

            best =
                price
        end
    end

    return best.price_per_kwh

end


# ------------------------------------------------------------
# Appliance energy model
# ------------------------------------------------------------

export appliance_energy


function appliance_energy(
    appliance::Appliance
)

    return appliance.energy_kwh > 0 ?
        appliance.energy_kwh :
        appliance.power_kw *
        appliance.runtime_minutes /
        60.0

end


# ------------------------------------------------------------
// Cost function
# ------------------------------------------------------------

export schedule_cost


function schedule_cost(
    appliance::Appliance,
    start_minute::Int,
    prices::Vector{ElectricityPrice}
)

    runtime =
        appliance.runtime_minutes

    energy =
        appliance_energy(
            appliance
        )

    slot_minutes =
        30

    slots =
        max(
            1,
            ceil(
                Int,
                runtime /
                slot_minutes
            )
        )

    total =
        0.0

    for i in 0:(slots - 1)

        minute =
            start_minute +
            i * slot_minutes

        price =
            price_at(
                prices,
                minute
            )

        total +=
            energy /
            slots *
            price
    end

    return total

end


# ------------------------------------------------------------
# Constraint checking
# ------------------------------------------------------------

export valid_start


function valid_start(
    appliance::Appliance,
    start_minute::Int
)

    finish =
        start_minute +
        appliance.runtime_minutes

    return (
        start_minute >=
            appliance.earliest_start
    ) &&
    (
        finish <=
            appliance.latest_finish
    )

end


# ------------------------------------------------------------
# Find cheapest schedule
# ------------------------------------------------------------

export optimise_appliance


function optimise_appliance(
    appliance::Appliance,
    prices::Vector{ElectricityPrice};
    slot_minutes::Int = 15
)

    best_start =
        appliance.earliest_start

    best_cost =
        Inf

    start =
        appliance.earliest_start

    while start <=
          appliance.latest_finish -
          appliance.runtime_minutes

        if valid_start(
            appliance,
            start
        )

            cost =
                schedule_cost(
                    appliance,
                    start,
                    prices
                )

            if cost < best_cost

                best_cost =
                    cost

                best_start =
                    start
            end
        end

        start +=
            slot_minutes
    end

    finish =
        best_start +
        appliance.runtime_minutes

    energy =
        appliance_energy(
            appliance
        )

    return ApplianceSchedule(
        appliance.id,
        best_start,
        finish,
        energy,
        best_cost
    )

end


# ------------------------------------------------------------
# Solar-aware optimisation
# ------------------------------------------------------------

export solar_adjusted_cost


function solar_adjusted_cost(
    appliance::Appliance,
    start_minute::Int,
    prices::Vector{ElectricityPrice},
    solar_forecast::Dict{Int,Float64}
)

    base =
        schedule_cost(
            appliance,
            start_minute,
            prices
        )

    runtime =
        appliance.runtime_minutes

    solar_energy =
        0.0

    for minute in
        start_minute:
        30:
        start_minute +
        runtime

        solar =
            get(
                solar_forecast,
                minute,
                0.0
            )

        solar_energy +=
            min(
                appliance.power_kw,
                solar
            ) *
            (30 / 60)
    end

    avoided =
        solar_energy *
        price_at(
            prices,
            start_minute
        )

    return max(
        0.0,
        base - avoided
    )

end


# ------------------------------------------------------------
# Solar-aware schedule
# ------------------------------------------------------------

export optimise_with_solar


function optimise_with_solar(
    appliance::Appliance,
    prices::Vector{ElectricityPrice},
    solar_forecast::Dict{Int,Float64};
    slot_minutes::Int = 15
)

    best_start =
        appliance.earliest_start

    best_cost =
        Inf

    latest =
        appliance.latest_finish -
        appliance.runtime_minutes

    for start in
        appliance.earliest_start:
        slot_minutes:
        latest

        cost =
            solar_adjusted_cost(
                appliance,
                start,
                prices,
                solar_forecast
            )

        if cost < best_cost

            best_cost =
                cost

            best_start =
                start
        end
    end

    finish =
        best_start +
        appliance.runtime_minutes

    return ApplianceSchedule(
        appliance.id,
        best_start,
        finish,
        appliance_energy(
            appliance
        ),
        best_cost
    )

end


# ------------------------------------------------------------
# Household load coordination
# ------------------------------------------------------------

export simultaneous_power


function simultaneous_power(
    schedules::Vector{ApplianceSchedule},
    appliances::Vector{Appliance}
)

    peak =
        0.0

    for schedule in schedules

        appliance =
            findfirst(
                a ->
                    a.id ==
                    schedule.appliance_id,
                appliances
            )

        appliance === nothing &&
            continue

        power =
            appliances[appliance].power_kw

        peak =
            max(
                peak,
                power
            )
    end

    return peak

end


# ------------------------------------------------------------
# Whole-house scheduling
# ------------------------------------------------------------

export optimise_household


function optimise_household(
    state::ApplianceState,
    prices::Vector{ElectricityPrice};
    solar_forecast =
        Dict{Int,Float64}()
)

    schedules =
        ApplianceSchedule[]

    flexible =
        filter(
            a ->
                a.flexible &&
                a.reachable,
            state.appliances
        )

    # Schedule the most energy-intensive loads first.
    sort!(
        flexible,
        by = a ->
            appliance_energy(a),
        rev = true
    )

    for appliance in flexible

        schedule =
            isempty(
                solar_forecast
            ) ?

            optimise_appliance(
                appliance,
                prices
            ) :

            optimise_with_solar(
                appliance,
                prices,
                solar_forecast
            )

        push!(
            schedules,
            schedule
        )
    end

    return schedules

end


# ------------------------------------------------------------
# Appliance priorities
# ------------------------------------------------------------

export appliance_priority


function appliance_priority(
    appliance::Appliance
)

    priorities = Dict(
        "dishwasher" => 0.8,
        "washingMachine" => 0.7,
        "tumbleDryer" => 0.6,
        "waterHeater" => 0.9,
        "EVCharger" => 1.0,
        "kettle" => 0.2,
        "generic" => 0.5
    )

    return get(
        priorities,
        appliance.appliance_type,
        0.5
    )

end


# ------------------------------------------------------------
# Deadline risk
# ------------------------------------------------------------

export deadline_risk


function deadline_risk(
    appliance::Appliance,
    current_minute::Int
)

    remaining =
        appliance.latest_finish -
        current_minute

    required =
        appliance.runtime_minutes

    if remaining <= required
        return 1.0
    end

    return clamp(
        required / remaining,
        0.0,
        1.0
    )

end


# ------------------------------------------------------------
# Smart scheduling objective
# ------------------------------------------------------------

export intelligent_cost


function intelligent_cost(
    appliance::Appliance,
    start_minute::Int,
    prices::Vector{ElectricityPrice},
    current_minute::Int,
    solar_forecast::Dict{Int,Float64}
)

    energy_cost =
        isempty(solar_forecast) ?

        schedule_cost(
            appliance,
            start_minute,
            prices
        ) :

        solar_adjusted_cost(
            appliance,
            start_minute,
            prices,
            solar_forecast
        )

    deadline =
        deadline_risk(
            appliance,
            current_minute
        )

    priority =
        appliance_priority(
            appliance
        )

    delay_penalty =
        deadline *
        priority *
        0.10

    return energy_cost +
           delay_penalty

end


# ------------------------------------------------------------
# Advanced optimiser
# ------------------------------------------------------------

export intelligent_schedule


function intelligent_schedule(
    appliance::Appliance,
    prices::Vector{ElectricityPrice},
    current_minute::Int;
    solar_forecast =
        Dict{Int,Float64}(),
    slot_minutes::Int = 15
)

    latest =
        appliance.latest_finish -
        appliance.runtime_minutes

    best_start =
        appliance.earliest_start

    best_cost =
        Inf

    for start in
        appliance.earliest_start:
        slot_minutes:
        latest

        if start < current_minute
            continue
        end

        cost =
            intelligent_cost(
                appliance,
                start,
                prices,
                current_minute,
                solar_forecast
            )

        if cost < best_cost

            best_cost =
                cost

            best_start =
                start
        end
    end

    return ApplianceSchedule(
        appliance.id,
        best_start,
        best_start +
            appliance.runtime_minutes,
        appliance_energy(
            appliance
        ),
        best_cost
    )

end


# ------------------------------------------------------------
# Julia → Swift policy
# ------------------------------------------------------------

export create_appliance_policy


function create_appliance_policy(
    state::ApplianceState,
    prices::Vector{ElectricityPrice},
    current_minute::Int;
    solar_forecast =
        Dict{Int,Float64}()
)

    schedules =
        ApplianceSchedule[]

    actions =
        ApplianceAction[]

    for appliance
        in state.appliances

        if !appliance.flexible ||
           !appliance.reachable

            continue
        end

        schedule =
            intelligent_schedule(
                appliance,
                prices,
                current_minute;
                solar_forecast =
                    solar_forecast
            )

        push!(
            schedules,
            schedule
        )

        reason =
            "Scheduled for the lowest expected household energy cost within the permitted operating window."

        push!(
            actions,
            ApplianceAction(
                appliance.id,
                "schedule",
                schedule.start_minute,
                schedule.finish_minute,
                reason
            )
        )
    end

    return AppliancePolicy(
        schedules,
        actions
    )

end


# ------------------------------------------------------------
# Human preference layer
# ------------------------------------------------------------

export apply_user_preference


function apply_user_preference(
    schedule::ApplianceSchedule,
    preferred_start::Union{Int,Nothing},
    flexibility_minutes::Int
)

    preferred_start === nothing &&
        return schedule

    difference =
        abs(
            schedule.start_minute -
            preferred_start
        )

    if difference <=
       flexibility_minutes

        return ApplianceSchedule(
            schedule.appliance_id,
            preferred_start,
            preferred_start +
                (
                    schedule.finish_minute -
                    schedule.start_minute
                ),
            schedule.expected_energy_kwh,
            schedule.expected_cost
        )
    end

    return schedule

end


# ------------------------------------------------------------
# Example appliance presets
# ------------------------------------------------------------

export default_appliance_constraints


function default_appliance_constraints(
    appliance_type::String
)

    if appliance_type ==
       "dishwasher"

        return (
            runtime = 120,
            earliest = 0,
            latest = 1440
        )

    elseif appliance_type ==
           "washingMachine"

        return (
            runtime = 90,
            earliest = 0,
            latest = 1440
        )

    elseif appliance_type ==
           "tumbleDryer"

        return (
            runtime = 90,
            earliest = 0,
            latest = 1440
        )

    elseif appliance_type ==
           "EVCharger"

        return (
            runtime = 360,
            earliest = 0,
            latest = 1440
        )

    elseif appliance_type ==
           "waterHeater"

        return (
            runtime = 120,
            earliest = 0,
            latest = 1440
        )

    else

        return (
            runtime = 30,
            earliest = 0,
            latest = 1440
        )
    end

end


end





# ============================================================
# JSON output
# ============================================================

using JSON3

function appliance_policy_to_json(
    policy::AppliancePolicy
)

    schedules = [
        Dict(
            "appliance_id" =>
                schedule.appliance_id,

            "start_minute" =>
                schedule.start_minute,

            "finish_minute" =>
                schedule.finish_minute,

            "expected_energy_kwh" =>
                schedule.expected_energy_kwh,

            "expected_cost" =>
                schedule.expected_cost
        )
        for schedule in
            policy.schedules
    ]

    actions = [
        Dict(
            "appliance_id" =>
                action.appliance_id,

            "action_type" =>
                action.action_type,

            "scheduled_start" =>
                action.scheduled_start,

            "scheduled_finish" =>
                action.scheduled_finish,

            "reason" =>
                action.reason
        )
        for action in
            policy.actions
    ]

    return JSON3.write(
        Dict(
            "schedules" => schedules,
            "actions" => actions
        )
    )

end



# ============================================================
# Example #7
# ============================================================

using Dates

include("ApplianceScheduling.jl")

using .ApplianceScheduling

appliances = Appliance[
    Appliance(
        "dishwasher-01",
        "Kitchen Dishwasher",
        "Kitchen",
        "dishwasher",
        false,
        true,
        1.2,
        1.8,
        true,
        120,
        60,
        1320
    ),

    Appliance(
        "washer-01",
        "Washing Machine",
        "Utility Room",
        "washingMachine",
        false,
        true,
        0.8,
        1.0,
        true,
        90,
        480,
        1320
    ),

    Appliance(
        "ev-01",
        "EV Charger",
        "Driveway",
        "EVCharger",
        false,
        true,
        7.0,
        35.0,
        true,
        300,
        1080,
        420
    )
]

state =
    ApplianceState(
        DateTime(
            2026,
            10,
            8,
            18,
            30
        ),
        appliances
    )

prices = ElectricityPrice[]

for minute in 0:30:1410

    hour_value =
        minute / 60

    price =
        if hour_value >= 17 &&
           hour_value <= 20

            0.34

        elseif hour_value >= 0 &&
               hour_value <= 6

            0.16

        else

            0.24
        end

    push!(
        prices,
        ElectricityPrice(
            DateTime(
                2026,
                10,
                8
            ) +
            Minute(minute),
            price
        )
    )
end

solar =
    Dict{Int,Float64}(
        600 => 1.5,
        630 => 2.0,
        660 => 2.5,
        690 => 3.0,
        720 => 3.5,
        750 => 3.2,
        780 => 2.8,
        810 => 2.0,
        840 => 1.2
    )

policy =
    create_appliance_policy(
        state,
        prices,
        1110;
        solar_forecast = solar
    )

println(
    appliance_policy_to_json(
        policy
    )
)



// ============================================================
// Swift scheduling bridge
// ============================================================

import Foundation

struct ApplianceJSONBridge {

    static func encode(
        _ snapshot: ApplianceSnapshot
    ) throws -> Data {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        encoder.outputFormatting = [
            .sortedKeys
        ]

        return try encoder.encode(
            snapshot
        )
    }

    static func decodeCommands(
        _ data: Data
    ) throws -> [ApplianceCommand] {

        let decoder = JSONDecoder()

        return try decoder.decode(
            [ApplianceCommand].self,
            from: data
        )
    }
}


// ============================================================
// #8 WHOLE-HOME DIGITAL TWIN
// Swift / HomeKit State + Visualisation Layer
// ============================================================

// ------------------------------------------------------------
// DigitalTwinModel.swift
// ------------------------------------------------------------

import Foundation
import HomeKit

struct TwinRoom: Codable, Identifiable {
    let id: UUID
    let name: String

    let temperature: Double?
    let humidity: Double?
    let occupancy: Bool

    let lightingLevel: Double?
    let heatingActive: Bool

    let applianceCount: Int
    let securityState: String
}

struct TwinDevice: Codable, Identifiable {
    let id: UUID

    let name: String
    let room: String
    let category: String

    let reachable: Bool
    let isOn: Bool

    let powerWatts: Double?
    let temperature: Double?
}

struct TwinEnergyState: Codable {
    let householdPowerWatts: Double
    let gridPowerWatts: Double
    let solarPowerWatts: Double
    let batteryPowerWatts: Double

    let batteryStateOfCharge: Double
}

struct WholeHomeDigitalTwin: Codable {

    let timestamp: Date

    let homeName: String

    let rooms: [TwinRoom]
    let devices: [TwinDevice]

    let energy: TwinEnergyState

    let heatingSnapshot: HeatingSnapshot?
    let lightingSnapshot: LightingSnapshot?
    let securitySnapshot: SecuritySnapshot?
    let applianceSnapshot: ApplianceSnapshot?
}




// ------------------------------------------------------------
// DigitalTwinManager.swift
// ------------------------------------------------------------

import Foundation
import HomeKit

@MainActor
final class DigitalTwinManager: ObservableObject {

    private let homeManager: HomeManager

    private let heatingManager:
        HeatingManager

    private let lightingManager:
        LightingManager

    private let securityManager:
        SecurityManager

    private let applianceManager:
        ApplianceManager

    @Published private(set) var twin:
        WholeHomeDigitalTwin?

    init(
        homeManager: HomeManager,
        heatingManager: HeatingManager,
        lightingManager: LightingManager,
        securityManager: SecurityManager,
        applianceManager: ApplianceManager
    ) {

        self.homeManager =
            homeManager

        self.heatingManager =
            heatingManager

        self.lightingManager =
            lightingManager

        self.securityManager =
            securityManager

        self.applianceManager =
            applianceManager
    }

    // --------------------------------------------------------
    // Build complete twin
    // --------------------------------------------------------

    func buildTwin(
        homeOccupied: Bool,
        homeMode: String
    ) async throws
        -> WholeHomeDigitalTwin {

        let heating =
            try await heatingManager.snapshot()

        let lighting =
            try await lightingManager.snapshot()

        let security =
            try await securityManager.snapshot(
                homeOccupied: homeOccupied,
                homeMode: homeMode
            )

        let appliances =
            try await applianceManager.snapshot()

        var rooms:
            [TwinRoom] = []

        var devices:
            [TwinDevice] = []

        let home =
            homeManager.primaryHome()

        // ----------------------------------------------------
        // Build device model
        // ----------------------------------------------------

        if let home {

            for accessory
                in home.accessories {

                let room =
                    accessory.room?.name ??
                    "Unknown"

                let reachable =
                    accessory.isReachable

                let switchService =
                    accessory.services.first {
                        $0.serviceType ==
                        HMServiceTypeSwitch ||
                        $0.serviceType ==
                        HMServiceTypeOutlet
                    }

                let power =
                    switchService?
                        .characteristics
                        .first {
                            $0.characteristicType ==
                            HMCharacteristicTypePowerState
                        }?
                        .value as? Bool

                devices.append(
                    TwinDevice(
                        id:
                            accessory.uniqueIdentifier,

                        name:
                            accessory.name,

                        room:
                            room,

                        category:
                            accessory.category.categoryType,

                        reachable:
                            reachable,

                        isOn:
                            power ?? false,

                        powerWatts:
                            nil,

                        temperature:
                            nil
                    )
                )
            }
        }

        // ----------------------------------------------------
        // Build room model
        // ----------------------------------------------------

        let roomNames =
            Set(
                devices.map {
                    $0.room
                }
            )

        for roomName in roomNames {

            let roomDevices =
                devices.filter {
                    $0.room == roomName
                }

            let heatingZone =
                heating.zones.first {
                    $0.room == roomName
                }

            let lightingZone =
                lighting.zones.first {
                    $0.room == roomName
                }

            let occupied =
                security.sensors.contains {
                    $0.room == roomName &&
                    $0.triggered
                }

            rooms.append(
                TwinRoom(
                    id: UUID(),
                    name: roomName,

                    temperature:
                        heatingZone?
                        .currentTemperature,

                    humidity:
                        heatingZone?
                        .humidity,

                    occupancy:
                        occupied,

                    lightingLevel:
                        lightingZone?
                        .brightness,

                    heatingActive:
                        heatingZone?
                        .heatingActive,

                    applianceCount:
                        roomDevices.filter {
                            applianceManager
                                .discoverAppliances()
                                .contains {
                                    $0.uniqueIdentifier ==
                                    $0.id
                                }
                        }.count,

                    securityState:
                        occupied
                        ? "active"
                        : "quiet"
                )
            )
        }

        let energy =
            TwinEnergyState(
                householdPowerWatts: 0,
                gridPowerWatts: 0,
                solarPowerWatts: 0,
                batteryPowerWatts: 0,
                batteryStateOfCharge: 0
            )

        let result =
            WholeHomeDigitalTwin(
                timestamp: Date(),

                homeName:
                    home?.name ??
                    "Home",

                rooms:
                    rooms.sorted {
                        $0.name < $1.name
                    },

                devices:
                    devices.sorted {
                        $0.name < $1.name
                    },

                energy:
                    energy,

                heatingSnapshot:
                    heating,

                lightingSnapshot:
                    lighting,

                securitySnapshot:
                    security,

                applianceSnapshot:
                    appliances
            )

        twin = result

        return result
    }

    // --------------------------------------------------------
    // JSON export
    // --------------------------------------------------------

    func encodeTwin()
        throws -> Data {

        guard let twin else {
            throw DigitalTwinError
                .twinUnavailable
        }

        let encoder =
            JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        encoder.outputFormatting = [
            .prettyPrinted,
            .sortedKeys
        ]

        return try encoder.encode(
            twin
        )
    }
}

enum DigitalTwinError: Error {
    case twinUnavailable
}





// ============================================================
// #8 DIGITAL TWIN SIMULATION INTERFACE
// Swift
// ============================================================

import Foundation

struct TwinSimulationRequest: Codable {

    let heatingTargets:
        [UUID: Double]

    let lightingLevels:
        [UUID: Double]

    let applianceStates:
        [UUID: Bool]

    let simulationMinutes: Int
}


struct TwinSimulationResult: Codable {

    let startingTimestamp: Date
    let endingTimestamp: Date

    let temperatures:
        [UUID: [Double]]

    let energyConsumptionKWh:
        Double

    let estimatedEnergyCost:
        Double

    let comfortScore:
        Double
}



// ------------------------------------------------------------
// DigitalTwinJSON.swift
// ------------------------------------------------------------

import Foundation

struct DigitalTwinJSON {

    static func encode(
        _ twin: WholeHomeDigitalTwin
    ) throws -> Data {

        let encoder =
            JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        encoder.outputFormatting = [
            .prettyPrinted,
            .sortedKeys
        ]

        return try encoder.encode(
            twin
        )
    }

    static func decodeSimulation(
        _ data: Data
    ) throws
        -> TwinSimulationRequest {

        let decoder =
            JSONDecoder()

        return try decoder.decode(
            TwinSimulationRequest.self,
            from: data
        )
    }
}



# ============================================================
# #8 WHOLE-HOME DIGITAL TWIN
# Julia Simulation + Optimisation Engine
# ============================================================

module WholeHomeTwin

using Dates
using Statistics

export TwinRoom
export TwinDevice
export TwinEnergy
export TwinState
export TwinParameters
export TwinSimulation
export TwinResult


# ------------------------------------------------------------
# TwinTypes.jl
# ------------------------------------------------------------

struct TwinRoom

    id::String
    name::String

    temperature::Float64
    humidity::Float64

    occupancy::Bool

    lighting_level::Float64
    heating_active::Bool

end


struct TwinDevice

    id::String
    name::String
    room::String
    category::String

    reachable::Bool
    is_on::Bool

    power_watts::Float64

end


struct TwinEnergy

    household_power_watts::Float64
    grid_power_watts::Float64
    solar_power_watts::Float64

    battery_power_watts::Float64
    battery_soc::Float64

end


struct TwinState

    timestamp::DateTime

    rooms::Vector{TwinRoom}
    devices::Vector{TwinDevice}

    energy::TwinEnergy

end


struct TwinParameters

    thermal_loss::Float64
    thermal_gain::Float64

    lighting_power_per_percent::Float64

    solar_generation_kw::Float64

    electricity_price::Float64

end


struct TwinSimulation

    heating_targets::Dict{String,Float64}

    lighting_levels::Dict{String,Float64}

    appliance_states::Dict{String,Bool}

    simulation_minutes::Int

end


struct TwinResult

    starting_timestamp::DateTime
    ending_timestamp::DateTime

    temperatures::Dict{
        String,
        Vector{Float64}
    }

    energy_consumption_kwh::Float64
    estimated_energy_cost::Float64

    comfort_score::Float64

end


# ------------------------------------------------------------
# Thermal model
# ------------------------------------------------------------

export next_temperature


function next_temperature(
    current_temperature::Float64,
    outdoor_temperature::Float64,
    heating_power::Float64,
    parameters::TwinParameters,
    minutes::Int
)

    dt =
        minutes / 60.0

    thermal_loss =
        parameters.thermal_loss *
        (
            outdoor_temperature -
            current_temperature
        )

    thermal_gain =
        parameters.thermal_gain *
        heating_power

    return current_temperature +
           (
               thermal_loss +
               thermal_gain
           ) *
           dt

end


# ------------------------------------------------------------
# Occupancy heat gains
# ------------------------------------------------------------

export occupancy_heat_gain


function occupancy_heat_gain(
    occupied::Bool
)

    return occupied ?
        0.15 :
        0.0

end


# ------------------------------------------------------------
# Lighting model
# ------------------------------------------------------------

export lighting_power


function lighting_power(
    brightness::Float64,
    parameters::TwinParameters
)

    return (
        brightness / 100.0
    ) *
    parameters.lighting_power_per_percent

end


# ------------------------------------------------------------
# Appliance power
# ------------------------------------------------------------

export appliance_power


function appliance_power(
    device::TwinDevice,
    enabled::Bool
)

    if !enabled
        return 0.0
    end

    if device.power_watts > 0
        return device.power_watts
    end

    category =
        lowercase(
            device.category
        )

    if occursin(
        "dishwasher",
        category
    )
        return 1200.0

    elseif occursin(
        "washer",
        category
    )
        return 800.0

    elseif occursin(
        "dryer",
        category
    )
        return 2000.0

    elseif occursin(
        "heater",
        category
    )
        return 2000.0

    end

    return 500.0

end


# ------------------------------------------------------------
# Heating energy
# ------------------------------------------------------------

export heating_power


function heating_power(
    target::Float64,
    current::Float64
)

    difference =
        target -
        current

    if difference <= 0
        return 0.0
    end

    return clamp(
        difference /
        3.0,
        0.0,
        1.0
    )

end


# ------------------------------------------------------------
# Simulate room
# ------------------------------------------------------------

export simulate_room


function simulate_room(
    room::TwinRoom,
    target::Float64,
    outdoor_temperature::Float64,
    parameters::TwinParameters,
    minutes::Int
)

    current =
        room.temperature

    values =
        Float64[current]

    steps =
        max(
            1,
            Int(
                ceil(
                    minutes /
                    15
                )
            )
        )

    for _ in 1:steps

        heat =
            heating_power(
                target,
                current
            )

        heat +=
            occupancy_heat_gain(
                room.occupancy
            )

        current =
            next_temperature(
                current,
                outdoor_temperature,
                heat,
                parameters,
                15
            )

        push!(
            values,
            current
        )
    end

    return values

end


# ------------------------------------------------------------
# Comfort score
# ------------------------------------------------------------

export comfort_score


function comfort_score(
    temperatures::Vector{Float64},
    target::Float64
)

    if isempty(temperatures)
        return 0.0
    end

    errors =
        abs.(
            temperatures .-
            target
        )

    mean_error =
        mean(errors)

    return clamp(
        1.0 -
        mean_error /
        5.0,
        0.0,
        1.0
    )

end


# ------------------------------------------------------------
# Whole-home energy simulation
# ------------------------------------------------------------

export simulate_home


function simulate_home(
    state::TwinState,
    simulation::TwinSimulation,
    parameters::TwinParameters;
    outdoor_temperature::Float64 = 10.0
)

    temperatures =
        Dict{
            String,
            Vector{Float64}
        }()

    total_energy =
        0.0

    comfort_values =
        Float64[]

    # --------------------------------------------------------
    # Rooms
    # --------------------------------------------------------

    for room in state.rooms

        target =
            get(
                simulation.heating_targets,
                room.id,
                room.temperature
            )

        values =
            simulate_room(
                room,
                target,
                outdoor_temperature,
                parameters,
                simulation.simulation_minutes
            )

        temperatures[
            room.id
        ] = values

        push!(
            comfort_values,
            comfort_score(
                values,
                target
            )
        )

        heating_energy =
            sum(
                max.(
                    values .-
                    room.temperature,
                    0
                )
            )

        total_energy +=
            heating_energy *
            0.01
    end

    # --------------------------------------------------------
    # Lighting
    # --------------------------------------------------------

    for room in state.rooms

        brightness =
            get(
                simulation.lighting_levels,
                room.id,
                room.lighting_level
            )

        power =
            lighting_power(
                brightness,
                parameters
            )

        hours =
            simulation.simulation_minutes /
            60.0

        total_energy +=
            power *
            hours /
            1000.0
    end

    # --------------------------------------------------------
    # Appliances
    # --------------------------------------------------------

    for device in state.devices

        enabled =
            get(
                simulation.appliance_states,
                device.id,
                device.is_on
            )

        power =
            appliance_power(
                device,
                enabled
            )

        hours =
            simulation.simulation_minutes /
            60.0

        total_energy +=
            power *
            hours /
            1000.0
    end

    cost =
        total_energy *
        parameters.electricity_price

    average_comfort =
        isempty(
            comfort_values
        ) ?
        1.0 :
        mean(
            comfort_values
        )

    ending =
        state.timestamp +
        Minute(
            simulation.simulation_minutes
        )

    return TwinResult(
        state.timestamp,
        ending,
        temperatures,
        total_energy,
        cost,
        average_comfort
    )

end


# ------------------------------------------------------------
# Scenario generation
# ------------------------------------------------------------

export scenario


function scenario(
    state::TwinState;
    heating_delta::Float64 = 0.0,
    lighting_delta::Float64 = 0.0
)

    heating =
        Dict{
            String,
            Float64
        }()

    lighting =
        Dict{
            String,
            Float64
        }()

    for room in state.rooms

        heating[
            room.id
        ] =
            room.temperature +
            1.0 +
            heating_delta

        lighting[
            room.id
        ] =
            clamp(
                room.lighting_level +
                lighting_delta,
                0.0,
                100.0
            )
    end

    appliances =
        Dict{
            String,
            Bool
        }()

    for device in state.devices

        appliances[
            device.id
        ] =
            device.is_on
    end

    return TwinSimulation(
        heating,
        lighting,
        appliances,
        60
    )

end


# ------------------------------------------------------------
# Scenario comparison
# ------------------------------------------------------------

export compare_scenarios


function compare_scenarios(
    state::TwinState,
    scenarios::Vector{TwinSimulation},
    parameters::TwinParameters
)

    results =
        TwinResult[]

    for simulation in scenarios

        result =
            simulate_home(
                state,
                simulation,
                parameters
            )

        push!(
            results,
            result
        )
    end

    return results

end


# ------------------------------------------------------------
# Optimisation objective
# ------------------------------------------------------------

export twin_objective


function twin_objective(
    result::TwinResult
)

    energy_penalty =
        result.energy_consumption_kwh

    comfort_penalty =
        (
            1.0 -
            result.comfort_score
        ) *
        10.0

    return energy_penalty +
           comfort_penalty

end


# ------------------------------------------------------------
# Whole-home optimisation
# ------------------------------------------------------------

export optimise_twin


function optimise_twin(
    state::TwinState,
    parameters::TwinParameters
)

    candidates =
        TwinSimulation[]

    for heating_delta in
        -1.0:0.5:2.0

        for lighting_delta in
            -20.0:10.0:10.0

            push!(
                candidates,
                scenario(
                    state;
                    heating_delta =
                        heating_delta,
                    lighting_delta =
                        lighting_delta
                )
            )
        end
    end

    results =
        compare_scenarios(
            state,
            candidates,
            parameters
        )

    scores =
        twin_objective.(
            results
        )

    index =
        argmin(scores)

    return (
        simulation =
            candidates[index],
        result =
            results[index]
    )

end


# ------------------------------------------------------------
# Digital twin forecasting
# ------------------------------------------------------------

export forecast_home


function forecast_home(
    state::TwinState,
    parameters::TwinParameters,
    horizon_minutes::Int;
    outdoor_temperature::Float64 = 10.0
)

    simulation =
        TwinSimulation(
            Dict(
                room.id =>
                    room.temperature + 1.0
                for room in state.rooms
            ),

            Dict(
                room.id =>
                    room.lighting_level
                for room in state.rooms
            ),

            Dict(
                device.id =>
                    device.is_on
                for device in state.devices
            ),

            horizon_minutes
        )

    return simulate_home(
        state,
        simulation,
        parameters;
        outdoor_temperature =
            outdoor_temperature
    )

end


# ------------------------------------------------------------
# Sensitivity analysis
# ------------------------------------------------------------

export sensitivity_analysis


function sensitivity_analysis(
    state::TwinState,
    parameters::TwinParameters
)

    results =
        Dict{String,Float64}()

    baseline =
        forecast_home(
            state,
            parameters,
            120
        )

    results[
        "baseline_energy"
    ] =
        baseline.energy_consumption_kwh

    colder =
        forecast_home(
            state,
            parameters,
            120;
            outdoor_temperature = 5.0
        )

    results[
        "cold_weather_energy"
    ] =
        colder.energy_consumption_kwh

    warmer =
        forecast_home(
            state,
            parameters,
            120;
            outdoor_temperature = 15.0
        )

    results[
        "warm_weather_energy"
    ] =
        warmer.energy_consumption_kwh

    return results

end


end


# ============================================================
# Digital Twin JSON Interface
# ============================================================

using JSON3
using Dates

function twin_result_to_json(
    result::TwinResult
)

    temperatures =
        Dict(
            id => values
            for (
                id,
                values
            ) in result.temperatures
        )

    return JSON3.write(
        Dict(
            "starting_timestamp" =>
                string(
                    result.starting_timestamp
                ),

            "ending_timestamp" =>
                string(
                    result.ending_timestamp
                ),

            "temperatures" =>
                temperatures,

            "energy_consumption_kwh" =>
                result.energy_consumption_kwh,

            "estimated_energy_cost" =>
                result.estimated_energy_cost,

            "comfort_score" =>
                result.comfort_score
        )
    )

end








# ============================================================
# Example Whole-Home Digital Twin
# ============================================================

using Dates

include("WholeHomeTwin.jl")

using .WholeHomeTwin

rooms = TwinRoom[
    TwinRoom(
        "living-room",
        "Living Room",
        19.5,
        48.0,
        true,
        65.0,
        true
    ),

    TwinRoom(
        "kitchen",
        "Kitchen",
        20.0,
        51.0,
        true,
        70.0,
        false
    ),

    TwinRoom(
        "bedroom",
        "Bedroom",
        17.5,
        55.0,
        false,
        10.0,
        false
    )
]

devices = TwinDevice[
    TwinDevice(
        "dishwasher",
        "Dishwasher",
        "Kitchen",
        "dishwasher",
        true,
        false,
        1200.0
    ),

    TwinDevice(
        "washing-machine",
        "Washing Machine",
        "Utility",
        "washingMachine",
        true,
        false,
        800.0
    ),

    TwinDevice(
        "tv",
        "Television",
        "Living Room",
        "media",
        true,
        true,
        120.0
    )
]

energy =
    TwinEnergy(
        1850.0,
        1500.0,
        0.0,
        0.0,
        0.54
    )

state =
    TwinState(
        DateTime(
            2026,
            10,
            8,
            19,
            0
        ),
        rooms,
        devices,
        energy
    )

parameters =
    TwinParameters(
        0.08,
        0.8,
        0.8,
        0.0,
        0.31
    )

forecast =
    forecast_home(
        state,
        parameters,
        240;
        outdoor_temperature = 9.0
    )

println(
    twin_result_to_json(
        forecast
    )
)

# ------------------------------------------------------------
# Find the best whole-home scenario
# ------------------------------------------------------------

optimised =
    optimise_twin(
        state,
        parameters
    )

println(
    "Optimal energy: ",
    optimised.result
        .energy_consumption_kwh,
    " kWh"
)

println(
    "Comfort: ",
    optimised.result
        .comfort_score
)

println(
    "Cost: £",
    optimised.result
        .estimated_energy_cost
)





# ============================================================
# Advanced Digital Twin Controller
# Combines #2 + #3 + #4 + #5 + #7
# ============================================================

function whole_home_control_loop(
    state::TwinState,
    parameters::TwinParameters;
    horizon_minutes::Int = 240
)

    forecast =
        forecast_home(
            state,
            parameters,
            horizon_minutes
        )

    baseline_cost =
        forecast.estimated_energy_cost

    baseline_comfort =
        forecast.comfort_score

    candidate =
        optimise_twin(
            state,
            parameters
        )

    optimised_cost =
        candidate.result
            .estimated_energy_cost

    optimised_comfort =
        candidate.result
            .comfort_score

    return Dict(
        "baseline_cost" =>
            baseline_cost,

        "optimised_cost" =>
            optimised_cost,

        "baseline_comfort" =>
            baseline_comfort,

        "optimised_comfort" =>
            optimised_comfort,

        "energy_saved_kwh" =>
            max(
                0.0,
                forecast
                    .energy_consumption_kwh -
                candidate.result
                    .energy_consumption_kwh
            ),

        "recommended_simulation" =>
            candidate.simulation
    )

end





// ============================================================
// Swift Digital Twin Coordinator
// ============================================================

import Foundation

@MainActor
final class WholeHomeCoordinator {

    private let twinManager:
        DigitalTwinManager

    init(
        twinManager: DigitalTwinManager
    ) {
        self.twinManager =
            twinManager
    }

    func refresh(
        homeOccupied: Bool,
        homeMode: String
    ) async throws {

        _ = try await
            twinManager.buildTwin(
                homeOccupied:
                    homeOccupied,
                homeMode:
                    homeMode
            )
    }

    func exportState()
        throws -> Data {

        return try
            twinManager.encodeTwin()
    }
}





# ============================================================
# Final Julia Digital Twin API
# ============================================================

function run_digital_twin(
    state::TwinState,
    parameters::TwinParameters;
    horizon_minutes::Int = 240
)

    baseline =
        forecast_home(
            state,
            parameters,
            horizon_minutes
        )

    optimal =
        optimise_twin(
            state,
            parameters
        )

    return Dict(
        "baseline" => baseline,
        "optimal" => optimal.result,
        "recommended_scenario" =>
            optimal.simulation,
        "sensitivity" =>
            sensitivity_analysis(
                state,
                parameters
            )
    )

end










#8 — Whole-Home Digital Twin
Architecture
                    APPLE HOME / HOMEKIT
                           │
                           ▼
                    ┌──────────────┐
                    │ Swift Layer  │
                    │              │
                    │ Live Home    │
                    │ State        │
                    │ Sensors      │
                    │ Devices      │
                    │ Permissions  │
                    └──────┬───────┘
                           │ JSON / IPC
                           ▼
                 ┌────────────────────┐
                 │    Julia Engine    │
                 │                    │
                 │  Whole-Home Twin   │
                 │                    │
                 │  Thermal model      │
                 │  Energy model      │
                 │  Occupancy model   │
                 │  Lighting model    │
                 │  Appliance model   │
                 │  Security state    │
                 │                    │
                 │  Simulation        │
                 │       ↓            │
                 │  Optimisation      │
                 └─────────┬──────────┘
                           │
                    Proposed policy
                           │
                           ▼
                    ┌──────────────┐
                    │ Swift Layer  │
                    │ Validate     │
                    │ Execute      │
                    └──────────────┘

The key idea is that Julia doesn't merely ask "what should I turn on?" It asks:
"What will happen to the whole house over the next six hours if I do this?"

1. Swift — Digital Twin Model
import Foundation

struct TwinRoom: Codable, Identifiable {
    let id: UUID
    let name: String

    var temperature: Double?
    var humidity: Double?

    var occupied: Bool

    var lightingLevel: Double
    var heatingActive: Bool

    var applianceCount: Int
    var securityState: String
}

struct TwinDevice: Codable, Identifiable {
    let id: UUID
    let name: String
    let room: String

    let category: String

    var reachable: Bool
    var isOn: Bool

    var powerWatts: Double
    var temperature: Double?
}

struct TwinEnergyState: Codable {
    var householdPowerWatts: Double
    var gridPowerWatts: Double
    var solarPowerWatts: Double

    var batteryPowerWatts: Double
    var batteryStateOfCharge: Double
}

struct WholeHomeDigitalTwin: Codable {

    let timestamp: Date
    let homeName: String

    var rooms: [TwinRoom]
    var devices: [TwinDevice]

    var energy: TwinEnergyState

    var homeOccupied: Bool
    var homeMode: String
}

2. Swift — Twin Manager
This converts the real Apple Home into a clean model that Julia can understand.
import Foundation
import HomeKit

@MainActor
final class DigitalTwinManager: ObservableObject {

    private let homeManager: HomeManager
    private let heatingManager: HeatingManager
    private let lightingManager: LightingManager
    private let securityManager: SecurityManager
    private let applianceManager: ApplianceManager

    @Published private(set) var twin: WholeHomeDigitalTwin?

    init(
        homeManager: HomeManager,
        heatingManager: HeatingManager,
        lightingManager: LightingManager,
        securityManager: SecurityManager,
        applianceManager: ApplianceManager
    ) {
        self.homeManager = homeManager
        self.heatingManager = heatingManager
        self.lightingManager = lightingManager
        self.securityManager = securityManager
        self.applianceManager = applianceManager
    }

    func rebuild(
        homeOccupied: Bool,
        homeMode: String
    ) async throws -> WholeHomeDigitalTwin {

        guard let home = homeManager.primaryHome else {
            throw DigitalTwinError.noHome
        }

        let heating = await heatingManager.snapshot()
        let lighting = await lightingManager.snapshot()
        let security = await securityManager.snapshot()
        let appliances = await applianceManager.snapshot()

        var devices: [TwinDevice] = []

        for accessory in home.accessories {

            let room = accessory.room?.name ?? "Unknown"

            let powerService = accessory.services.first {
                $0.serviceType == HMServiceTypeSwitch
            }

            var isOn = false

            if let characteristic = powerService?.characteristics.first(
                where: {
                    $0.characteristicType == HMCharacteristicTypePowerState
                }
            ) {
                isOn = (characteristic.value as? Bool) ?? false
            }

            let device = TwinDevice(
                id: accessory.uniqueIdentifier,
                name: accessory.name,
                room: room,
                category: categoryName(accessory.category),
                reachable: accessory.isReachable,
                isOn: isOn,
                powerWatts: 0,
                temperature: nil
            )

            devices.append(device)
        }

        let rooms = buildRooms(
            home: home,
            devices: devices,
            heating: heating,
            lighting: lighting,
            security: security,
            appliances: appliances
        )

        let energy = TwinEnergyState(
            householdPowerWatts: 0,
            gridPowerWatts: 0,
            solarPowerWatts: 0,
            batteryPowerWatts: 0,
            batteryStateOfCharge: 0
        )

        let result = WholeHomeDigitalTwin(
            timestamp: Date(),
            homeName: home.name,
            rooms: rooms,
            devices: devices,
            energy: energy,
            homeOccupied: homeOccupied,
            homeMode: homeMode
        )

        self.twin = result

        return result
    }

    private func buildRooms(
        home: HMHome,
        devices: [TwinDevice],
        heating: HeatingSnapshot?,
        lighting: LightingSnapshot?,
        security: SecuritySnapshot?,
        appliances: ApplianceSnapshot?
    ) -> [TwinRoom] {

        let roomNames = Set(
            devices.map { $0.room }
        )

        return roomNames.map { roomName in

            let roomDevices = devices.filter {
                $0.room == roomName
            }

            let heatingZone = heating?.zones.first {
                $0.room == roomName
            }

            let lightingZone = lighting?.zones.first {
                $0.room == roomName
            }

            let securitySensors = security?.sensors.filter {
                $0.room == roomName
            } ?? []

            let occupied = securitySensors.contains {
                $0.triggered
            }

            let heatingActive =
                heatingZone?.heatingActive ?? false

            let temperature =
                heatingZone?.currentTemperature

            let humidity =
                heatingZone?.humidity

            let lightingLevel =
                lightingZone?.brightness ?? 0

            let applianceIDs = Set(
                appliances?.appliances
                    .filter { $0.room == roomName }
                    .map { $0.id } ?? []
            )

            let applianceCount = roomDevices.filter {
                applianceIDs.contains($0.id)
            }.count

            let securityState =
                occupied ? "occupied" : "clear"

            return TwinRoom(
                id: UUID(),
                name: roomName,
                temperature: temperature,
                humidity: humidity,
                occupied: occupied,
                lightingLevel: lightingLevel,
                heatingActive: heatingActive,
                applianceCount: applianceCount,
                securityState: securityState
            )
        }
    }

    private func categoryName(
        _ category: HMAccessoryCategory
    ) -> String {

        return category.localizedDescription
    }
}

enum DigitalTwinError: Error {
    case noHome
}

3. Swift — Simulation Request
Julia shouldn't receive the entire HomeKit world every time it wants to test something.
Give it a clean simulation interface.
struct TwinSimulationRequest: Codable {

    let horizonMinutes: Int
    let timestepMinutes: Int

    let heatingTargets: [String: Double]

    let lightingLevels: [String: Double]

    let applianceStates: [UUID: Bool]

    let batteryTargetSOC: Double?
}

And the result:
struct TwinSimulationResult: Codable {

    let energyKWh: Double

    let peakPowerWatts: Double

    let comfortScore: Double

    let minimumTemperature: Double

    let maximumTemperature: Double

    let batteryFinalSOC: Double

    let feasible: Bool

    let explanation: String
}

4. Swift — JSON Bridge
enum DigitalTwinJSON {

    static func encode(
        _ twin: WholeHomeDigitalTwin
    ) throws -> Data {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [
            .prettyPrinted,
            .sortedKeys
        ]

        return try encoder.encode(twin)
    }

    static func decode(
        _ data: Data
    ) throws -> WholeHomeDigitalTwin {

        let decoder = JSONDecoder()

        decoder.dateDecodingStrategy = .iso8601

        return try decoder.decode(
            WholeHomeDigitalTwin.self,
            from: data
        )
    }
}

5. Julia — Digital Twin
Now Julia gets the interesting part.
module WholeHomeTwin

using Dates
using JSON3
using Statistics

export TwinRoom
export TwinDevice
export TwinEnergy
export TwinState
export TwinParameters
export TwinResult

struct TwinRoom
    id::String
    name::String

    temperature::Float64
    humidity::Float64

    occupied::Bool

    lighting_level::Float64
    heating_active::Bool

    appliance_count::Int
end

struct TwinDevice
    id::String
    name::String
    room::String
    category::String

    reachable::Bool
    is_on::Bool

    power_watts::Float64
end

struct TwinEnergy
    household_power::Float64
    grid_power::Float64
    solar_power::Float64
    battery_power::Float64
    battery_soc::Float64
end

struct TwinState
    timestamp::DateTime
    home_name::String

    rooms::Vector{TwinRoom}
    devices::Vector{TwinDevice}

    energy::TwinEnergy

    home_occupied::Bool
    home_mode::String
end

6. Thermal Model
Each room becomes a small physical simulation.
struct TwinParameters

    thermal_alpha::Float64
    heating_gain::Float64
    occupancy_gain::Float64

    lighting_power::Float64
    timestep_hours::Float64

    comfort_temperature::Float64
    minimum_temperature::Float64
    maximum_temperature::Float64
end


const DEFAULT_PARAMETERS = TwinParameters(
    0.035,
    0.20,
    0.015,
    0.010,
    0.25,
    20.5,
    18.0,
    24.0
)

The basic thermal equation:
function next_temperature(
    temperature::Float64,
    outdoor_temperature::Float64,
    heating_level::Float64,
    occupied::Bool,
    p::TwinParameters
)

    heat_loss =
        p.thermal_alpha *
        (outdoor_temperature - temperature)

    heating_gain =
        p.heating_gain *
        heating_level

    occupancy_gain =
        occupied ?
        p.occupancy_gain :
        0.0

    return temperature +
           heat_loss +
           heating_gain +
           occupancy_gain
end

7. Room Simulation
function simulate_room(
    room::TwinRoom,
    heating_level::Float64,
    outdoor_temperature::Float64,
    horizon_minutes::Int,
    p::TwinParameters
)

    steps = Int(
        horizon_minutes /
        (p.timestep_hours * 60)
    )

    temperature = room.temperature

    temperatures = Float64[]
    energy = 0.0

    for _ in 1:steps

        temperature = next_temperature(
            temperature,
            outdoor_temperature,
            heating_level,
            room.occupied,
            p
        )

        push!(
            temperatures,
            temperature
        )

        energy +=
            heating_level *
            p.timestep_hours
    end

    return (
        temperatures = temperatures,
        energy = energy
    )
end

8. Whole-Home Energy Model
function device_power(
    device::TwinDevice
)

    return device.is_on ?
        device.power_watts :
        0.0
end


function household_power(
    state::TwinState
)

    return sum(
        device_power(device)
        for device in state.devices
    )
end

9. Lighting Model
function lighting_power(
    room::TwinRoom,
    level::Float64
)

    return level * 0.01
end

You can later replace this with actual measured watts per room.
10. Appliance Model
function appliance_power(
    state::TwinState
)

    total = 0.0

    for device in state.devices

        category = lowercase(
            device.category
        )

        if device.is_on

            if occursin("dishwasher", category)
                total += 1200

            elseif occursin("washing", category)
                total += 500

            elseif occursin("dryer", category)
                total += 2000

            elseif occursin("oven", category)
                total += 2500

            elseif occursin("water", category)
                total += 1800

            else
                total += device.power_watts
            end
        end
    end

    return total
end

11. Whole-Home Simulation
This is the key function.
function simulate_home(
    state::TwinState,
    heating_levels::Dict{String,Float64},
    lighting_levels::Dict{String,Float64},
    outdoor_temperature::Float64,
    horizon_minutes::Int;
    parameters = DEFAULT_PARAMETERS
)

    total_energy = 0.0
    peak_power = 0.0

    comfort_scores = Float64[]

    room_results = Dict{String,Any}()

    for room in state.rooms

        heating =
            get(
                heating_levels,
                room.name,
                0.0
            )

        lighting =
            get(
                lighting_levels,
                room.name,
                room.lighting_level
            )

        result = simulate_room(
            room,
            heating,
            outdoor_temperature,
            horizon_minutes,
            parameters
        )

        room_results[room.name] = result

        total_energy +=
            result.energy

        for temperature in result.temperatures

            deviation =
                abs(
                    temperature -
                    parameters.comfort_temperature
                )

            score =
                max(
                    0.0,
                    1.0 -
                    deviation / 5.0
                )

            push!(
                comfort_scores,
                score
            )
        end

        total_energy +=
            lighting_power(
                room,
                lighting
            ) *
            horizon_minutes /
            60
    end

    base_power =
        household_power(state) +
        appliance_power(state)

    peak_power =
        base_power

    total_energy +=
        base_power *
        horizon_minutes /
        60 /
        1000

    comfort =
        isempty(comfort_scores) ?
        1.0 :
        mean(comfort_scores)

    return (
        energy_kwh = total_energy,
        peak_power_watts = peak_power,
        comfort_score = comfort,
        rooms = room_results
    )
end

12. Objective Function
Now the digital twin can compare competing futures.
function objective(
    result;
    energy_weight = 1.0,
    comfort_weight = 20.0,
    peak_weight = 0.002
)

    comfort_penalty =
        1.0 -
        result.comfort_score

    return (
        energy_weight *
        result.energy_kwh
        +
        comfort_weight *
        comfort_penalty
        +
        peak_weight *
        result.peak_power_watts
    )
end

So Julia isn't necessarily looking for the lowest energy consumption.
It's looking for the best whole-home state.
13. Automatic Scenario Generation
function generate_scenarios(
    state::TwinState
)

    scenarios = NamedTuple[]

    for heating in 0.0:0.25:1.0

        heating_levels = Dict(
            room.name => heating
            for room in state.rooms
        )

        lighting_levels = Dict(
            room.name =>
                room.lighting_level
            for room in state.rooms
        )

        push!(
            scenarios,
            (
                heating = heating_levels,
                lighting = lighting_levels
            )
        )
    end

    return scenarios
end

14. Optimiser
function optimise_twin(
    state::TwinState,
    outdoor_temperature::Float64,
    horizon_minutes::Int
)

    scenarios =
        generate_scenarios(state)

    best_result = nothing
    best_scenario = nothing
    best_score = Inf

    for scenario in scenarios

        result = simulate_home(
            state,
            scenario.heating,
            scenario.lighting,
            outdoor_temperature,
            horizon_minutes
        )

        score = objective(result)

        if score < best_score

            best_score = score

            best_result = result
            best_scenario = scenario
        end
    end

    return (
        score = best_score,
        scenario = best_scenario,
        result = best_result
    )
end

15. Forecasting
The really useful part is that the twin can run repeatedly into the future.
function forecast_home(
    state::TwinState,
    outdoor_forecast::Vector{Float64},
    horizon_minutes::Int
)

    forecasts = []

    for temperature in outdoor_forecast

        optimisation =
            optimise_twin(
                state,
                temperature,
                horizon_minutes
            )

        push!(
            forecasts,
            (
                outdoor_temperature = temperature,
                optimisation = optimisation
            )
        )
    end

    return forecasts
end

16. Scenario Comparison
This lets Julia ask questions such as:
- What if heating starts now?
- What if it waits 30 minutes?
- What if lights are dimmed?
- What if the dishwasher runs at 02:00?
- What if the battery charges now?
- What if solar is expected to rise?
- What if everyone leaves the house?
function compare_scenarios(
    state::TwinState,
    scenarios,
    outdoor_temperature::Float64,
    horizon_minutes::Int
)

    results = []

    for scenario in scenarios

        result = simulate_home(
            state,
            scenario.heating,
            scenario.lighting,
            outdoor_temperature,
            horizon_minutes
        )

        push!(
            results,
            (
                scenario = scenario,
                objective = objective(result),
                result = result
            )
        )
    end

    sort!(
        results,
        by = x -> x.objective
    )

    return results
end

17. Sensitivity Analysis
This is where the digital twin becomes much more interesting.
function heating_sensitivity(
    state::TwinState,
    outdoor_temperature::Float64,
    horizon_minutes::Int
)

    results = []

    for heating in 0.0:0.1:1.0

        levels = Dict(
            room.name => heating
            for room in state.rooms
        )

        lighting = Dict(
            room.name => room.lighting_level
            for room in state.rooms
        )

        result = simulate_home(
            state,
            levels,
            lighting,
            outdoor_temperature,
            horizon_minutes
        )

        push!(
            results,
            (
                heating_level = heating,
                energy_kwh = result.energy_kwh,
                comfort = result.comfort_score,
                peak_power = result.peak_power_watts
            )
        )
    end

    return results
end

18. Julia → Swift Policy
Julia shouldn't send arbitrary commands.
It sends a proposed policy.
function create_policy(
    optimisation
)

    scenario =
        optimisation.scenario

    commands = []

    for (room, heating) in scenario.heating

        push!(
            commands,
            Dict(
                "room" => room,
                "type" => "heating",
                "value" => heating
            )
        )
    end

    for (room, lighting) in scenario.lighting

        push!(
            commands,
            Dict(
                "room" => room,
                "type" => "lighting",
                "value" => lighting
            )
        )
    end

    return Dict(
        "type" => "whole_home_policy",
        "objective" => optimisation.score,
        "commands" => commands
    )
end

19. Swift — Policy Validation
This is important for the architecture.
Julia never gets permission to execute anything.
struct TwinPolicyCommand: Codable {

    let room: String
    let type: String
    let value: Double
}

struct TwinPolicy: Codable {

    let type: String
    let objective: Double
    let commands: [TwinPolicyCommand]
}

Validator:
struct TwinPolicyValidator {

    static func validate(
        _ policy: TwinPolicy,
        against twin: WholeHomeDigitalTwin
    ) throws {

        guard policy.type == "whole_home_policy" else {
            throw ValidationError.invalidPolicy
        }

        guard policy.objective.isFinite else {
            throw ValidationError.invalidObjective
        }

        for command in policy.commands {

            guard twin.rooms.contains(
                where: { $0.name == command.room }
            ) else {
                throw ValidationError.unknownRoom
            }

            guard command.value.isFinite else {
                throw ValidationError.invalidValue
            }

            switch command.type {

            case "heating":

                guard
                    command.value >= 0 &&
                    command.value <= 1
                else {
                    throw ValidationError.invalidHeatingLevel
                }

            case "lighting":

                guard
                    command.value >= 0 &&
                    command.value <= 1
                else {
                    throw ValidationError.invalidLightingLevel
                }

            default:

                throw ValidationError.unsupportedCommand
            }
        }
    }
}

enum ValidationError: Error {
    case invalidPolicy
    case invalidObjective
    case unknownRoom
    case invalidValue
    case invalidHeatingLevel
    case invalidLightingLevel
    case unsupportedCommand
}

20. The Complete Control Loop
The finished architecture becomes:
@MainActor
final class WholeHomeCoordinator {

    private let twinManager: DigitalTwinManager

    init(
        twinManager: DigitalTwinManager
    ) {
        self.twinManager = twinManager
    }

    func runCycle() async throws {

        // 1. Read real HomeKit state
        let twin =
            try await twinManager.rebuild(
                homeOccupied: true,
                homeMode: "home"
            )

        // 2. Send twin JSON to Julia
        let json =
            try DigitalTwinJSON.encode(twin)

        let response =
            try await sendToJulia(json)

        // 3. Decode Julia's proposed policy
        let policy =
            try JSONDecoder().decode(
                TwinPolicy.self,
                from: response
            )

        // 4. Validate inside Swift
        try TwinPolicyValidator.validate(
            policy,
            against: twin
        )

        // 5. Execute validated commands
        try await execute(policy)
    }

    private func sendToJulia(
        _ data: Data
    ) async throws -> Data {

        // Local IPC / Unix socket / localhost service
        fatalError("Connect to Julia engine")
    }

    private func execute(
        _ policy: TwinPolicy
    ) async throws {

        for command in policy.commands {

            print(
                "Executing:",
                command.type,
                command.room,
                command.value
            )

            // Route to the existing
            // heating / lighting / appliance
            // Swift managers.
        }
    }
}



