//
//  IOSLatencyEngine.swift
//
//  Pure Swift iOS application latency engine.
//
//  Goals:
//  - Keep UI work off the main thread
//  - Prioritise interactive tasks
//  - Avoid unnecessary allocations
//  - Detect frame drops
//  - Monitor thermal state
//  - Monitor memory pressure
//  - Cancel stale work
//  - Batch background work
//  - Maintain responsive networking
//
//  Designed for iOS 17+.
//

import Foundation
import UIKit
import os


// ============================================================
// MARK: - Priority
// ============================================================

enum LatencyPriority {

    case realtime
    case userInteractive
    case userInitiated
    case utility
    case background

    var qos:
        DispatchQoS.QoSClass {

        switch self {

        case .realtime:
            return .userInteractive

        case .userInteractive:
            return .userInteractive

        case .userInitiated:
            return .userInitiated

        case .utility:
            return .utility

        case .background:
            return .background
        }
    }
}


// ============================================================
// MARK: - Task
// ============================================================

struct LatencyTask {

    let id:
        UUID

    let priority:
        LatencyPriority

    let created:
        ContinuousClock.Instant

    let operation:
        @Sendable () async -> Void
}


// ============================================================
// MARK: - Latency Metrics
// ============================================================

struct LatencyMetrics {

    var frameTimeMS:
        Double = 0

    var droppedFrames:
        Int = 0

    var mainThreadLatencyMS:
        Double = 0

    var memoryMB:
        Double = 0

    var thermalState:
        ProcessInfo.ThermalState =
            .nominal

    var activeTasks:
        Int = 0

    var completedTasks:
        Int = 0

    var cancelledTasks:
        Int = 0
}


// ============================================================
// MARK: - Main Thread Monitor
// ============================================================

final class MainThreadMonitor {

    private let logger =
        Logger(
            subsystem:
                "Aureom.iOSLatency",
            category:
                "MainThread"
        )

    private var timer:
        DispatchSourceTimer?

    private var lastTick:
        UInt64 = 0

    private(set) var latencyMS:
        Double = 0


    func start() {

        let timer =
            DispatchSource.makeTimerSource(
                queue:
                    DispatchQueue.main
            )

        self.timer =
            timer

        lastTick =
            DispatchTime
                .now()
                .uptimeNanoseconds

        timer.schedule(
            deadline:
                .now(),
            repeating:
                .milliseconds(100)
        )

        timer.setEventHandler {

            [weak self] in

            guard let self
            else {
                return
            }

            let current =
                DispatchTime
                    .now()
                    .uptimeNanoseconds

            let expected =
                self.lastTick +
                100_000_000

            let delay =
                current > expected
                ? current - expected
                : 0

            self.latencyMS =
                Double(delay) /
                1_000_000.0

            self.lastTick =
                current

            if self.latencyMS > 32 {

                self.logger.warning(
                    """
                    Main thread latency:
                    \(self.latencyMS) ms
                    """
                )
            }
        }

        timer.resume()
    }


    func stop() {

        timer?.cancel()

        timer = nil
    }
}


// ============================================================
// MARK: - Frame Monitor
// ============================================================

final class FrameMonitor {

    private var displayLink:
        CADisplayLink?

    private var previousTimestamp:
        CFTimeInterval = 0

    private(set) var frameTimeMS:
        Double = 0

    private(set) var droppedFrames:
        Int = 0


    func start() {

        let link =
            CADisplayLink(
                target:
                    self,
                selector:
                    #selector(
                        tick
                    )
            )

        displayLink =
            link

        link.add(
            to:
                .main,
            forMode:
                .common
        )
    }


    func stop() {

        displayLink?.invalidate()

        displayLink = nil
    }


    @objc
    private func tick(
        _ link:
            CADisplayLink
    ) {

        if previousTimestamp != 0 {

            let delta =
                link.timestamp -
                previousTimestamp

            frameTimeMS =
                delta *
                1000

            /*
             A 60 Hz display has roughly
             16.67 ms per frame.

             A 120 Hz display has roughly
             8.33 ms.
            */

            let expected =
                1.0 /
                link.preferredFramesPerSecond

            if delta >
                expected * 1.5 {

                droppedFrames += 1
            }
        }

        previousTimestamp =
            link.timestamp
    }
}


// ============================================================
// MARK: - Memory Monitor
// ============================================================

final class MemoryMonitor {

    private(set) var memoryMB:
        Double = 0


