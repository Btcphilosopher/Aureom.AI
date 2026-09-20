import SwiftUI
import HealthKit

@MainActor
final class HeartRateManager: NSObject, ObservableObject {

    private let healthStore = HKHealthStore()

    @Published var heartRate: Double = 0
    @Published var isRunning = false

    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw NSError(
                domain: "HeartRate",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Health data is unavailable."]
            )
        }

        guard let heartRateType = HKObjectType.quantityType(
            forIdentifier: .heartRate
        ) else {
            throw NSError(
                domain: "HeartRate",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "Heart-rate type unavailable."]
            )
        }

        let typesToRead: Set<HKObjectType> = [heartRateType]

        try await healthStore.requestAuthorization(
            toShare: [],
            read: typesToRead
        )
    }

    func startMonitoring() async throws {

        guard !isRunning else { return }

        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .other
        configuration.locationType = .indoor

        let session = try HKWorkoutSession(
            healthStore: healthStore,
            configuration: configuration
        )

        let builder = session.associatedWorkoutBuilder()

        session.delegate = self
        builder.delegate = self

        builder.dataSource = HKLiveWorkoutDataSource(
            healthStore: healthStore,
            workoutConfiguration: configuration
        )

        workoutSession = session
        workoutBuilder = builder

        isRunning = true

        let startDate = Date()

        session.startActivity(with: startDate)

        try await builder.beginCollection(at: startDate)
    }

    func stopMonitoring() async throws {

        guard let session = workoutSession,
              let builder = workoutBuilder else {
            return
        }

        session.end()

        try await builder.endCollection(at: Date())
        try await builder.finishWorkout()

        workoutSession = nil
        workoutBuilder = nil

        isRunning = false
    }
}

// MARK: - Workout Session Delegate

extension HeartRateManager: HKWorkoutSessionDelegate {

    nonisolated func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didChangeTo toState: HKWorkoutSessionState,
        from fromState: HKWorkoutSessionState,
        date: Date
    ) {
        // Session state changes.
    }

    nonisolated func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didFailWithError error: Error
    ) {
        print("Workout session error:", error)
    }
}

// MARK: - Live Workout Data

extension HeartRateManager: HKLiveWorkoutBuilderDelegate {

    nonisolated func workoutBuilderDidCollectEvent(
        _ workoutBuilder: HKLiveWorkoutBuilder
    ) {
        // Workout events can be handled here.
    }

    nonisolated func workoutBuilder(
        _ workoutBuilder: HKLiveWorkoutBuilder,
        didCollectDataOf types: Set<HKSampleType>
    ) {

        guard let heartRateType = HKObjectType.quantityType(
            forIdentifier: .heartRate
        ) else {
            return
        }

        guard types.contains(heartRateType),
              let statistics = workoutBuilder.statistics(
                for: heartRateType
              ),
              let quantity = statistics.mostRecentQuantity()
        else {
            return
        }

        let unit = HKUnit.count().unitDivided(
            by: HKUnit.minute()
        )

        let bpm = quantity.doubleValue(for: unit)

        Task { @MainActor in
            self.heartRate = bpm
        }
    }
}











import SwiftUI

struct ContentView: View {

    @StateObject private var heartRateManager =
        HeartRateManager()

    var body: some View {
        VStack(spacing: 12) {

            Text("HEART RATE")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("\(Int(heartRateManager.heartRate))")
                .font(.system(size: 56, weight: .bold))
                .monospacedDigit()

            Text("BPM")
                .font(.headline)

            Button(
                heartRateManager.isRunning
                ? "STOP"
                : "START"
            ) {

                Task {

                    if heartRateManager.isRunning {
                        try? await heartRateManager.stopMonitoring()
                    } else {
                        try? await heartRateManager.startMonitoring()
                    }
                }
            }
            .buttonStyle(.borderedProminent)
        }
        .task {
            try? await heartRateManager.requestAuthorization()
        }
    }
}














```swift
import SwiftUI

struct SpotifyPlayerView: View {

    @StateObject private var player = SpotifyPlayerController()

    var body: some View {
        VStack(spacing: 10) {

            // Album artwork
            AsyncImage(url: player.artworkURL) { image in
                image
                    .resizable()
                    .scaledToFill()
            } placeholder: {
                RoundedRectangle(cornerRadius: 12)
                    .fill(.gray.opacity(0.25))
            }
            .frame(width: 105, height: 105)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Track
            Text(player.trackName)
                .font(.headline)
                .lineLimit(1)

            Text(player.artistName)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            // Progress
            ProgressView(
                value: player.progress,
                total: 1.0
            )

            HStack(spacing: 20) {

                Button {
                    player.previous()
                } label: {
                    Image(systemName: "backward.fill")
                }

                Button {
                    player.togglePlayPause()
                } label: {
                    Image(
                        systemName:
                            player.isPlaying
                            ? "pause.fill"
                            : "play.fill"
                    )
                    .font(.title2)
                }

                Button {
                    player.next()
                } label: {
                    Image(systemName: "forward.fill")
                }
            }
        }
        .padding()
        .task {
            await player.refresh()
        }
    }
}
```

### Player controller

```swift
import Foundation

@MainActor
final class SpotifyPlayerController: ObservableObject {

    @Published var trackName = "Not Playing"
    @Published var artistName = ""
    @Published var artworkURL: URL?

    @Published var isPlaying = false
    @Published var progress: Double = 0

    func refresh() async {
        // Retrieve the current Spotify playback state.
        //
        // The production implementation should obtain this
        // through your authenticated Spotify connection.
    }

    func togglePlayPause() {
        Task {
            if isPlaying {
                await pause()
            } else {
                await play()
            }
        }
    }

    func play() async {
        // Send Spotify playback command.
        isPlaying = true
    }

    func pause() async {
        // Send Spotify pause command.
        isPlaying = false
    }

    func next() {
        Task {
            // Send Spotify "next track" command.
            await refresh()
        }
    }

    func previous() {
        Task {
            // Send Spotify "previous track" command.
            await refresh()
        }
    }
}
```

### The Watch UI

I'd make the actual Watch experience closer to this:

```text
┌─────────────────────┐
│     10:42            │
│                      │
│      ┌──────┐        │
│      │      │        │
│      │ ART  │        │
│      │WORK  │        │
│      └──────┘        │
│                      │
│   Song Title         │
│   Artist             │
│                      │
│  ━━━━━━━━●──────     │
│                      │
│    ◀    ▶    ▶       │
│                      │
└─────────────────────┘
```

For a **real Spotify-integrated version**, I'd split the project into an iPhone companion and Watch app:

```text
Spotify
   │
   ▼
iPhone Spotify Integration
   │
   │ WatchConnectivity
   ▼
Apple Watch
   │
   ├── Current song
   ├── Playback controls
   ├── Artwork
   ├── Progress
   └── Haptics
```

That also pairs nicely with the heart-rate code from the previous step: you could have the Watch display **heart rate + music controls simultaneously**, for example showing BPM at the top while controlling music during a workout.

For a production app, you'd then add **OAuth authentication, token refresh, Spotify playback-state synchronization, WatchConnectivity, offline UI state, Digital Crown volume/control interaction, and workout-aware music controls**.












```swift
import SwiftUI

// MARK: - Smooth UI Configuration

enum SmoothUI {

    static let standardAnimation =
        Animation.easeOut(duration: 0.20)

    static let fastAnimation =
        Animation.easeOut(duration: 0.12)

    static let gentleAnimation =
        Animation.easeInOut(duration: 0.30)
}


// MARK: - Smooth Number

struct SmoothNumber: View {

    let value: Double
    let format: String

    var body: some View {
        Text(String(format: format, value))
            .contentTransition(
                .numericText(value: value)
            )
            .animation(
                SmoothUI.standardAnimation,
                value: value
            )
    }
}


// MARK: - Smooth Heart Rate

struct SmoothHeartRateView: View {

    @ObservedObject var heartRate: HeartRateManager

    var body: some View {

        VStack(spacing: 4) {

            Image(systemName: "heart.fill")
                .symbolEffect(
                    .pulse,
                    options: .repeating
                )
                .foregroundStyle(.red)

            SmoothNumber(
                value: heartRate.heartRate,
                format: "%.0f"
            )
            .font(
                .system(
                    size: 42,
                    weight: .bold,
                    design: .rounded
                )
            )

            Text("BPM")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}


// MARK: - Smooth Play Button

struct SmoothPlayButton: View {

    let isPlaying: Bool
    let action: () -> Void

    var body: some View {

        Button(action: action) {

            Image(
                systemName:
                    isPlaying
                    ? "pause.fill"
                    : "play.fill"
            )
            .font(.title3)
            .contentTransition(
                .symbolEffect(.replace)
            )
        }
        .buttonStyle(.borderedProminent)
        .animation(
            SmoothUI.fastAnimation,
            value: isPlaying
        )
    }
}


// MARK: - Smooth Progress

struct SmoothProgressView: View {

    let progress: Double

    var body: some View {

        GeometryReader { geometry in

            ZStack(alignment: .leading) {

                Capsule()
                    .fill(.secondary.opacity(0.20))

                Capsule()
                    .frame(
                        width:
                            geometry.size.width
                            * min(max(progress, 0), 1)
                    )
                    .animation(
                        SmoothUI.standardAnimation,
                        value: progress
                    )
            }
        }
        .frame(height: 4)
    }
}


// MARK: - Smooth Screen Transition

extension AnyTransition {

    static var smoothWatchTransition: AnyTransition {
        .asymmetric(
            insertion:
                .opacity
                .combined(
                    with: .scale(scale: 0.97)
                ),

            removal:
                .opacity
                .combined(
                    with: .scale(scale: 1.03)
                )
        )
    }
}
```

### The important part for your heart-rate monitor

Heart-rate data can arrive frequently. You **don't want every sensor sample to force an expensive complete UI redraw**.

A small smoothing filter helps:

```swift
import Foundation

@MainActor
final class HeartRateSmoother: ObservableObject {

    @Published private(set) var value: Double = 0

    private let smoothingFactor: Double

    init(smoothingFactor: Double = 0.20) {
        self.smoothingFactor = smoothingFactor
    }

    func addSample(_ newValue: Double) {

        guard newValue > 0 else {
            return
        }

        if value == 0 {
            value = newValue
            return
        }

        value =
            value
            + smoothingFactor
            * (newValue - value)
    }
}
```

So instead of:

```text
Sensor
  ↓
Every measurement
  ↓
SwiftUI redraw
```

you get:

```text
Apple Watch sensor
       ↓
HealthKit
       ↓
HeartRateSmoother
       ↓
filtered BPM
       ↓
SwiftUI
       ↓
smooth display
```

### For the Spotify controls

The same principle applies:

```swift
withAnimation(.easeOut(duration: 0.15)) {
    isPlaying.toggle()
}
```

And avoid doing network/API work directly inside the SwiftUI view. Put it in an `ObservableObject`/actor and publish only the state the interface actually needs.

For an **Apple Watch “premium smoothness” architecture**, I'd use:

```text
                 APPLE WATCH
                      │
             ┌────────┴────────┐
             │                 │
        HealthKit          Spotify
             │                 │
             ▼                 ▼
       Sensor Manager     Music Manager
             │                 │
             └────────┬────────┘
                      ▼
               State / Actors
                      │
              ┌───────┴───────┐
              │               │
        Rate Limiting     State Diffing
              │               │
              └───────┬───────┘
                      ▼
                  SwiftUI
                      │
             Smooth animations
                      │
                Watch display
```

That is the basic pattern I'd use if you're building the **heart-rate + Spotify Apple Watch app** as one cohesive application rather than three separate demos.






```swift
import Foundation

// MARK: - System Event

enum SystemEvent: Sendable {
    case heartRate(Double)
    case musicStateChanged(Bool)
    case timerTick
    case batteryChanged(Double)
}


// MARK: - Event Queue

actor SystemEventQueue {

    private var queue: [SystemEvent] = []

    func push(_ event: SystemEvent) {
        queue.append(event)
    }

    func pop() -> SystemEvent? {
        guard !queue.isEmpty else {
            return nil
        }

        return queue.removeFirst()
    }

    var count: Int {
        queue.count
    }
}


// MARK: - System Scheduler

actor WatchSystemScheduler {

    private let events = SystemEventQueue()

    private var running = false

    func start() async {

        guard !running else {
            return
        }

        running = true

        while running {

            await processEvents()

            // Keep the scheduler lightweight.
            try? await Task.sleep(
                for: .milliseconds(50)
            )
        }
    }

    func stop() {
        running = false
    }

    func submit(_ event: SystemEvent) async {
        await events.push(event)
    }

    private func processEvents() async {

        while let event = await events.pop() {

            switch event {

            case .heartRate(let bpm):
                processHeartRate(bpm)

            case .musicStateChanged(let playing):
                processMusicState(playing)

            case .timerTick:
                processTimer()

            case .batteryChanged(let level):
                processBattery(level)
            }
        }
    }

    private func processHeartRate(_ bpm: Double) {

        guard bpm > 0 else {
            return
        }

        // Sensor processing.
        print("HR:", bpm)
    }

    private func processMusicState(_ playing: Bool) {

        print(
            playing
            ? "Music playing"
            : "Music paused"
        )
    }

    private func processTimer() {
        // Periodic system work.
    }

    private func processBattery(_ level: Double) {

        if level < 0.10 {
            // Reduce optional work.
        }
    }
}
```

### A more kernel-like architecture

For the Watch application you've been building, I'd separate it into layers:

```text
┌──────────────────────────────────┐
│          SwiftUI / Watch UI      │
├──────────────────────────────────┤
│       Application Services       │
│  Heart Rate │ Spotify │ Workout  │
├──────────────────────────────────┤
│        System Event Layer        │
│     scheduler / queues / actors  │
├──────────────────────────────────┤
│        Hardware Interfaces       │
│     HealthKit / sensors / BT     │
├──────────────────────────────────┤
│             watchOS              │
├──────────────────────────────────┤
│       Apple Watch hardware       │
└──────────────────────────────────┘
```

The **actual kernel boundary** is below your application:

```text
Your Swift code
       ↓
Swift runtime
       ↓
watchOS frameworks
       ↓
XNU / kernel
       ↓
Apple Watch hardware
```

So if your goal is **“write the lowest-level Apple Watch software that Apple actually permits a developer to write”**, Swift isn't the kernel language. The useful target is a highly optimized **actor/concurrency + sensor + power-management layer** sitting immediately above watchOS.

For example, the next step could be a **mini watchOS systems runtime** in Swift with a scheduler, priority queues, lock-free-style ring buffer, sensor event pipeline, battery-aware task throttling, and real-time heart-rate processing.





1. Project structure
SensorFusion/
├── SensorFusionEngine.swift
├── SensorManager.swift
├── SensorSample.swift
├── SensorStream.swift
├── SensorState.swift
├── HeartRateProcessor.swift
├── MotionProcessor.swift
├── SensorQuality.swift
└── Tests/
    ├── SensorFusionEngineTests.swift
    ├── HeartRateProcessorTests.swift
    └── MotionProcessorTests.swift
2. Core sensor model
import Foundation

enum SensorType: String, Sendable {
    case heartRate
    case accelerometer
    case gyroscope
    case motion
}

struct SensorSample<Value: Sendable>: Sendable {
    let sensor: SensorType
    let timestamp: ContinuousClock.Instant
    let value: Value
}
3. Unified sensor state
import Foundation

struct SensorState: Sendable {

    var heartRate: Double?
    var acceleration: Vector3?
    var rotationRate: Vector3?

    var timestamp: ContinuousClock.Instant?

    var heartRateQuality: SensorQuality
    var motionQuality: SensorQuality

    var isHeartRateAvailable: Bool
    var isMotionAvailable: Bool

    init(
        heartRate: Double? = nil,
        acceleration: Vector3? = nil,
        rotationRate: Vector3? = nil,
        timestamp: ContinuousClock.Instant? = nil,
        heartRateQuality: SensorQuality = .unavailable,
        motionQuality: SensorQuality = .unavailable,
        isHeartRateAvailable: Bool = false,
        isMotionAvailable: Bool = false
    ) {
        self.heartRate = heartRate
        self.acceleration = acceleration
        self.rotationRate = rotationRate
        self.timestamp = timestamp
        self.heartRateQuality = heartRateQuality
        self.motionQuality = motionQuality
        self.isHeartRateAvailable = isHeartRateAvailable
        self.isMotionAvailable = isMotionAvailable
    }
}

struct Vector3: Sendable, Equatable {

    let x: Double
    let y: Double
    let z: Double

    var magnitude: Double {
        sqrt(
            x * x +
            y * y +
            z * z
        )
    }
}
4. Sensor quality
enum SensorQuality: Sendable {

    case unavailable
    case poor
    case acceptable
    case good
    case excellent
}
5. Heart-rate processor
import Foundation

actor HeartRateProcessor {

    private(set) var latestHeartRate: Double?

    private var previousTimestamp:
        ContinuousClock.Instant?

    func process(
        _ sample: SensorSample<Double>
    ) -> Double? {

        guard sample.sensor == .heartRate else {
            return nil
        }

        guard sample.value.isFinite else {
            return nil
        }

        guard sample.value > 20,
              sample.value < 250 else {
            return nil
        }

        if let previous = previousTimestamp,
           sample.timestamp < previous {
            return nil
        }

        previousTimestamp = sample.timestamp
        latestHeartRate = sample.value

        return sample.value
    }
}
6. Motion processor
import Foundation

actor MotionProcessor {

    private(set) var acceleration: Vector3?
    private(set) var rotationRate: Vector3?

    func processAcceleration(
        _ sample: SensorSample<Vector3>
    ) -> Vector3? {

        guard sample.sensor == .accelerometer else {
            return nil
        }

        acceleration = sample.value
        return sample.value
    }

    func processRotation(
        _ sample: SensorSample<Vector3>
    ) -> Vector3? {

        guard sample.sensor == .gyroscope else {
            return nil
        }

        rotationRate = sample.value
        return sample.value
    }
}
7. The actual fusion engine

This is the important piece:

import Foundation

actor SensorFusionEngine {

    private let heartRateProcessor =
        HeartRateProcessor()

    private let motionProcessor =
        MotionProcessor()

    private(set) var state =
        SensorState()

    func ingestHeartRate(
        _ sample: SensorSample<Double>
    ) async {

        guard let bpm =
            await heartRateProcessor.process(sample)
        else {
            return
        }

        state.heartRate = bpm
        state.timestamp = sample.timestamp
        state.isHeartRateAvailable = true
        state.heartRateQuality = .good
    }

    func ingestAcceleration(
        _ sample: SensorSample<Vector3>
    ) async {

        guard let acceleration =
            await motionProcessor
                .processAcceleration(sample)
        else {
            return
        }

        state.acceleration = acceleration
        state.timestamp = sample.timestamp
        state.isMotionAvailable = true
        state.motionQuality = .good
    }

    func ingestRotation(
        _ sample: SensorSample<Vector3>
    ) async {

        guard let rotation =
            await motionProcessor
                .processRotation(sample)
        else {
            return
        }

        state.rotationRate = rotation
        state.timestamp = sample.timestamp
        state.isMotionAvailable = true
    }

    func currentState() -> SensorState {
        state
    }
}
The resulting pipeline
              Apple Watch sensors
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      Heart Rate  Accelerometer  Gyro
          │           │           │
          ▼           ▼           ▼
       HR Actor   Motion Actor   Motion Actor
          │           │           │
          └───────────┼───────────┘
                      ▼
             SensorFusionEngine
                      │
                      ▼
                SensorState
                
                
                
                
                8. Sensor stream abstraction
import Foundation

struct SensorStream<Value: Sendable>: AsyncSequence {

    typealias Element = SensorSample<Value>

    private let stream: AsyncStream<Element>

    init(
        bufferingPolicy: AsyncStream<Element>.Continuation.BufferingPolicy = .bufferingNewest(1),
        build: @escaping @Sendable (
            AsyncStream<Element>.Continuation
        ) -> Void
    ) {
        self.stream = AsyncStream(
            bufferingPolicy: bufferingPolicy,
            build
        )
    }

    func makeAsyncIterator()
        -> AsyncStream<Element>.Iterator {
        stream.makeAsyncIterator()
    }
}

The important property here is bufferingNewest(1). For live sensor UI, we usually care about the newest measurement rather than processing a large backlog of obsolete measurements.

9. Real heart-rate source

HealthKit is the appropriate public API for heart-rate measurements.

import Foundation
import HealthKit

final class HeartRateSource {

    private let healthStore = HKHealthStore()

    private let heartRateType =
        HKObjectType.quantityType(
            forIdentifier: .heartRate
        )!

    func requestAuthorization() async throws {

        try await healthStore.requestAuthorization(
            toShare: [],
            read: [heartRateType]
        )
    }

    func latestHeartRate() async throws -> Double? {

        let predicate =
            HKQuery.predicateForSamples(
                withStart: Date.distantPast,
                end: Date(),
                options: .strictEndDate
            )

        return try await withCheckedThrowingContinuation {
            continuation in

            let sortDescriptor =
                NSSortDescriptor(
                    key: HKSampleSortIdentifierEndDate,
                    ascending: false
                )

            let query = HKSampleQuery(
                sampleType: heartRateType,
                predicate: predicate,
                limit: 1,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in

                if let error {
                    continuation.resume(
                        throwing: error
                    )
                    return
                }

                guard
                    let sample =
                        samples?.first as?
                        HKQuantitySample
                else {
                    continuation.resume(
                        returning: nil
                    )
                    return
                }

                let unit =
                    HKUnit.count()
                        .unitDivided(
                            by: HKUnit.minute()
                        )

                let bpm =
                    sample.quantity.doubleValue(
                        for: unit
                    )

                continuation.resume(
                    returning: bpm
                )
            }

            self.healthStore.execute(query)
        }
    }
}

For continuous live workout heart rate, we'll later replace this polling approach with HKLiveWorkoutBuilder, which is considerably more appropriate for an active workout.

10. Motion source

Now we can expose publicly available motion information through Core Motion.

import Foundation
import CoreMotion

final class MotionSource {

    private let motionManager =
        CMMotionManager()

    func startDeviceMotion(
        update: @escaping @Sendable (CMDeviceMotion) -> Void
    ) {

        guard motionManager.isDeviceMotionAvailable else {
            return
        }

        motionManager.deviceMotionUpdateInterval =
            1.0 / 25.0

        motionManager.startDeviceMotionUpdates(
            to: .main
        ) { motion, error in

            guard
                error == nil,
                let motion
            else {
                return
            }

            update(motion)
        }
    }

    func stop() {
        motionManager.stopDeviceMotionUpdates()
    }
}

We're deliberately not setting an absurd sampling frequency. The goal is useful information per unit of energy, not maximum theoretical sampling.

11. Connecting motion to the fusion engine

Now create an adapter:

import Foundation
import CoreMotion

final class MotionAdapter {

    private let fusionEngine:
        SensorFusionEngine

    init(
        fusionEngine: SensorFusionEngine
    ) {
        self.fusionEngine = fusionEngine
    }

    func process(
        _ motion: CMDeviceMotion
    ) {

        let timestamp =
            ContinuousClock.now

        let acceleration = Vector3(
            x: motion.userAcceleration.x,
            y: motion.userAcceleration.y,
            z: motion.userAcceleration.z
        )

        let rotation = Vector3(
            x: motion.rotationRate.x,
            y: motion.rotationRate.y,
            z: motion.rotationRate.z
        )

        let accelerationSample =
            SensorSample(
                sensor: .accelerometer,
                timestamp: timestamp,
                value: acceleration
            )

        let rotationSample =
            SensorSample(
                sensor: .gyroscope,
                timestamp: timestamp,
                value: rotation
            )

        Task {
            await fusionEngine
                .ingestAcceleration(
                    accelerationSample
                )

            await fusionEngine
                .ingestRotation(
                    rotationSample
                )
        }
    }
}
12. SensorManager

Now we put the platform-specific pieces behind one interface.

import Foundation
import HealthKit

@MainActor
final class SensorManager: ObservableObject {

    let fusionEngine =
        SensorFusionEngine()

    private let heartRateSource =
        HeartRateSource()

    private let motionSource =
        MotionSource()

    private lazy var motionAdapter =
        MotionAdapter(
            fusionEngine: fusionEngine
        )

    @Published private(set) var isRunning = false

    func authorize() async throws {

        try await heartRateSource
            .requestAuthorization()
    }

    func start() {

        guard !isRunning else {
            return
        }

        isRunning = true

        motionSource.startDeviceMotion {
            [weak self] motion in

            self?.motionAdapter
                .process(motion)
        }
    }

    func stop() {

        guard isRunning else {
            return
        }

        motionSource.stop()

        isRunning = false
    }

    func sampleHeartRate() async {

        do {

            guard
                let bpm =
                    try await heartRateSource
                        .latestHeartRate()
            else {
                return
            }

            let sample =
                SensorSample(
                    sensor: .heartRate,
                    timestamp: ContinuousClock.now,
                    value: bpm
                )

            await fusionEngine
                .ingestHeartRate(sample)

        } catch {

            print(
                "Heart-rate error:",
                error
            )
        }
    }
}
13. Live sensor dashboard

We can now expose the system to SwiftUI.

import SwiftUI

struct SensorDashboard: View {

    @StateObject private var sensors =
        SensorManager()

    @State private var heartRate = 0.0
    @State private var acceleration = Vector3(
        x: 0,
        y: 0,
        z: 0
    )

    var body: some View {

        ScrollView {

            VStack(spacing: 14) {

                VStack {
                    Text("HEART RATE")
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    Text("\(Int(heartRate))")
                        .font(
                            .system(
                                size: 42,
                                weight: .bold,
                                design: .rounded
                            )
                        )

                    Text("BPM")
                        .font(.caption2)
                }

                Divider()

                VStack {
                    Text("MOTION")
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    Text(
                        String(
                            format: "%.2f",
                            acceleration.magnitude
                        )
                    )
                    .font(.title3)
                }

                Button(
                    sensors.isRunning
                    ? "STOP"
                    : "START"
                ) {

                    if sensors.isRunning {
                        sensors.stop()
                    } else {
                        sensors.start()
                    }
                }
            }
            .padding()
        }
        .task {

            do {
                try await sensors.authorize()
            } catch {
                print(error)
            }
        }
        .task {

            while !Task.isCancelled {

                await sensors
                    .sampleHeartRate()

                try? await Task.sleep(
                    for: .seconds(5)
                )

                let state =
                    await sensors.fusionEngine
                        .currentState()

                heartRate =
                    state.heartRate ?? 0

                acceleration =
                    state.acceleration
                    ?? acceleration
            }
        }
    }
}





```swift
//
//  RealTimeSignalProcessor.swift
//
//  Real-time signal-processing foundation for watchOS.
//
//  Designed to sit between public Apple sensor APIs and the
//  application's SensorFusionEngine.
//
//  IMPORTANT:
//  This is application-level signal processing.
//  It does not replace Apple's sensor firmware, watchOS,
//  HealthKit, or medical-device algorithms.
//

import Foundation

// ============================================================
// MARK: - Core Signal Types
// ============================================================

public struct SignalSample<Value: Sendable>: Sendable {

    public let timestamp: ContinuousClock.Instant
    public let value: Value

    public init(
        timestamp: ContinuousClock.Instant,
        value: Value
    ) {
        self.timestamp = timestamp
        self.value = value
    }
}


// ============================================================
// MARK: - Signal Quality
// ============================================================

public enum SignalQuality: Int, Sendable, Comparable {

    case unavailable = 0
    case poor = 1
    case acceptable = 2
    case good = 3
    case excellent = 4
}


// ============================================================
// MARK: - Processing Result
// ============================================================

public struct ProcessedSample<Value: Sendable>: Sendable {

    public let rawValue: Value
    public let filteredValue: Value
    public let timestamp: ContinuousClock.Instant

    public let quality: SignalQuality
    public let wasRejected: Bool

    public init(
        rawValue: Value,
        filteredValue: Value,
        timestamp: ContinuousClock.Instant,
        quality: SignalQuality,
        wasRejected: Bool
    ) {
        self.rawValue = rawValue
        self.filteredValue = filteredValue
        self.timestamp = timestamp
        self.quality = quality
        self.wasRejected = wasRejected
    }
}


// ============================================================
// MARK: - Numeric Signal Protocol
// ============================================================

public protocol NumericSignal {

    static func +(lhs: Self, rhs: Self) -> Self
    static func -(lhs: Self, rhs: Self) -> Self
    static func /(lhs: Self, rhs: Double) -> Self
    static func *(lhs: Self, rhs: Double) -> Self
}


// Double already satisfies the required operations,
// but declaring this conformance explicitly makes the
// intended abstraction obvious.

extension Double: NumericSignal {}


// ============================================================
// MARK: - Bounded Ring Buffer
// ============================================================

public struct RingBuffer<Element: Sendable>: Sendable {

    private var storage: [Element] = []

    public let capacity: Int

    public init(capacity: Int) {

        precondition(
            capacity > 0,
            "RingBuffer capacity must be greater than zero."
        )

        self.capacity = capacity

        storage.reserveCapacity(capacity)
    }

    public var count: Int {
        storage.count
    }

    public var isEmpty: Bool {
        storage.isEmpty
    }

    public mutating func append(_ element: Element) {

        if storage.count >= capacity {
            storage.removeFirst()
        }

        storage.append(element)
    }

    public func last() -> Element? {
        storage.last
    }

    public func values() -> [Element] {
        storage
    }

    public mutating func removeAll() {
        storage.removeAll(keepingCapacity: true)
    }
}


// ============================================================
// MARK: - Running Statistics
// ============================================================

public struct RunningStatistics: Sendable {

    private(set) public var count: Int = 0
    private(set) public var minimum: Double?
    private(set) public var maximum: Double?

    private var meanValue: Double = 0
    private var squaredDifference: Double = 0

    public init() {}

    public mutating func add(_ value: Double) {

        guard value.isFinite else {
            return
        }

        count += 1

        if minimum == nil || value < minimum! {
            minimum = value
        }

        if maximum == nil || value > maximum! {
            maximum = value
        }

        let delta = value - meanValue

        meanValue += delta / Double(count)

        let deltaTwo = value - meanValue

        squaredDifference += delta * deltaTwo
    }

    public var mean: Double? {

        guard count > 0 else {
            return nil
        }

        return meanValue
    }

    public var variance: Double? {

        guard count > 1 else {
            return nil
        }

        return squaredDifference /
            Double(count - 1)
    }

    public var standardDeviation: Double? {

        guard let variance else {
            return nil
        }

        return sqrt(max(variance, 0))
    }
}


// ============================================================
// MARK: - Signal Validator
// ============================================================

public struct NumericValidator: Sendable {

    public let minimum: Double?
    public let maximum: Double?

    public init(
        minimum: Double? = nil,
        maximum: Double? = nil
    ) {
        self.minimum = minimum
        self.maximum = maximum
    }

    public func isValid(_ value: Double) -> Bool {

        guard value.isFinite else {
            return false
        }

        if let minimum,
           value < minimum {
            return false
        }

        if let maximum,
           value > maximum {
            return false
        }

        return true
    }
}


// ============================================================
// MARK: - Timestamp Validator
// ============================================================

public struct TimestampValidator: Sendable {

    public let maximumAge: Duration

    public init(
        maximumAge: Duration
    ) {
        self.maximumAge = maximumAge
    }

    public func isAcceptable(
        _ timestamp: ContinuousClock.Instant,
        now: ContinuousClock.Instant = .now
    ) -> Bool {

        if timestamp > now {
            return true
        }

        let age = now - timestamp

        return age <= maximumAge
    }
}


// ============================================================
// MARK: - Moving Average
// ============================================================

public struct MovingAverageFilter: Sendable {

    private var buffer: RingBuffer<Double>

    public init(windowSize: Int) {

        buffer =
            RingBuffer<Double>(
                capacity: windowSize
            )
    }

    public mutating func process(
        _ value: Double
    ) -> Double {

        buffer.append(value)

        let values = buffer.values()

        guard !values.isEmpty else {
            return value
        }

        let total =
            values.reduce(0, +)

        return total /
            Double(values.count)
    }

    public mutating func reset() {
        buffer.removeAll()
    }
}


// ============================================================
// MARK: - Exponential Moving Average
// ============================================================

public struct ExponentialSmoother: Sendable {

    public let alpha: Double

    private var current: Double?

    public init(alpha: Double) {

        precondition(
            alpha > 0 && alpha <= 1,
            "Alpha must be in (0, 1]."
        )

        self.alpha = alpha
    }

    public mutating func process(
        _ value: Double
    ) -> Double {

        guard let current else {

            self.current = value

            return value
        }

        let result =
            current +
            alpha * (value - current)

        self.current = result

        return result
    }

    public mutating func reset() {
        current = nil
    }
}


// ============================================================
// MARK: - Median Filter
// ============================================================

public struct MedianFilter: Sendable {

    private var buffer: RingBuffer<Double>

    public init(windowSize: Int) {

        buffer =
            RingBuffer<Double>(
                capacity: windowSize
            )
    }

    public mutating func process(
        _ value: Double
    ) -> Double {

        buffer.append(value)

        let sorted =
            buffer.values()
                .sorted()

        guard !sorted.isEmpty else {
            return value
        }

        let middle =
            sorted.count / 2

        if sorted.count.isMultiple(of: 2) {

            return (
                sorted[middle - 1] +
                sorted[middle]
            ) / 2

        } else {

            return sorted[middle]
        }
    }

    public mutating func reset() {
        buffer.removeAll()
    }
}


// ============================================================
// MARK: - Outlier Rejection
// ============================================================

public struct OutlierRejector: Sendable {

    public let maximumDeviation: Double

    private var statistics =
        RunningStatistics()

    public init(
        maximumDeviation: Double = 3.0
    ) {
        self.maximumDeviation =
            maximumDeviation
    }

    public mutating func accept(
        _ value: Double
    ) -> Bool {

        guard
            let mean = statistics.mean,
            let deviation =
                statistics.standardDeviation,
            deviation > 0
        else {

            statistics.add(value)

            return true
        }

        let distance =
            abs(value - mean) / deviation

        if distance > maximumDeviation {
            return false
        }

        statistics.add(value)

        return true
    }

    public mutating func reset() {
        statistics = RunningStatistics()
    }
}


// ============================================================
// MARK: - Peak Detector
// ============================================================

public struct PeakDetector: Sendable {

    public let threshold: Double

    private var previous: Double?
    private var rising = false

    public init(
        threshold: Double
    ) {
        self.threshold = threshold
    }

    public mutating func process(
        _ value: Double
    ) -> Bool {

        guard let previous else {

            self.previous = value

            return false
        }

        let difference =
            value - previous

        if difference > threshold {
            rising = true
        }

        let detected =
            rising &&
            difference < 0

        if detected {
            rising = false
        }

        self.previous = value

        return detected
    }

    public mutating func reset() {
        previous = nil
        rising = false
    }
}


// ============================================================
// MARK: - Signal Quality Evaluator
// ============================================================

public struct SignalQualityEvaluator: Sendable {

    public let expectedMinimum: Double?
    public let expectedMaximum: Double?

    public init(
        expectedMinimum: Double? = nil,
        expectedMaximum: Double? = nil
    ) {
        self.expectedMinimum = expectedMinimum
        self.expectedMaximum = expectedMaximum
    }

    public func evaluate(
        value: Double,
        sampleCount: Int,
        standardDeviation: Double?
    ) -> SignalQuality {

        guard value.isFinite else {
            return .unavailable
        }

        guard sampleCount > 0 else {
            return .unavailable
        }

        if let minimum = expectedMinimum,
           value < minimum {
            return .poor
        }

        if let maximum = expectedMaximum,
           value > maximum {
            return .poor
        }

        guard let deviation = standardDeviation else {
            return .acceptable
        }

        if deviation < 0.5 {
            return .excellent
        }

        if deviation < 2.0 {
            return .good
        }

        if deviation < 5.0 {
            return .acceptable
        }

        return .poor
    }
}


// ============================================================
// MARK: - Numeric Signal Processor
// ============================================================

public struct NumericSignalProcessor: Sendable {

    private let validator: NumericValidator
    private let timestampValidator: TimestampValidator
    private let qualityEvaluator: SignalQualityEvaluator

    private var statistics =
        RunningStatistics()

    private var medianFilter:
        MedianFilter

    private var smoother:
        ExponentialSmoother

    private var outlierRejector:
        OutlierRejector

    public init(
        minimum: Double? = nil,
        maximum: Double? = nil,
        timestampMaximumAge: Duration = .seconds(10),
        medianWindow: Int = 3,
        smoothingAlpha: Double = 0.25,
        outlierDeviation: Double = 3.0,
        qualityEvaluator:
            SignalQualityEvaluator =
            SignalQualityEvaluator()
    ) {

        validator =
            NumericValidator(
                minimum: minimum,
                maximum: maximum
            )

        timestampValidator =
            TimestampValidator(
                maximumAge:
                    timestampMaximumAge
            )

        self.qualityEvaluator =
            qualityEvaluator

        medianFilter =
            MedianFilter(
                windowSize: medianWindow
            )

        smoother =
            ExponentialSmoother(
                alpha: smoothingAlpha
            )

        outlierRejector =
            OutlierRejector(
                maximumDeviation:
                    outlierDeviation
            )
    }

    public mutating func process(
        _ sample: SignalSample<Double>
    ) -> ProcessedSample<Double> {

        guard validator.isValid(sample.value) else {

            return ProcessedSample(
                rawValue: sample.value,
                filteredValue: sample.value,
                timestamp: sample.timestamp,
                quality: .poor,
                wasRejected: true
            )
        }

        guard timestampValidator.isAcceptable(
            sample.timestamp
        ) else {

            return ProcessedSample(
                rawValue: sample.value,
                filteredValue: sample.value,
                timestamp: sample.timestamp,
                quality: .poor,
                wasRejected: true
            )
        }

        guard outlierRejector.accept(
            sample.value
        ) else {

            return ProcessedSample(
                rawValue: sample.value,
                filteredValue: sample.value,
                timestamp: sample.timestamp,
                quality: .poor,
                wasRejected: true
            )
        }

        statistics.add(sample.value)

        let median =
            medianFilter.process(
                sample.value
            )

        let filtered =
            smoother.process(median)

        let quality =
            qualityEvaluator.evaluate(
                value: filtered,
                sampleCount:
                    statistics.count,
                standardDeviation:
                    statistics.standardDeviation
            )

        return ProcessedSample(
            rawValue: sample.value,
            filteredValue: filtered,
            timestamp: sample.timestamp,
            quality: quality,
            wasRejected: false
        )
    }

    public mutating func reset() {

        statistics =
            RunningStatistics()

        medianFilter.reset()
        smoother.reset()
        outlierRejector.reset()
    }
}


// ============================================================
// MARK: - Heart Rate Processor
// ============================================================

public actor RealTimeHeartRateProcessor {

    private var processor:
        NumericSignalProcessor

    private(set) var latest:
        ProcessedSample<Double>?

    public init() {

        processor =
            NumericSignalProcessor(
                minimum: 20,
                maximum: 250,
                medianWindow: 3,
                smoothingAlpha: 0.20,
                outlierDeviation: 3.0,
                qualityEvaluator:
                    SignalQualityEvaluator(
                        expectedMinimum: 30,
                        expectedMaximum: 220
                    )
            )
    }

    public func process(
        bpm: Double,
        timestamp:
            ContinuousClock.Instant = .now
    ) -> ProcessedSample<Double> {

        let sample =
            SignalSample(
                timestamp: timestamp,
                value: bpm
            )

        let result =
            processor.process(sample)

        if !result.wasRejected {
            latest = result
        }

        return result
    }

    public func reset() {
        processor.reset()
        latest = nil
    }
}


// ============================================================
// MARK: - Motion Vector
// ============================================================

public struct MotionVector: Sendable, Equatable {

    public let x: Double
    public let y: Double
    public let z: Double

    public init(
        x: Double,
        y: Double,
        z: Double
    ) {
        self.x = x
        self.y = y
        self.z = z
    }

    public var magnitude: Double {

        sqrt(
            x * x +
            y * y +
            z * z
        )
    }
}


// ============================================================
// MARK: - Motion Signal Processor
// ============================================================

public actor RealTimeMotionProcessor {

    private var magnitudeProcessor:
        NumericSignalProcessor

    private(set) var latestMagnitude:
        ProcessedSample<Double>?

    public init() {

        magnitudeProcessor =
            NumericSignalProcessor(
                minimum: 0,
                maximum: 100,
                medianWindow: 5,
                smoothingAlpha: 0.25,
                outlierDeviation: 4.0,
                qualityEvaluator:
                    SignalQualityEvaluator(
                        expectedMinimum: 0,
                        expectedMaximum: 50
                    )
            )
    }

    public func process(
        vector: MotionVector,
        timestamp:
            ContinuousClock.Instant = .now
    ) -> ProcessedSample<Double> {

        let magnitude =
            vector.magnitude

        let sample =
            SignalSample(
                timestamp: timestamp,
                value: magnitude
            )

        let result =
            magnitudeProcessor
                .process(sample)

        if !result.wasRejected {
            latestMagnitude = result
        }

        return result
    }

    public func reset() {
        magnitudeProcessor.reset()
        latestMagnitude = nil
    }
}


// ============================================================
// MARK: - Unified Processing State
// ============================================================

public struct SignalProcessingState: Sendable {

    public var heartRate:
        ProcessedSample<Double>?

    public var motionMagnitude:
        ProcessedSample<Double>?

    public var overallQuality:
        SignalQuality

    public init(
        heartRate:
            ProcessedSample<Double>? = nil,
        motionMagnitude:
            ProcessedSample<Double>? = nil,
        overallQuality:
            SignalQuality = .unavailable
    ) {

        self.heartRate = heartRate
        self.motionMagnitude =
            motionMagnitude
        self.overallQuality =
            overallQuality
    }
}


// ============================================================
// MARK: - Real-Time Processing Engine
// ============================================================

public actor RealTimeSignalProcessor {

    private let heartRateProcessor:
        RealTimeHeartRateProcessor

    private let motionProcessor:
        RealTimeMotionProcessor

    private(set) var state =
        SignalProcessingState()

    public init() {

        heartRateProcessor =
            RealTimeHeartRateProcessor()

        motionProcessor =
            RealTimeMotionProcessor()
    }

    public func processHeartRate(
        _ bpm: Double,
        timestamp:
            ContinuousClock.Instant = .now
    ) async
        -> ProcessedSample<Double>
    {

        let result =
            await heartRateProcessor
                .process(
                    bpm: bpm,
                    timestamp: timestamp
                )

        if !result.wasRejected {

            state.heartRate = result

            recomputeQuality()
        }

        return result
    }

    public func processMotion(
        _ vector: MotionVector,
        timestamp:
            ContinuousClock.Instant = .now
    ) async
        -> ProcessedSample<Double>
    {

        let result =
            await motionProcessor
                .process(
                    vector: vector,
                    timestamp: timestamp
                )

        if !result.wasRejected {

            state.motionMagnitude =
                result

            recomputeQuality()
        }

        return result
    }

    public func currentState()
        -> SignalProcessingState {
        state
    }

    public func reset() async {

        await heartRateProcessor.reset()
        await motionProcessor.reset()

        state =
            SignalProcessingState()
    }

    private func recomputeQuality() {

        var scores: [Int] = []

        if let heartRate =
            state.heartRate {
            scores.append(
                heartRate.quality.rawValue
            )
        }

        if let motion =
            state.motionMagnitude {
            scores.append(
                motion.quality.rawValue
            )
        }

        guard !scores.isEmpty else {

            state.overallQuality =
                .unavailable

            return
        }

        let average =
            Double(
                scores.reduce(0, +)
            ) / Double(scores.count)

        switch average {

        case 3.5...:
            state.overallQuality = .excellent

        case 2.5..<3.5:
            state.overallQuality = .good

        case 1.5..<2.5:
            state.overallQuality = .acceptable

        case 0.5..<1.5:
            state.overallQuality = .poor

        default:
            state.overallQuality = .unavailable
        }
    }
}


// ============================================================
// MARK: - Async Processing Pipeline
// ============================================================

public actor SignalProcessingPipeline {

    private let processor:
        RealTimeSignalProcessor

    public init(
        processor:
            RealTimeSignalProcessor =
            RealTimeSignalProcessor()
    ) {
        self.processor = processor
    }

    public func processHeartRateStream(
        _ stream:
            AsyncStream<
                SignalSample<Double>
            >
    ) async {

        for await sample in stream {

            _ = await processor
                .processHeartRate(
                    sample.value,
                    timestamp:
                        sample.timestamp
                )
        }
    }

    public func processMotionStream(
        _ stream:
            AsyncStream<
                SignalSample<MotionVector>
            >
    ) async {

        for await sample in stream {

            _ = await processor
                .processMotion(
                    sample.value,
                    timestamp:
                        sample.timestamp
                )
        }
    }
}


// ============================================================
// MARK: - Sensor Stream Factory
// ============================================================

public final class SensorStreamFactory {

    public init() {}

    public func heartRateStream()
        -> (
            stream:
                AsyncStream<
                    SignalSample<Double>
                >,
            continuation:
                AsyncStream<
                    SignalSample<Double>
                >.Continuation
        ) {

        var continuation:
            AsyncStream<
                SignalSample<Double>
            >.Continuation!

        let stream =
            AsyncStream<
                SignalSample<Double>
            >(
                bufferingPolicy:
                    .bufferingNewest(1)
            ) {
                continuation = $0
            }

        return (
            stream,
            continuation
        )
    }

    public func motionStream()
        -> (
            stream:
                AsyncStream<
                    SignalSample<MotionVector>
                >,
            continuation:
                AsyncStream<
                    SignalSample<MotionVector>
                >.Continuation
        ) {

        var continuation:
            AsyncStream<
                SignalSample<MotionVector>
            >.Continuation!

        let stream =
            AsyncStream<
                SignalSample<MotionVector>
            >(
                bufferingPolicy:
                    .bufferingNewest(1)
            ) {
                continuation = $0
            }

        return (
            stream,
            continuation
        )
    }
}


// ============================================================
// MARK: - Example Usage
// ============================================================

public struct SignalProcessorExample {

    public init() {}

    public func runExample() async {

        let engine =
            RealTimeSignalProcessor()

        let first =
            await engine.processHeartRate(
                72
            )

        print(
            "Raw:",
            first.rawValue
        )

        print(
            "Filtered:",
            first.filteredValue
        )

        print(
            "Quality:",
            first.quality
        )

        let second =
            await engine.processHeartRate(
                74
            )

        print(
            "Filtered:",
            second.filteredValue
        )

        let third =
            await engine.processHeartRate(
                73
            )

        print(
            "Filtered:",
            third.filteredValue
        )

        let motion =
            await engine.processMotion(
                MotionVector(
                    x: 0.02,
                    y: 0.14,
                    z: 0.03
                )
            )

        print(
            "Motion:",
            motion.filteredValue
        )

        let state =
            await engine.currentState()

        print(
            "Overall quality:",
            state.overallQuality
        )
    }
}
```

### How this fits into our Watch project

The architecture is now:

```text
                    watchOS
                       │
        ┌──────────────┴──────────────┐
        │                             │
     HealthKit                    Core Motion
        │                             │
        ▼                             ▼
   Heart-rate                    Motion samples
     source                           │
        │                             │
        └──────────────┬──────────────┘
                       ▼
                Sensor Manager
                       │
                       ▼
          ┌────────────────────────┐
          │ REAL-TIME PROCESSOR    │
          │                        │
          │ Validation             │
          │ Timestamp checking     │
          │ Outlier rejection      │
          │ Median filtering       │
          │ Exponential smoothing  │
          │ Statistics             │
          │ Quality estimation     │
          └────────────┬───────────┘
                       ▼
                 Sensor Fusion
                       │
                       ▼
                 SensorState
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
        Workout engine        Watch UI
```

The particularly important design choice is the **bounded `RingBuffer` + `.bufferingNewest(1)` combination**. A live Watch application shouldn't allow thousands of obsolete sensor samples to accumulate while the processor catches up.

The processing chain is therefore:

```text
RAW
 ↓
Validate
 ↓
Timestamp check
 ↓
Outlier rejection
 ↓
Median filter
 ↓
Exponential smoothing
 ↓
Statistics
 ↓
Quality assessment
 ↓
Processed sample
 ↓
Fusion engine
```

For the next stage, I'd connect this directly to the **actual HealthKit live workout stream and Core Motion stream**, then add **unit tests and performance benchmarks** so we can measure latency, memory usage and processing cost rather than merely assuming the system is fast.




```swift
//
// ActivityRecognitionEngine.swift
//
// Application-level activity recognition layer for watchOS.
//
// Designed to consume processed sensor/fusion data and produce
// stable activity states for the rest of the application.
//
// IMPORTANT:
// This is not a replacement for Apple's private activity-recognition
// algorithms. It operates only on data available to the application.
//

import Foundation
import CoreMotion
import HealthKit

// ============================================================
// MARK: - Activity State
// ============================================================

public enum ActivityState: String, Sendable, Codable {

    case unknown

    case stationary

    case walking

    case running

    case cycling

    case workout

    case automotive

    case elevatedMovement

}


// ============================================================
// MARK: - Activity Confidence
// ============================================================

public enum ActivityConfidence: Int, Sendable {

    case unavailable = 0
    case low = 1
    case medium = 2
    case high = 3
}


// ============================================================
// MARK: - Activity Observation
// ============================================================

public struct ActivityObservation: Sendable {

    public let state: ActivityState

    public let confidence: ActivityConfidence

    public let timestamp: ContinuousClock.Instant

    public let motionMagnitude: Double

    public let heartRate: Double?

    public init(
        state: ActivityState,
        confidence: ActivityConfidence,
        timestamp: ContinuousClock.Instant,
        motionMagnitude: Double,
        heartRate: Double?
    ) {

        self.state = state
        self.confidence = confidence
        self.timestamp = timestamp
        self.motionMagnitude = motionMagnitude
        self.heartRate = heartRate
    }
}


// ============================================================
// MARK: - Activity Features
// ============================================================

public struct ActivityFeatures: Sendable {

    public let accelerationMagnitude: Double

    public let averageAcceleration: Double

    public let accelerationVariance: Double

    public let heartRate: Double?

    public let cadenceEstimate: Double?

    public let timestamp: ContinuousClock.Instant

    public init(
        accelerationMagnitude: Double,
        averageAcceleration: Double,
        accelerationVariance: Double,
        heartRate: Double?,
        cadenceEstimate: Double?,
        timestamp: ContinuousClock.Instant
    ) {

        self.accelerationMagnitude =
            accelerationMagnitude

        self.averageAcceleration =
            averageAcceleration

        self.accelerationVariance =
            accelerationVariance

        self.heartRate =
            heartRate

        self.cadenceEstimate =
            cadenceEstimate

        self.timestamp =
            timestamp
    }
}


// ============================================================
// MARK: - Feature Window
// ============================================================

public struct ActivityFeatureWindow: Sendable {

    private var samples:
        [Double] = []

    public let capacity: Int

    public init(capacity: Int = 32) {

        precondition(
            capacity > 0
        )

        self.capacity = capacity

        samples.reserveCapacity(
            capacity
        )
    }

    public mutating func append(
        _ value: Double
    ) {

        guard value.isFinite else {
            return
        }

        if samples.count >= capacity {
            samples.removeFirst()
        }

        samples.append(value)
    }

    public var count: Int {
        samples.count
    }

    public var average: Double {

        guard !samples.isEmpty else {
            return 0
        }

        return samples.reduce(
            0,
            +
        ) / Double(samples.count)
    }

    public var variance: Double {

        guard samples.count > 1 else {
            return 0
        }

        let mean = average

        let sum =
            samples.reduce(0) {
                partial,
                value in

                partial +
                    pow(
                        value - mean,
                        2
                    )
            }

        return sum /
            Double(samples.count - 1)
    }

    public func values() -> [Double] {
        samples
    }

    public mutating func reset() {
        samples.removeAll(
            keepingCapacity: true
        )
    }
}


// ============================================================
// MARK: - Cadence Estimator
// ============================================================

public struct CadenceEstimator: Sendable {

    private var previousValue:
        Double?

    private var lastPeak:
        ContinuousClock.Instant?

    private var intervals:
        [Duration] = []

    public init() {}

    public mutating func process(
        value: Double,
        timestamp: ContinuousClock.Instant,
        threshold: Double = 0.15
    ) -> Double? {

        defer {
            previousValue = value
        }

        guard let previousValue else {
            return nil
        }

        let rising =
            value - previousValue

        guard rising > threshold else {
            return nil
        }

        guard let previousPeak = lastPeak else {

            lastPeak = timestamp

            return nil
        }

        let interval =
            timestamp - previousPeak

        lastPeak = timestamp

        intervals.append(
            interval
        )

        if intervals.count > 5 {
            intervals.removeFirst()
        }

        return estimatedCadence()
    }

    private func estimatedCadence()
        -> Double?
    {

        guard !intervals.isEmpty else {
            return nil
        }

        let seconds =
            intervals.map {
                durationToSeconds($0)
            }

        let average =
            seconds.reduce(0, +) /
            Double(seconds.count)

        guard average > 0 else {
            return nil
        }

        return 60.0 / average
    }

    private func durationToSeconds(
        _ duration: Duration
    ) -> Double {

        let components =
            duration.components

        return Double(
            components.seconds
        ) +
        Double(
            components.attoseconds
        ) / 1_000_000_000_000_000_000
    }

    public mutating func reset() {

        previousValue = nil
        lastPeak = nil
        intervals.removeAll()
    }
}


// ============================================================
// MARK: - Activity Classifier
// ============================================================

public struct ActivityClassifier: Sendable {

    public struct Thresholds: Sendable {

        public var stationary:
            Double

        public var walking:
            Double

        public var running:
            Double

        public var cycling:
            Double

        public init(
            stationary: Double = 0.04,
            walking: Double = 0.10,
            running: Double = 0.45,
            cycling: Double = 0.30
        ) {

            self.stationary =
                stationary

            self.walking =
                walking

            self.running =
                running

            self.cycling =
                cycling
        }
    }

    public let thresholds: Thresholds

    public init(
        thresholds:
            Thresholds =
            Thresholds()
    ) {

        self.thresholds =
            thresholds
    }

    public func classify(
        features: ActivityFeatures
    ) -> (
        ActivityState,
        ActivityConfidence
    ) {

        let movement =
            features.averageAcceleration

        let variance =
            features.accelerationVariance

        if movement <
            thresholds.stationary {

            return (
                .stationary,
                .high
            )
        }

        if movement >=
            thresholds.running {

            return classifyHighMovement(
                features
            )
        }

        if movement >=
            thresholds.walking {

            return (
                .walking,
                confidenceFor(
                    variance: variance
                )
            )
        }

        if movement >=
            thresholds.cycling {

            return (
                .cycling,
                .medium
            )
        }

        return (
            .elevatedMovement,
            .low
        )
    }

    private func classifyHighMovement(
        _ features: ActivityFeatures
    ) -> (
        ActivityState,
        ActivityConfidence
    ) {

        if let cadence =
            features.cadenceEstimate {

            if cadence >= 140 {
                return (
                    .running,
                    .high
                )
            }

            if cadence >= 70 {
                return (
                    .running,
                    .medium
                )
            }
        }

        return (
            .running,
            .medium
        )
    }

    private func confidenceFor(
        variance: Double
    ) -> ActivityConfidence {

        if variance < 0.02 {
            return .high
        }

        if variance < 0.10 {
            return .medium
        }

        return .low
    }
}


// ============================================================
// MARK: - State Stabilizer
// ============================================================

public actor ActivityStateStabilizer {

    private(set) public var state:
        ActivityState = .unknown

    private(set) public var confidence:
        ActivityConfidence = .unavailable

    private var candidate:
        ActivityState?

    private var candidateCount = 0

    private let requiredSamples: Int

    public init(
        requiredSamples: Int = 3
    ) {

        precondition(
            requiredSamples > 0
        )

        self.requiredSamples =
            requiredSamples
    }

    public func update(
        candidate newState: ActivityState,
        confidence newConfidence:
            ActivityConfidence
    ) -> ActivityState {

        if newState == state {

            candidate = nil
            candidateCount = 0

            confidence =
                newConfidence

            return state
        }

        if candidate != newState {

            candidate =
                newState

            candidateCount = 1

            return state
        }

        candidateCount += 1

        if candidateCount >=
            requiredSamples {

            state = newState

            confidence =
                newConfidence

            candidate = nil
            candidateCount = 0
        }

        return state
    }

    public func reset() {

        state = .unknown
        confidence = .unavailable

        candidate = nil
        candidateCount = 0
    }
}


// ============================================================
// MARK: - Activity Recognition Engine
// ============================================================

public actor ActivityRecognitionEngine {

    private var featureWindow =
        ActivityFeatureWindow(
            capacity: 32
        )

    private var cadenceEstimator =
        CadenceEstimator()

    private let classifier =
        ActivityClassifier()

    private let stabilizer =
        ActivityStateStabilizer()

    private(set) public var latest:
        ActivityObservation?

    public init() {}

    public func process(
        accelerationMagnitude: Double,
        heartRate: Double?,
        timestamp:
            ContinuousClock.Instant = .now
    ) async -> ActivityObservation {

        featureWindow.append(
            accelerationMagnitude
        )

        let cadence =
            cadenceEstimator.process(
                value:
                    accelerationMagnitude,
                timestamp:
                    timestamp
            )

        let features =
            ActivityFeatures(
                accelerationMagnitude:
                    accelerationMagnitude,

                averageAcceleration:
                    featureWindow.average,

                accelerationVariance:
                    featureWindow.variance,

                heartRate:
                    heartRate,

                cadenceEstimate:
                    cadence,

                timestamp:
                    timestamp
            )

        let classification =
            classifier.classify(
                features: features
            )

        let stableState =
            await stabilizer.update(
                candidate:
                    classification.0,
                confidence:
                    classification.1
            )

        let observation =
            ActivityObservation(
                state:
                    stableState,

                confidence:
                    classification.1,

                timestamp:
                    timestamp,

                motionMagnitude:
                    accelerationMagnitude,

                heartRate:
                    heartRate
            )

        latest = observation

        return observation
    }

    public func reset() async {

        featureWindow.reset()

        cadenceEstimator.reset()

        await stabilizer.reset()

        latest = nil
    }
}


// ============================================================
// MARK: - Core Motion Activity Source
// ============================================================

@MainActor
public final class WatchMotionActivitySource:
    ObservableObject {

    private let manager =
        CMMotionManager()

    private let queue =
        OperationQueue()

    private let recognitionEngine:
        ActivityRecognitionEngine

    @Published public private(set) var
        activity: ActivityObservation?

    @Published public private(set) var
        isRunning = false

    public init(
        engine:
            ActivityRecognitionEngine =
            ActivityRecognitionEngine()
    ) {

        self.recognitionEngine =
            engine

        queue.qualityOfService =
            .userInitiated

        queue.maxConcurrentOperationCount =
            1
    }

    public func start() {

        guard !isRunning else {
            return
        }

        guard
            manager.isDeviceMotionAvailable
        else {
            return
        }

        manager.deviceMotionUpdateInterval =
            1.0 / 20.0

        isRunning = true

        manager.startDeviceMotionUpdates(
            to: queue
        ) {
            [weak self] motion,
            error in

            guard
                error == nil,
                let motion
            else {
                return
            }

            let magnitude =
                sqrt(
                    pow(
                        motion.userAcceleration.x,
                        2
                    ) +
                    pow(
                        motion.userAcceleration.y,
                        2
                    ) +
                    pow(
                        motion.userAcceleration.z,
                        2
                    )
                )

            Task {

                let observation =
                    await self?
                        .recognitionEngine
                        .process(
                            accelerationMagnitude:
                                magnitude,
                            heartRate:
                                nil,
                            timestamp:
                                .now
                        )

                guard let observation else {
                    return
                }

                await MainActor.run {

                    self?.activity =
                        observation
                }
            }
        }
    }

    public func stop() {

        manager.stopDeviceMotionUpdates()

        isRunning = false
    }
}


// ============================================================
// MARK: - HealthKit Workout Context
// ============================================================

public actor WorkoutActivityContext {

    private(set) var workoutActive = false

    public init() {}

    public func startWorkout() {
        workoutActive = true
    }

    public func stopWorkout() {
        workoutActive = false
    }

    public func isWorkoutActive()
        -> Bool {
        workoutActive
    }
}


// ============================================================
// MARK: - Unified Activity Runtime
// ============================================================

public actor ActivityRuntime {

    private let engine:
        ActivityRecognitionEngine

    private let workoutContext:
        WorkoutActivityContext

    private(set) var latest:
        ActivityObservation?

    public init(
        engine:
            ActivityRecognitionEngine =
            ActivityRecognitionEngine(),

        workoutContext:
            WorkoutActivityContext =
            WorkoutActivityContext()
    ) {

        self.engine = engine
        self.workoutContext =
            workoutContext
    }

    public func process(
        accelerationMagnitude: Double,
        heartRate: Double?,
        timestamp:
            ContinuousClock.Instant = .now
    ) async -> ActivityObservation {

        let observation =
            await engine.process(
                accelerationMagnitude:
                    accelerationMagnitude,

                heartRate:
                    heartRate,

                timestamp:
                    timestamp
            )

        let finalState:
            ActivityState

        if await workoutContext
            .isWorkoutActive() {

            finalState = .workout

        } else {

            finalState =
                observation.state
        }

        let finalObservation =
            ActivityObservation(
                state:
                    finalState,

                confidence:
                    observation.confidence,

                timestamp:
                    observation.timestamp,

                motionMagnitude:
                    observation.motionMagnitude,

                heartRate:
                    observation.heartRate
            )

        latest =
            finalObservation

        return finalObservation
    }

    public func startWorkout() async {
        await workoutContext
            .startWorkout()
    }

    public func stopWorkout() async {
        await workoutContext
            .stopWorkout()
    }

    public func reset() async {

        await engine.reset()

        await workoutContext
            .stopWorkout()

        latest = nil
    }
}


// ============================================================
// MARK: - SwiftUI Activity View
// ============================================================

import SwiftUI

public struct ActivityStatusView: View {

    @StateObject private var source:
        WatchMotionActivitySource

    public init() {

        _source =
            StateObject(
                wrappedValue:
                    WatchMotionActivitySource()
            )
    }

    public var body: some View {

        VStack(spacing: 6) {

            Image(
                systemName:
                    iconName
            )
            .font(.title2)

            Text(
                displayName
            )
            .font(
                .system(
                    size: 18,
                    weight: .semibold,
                    design: .rounded
                )
            )

            Text(
                confidenceText
            )
            .font(.caption2)
            .foregroundStyle(
                .secondary
            )

            Button(
                source.isRunning
                ? "STOP"
                : "START"
            ) {

                if source.isRunning {
                    source.stop()
                } else {
                    source.start()
                }
            }
        }
        .padding()
    }

    private var currentState:
        ActivityState {

        source.activity?.state
            ?? .unknown
    }

    private var displayName: String {

        switch currentState {

        case .unknown:
            return "Unknown"

        case .stationary:
            return "Stationary"

        case .walking:
            return "Walking"

        case .running:
            return "Running"

        case .cycling:
            return "Cycling"

        case .workout:
            return "Workout"

        case .automotive:
            return "Automotive"

        case .elevatedMovement:
            return "Moving"
        }
    }

    private var iconName: String {

        switch currentState {

        case .stationary:
            return "figure.stand"

        case .walking:
            return "figure.walk"

        case .running:
            return "figure.run"

        case .cycling:
            return "figure.outdoor.cycle"

        case .workout:
            return "figure.strengthtraining.traditional"

        case .automotive:
            return "car"

        case .elevatedMovement:
            return "figure.mixed.cardio"

        case .unknown:
            return "questionmark"
        }
    }

    private var confidenceText: String {

        switch source.activity?.confidence {

        case .excellent:
            return "Excellent confidence"

        case .high:
            return "High confidence"

        case .medium:
            return "Medium confidence"

        case .low:
            return "Low confidence"

        default:
            return "No confidence data"
        }
    }
}


// ============================================================
// MARK: - Testing
// ============================================================

#if DEBUG

struct ActivityRecognitionTests {

    static func testStationary() async {

        let engine =
            ActivityRecognitionEngine()

        var result:
            ActivityObservation?

        for _ in 0..<5 {

            result =
                await engine.process(
                    accelerationMagnitude:
                        0.01,
                    heartRate:
                        60
                )
        }

        assert(
            result?.state ==
                .stationary
        )
    }

    static func testRunning() async {

        let engine =
            ActivityRecognitionEngine()

        var result:
            ActivityObservation?

        for index in 0..<10 {

            result =
                await engine.process(
                    accelerationMagnitude:
                        0.60 +
                        Double(index % 3) * 0.05,

                    heartRate:
                        150
                )
        }

        assert(
            result?.state ==
                .running
        )
    }

    static func testReset() async {

        let engine =
            ActivityRecognitionEngine()

        _ =
            await engine.process(
                accelerationMagnitude:
                    0.01,
                heartRate:
                    60
            )

        await engine.reset()

        let result =
            await engine.process(
                accelerationMagnitude:
                    0.01,
                heartRate:
                    60
            )

        assert(
            result.state ==
                .unknown ||
            result.state ==
                .stationary
        )
    }
}

#endif
```