    func update() {

        var info =
            mach_task_basic_info()

        var count =
            mach_msg_type_number_t(
                MemoryLayout<
                    mach_task_basic_info
                >.size
                /
                MemoryLayout<
                    natural_t
                >.size
            )

        let result =
            withUnsafeMutablePointer(
                to:
                    &info
            ) {

                pointer in

                pointer.withMemoryRebound(
                    to:
                        integer_t.self,
                    capacity:
                        Int(count)
                ) {

                    task_info(
                        mach_task_self_,
                        task_flavor_t(
                            MACH_TASK_BASIC_INFO
                        ),
                        $0,
                        &count
                    )
                }
            }

        if result ==
            KERN_SUCCESS {

            memoryMB =
                Double(
                    info.resident_size
                )
                /
                1024
                /
                1024
        }
    }
}


// ============================================================
// MARK: - Thermal Manager
// ============================================================

final class ThermalManager {

    private(set) var state:
        ProcessInfo.ThermalState =
            .nominal

    func start() {

        state =
            ProcessInfo
                .processInfo
                .thermalState

        NotificationCenter.default.addObserver(
            forName:
                ProcessInfo
                    .thermalStateDidChangeNotification,
            object:
                nil,
            queue:
                .main
        ) {

            [weak self] _ in

            self?.state =
                ProcessInfo
                    .processInfo
                    .thermalState
        }
    }


    func recommendedPriority()
        -> LatencyPriority {

        switch state {

        case .nominal:
            return .userInitiated

        case .fair:
            return .utility

        case .serious:
            return .utility

        case .critical:
            return .background

        @unknown default:
            return .utility
        }
    }
}


// ============================================================
// MARK: - Latency Scheduler
// ============================================================

actor LatencyScheduler {

    private var tasks:
        [UUID: Task<Void, Never>] = [:]

    private(set) var completed:
        Int = 0

    private(set) var cancelled:
        Int = 0


    func submit(
        priority:
            LatencyPriority,

        operation:
            @escaping @Sendable () async -> Void
    )
        -> UUID
    {

        let id =
            UUID()

        let task =
            Task.detached(
                priority:
                    priority.taskPriority
            ) {

                await operation()
            }

        tasks[id] =
            task

        return id
    }


    func cancel(
        _ id:
            UUID
    ) {

        tasks[id]?.cancel()

        tasks.removeValue(
            forKey:
                id
        )

        cancelled += 1
    }


    func cancelBackgroundWork() {

        for (
            _,
            task
        ) in tasks {

            task.cancel()
        }

        cancelled +=
            tasks.count

        tasks.removeAll()
    }


    func taskFinished(
        _ id:
            UUID
    ) {

        tasks.removeValue(
            forKey:
                id
        )

        completed += 1
    }


    var activeCount:
        Int {

        tasks.count
    }
}


// ============================================================
// MARK: - Swift Priority Bridge
// ============================================================

extension LatencyPriority {

    var taskPriority:
        TaskPriority {

        switch self {

        case .realtime:
            return .high

        case .userInteractive:
            return .high

        case .userInitiated:
            return .high

        case .utility:
            return .medium

        case .background:
            return .low
        }
    }
}


// ============================================================
// MARK: - Debouncer
// ============================================================

actor LatencyDebouncer {

    private var current:
        Task<Void, Never>?


    func submit(
        delay:
            UInt64,
        operation:
            @escaping @Sendable () async -> Void
    ) {

        current?.cancel()

        current =
            Task {

                try? await Task.sleep(
                    nanoseconds:
                        delay
                )

                guard
                    !Task.isCancelled
                else {
                    return
                }

                await operation()
            }
    }
}


// ============================================================
// MARK: - Cache
// ============================================================

actor FastCache<Key: Hashable, Value> {

    private var storage:
        [Key: Value] = [:]


    func get(
        _ key:
            Key
    )
        -> Value?
    {

        storage[key]
    }


    func set(
        _ value:
            Value,
        for key:
            Key
    ) {

        storage[key] =
            value
    }


    func remove(
        _ key:
            Key
    ) {

        storage.removeValue(
            forKey:
                key
        )
    }


    func clear() {

        storage.removeAll(
            keepingCapacity:
                true
        )
    }
}


// ============================================================
// MARK: - Network Optimiser
// ============================================================

final class FastNetwork {

    private let session:
        URLSession