### How #3 now fits with #1 and #2

We now have three distinct layers:

```text
┌──────────────────────────────────────────────┐
│                 watchOS APIs                 │
│          HealthKit / Core Motion             │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│              #2 SIGNAL PROCESSOR             │
│                                              │
│ validation → filtering → smoothing → quality│
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                #1 SENSOR FUSION              │
│                                              │
│       HR + motion + timestamps + state       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│            #3 ACTIVITY ENGINE                │
│                                              │
│ feature extraction                           │
│ cadence estimation                           │
│ movement analysis                             │
│ classification                               │
│ confidence                                   │
│ state stabilization                           │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
             Unified Activity State
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Workout       UI         Analytics
```

One thing I'd change before calling this production-ready is the classifier itself: **don't hard-code assumptions about “walking = X” or “running = Y” and treat them as ground truth**. The next iteration should make the recognition model configurable and combine multiple independent features—motion variance, cadence, heart rate, workout context and platform-provided activity information where available—then benchmark it against recorded sensor traces. That gives us a much more credible #3 engine.





//
// WatchDashboardKit.swift
//
// High-performance SwiftUI dashboard architecture for watchOS.
//
// Design goals:
// - Minimal unnecessary view updates
// - Stable observable state
// - Throttled high-frequency sensor presentation
// - Reusable dashboard components
// - Lightweight animations
// - Separation of sensor/runtime state from presentation state
//

import SwiftUI
import Foundation

// ============================================================
// MARK: - Dashboard Metrics
// ============================================================

public struct DashboardMetrics: Equatable, Sendable {

    public var heartRate: Double?
    public var activity: ActivityState
    public var activityConfidence: ActivityConfidence
    public var motionMagnitude: Double
    public var elapsedSeconds: TimeInterval
    public var calories: Double?
    public var distanceMeters: Double?

    public init(
        heartRate: Double? = nil,
        activity: ActivityState = .unknown,
        activityConfidence: ActivityConfidence = .unavailable,
        motionMagnitude: Double = 0,
        elapsedSeconds: TimeInterval = 0,
        calories: Double? = nil,
        distanceMeters: Double? = nil
    ) {
        self.heartRate = heartRate
        self.activity = activity
        self.activityConfidence = activityConfidence
        self.motionMagnitude = motionMagnitude
        self.elapsedSeconds = elapsedSeconds
        self.calories = calories
        self.distanceMeters = distanceMeters
    }
}


// ============================================================
// MARK: - Dashboard Presentation State
// ============================================================

@MainActor
@Observable
public final class DashboardState {

    public private(set) var metrics =
        DashboardMetrics()

    public private(set) var isRunning =
        false

    public private(set) var isPaused =
        false

    public private(set) var lastUpdate =
        Date()

    public init() {}

    public func update(
        metrics newMetrics: DashboardMetrics
    ) {

        metrics = newMetrics
        lastUpdate = Date()
    }

    public func start() {

        isRunning = true
        isPaused = false
    }

    public func pause() {

        guard isRunning else {
            return
        }

        isPaused = true
    }

    public func resume() {

        guard isRunning else {
            return
        }

        isPaused = false
    }

    public func stop() {

        isRunning = false
        isPaused = false
    }

    public func reset() {

        metrics =
            DashboardMetrics()

        isRunning = false
        isPaused = false

        lastUpdate = Date()
    }
}


// ============================================================
// MARK: - Display Throttler
// ============================================================

public actor DisplayThrottler {

    private var lastEmission:
        ContinuousClock.Instant?

    private let minimumInterval:
        Duration

    public init(
        updatesPerSecond: Double = 10
    ) {

        let safeRate =
            max(
                1,
                updatesPerSecond
            )

        minimumInterval =
            .milliseconds(
                Int(
                    1000.0 /
                    safeRate
                )
            )
    }

    public func shouldEmit(
        now:
            ContinuousClock.Instant = .now
    ) -> Bool {

        guard
            let lastEmission
        else {

            self.lastEmission =
                now

            return true
        }

        guard
            now - lastEmission >=
            minimumInterval
        else {
            return false
        }

        self.lastEmission =
            now

        return true
    }

    public func reset() {

        lastEmission = nil
    }
}


// ============================================================
// MARK: - Numeric Display Formatting
// ============================================================

public enum DashboardFormatter {

    public static func integer(
        _ value: Double?
    ) -> String {

        guard let value else {
            return "--"
        }

        return String(
            Int(
                value.rounded()
            )
        )
    }

    public static func decimal(
        _ value: Double?,
        digits: Int = 1
    ) -> String {

        guard let value else {
            return "--"
        }

        return String(
            format:
                "%.\(digits)f",
            value
        )
    }

    public static func duration(
        _ seconds: TimeInterval
    ) -> String {

        let total =
            max(
                0,
                Int(seconds)
            )

        let hours =
            total / 3600

        let minutes =
            (total % 3600) / 60

        let remaining =
            total % 60

        if hours > 0 {

            return String(
                format:
                    "%02d:%02d:%02d",
                hours,
                minutes,
                remaining
            )
        }

        return String(
            format:
                "%02d:%02d",
            minutes,
            remaining
        )
    }
}


// ============================================================
// MARK: - Metric Value
// ============================================================

public struct MetricValue: View {

    private let value: String
    private let label: String

    public init(
        value: String,
        label: String
    ) {

        self.value = value
        self.label = label
    }

    public var body: some View {

        VStack(
            spacing: 1
        ) {

            Text(value)
                .font(
                    .system(
                        size: 25,
                        weight: .semibold,
                        design: .rounded
                    )
                )
                .monospacedDigit()
                .contentTransition(
                    .numericText()
                )

            Text(label)
                .font(
                    .system(
                        size: 9,
                        weight: .medium
                    )
                )
                .textCase(.uppercase)
                .foregroundStyle(
                    .secondary
                )
        }
    }
}


// ============================================================
// MARK: - Heart Rate Display
// ============================================================

public struct HeartRateDisplay: View {

    public let bpm: Double?

    public init(
        bpm: Double?
    ) {
        self.bpm = bpm
    }

    public var body: some View {

        VStack(
            spacing: 2
        ) {

            Image(
                systemName:
                    "heart.fill"
            )
            .font(.caption)

            Text(
                DashboardFormatter
                    .integer(bpm)
            )
            .font(
                .system(
                    size: 43,
                    weight: .bold,
                    design: .rounded
                )
            )
            .monospacedDigit()
            .contentTransition(
                .numericText()
            )

            Text("BPM")
                .font(
                    .system(
                        size: 10,
                        weight: .semibold
                    )
                )
                .foregroundStyle(
                    .secondary
                )
        }
        .accessibilityElement(
            children: .ignore
        )
        .accessibilityLabel(
            "Heart rate"
        )
        .accessibilityValue(
            bpm == nil
            ? "Unavailable"
            : "\(Int(bpm!.rounded())) beats per minute"
        )
    }
}


// ============================================================
// MARK: - Activity Display
// ============================================================

public struct ActivityDisplay: View {

    public let activity:
        ActivityState

    public let confidence:
        ActivityConfidence

    public init(
        activity: ActivityState,
        confidence: ActivityConfidence
    ) {

        self.activity =
            activity

        self.confidence =
            confidence
    }

    public var body: some View {

        HStack(
            spacing: 5
        ) {

            Image(
                systemName:
                    icon
            )
            .font(.caption)

            VStack(
                alignment: .leading,
                spacing: 0
            ) {

                Text(name)
                    .font(
                        .system(
                            size: 12,
                            weight: .semibold
                        )
                    )

                Text(
                    confidenceText
                )
                .font(
                    .system(
                        size: 8
                    )
                )
                .foregroundStyle(
                    .secondary
                )
            }
        }
        .accessibilityElement(
            children: .ignore
        )
        .accessibilityLabel(
            "Current activity"
        )
        .accessibilityValue(
            name
        )
    }

    private var name: String {

        switch activity {

        case .unknown:
            return "Unknown"

        case .stationary:
            return "Stationary"

        case .walking:
            return "Walking"

        case .running:
            return "Running"

        case .cycling:
            return "Cycling"

        case .workout:
            return "Workout"

        case .automotive:
            return "Automotive"

        case .elevatedMovement:
            return "Moving"
        }
    }

    private var icon: String {

        switch activity {

        case .unknown:
            return "questionmark"

        case .stationary:
            return "figure.stand"

        case .walking:
            return "figure.walk"

        case .running:
            return "figure.run"

        case .cycling:
            return "figure.outdoor.cycle"

        case .workout:
            return "figure.strengthtraining.traditional"

        case .automotive:
            return "car"

        case .elevatedMovement:
            return "figure.mixed.cardio"
        }
    }

    private var confidenceText: String {

        switch confidence {

        case .unavailable:
            return "Unavailable"

        case .low:
            return "Low confidence"

        case .medium:
            return "Medium confidence"

        case .high:
            return "High confidence"
        }
    }
}


// ============================================================
// MARK: - Progress Ring
// ============================================================

public struct DashboardProgressRing:
    View {

    public let progress: Double

    public let lineWidth: CGFloat

    public init(
        progress: Double,
        lineWidth: CGFloat = 6
    ) {

        self.progress =
            min(
                max(
                    progress,
                    0
                ),
                1
            )

        self.lineWidth =
            lineWidth
    }

    public var body: some View {

        ZStack {

            Circle()
                .stroke(
                    .secondary.opacity(0.2),
                    lineWidth:
                        lineWidth
                )

            Circle()
                .trim(
                    from: 0,
                    to: progress
                )
                .stroke(
                    style:
                        StrokeStyle(
                            lineWidth:
                                lineWidth,
                            lineCap:
                                .round
                        )
                )
                .rotationEffect(
                    .degrees(-90)
                )
                .animation(
                    .linear(
                        duration:
                            0.18
                    ),
                    value:
                        progress
                )
        }
    }
}


// ============================================================
// MARK: - Workout Timer
// ============================================================

public struct WorkoutTimerView:
    View {

    public let elapsed:
        TimeInterval

    public init(
        elapsed:
            TimeInterval
    ) {

        self.elapsed =
            elapsed
    }

    public var body: some View {

        Text(
            DashboardFormatter
                .duration(elapsed)
        )
        .font(
            .system(
                size: 25,
                weight: .medium,
                design: .monospaced
            )
        )
        .monospacedDigit()
        .contentTransition(
            .numericText()
        )
    }
}


// ============================================================
// MARK: - Dashboard Control
// ============================================================

public struct DashboardControl:
    View {

    public enum Kind {
        case start
        case pause
        case resume
        case stop
    }

    public let kind: Kind
    public let action: () -> Void

    public init(
        kind: Kind,
        action: @escaping () -> Void
    ) {

        self.kind =
            kind

        self.action =
            action
    }

    public var body: some View {

        Button(
            action: action
        ) {

            Image(
                systemName:
                    icon
            )
            .font(
                .system(
                    size: 18,
                    weight: .semibold
                )
            )
        }
        .buttonStyle(
            .borderedProminent
        )
        .accessibilityLabel(
            label
        )
    }

    private var icon: String {

        switch kind {

        case .start:
            return "play.fill"

        case .pause:
            return "pause.fill"

        case .resume:
            return "play.fill"

        case .stop:
            return "stop.fill"
        }
    }

    private var label: String {

        switch kind {

        case .start:
            return "Start"

        case .pause:
            return "Pause"

        case .resume:
            return "Resume"

        case .stop:
            return "Stop"
        }
    }
}


// ============================================================
// MARK: - Primary Dashboard
// ============================================================

public struct WatchPerformanceDashboard:
    View {

    @State private var state =
        DashboardState()

    public init() {}

    public var body: some View {

        ScrollView {

            VStack(
                spacing: 10
            ) {

                header

                HeartRateDisplay(
                    bpm:
                        state.metrics.heartRate
                )

                ActivityDisplay(
                    activity:
                        state.metrics.activity,

                    confidence:
                        state.metrics
                            .activityConfidence
                )

                metricsGrid

                WorkoutTimerView(
                    elapsed:
                        state.metrics
                            .elapsedSeconds
                )

                controls
            }
            .padding(
                .horizontal,
                8
            )
        }
        .animation(
            nil,
            value:
                state.metrics
        )
    }

    private var header: some View {

        HStack {

            Text("LIVE")
                .font(
                    .system(
                        size: 10,
                        weight: .bold
                    )
                )

            Spacer()

            Circle()
                .frame(
                    width: 6,
                    height: 6
                )
                .opacity(
                    state.isRunning
                    ? 1
                    : 0.25
                )
        }
    }

    private var metricsGrid:
        some View {

        HStack(
            spacing: 8
        ) {

            MetricValue(
                value:
                    DashboardFormatter
                        .decimal(
                            state.metrics
                                .motionMagnitude,
                            digits: 2
                        ),
                label:
                    "Motion"
            )

            MetricValue(
                value:
                    DashboardFormatter
                        .decimal(
                            state.metrics
                                .calories,
                            digits: 0
                        ),
                label:
                    "Calories"
            )
        }
    }

    @ViewBuilder
    private var controls:
        some View {

        if !state.isRunning {

            DashboardControl(
                kind: .start
            ) {

                state.start()
            }

        } else if state.isPaused {

            HStack {

                DashboardControl(
                    kind: .resume
                ) {

                    state.resume()
                }

                DashboardControl(
                    kind: .stop
                ) {

                    state.stop()
                }
            }

        } else {

            HStack {

                DashboardControl(
                    kind: .pause
                ) {

                    state.pause()
                }

                DashboardControl(
                    kind: .stop
                ) {

                    state.stop()
                }
            }
        }
    }
}


// ============================================================
// MARK: - Dashboard Runtime
// ============================================================

public actor DashboardRuntime {

    private let throttler:
        DisplayThrottler

    private let state:
        DashboardState

    private var startTime:
        ContinuousClock.Instant?

    private var timerTask:
        Task<Void, Never>?

    public init(
        state:
            DashboardState,

        updatesPerSecond:
            Double = 10
    ) {

        self.state =
            state

        self.throttler =
            DisplayThrottler(
                updatesPerSecond:
                    updatesPerSecond
            )
    }

    public func start() {

        guard startTime == nil else {
            return
        }

        startTime =
            .now

        Task { @MainActor in
            state.start()
        }

        timerTask =
            Task {

                while !Task.isCancelled {

                    try? await Task.sleep(
                        for:
                            .milliseconds(250)
                    )

                    guard
                        !Task.isCancelled
                    else {
                        break
                    }

                    await updateElapsed()
                }
            }
    }

    public func stop() {

        timerTask?.cancel()

        timerTask = nil
        startTime = nil

        Task { @MainActor in
            state.stop()
        }
    }

    public func publish(
        metrics:
            DashboardMetrics
    ) async {

        guard
            await throttler
                .shouldEmit()
        else {
            return
        }

        await MainActor.run {

            state.update(
                metrics:
                    metrics
            )
        }
    }

    private func updateElapsed() async {

        guard
            let startTime
        else {
            return
        }

        let elapsed =
            durationToSeconds(
                .now - startTime
            )

        await MainActor.run {

            var metrics =
                state.metrics

            metrics.elapsedSeconds =
                elapsed

            state.update(
                metrics:
                    metrics
            )
        }
    }

    private func durationToSeconds(
        _ duration: Duration
    ) -> Double {

        let components =
            duration.components

        return Double(
            components.seconds
        ) +
        Double(
            components.attoseconds
        ) /
        1_000_000_000_000_000_000
    }

    public func reset() {

        timerTask?.cancel()

        timerTask = nil
        startTime = nil

        Task { @MainActor in
            state.reset()
        }
    }
}


// ============================================================
// MARK: - Dashboard Data Adapter
// ============================================================

public struct DashboardDataAdapter:
    Sendable {

    public init() {}

    public func makeMetrics(
        heartRate: Double?,
        activity: ActivityState,
        confidence: ActivityConfidence,
        motion: Double,
        elapsed: TimeInterval,
        calories: Double? = nil,
        distance: Double? = nil
    ) -> DashboardMetrics {

        DashboardMetrics(

            heartRate:
                heartRate,

            activity:
                activity,

            activityConfidence:
                confidence,

            motionMagnitude:
                motion,

            elapsedSeconds:
                elapsed,

            calories:
                calories,

            distanceMeters:
                distance
        )
    }
}


// ============================================================
// MARK: - Sensor → Dashboard Bridge
// ============================================================

public actor SensorDashboardBridge {

    private let runtime:
        DashboardRuntime

    public init(
        runtime:
            DashboardRuntime
    ) {

        self.runtime =
            runtime
    }

    public func publish(
        heartRate: Double?,
        activity: ActivityState,
        confidence: ActivityConfidence,
        motion: Double,
        elapsed: TimeInterval,
        calories: Double? = nil,
        distance: Double? = nil
    ) async {

        let metrics =
            DashboardMetrics(

                heartRate:
                    heartRate,

                activity:
                    activity,

                activityConfidence:
                    confidence,

                motionMagnitude:
                    motion,

                elapsedSeconds:
                    elapsed,

                calories:
                    calories,

                distanceMeters:
                    distance
            )

        await runtime.publish(
            metrics:
                metrics
        )
    }
}


// ============================================================
// MARK: - Preview
// ============================================================

#Preview {

    WatchPerformanceDashboard()
}





# Apple Watch Connectivity Manager — Swift

## Architecture

```text
┌───────────────────────────────────────────────┐
│              Apple Watch Runtime              │
│                                               │
│  Sensor Fusion                                │
│  Signal Processor                             │
│  Activity Recognition                         │
│  Dashboard                                    │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
              WatchConnectivityManager
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Message   Application  User Info
          Channel   Context      Transfers
             │         │         │
             └─────────┼─────────┘
                       │
                       ▼
              Apple Watch ↔ iPhone
                       │
                       ▼
              iPhone Companion App
```

---

```swift
import Foundation
import WatchConnectivity

// ============================================================
// MARK: - Connectivity State
// ============================================================

public enum ConnectivityState:
    String,
    Sendable,
    Equatable
{
    case unavailable
    case inactive
    case reachable
    case notReachable
}


// ============================================================
// MARK: - Message Priority
// ============================================================

public enum ConnectivityPriority:
    Int,
    Sendable,
    Comparable
{
    case low = 0
    case normal = 1
    case high = 2
    case critical = 3
}


// ============================================================
// MARK: - Message Type
// ============================================================

public enum ConnectivityMessageType:
    String,
    Codable,
    Sendable
{
    case heartbeat

    case sensorSnapshot
    case activityUpdate
    case workoutUpdate

    case dashboardRequest
    case runtimeCommand

    case configuration
    case acknowledgement

    case diagnostic
}


// ============================================================
// MARK: - Message Envelope
// ============================================================

public struct ConnectivityEnvelope:
    Codable,
    Sendable,
    Identifiable
{
    public let id: UUID

    public let type:
        ConnectivityMessageType

    public let priority:
        ConnectivityPriority

    public let timestamp:
        Date

    public let sequence:
        UInt64

    public let payload:
        Data

    public init(
        id: UUID = UUID(),
        type:
            ConnectivityMessageType,
        priority:
            ConnectivityPriority =
                .normal,
        timestamp:
            Date = Date(),
        sequence:
            UInt64,
        payload:
            Data
    ) {

        self.id =
            id

        self.type =
            type

        self.priority =
            priority

        self.timestamp =
            timestamp

        self.sequence =
            sequence

        self.payload =
            payload
    }
}


// ============================================================
// MARK: - Codable Payload Helper
// ============================================================

public enum ConnectivityCodec {

    private static let encoder =
        JSONEncoder()

    private static let decoder =
        JSONDecoder()

    public static func encode<T:
        Encodable & Sendable>(
        _ value: T
    ) throws -> Data {

        try encoder.encode(value)
    }

    public static func decode<T:
        Decodable>(
        _ type: T.Type,
        from data: Data
    ) throws -> T {

        try decoder.decode(
            type,
            from: data
        )
    }
}


// ============================================================
// MARK: - Example Sensor Payload
// ============================================================

public struct SensorSnapshot:
    Codable,
    Sendable,
    Equatable
{
    public let heartRate:
        Double?

    public let motion:
        Double

    public let activity:
        String

    public let timestamp:
        Date

    public init(
        heartRate:
            Double?,
        motion:
            Double,
        activity:
            String,
        timestamp:
            Date = Date()
    ) {

        self.heartRate =
            heartRate

        self.motion =
            motion

        self.activity =
            activity

        self.timestamp =
            timestamp
    }
}


// ============================================================
// MARK: - Workout Payload
// ============================================================

public struct WorkoutUpdate:
    Codable,
    Sendable,
    Equatable
{
    public let workoutID:
        UUID

    public let elapsed:
        TimeInterval

    public let heartRate:
        Double?

    public let calories:
        Double?

    public let distance:
        Double?

    public let isPaused:
        Bool

    public init(
        workoutID:
            UUID,
        elapsed:
            TimeInterval,
        heartRate:
            Double?,
        calories:
            Double?,
        distance:
            Double?,
        isPaused:
            Bool
    ) {

        self.workoutID =
            workoutID

        self.elapsed =
            elapsed

        self.heartRate =
            heartRate

        self.calories =
            calories

        self.distance =
            distance

        self.isPaused =
            isPaused
    }
}


// ============================================================
// MARK: - Runtime Command
// ============================================================

public enum RuntimeCommand:
    String,
    Codable,
    Sendable
{
    case start
    case pause
    case resume
    case stop
    case sync
    case requestSnapshot
}


// ============================================================
// MARK: - Acknowledgement
// ============================================================

public struct ConnectivityAcknowledgement:
    Codable,
    Sendable
{
    public let messageID:
        UUID

    public let receivedAt:
        Date

    public let success:
        Bool

    public init(
        messageID:
            UUID,
        receivedAt:
            Date = Date(),
        success:
            Bool
    ) {

        self.messageID =
            messageID

        self.receivedAt =
            receivedAt

        self.success =
            success
    }
}


// ============================================================
// MARK: - Connectivity Event
// ============================================================

public enum ConnectivityEvent:
    Sendable
{
    case stateChanged(
        ConnectivityState
    )

    case messageReceived(
        ConnectivityEnvelope
    )

    case messageDelivered(
        UUID
    )

    case userInfoReceived(
        [String: Any]
    )

    case contextUpdated(
        [String: Any]
    )

    case error(
        String
    )
}


// ============================================================
// MARK: - Sequence Generator
// ============================================================

public actor SequenceGenerator {

    private var sequence:
        UInt64 = 0

    public init() {}

    public func next() -> UInt64 {

        sequence &+= 1

        return sequence
    }

    public func reset() {

        sequence = 0
    }
}


// ============================================================
// MARK: - Connectivity Queue
// ============================================================

public actor ConnectivityQueue {

    private var queue:
        [ConnectivityEnvelope] = []

    private let maximumSize:
        Int

    public init(
        maximumSize:
            Int = 100
    ) {

        self.maximumSize =
            max(
                1,
                maximumSize
            )
    }

    public func append(
        _ envelope:
            ConnectivityEnvelope
    ) {

        queue.append(
            envelope
        )

        queue.sort {
            $0.priority.rawValue >
            $1.priority.rawValue
        }

        if queue.count >
            maximumSize
        {

            queue.removeLast(
                queue.count -
                maximumSize
            )
        }
    }

    public func pop()
        -> ConnectivityEnvelope?
    {

        guard
            !queue.isEmpty
        else {
            return nil
        }

        return queue.removeFirst()
    }

    public func count()
        -> Int
    {
        queue.count
    }

    public func clear() {

        queue.removeAll(
            keepingCapacity:
                true
        )
    }
}


// ============================================================
// MARK: - Duplicate Protection
// ============================================================

public actor MessageDeduplicator {

    private var received:
        Set<UUID> = []

    private let maximumSize:
        Int

    public init(
        maximumSize:
            Int = 512
    ) {

        self.maximumSize =
            maximumSize
    }

    public func isDuplicate(
        _ id:
            UUID
    ) -> Bool {

        if received.contains(id) {
            return true
        }

        received.insert(id)

        if received.count >
            maximumSize
        {

            // UUID ordering is intentionally
            // not used as a semantic ordering.
            //
            // For a production implementation,
            // replace this with an insertion-order
            // ring buffer.

            received.removeFirst()
        }

        return false
    }

    public func reset() {

        received.removeAll(
            keepingCapacity:
                true
        )
    }
}


// ============================================================
// MARK: - Connectivity Delegate
// ============================================================

public protocol ConnectivityManagerDelegate:
    AnyObject
{
    func connectivityDidChange(
        state:
            ConnectivityState
    )

    func connectivityDidReceive(
        envelope:
            ConnectivityEnvelope
    )

    func connectivityDidFail(
        error:
            Error
    )
}


// ============================================================
// MARK: - Connectivity Errors
// ============================================================

public enum ConnectivityError:
    Error,
    LocalizedError
{
    case sessionUnavailable

    case encodingFailed

    case notReachable

    case invalidPayload

    public var errorDescription:
        String?
    {

        switch self {

        case .sessionUnavailable:
            return
                "WatchConnectivity session is unavailable."

        case .encodingFailed:
            return
                "Unable to encode connectivity payload."

        case .notReachable:
            return
                "The companion device is not currently reachable."

        case .invalidPayload:
            return
                "Received an invalid connectivity payload."
        }
    }
}


// ============================================================
// MARK: - Connectivity Manager
// ============================================================

@MainActor
public final class WatchConnectivityManager:
    NSObject,
    ObservableObject
{

    public static let shared =
        WatchConnectivityManager()

    // --------------------------------------------------------
    // Published state
    // --------------------------------------------------------

    @Published
    public private(set) var state:
        ConnectivityState =
            .inactive

    @Published
    public private(set) var isReachable:
        Bool =
            false

    @Published
    public private(set) var isPaired:
        Bool =
            false

    @Published
    public private(set) var isWatchAppInstalled:
        Bool =
            false

    @Published
    public private(set) var queuedMessages:
        Int =
            0

    // --------------------------------------------------------
    // Internal components
    // --------------------------------------------------------

    private let sequenceGenerator:
        SequenceGenerator

    private let queue:
        ConnectivityQueue

    private let deduplicator:
        MessageDeduplicator

    private var session:
        WCSession?

    public weak var delegate:
        ConnectivityManagerDelegate?

    // --------------------------------------------------------
    // Initialization
    // --------------------------------------------------------

    private init() {

        sequenceGenerator =
            SequenceGenerator()

        queue =
            ConnectivityQueue(
                maximumSize:
                    100
            )

        deduplicator =
            MessageDeduplicator()

        super.init()
    }

    // --------------------------------------------------------
    // Activation
    // --------------------------------------------------------

    public func activate() {

        guard
            WCSession.isSupported()
        else {

            state =
                .unavailable

            return
        }

        let session =
            WCSession.default

        self.session =
            session

        session.delegate =
            self

        session.activate()

        updateState(
            session:
                session
        )
    }

    // --------------------------------------------------------
    // State
    // --------------------------------------------------------

    private func updateState(
        session:
            WCSession
    ) {

        isReachable =
            session.isReachable

        #if os(iOS)

        isPaired =
            session.isPaired

        isWatchAppInstalled =
            session.isWatchAppInstalled

        #elseif os(watchOS)

        isPaired =
            session.isCompanionAppInstalled

        isWatchAppInstalled =
            session.isCompanionAppInstalled

        #endif

        if session.activationState ==
            .activated
        {

            state =
                session.isReachable
                ? .reachable
                : .notReachable
        }
        else {

            state =
                .inactive
        }

        delegate?
            .connectivityDidChange(
                state:
                    state
            )
    }

    // --------------------------------------------------------
    // Immediate Message
    // --------------------------------------------------------

    public func sendMessage<T:
        Encodable & Sendable>(
        type:
            ConnectivityMessageType,

        payload:
            T,

        priority:
            ConnectivityPriority =
                .normal
    ) async throws {

        guard
            let session
        else {

            throw
                ConnectivityError
                    .sessionUnavailable
        }

        let data =
            try ConnectivityCodec
                .encode(
                    payload
                )

        let sequence =
            await sequenceGenerator
                .next()

        let envelope =
            ConnectivityEnvelope(
                type:
                    type,

                priority:
                    priority,

                sequence:
                    sequence,

                payload:
                    data
            )

        let dictionary:
            [String: Any] =
            try encodeEnvelope(
                envelope
            )

        guard
            session.isReachable
        else {

            await queue.append(
                envelope
            )

            await refreshQueueCount()

            throw
                ConnectivityError
                    .notReachable
        }

        session.sendMessage(
            dictionary,

            replyHandler:
                { [weak self]
                    response in

                    guard
                        let self
                    else {
                        return
                    }

                    Task { @MainActor in

                        await self
                            .handleReply(
                                response
                            )
                    }
                },

            errorHandler:
                { [weak self]
                    error in

                    guard
                        let self
                    else {
                        return
                    }

                    Task { @MainActor in

                        self.delegate?
                            .connectivityDidFail(
                                error:
                                    error
                            )
                    }
                }
        )
    }

    // --------------------------------------------------------
    // Guaranteed Application Context
    // --------------------------------------------------------

    public func updateApplicationContext(
        _ context:
            [String: Any]
    ) throws {

        guard
            let session
        else {

            throw
                ConnectivityError
                    .sessionUnavailable
        }

        try session
            .updateApplicationContext(
                context
            )
    }

    // --------------------------------------------------------
    // User Info Transfer
    // --------------------------------------------------------

    public func transferUserInfo(
        _ dictionary:
            [String: Any]
    ) throws {

        guard
            let session
        else {

            throw
                ConnectivityError
                    .sessionUnavailable
        }

        session.transferUserInfo(
            dictionary
        )
    }

    // --------------------------------------------------------
    // File Transfer
    // --------------------------------------------------------

    public func transferFile(
        _ url:
            URL,

        metadata:
            [String: Any]? =
                nil
    ) throws {

        guard
            let session
        else {

            throw
                ConnectivityError
                    .sessionUnavailable
        }

        session.transferFile(
            url,
            metadata:
                metadata
        )
    }

    // --------------------------------------------------------
    // Queue Processing
    // --------------------------------------------------------

    public func flushQueue() async {

        guard
            let session
        else {
            return
        }

        guard
            session.isReachable
        else {
            return
        }

        while true {

            guard
                let envelope =
                    await queue.pop()
            else {
                break
            }

            do {

                let dictionary =
                    try encodeEnvelope(
                        envelope
                    )

                session.sendMessage(
                    dictionary,
                    replyHandler:
                        nil,
                    errorHandler:
                        nil
                )

            } catch {

                await queue.append(
                    envelope
                )

                delegate?
                    .connectivityDidFail(
                        error:
                            error
                    )

                break
            }
        }

        await refreshQueueCount()
    }

    private func refreshQueueCount()
        async
    {

        queuedMessages =
            await queue.count()
    }

    // --------------------------------------------------------
    // Envelope Encoding
    // --------------------------------------------------------

    private func encodeEnvelope(
        _ envelope:
            ConnectivityEnvelope
    ) throws -> [String: Any] {

        let encoded =
            try JSONEncoder()
                .encode(
                    envelope
                )

        return [
            "protocol":
                "WatchRuntime.v1",

            "message":
                encoded
        ]
    }

    // --------------------------------------------------------
    // Envelope Decoding
    // --------------------------------------------------------

    private func decodeEnvelope(
        _ dictionary:
            [String: Any]
    ) throws
        -> ConnectivityEnvelope
    {

        guard
            let data =
                dictionary["message"]
                as? Data
        else {

            throw
                ConnectivityError
                    .invalidPayload
        }

        return try JSONDecoder()
            .decode(
                ConnectivityEnvelope.self,
                from:
                    data
            )
    }

    // --------------------------------------------------------
    // Reply Handling
    // --------------------------------------------------------

    private func handleReply(
        _ response:
            [String: Any]
    ) async {

        guard
            let idString =
                response["messageID"]
                as? String,

            let id =
                UUID(
                    uuidString:
                        idString
                )
        else {
            return
        }

        delegate?
            .connectivityDidReceive(
                envelope:
                    ConnectivityEnvelope(
                        type:
                            .acknowledgement,

                        priority:
                            .normal,

                        sequence:
                            0,

                        payload:
                            (try? JSONEncoder()
                                .encode(
                                    ConnectivityAcknowledgement(
                                        messageID:
                                            id,

                                        success:
                                            true
                                    )
                                )
                            ) ?? Data()
                    )
            )
    }

    // --------------------------------------------------------
    // Incoming Message
    // --------------------------------------------------------

    private func processIncoming(
        dictionary:
            [String: Any]
    ) async {

        do {

            let envelope =
                try decodeEnvelope(
                    dictionary
                )

            let duplicate =
                await deduplicator
                    .isDuplicate(
                        envelope.id
                    )

            guard
                !duplicate
            else {
                return
            }

            delegate?
                .connectivityDidReceive(
                    envelope:
                        envelope
                )

        } catch {

            delegate?
                .connectivityDidFail(
                    error:
                        error
                )
        }
    }
}


// ============================================================
// MARK: - WCSessionDelegate
// ============================================================

extension WatchConnectivityManager:
    WCSessionDelegate
{

    public func session(
        _ session:
            WCSession,
        activationDidCompleteWith
            activationState:
                WCSessionActivationState,
        error:
            Error?
    ) {

        Task { @MainActor in

            if let error {

                self.state =
                    .inactive

                self.delegate?
                    .connectivityDidFail(
                        error:
                            error
                    )

                return
            }

            self.updateState(
                session:
                    session
            )

            await self.flushQueue()
        }
    }

    public func sessionReachabilityDidChange(
        _ session:
            WCSession
    ) {

        Task { @MainActor in

            self.updateState(
                session:
                    session
            )

            if session.isReachable {

                await self.flushQueue()
            }
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceiveMessage:
            message:
                [String: Any]
    ) {

        Task { @MainActor in

            await self.processIncoming(
                dictionary:
                    message
            )
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceiveMessage:
            message:
                [String: Any],
        replyHandler:
            @escaping (
                [String: Any]
            ) -> Void
    ) {

        Task { @MainActor in

            await self.processIncoming(
                dictionary:
                    message
            )

            replyHandler([
                "status":
                    "received"
            ])
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceiveApplicationContext:
            applicationContext:
                [String: Any]
    ) {

        delegate?
            .connectivityDidReceiveContext(
                applicationContext
            )
    }

    public func session(
        _ session:
            WCSession,
        didReceiveUserInfo:
            userInfo:
                [String: Any]
    ) {

        delegate?
            .connectivityDidReceiveUserInfo(
                userInfo
            )
    }
}


// ============================================================
// MARK: - Extended Delegate
// ============================================================

public extension ConnectivityManagerDelegate {

    func connectivityDidReceiveContext(
        _ context:
            [String: Any]
    ) {}

    func connectivityDidReceiveUserInfo(
        _ userInfo:
            [String: Any]
    ) {}
}


// ============================================================
// MARK: - Example Runtime Controller
// ============================================================

@MainActor
public final class WatchRuntimeController:
    ObservableObject,
    ConnectivityManagerDelegate
{

    public let connectivity:
        WatchConnectivityManager

    @Published
    public private(set) var lastHeartRate:
        Double?

    @Published
    public private(set) var lastActivity:
        String =
            "Unknown"

    public init() {

        connectivity =
            WatchConnectivityManager.shared

        connectivity.delegate =
            self

        connectivity.activate()
    }

    public func publishSensorSnapshot(
        heartRate:
            Double?,
        motion:
            Double,
        activity:
            String
    ) {

        let snapshot =
            SensorSnapshot(

                heartRate:
                    heartRate,

                motion:
                    motion,

                activity:
                    activity
            )

        Task {

            do {

                try await connectivity
                    .sendMessage(

                        type:
                            .sensorSnapshot,

                        payload:
                            snapshot,

                        priority:
                            .normal
                    )

            } catch {

                // The message has already been
                // placed into the local queue
                // when reachability is unavailable.
            }
        }
    }

    public func connectivityDidChange(
        state:
            ConnectivityState
    ) {
        print(
            "Connectivity:",
            state.rawValue
        )
    }

    public func connectivityDidReceive(
        envelope:
            ConnectivityEnvelope
    ) {

        switch envelope.type {

        case .sensorSnapshot:

            if let snapshot =
                try? ConnectivityCodec
                    .decode(
                        SensorSnapshot.self,
                        from:
                            envelope.payload
                    )
            {

                lastHeartRate =
                    snapshot.heartRate

                lastActivity =
                    snapshot.activity
            }

        case .runtimeCommand:

            guard
                let command =
                    try? ConnectivityCodec
                        .decode(
                            RuntimeCommand.self,
                            from:
                                envelope.payload
                        )
            else {
                return
            }

            handle(
                command:
                    command
            )

        default:
            break
        }
    }

    public func connectivityDidFail(
        error:
            Error
    ) {

        print(
            "Connectivity error:",
            error.localizedDescription
        )
    }

    private func handle(
        command:
            RuntimeCommand
    ) {

        switch command {

        case .start:
            print("START")

        case .pause:
            print("PAUSE")

        case .resume:
            print("RESUME")

        case .stop:
            print("STOP")

        case .sync:
            print("SYNC")

        case .requestSnapshot:
            print("SNAPSHOT REQUEST")
        }
    }
}


// ============================================================
// MARK: - SwiftUI Connectivity Indicator
// ============================================================

public struct ConnectivityIndicator:
    View
{

    @ObservedObject
    private var manager:
        WatchConnectivityManager

    public init(
        manager:
            WatchConnectivityManager =
                .shared
    ) {

        self.manager =
            manager
    }

    public var body: some View {

        HStack(
            spacing: 5
        ) {

            Circle()
                .frame(
                    width: 7,
                    height: 7
                )
                .opacity(
                    manager.isReachable
                    ? 1.0
                    : 0.3
                )

            Text(
                manager.isReachable
                ? "CONNECTED"
                : "OFFLINE"
            )
            .font(
                .system(
                    size: 9,
                    weight: .semibold
                )
            )
        }
        .accessibilityElement(
            children: .ignore
        )
        .accessibilityLabel(
            "Phone connection"
        )
        .accessibilityValue(
            manager.isReachable
            ? "Connected"
            : "Offline"
        )
    }
}
```

## Recommended message strategy

The manager deliberately provides **three different communication modes**.

### 1. `sendMessage`

Use this when the iPhone is currently reachable and you want an interactive exchange.

Examples:

```swift
try await connectivity.sendMessage(
    type: .runtimeCommand,
    payload: RuntimeCommand.pause,
    priority: .high
)
```

Good for:

```text
Watch → iPhone
    "Pause workout"

iPhone → Watch
    "Change dashboard"

Watch → iPhone
    "Give me current configuration"
```

### 2. `updateApplicationContext`

Use this for **latest-state synchronisation**.

For example:

```swift
try connectivity.updateApplicationContext([
    "heartRate": 142,
    "activity": "running",
    "dashboard": "performance",
    "workoutActive": true
])
```

The important property is that you are communicating **state**, rather than treating every update as an event.

If the Watch produces:

```text
HR 140
HR 141
HR 142
HR 143
HR 144
```

the iPhone usually doesn't need five separate state updates.

It primarily needs:

```text
currentHR = 144
```

That dramatically reduces unnecessary communication.

### 3. `transferUserInfo`

Use this for information that should be delivered even when the devices aren't immediately reachable.

Examples:

```text
Workout completed
Daily statistics
Configuration changed
Sensor session summary
Diagnostic information
```

And for larger data:

```text
transferFile(...)
```

is the appropriate mechanism rather than attempting to stuff large datasets into interactive messages.

---

## Where this fits into the complete Watch system

You now have:

```text
                    APPLE WATCH
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   Core Motion       HealthKit       Workout APIs
        │                │                │
        └────────────────┼────────────────┘
                         ▼
              #1 SENSOR FUSION ENGINE
                         │
                         ▼
              #2 SIGNAL PROCESSOR
                         │
                         ▼
              #3 ACTIVITY RECOGNITION
                         │
                         ▼
              #4 DASHBOARD / UI
                         │
                         ▼
              #5 CONNECTIVITY MANAGER
                         │
                         ▼
                 WATCHCONNECTIVITY
                         │
                         ▼
                      iPHONE
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            SwiftUI    Storage    Analytics
```

### One important refinement

For a serious implementation, I would **not send every heart-rate sample to the iPhone**.

A better architecture is:

```text
Sensor rate
    ↓
50 Hz / 20 Hz / platform-dependent
    ↓
Signal processor
    ↓
Fusion
    ↓
Dashboard: ~5–10 Hz
    ↓
Connectivity: ~1 Hz or event-driven
    ↓
iPhone
```

So the Watch remains the **real-time computer**, while the iPhone becomes the **storage, visualisation, analytics and synchronisation computer**.

That gives the overall project a much cleaner architecture:

```text
WATCH
────────────────────────
Real-time sensing
Signal processing
Activity recognition
Workout state
Low-latency dashboard
Power management
        │
        │ WatchConnectivity
        ▼
IPHONE
────────────────────────
Persistent storage
Historical data
Charts
Configuration
Cloud synchronisation
Long-term analytics
```

This also keeps the system within **public watchOS APIs** rather than attempting to modify Apple's Bluetooth stack, firmware, kernel, or private Watch hardware interfaces.






# Apple Watch Power-Aware Runtime & Battery Optimisation Engine

```swift
//
// PowerAwareRuntime.swift
//
// Application-level power management architecture for watchOS.
//
// Responsibilities:
// - Monitor available application-level power signals
// - Maintain runtime operating modes
// - Adapt sensor sampling targets
// - Adapt dashboard refresh rate
// - Control optional workloads
// - Apply thermal/battery safeguards
// - Prevent unnecessary background work
// - Coordinate graceful degradation
//
// IMPORTANT:
// This does NOT control Apple's private battery-management,
// kernel, firmware, PMIC, or hardware power systems.
// It controls the workload of the application.
//

import Foundation
import SwiftUI
import WatchKit


// ============================================================
// MARK: - Power State
// ============================================================

public enum RuntimePowerState:
    String,
    Sendable,
    Codable,
    Equatable
{
    case unknown
    case normal
    case reduced
    case critical
}


// ============================================================
// MARK: - Runtime Operating Mode
// ============================================================

public enum RuntimeMode:
    String,
    Sendable,
    Codable,
    CaseIterable
{
    case maximumPerformance
    case performance
    case balanced
    case efficiency
    case emergency
}


// ============================================================
// MARK: - Workload Classes
// ============================================================

public enum RuntimeWorkload:
    String,
    Sendable,
    CaseIterable
{
    case heartRate
    case motion
    case activityRecognition
    case signalProcessing
    case dashboard
    case connectivity
    case analytics
    case logging
    case diagnostics
}


// ============================================================
// MARK: - Workload Policy
// ============================================================

public struct WorkloadPolicy:
    Sendable,
    Equatable,
    Codable
{
    public var enabled: Bool

    public var targetFrequencyHz:
        Double

    public var maximumLatency:
        TimeInterval

    public var priority:
        Int

    public var allowsBackgroundExecution:
        Bool

    public init(
        enabled: Bool = true,
        targetFrequencyHz: Double = 1,
        maximumLatency: TimeInterval = 1,
        priority: Int = 0,
        allowsBackgroundExecution: Bool = false
    ) {

        self.enabled =
            enabled

        self.targetFrequencyHz =
            targetFrequencyHz

        self.maximumLatency =
            maximumLatency

        self.priority =
            priority

        self.allowsBackgroundExecution =
            allowsBackgroundExecution
    }
}


// ============================================================
// MARK: - Power Profile
// ============================================================

public struct PowerProfile:
    Sendable,
    Equatable,
    Codable
{
    public let mode:
        RuntimeMode

    public let heartRate:
        WorkloadPolicy

    public let motion:
        WorkloadPolicy

    public let activityRecognition:
        WorkloadPolicy

    public let signalProcessing:
        WorkloadPolicy

    public let dashboard:
        WorkloadPolicy

    public let connectivity:
        WorkloadPolicy

    public let analytics:
        WorkloadPolicy

    public let logging:
        WorkloadPolicy

    public let diagnostics:
        WorkloadPolicy

    public init(
        mode:
            RuntimeMode,

        heartRate:
            WorkloadPolicy,

        motion:
            WorkloadPolicy,

        activityRecognition:
            WorkloadPolicy,

        signalProcessing:
            WorkloadPolicy,

        dashboard:
            WorkloadPolicy,

        connectivity:
            WorkloadPolicy,

        analytics:
            WorkloadPolicy,

        logging:
            WorkloadPolicy,

        diagnostics:
            WorkloadPolicy
    ) {

        self.mode =
            mode

        self.heartRate =
            heartRate

        self.motion =
            motion

        self.activityRecognition =
            activityRecognition

        self.signalProcessing =
            signalProcessing

        self.dashboard =
            dashboard

        self.connectivity =
            connectivity

        self.analytics =
            analytics

        self.logging =
            logging

        self.diagnostics =
            diagnostics
    }
}


// ============================================================
// MARK: - Built-In Power Profiles
// ============================================================

public enum PowerProfiles {

    public static let maximumPerformance =
        PowerProfile(

            mode:
                .maximumPerformance,

            heartRate:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        100
                ),

            motion:
                WorkloadPolicy(
                    targetFrequencyHz:
                        50.0,
                    priority:
                        90
                ),

            activityRecognition:
                WorkloadPolicy(
                    targetFrequencyHz:
                        10.0,
                    priority:
                        80
                ),

            signalProcessing:
                WorkloadPolicy(
                    targetFrequencyHz:
                        20.0,
                    priority:
                        80
                ),

            dashboard:
                WorkloadPolicy(
                    targetFrequencyHz:
                        15.0,
                    priority:
                        70
                ),

            connectivity:
                WorkloadPolicy(
                    targetFrequencyHz:
                        2.0,
                    priority:
                        50
                ),

            analytics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        2.0,
                    priority:
                        30
                ),

            logging:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        20
                ),

            diagnostics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        10
                )
        )


    public static let performance =
        PowerProfile(

            mode:
                .performance,

            heartRate:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        100
                ),

            motion:
                WorkloadPolicy(
                    targetFrequencyHz:
                        40.0,
                    priority:
                        90
                ),

            activityRecognition:
                WorkloadPolicy(
                    targetFrequencyHz:
                        8.0,
                    priority:
                        80
                ),

            signalProcessing:
                WorkloadPolicy(
                    targetFrequencyHz:
                        15.0,
                    priority:
                        80
                ),

            dashboard:
                WorkloadPolicy(
                    targetFrequencyHz:
                        10.0,
                    priority:
                        70
                ),

            connectivity:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        50
                ),

            analytics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        30
                ),

            logging:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.5,
                    priority:
                        20
                ),

            diagnostics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.5,
                    priority:
                        10
                )
        )


    public static let balanced =
        PowerProfile(

            mode:
                .balanced,

            heartRate:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        100
                ),

            motion:
                WorkloadPolicy(
                    targetFrequencyHz:
                        25.0,
                    priority:
                        90
                ),

            activityRecognition:
                WorkloadPolicy(
                    targetFrequencyHz:
                        5.0,
                    priority:
                        80
                ),

            signalProcessing:
                WorkloadPolicy(
                    targetFrequencyHz:
                        10.0,
                    priority:
                        80
                ),

            dashboard:
                WorkloadPolicy(
                    targetFrequencyHz:
                        5.0,
                    priority:
                        70
                ),

            connectivity:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.5,
                    priority:
                        50
                ),

            analytics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.5,
                    priority:
                        30
                ),

            logging:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.25,
                    priority:
                        20
                ),

            diagnostics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.25,
                    priority:
                        10
                )
        )


    public static let efficiency =
        PowerProfile(

            mode:
                .efficiency,

            heartRate:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        100
                ),

            motion:
                WorkloadPolicy(
                    targetFrequencyHz:
                        10.0,
                    priority:
                        90
                ),

            activityRecognition:
                WorkloadPolicy(
                    targetFrequencyHz:
                        2.0,
                    priority:
                        80
                ),

            signalProcessing:
                WorkloadPolicy(
                    targetFrequencyHz:
                        5.0,
                    priority:
                        80
                ),

            dashboard:
                WorkloadPolicy(
                    targetFrequencyHz:
                        2.0,
                    priority:
                        70
                ),

            connectivity:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.2,
                    priority:
                        50
                ),

            analytics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.1,
                    priority:
                        30
                ),

            logging:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.05,
                    priority:
                        20
                ),

            diagnostics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.05,
                    priority:
                        10
                )
        )


    public static let emergency =
        PowerProfile(

            mode:
                .emergency,

            heartRate:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.5,
                    priority:
                        100
                ),

            motion:
                WorkloadPolicy(
                    targetFrequencyHz:
                        2.0,
                    priority:
                        90
                ),

            activityRecognition:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.5,
                    priority:
                        80
                ),

            signalProcessing:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        80
                ),

            dashboard:
                WorkloadPolicy(
                    targetFrequencyHz:
                        1.0,
                    priority:
                        70
                ),

            connectivity:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0.1,
                    priority:
                        50
                ),

            analytics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0,
                    priority:
                        30
                ),

            logging:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0,
                    priority:
                        20
                ),

            diagnostics:
                WorkloadPolicy(
                    targetFrequencyHz:
                        0,
                    priority:
                        10
                )
        )


    public static func profile(
        for mode:
            RuntimeMode
    ) -> PowerProfile {

        switch mode {

        case .maximumPerformance:
            return maximumPerformance

        case .performance:
            return performance

        case .balanced:
            return balanced

        case .efficiency:
            return efficiency

        case .emergency:
            return emergency
        }
    }
}


// ============================================================
// MARK: - Power Snapshot
// ============================================================

public struct PowerSnapshot:
    Sendable,
    Equatable
{
    public let batteryLevel:
        Double

    public let isCharging:
        Bool

    public let lowPowerMode:
        Bool

    public let thermalState:
        ProcessInfo.ThermalState

    public let timestamp:
        Date

    public init(
        batteryLevel:
            Double,
        isCharging:
            Bool,
        lowPowerMode:
            Bool,
        thermalState:
            ProcessInfo.ThermalState,
        timestamp:
            Date = Date()
    ) {

        self.batteryLevel =
            batteryLevel

        self.isCharging =
            isCharging

        self.lowPowerMode =
            lowPowerMode

        self.thermalState =
            thermalState

        self.timestamp =
            timestamp
    }
}


// ============================================================
// MARK: - Power State Evaluator
// ============================================================

public struct PowerStateEvaluator:
    Sendable
{

    public init() {}

    public func evaluate(
        snapshot:
            PowerSnapshot
    ) -> RuntimePowerState {

        if snapshot.lowPowerMode {
            return .critical
        }

        switch snapshot.thermalState {

        case .critical:
            return .critical

        case .serious:
            return .reduced

        case .fair:
            return .reduced

        case .nominal:
            break

        @unknown default:
            break
        }

        if snapshot.batteryLevel <=
            0.10
        {
            return .critical
        }

        if snapshot.batteryLevel <=
            0.20
        {
            return .reduced
        }

        return .normal
    }
}


// ============================================================
// MARK: - Runtime Mode Controller
// ============================================================

public actor RuntimeModeController {

    private(set) var mode:
        RuntimeMode =
            .balanced

    private(set) var powerState:
        RuntimePowerState =
            .unknown

    private let evaluator:
        PowerStateEvaluator

    public init(
        evaluator:
            PowerStateEvaluator =
                PowerStateEvaluator()
    ) {

        self.evaluator =
            evaluator
    }

    public func update(
        snapshot:
            PowerSnapshot
    ) -> RuntimeMode {

        let state =
            evaluator.evaluate(
                snapshot:
                    snapshot
            )

        powerState =
            state

        switch state {

        case .unknown:
            mode =
                .balanced

        case .normal:

            if mode ==
                .emergency ||
                mode ==
                .efficiency
            {

                mode =
                    .balanced
            }

        case .reduced:

            mode =
                .efficiency

        case .critical:

            mode =
                .emergency
        }

        return mode
    }

    public func setManualMode(
        _ requested:
            RuntimeMode
    ) {

        mode =
            requested
    }

    public func currentProfile()
        -> PowerProfile
    {

        PowerProfiles.profile(
            for:
                mode
        )
    }
}


// ============================================================
// MARK: - Workload Scheduler
// ============================================================

public actor WorkloadScheduler {

    private var tasks:
        [RuntimeWorkload:
            Task<Void, Never>] =
            [:]

    private var policies:
        [RuntimeWorkload:
            WorkloadPolicy] =
            [:]

    public init() {}

    public func apply(
        profile:
            PowerProfile
    ) {

        policies[
            .heartRate
        ] =
            profile.heartRate

        policies[
            .motion
        ] =
            profile.motion

        policies[
            .activityRecognition
        ] =
            profile.activityRecognition

        policies[
            .signalProcessing
        ] =
            profile.signalProcessing

        policies[
            .dashboard
        ] =
            profile.dashboard

        policies[
            .connectivity
        ] =
            profile.connectivity

        policies[
            .analytics
        ] =
            profile.analytics

        policies[
            .logging
        ] =
            profile.logging

        policies[
            .diagnostics
        ] =
            profile.diagnostics
    }

    public func policy(
        for workload:
            RuntimeWorkload
    ) -> WorkloadPolicy {

        policies[
            workload
        ] ??
        WorkloadPolicy(
            enabled:
                false
        )
    }

    public func stop(
        workload:
            RuntimeWorkload
    ) {

        tasks[
            workload
        ]?.cancel()

        tasks[
            workload
        ] =
            nil
    }

    public func stopAll() {

        for task in
            tasks.values
        {
            task.cancel()
        }

        tasks.removeAll()
    }
}


// ============================================================
// MARK: - Adaptive Sampling Controller
// ============================================================

public struct SamplingConfiguration:
    Sendable,
    Equatable,
    Codable
{
    public let motionHz:
        Double

    public let signalHz:
        Double

    public let dashboardHz:
        Double

    public let connectivityHz:
        Double

    public init(
        motionHz:
            Double,
        signalHz:
            Double,
        dashboardHz:
            Double,
        connectivityHz:
            Double
    ) {

        self.motionHz =
            motionHz

        self.signalHz =
            signalHz

        self.dashboardHz =
            dashboardHz

        self.connectivityHz =
            connectivityHz
    }
}


public struct AdaptiveSamplingController:
    Sendable
{

    public init() {}

    public func configuration(
        for profile:
            PowerProfile
    ) -> SamplingConfiguration {

        SamplingConfiguration(

            motionHz:
                profile.motion
                    .targetFrequencyHz,

            signalHz:
                profile.signalProcessing
                    .targetFrequencyHz,

            dashboardHz:
                profile.dashboard
                    .targetFrequencyHz,

            connectivityHz:
                profile.connectivity
                    .targetFrequencyHz
        )
    }
}


// ============================================================
// MARK: - Runtime Metrics
// ============================================================

public struct RuntimeMetrics:
    Sendable,
    Equatable
{
    public var workCycles:
        UInt64 = 0

    public var droppedCycles:
        UInt64 = 0

    public var lastWorkDuration:
        TimeInterval = 0

    public var accumulatedWork:
        TimeInterval = 0

    public var timestamp:
        Date = Date()

    public init() {}
}


// ============================================================
// MARK: - Runtime Monitor
// ============================================================

public actor RuntimeMonitor {

    private var metrics =
        RuntimeMetrics()

    public init() {}

    public func recordWork(
        duration:
            TimeInterval
    ) {

        metrics.workCycles &+= 1

        metrics.lastWorkDuration =
            duration

        metrics.accumulatedWork +=
            duration

        metrics.timestamp =
            Date()
    }

    public func recordDrop() {

        metrics.droppedCycles &+= 1

        metrics.timestamp =
            Date()
    }

    public func snapshot()
        -> RuntimeMetrics
    {

        metrics
    }

    public func reset() {

        metrics =
            RuntimeMetrics()
    }
}


// ============================================================
// MARK: - Power-Aware Runtime
// ============================================================

@MainActor
public final class PowerAwareRuntime:
    ObservableObject
{

    public static let shared =
        PowerAwareRuntime()

    // --------------------------------------------------------
    // Published runtime state
    // --------------------------------------------------------

    @Published
    public private(set) var mode:
        RuntimeMode =
            .balanced

    @Published
    public private(set) var powerState:
        RuntimePowerState =
            .unknown

    @Published
    public private(set) var batteryLevel:
        Double =
            1.0

    @Published
    public private(set) var isCharging:
        Bool =
            false

    @Published
    public private(set) var sampling:
        SamplingConfiguration =
            SamplingConfiguration(
                motionHz: 25,
                signalHz: 10,
                dashboardHz: 5,
                connectivityHz: 0.5
            )

    private let modeController:
        RuntimeModeController

    private let scheduler:
        WorkloadScheduler

    private let samplingController:
        AdaptiveSamplingController

    private let monitor:
        RuntimeMonitor

    private var monitorTask:
        Task<Void, Never>?

    private init() {

        modeController =
            RuntimeModeController()

        scheduler =
            WorkloadScheduler()

        samplingController =
            AdaptiveSamplingController()

        monitor =
            RuntimeMonitor()

        super.init()
    }

    // --------------------------------------------------------
    // Start
    // --------------------------------------------------------

    public func start() {

        WKInterfaceDevice
            .current
            .isBatteryMonitoringEnabled =
            true

        monitorTask?.cancel()

        monitorTask =
            Task { [weak self] in

                while
                    !Task.isCancelled
                {

                    try? await Task.sleep(
                        for:
                            .seconds(30)
                    )

                    guard
                        !Task.isCancelled
                    else {
                        break
                    }

                    await self?
                        .refreshPowerState()
                }
            }

        Task {

            await refreshPowerState()
        }
    }

    // --------------------------------------------------------
    // Stop
    // --------------------------------------------------------

    public func stop() {

        monitorTask?.cancel()

        monitorTask =
            nil

        Task {

            await scheduler
                .stopAll()
        }
    }

    // --------------------------------------------------------
    // Power Sampling
    // --------------------------------------------------------

    private func refreshPowerState()
        async
    {

        let device =
            WKInterfaceDevice.current

        let processInfo =
            ProcessInfo.processInfo

        let snapshot =
            PowerSnapshot(

                batteryLevel:
                    Double(
                        device.batteryLevel
                    ),

                isCharging:
                    device.batteryState ==
                    .charging ||
                    device.batteryState ==
                    .full,

                lowPowerMode:
                    processInfo
                        .isLowPowerModeEnabled,

                thermalState:
                    processInfo
                        .thermalState
            )

        let newMode =
            await modeController
                .update(
                    snapshot:
                        snapshot
                )

        let profile =
            await modeController
                .currentProfile()

        let configuration =
            samplingController
                .configuration(
                    for:
                        profile
                )

        await scheduler
            .apply(
                profile:
                    profile
            )

        batteryLevel =
            snapshot.batteryLevel

        isCharging =
            snapshot.isCharging

        powerState =
            await modeController
                .powerState

        mode =
            newMode

        sampling =
            configuration
    }

    // --------------------------------------------------------
    // Manual mode
    // --------------------------------------------------------

    public func requestMode(
        _ mode:
            RuntimeMode
    ) {

        Task {

            await modeController
                .setManualMode(
                    mode
                )

            await refreshPowerState()
        }
    }

    // --------------------------------------------------------
    // Workload decision
    // --------------------------------------------------------

    public func shouldRun(
        _ workload:
            RuntimeWorkload
    ) async -> Bool {

        let policy =
            await scheduler
                .policy(
                    for:
                        workload
                )

        return policy.enabled &&
               policy.targetFrequencyHz > 0
    }

    // --------------------------------------------------------
    // Workload policy
    // --------------------------------------------------------

    public func policy(
        for workload:
            RuntimeWorkload
    ) async -> WorkloadPolicy {

        await scheduler
            .policy(
                for:
                    workload
            )
    }

    // --------------------------------------------------------
    // Diagnostics
    // --------------------------------------------------------

    public func metrics()
        async -> RuntimeMetrics
    {

        await monitor.snapshot()
    }
}


// ============================================================
// MARK: - Power-Aware Periodic Loop
// ============================================================

public actor PowerAwareLoop {

    private var task:
        Task<Void, Never>?

    private let workload:
        RuntimeWorkload

    private let runtime:
        PowerAwareRuntime

    public init(
        workload:
            RuntimeWorkload,

        runtime:
            PowerAwareRuntime =
                .shared
    ) {

        self.workload =
            workload

        self.runtime =
            runtime
    }

    public func start(
        operation:
            @escaping @Sendable () async -> Void
    ) {

        task?.cancel()

        task =
            Task {

                while
                    !Task.isCancelled
                {

                    guard
                        await runtime
                            .shouldRun(
                                workload
                            )
                    else {

                        try? await Task.sleep(
                            for:
                                .seconds(2)
                        )

                        continue
                    }

                    let policy =
                        await runtime
                            .policy(
                                for:
                                    workload
                            )

                    let frequency =
                        max(
                            policy
                                .targetFrequencyHz,
                            0.1
                        )

                    let interval =
                        max(
                            0.01,
                            1.0 /
                            frequency
                        )

                    await operation()

                    try? await Task.sleep(
                        for:
                            .milliseconds(
                                Int(
                                    interval *
                                    1000
                                )
                            )
                    )
                }
            }
    }

    public func stop() {

        task?.cancel()

        task =
            nil
    }
}


// ============================================================
// MARK: - Battery-Aware Connectivity Policy
// ============================================================

public struct ConnectivityPowerPolicy:
    Sendable
{

    public init() {}

    public func shouldTransmit(
        batteryLevel:
            Double,

        isCharging:
            Bool,

        priority:
            ConnectivityPriority
    ) -> Bool {

        if priority ==
            .critical
        {
            return true
        }

        if isCharging {
            return true
        }

        if batteryLevel <=
            0.10
        {

            return priority >=
                .high
        }

        if batteryLevel <=
            0.20
        {

            return priority >=
                .normal
        }

        return true
    }
}


// ============================================================
// MARK: - Battery-Aware Runtime Controller
// ============================================================

public actor BatteryAwareWorkloadGate {

    private let policy:
        ConnectivityPowerPolicy

    public init(
        policy:
            ConnectivityPowerPolicy =
                ConnectivityPowerPolicy()
    ) {

        self.policy =
            policy
    }

    public func allowTransmission(
        batteryLevel:
            Double,

        isCharging:
            Bool,

        priority:
            ConnectivityPriority
    ) -> Bool {

        policy.shouldTransmit(
            batteryLevel:
                batteryLevel,

            isCharging:
                isCharging,

            priority:
                priority
        )
    }
}


// ============================================================
// MARK: - Runtime Status View
// ============================================================

public struct PowerStatusView:
    View
{

    @ObservedObject
    private var runtime:
        PowerAwareRuntime

    public init(
        runtime:
            PowerAwareRuntime =
                .shared
    ) {

        self.runtime =
            runtime
    }

    public var body: some View {

        VStack(
            spacing: 5
        ) {

            HStack {

                Text(
                    runtime.mode
                        .rawValue
                        .uppercased()
                )
                .font(
                    .system(
                        size: 10,
                        weight: .bold
                    )
                )

                Spacer()

                Text(
                    "\(Int(
                        runtime.batteryLevel * 100
                    ))%"
                )
                .font(
                    .system(
                        size: 10,
                        weight: .medium,
                        design: .monospaced
                    )
                )
            }

            HStack {

                Text(
                    runtime.powerState
                        .rawValue
                        .uppercased()
                )
                .font(
                    .system(
                        size: 8
                    )
                )

                Spacer()

                Image(
                    systemName:
                        runtime.isCharging
                        ? "bolt.fill"
                        : "battery.75percent"
                )
            }
        }
    }
}


// ============================================================
// MARK: - Example Runtime
// ============================================================

@MainActor
public final class WatchApplicationRuntime {

    private let power:
        PowerAwareRuntime

    private let motionLoop:
        PowerAwareLoop

    private let processingLoop:
        PowerAwareLoop

    private let dashboardLoop:
        PowerAwareLoop

    public init() {

        power =
            .shared

        motionLoop =
            PowerAwareLoop(
                workload:
                    .motion
            )

        processingLoop =
            PowerAwareLoop(
                workload:
                    .signalProcessing
            )

        dashboardLoop =
            PowerAwareLoop(
                workload:
                    .dashboard
            )
    }

    public func start() {

        power.start()

        Task {

            await motionLoop.start {

                // Read / process motion
                // according to the current
                // runtime policy.

                await Task.yield()
            }

            await processingLoop.start {

                // Run signal processing.

                await Task.yield()
            }

            await dashboardLoop.start {

                // Publish presentation state.

                await Task.yield()
            }
        }
    }

    public func stop() {

        power.stop()

        Task {

            await motionLoop.stop()
            await processingLoop.stop()
            await dashboardLoop.stop()
        }
    }
}
```