    init() {

        let configuration =
            URLSessionConfiguration
                .ephemeral

        configuration
            .waitsForConnectivity =
            false

        configuration
            .httpMaximumConnectionsPerHost =
            6

        configuration
            .timeoutIntervalForRequest =
            10

        configuration
            .timeoutIntervalForResource =
            20

        configuration
            .requestCachePolicy =
            .returnCacheDataElseLoad

        session =
            URLSession(
                configuration:
                    configuration
            )
    }


    func get(
        _ url:
            URL
    ) async throws
        -> Data
    {

        let (
            data,
            _
        ) =
            try await session.data(
                from:
                    url
            )

        return data
    }
}


// ============================================================
// MARK: - Master Engine
// ============================================================

@MainActor
final class IOSLatencyEngine {

    static let shared =
        IOSLatencyEngine()

    private let scheduler =
        LatencyScheduler()

    private let mainMonitor =
        MainThreadMonitor()

    private let frameMonitor =
        FrameMonitor()

    private let memoryMonitor =
        MemoryMonitor()

    private let thermalManager =
        ThermalManager()

    private let logger =
        Logger(
            subsystem:
                "Aureom.iOSLatency",
            category:
                "Core"
        )

    private(set) var metrics =
        LatencyMetrics()

    private var monitorTimer:
        Timer?


    // ========================================================
    // START
    // ========================================================

    func start() {

        mainMonitor.start()

        frameMonitor.start()

        thermalManager.start()

        monitorTimer =
            Timer.scheduledTimer(
                withTimeInterval:
                    1.0,
                repeats:
                    true
            ) {

                [weak self] _ in

                self?.updateMetrics()
            }

        logger.info(
            "iOS latency engine started"
        )
    }


    // ========================================================
    // METRICS
    // ========================================================

    private func updateMetrics() {

        memoryMonitor.update()

        metrics.frameTimeMS =
            frameMonitor.frameTimeMS

        metrics.droppedFrames =
            frameMonitor.droppedFrames

        metrics.mainThreadLatencyMS =
            mainMonitor.latencyMS

        metrics.memoryMB =
            memoryMonitor.memoryMB

        metrics.thermalState =
            thermalManager.state

        Task {

            metrics.activeTasks =
                await scheduler.activeCount

            metrics.completedTasks =
                await scheduler.completed

            metrics.cancelledTasks =
                await scheduler.cancelled
        }
    }


    // ========================================================
    // SUBMIT WORK
    // ========================================================

    func submit(
        priority:
            LatencyPriority,

        operation:
            @escaping @Sendable () async -> Void
    ) {

        Task {

            await scheduler.submit(
                priority:
                    priority,
                operation:
                    operation
            )
        }
    }


    // ========================================================
    // USER INTERACTION
    // ========================================================

    func userInteraction(
        operation:
            @escaping @Sendable () async -> Void
    ) {

        submit(
            priority:
                .userInteractive,
            operation:
                operation
        )
    }


    // ========================================================
    // BACKGROUND
    // ========================================================

    func background(
        operation:
            @escaping @Sendable () async -> Void
    ) {

        submit(
            priority:
                .background,
            operation:
                operation
        )
    }


    // ========================================================
    // THERMAL ADAPTATION
    // ========================================================

    func adaptivePriority()
        -> LatencyPriority {

        return thermalManager
            .recommendedPriority()
    }


    // ========================================================
    // MEMORY PRESSURE RESPONSE
    // ========================================================

    func handleMemoryWarning() {

        logger.warning(
            "Memory pressure detected"
        )

        /*
         Cancel work that doesn't
         contribute to immediate UI.
         */

        Task {

            await scheduler
                .cancelBackgroundWork()
        }
    }


    // ========================================================
    // SHUTDOWN
    // ========================================================

    func stop() {

        monitorTimer?.invalidate()

        monitorTimer = nil

        mainMonitor.stop()

        frameMonitor.stop()

        Task {

            await scheduler
                .cancelBackgroundWork()
        }

        logger.info(
            "iOS latency engine stopped"
        )
    }
}


// ============================================================
// MARK: - Usage
// ============================================================

final class ApplicationPerformance {

    func start() {

        let engine =
            IOSLatencyEngine.shared

        engine.start()


        // ----------------------------------------------------
        // Interactive operation
        // ----------------------------------------------------

        engine.userInteraction {

            // Fast user-facing work.

            print(
                "Interactive task"
            )
        }


        // ----------------------------------------------------
        // Background operation
        // ----------------------------------------------------

        engine.background {

            // Expensive non-urgent work.

            print(
                "Background task"
            )
        }
    }
}