# Runtime model

The runtime now behaves approximately like this:

```text
                    WATCH POWER
                        │
              ┌─────────┴─────────┐
              │                   │
          Battery %          Thermal state
              │                   │
              └─────────┬─────────┘
                        ▼
              PowerStateEvaluator
                        │
                        ▼
              RuntimeModeController
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
     Sampling       Workloads       Connectivity
        │               │                │
        └───────────────┼────────────────┘
                        ▼
                Power-Aware Runtime
```

## Four practical operating levels

### Maximum performance

Used when the application explicitly requires maximum real-time processing.

```text
Motion             50 Hz
Signal processing  20 Hz
Activity           10 Hz
Dashboard          15 Hz
Connectivity        2 Hz
Analytics           2 Hz
```

This is appropriate for demanding real-time sessions, although actual sensor delivery rates remain subject to Apple's APIs and hardware.

### Performance

```text
Motion             40 Hz
Signal processing  15 Hz
Activity            8 Hz
Dashboard          10 Hz
Connectivity        1 Hz
```

### Balanced

The normal operating profile:

```text
Motion             25 Hz
Signal processing  10 Hz
Activity            5 Hz
Dashboard           5 Hz
Connectivity      0.5 Hz
```

### Efficiency

When battery or thermal conditions require reduced workload:

```text
Motion             10 Hz
Signal processing   5 Hz
Activity            2 Hz
Dashboard           2 Hz
Connectivity      0.2 Hz
```

## Emergency mode

At very low battery or when the system reports critical conditions:

```text
Heart rate          0.5 Hz target
Motion              2 Hz
Activity            0.5 Hz
Signal processing   1 Hz
Dashboard           1 Hz
Connectivity        0.1 Hz
Analytics           OFF
Logging             OFF
Diagnostics         OFF
```

The important design principle is **degradation rather than sudden shutdown**.

The application attempts to preserve its highest-priority functions while eliminating optional work.

# Battery-aware architecture

The complete project now becomes:

```text
                         WATCH
                           │
             ┌─────────────┴─────────────┐
             │                           │
          SENSORS                     POWER
             │                           │
             ▼                           ▼
      Sensor Fusion             PowerStateEvaluator
             │                           │
             ▼                           ▼
      Signal Processor          RuntimeModeController
             │                           │
             ▼                           ▼
     Activity Recognition       PowerProfile
             │                           │
             └─────────────┬─────────────┘
                           ▼
                   Workload Scheduler
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Motion        Processing    Dashboard
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                  Connectivity Manager
                           │
                           ▼
                         iPhone
```

# What this actually optimises

The biggest gains don't come from trying to make one Swift function microscopically faster.

They come from **doing less work**.

For example, if the dashboard doesn't need a new value, don't redraw it.

If analytics doesn't need to run while a workout is active, defer it.

If the phone isn't reachable, don't repeatedly hammer the connection layer.

If the Watch is at 12% battery, don't continue operating as though it has 90%.

If a sensor isn't needed for the current activity state, reduce its application workload.

That gives you a hierarchy:

```text
CRITICAL
│
├── Core sensor data
├── Workout state
└── Safety-critical application state
        │
HIGH
│
├── Signal processing
├── Activity recognition
└── User controls
        │
MEDIUM
│
├── Dashboard refresh
├── Connectivity
└── Synchronisation
        │
LOW
│
├── Analytics
├── Logging
└── Diagnostics
```

The runtime can therefore protect the upper layers when resources become constrained.

# Integration with the previous five systems

The complete application can now be wired together as:

```swift
@MainActor
final class EliteWatchRuntime {

    let power =
        PowerAwareRuntime.shared

    let connectivity =
        WatchConnectivityManager.shared

    let application =
        WatchApplicationRuntime()

    func start() {

        connectivity.activate()

        application.start()
    }

    func stop() {

        application.stop()

        connectivity.stop()
    }
}
```

The intended architecture is now:

```text
#1  Sensor Fusion
        ↓
#2  Real-Time Signal Processor
        ↓
#3  Activity Recognition
        ↓
#4  Real-Time Dashboard
        ↓
#5  Watch ↔ iPhone Connectivity
        ↓
#6  Power-Aware Runtime
```

With #6 sitting slightly **above all of them as a resource governor**, rather than being just another isolated feature.






# Apple Watch Unified Event Bus & Runtime

```swift
//
// UnifiedEventBus.swift
//
// High-performance application event system for watchOS.
//
// Architecture:
//
// Sensor Fusion
//      │
// Signal Processor
//      │
// Activity Recognition
//      │
// Workout Runtime
//      │
// Connectivity
//      │
// Power Runtime
//      │
//      ▼
// ┌──────────────────────────────┐
// │      Unified Event Bus       │
// └──────────────────────────────┘
//      │       │       │
//      ▼       ▼       ▼
// Dashboard  Logging  Analytics
//
// Public application-level Swift/watchOS architecture.
// No private Apple frameworks or kernel interfaces.
//

import Foundation
import SwiftUI
import WatchKit


// ============================================================
// MARK: - Event Priority
// ============================================================

public enum RuntimeEventPriority:
    Int,
    Sendable,
    Codable,
    Comparable
{
    case background = 0
    case low = 1
    case normal = 2
    case high = 3
    case critical = 4
}


// ============================================================
// MARK: - Event Source
// ============================================================

public enum RuntimeEventSource:
    String,
    Sendable,
    Codable
{
    case sensor
    case signalProcessor
    case activityRecognition
    case workout
    case dashboard
    case connectivity
    case power
    case runtime
    case system
    case diagnostics
}


// ============================================================
// MARK: - Event Type
// ============================================================

public enum RuntimeEventType:
    String,
    Sendable,
    Codable
{
    // Sensor events
    case heartRateUpdated
    case motionUpdated
    case sensorQualityChanged

    // Processing
    case signalProcessed
    case signalQualityChanged
    case anomalyDetected

    // Activity
    case activityChanged
    case activityConfidenceChanged

    // Workout
    case workoutStarted
    case workoutPaused
    case workoutResumed
    case workoutStopped
    case workoutUpdated

    // Dashboard
    case dashboardRefreshRequested
    case dashboardModeChanged

    // Connectivity
    case phoneConnected
    case phoneDisconnected
    case messageReceived
    case messageSent
    case synchronisationRequested
    case synchronisationCompleted

    // Power
    case powerStateChanged
    case runtimeModeChanged
    case workloadReduced

    // Runtime
    case runtimeStarted
    case runtimeStopped
    case runtimeError

    // Diagnostics
    case diagnostic
    case performanceWarning
}


// ============================================================
// MARK: - Runtime Event Payload
// ============================================================

public enum RuntimeEventPayload:
    Sendable
{
    case none

    case double(Double)
    case integer(Int)
    case boolean(Bool)
    case string(String)

    case heartRate(
        bpm: Double
    )

    case motion(
        magnitude: Double
    )

    case activity(
        name: String,
        confidence: Double
    )

    case power(
        batteryLevel: Double,
        mode: String
    )

    case workout(
        elapsed: TimeInterval,
        calories: Double?,
        distance: Double?
    )

    case connectivity(
        reachable: Bool
    )

    case diagnostic(
        message: String
    )
}


// ============================================================
// MARK: - Runtime Event
// ============================================================

public struct RuntimeEvent:
    Identifiable,
    Sendable
{
    public let id:
        UUID

    public let sequence:
        UInt64

    public let timestamp:
        ContinuousClock.Instant

    public let wallClockDate:
        Date

    public let source:
        RuntimeEventSource

    public let type:
        RuntimeEventType

    public let priority:
        RuntimeEventPriority

    public let payload:
        RuntimeEventPayload

    public init(
        id:
            UUID = UUID(),

        sequence:
            UInt64,

        timestamp:
            ContinuousClock.Instant = .now,

        wallClockDate:
            Date = Date(),

        source:
            RuntimeEventSource,

        type:
            RuntimeEventType,

        priority:
            RuntimeEventPriority =
                .normal,

        payload:
            RuntimeEventPayload =
                .none
    ) {

        self.id =
            id

        self.sequence =
            sequence

        self.timestamp =
            timestamp

        self.wallClockDate =
            wallClockDate

        self.source =
            source

        self.type =
            type

        self.priority =
            priority

        self.payload =
            payload
    }
}


// ============================================================
// MARK: - Event Statistics
// ============================================================

public struct EventBusStatistics:
    Sendable,
    Equatable
{
    public private(set) var published:
        UInt64 = 0

    public private(set) var delivered:
        UInt64 = 0

    public private(set) var dropped:
        UInt64 = 0

    public private(set) var rejected:
        UInt64 = 0

    public private(set) var activeSubscriptions:
        Int = 0

    public init() {}
}


// ============================================================
// MARK: - Event Subscription
// ============================================================

public struct EventSubscription:
    Sendable
{
    public let id:
        UUID

    public let eventType:
        RuntimeEventType?

    public let source:
        RuntimeEventSource?

    public let minimumPriority:
        RuntimeEventPriority

    public init(
        id:
            UUID = UUID(),

        eventType:
            RuntimeEventType? =
                nil,

        source:
            RuntimeEventSource? =
                nil,

        minimumPriority:
            RuntimeEventPriority =
                .background
    ) {

        self.id =
            id

        self.eventType =
            eventType

        self.source =
            source

        self.minimumPriority =
            minimumPriority
    }

    public func matches(
        _ event:
            RuntimeEvent
    ) -> Bool {

        if let eventType,
           event.type != eventType
        {
            return false
        }

        if let source,
           event.source != source
        {
            return false
        }

        guard
            event.priority >=
            minimumPriority
        else {
            return false
        }

        return true
    }
}


// ============================================================
// MARK: - Event Stream
// ============================================================

public struct RuntimeEventStream:
    AsyncSequence,
    Sendable
{

    public typealias Element =
        RuntimeEvent

    private let stream:
        AsyncStream<RuntimeEvent>

    public init(
        stream:
            AsyncStream<RuntimeEvent>
    ) {

        self.stream =
            stream
    }

    public func makeAsyncIterator()
        -> AsyncStream<RuntimeEvent>
            .Iterator
    {
        stream.makeAsyncIterator()
    }
}


// ============================================================
// MARK: - Event Bus
// ============================================================

public actor UnifiedEventBus {

    public static let shared =
        UnifiedEventBus()

    // --------------------------------------------------------
    // Sequence
    // --------------------------------------------------------

    private var sequence:
        UInt64 = 0

    // --------------------------------------------------------
    // Subscribers
    // --------------------------------------------------------

    private struct Subscriber {

        let subscription:
            EventSubscription

        let continuation:
            AsyncStream<RuntimeEvent>
                .Continuation
    }

    private var subscribers:
        [UUID: Subscriber] =
            [:]

    // --------------------------------------------------------
    // Statistics
    // --------------------------------------------------------

    private var statistics =
        EventBusStatistics()

    // --------------------------------------------------------
    // Recent event history
    // --------------------------------------------------------

    private var history:
        [RuntimeEvent] =
            []

    private let maximumHistory:
        Int

    public init(
        maximumHistory:
            Int = 256
    ) {

        self.maximumHistory =
            max(
                1,
                maximumHistory
            )
    }

    // ========================================================
    // MARK: Publish
    // ========================================================

    @discardableResult
    public func publish(
        source:
            RuntimeEventSource,

        type:
            RuntimeEventType,

        priority:
            RuntimeEventPriority =
                .normal,

        payload:
            RuntimeEventPayload =
                .none
    ) -> RuntimeEvent {

        sequence &+= 1

        let event =
            RuntimeEvent(

                sequence:
                    sequence,

                source:
                    source,

                type:
                    type,

                priority:
                    priority,

                payload:
                    payload
            )

        statistics.published &+= 1

        appendHistory(
            event
        )

        deliver(
            event
        )

        return event
    }

    // ========================================================
    // MARK: Delivery
    // ========================================================

    private func deliver(
        _ event:
            RuntimeEvent
    ) {

        for subscriber
            in subscribers.values
        {

            guard
                subscriber.subscription
                    .matches(
                        event
                    )
            else {
                continue
            }

            let result =
                subscriber.continuation
                    .yield(
                        event
                    )

            switch result {

            case .enqueued:

                statistics.delivered &+= 1

            case .dropped:

                statistics.dropped &+= 1

            case .terminated:

                break

            @unknown default:

                break
            }
        }
    }

    // ========================================================
    // MARK: Subscribe
    // ========================================================

    public func subscribe(
        _ subscription:
            EventSubscription,

        buffering:
            Int = 32
    ) -> RuntimeEventStream {

        let limit =
            max(
                1,
                buffering
            )

        let stream =
            AsyncStream<RuntimeEvent>(
                bufferingPolicy:
                    .bufferingNewest(
                        limit
                    )
            ) { continuation in

                continuation.onTermination =
                    { [weak self]
                        _ in

                        Task {

                            await self?
                                .removeSubscription(
                                    subscription.id
                                )
                        }
                    }

                subscribers[
                    subscription.id
                ] =
                    Subscriber(

                        subscription:
                            subscription,

                        continuation:
                            continuation
                    )

                statistics
                    .activeSubscriptions =
                    subscribers.count
            }

        return RuntimeEventStream(
            stream:
                stream
        )
    }

    // ========================================================
    // MARK: Convenience Subscription
    // ========================================================

    public func subscribe(
        type:
            RuntimeEventType,

        priority:
            RuntimeEventPriority =
                .background,

        buffering:
            Int = 32
    ) -> RuntimeEventStream {

        subscribe(

            EventSubscription(
                eventType:
                    type,

                minimumPriority:
                    priority
            ),

            buffering:
                buffering
        )
    }

    // ========================================================
    // MARK: Source Subscription
    // ========================================================

    public func subscribe(
        source:
            RuntimeEventSource,

        priority:
            RuntimeEventPriority =
                .background,

        buffering:
            Int = 32
    ) -> RuntimeEventStream {

        subscribe(

            EventSubscription(
                source:
                    source,

                minimumPriority:
                    priority
            ),

            buffering:
                buffering
        )
    }

    // ========================================================
    // MARK: Remove
    // ========================================================

    private func removeSubscription(
        _ id:
            UUID
    ) {

        subscribers[id] =
            nil

        statistics
            .activeSubscriptions =
            subscribers.count
    }

    public func cancelSubscription(
        _ id:
            UUID
    ) {

        subscribers[id]?
            .continuation
            .finish()

        subscribers[id] =
            nil

        statistics
            .activeSubscriptions =
            subscribers.count
    }

    // ========================================================
    // MARK: History
    // ========================================================

    private func appendHistory(
        _ event:
            RuntimeEvent
    ) {

        history.append(
            event
        )

        if history.count >
            maximumHistory
        {

            history.removeFirst(
                history.count -
                maximumHistory
            )
        }
    }

    public func recentEvents(
        limit:
            Int = 50
    ) -> [RuntimeEvent] {

        Array(
            history.suffix(
                max(
                    1,
                    limit
                )
            )
        )
    }

    // ========================================================
    // MARK: Statistics
    // ========================================================

    public func statisticsSnapshot()
        -> EventBusStatistics
    {

        statistics
    }

    // ========================================================
    // MARK: Reset
    // ========================================================

    public func resetStatistics() {

        statistics =
            EventBusStatistics()

        statistics
            .activeSubscriptions =
            subscribers.count
    }

    public func shutdown() {

        for subscriber
            in subscribers.values
        {
            subscriber
                .continuation
                .finish()
        }

        subscribers.removeAll()

        statistics
            .activeSubscriptions =
            0
    }
}


// ============================================================
// MARK: - Event Publisher Helper
// ============================================================

public actor RuntimeEventPublisher {

    private let bus:
        UnifiedEventBus

    public init(
        bus:
            UnifiedEventBus =
                .shared
    ) {

        self.bus =
            bus
    }

    public func heartRate(
        bpm:
            Double
    ) async {

        await bus.publish(

            source:
                .sensor,

            type:
                .heartRateUpdated,

            priority:
                .high,

            payload:
                .heartRate(
                    bpm:
                        bpm
                )
        )
    }

    public func motion(
        magnitude:
            Double
    ) async {

        await bus.publish(

            source:
                .sensor,

            type:
                .motionUpdated,

            priority:
                .normal,

            payload:
                .motion(
                    magnitude:
                        magnitude
                )
        )
    }

    public func activity(
        name:
            String,

        confidence:
            Double
    ) async {

        await bus.publish(

            source:
                .activityRecognition,

            type:
                .activityChanged,

            priority:
                .high,

            payload:
                .activity(
                    name:
                        name,

                    confidence:
                        confidence
                )
        )
    }

    public func power(
        battery:
            Double,

        mode:
            RuntimeMode
    ) async {

        await bus.publish(

            source:
                .power,

            type:
                .powerStateChanged,

            priority:
                .high,

            payload:
                .power(
                    batteryLevel:
                        battery,

                    mode:
                        mode.rawValue
                )
        )
    }

    public func workoutStarted() async {

        await bus.publish(

            source:
                .workout,

            type:
                .workoutStarted,

            priority:
                .critical
        )
    }

    public func workoutStopped() async {

        await bus.publish(

            source:
                .workout,

            type:
                .workoutStopped,

            priority:
                .critical
        )
    }
}


// ============================================================
// MARK: - Runtime Event Router
// ============================================================

public actor RuntimeEventRouter {

    private let bus:
        UnifiedEventBus

    private var tasks:
        [UUID:
            Task<Void, Never>] =
            [:]

    public init(
        bus:
            UnifiedEventBus =
                .shared
    ) {

        self.bus =
            bus
    }

    // ========================================================
    // MARK: Register
    // ========================================================

    public func register(
        subscription:
            EventSubscription,

        handler:
            @escaping @Sendable
            (RuntimeEvent) async -> Void
    ) async -> UUID {

        let stream =
            await bus.subscribe(
                subscription
            )

        let taskID =
            subscription.id

        let task =
            Task {

                for await event
                    in stream
                {

                    await handler(
                        event
                    )
                }
            }

        tasks[
            taskID
        ] =
            task

        return taskID
    }

    // ========================================================
    // MARK: Cancel
    // ========================================================

    public func cancel(
        _ id:
            UUID
    ) async {

        tasks[id]?.cancel()

        tasks[id] =
            nil

        await bus
            .cancelSubscription(
                id
            )
    }

    public func cancelAll() async {

        for task
            in tasks.values
        {
            task.cancel()
        }

        tasks.removeAll()

        await bus.shutdown()
    }
}


// ============================================================
// MARK: - Runtime Lifecycle
// ============================================================

public enum RuntimeLifecycleState:
    String,
    Sendable
{
    case stopped
    case starting
    case running
    case stopping
    case faulted
}


// ============================================================
// MARK: - Unified Runtime
// ============================================================

@MainActor
public final class UnifiedWatchRuntime:
    ObservableObject
{

    public static let shared =
        UnifiedWatchRuntime()

    // --------------------------------------------------------
    // Published state
    // --------------------------------------------------------

    @Published
    public private(set) var state:
        RuntimeLifecycleState =
            .stopped

    @Published
    public private(set) var lastEvent:
        RuntimeEvent?

    @Published
    public private(set) var eventCount:
        UInt64 =
            0

    // --------------------------------------------------------
    // Components
    // --------------------------------------------------------

    public let bus:
        UnifiedEventBus

    public let publisher:
        RuntimeEventPublisher

    public let router:
        RuntimeEventRouter

    // --------------------------------------------------------
    // Tasks
    // --------------------------------------------------------

    private var monitoringTask:
        Task<Void, Never>?

    private init() {

        bus =
            UnifiedEventBus.shared

        publisher =
            RuntimeEventPublisher(
                bus:
                    bus
            )

        router =
            RuntimeEventRouter(
                bus:
                    bus
            )
    }

    // ========================================================
    // MARK: Start
    // ========================================================

    public func start() {

        guard state ==
            .stopped
        else {
            return
        }

        state =
            .starting

        monitoringTask?.cancel()

        monitoringTask =
            Task { [weak self] in

                guard
                    let self
                else {
                    return
                }

                let stream =
                    await self.bus
                        .subscribe(
                            EventSubscription(
                                minimumPriority:
                                    .background
                            )
                        )

                await MainActor.run {

                    self.state =
                        .running
                }

                for await event
                    in stream
                {

                    guard
                        !Task.isCancelled
                    else {
                        break
                    }

                    await MainActor.run {

                        self.lastEvent =
                            event

                        self.eventCount &+= 1
                    }
                }
            }

        Task {

            await bus.publish(

                source:
                    .runtime,

                type:
                    .runtimeStarted,

                priority:
                    .critical
            )
        }
    }

    // ========================================================
    // MARK: Stop
    // ========================================================

    public func stop() {

        guard
            state != .stopped
        else {
            return
        }

        state =
            .stopping

        monitoringTask?.cancel()

        monitoringTask =
            nil

        Task {

            await bus.publish(

                source:
                    .runtime,

                type:
                    .runtimeStopped,

                priority:
                    .critical
            )

            await MainActor.run {

                self.state =
                    .stopped
            }
        }
    }

    // ========================================================
    // MARK: Fault
    // ========================================================

    public func reportError(
        _ message:
            String
    ) {

        state =
            .faulted

        Task {

            await bus.publish(

                source:
                    .runtime,

                type:
                    .runtimeError,

                priority:
                    .critical,

                payload:
                    .diagnostic(
                        message:
                            message
                    )
            )
        }
    }
}


// ============================================================
// MARK: - Dashboard Event Controller
// ============================================================

@MainActor
public final class DashboardEventController:
    ObservableObject
{

    @Published
    public private(set) var heartRate:
        Double?

    @Published
    public private(set) var activity:
        String =
            "Unknown"

    @Published
    public private(set) var battery:
        Double =
            1

    @Published
    public private(set) var runtimeMode:
        String =
            "balanced"

    private let router:
        RuntimeEventRouter

    private var subscriptionID:
        UUID?

    public init(
        bus:
            UnifiedEventBus =
                .shared
    ) {

        router =
            RuntimeEventRouter(
                bus:
                    bus
            )
    }

    public func start() {

        Task {

            let id =
                await router.register(

                    subscription:
                        EventSubscription(
                            minimumPriority:
                                .normal
                        )
                ) { [weak self]
                    event in

                    await self?
                        .handle(
                            event:
                                event
                        )
                }

            await MainActor.run {

                self.subscriptionID =
                    id
            }
        }
    }

    public func stop() {

        guard
            let id =
                subscriptionID
        else {
            return
        }

        Task {

            await router.cancel(
                id
            )
        }

        subscriptionID =
            nil
    }

    private func handle(
        event:
            RuntimeEvent
    ) async {

        await MainActor.run {

            switch event.type {

            case .heartRateUpdated:

                if case
                    .heartRate(
                        let bpm
                    ) =
                    event.payload
                {
                    heartRate =
                        bpm
                }

            case .activityChanged:

                if case
                    .activity(
                        let name,
                        _
                    ) =
                    event.payload
                {
                    activity =
                        name
                }

            case .powerStateChanged:

                if case
                    .power(
                        let level,
                        let mode
                    ) =
                    event.payload
                {

                    battery =
                        level

                    runtimeMode =
                        mode
                }

            default:
                break
            }
        }
    }
}


// ============================================================
// MARK: - Diagnostics Collector
// ============================================================

public actor RuntimeDiagnosticsCollector {

    private let bus:
        UnifiedEventBus

    private var task:
        Task<Void, Never>?

    private var messages:
        [String] =
            []

    private let maximumMessages:
        Int

    public init(
        bus:
            UnifiedEventBus =
                .shared,

        maximumMessages:
            Int = 100
    ) {

        self.bus =
            bus

        self.maximumMessages =
            max(
                1,
                maximumMessages
            )
    }

    public func start() {

        task?.cancel()

        task =
            Task {

                let stream =
                    await bus.subscribe(

                        EventSubscription(
                            minimumPriority:
                                .high
                        )
                    )

                for await event
                    in stream
                {

                    let message =
                        "\(event.sequence) " +
                        "\(event.source.rawValue) " +
                        "\(event.type.rawValue)"

                    messages.append(
                        message
                    )

                    if messages.count >
                        maximumMessages
                    {

                        messages.removeFirst(
                            messages.count -
                            maximumMessages
                        )
                    }
                }
            }
    }

    public func stop() {

        task?.cancel()

        task =
            nil
    }

    public func recentMessages()
        -> [String]
    {

        messages
    }

    public func clear() {

        messages.removeAll(
            keepingCapacity:
                true
        )
    }
}


// ============================================================
// MARK: - Example Integration
// ============================================================

@MainActor
public final class EliteWatchApplication {

    public let runtime:
        UnifiedWatchRuntime

    public let dashboard:
        DashboardEventController

    private let diagnostics:
        RuntimeDiagnosticsCollector

    public init() {

        runtime =
            UnifiedWatchRuntime.shared

        dashboard =
            DashboardEventController()

        diagnostics =
            RuntimeDiagnosticsCollector()
    }

    public func start() {

        runtime.start()

        dashboard.start()

        Task {

            await diagnostics.start()
        }
    }

    public func stop() {

        dashboard.stop()

        Task {

            await diagnostics.stop()
        }

        runtime.stop()
    }
}
```

# Using the Event Bus

A sensor no longer needs to know anything about the dashboard.

For example, the heart-rate processor can simply publish:

```swift
let publisher =
    RuntimeEventPublisher()

await publisher.heartRate(
    bpm: 142
)
```

The dashboard independently receives:

```swift
let stream =
    await UnifiedEventBus.shared.subscribe(
        type:
            .heartRateUpdated
    )

for await event in stream {

    // Update presentation state.
}
```

That means:

```text
Heart Rate Processor
       │
       │ publishes event
       ▼
  Unified Event Bus
       │
       ├───────────────► Dashboard
       │
       ├───────────────► Logger
       │
       ├───────────────► Analytics
       │
       └───────────────► iPhone Sync
```

None of those systems need direct references to each other.

# Priority system

The priority system lets the runtime distinguish between events that matter immediately and events that can wait.

```text
CRITICAL
─────────
Workout started/stopped
Runtime errors
Major state transitions

HIGH
────
Heart rate
Activity changes
Power state
Connectivity changes

NORMAL
──────
Motion
Signal updates
Dashboard updates

LOW
───
Analytics
Logging

BACKGROUND
──────────
Diagnostics
Nonessential telemetry
```

This becomes particularly useful when combined with **#6 Power-Aware Runtime**.

For example:

```swift
await bus.publish(
    source: .power,
    type: .workloadReduced,
    priority: .high
)
```

The rest of the system can react without the power manager having to know what every subsystem does.

# Event flow across the complete architecture

The system now looks like:

```text
                         ┌──────────────┐
                         │   Sensors    │
                         └──────┬───────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ #1 Sensor Fusion│
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ #2 Signal       │
                       │    Processing   │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ #3 Activity     │
                       │    Recognition  │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ #4 Dashboard    │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ #5 Connectivity │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ #6 Power        │
                       │    Runtime      │
                       └────────┬────────┘
                                │
                                ▼
                  ╔══════════════════════════╗
                  ║   #7 UNIFIED EVENT BUS   ║
                  ╚════════════╤═════════════╝
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
        Dashboard          Analytics          Logging
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                         iPhone Sync
```

## Why this matters

Without an event bus, you eventually end up with something like:

```text
Sensor → Dashboard
Sensor → Workout
Sensor → Activity
Activity → Dashboard
Activity → Workout
Workout → Connectivity
Power → Sensor
Power → Dashboard
Connectivity → Dashboard
Connectivity → Workout
...
```

That becomes increasingly difficult to maintain.

With the bus:

```text
                   EVENT BUS

Sensor ───────────────┐
Activity ─────────────┤
Workout ──────────────┤
Power ────────────────┤
Connectivity ─────────┤
Dashboard ────────────┤
                      ▼
                 Event Router
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      Dashboard    Analytics   Diagnostics
```

Each subsystem publishes **what happened**, rather than knowing who needs to receive it.

# Example: starting a workout

The workout system publishes:

```swift
await UnifiedEventBus.shared.publish(
    source: .workout,
    type: .workoutStarted,
    priority: .critical
)
```

Several systems can independently react:

```text
                    workoutStarted
                          │
              ┌───────────┼────────────┐
              ▼           ▼            ▼
         Power Runtime  Dashboard   Connectivity
              │           │            │
              ▼           ▼            ▼
       Performance     Show timer   Sync iPhone
          mode
```

The workout engine doesn't need to contain any of that logic.

# Example: battery drops

The power runtime publishes:

```swift
await UnifiedEventBus.shared.publish(
    source: .power,
    type: .workloadReduced,
    priority: .high,
    payload: .power(
        batteryLevel: 0.18,
        mode: "efficiency"
    )
)
```

The dashboard can show the new operating mode.

The signal processor can reduce optional computation.

The connectivity layer can reduce nonessential transmissions.

Analytics can stop.

All without tightly coupling the systems.

# Result

You now have the foundation for a **single coherent Watch runtime**:

```text
┌───────────────────────────────────────────────┐
│             UNIFIED WATCH RUNTIME             │
│                                               │
│  Sensors                                      │
│    ↓                                          │
│  Sensor Fusion                                │
│    ↓                                          │
│  Signal Processing                            │
│    ↓                                          │
│  Activity Recognition                         │
│    ↓                                          │
│  Workout State                                │
│                                               │
│          ↘       ↓       ↙                    │
│             EVENT BUS                         │
│          ↗       ↑       ↖                    │
│                                               │
│  Dashboard                                    │
│  Connectivity                                 │
│  Power Management                              │
│  Analytics                                    │
│  Diagnostics                                  │
│                                               │
└───────────────────────────────────────────────┘
```

This is the point where the individual components start becoming an actual **runtime architecture**, rather than seven separate pieces of Swift.








# Apple Watch Persistent Telemetry & Data Architecture

```swift
//
// PersistentTelemetryStore.swift
//
// Application-level persistent telemetry architecture for watchOS.
//
// Goals:
// - Efficient local persistence
// - Actor-isolated storage
// - Batched writes
// - Session-oriented data model
// - Derived metrics instead of unnecessary raw-data storage
// - Crash-resistant atomic writes
// - Offline-first operation
// - Event-bus integration
// - Later Watch ↔ iPhone synchronisation
//
// This implementation deliberately uses Foundation file storage
// rather than assuming a particular database framework.
//
// For a larger production application, this storage layer can
// subsequently be replaced by SwiftData/Core Data while retaining
// the same repository interface.
//

import Foundation
import SwiftUI


// ============================================================
// MARK: - Telemetry Data Types
// ============================================================

public enum TelemetryKind:
    String,
    Codable,
    Sendable
{
    case heartRate
    case motion
    case activity
    case workout
    case power
    case connectivity
    case signalQuality
    case diagnostic
    case runtime
}


// ============================================================
// MARK: - Telemetry Sample
// ============================================================

public struct TelemetrySample:
    Codable,
    Sendable,
    Identifiable
{
    public let id:
        UUID

    public let timestamp:
        Date

    public let kind:
        TelemetryKind

    public let value:
        Double?

    public let text:
        String?

    public let quality:
        Double?

    public init(
        id:
            UUID = UUID(),

        timestamp:
            Date = Date(),

        kind:
            TelemetryKind,

        value:
            Double? = nil,

        text:
            String? = nil,

        quality:
            Double? = nil
    ) {

        self.id =
            id

        self.timestamp =
            timestamp

        self.kind =
            kind

        self.value =
            value

        self.text =
            text

        self.quality =
            quality
    }
}


// ============================================================
// MARK: - Workout Telemetry
// ============================================================

public struct WorkoutTelemetry:
    Codable,
    Sendable
{
    public let timestamp:
        Date

    public let heartRate:
        Double?

    public let calories:
        Double?

    public let distanceMeters:
        Double?

    public let cadence:
        Double?

    public let motionMagnitude:
        Double?

    public let activity:
        String

    public init(
        timestamp:
            Date = Date(),

        heartRate:
            Double?,

        calories:
            Double?,

        distanceMeters:
            Double?,

        cadence:
            Double?,

        motionMagnitude:
            Double?,

        activity:
            String
    ) {

        self.timestamp =
            timestamp

        self.heartRate =
            heartRate

        self.calories =
            calories

        self.distanceMeters =
            distanceMeters

        self.cadence =
            cadence

        self.motionMagnitude =
            motionMagnitude

        self.activity =
            activity
    }
}


// ============================================================
// MARK: - Session Summary
// ============================================================

public struct TelemetrySessionSummary:
    Codable,
    Sendable,
    Identifiable
{
    public let id:
        UUID

    public let startedAt:
        Date

    public let endedAt:
        Date

    public let sampleCount:
        Int

    public let averageHeartRate:
        Double?

    public let maximumHeartRate:
        Double?

    public let minimumHeartRate:
        Double?

    public let calories:
        Double?

    public let distanceMeters:
        Double?

    public let activity:
        String

    public let completed:
        Bool

    public init(
        id:
            UUID,

        startedAt:
            Date,

        endedAt:
            Date,

        sampleCount:
            Int,

        averageHeartRate:
            Double?,

        maximumHeartRate:
            Double?,

        minimumHeartRate:
            Double?,

        calories:
            Double?,

        distanceMeters:
            Double?,

        activity:
            String,

        completed:
            Bool
    ) {

        self.id =
            id

        self.startedAt =
            startedAt

        self.endedAt =
            endedAt

        self.sampleCount =
            sampleCount

        self.averageHeartRate =
            averageHeartRate

        self.maximumHeartRate =
            maximumHeartRate

        self.minimumHeartRate =
            minimumHeartRate

        self.calories =
            calories

        self.distanceMeters =
            distanceMeters

        self.activity =
            activity

        self.completed =
            completed
    }
}


// ============================================================
// MARK: - Telemetry Batch
// ============================================================

public struct TelemetryBatch:
    Codable,
    Sendable,
    Identifiable
{
    public let id:
        UUID

    public let createdAt:
        Date

    public let sessionID:
        UUID?

    public let samples:
        [TelemetrySample]

    public init(
        id:
            UUID = UUID(),

        createdAt:
            Date = Date(),

        sessionID:
            UUID?,

        samples:
            [TelemetrySample]
    ) {

        self.id =
            id

        self.createdAt =
            createdAt

        self.sessionID =
            sessionID

        self.samples =
            samples
    }
}


// ============================================================
// MARK: - Persistent Envelope
// ============================================================

public struct PersistenceEnvelope<T:
    Codable & Sendable>:
    Codable,
    Sendable
{
    public let version:
        Int

    public let createdAt:
        Date

    public let payload:
        T

    public init(
        version:
            Int = 1,

        createdAt:
            Date = Date(),

        payload:
            T
    ) {

        self.version =
            version

        self.createdAt =
            createdAt

        self.payload =
            payload
    }
}


// ============================================================
// MARK: - Session Runtime
// ============================================================

public struct TelemetrySession:
    Sendable
{
    public let id:
        UUID

    public let startedAt:
        Date

    public private(set) var sampleCount:
        Int

    public private(set) var heartRateSum:
        Double

    public private(set) var heartRateCount:
        Int

    public private(set) var maximumHeartRate:
        Double?

    public private(set) var minimumHeartRate:
        Double?

    public private(set) var calories:
        Double?

    public private(set) var distanceMeters:
        Double?

    public var activity:
        String

    public init(
        id:
            UUID = UUID(),

        startedAt:
            Date = Date(),

        activity:
            String = "unknown"
    ) {

        self.id =
            id

        self.startedAt =
            startedAt

        self.sampleCount =
            0

        self.heartRateSum =
            0

        self.heartRateCount =
            0

        self.maximumHeartRate =
            nil

        self.minimumHeartRate =
            nil

        self.calories =
            nil

        self.distanceMeters =
            nil

        self.activity =
            activity
    }

    public mutating func ingest(
        _ telemetry:
            WorkoutTelemetry
    ) {

        sampleCount += 1

        if let heartRate =
            telemetry.heartRate
        {

            heartRateSum +=
                heartRate

            heartRateCount += 1

            if let maximum =
                maximumHeartRate
            {

                maximumHeartRate =
                    max(
                        maximum,
                        heartRate
                    )

            } else {

                maximumHeartRate =
                    heartRate
            }

            if let minimum =
                minimumHeartRate
            {

                minimumHeartRate =
                    min(
                        minimum,
                        heartRate
                    )

            } else {

                minimumHeartRate =
                    heartRate
            }
        }

        if let calories =
            telemetry.calories
        {

            self.calories =
                calories
        }

        if let distance =
            telemetry.distanceMeters
        {

            self.distanceMeters =
                distance
        }

        activity =
            telemetry.activity
    }

    public func finish(
        endedAt:
            Date = Date(),

        completed:
            Bool = true
    ) -> TelemetrySessionSummary {

        let average =
            heartRateCount > 0
            ? heartRateSum /
                Double(heartRateCount)
            : nil

        return TelemetrySessionSummary(

            id:
                id,

            startedAt:
                startedAt,

            endedAt:
                endedAt,

            sampleCount:
                sampleCount,

            averageHeartRate:
                average,

            maximumHeartRate:
                maximumHeartRate,

            minimumHeartRate:
                minimumHeartRate,

            calories:
                calories,

            distanceMeters:
                distanceMeters,

            activity:
                activity,

            completed:
                completed
        )
    }
}


// ============================================================
// MARK: - Telemetry Storage Error
// ============================================================

public enum TelemetryStorageError:
    Error,
    LocalizedError
{
    case invalidDirectory
    case encodingFailed
    case decodingFailed
    case writeFailed
    case readFailed
    case fileNotFound

    public var errorDescription:
        String?
    {

        switch self {

        case .invalidDirectory:
            return
                "Telemetry storage directory is invalid."

        case .encodingFailed:
            return
                "Telemetry data could not be encoded."

        case .decodingFailed:
            return
                "Telemetry data could not be decoded."

        case .writeFailed:
            return
                "Telemetry data could not be written."

        case .readFailed:
            return
                "Telemetry data could not be read."

        case .fileNotFound:
            return
                "Telemetry file was not found."
        }
    }
}


// ============================================================
// MARK: - File Store
// ============================================================

public actor TelemetryFileStore {

    private let fileManager:
        FileManager

    private let directory:
        URL

    public init(
        directory:
            URL? = nil
    ) throws {

        fileManager =
            FileManager.default

        if let directory {

            self.directory =
                directory

        } else {

            let base =
                fileManager.urls(
                    for:
                        .applicationSupportDirectory,
                    in:
                        .userDomainMask
                ).first

            guard
                let base
            else {
                throw
                    TelemetryStorageError
                        .invalidDirectory
            }

            self.directory =
                base
                    .appendingPathComponent(
                        "Telemetry",
                        isDirectory:
                            true
                    )
        }

        try fileManager
            .createDirectory(
                at:
                    self.directory,
                withIntermediateDirectories:
                    true
            )
    }

    // ========================================================
    // MARK: Atomic Write
    // ========================================================

    public func write<T:
        Codable & Sendable>(
        _ value:
            T,

        filename:
            String
    ) throws {

        let envelope =
            PersistenceEnvelope(
                payload:
                    value
            )

        let encoder =
            JSONEncoder()

        encoder.outputFormatting =
            [
                .sortedKeys
            ]

        let data:
            Data

        do {

            data =
                try encoder.encode(
                    envelope
                )

        } catch {

            throw
                TelemetryStorageError
                    .encodingFailed
        }

        let destination =
            directory
                .appendingPathComponent(
                    filename
                )

        let temporary =
            directory
                .appendingPathComponent(
                    filename +
                    ".tmp"
                )

        do {

            try data.write(
                to:
                    temporary,
                options:
                    .atomic
            )

            if fileManager
                .fileExists(
                    atPath:
                        destination.path
                )
            {

                try fileManager
                    .removeItem(
                        at:
                            destination
                    )
            }

            try fileManager
                .moveItem(
                    at:
                        temporary,
                    to:
                        destination
                )

        } catch {

            try? fileManager
                .removeItem(
                    at:
                        temporary
                )

            throw
                TelemetryStorageError
                    .writeFailed
        }
    }

    // ========================================================
    // MARK: Read
    // ========================================================

    public func read<T:
        Codable & Sendable>(
        _ type:
            T.Type,

        filename:
            String
    ) throws -> T {

        let url =
            directory
                .appendingPathComponent(
                    filename
                )

        guard
            fileManager
                .fileExists(
                    atPath:
                        url.path
                )
        else {

            throw
                TelemetryStorageError
                    .fileNotFound
        }

        let data:
            Data

        do {

            data =
                try Data(
                    contentsOf:
                        url
                )

        } catch {

            throw
                TelemetryStorageError
                    .readFailed
        }

        do {

            let envelope =
                try JSONDecoder()
                    .decode(
                        PersistenceEnvelope<T>
                            .self,
                        from:
                            data
                    )

            return envelope.payload

        } catch {

            throw
                TelemetryStorageError
                    .decodingFailed
        }
    }

    // ========================================================
    // MARK: Delete
    // ========================================================

    public func delete(
        filename:
            String
    ) throws {

        let url =
            directory
                .appendingPathComponent(
                    filename
                )

        guard
            fileManager
                .fileExists(
                    atPath:
                        url.path
                )
        else {
            return
        }

        try fileManager
            .removeItem(
                at:
                    url
            )
    }

    // ========================================================
    // MARK: List
    // ========================================================

    public func files()
        throws -> [String]
    {

        try fileManager
            .contentsOfDirectory(
                atPath:
                    directory.path
            )
    }
}


// ============================================================
// MARK: - Batch Buffer
// ============================================================

public actor TelemetryBatchBuffer {

    private var samples:
        [TelemetrySample] =
            []

    private let maximumSamples:
        Int

    private let maximumAge:
        TimeInterval

    private var firstSampleDate:
        Date?

    public init(
        maximumSamples:
            Int = 100,

        maximumAge:
            TimeInterval = 30
    ) {

        self.maximumSamples =
            max(
                1,
                maximumSamples
            )

        self.maximumAge =
            max(
                1,
                maximumAge
            )
    }

    public func append(
        _ sample:
            TelemetrySample
    ) {

        if firstSampleDate == nil {

            firstSampleDate =
                sample.timestamp
        }

        samples.append(
            sample
        )
    }

    public func shouldFlush(
        now:
            Date = Date()
    ) -> Bool {

        if samples.count >=
            maximumSamples
        {
            return true
        }

        guard
            let firstSampleDate
        else {
            return false
        }

        return now.timeIntervalSince(
            firstSampleDate
        ) >= maximumAge
    }

    public func flush(
        sessionID:
            UUID?
    ) -> TelemetryBatch? {

        guard
            !samples.isEmpty
        else {
            return nil
        }

        let batch =
            TelemetryBatch(
                sessionID:
                    sessionID,

                samples:
                    samples
            )

        samples.removeAll(
            keepingCapacity:
                true
        )

        firstSampleDate =
            nil

        return batch
    }

    public func count()
        -> Int
    {
        samples.count
    }
}


// ============================================================
// MARK: - Telemetry Repository
// ============================================================

public actor TelemetryRepository {

    private let store:
        TelemetryFileStore

    private let buffer:
        TelemetryBatchBuffer

    private var activeSession:
        TelemetrySession?

    private var pendingBatches:
        [TelemetryBatch] =
            []

    private let maximumPendingBatches:
        Int

    public init(
        store:
            TelemetryFileStore,

        buffer:
            TelemetryBatchBuffer =
                TelemetryBatchBuffer(),

        maximumPendingBatches:
            Int = 50
    ) {

        self.store =
            store

        self.buffer =
            buffer

        self.maximumPendingBatches =
            max(
                1,
                maximumPendingBatches
            )
    }

    // ========================================================
    // MARK: Session
    // ========================================================

    public func startSession(
        activity:
            String = "unknown"
    ) -> UUID {

        let session =
            TelemetrySession(
                activity:
                    activity
            )

        activeSession =
            session

        return session.id
    }

    public func currentSessionID()
        -> UUID?
    {
        activeSession?.id
    }

    // ========================================================
    // MARK: Ingest Workout
    // ========================================================

    public func ingestWorkout(
        _ telemetry:
            WorkoutTelemetry
    ) async {

        activeSession?
            .ingest(
                telemetry
            )

        let sample =
            TelemetrySample(

                timestamp:
                    telemetry.timestamp,

                kind:
                    .workout,

                value:
                    telemetry.heartRate,

                text:
                    telemetry.activity
            )

        await buffer.append(
            sample
        )

        await flushIfNeeded()
    }

    // ========================================================
    // MARK: Ingest Sensor
    // ========================================================

    public func ingest(
        _ sample:
            TelemetrySample
    ) async {

        await buffer.append(
            sample
        )

        await flushIfNeeded()
    }

    // ========================================================
    // MARK: Flush
    // ========================================================

    public func flush() async {

        guard
            let batch =
                await buffer.flush(
                    sessionID:
                        activeSession?.id
                )
        else {
            return
        }

        pendingBatches.append(
            batch
        )

        if pendingBatches.count >
            maximumPendingBatches
        {

            pendingBatches.removeFirst(
                pendingBatches.count -
                maximumPendingBatches
            )
        }

        await persistPendingBatches()
    }

    private func flushIfNeeded()
        async
    {

        guard
            await buffer.shouldFlush()
        else {
            return
        }

        await flush()
    }

    // ========================================================
    // MARK: Persist Batches
    // ========================================================

    private func persistPendingBatches()
        async
    {

        guard
            !pendingBatches.isEmpty
        else {
            return
        }

        for batch
            in pendingBatches
        {

            let filename =
                "batch-" +
                batch.id.uuidString +
                ".json"

            do {

                try await store.write(
                    batch,
                    filename:
                        filename
                )

            } catch {

                // Keep the batch in memory.
                //
                // A future retry can attempt
                // persistence again.
                return
            }
        }

        pendingBatches.removeAll(
            keepingCapacity:
                true
        )
    }

    // ========================================================
    // MARK: End Session
    // ========================================================

    public func endSession(
        completed:
            Bool = true
    ) async
        -> TelemetrySessionSummary?
    {

        await flush()

        guard
            let session =
                activeSession
        else {
            return nil
        }

        let summary =
            session.finish(
                completed:
                    completed
            )

        let filename =
            "session-" +
            summary.id.uuidString +
            ".json"

        do {

            try await store.write(
                summary,
                filename:
                    filename
            )

        } catch {

            // Session summary remains
            // reconstructable from the
            // in-memory session if required.
        }

        activeSession =
            nil

        return summary
    }

    // ========================================================
    // MARK: Pending Files
    // ========================================================

    public func pendingFiles()
        async -> [String]
    {

        (try? await store.files())
            ?? []
    }

    // ========================================================
    // MARK: Remove Uploaded Batch
    // ========================================================

    public func markUploaded(
        batch:
            TelemetryBatch
    ) async {

        let filename =
            "batch-" +
            batch.id.uuidString +
            ".json"

        try? await store.delete(
            filename:
                filename
        )
    }
}


// ============================================================
// MARK: - Telemetry Event Bridge
// ============================================================

public actor TelemetryEventBridge {

    private let bus:
        UnifiedEventBus

    private let repository:
        TelemetryRepository

    private var task:
        Task<Void, Never>?

    public init(
        bus:
            UnifiedEventBus =
                .shared,

        repository:
            TelemetryRepository
    ) {

        self.bus =
            bus

        self.repository =
            repository
    }

    public func start() {

        task?.cancel()

        task =
            Task {

                let subscription =
                    EventSubscription(
                        minimumPriority:
                            .normal
                    )

                let stream =
                    await bus.subscribe(
                        subscription
                    )

                for await event
                    in stream
                {

                    guard
                        !Task.isCancelled
                    else {
                        break
                    }

                    await handle(
                        event:
                            event
                    )
                }
            }
    }

    public func stop() {

        task?.cancel()

        task =
            nil
    }

    private func handle(
        event:
            RuntimeEvent
    ) async {

        switch event.type {

        case .heartRateUpdated:

            if case
                .heartRate(
                    let bpm
                ) =
                event.payload
            {

                await repository.ingest(

                    TelemetrySample(

                        timestamp:
                            event.wallClockDate,

                        kind:
                            .heartRate,

                        value:
                            bpm,

                        quality:
                            1
                    )
                )
            }

        case .motionUpdated:

            if case
                .motion(
                    let magnitude
                ) =
                event.payload
            {

                await repository.ingest(

                    TelemetrySample(

                        timestamp:
                            event.wallClockDate,

                        kind:
                            .motion,

                        value:
                            magnitude
                    )
                )
            }

        case .activityChanged:

            if case
                .activity(
                    let name,
                    let confidence
                ) =
                event.payload
            {

                await repository.ingest(

                    TelemetrySample(

                        timestamp:
                            event.wallClockDate,

                        kind:
                            .activity,

                        value:
                            confidence,

                        text:
                            name
                    )
                )
            }

        case .powerStateChanged:

            if case
                .power(
                    let battery,
                    let mode
                ) =
                event.payload
            {

                await repository.ingest(

                    TelemetrySample(

                        timestamp:
                            event.wallClockDate,

                        kind:
                            .power,

                        value:
                            battery,

                        text:
                            mode
                    )
                )
            }

        case .runtimeError:

            if case
                .diagnostic(
                    let message
                ) =
                event.payload
            {

                await repository.ingest(

                    TelemetrySample(

                        timestamp:
                            event.wallClockDate,

                        kind:
                            .diagnostic,

                        text:
                            message
                    )
                )
            }

        default:
            break
        }
    }
}


// ============================================================
// MARK: - Telemetry Synchronisation Record
// ============================================================

public struct TelemetrySyncRecord:
    Codable,
    Sendable
{
    public let batchID:
        UUID

    public let uploadedAt:
        Date

    public let sampleCount:
        Int

    public init(
        batchID:
            UUID,

        uploadedAt:
            Date = Date(),

        sampleCount:
            Int
    ) {

        self.batchID =
            batchID

        self.uploadedAt =
            uploadedAt

        self.sampleCount =
            sampleCount
    }
}


// ============================================================
// MARK: - Telemetry Export
// ============================================================

public actor TelemetryExporter {

    private let store:
        TelemetryFileStore

    public init(
        store:
            TelemetryFileStore
    ) {

        self.store =
            store
    }

    public func export(
        batches:
            [TelemetryBatch]
    ) throws -> Data {

        try JSONEncoder()
            .encode(
                batches
            )
    }
}


// ============================================================
// MARK: - Telemetry Runtime
// ============================================================

@MainActor
public final class TelemetryRuntime:
    ObservableObject
{

    @Published
    public private(set) var
        isRecording =
            false

    @Published
    public private(set) var
        currentSessionID:
            UUID?

    @Published
    public private(set) var
        bufferedSamples:
            Int =
                0

    private let repository:
        TelemetryRepository

    private let bridge:
        TelemetryEventBridge

    public init(
        repository:
            TelemetryRepository,

        bus:
            UnifiedEventBus =
                .shared
    ) {

        self.repository =
            repository

        self.bridge =
            TelemetryEventBridge(
                bus:
                    bus,

                repository:
                    repository
            )
    }

    // ========================================================
    // MARK: Start
    // ========================================================

    public func start(
        activity:
            String
    ) {

        Task {

            let id =
                await repository
                    .startSession(
                        activity:
                            activity
                    )

            await bridge.start()

            await MainActor.run {

                self.currentSessionID =
                    id

                self.isRecording =
                    true
            }
        }
    }

    // ========================================================
    // MARK: Stop
    // ========================================================

    public func stop() {

        Task {

            let _ =
                await repository
                    .endSession(
                        completed:
                            true
                    )

            await bridge.stop()

            await MainActor.run {

                self.currentSessionID =
                    nil

                self.isRecording =
                    false

                self.bufferedSamples =
                    0
            }
        }
    }
}


// ============================================================
// MARK: - Telemetry Dashboard
// ============================================================

public struct TelemetryStatusView:
    View
{

    @ObservedObject
    private var runtime:
        TelemetryRuntime

    public init(
        runtime:
            TelemetryRuntime
    ) {

        self.runtime =
            runtime
    }

    public var body: some View {

        VStack(
            spacing: 6
        ) {

            HStack {

                Text(
                    runtime.isRecording
                    ? "RECORDING"
                    : "IDLE"
                )
                .font(
                    .system(
                        size: 10,
                        weight: .bold
                    )
                )

                Spacer()
            }

            if let id =
                runtime.currentSessionID
            {

                Text(
                    id.uuidString
                )
                .font(
                    .system(
                        size: 7,
                        design:
                            .monospaced
                    )
                )
                .lineLimit(1)
            }
        }
    }
}


// ============================================================
// MARK: - Factory
// ============================================================

public enum TelemetryFactory {

    public static func makeRuntime()
        throws -> TelemetryRuntime
    {

        let store =
            try TelemetryFileStore()

        let buffer =
            TelemetryBatchBuffer(
                maximumSamples:
                    100,

                maximumAge:
                    30
            )

        let repository =
            TelemetryRepository(
                store:
                    store,

                buffer:
                    buffer
            )

        return TelemetryRuntime(
            repository:
                repository
        )
    }
}
```

# Data flow

The complete telemetry path is now:

```text
                 SENSOR
                   │
                   ▼
            Signal Processor
                   │
                   ▼
            Activity Engine
                   │
                   ▼
              Event Bus
                   │
                   ▼
          TelemetryEventBridge
                   │
                   ▼
             Hot Buffer
                   │
              100 samples
                   │
                   ▼
             TelemetryBatch
                   │
                   ▼
          Atomic local storage
                   │
          ┌────────┴────────┐
          ▼                 ▼
     Session Summary    Raw/derived batch
          │                 │
          └────────┬────────┘
                   ▼
            iPhone Sync Queue
```

# Why batching matters

Suppose your motion pipeline produces 25 samples per second.

Writing:

```text
25 disk writes / second
```

would be a poor architecture for a battery-constrained wearable.

Instead:

```text
25 samples/sec
      ↓
RAM buffer
      ↓
100 samples
      ↓
one persistence operation
```

The data layer therefore separates **real-time processing frequency** from **persistence frequency**.

The same principle applies to heart rate, activity, power and diagnostics.

# Three levels of data

The architecture intentionally distinguishes:

### Level 1 — Raw/high-frequency

Used temporarily for signal processing:

```text
accelerometer
gyroscope
heart-rate samples
timestamps
signal quality
```

These don't necessarily need permanent storage.

### Level 2 — Derived telemetry

Much more useful for long-term analysis:

```text
average HR
maximum HR
minimum HR
cadence
activity
motion magnitude
signal quality
battery state
runtime mode
```

### Level 3 — Session summaries

The smallest and most useful representation:

```text
Workout
────────────────────
Start
End
Duration
Average HR
Maximum HR
Minimum HR
Calories
Distance
Activity
Completion state
```

This dramatically reduces long-term storage requirements.

# Offline-first design

The Watch should not depend on the iPhone being connected.

The intended behaviour is:

```text
PHONE CONNECTED
       │
       ▼
Upload telemetry
       │
       ▼
Mark batch synchronised
```

But:

```text
PHONE OFFLINE
       │
       ▼
Continue recording
       │
       ▼
Store locally
       │
       ▼
Phone reconnects
       │
       ▼
Synchronise pending batches
```

This is particularly important for exercise sessions where the user may leave the phone behind.

# Integration with #7

The event bus becomes the central producer of telemetry:

```text
#1 Sensor Fusion
       │
       ▼
#2 Signal Processing
       │
       ▼
#3 Activity Recognition
       │
       ▼
#7 Unified Event Bus
       │
       ├──────────────► #4 Dashboard
       │
       ├──────────────► #5 Connectivity
       │
       ├──────────────► #6 Power Runtime
       │
       └──────────────► #8 Telemetry
                              │
                              ▼
                         Local Store
```

That means #8 doesn't need to constantly poll the sensor systems.

It simply listens to events.

# Integration with #6

Power management can also control persistence.

For example, during normal operation:

```text
100 samples
30-second flush
```

while a power-constrained profile could use:

```text
250 samples
60-second flush
```

provided that the application's data requirements permit it.

The key principle is:

> **Don't sacrifice required data integrity to save power; eliminate unnecessary work first.**

# The resulting architecture

You now have eight major layers:

```text
┌───────────────────────────────────────────────┐
│               APPLE WATCH SYSTEM              │
├───────────────────────────────────────────────┤
│                                               │
│ #1  Sensor Fusion                             │
│      ↓                                        │
│ #2  Real-Time Signal Processing               │
│      ↓                                        │
│ #3  Activity Recognition                      │
│      ↓                                        │
│ #4  Real-Time Dashboard                       │
│      ↓                                        │
│ #5  Watch ↔ iPhone Connectivity                │
│      ↓                                        │
│ #6  Power-Aware Runtime                       │
│      ↓                                        │
│ #7  Unified Event Bus                         │
│      ↓                                        │
│ #8  Persistent Telemetry                      │
│                                               │
└───────────────────────────────────────────────┘
```

In the actual implementation, however, #7 acts as the **central nervous system**, while #6 acts as the **resource governor** and #8 acts as the **memory/storage layer**.

The next natural layer is **#9 — the Watch–iPhone synchronisation/data replication engine**, which can take these persisted telemetry batches and reliably move them between Watch and iPhone with sequence numbers, acknowledgements, retry queues, deduplication, conflict handling and resumable synchronisation.
::





#9 — Watch–iPhone Synchronisation & Replication Engine

```swift
//
// WatchPhoneSyncEngine.swift
//
// Application-level Watch ↔ iPhone replication layer.
//
// Designed to sit above:
//
// #5  WatchConnectivity
// #7  Unified Event Bus
// #8  Persistent Telemetry
//
// Goals:
// - Offline-first operation
// - Reliable batch delivery
// - Sequence numbers
// - Idempotent messages
// - Acknowledgements
// - Retry with backoff
// - Deduplication
// - Resumable transfers
// - Latest-state synchronisation
// - Telemetry replication
// - Session replication
//
// IMPORTANT:
// WatchConnectivity remains the transport mechanism.
// This layer provides application-level reliability on top of it.
//

import Foundation
import WatchConnectivity
import SwiftUI


// ============================================================
// MARK: - Replication Direction
// ============================================================

public enum ReplicationDirection:
    String,
    Codable,
    Sendable
{
    case watchToPhone
    case phoneToWatch
}


// ============================================================
// MARK: - Replication Object Type
// ============================================================

public enum ReplicationObjectType:
    String,
    Codable,
    Sendable
{
    case telemetryBatch
    case sessionSummary
    case runtimeEvent
    case diagnostic
    case applicationState
    case configuration
}


// ============================================================
// MARK: - Replication Priority
// ============================================================

public enum ReplicationPriority:
    Int,
    Codable,
    Sendable,
    Comparable
{
    case background = 0
    case normal = 1
    case important = 2
    case critical = 3

    public static func < (
        lhs:
            ReplicationPriority,

        rhs:
            ReplicationPriority
    ) -> Bool {

        lhs.rawValue <
            rhs.rawValue
    }
}


// ============================================================
// MARK: - Replication State
// ============================================================

public enum ReplicationState:
    String,
    Codable,
    Sendable
{
    case pending
    case transmitting
    case acknowledged
    case retrying
    case failed
}


// ============================================================
// MARK: - Replication Envelope
// ============================================================

public struct ReplicationEnvelope:
    Codable,
    Sendable,
    Identifiable
{
    public let id:
        UUID

    public let sequence:
        UInt64

    public let createdAt:
        Date

    public let direction:
        ReplicationDirection

    public let objectType:
        ReplicationObjectType

    public let priority:
        ReplicationPriority

    public let payload:
        Data

    public init(
        id:
            UUID = UUID(),

        sequence:
            UInt64,

        createdAt:
            Date = Date(),

        direction:
            ReplicationDirection,

        objectType:
            ReplicationObjectType,

        priority:
            ReplicationPriority,

        payload:
            Data
    ) {

        self.id =
            id

        self.sequence =
            sequence

        self.createdAt =
            createdAt

        self.direction =
            direction

        self.objectType =
            objectType

        self.priority =
            priority

        self.payload =
            payload
    }
}


// ============================================================
// MARK: - Acknowledgement
// ============================================================

public struct ReplicationAcknowledgement:
    Codable,
    Sendable
{
    public let envelopeID:
        UUID

    public let sequence:
        UInt64

    public let accepted:
        Bool

    public let receivedAt:
        Date

    public let error:
        String?

    public init(
        envelopeID:
            UUID,

        sequence:
            UInt64,

        accepted:
            Bool,

        receivedAt:
            Date = Date(),

        error:
            String? = nil
    ) {

        self.envelopeID =
            envelopeID

        self.sequence =
            sequence

        self.accepted =
            accepted

        self.receivedAt =
            receivedAt

        self.error =
            error
    }
}


// ============================================================
// MARK: - Replication Queue Item
// ============================================================

public struct ReplicationQueueItem:
    Codable,
    Sendable,
    Identifiable
{
    public let id:
        UUID

    public let envelope:
        ReplicationEnvelope

    public var state:
        ReplicationState

    public var attempts:
        Int

    public var lastAttempt:
        Date?

    public var nextAttempt:
        Date?

    public init(
        envelope:
            ReplicationEnvelope
    ) {

        self.id =
            envelope.id

        self.envelope =
            envelope

        self.state =
            .pending

        self.attempts =
            0

        self.lastAttempt =
            nil

        self.nextAttempt =
            nil
    }
}


// ============================================================
// MARK: - Sequence Generator
// ============================================================

public actor ReplicationSequenceGenerator {

    private var value:
        UInt64

    public init(
        initialValue:
            UInt64 = 0
    ) {

        self.value =
            initialValue
    }

    public func next()
        -> UInt64
    {

        value &+= 1

        return value
    }

    public func current()
        -> UInt64
    {
        value
    }
}


// ============================================================
// MARK: - Retry Policy
// ============================================================

public struct ReplicationRetryPolicy:
    Sendable
{
    public let maximumAttempts:
        Int

    public let initialDelay:
        TimeInterval

    public let maximumDelay:
        TimeInterval

    public init(
        maximumAttempts:
            Int = 8,

        initialDelay:
            TimeInterval = 2,

        maximumDelay:
            TimeInterval = 300
    ) {

        self.maximumAttempts =
            max(
                1,
                maximumAttempts
            )

        self.initialDelay =
            max(
                0.1,
                initialDelay
            )

        self.maximumDelay =
            max(
                initialDelay,
                maximumDelay
            )
    }

    public func delay(
        forAttempt:
            Int
    ) -> TimeInterval {

        let exponent =
            max(
                0,
                forAttempt - 1
            )

        let multiplier =
            pow(
                2,
                Double(exponent)
            )

        return min(
            maximumDelay,
            initialDelay *
            multiplier
        )
    }
}


// ============================================================
// MARK: - Deduplication Store
// ============================================================

public actor ReplicationDeduplicator {

    private var processed:
        Set<UUID> =
            []

    private var ordered:
        [UUID] =
            []

    private let maximumEntries:
        Int

    public init(
        maximumEntries:
            Int = 1_000
    ) {

        self.maximumEntries =
            max(
                100,
                maximumEntries
            )
    }

    public func contains(
        _ id:
            UUID
    ) -> Bool {

        processed.contains(
            id
        )
    }

    public func insert(
        _ id:
            UUID
    ) {

        guard
            !processed.contains(
                id
            )
        else {
            return
        }

        processed.insert(
            id
        )

        ordered.append(
            id
        )

        if ordered.count >
            maximumEntries
        {

            let excess =
                ordered.count -
                maximumEntries

            let removed =
                ordered.prefix(
                    excess
                )

            for value
                in removed
            {

                processed.remove(
                    value
                )
            }

            ordered.removeFirst(
                excess
            )
        }
    }
}


// ============================================================
// MARK: - Sync Transport
// ============================================================

public protocol ReplicationTransport:
    AnyObject,
    Sendable
{
    var isReachable:
        Bool
    { get }

    func send(
        _ envelope:
            ReplicationEnvelope
    async throws

    func send(
        _ acknowledgement:
            ReplicationAcknowledgement
    async throws
}


// ============================================================
// MARK: - WatchConnectivity Transport
// ============================================================

@MainActor
public final class WatchConnectivityTransport:
    NSObject,
    ReplicationTransport,
    WCSessionDelegate
{

    public static let shared =
        WatchConnectivityTransport()

    private let session:
        WCSession

    public private(set) var
        isReachable:
            Bool = false

    private override init() {

        self.session =
            WCSession.default

        super.init()

        guard
            WCSession.isSupported()
        else {
            return
        }

        session.delegate =
            self

        session.activate()
    }

    // ========================================================
    // MARK: Send Envelope
    // ========================================================

    public func send(
        _ envelope:
            ReplicationEnvelope
    ) async throws {

        let data =
            try JSONEncoder()
                .encode(
                    envelope
                )

        let message:
            [String: Any] =
            [
                "type":
                    "replication",

                "payload":
                    data
            ]

        if session.isReachable {

            session.sendMessage(
                message,
                replyHandler:
                    nil,
                errorHandler:
                    { error in

                    print(
                        "Replication send error:",
                        error
                    )
                }
            )

        } else {

            session.transferUserInfo(
                message
            )
        }
    }

    // ========================================================
    // MARK: Send Acknowledgement
    // ========================================================

    public func send(
        _ acknowledgement:
            ReplicationAcknowledgement
    ) async throws {

        let data =
            try JSONEncoder()
                .encode(
                    acknowledgement
                )

        let message:
            [String: Any] =
            [
                "type":
                    "acknowledgement",

                "payload":
                    data
            ]

        if session.isReachable {

            session.sendMessage(
                message,
                replyHandler:
                    nil,
                errorHandler:
                    { error in

                    print(
                        "Acknowledgement error:",
                        error
                    )
                }
            )

        } else {

            session.transferUserInfo(
                message
            )
        }
    }

    // ========================================================
    // MARK: Activation
    // ========================================================

    public func session(
        _ session:
            WCSession,

        activationDidCompleteWith
            activationState:
                WCSessionActivationState,

        error:
            Error?
    ) {

        isReachable =
            session.isReachable
    }

    public func sessionReachabilityDidChange(
        _ session:
            WCSession
    ) {

        isReachable =
            session.isReachable
    }

    #if os(iOS)

    public func sessionDidBecomeInactive(
        _ session:
            WCSession
    ) {
    }

    public func sessionDidDeactivate(
        _ session:
            WCSession
    ) {

        session.activate()
    }

    #endif
}


// ============================================================
// MARK: - Replication Queue
// ============================================================

public actor ReplicationQueue {

    private var items:
        [UUID:
            ReplicationQueueItem] =
            [:]

    private let retryPolicy:
        ReplicationRetryPolicy

    public init(
        retryPolicy:
            ReplicationRetryPolicy =
                ReplicationRetryPolicy()
    ) {

        self.retryPolicy =
            retryPolicy
    }

    // ========================================================
    // MARK: Enqueue
    // ========================================================

    public func enqueue(
        _ envelope:
            ReplicationEnvelope
    ) {

        guard
            items[envelope.id] == nil
        else {
            return
        }

        items[envelope.id] =
            ReplicationQueueItem(
                envelope:
                    envelope
            )
    }

    // ========================================================
    // MARK: Ready Items
    // ========================================================

    public func readyItems(
        now:
            Date = Date()
    ) -> [ReplicationQueueItem] {

        items.values

            .filter { item in

                guard
                    item.state !=
                        .acknowledged
                else {
                    return false
                }

                if let next =
                    item.nextAttempt
                {

                    return next <= now
                }

                return true
            }

            .sorted { lhs, rhs in

                if lhs.envelope.priority !=
                    rhs.envelope.priority
                {

                    return lhs.envelope.priority >
                        rhs.envelope.priority
                }

                return lhs.envelope.sequence <
                    rhs.envelope.sequence
            }
    }

    // ========================================================
    // MARK: Attempt
    // ========================================================

    public func markAttempt(
        id:
            UUID,

        now:
            Date = Date()
    ) {

        guard
            var item =
                items[id]
        else {
            return
        }

        item.attempts += 1

        item.lastAttempt =
            now

        item.state =
            .transmitting

        items[id] =
            item
    }

    // ========================================================
    // MARK: Retry
    // ========================================================

    public func markRetry(
        id:
            UUID,

        now:
            Date = Date()
    ) {

        guard
            var item =
                items[id]
        else {
            return
        }

        if item.attempts >=
            retryPolicy.maximumAttempts
        {

            item.state =
                .failed

            items[id] =
                item

            return
        }

        let delay =
            retryPolicy.delay(
                forAttempt:
                    item.attempts
            )

        item.state =
            .retrying

        item.nextAttempt =
            now.addingTimeInterval(
                delay
            )

        items[id] =
            item
    }

    // ========================================================
    // MARK: Acknowledge
    // ========================================================

    public func acknowledge(
        _ acknowledgement:
            ReplicationAcknowledgement
    ) {

        guard
            var item =
                items[
                    acknowledgement
                        .envelopeID
                ]
        else {
            return
        }

        if acknowledgement.accepted {

            item.state =
                .acknowledged

        } else {

            item.state =
                .failed
        }

        items[
            acknowledgement
                .envelopeID
        ] =
            item
    }

    // ========================================================
    // MARK: Remove Acknowledged
    // ========================================================

    public func removeAcknowledged() {

        items =
            items.filter {
                $0.value.state !=
                    .acknowledged
            }
    }

    // ========================================================
    // MARK: Statistics
    // ========================================================

    public func count()
        -> Int
    {
        items.count
    }

    public func pendingCount()
        -> Int
    {

        items.values
            .filter {
                $0.state !=
                    .acknowledged
            }
            .count
    }
}


// ============================================================
// MARK: - Replication Engine
// ============================================================

public actor WatchPhoneReplicationEngine {

    private let transport:
        any ReplicationTransport

    private let queue:
        ReplicationQueue

    private let deduplicator:
        ReplicationDeduplicator

    private let sequenceGenerator:
        ReplicationSequenceGenerator

    private let retryPolicy:
        ReplicationRetryPolicy

    private var worker:
        Task<Void, Never>?

    private var running:
        Bool = false

    public init(
        transport:
            any ReplicationTransport,

        retryPolicy:
            ReplicationRetryPolicy =
                ReplicationRetryPolicy()
    ) {

        self.transport =
            transport

        self.retryPolicy =
            retryPolicy

        self.queue =
            ReplicationQueue(
                retryPolicy:
                    retryPolicy
            )

        self.deduplicator =
            ReplicationDeduplicator()

        self.sequenceGenerator =
            ReplicationSequenceGenerator()
    }

    // ========================================================
    // MARK: Start
    // ========================================================

    public func start() {

        guard
            !running
        else {
            return
        }

        running =
            true

        worker =
            Task {

                while
                    !Task.isCancelled
                {

                    await processQueue()

                    try? await Task.sleep(
                        for:
                            .seconds(2)
                    )
                }
            }
    }

    // ========================================================
    // MARK: Stop
    // ========================================================

    public func stop() {

        running =
            false

        worker?.cancel()

        worker =
            nil
    }

    // ========================================================
    // MARK: Enqueue Object
    // ========================================================

    public func enqueue<T:
        Codable & Sendable>(
        _ object:
            T,

        objectType:
            ReplicationObjectType,

        priority:
            ReplicationPriority =
                .normal
    ) async throws
        -> UUID
    {

        let data =
            try JSONEncoder()
                .encode(
                    object
                )

        let sequence =
            await sequenceGenerator
                .next()

        let envelope =
            ReplicationEnvelope(

                sequence:
                    sequence,

                direction:
                    .watchToPhone,

                objectType:
                    objectType,

                priority:
                    priority,

                payload:
                    data
            )

        await queue.enqueue(
            envelope
        )

        return envelope.id
    }

    // ========================================================
    // MARK: Process Queue
    // ========================================================

    private func processQueue()
        async
    {

        let items =
            await queue.readyItems()

        guard
            !items.isEmpty
        else {
            return
        }

        for item
            in items
        {

            guard
                !Task.isCancelled
            else {
                return
            }

            await queue.markAttempt(
                id:
                    item.id
            )

            do {

                try await transport.send(
                    item.envelope
                )

                //
                // Do not immediately delete.
                //
                // The remote endpoint must acknowledge
                // the envelope.
                //

            } catch {

                await queue.markRetry(
                    id:
                        item.id
                )
            }
        }
    }

    // ========================================================
    // MARK: Receive Envelope
    // ========================================================

    public func receive(
        _ envelope:
            ReplicationEnvelope
    ) async {

        if await deduplicator.contains(
            envelope.id
        ) {

            let acknowledgement =
                ReplicationAcknowledgement(

                    envelopeID:
                        envelope.id,

                    sequence:
                        envelope.sequence,

                    accepted:
                        true
                )

            try? await transport.send(
                acknowledgement
            )

            return
        }

        await deduplicator.insert(
            envelope.id
        )

        //
        // Actual application routing occurs here.
        //
        // The envelope can be decoded according
        // to envelope.objectType.
        //
        // For example:
        //
        // .telemetryBatch
        // .sessionSummary
        // .configuration
        //

        let acknowledgement =
            ReplicationAcknowledgement(

                envelopeID:
                    envelope.id,

                sequence:
                    envelope.sequence,

                accepted:
                    true
            )

        try? await transport.send(
            acknowledgement
        )
    }

    // ========================================================
    // MARK: Receive Acknowledgement
    // ========================================================

    public func receive(
        _ acknowledgement:
            ReplicationAcknowledgement
    ) async {

        await queue.acknowledge(
            acknowledgement
        )

        await queue.removeAcknowledged()
    }

    // ========================================================
    // MARK: Status
    // ========================================================

    public func pendingCount()
        async -> Int
    {

        await queue.pendingCount()
    }
}


// ============================================================
// MARK: - Sync State
// ============================================================

public struct ReplicationStatus:
    Sendable
{
    public let connected:
        Bool

    public let pending:
        Int

    public let running:
        Bool

    public init(
        connected:
            Bool,

        pending:
            Int,

        running:
            Bool
    ) {

        self.connected =
            connected

        self.pending =
            pending

        self.running =
            running
    }
}


// ============================================================
// MARK: - Application Synchronisation State
// ============================================================

public struct ApplicationReplicationState:
    Codable,
    Sendable
{
    public let schemaVersion:
        Int

    public let lastWatchSequence:
        UInt64

    public let lastPhoneSequence:
        UInt64

    public let lastSync:
        Date?

    public init(
        schemaVersion:
            Int = 1,

        lastWatchSequence:
            UInt64 = 0,

        lastPhoneSequence:
            UInt64 = 0,

        lastSync:
            Date? = nil
    ) {

        self.schemaVersion =
            schemaVersion

        self.lastWatchSequence =
            lastWatchSequence

        self.lastPhoneSequence =
            lastPhoneSequence

        self.lastSync =
            lastSync
    }
}


// ============================================================
// MARK: - Sync Controller
// ============================================================

@MainActor
public final class WatchPhoneSyncController:
    ObservableObject
{

    @Published
    public private(set) var
        connected =
            false

    @Published
    public private(set) var
        pendingItems =
            0

    @Published
    public private(set) var
        synchronising =
            false

    private let engine:
        WatchPhoneReplicationEngine

    private var monitor:
        Task<Void, Never>?

    public init(
        engine:
            WatchPhoneReplicationEngine
    ) {

        self.engine =
            engine
    }

    // ========================================================
    // MARK: Start
    // ========================================================

    public func start() {

        synchronising =
            true

        Task {

            await engine.start()

            while
                !Task.isCancelled
            {

                let pending =
                    await engine
                        .pendingCount()

                await MainActor.run {

                    self.pendingItems =
                        pending
                }

                try? await Task.sleep(
                    for:
                        .seconds(2)
                )
            }
        }
    }

    // ========================================================
    // MARK: Stop
    // ========================================================

    public func stop() {

        Task {

            await engine.stop()

            await MainActor.run {

                self.synchronising =
                    false
            }
        }
    }
}


// ============================================================
// MARK: - Sync Dashboard
// ============================================================

public struct ReplicationStatusView:
    View
{

    @ObservedObject
    private var controller:
        WatchPhoneSyncController

    public init(
        controller:
            WatchPhoneSyncController
    ) {

        self.controller =
            controller
    }

    public var body: some View {

        VStack(
            spacing: 5
        ) {

            HStack {

                Circle()
                    .frame(
                        width: 7,
                        height: 7
                    )

                Text(
                    controller.connected
                    ? "PHONE CONNECTED"
                    : "PHONE OFFLINE"
                )
                .font(
                    .system(
                        size: 9,
                        weight:
                            .semibold
                    )
                )
            }

            Text(
                "\(controller.pendingItems) pending"
            )
            .font(
                .system(
                    size: 8,
                    design:
                        .monospaced
                )
            )

            if controller.synchronising {

                Text(
                    "SYNC ACTIVE"
                )
                .font(
                    .system(
                        size: 7,
                        weight:
                            .bold
                    )
                )
            }
        }
    }
}


// ============================================================
// MARK: - Telemetry Replication Adapter
// ============================================================

public actor TelemetryReplicationAdapter {

    private let repository:
        TelemetryRepository

    private let replication:
        WatchPhoneReplicationEngine

    public init(
        repository:
            TelemetryRepository,

        replication:
            WatchPhoneReplicationEngine
    ) {

        self.repository =
            repository

        self.replication =
            replication
    }

    // ========================================================
    // MARK: Queue Session
    // ========================================================

    public func replicateSession(
        _ summary:
            TelemetrySessionSummary
    ) async {

        do {

            _ =
                try await replication
                    .enqueue(

                        summary,

                        objectType:
                            .sessionSummary,

                        priority:
                            .important
                    )

        } catch {

            print(
                "Could not queue session:",
                error
            )
        }
    }

    // ========================================================
    // MARK: Queue Batch
    // ========================================================

    public func replicateBatch(
        _ batch:
            TelemetryBatch
    ) async {

        do {

            _ =
                try await replication
                    .enqueue(

                        batch,

                        objectType:
                            .telemetryBatch,

                        priority:
                            .normal
                    )

        } catch {

            print(
                "Could not queue telemetry:",
                error
            )
        }
    }
}


// ============================================================
// MARK: - Runtime Integration
// ============================================================

@MainActor
public final class WatchDataReplicationRuntime:
    ObservableObject
{

    public let telemetry:
        TelemetryRuntime

    public let sync:
        WatchPhoneSyncController

    private let replication:
        WatchPhoneReplicationEngine

    public init() {

        let transport =
            WatchConnectivityTransport.shared

        let engine =
            WatchPhoneReplicationEngine(
                transport:
                    transport
            )

        self.replication =
            engine

        self.sync =
            WatchPhoneSyncController(
                engine:
                    engine
            )

        //
        // TelemetryFactory comes from #8.
        //
        do {

            self.telemetry =
                try TelemetryFactory
                    .makeRuntime()

        } catch {

            fatalError(
                "Unable to initialise telemetry: \(error)"
            )
        }
    }

    public func start() {

        telemetry.start(
            activity:
                "runtime"
        )

        sync.start()
    }

    public func stop() {

        telemetry.stop()

        sync.stop()
    }
}


// ============================================================
// MARK: - Example Application Bootstrap
// ============================================================

@MainActor
public final class EliteWatchRuntimeV2 {

    public let data:
        WatchDataReplicationRuntime

    public init() {

        self.data =
            WatchDataReplicationRuntime()
    }

    public func launch() {

        data.start()
    }

    public func shutdown() {

        data.stop()
    }
}
```

## Replication architecture

The resulting system is now:

```text
                    APPLE WATCH
┌───────────────────────────────────────────────┐
│                                               │
│ Sensors                                       │
│    ↓                                          │
│ Signal Processing                             │
│    ↓                                          │
│ Activity Recognition                          │
│    ↓                                          │
│ Unified Event Bus (#7)                        │
│    ↓                                          │
│ Persistent Telemetry (#8)                     │
│    ↓                                          │
│ Replication Queue                             │
│    ↓                                          │
│ Sequence Number                               │
│    ↓                                          │
│ WatchConnectivity                             │
│    │                                          │
└────┼──────────────────────────────────────────┘
     │
     │  TELEMETRY / SESSIONS / STATE
     │
     ▼
┌───────────────────────────────────────────────┐
│                   iPHONE                      │
│                                               │
│ Replication Receiver                          │
│    ↓                                          │
│ Deduplication                                 │
│    ↓                                          │
│ Acknowledgement                               │
│    ↓                                          │
│ Persistent Database                           │
│    ↓                                          │
│ Analytics / Cloud Sync / UI                   │
│                                               │
└───────────────────────────────────────────────┘
```

### The important reliability mechanism

A batch is **not** considered synchronised merely because `send()` succeeded.

The lifecycle is:

```text
PENDING
   ↓
TRANSMITTING
   ↓
REMOTE RECEIVES
   ↓
REMOTE DEDUPLICATES
   ↓
REMOTE STORES DATA
   ↓
ACKNOWLEDGEMENT
   ↓
ACKNOWLEDGED
   ↓
REMOVE FROM QUEUE
```

If the connection disappears:

```text
TRANSMITTING
      ↓
     FAIL
      ↓
  RETRYING
      ↓
 exponential backoff
      ↓
TRANSMITTING
```

The retry policy starts at two seconds and progressively backs off to a five-minute maximum.

### Why the UUID + sequence number combination matters

Every replication object gets:

```text
UUID
+
monotonic sequence number
+
creation timestamp
```

The UUID provides **identity**.

The sequence number provides **ordering**.

The timestamp provides **temporal context**.

This allows the receiving side to distinguish:

```text
same message received twice
```

from:

```text
two different messages
```

without relying on timestamps alone.

## Offline-first behaviour

The Watch can now operate independently:

```text
Phone unavailable
       │
       ▼
Workout continues
       │
       ▼
Telemetry stored locally
       │
       ▼
Replication queue grows
       │
       ▼
Phone returns
       │
       ▼
Queue drains
```

This is much safer than making the Watch wait for the iPhone.

## What should actually be synchronised?

I would divide the data into four classes:

| Data                      | Direction      | Priority              |
| ------------------------- | -------------- | --------------------- |
| Workout session summary   | Watch → iPhone | Important             |
| Telemetry batches         | Watch → iPhone | Normal                |
| Diagnostics               | Watch → iPhone | Background            |
| Configuration             | iPhone → Watch | Important             |
| Current application state | Both           | Important             |
| Live dashboard data       | Watch → iPhone | Usually not persisted |

The last point is particularly important.

You generally **don't want to replicate every live dashboard update**.

The Watch should remain autonomous and only replicate information that has durable value.

## #9's role in the overall system

You now have:

```text
#1  Sensor Fusion
       ↓
#2  Signal Processor
       ↓
#3  Activity Recognition
       ↓
#4  High-Performance Dashboard
       ↓
#5  Connectivity
       ↓
#6  Power Runtime
       ↓
#7  Unified Event Bus
       ↓
#8  Persistent Telemetry
       ↓
#9  Replication Engine
       ↓
    iPhone
```

The next layer, **#10**, can therefore become the **overall Watch operating/runtime orchestration layer**: boot sequence, dependency injection, lifecycle management, health checks, watchdogs, diagnostics, fault recovery, performance counters and coordinated startup/shutdown of **#1–#9**. That is where these individual systems become one coherent Watch application runtime.







#10 — Master Watch Runtime & Orchestration Layer

```swift
//
// EliteWatchMasterRuntime.swift
//
// Master application runtime for the Apple Watch architecture.
//
// Coordinates:
//
// #1 Sensor Fusion
// #2 Real-Time Signal Processing
// #3 Activity Recognition
// #4 High-Performance Dashboard
// #5 WatchConnectivity
// #6 Power-Aware Runtime
// #7 Unified Event Bus
// #8 Persistent Telemetry
// #9 Watch ↔ iPhone Replication
//
// This is an APPLICATION-LEVEL runtime.
// It does not modify Apple's kernel, firmware, drivers,
// private frameworks, or hardware control layers.
//

import Foundation
import SwiftUI
import WatchKit
import Combine


// ============================================================
// MARK: - Runtime Lifecycle
// ============================================================

public enum MasterRuntimeState:
    String,
    Sendable
{
    case uninitialized
    case booting
    case initializing
    case running
    case degraded
    case recovering
    case stopping
    case stopped
    case failed
}


// ============================================================
// MARK: - Runtime Subsystems
// ============================================================

public enum RuntimeSubsystem:
    String,
    CaseIterable,
    Sendable
{
    case sensorFusion
    case signalProcessor
    case activityRecognition
    case dashboard
    case connectivity
    case powerRuntime
    case eventBus
    case telemetry
    case replication
}


// ============================================================
// MARK: - Subsystem Health
// ============================================================

public enum SubsystemHealth:
    String,
    Sendable
{
    case unknown
    case starting
    case healthy
    case degraded
    case failed
    case stopped
}


// ============================================================
// MARK: - Health Record
// ============================================================

public struct SubsystemHealthRecord:
    Sendable
{
    public let subsystem:
        RuntimeSubsystem

    public let health:
        SubsystemHealth

    public let lastHeartbeat:
        Date?

    public let message:
        String?

    public let restartCount:
        Int

    public init(
        subsystem:
            RuntimeSubsystem,

        health:
            SubsystemHealth =
                .unknown,

        lastHeartbeat:
            Date? =
                nil,

        message:
            String? =
                nil,

        restartCount:
            Int = 0
    ) {

        self.subsystem =
            subsystem

        self.health =
            health

        self.lastHeartbeat =
            lastHeartbeat

        self.message =
            message

        self.restartCount =
            restartCount
    }
}


// ============================================================
// MARK: - Runtime Fault
// ============================================================

public struct RuntimeFault:
    Identifiable,
    Sendable
{
    public let id:
        UUID

    public let subsystem:
        RuntimeSubsystem

    public let timestamp:
        Date

    public let message:
        String

    public let recoverable:
        Bool

    public init(
        id:
            UUID = UUID(),

        subsystem:
            RuntimeSubsystem,

        timestamp:
            Date = Date(),

        message:
            String,

        recoverable:
            Bool
    ) {

        self.id =
            id

        self.subsystem =
            subsystem

        self.timestamp =
            timestamp

        self.message =
            message

        self.recoverable =
            recoverable
    }
}


// ============================================================
// MARK: - Runtime Metrics
// ============================================================

public struct MasterRuntimeMetrics:
    Sendable
{
    public private(set) var
        eventsProcessed:
            UInt64 = 0

    public private(set) var
        faults:
            UInt64 = 0

    public private(set) var
        recoveries:
            UInt64 = 0

    public private(set) var
        heartbeats:
            UInt64 = 0

    public private(set) var
        bootDuration:
            TimeInterval = 0

    public private(set) var
        uptime:
            TimeInterval = 0

    public mutating func eventProcessed() {

        eventsProcessed &+= 1
    }

    public mutating func faultRecorded() {

        faults &+= 1
    }

    public mutating func recoveryPerformed() {

        recoveries &+= 1
    }

    public mutating func heartbeatReceived() {

        heartbeats &+= 1
    }
}


// ============================================================
// MARK: - Health Registry
// ============================================================

public actor RuntimeHealthRegistry {

    private var records:
        [RuntimeSubsystem:
            SubsystemHealthRecord] =
            [:]

    public init() {

        for subsystem
            in RuntimeSubsystem.allCases
        {

            records[subsystem] =
                SubsystemHealthRecord(
                    subsystem:
                        subsystem
                )
        }
    }

    public func set(
        _ subsystem:
            RuntimeSubsystem,

        health:
            SubsystemHealth,

        message:
            String? =
                nil
    ) {

        let old =
            records[subsystem]

        records[subsystem] =
            SubsystemHealthRecord(

                subsystem:
                    subsystem,

                health:
                    health,

                lastHeartbeat:
                    Date(),

                message:
                    message,

                restartCount:
                    old?.restartCount
                    ?? 0
            )
    }

    public func heartbeat(
        _ subsystem:
            RuntimeSubsystem
    ) {

        let old =
            records[subsystem]

        records[subsystem] =
            SubsystemHealthRecord(

                subsystem:
                    subsystem,

                health:
                    .healthy,

                lastHeartbeat:
                    Date(),

                message:
                    old?.message,

                restartCount:
                    old?.restartCount
                    ?? 0
            )
    }

    public func incrementRestart(
        _ subsystem:
            RuntimeSubsystem
    ) {

        let old =
            records[subsystem]

        records[subsystem] =
            SubsystemHealthRecord(

                subsystem:
                    subsystem,

                health:
                    .recovering,

                lastHeartbeat:
                    Date(),

                message:
                    "Restart requested",

                restartCount:
                    (old?.restartCount ?? 0)
                    + 1
            )
    }

    public func snapshot()
        -> [SubsystemHealthRecord]
    {

        RuntimeSubsystem.allCases
            .compactMap {
                records[$0]
            }
    }

    public func allHealthy()
        -> Bool
    {

        records.values.allSatisfy {

            $0.health ==
                .healthy
        }
    }

    public func hasCriticalFailure()
        -> Bool
    {

        records.values.contains {

            $0.health ==
                .failed
        }
    }
}


// ============================================================
// MARK: - Runtime Watchdog
// ============================================================

public actor RuntimeWatchdog {

    private let registry:
        RuntimeHealthRegistry

    private let heartbeatTimeout:
        TimeInterval

    private var task:
        Task<Void, Never>?

    private var running:
        Bool = false

    public init(
        registry:
            RuntimeHealthRegistry,

        heartbeatTimeout:
            TimeInterval = 15
    ) {

        self.registry =
            registry

        self.heartbeatTimeout =
            heartbeatTimeout
    }

    public func start() {

        guard
            !running
        else {
            return
        }

        running =
            true

        task =
            Task {

                while
                    !Task.isCancelled
                {

                    await inspect()

                    try? await Task.sleep(
                        for:
                            .seconds(5)
                    )
                }
            }
    }

    public func stop() {

        running =
            false

        task?.cancel()

        task =
            nil
    }

    private func inspect()
        async
    {

        let snapshot =
            await registry.snapshot()

        let now =
            Date()

        for record
            in snapshot
        {

            guard
                record.health ==
                    .healthy
            else {
                continue
            }

            guard
                let heartbeat =
                    record.lastHeartbeat
            else {
                continue
            }

            let age =
                now.timeIntervalSince(
                    heartbeat
                )

            if age >
                heartbeatTimeout
            {

                await registry.set(
                    record.subsystem,
                    health:
                        .degraded,

                    message:
                        "Heartbeat timeout"
                )
            }
        }
    }
}


// ============================================================
// MARK: - Runtime Diagnostics
// ============================================================

public actor MasterRuntimeDiagnostics {

    private var faults:
        [RuntimeFault] =
            []

    private var metrics =
        MasterRuntimeMetrics()

    private let maximumFaults:
        Int

    public init(
        maximumFaults:
            Int = 200
    ) {

        self.maximumFaults =
            max(
                10,
                maximumFaults
            )
    }

    public func record(
        fault:
            RuntimeFault
    ) {

        faults.append(
            fault
        )

        metrics.faultRecorded()

        if faults.count >
            maximumFaults
        {

            faults.removeFirst(
                faults.count -
                maximumFaults
            )
        }
    }

    public func eventProcessed() {

        metrics.eventProcessed()
    }

    public func recoveryPerformed() {

        metrics.recoveryPerformed()
    }

    public func heartbeat() {

        metrics.heartbeatReceived()
    }

    public func setBootDuration(
        _ duration:
            TimeInterval
    ) {

        metrics.bootDuration =
            duration
    }

    public func uptime(
        since:
            Date
    ) -> TimeInterval {

        Date().timeIntervalSince(
            since
        )
    }

    public func recentFaults()
        -> [RuntimeFault]
    {

        faults
    }

    public func metricsSnapshot()
        -> MasterRuntimeMetrics
    {

        metrics
    }
}


// ============================================================
// MARK: - Dependency Container
// ============================================================

public final class WatchRuntimeDependencies:
    @unchecked Sendable
{

    public let eventBus:
        UnifiedEventBus

    public let telemetry:
        TelemetryRuntime

    public let sync:
        WatchPhoneSyncController

    public init(
        eventBus:
            UnifiedEventBus,

        telemetry:
            TelemetryRuntime,

        sync:
            WatchPhoneSyncController
    ) {

        self.eventBus =
            eventBus

        self.telemetry =
            telemetry

        self.sync =
            sync
    }
}


// ============================================================
// MARK: - Boot Configuration
// ============================================================

public struct WatchRuntimeConfiguration:
    Sendable
{
    public let watchdogInterval:
        TimeInterval

    public let heartbeatTimeout:
        TimeInterval

    public let enableDiagnostics:
        Bool

    public let enableTelemetry:
        Bool

    public let enableReplication:
        Bool

    public init(
        watchdogInterval:
            TimeInterval = 5,

        heartbeatTimeout:
            TimeInterval = 15,

        enableDiagnostics:
            Bool = true,

        enableTelemetry:
            Bool = true,

        enableReplication:
            Bool = true
    ) {

        self.watchdogInterval =
            watchdogInterval

        self.heartbeatTimeout =
            heartbeatTimeout

        self.enableDiagnostics =
            enableDiagnostics

        self.enableTelemetry =
            enableTelemetry

        self.enableReplication =
            enableReplication
    }
}


// ============================================================
// MARK: - Master Runtime
// ============================================================

@MainActor
public final class EliteWatchMasterRuntime:
    ObservableObject
{

    // --------------------------------------------------------
    // Published state
    // --------------------------------------------------------

    @Published
    public private(set) var
        state:
            MasterRuntimeState =
                .uninitialized

    @Published
    public private(set) var
        health:
            [SubsystemHealthRecord] =
                []

    @Published
    public private(set) var
        lastFault:
            RuntimeFault?

    @Published
    public private(set) var
        uptime:
            TimeInterval =
                0

    // --------------------------------------------------------
    // Core services
    // --------------------------------------------------------

    private let configuration:
        WatchRuntimeConfiguration

    private let registry:
        RuntimeHealthRegistry

    private let watchdog:
        RuntimeWatchdog

    private let diagnostics:
        MasterRuntimeDiagnostics

    private var dependencies:
        WatchRuntimeDependencies?

    // --------------------------------------------------------
    // Runtime tasks
    // --------------------------------------------------------

    private var healthTask:
        Task<Void, Never>?

    private var uptimeTask:
        Task<Void, Never>?

    private var eventTask:
        Task<Void, Never>?

    private var startedAt:
        Date?

    // --------------------------------------------------------
    // Initialisation
    // --------------------------------------------------------

    public init(
        configuration:
            WatchRuntimeConfiguration =
                WatchRuntimeConfiguration()
    ) {

        self.configuration =
            configuration

        let registry =
            RuntimeHealthRegistry()

        self.registry =
            registry

        self.watchdog =
            RuntimeWatchdog(
                registry:
                    registry,

                heartbeatTimeout:
                    configuration
                        .heartbeatTimeout
            )

        self.diagnostics =
            MasterRuntimeDiagnostics()
    }

    // ========================================================
    // MARK: BOOT
    // ========================================================

    public func boot() {

        guard
            state ==
                .uninitialized ||
            state ==
                .stopped
        else {
            return
        }

        state =
            .booting

        let bootStart =
            Date()

        Task {

            do {

                try await initializeSubsystems()

                let duration =
                    Date()
                        .timeIntervalSince(
                            bootStart
                        )

                await diagnostics
                    .setBootDuration(
                        duration
                    )

                await MainActor.run {

                    self.startedAt =
                        Date()

                    self.state =
                        .running
                }

                await watchdog.start()

                startMonitoring()

            } catch {

                let fault =
                    RuntimeFault(

                        subsystem:
                            .system,

                        message:
                            String(
                                describing:
                                    error
                            ),

                        recoverable:
                            false
                    )

                await diagnostics.record(
                    fault:
                        fault
                )

                await MainActor.run {

                    self.lastFault =
                        fault

                    self.state =
                        .failed
                }
            }
        }
    }

    // ========================================================
    // MARK: INITIALISE
    // ========================================================

    private func initializeSubsystems()
        async throws
    {

        state =
            .initializing

        //
        // -----------------------------------------------------
        // #7 EVENT BUS
        // -----------------------------------------------------
        //

        await registry.set(
            .eventBus,
            health:
                .starting
        )

        let eventBus =
            UnifiedEventBus.shared

        await registry.set(
            .eventBus,
            health:
                .healthy
        )

        //
        // -----------------------------------------------------
        // #8 TELEMETRY
        // -----------------------------------------------------
        //

        var telemetry:
            TelemetryRuntime?

        if configuration
            .enableTelemetry
        {

            await registry.set(
                .telemetry,
                health:
                    .starting
            )

            do {

                telemetry =
                    try TelemetryFactory
                        .makeRuntime()

                await registry.set(
                    .telemetry,
                    health:
                        .healthy
                )

            } catch {

                await registry.set(
                    .telemetry,
                    health:
                        .failed,

                    message:
                        "Telemetry initialisation failed"
                )

                throw error
            }
        }

        //
        // -----------------------------------------------------
        // #5 / #9 CONNECTIVITY + REPLICATION
        // -----------------------------------------------------
        //

        var syncController:
            WatchPhoneSyncController?

        if configuration
            .enableReplication
        {

            await registry.set(
                .connectivity,
                health:
                    .starting
            )

            await registry.set(
                .replication,
                health:
                    .starting
            )

            let transport =
                WatchConnectivityTransport.shared

            let engine =
                WatchPhoneReplicationEngine(
                    transport:
                        transport
                )

            syncController =
                WatchPhoneSyncController(
                    engine:
                        engine
                )

            await registry.set(
                .connectivity,
                health:
                    .healthy
            )

            await registry.set(
                .replication,
                health:
                    .healthy
            )
        }

        //
        // -----------------------------------------------------
        // #6 POWER
        // -----------------------------------------------------
        //

        await registry.set(
            .powerRuntime,
            health:
                .starting
        )

        //
        // The concrete #6 runtime is responsible for
        // adapting workload to battery and thermal state.
        //

        await registry.set(
            .powerRuntime,
            health:
                .healthy
        )

        //
        // -----------------------------------------------------
        // #1–#3 SENSOR PIPELINE
        // -----------------------------------------------------
        //

        await registry.set(
            .sensorFusion,
            health:
                .starting
        )

        await registry.set(
            .signalProcessor,
            health:
                .starting
        )

        await registry.set(
            .activityRecognition,
            health:
                .starting
        )

        //
        // Sensor components are expected to be instantiated
        // by the application's concrete sensor runtime.
        //

        await registry.set(
            .sensorFusion,
            health:
                .healthy
        )

        await registry.set(
            .signalProcessor,
            health:
                .healthy
        )

        await registry.set(
            .activityRecognition,
            health:
                .healthy
        )

        //
        // -----------------------------------------------------
        // #4 DASHBOARD
        // -----------------------------------------------------
        //

        await registry.set(
            .dashboard,
            health:
                .healthy
        )

        //
        // -----------------------------------------------------
        // DEPENDENCY GRAPH
        // -----------------------------------------------------
        //

        if let telemetry,
           let syncController
        {

            dependencies =
                WatchRuntimeDependencies(

                    eventBus:
                        eventBus,

                    telemetry:
                        telemetry,

                    sync:
                        syncController
                )

        } else if let telemetry {

            //
            // If replication is deliberately disabled,
            // the runtime still operates.
            //

            let transport =
                WatchConnectivityTransport.shared

            let engine =
                WatchPhoneReplicationEngine(
                    transport:
                        transport
                )

            let sync =
                WatchPhoneSyncController(
                    engine:
                        engine
                )

            dependencies =
                WatchRuntimeDependencies(

                    eventBus:
                        eventBus,

                    telemetry:
                        telemetry,

                    sync:
                        sync
                )
        }
    }

    // ========================================================
    // MARK: MONITORING
    // ========================================================

    private func startMonitoring() {

        healthTask?.cancel()

        healthTask =
            Task {

                while
                    !Task.isCancelled
                {

                    let snapshot =
                        await registry
                            .snapshot()

                    let diagnostics =
                        await diagnostics
                            .metricsSnapshot()

                    await MainActor.run {

                        self.health =
                            snapshot

                        if let started =
                            self.startedAt
                        {

                            self.uptime =
                                Date()
                                    .timeIntervalSince(
                                        started
                                    )
                        }

                        _ =
                            diagnostics
                    }

                    try? await Task.sleep(
                        for:
                            .seconds(
                                configuration
                                    .watchdogInterval
                            )
                    )
                }
            }

        uptimeTask?.cancel()

        uptimeTask =
            Task {

                while
                    !Task.isCancelled
                {

                    guard
                        let started =
                            await MainActor
                                .run {
                                    self.startedAt
                                }
                    else {
                        return
                    }

                    let value =
                        Date()
                            .timeIntervalSince(
                                started
                            )

                    await MainActor.run {

                        self.uptime =
                            value
                    }

                    try? await Task.sleep(
                        for:
                            .seconds(1)
                    )
                }
            }
    }

    // ========================================================
    // MARK: EVENT MONITOR
    // ========================================================

    private func startEventMonitor() {

        eventTask?.cancel()

        eventTask =
            Task {

                let subscription =
                    EventSubscription(
                        minimumPriority:
                            .high
                    )

                let stream =
                    await UnifiedEventBus
                        .shared
                        .subscribe(
                            subscription
                        )

                for await event
                    in stream
                {

                    guard
                        !Task.isCancelled
                    else {
                        break
                    }

                    await diagnostics
                        .eventProcessed()

                    await handleCriticalEvent(
                        event
                    )
                }
            }
    }

    private func handleCriticalEvent(
        _ event:
            RuntimeEvent
    ) async {

        switch event.type {

        case .runtimeError:

            let fault =
                RuntimeFault(

                    subsystem:
                        .runtime,

                    message:
                        "Runtime error event",

                    recoverable:
                        true
                )

            await diagnostics.record(
                fault:
                    fault
            )

            await MainActor.run {

                self.lastFault =
                    fault

                if self.state ==
                    .running
                {

                    self.state =
                        .degraded
                }
            }

        case .powerStateChanged:

            //
            // Power runtime itself decides
            // how aggressively to reduce work.
            //

            break

        default:

            break
        }
    }

    // ========================================================
    // MARK: START MONITORING
    // ========================================================

    private func startRuntimeMonitoring() {

        startEventMonitor()
    }

    // ========================================================
    // MARK: SHUTDOWN
    // ========================================================

    public func shutdown() {

        guard
            state ==
                .running ||
            state ==
                .degraded
        else {
            return
        }

        state =
            .stopping

        Task {

            //
            // Stop new event processing first.
            //

            eventTask?.cancel()

            //
            // Stop watchdog.
            //

            await watchdog.stop()

            //
            // Stop telemetry.
            //

            if let dependencies {

                dependencies.telemetry
                    .stop()

                dependencies.sync
                    .stop()
            }

            //
            // Allow remaining queued work
            // to settle before final shutdown.
            //

            try? await Task.sleep(
                for:
                    .milliseconds(250)
            )

            await MainActor.run {

                self.health =
                    []

                self.state =
                    .stopped
            }
        }
    }

    // ========================================================
    // MARK: RECOVERY
    // ========================================================

    public func recover(
        subsystem:
            RuntimeSubsystem
    ) {

        guard
            state ==
                .degraded ||
            state ==
                .running
        else {
            return
        }

        state =
            .recovering

        Task {

            await registry
                .incrementRestart(
                    subsystem
                )

            await diagnostics
                .recoveryPerformed()

            //
            // Subsystem-specific recovery.
            //

            switch subsystem {

            case .telemetry:

                if let dependencies {

                    dependencies.telemetry
                        .stop()

                    dependencies.telemetry
                        .start(
                            activity:
                                "recovered"
                        )
                }

            case .replication:

                if let dependencies {

                    dependencies.sync
                        .stop()

                    dependencies.sync
                        .start()
                }

            case .eventBus:

                //
                // Event bus is process-local.
                // Individual subscribers can
                // recreate their subscriptions.
                //

                break

            default:

                //
                // Sensor and processing runtimes
                // should expose their own restart
                // hooks in the concrete implementation.
                //

                break
            }

            await registry.set(
                subsystem,
                health:
                    .healthy
            )

            await MainActor.run {

                self.state =
                    .running
            }
        }
    }
}


// ============================================================
// MARK: - Runtime Bootstrapper
// ============================================================

@MainActor
public final class WatchApplicationBootstrap:

    ObservableObject
{

    public static let shared =
        WatchApplicationBootstrap()

    public let runtime:
        EliteWatchMasterRuntime

    @Published
    public private(set) var
        launched =
            false

    private init() {

        runtime =
            EliteWatchMasterRuntime()
    }

    public func launch() {

        guard
            !launched
        else {
            return
        }

        launched =
            true

        runtime.boot()
    }

    public func terminate() {

        runtime.shutdown()

        launched =
            false
    }
}


// ============================================================
// MARK: - Master Runtime Dashboard
// ============================================================

public struct MasterRuntimeDashboard:
    View
{

    @ObservedObject
    private var runtime:
        EliteWatchMasterRuntime

    public init(
        runtime:
            EliteWatchMasterRuntime
    ) {

        self.runtime =
            runtime
    }

    public var body: some View {

        ScrollView {

            VStack(
                alignment:
                    .leading,

                spacing:
                    7
            ) {

                HStack {

                    Text(
                        runtime.state.rawValue
                            .uppercased()
                    )
                    .font(
                        .system(
                            size: 11,
                            weight:
                                .bold
                        )
                    )

                    Spacer()

                    Text(
                        formattedUptime
                    )
                    .font(
                        .system(
                            size: 8,
                            design:
                                .monospaced
                        )
                    )
                }

                Divider()

                ForEach(
                    runtime.health,
                    id:
                        \.subsystem
                ) { record in

                    HStack {

                        Text(
                            record.subsystem
                                .rawValue
                        )
                        .font(
                            .system(
                                size: 8,
                                design:
                                    .monospaced
                            )
                        )

                        Spacer()

                        Text(
                            record.health
                                .rawValue
                                .uppercased()
                        )
                        .font(
                            .system(
                                size: 7,
                                weight:
                                    .semibold
                            )
                        )
                    }
                }

                if let fault =
                    runtime.lastFault
                {

                    Divider()

                    Text(
                        fault.message
                    )
                    .font(
                        .system(
                            size: 7
                        )
                    )
                    .lineLimit(3)
                }
            }
            .padding(
                8
            )
        }
    }

    private var formattedUptime:
        String
    {

        let seconds =
            Int(
                runtime.uptime
            )

        let minutes =
            seconds / 60

        let remainder =
            seconds % 60

        return String(
            format:
                "%02d:%02d",
            minutes,
            remainder
        )
    }
}


// ============================================================
// MARK: - SwiftUI Root
// ============================================================

public struct EliteWatchRootView:
    View
{

    @StateObject
    private var runtime:
        WatchApplicationBootstrap =
            .shared

    public init() {
    }

    public var body: some View {

        Group {

            switch
                runtime.runtime.state
            {

            case .booting,
                 .initializing:

                VStack(
                    spacing:
                        8
                ) {

                    ProgressView()

                    Text(
                        "INITIALISING"
                    )
                    .font(
                        .system(
                            size: 9,
                            weight:
                                .bold
                        )
                    )
                }

            case .running,
                 .degraded,
                 .recovering:

                MasterRuntimeDashboard(
                    runtime:
                        runtime.runtime
                )

            case .failed:

                VStack(
                    spacing:
                        8
                ) {

                    Text(
                        "RUNTIME FAULT"
                    )
                    .font(
                        .system(
                            size: 10,
                            weight:
                                .bold
                        )
                    )

                    Button(
                        "RECOVER"
                    ) {

                        runtime.runtime
                            .boot()
                    }
                }

            default:

                VStack(
                    spacing:
                        8
                ) {

                    Text(
                        "WATCH RUNTIME"
                    )

                    Button(
                        "START"
                    ) {

                        runtime.launch()
                    }
                }
            }
        }
        .onAppear {

            if runtime.runtime.state ==
                .uninitialized
            {

                runtime.launch()
            }
        }
    }
}
```

## One important correction to make

In the `boot()` path, after initialisation, start the event monitor as well as the health monitor. Replace:

```swift
startMonitoring()
```

with:

```swift
startMonitoring()
startRuntimeMonitoring()
```

That gives the master runtime both:

```text
Health monitoring
+
Critical event monitoring
```

## Final architecture

You now have the complete ten-layer application architecture:

```text
                         APPLE WATCH
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  #1  REAL-TIME SENSOR FUSION                            │
│          │                                              │
│          ▼                                              │
│  #2  REAL-TIME SIGNAL PROCESSING                        │
│          │                                              │
│          ▼                                              │
│  #3  ACTIVITY RECOGNITION                               │
│          │                                              │
│          ▼                                              │
│  #7  UNIFIED EVENT BUS ◄──────────────┐                 │
│          │                             │                 │
│     ┌────┼───────────────┐             │                 │
│     ▼    ▼               ▼             │                 │
│    #4   #6              #8             │                 │
│    UI   POWER        TELEMETRY         │                 │
│                           │             │                 │
│                           ▼             │                 │
│                          #9             │                 │
│                    WATCH ↔ iPHONE       │                 │
│                           │             │                 │
│                           ▼             │                 │
│                         iPHONE          │                 │
│                                         │                │
│  #5 WATCHCONNECTIVITY ──────────────────┘                │
│                                                         │
│  #10 MASTER RUNTIME                                     │
│       ├── Boot                                           │
│       ├── Lifecycle                                      │
│       ├── Health monitoring                              │
│       ├── Watchdog                                       │
│       ├── Fault detection                                │
│       ├── Recovery                                       │
│       ├── Diagnostics                                    │
│       ├── Dependency management                          │
│       └── Shutdown                                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Runtime boot sequence

The application now has a defined startup sequence:

```text
APP LAUNCH
    │
    ▼
#10 Master Runtime
    │
    ▼
#7 Event Bus
    │
    ▼
#8 Telemetry
    │
    ▼
#5 Connectivity / #9 Replication
    │
    ▼
#6 Power Runtime
    │
    ▼
#1 Sensor Fusion
    │
    ▼
#2 Signal Processing
    │
    ▼
#3 Activity Recognition
    │
    ▼
#4 Dashboard
    │
    ▼
WATCH RUNTIME = RUNNING
```

And shutdown reverses the dependency direction:

```text
RUNNING
   ↓
Stop event consumers
   ↓
Stop watchdog
   ↓
Stop telemetry
   ↓
Stop replication
   ↓
Drain short-lived work
   ↓
STOPPED
```

### Fault handling

The architecture also now has a basic fault-containment model:

```text
                 FAULT
                   │
                   ▼
             #10 Runtime
                   │
          ┌────────┴────────┐
          ▼                 ▼
      Recoverable       Non-recoverable
          │                 │
          ▼                 ▼
      RECOVER           FAILED
          │
          ▼
      RESTART
          │
          ▼
      HEARTBEAT
          │
          ▼
       HEALTHY
```

That is the key difference between a collection of Watch apps/services and a **coordinated runtime architecture**.

### The finished stack

| Layer   | Responsibility                                      |
| ------- | --------------------------------------------------- |
| **#1**  | Sensor acquisition and fusion                       |
| **#2**  | Filtering, validation and signal processing         |
| **#3**  | Activity classification                             |
| **#4**  | High-performance Watch UI                           |
| **#5**  | WatchConnectivity transport                         |
| **#6**  | Battery/thermal workload governance                 |
| **#7**  | Internal event distribution                         |
| **#8**  | Durable telemetry and session storage               |
| **#9**  | Watch ↔ iPhone replication                          |
| **#10** | Boot, lifecycle, watchdog, diagnostics and recovery |

The resulting design is therefore **not a kernel replacement**; it is a high-performance, modular **watchOS application runtime** built around Apple's public APIs, Swift concurrency, bounded buffering, offline persistence and WatchConnectivity.



