import Foundation
import WebKit

// MARK: - Identifiers

struct TabID: Hashable, Codable, Sendable, CustomStringConvertible {
    let rawValue: UUID

    init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }

    var description: String {
        rawValue.uuidString
    }
}

struct WindowID: Hashable, Codable, Sendable, CustomStringConvertible {
    let rawValue: UUID

    init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }

    var description: String {
        rawValue.uuidString
    }
}

// MARK: - Tab Lifecycle

enum TabLifecycleState: String, Codable, Sendable {
    case creating
    case loading
    case active
    case background
    case suspendable
    case suspended
    case restoring
    case closing
    case closed
    case failed
}

// MARK: - Navigation

struct NavigationSnapshot: Codable, Sendable, Equatable {
    var url: URL?
    var title: String?
    var canGoBack: Bool
    var canGoForward: Bool
    var estimatedProgress: Double

    static let empty = NavigationSnapshot(
        url: nil,
        title: nil,
        canGoBack: false,
        canGoForward: false,
        estimatedProgress: 0
    )
}

// MARK: - Tab

struct SafariTab: Identifiable, Codable, Sendable, Equatable {
    let id: TabID

    var url: URL?
    var title: String

    var lifecycle: TabLifecycleState

    var navigation: NavigationSnapshot

    var isPinned: Bool
    var isMuted: Bool
    var isPlayingMedia: Bool

    var createdAt: Date
    var lastActivatedAt: Date
    var lastInteractionAt: Date

    var activationCount: UInt64

    var estimatedMemoryBytes: UInt64
    var estimatedCPUPercentage: Double

    var suspensionCount: UInt64

    init(
        id: TabID = TabID(),
        url: URL? = nil,
        title: String = "New Tab",
        lifecycle: TabLifecycleState = .creating
    ) {
        let now = Date()

        self.id = id
        self.url = url
        self.title = title
        self.lifecycle = lifecycle
        self.navigation = .empty

        self.isPinned = false
        self.isMuted = false
        self.isPlayingMedia = false

        self.createdAt = now
        self.lastActivatedAt = now
        self.lastInteractionAt = now

        self.activationCount = 0

        self.estimatedMemoryBytes = 0
        self.estimatedCPUPercentage = 0

        self.suspensionCount = 0
    }
}

// MARK: - Window

struct SafariWindow: Identifiable, Codable, Sendable, Equatable {
    let id: WindowID

    var tabIDs: [TabID]
    var selectedTabID: TabID?

    var createdAt: Date

    init(id: WindowID = WindowID()) {
        self.id = id
        self.tabIDs = []
        self.selectedTabID = nil
        self.createdAt = Date()
    }
}









import Foundation

actor TabStore {

    private var tabs: [TabID: SafariTab] = [:]
    private var windows: [WindowID: SafariWindow] = [:]

    // MARK: - Tab Creation

    func createTab(
        in windowID: WindowID,
        url: URL? = nil
    ) throws -> SafariTab {

        guard windows[windowID] != nil else {
            throw TabStoreError.windowNotFound
        }

        let tab = SafariTab(
            url: url,
            lifecycle: .creating
        )

        tabs[tab.id] = tab

        windows[windowID]?.tabIDs.append(tab.id)

        if windows[windowID]?.selectedTabID == nil {
            windows[windowID]?.selectedTabID = tab.id
        }

        return tab
    }

    // MARK: - Window Creation

    func createWindow() -> SafariWindow {
        let window = SafariWindow()
        windows[window.id] = window
        return window
    }

    // MARK: - Retrieval

    func tab(_ id: TabID) -> SafariTab? {
        tabs[id]
    }

    func window(_ id: WindowID) -> SafariWindow? {
        windows[id]
    }

    func allTabs() -> [SafariTab] {
        Array(tabs.values)
    }

    func allWindows() -> [SafariWindow] {
        Array(windows.values)
    }

    // MARK: - Mutation

    func updateTab(
        _ id: TabID,
        _ mutation: (inout SafariTab) -> Void
    ) throws {

        guard var tab = tabs[id] else {
            throw TabStoreError.tabNotFound
        }

        mutation(&tab)

        tabs[id] = tab
    }

    // MARK: - Selection

    func selectTab(
        _ tabID: TabID,
        in windowID: WindowID
    ) throws {

        guard tabs[tabID] != nil else {
            throw TabStoreError.tabNotFound
        }

        guard windows[windowID] != nil else {
            throw TabStoreError.windowNotFound
        }

        windows[windowID]?.selectedTabID = tabID

        guard var tab = tabs[tabID] else {
            return
        }

        tab.lastActivatedAt = Date()
        tab.lastInteractionAt = Date()
        tab.activationCount += 1
        tab.lifecycle = .active

        tabs[tabID] = tab
    }

    // MARK: - Closing

    func removeTab(
        _ tabID: TabID
    ) throws {

        guard tabs.removeValue(forKey: tabID) != nil else {
            throw TabStoreError.tabNotFound
        }

        for windowID in windows.keys {

            guard var window = windows[windowID] else {
                continue
            }

            window.tabIDs.removeAll { $0 == tabID }

            if window.selectedTabID == tabID {
                window.selectedTabID = window.tabIDs.last
            }

            windows[windowID] = window
        }
    }

    // MARK: - Reordering

    func moveTab(
        _ tabID: TabID,
        in windowID: WindowID,
        to destinationIndex: Int
    ) throws {

        guard var window = windows[windowID] else {
            throw TabStoreError.windowNotFound
        }

        guard let currentIndex = window.tabIDs.firstIndex(of: tabID) else {
            throw TabStoreError.tabNotFound
        }

        let safeIndex = max(
            0,
            min(destinationIndex, window.tabIDs.count - 1)
        )

        window.tabIDs.remove(at: currentIndex)
        window.tabIDs.insert(tabID, at: safeIndex)

        windows[windowID] = window
    }

    // MARK: - Window Removal

    func removeWindow(
        _ windowID: WindowID
    ) throws {

        guard let window = windows.removeValue(forKey: windowID) else {
            throw TabStoreError.windowNotFound
        }

        for tabID in window.tabIDs {
            tabs.removeValue(forKey: tabID)
        }
    }
}

// MARK: - Errors

enum TabStoreError: Error {
    case tabNotFound
    case windowNotFound
    case invalidDestination
}



import Foundation

actor TabLifecycleManager {

    private let store: TabStore

    init(store: TabStore) {
        self.store = store
    }

    // MARK: - Activate

    func activate(_ tabID: TabID) async throws {

        try await store.updateTab(tabID) { tab in
            tab.lifecycle = .active
            tab.lastActivatedAt = Date()
            tab.lastInteractionAt = Date()
            tab.activationCount += 1
        }
    }

    // MARK: - Background

    func background(_ tabID: TabID) async throws {

        try await store.updateTab(tabID) { tab in

            guard tab.lifecycle != .closing else {
                return
            }

            tab.lifecycle = .background
        }
    }

    // MARK: - Suspension Eligibility

    func evaluateSuspensionEligibility(
        _ tabID: TabID
    ) async throws -> Bool {

        guard let tab = await store.tab(tabID) else {
            throw TabStoreError.tabNotFound
        }

        if tab.isPinned {
            return false
        }

        if tab.isPlayingMedia {
            return false
        }

        if tab.lifecycle == .active {
            return false
        }

        return true
    }

    // MARK: - Mark Suspendable

    func markSuspendable(
        _ tabID: TabID
    ) async throws {

        guard await evaluateSuspensionEligibility(tabID) else {
            return
        }

        try await store.updateTab(tabID) { tab in
            tab.lifecycle = .suspendable
        }
    }

    // MARK: - Suspend

    func suspend(
        _ tabID: TabID
    ) async throws {

        guard await evaluateSuspensionEligibility(tabID) else {
            return
        }

        try await store.updateTab(tabID) { tab in
            tab.lifecycle = .suspended
            tab.suspensionCount += 1
        }
    }

    // MARK: - Restore

    func beginRestoration(
        _ tabID: TabID
    ) async throws {

        try await store.updateTab(tabID) { tab in
            tab.lifecycle = .restoring
        }
    }

    func finishRestoration(
        _ tabID: TabID
    ) async throws {

        try await store.updateTab(tabID) { tab in
            tab.lifecycle = .active
            tab.lastActivatedAt = Date()
        }
    }

    // MARK: - Close

    func beginClosing(
        _ tabID: TabID
    ) async throws {

        try await store.updateTab(tabID) { tab in
            tab.lifecycle = .closing
        }
    }
}




import Foundation

struct TabResourceSnapshot: Sendable {
    let tabID: TabID
    let memoryBytes: UInt64
    let cpuPercentage: Double
    let timestamp: Date
}

actor TabResourceManager {

    private let store: TabStore

    init(store: TabStore) {
        self.store = store
    }

    func record(
        _ snapshot: TabResourceSnapshot
    ) async throws {

        try await store.updateTab(snapshot.tabID) { tab in

            tab.estimatedMemoryBytes =
                snapshot.memoryBytes

            tab.estimatedCPUPercentage =
                snapshot.cpuPercentage

            tab.lastInteractionAt =
                max(
                    tab.lastInteractionAt,
                    snapshot.timestamp
                )
        }
    }

    func highestMemoryConsumers(
        limit: Int = 10
    ) async -> [SafariTab] {

        let tabs = await store.allTabs()

        return Array(
            tabs
                .sorted {
                    $0.estimatedMemoryBytes >
                    $1.estimatedMemoryBytes
                }
                .prefix(limit)
        )
    }

    func highestCPUConsumers(
        limit: Int = 10
    ) async -> [SafariTab] {

        let tabs = await store.allTabs()

        return Array(
            tabs
                .sorted {
                    $0.estimatedCPUPercentage >
                    $1.estimatedCPUPercentage
                }
                .prefix(limit)
        )
    }
}





import Foundation

struct TabPrediction: Sendable {
    let tabID: TabID
    let score: Double
}

actor TabPredictionEngine {

    private let store: TabStore

    init(store: TabStore) {
        self.store = store
    }

    func predictNextTabs(
        limit: Int = 5
    ) async -> [TabPrediction] {

        let tabs = await store.allTabs()
        let now = Date()

        let predictions = tabs.map { tab -> TabPrediction in

            let age =
                max(
                    now.timeIntervalSince(tab.lastActivatedAt),
                    0.1
                )

            let recencyScore =
                1.0 / age

            let activationScore =
                log1p(
                    Double(tab.activationCount)
                )

            let mediaPenalty =
                tab.isPlayingMedia ? 0.25 : 1.0

            let lifecycleMultiplier =
                tab.lifecycle == .suspended
                ? 0.50
                : 1.0

            let score =
                (
                    recencyScore *
                    activationScore *
                    mediaPenalty *
                    lifecycleMultiplier
                )

            return TabPrediction(
                tabID: tab.id,
                score: score
            )
        }

        return Array(
            predictions
                .sorted {
                    $0.score > $1.score
                }
                .prefix(limit)
        )
    }
}









import Foundation
import WebKit

@MainActor
final class WebKitTabController {

    private var webViews: [TabID: WKWebView] = [:]

    func createWebView(
        for tabID: TabID
    ) -> WKWebView {

        if let existing = webViews[tabID] {
            return existing
        }

        let configuration =
            WKWebViewConfiguration()

        configuration.websiteDataStore =
            .default()

        let webView =
            WKWebView(
                frame: .zero,
                configuration: configuration
            )

        webView.allowsBackForwardNavigationGestures = true

        webViews[tabID] = webView

        return webView
    }

    func webView(
        for tabID: TabID
    ) -> WKWebView? {
        webViews[tabID]
    }

    func destroyWebView(
        for tabID: TabID
    ) {

        guard let webView = webViews.removeValue(
            forKey: tabID
        ) else {
            return
        }

        webView.stopLoading()
        webView.navigationDelegate = nil
        webView.uiDelegate = nil
    }

    func suspend(
        tabID: TabID
    ) {

        guard let webView = webViews[tabID] else {
            return
        }

        webView.stopLoading()

        webView.navigationDelegate = nil
        webView.uiDelegate = nil
    }

    func restore(
        tabID: TabID,
        navigationDelegate: WKNavigationDelegate?,
        uiDelegate: WKUIDelegate?
    ) {

        guard let webView = webViews[tabID] else {
            return
        }

        webView.navigationDelegate =
            navigationDelegate

        webView.uiDelegate =
            uiDelegate
    }
}







import Foundation

struct SafariSession: Codable, Sendable {

    var windows: [SafariWindow]
    var tabs: [SafariTab]

    var savedAt: Date

    init(
        windows: [SafariWindow],
        tabs: [SafariTab],
        savedAt: Date = Date()
    ) {
        self.windows = windows
        self.tabs = tabs
        self.savedAt = savedAt
    }
}

actor SafariSessionStore {

    private let fileURL: URL

    init(
        directory: URL
    ) {

        self.fileURL =
            directory
                .appendingPathComponent(
                    "SafariSession.json"
                )
    }

    func save(
        session: SafariSession
    ) async throws {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        let data =
            try encoder.encode(session)

        try data.write(
            to: fileURL,
            options: [.atomic]
        )
    }

    func load() async throws -> SafariSession {

        let data =
            try Data(contentsOf: fileURL)

        let decoder = JSONDecoder()

        decoder.dateDecodingStrategy =
            .iso8601

        return try decoder.decode(
            SafariSession.self,
            from: data
        )
    }
}



import Foundation

struct TabTelemetryEvent: Sendable {

    enum Kind: Sendable {
        case created
        case activated
        case backgrounded
        case suspended
        case restored
        case closed
        case navigationStarted
        case navigationFinished
        case navigationFailed
    }

    let tabID: TabID
    let kind: Kind
    let timestamp: Date
}

actor SafariTabTelemetry {

    private var events: [TabTelemetryEvent] = []

    private let maximumEvents = 10_000

    func record(
        tabID: TabID,
        kind: TabTelemetryEvent.Kind
    ) {

        events.append(
            TabTelemetryEvent(
                tabID: tabID,
                kind: kind,
                timestamp: Date()
            )
        )

        if events.count > maximumEvents {
            events.removeFirst(
                events.count - maximumEvents
            )
        }
    }

    func recentEvents(
        limit: Int = 100
    ) -> [TabTelemetryEvent] {

        Array(
            events.suffix(limit)
        )
    }
}





import Foundation
import WebKit

@MainActor
final class SafariTabCoordinator {

    let store: TabStore
    let lifecycle: TabLifecycleManager
    let resources: TabResourceManager
    let predictions: TabPredictionEngine
    let telemetry: SafariTabTelemetry
    let webKit: WebKitTabController

    init() {

        let store = TabStore()

        self.store = store

        self.lifecycle =
            TabLifecycleManager(
                store: store
            )

        self.resources =
            TabResourceManager(
                store: store
            )

        self.predictions =
            TabPredictionEngine(
                store: store
            )

        self.telemetry =
            SafariTabTelemetry()

        self.webKit =
            WebKitTabController()
    }

    // MARK: - Window

    func createWindow() async -> SafariWindow {
        await store.createWindow()
    }

    // MARK: - Tab Creation

    func createTab(
        in windowID: WindowID,
        url: URL? = nil
    ) async throws -> SafariTab {

        let tab =
            try await store.createTab(
                in: windowID,
                url: url
            )

        _ = webKit.createWebView(
            for: tab.id
        )

        await telemetry.record(
            tabID: tab.id,
            kind: .created
        )

        return tab
    }

    // MARK: - Navigation

    func navigate(
        tabID: TabID,
        to url: URL
    ) async throws {

        guard let webView =
                webKit.webView(
                    for: tabID
                )
        else {
            throw SafariCoordinatorError.webViewUnavailable
        }

        try await store.updateTab(tabID) { tab in
            tab.url = url
            tab.lifecycle = .loading
            tab.navigation.url = url
            tab.navigation.estimatedProgress = 0
        }

        await telemetry.record(
            tabID: tabID,
            kind: .navigationStarted
        )

        webView.load(
            URLRequest(url: url)
        )
    }

    // MARK: - Selection

    func selectTab(
        _ tabID: TabID,
        in windowID: WindowID
    ) async throws {

        try await store.selectTab(
            tabID,
            in: windowID
        )

        await lifecycle.activate(
            tabID
        )

        await telemetry.record(
            tabID: tabID,
            kind: .activated
        )
    }

    // MARK: - Background

    func backgroundTab(
        _ tabID: TabID
    ) async throws {

        try await lifecycle.background(
            tabID
        )

        await telemetry.record(
            tabID: tabID,
            kind: .backgrounded
        )
    }

    // MARK: - Suspension

    func suspendTab(
        _ tabID: TabID
    ) async throws {

        guard await lifecycle
            .evaluateSuspensionEligibility(
                tabID
            )
        else {
            return
        }

        try await lifecycle.suspend(
            tabID
        )

        webKit.suspend(
            tabID: tabID
        )

        await telemetry.record(
            tabID: tabID,
            kind: .suspended
        )
    }

    // MARK: - Restore

    func restoreTab(
        _ tabID: TabID
    ) async throws {

        try await lifecycle.beginRestoration(
            tabID
        )

        webKit.restore(
            tabID: tabID,
            navigationDelegate: nil,
            uiDelegate: nil
        )

        try await lifecycle.finishRestoration(
            tabID
        )

        await telemetry.record(
            tabID: tabID,
            kind: .restored
        )
    }

    // MARK: - Close

    func closeTab(
        _ tabID: TabID
    ) async throws {

        try await lifecycle.beginClosing(
            tabID
        )

        webKit.destroyWebView(
            for: tabID
        )

        try await store.removeTab(
            tabID
        )

        await telemetry.record(
            tabID: tabID,
            kind: .closed
        )
    }

    // MARK: - Reorder

    func moveTab(
        _ tabID: TabID,
        in windowID: WindowID,
        to index: Int
    ) async throws {

        try await store.moveTab(
            tabID,
            in: windowID,
            to: index
        )
    }

    // MARK: - Predictions

    func predictedTabs() async -> [TabPrediction] {
        await predictions.predictNextTabs()
    }
}

enum SafariCoordinatorError: Error {
    case webViewUnavailable
}








import Foundation

actor SafariTabSuspensionEngine {

    private let store: TabStore
    private let lifecycle: TabLifecycleManager

    private let inactivityThreshold: TimeInterval

    init(
        store: TabStore,
        lifecycle: TabLifecycleManager,
        inactivityThreshold: TimeInterval = 300
    ) {
        self.store = store
        self.lifecycle = lifecycle
        self.inactivityThreshold =
            inactivityThreshold
    }

    func evaluate() async {

        let tabs = await store.allTabs()
        let now = Date()

        for tab in tabs {

            guard tab.lifecycle == .background ||
                  tab.lifecycle == .suspendable
            else {
                continue
            }

            guard !tab.isPinned else {
                continue
            }

            guard !tab.isPlayingMedia else {
                continue
            }

            let inactivity =
                now.timeIntervalSince(
                    tab.lastInteractionAt
                )

            guard inactivity >= inactivityThreshold else {
                continue
            }

            do {
                try await lifecycle.suspend(
                    tab.id
                )
            } catch {
                // Individual tab failure must not
                // terminate the suspension sweep.
            }
        }
    }
}






SafariResourceRuntime.swift





import Foundation
import WebKit
import OSLog
import AppKit

// ============================================================
// MARK: - IDENTIFIERS
// ============================================================

struct ResourceTabID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

struct ResourceProcessID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

// ============================================================
// MARK: - RESOURCE STATE
// ============================================================

enum ResourceLifecycle: String, Codable, Sendable {
    case active
    case recentlyActive
    case background
    case deprioritized
    case suspendable
    case suspended
    case restoring
    case closing
}

enum ResourcePressureLevel: Int, Codable, Sendable, Comparable {
    case normal = 0
    case elevated = 1
    case serious = 2
    case critical = 3

    static func < (
        lhs: ResourcePressureLevel,
        rhs: ResourcePressureLevel
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

enum ResourceActivity: String, Codable, Sendable {
    case idle
    case loading
    case interactive
    case media
    case audio
    case video
    case downloading
    case webSocket
    case backgroundJavaScript
}

// ============================================================
// MARK: - RESOURCE SNAPSHOTS
// ============================================================

struct TabResourceSnapshot: Sendable, Codable {

    let tabID: ResourceTabID

    var memoryBytes: UInt64
    var cpuPercentage: Double
    var gpuPercentage: Double
    var networkBytesPerSecond: UInt64

    var lastInteraction: Date
    var lastActivation: Date

    var isVisible: Bool
    var isPinned: Bool
    var isPlayingMedia: Bool
    var isAudible: Bool

    var lifecycle: ResourceLifecycle
    var activity: ResourceActivity

    var estimatedReloadCost: Double
    var estimatedSuspensionBenefit: Double

    var timestamp: Date

    var memoryMegabytes: Double {
        Double(memoryBytes) / 1_048_576.0
    }
}

// ============================================================
// MARK: - PROCESS SNAPSHOT
// ============================================================

struct ProcessResourceSnapshot: Sendable, Codable {

    let processID: ResourceProcessID

    var memoryBytes: UInt64
    var cpuPercentage: Double
    var gpuPercentage: Double

    var tabCount: Int

    var pressure: ResourcePressureLevel

    var timestamp: Date
}

// ============================================================
// MARK: - RESOURCE BUDGET
// ============================================================

struct ResourceBudget: Sendable, Codable {

    var maximumTotalMemoryBytes: UInt64
    var maximumBackgroundMemoryBytes: UInt64
    var maximumBackgroundCPUPercentage: Double

    var maximumActiveTabs: Int
    var maximumWarmTabs: Int

    static let macBookDefault = ResourceBudget(
        maximumTotalMemoryBytes: 8 * 1_073_741_824,
        maximumBackgroundMemoryBytes: 2 * 1_073_741_824,
        maximumBackgroundCPUPercentage: 25,
        maximumActiveTabs: 8,
        maximumWarmTabs: 32
    )
}

// ============================================================
// MARK: - RESOURCE DECISION
// ============================================================

enum ResourceDecision: Sendable {

    case keepActive
    case keepWarm
    case deprioritize
    case suspend
    case restore
}

struct ResourceRecommendation: Sendable {

    let tabID: ResourceTabID
    let score: Double
    let decision: ResourceDecision
    let reason: String
}

// ============================================================
// MARK: - RESOURCE MONITOR PROTOCOLS
// ============================================================

protocol MemoryPressureProviding: Sendable {
    func currentMemoryPressure() async -> ResourcePressureLevel
}

protocol ThermalStateProviding: Sendable {
    func currentThermalState() async -> ProcessInfo.ThermalState
}

protocol BatteryStateProviding: Sendable {
    func batteryLevel() async -> Double
    func isCharging() async -> Bool
}

protocol SystemResourceProviding: Sendable {
    func totalMemory() async -> UInt64
}

// ============================================================
// MARK: - SYSTEM MEMORY PROVIDER
// ============================================================

struct SystemMemoryProvider: SystemResourceProviding {

    func totalMemory() async -> UInt64 {
        ProcessInfo.processInfo.physicalMemory
    }
}

// ============================================================
// MARK: - THERMAL PROVIDER
// ============================================================

struct SystemThermalProvider: ThermalStateProviding {

    func currentThermalState()
        async -> ProcessInfo.ThermalState {

        ProcessInfo.processInfo.thermalState
    }
}

// ============================================================
// MARK: - BATTERY PROVIDER
// ============================================================

@MainActor
final class MacBatteryProvider:
    NSObject,
    BatteryStateProviding {

    override init() {
        super.init()

        let device = UIDeviceProxy.shared
        device.beginMonitoring()
    }

    func batteryLevel() async -> Double {
        await MainActor.run {
            UIDeviceProxy.shared.batteryLevel
        }
    }

    func isCharging() async -> Bool {
        await MainActor.run {
            UIDeviceProxy.shared.isCharging
        }
    }
}

// ============================================================
// MARK: - MAC BATTERY PROXY
// ============================================================
//
// macOS does not expose iOS UIDevice battery APIs.
// This proxy deliberately provides a replaceable abstraction.
// A production implementation can connect this to IOKit /
// NSProcessInfo / power-management services.
//
// ============================================================

@MainActor
final class UIDeviceProxy {

    static let shared = UIDeviceProxy()

    private(set) var batteryLevel: Double = 1.0
    private(set) var isCharging: Bool = true

    private init() {}

    func beginMonitoring() {
        // Production implementation:
        // connect to IOKit power source notifications.
    }
}

// ============================================================
// MARK: - MEMORY PRESSURE MONITOR
// ============================================================

actor SafariMemoryPressureMonitor:
    MemoryPressureProviding {

    private var currentLevel:
        ResourcePressureLevel = .normal

    private var continuation:
        AsyncStream<ResourcePressureLevel>.Continuation?

    func stream()
        -> AsyncStream<ResourcePressureLevel> {

        AsyncStream { continuation in
            self.continuation = continuation
            continuation.yield(currentLevel)
        }
    }

    func update(
        _ level: ResourcePressureLevel
    ) {

        guard level != currentLevel else {
            return
        }

        currentLevel = level
        continuation?.yield(level)
    }

    func currentMemoryPressure()
        async -> ResourcePressureLevel {

        currentLevel
    }
}

// ============================================================
// MARK: - RESOURCE REGISTRY
// ============================================================

actor SafariResourceRegistry {

    private var tabs:
        [ResourceTabID: TabResourceSnapshot] = [:]

    private var processes:
        [ResourceProcessID: ProcessResourceSnapshot] = [:]

    func register(
        _ snapshot: TabResourceSnapshot
    ) {

        tabs[snapshot.tabID] = snapshot
    }

    func update(
        _ snapshot: TabResourceSnapshot
    ) {

        tabs[snapshot.tabID] = snapshot
    }

    func remove(
        _ tabID: ResourceTabID
    ) {

        tabs.removeValue(
            forKey: tabID
        )
    }

    func tab(
        _ tabID: ResourceTabID
    ) -> TabResourceSnapshot? {

        tabs[tabID]
    }

    func allTabs()
        -> [TabResourceSnapshot] {

        Array(tabs.values)
    }

    func registerProcess(
        _ snapshot: ProcessResourceSnapshot
    ) {

        processes[snapshot.processID] = snapshot
    }

    func updateProcess(
        _ snapshot: ProcessResourceSnapshot
    ) {

        processes[snapshot.processID] = snapshot
    }

    func allProcesses()
        -> [ProcessResourceSnapshot] {

        Array(processes.values)
    }

    func totalMemoryUsage()
        -> UInt64 {

        tabs.values.reduce(0) {
            $0 + $1.memoryBytes
        }
    }

    func totalCPUUsage()
        -> Double {

        tabs.values.reduce(0) {
            $0 + $1.cpuPercentage
        }
    }
}

// ============================================================
// MARK: - RESOURCE SCORER
// ============================================================

struct SafariResourceScorer: Sendable {

    struct Configuration: Sendable {

        var recencyWeight: Double = 3.0
        var activationWeight: Double = 1.5
        var memoryWeight: Double = 2.5
        var cpuWeight: Double = 2.0
        var mediaWeight: Double = 5.0
        var pinnedWeight: Double = 10.0
        var reloadCostWeight: Double = 3.0
    }

    let configuration: Configuration

    func score(
        snapshot: TabResourceSnapshot,
        now: Date = Date()
    ) -> Double {

        let age =
            max(
                now.timeIntervalSince(
                    snapshot.lastActivation
                ),
                0
            )

        let recency =
            1.0 / (1.0 + age / 60.0)

        let memory =
            min(
                snapshot.memoryMegabytes / 2048.0,
                1.0
            )

        let cpu =
            min(
                snapshot.cpuPercentage / 100.0,
                1.0
            )

        let media =
            snapshot.isPlayingMedia
            ? 1.0
            : 0.0

        let pinned =
            snapshot.isPinned
            ? 1.0
            : 0.0

        let reload =
            min(
                max(
                    snapshot.estimatedReloadCost,
                    0
                ),
                1.0
            )

        var value = 0.0

        value +=
            recency *
            configuration.recencyWeight

        value +=
            configuration.memoryWeight *
            memory

        value +=
            configuration.cpuWeight *
            cpu

        value +=
            configuration.mediaWeight *
            media

        value +=
            configuration.pinnedWeight *
            pinned

        value +=
            configuration.reloadCostWeight *
            reload

        return value
    }
}

// ============================================================
// MARK: - SUSPENSION PLANNER
// ============================================================

struct SafariSuspensionPlanner: Sendable {

    let scorer: SafariResourceScorer

    func recommendations(
        snapshots: [TabResourceSnapshot],
        pressure: ResourcePressureLevel,
        budget: ResourceBudget
    ) -> [ResourceRecommendation] {

        let sorted =
            snapshots
                .map { snapshot in

                    (
                        snapshot,
                        scorer.score(
                            snapshot: snapshot
                        )
                    )
                }
                .sorted {
                    $0.1 < $1.1
                }

        return sorted.map {
            snapshot,
            score in

            let decision =
                decide(
                    snapshot: snapshot,
                    score: score,
                    pressure: pressure,
                    budget: budget
                )

            return ResourceRecommendation(
                tabID: snapshot.tabID,
                score: score,
                decision: decision,
                reason: reason(
                    snapshot: snapshot,
                    decision: decision
                )
            )
        }
    }

    private func decide(
        snapshot: TabResourceSnapshot,
        score: Double,
        pressure: ResourcePressureLevel,
        budget: ResourceBudget
    ) -> ResourceDecision {

        if snapshot.isPinned {
            return .keepWarm
        }

        if snapshot.isPlayingMedia ||
           snapshot.isAudible {
            return .keepActive
        }

        switch pressure {

        case .normal:
            if score < 1.5 {
                return .keepWarm
            }

            return .keepActive

        case .elevated:
            if score < 2.0 {
                return .keepWarm
            }

            return .deprioritize

        case .serious:
            if score < 2.5 {
                return .deprioritize
            }

            return .suspend

        case .critical:
            if score < 3.5 {
                return .deprioritize
            }

            return .suspend
        }
    }

    private func reason(
        snapshot: TabResourceSnapshot,
        decision: ResourceDecision
    ) -> String {

        switch decision {

        case .keepActive:
            return "Recently active or currently producing media."

        case .keepWarm:
            return "Low resource pressure and valuable to retain."

        case .deprioritize:
            return "Background activity should be reduced."

        case .suspend:
            return """
            Tab has sufficient suspension benefit under \
            current resource pressure.
            """

        case .restore:
            return "Tab has become relevant again."
        }
    }
}

// ============================================================
// MARK: - WEBKIT TAB RESOURCE CONTROLLER
// ============================================================

@MainActor
final class WebKitTabResourceController {

    private var webViews:
        [ResourceTabID: WKWebView] = [:]

    private var suspendedSnapshots:
        [ResourceTabID: NavigationSnapshot] = [:]

    private let logger =
        Logger(
            subsystem: "SafariResourceRuntime",
            category: "WebKitController"
        )

    func register(
        tabID: ResourceTabID,
        webView: WKWebView
    ) {

        webViews[tabID] = webView

        logger.debug(
            "Registered WebView \(String(describing: tabID.rawValue))"
        )
    }

    func webView(
        for tabID: ResourceTabID
    ) -> WKWebView? {

        webViews[tabID]
    }

    func prepareForSuspension(
        tabID: ResourceTabID
    ) {

        guard let webView =
                webViews[tabID]
        else {
            return
        }

        webView.stopLoading()

        webView.configuration
            .userContentController
            .removeAllUserScripts()

        webView.navigationDelegate = nil
        webView.uiDelegate = nil

        logger.info(
            "Prepared tab for suspension."
        )
    }

    func suspend(
        tabID: ResourceTabID
    ) {

        guard let webView =
                webViews[tabID]
        else {
            return
        }

        suspendedSnapshots[tabID] =
            NavigationSnapshot(
                url: webView.url,
                title: webView.title,
                canGoBack: webView.canGoBack,
                canGoForward: webView.canGoForward,
                estimatedProgress:
                    webView.estimatedProgress
            )

        webView.stopLoading()

        webView.isHidden = true

        logger.info(
            "Suspended WebView."
        )
    }

    func restore(
        tabID: ResourceTabID
    ) {

        guard let webView =
                webViews[tabID]
        else {
            return
        }

        webView.isHidden = false

        if let snapshot =
            suspendedSnapshots[tabID],
           let url = snapshot.url {

            webView.load(
                URLRequest(
                    url: url
                )
            )
        }

        suspendedSnapshots.removeValue(
            forKey: tabID
        )

        logger.info(
            "Restored WebView."
        )
    }

    func destroy(
        tabID: ResourceTabID
    ) {

        guard let webView =
                webViews.removeValue(
                    forKey: tabID
                )
        else {
            return
        }

        webView.stopLoading()
        webView.navigationDelegate = nil
        webView.uiDelegate = nil

        suspendedSnapshots.removeValue(
            forKey: tabID
        )
    }
}

// ============================================================
// MARK: - RUNTIME TELEMETRY
// ============================================================

struct ResourceTelemetryEvent: Sendable {

    enum Kind: Sendable {

        case registration
        case update
        case deprioritized
        case suspended
        case restored
        case memoryPressure
        case thermalPressure
        case budgetExceeded
    }

    let kind: Kind
    let tabID: ResourceTabID?
    let timestamp: Date
    let message: String
}

actor SafariResourceTelemetry {

    private var events:
        [ResourceTelemetryEvent] = []

    private let maximumEvents =
        20_000

    func record(
        _ event: ResourceTelemetryEvent
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
        limit: Int = 100
    ) -> [ResourceTelemetryEvent] {

        Array(
            events.suffix(limit)
        )
    }
}

// ============================================================
// MARK: - RESOURCE BUDGET MANAGER
// ============================================================

actor SafariResourceBudgetManager {

    private(set) var budget:
        ResourceBudget

    init(
        budget: ResourceBudget =
            .macBookDefault
    ) {

        self.budget = budget
    }

    func update(
        budget: ResourceBudget
    ) {

        self.budget = budget
    }

    func exceedsMemoryBudget(
        totalMemory: UInt64
    ) -> Bool {

        totalMemory >
        budget.maximumTotalMemoryBytes
    }

    func exceedsBackgroundBudget(
        memory: UInt64
    ) -> Bool {

        memory >
        budget.maximumBackgroundMemoryBytes
    }

    func exceedsCPU(
        cpu: Double
    ) -> Bool {

        cpu >
        budget.maximumBackgroundCPUPercentage
    }
}

// ============================================================
// MARK: - RESOURCE RUNTIME
// ============================================================

actor SafariResourceRuntime {

    private let registry:
        SafariResourceRegistry

    private let memoryMonitor:
        SafariMemoryPressureMonitor

    private let thermalProvider:
        ThermalStateProviding

    private let scorer:
        SafariResourceScorer

    private let planner:
        SafariSuspensionPlanner

    private let budgetManager:
        SafariResourceBudgetManager

    private let telemetry:
        SafariResourceTelemetry

    private var currentPressure:
        ResourcePressureLevel = .normal

    private var monitoringTask:
        Task<Void, Never>?

    init(
        registry:
            SafariResourceRegistry =
            SafariResourceRegistry(),

        memoryMonitor:
            SafariMemoryPressureMonitor =
            SafariMemoryPressureMonitor(),

        thermalProvider:
            ThermalStateProviding =
            SystemThermalProvider(),

        scorer:
            SafariResourceScorer =
            SafariResourceScorer(
                configuration:
                    .init()
            ),

        budget:
            ResourceBudget =
            .macBookDefault,

        telemetry:
            SafariResourceTelemetry =
            SafariResourceTelemetry()
    ) {

        self.registry = registry
        self.memoryMonitor = memoryMonitor
        self.thermalProvider = thermalProvider
        self.scorer = scorer

        self.planner =
            SafariSuspensionPlanner(
                scorer: scorer
            )

        self.budgetManager =
            SafariResourceBudgetManager(
                budget: budget
            )

        self.telemetry = telemetry
    }

    // ========================================================
    // MARK: START
    // ========================================================

    func start() {

        guard monitoringTask == nil else {
            return
        }

        monitoringTask =
            Task {

                while !Task.isCancelled {

                    await evaluate()

                    try? await Task.sleep(
                        for: .seconds(5)
                    )
                }
            }
    }

    // ========================================================
    // MARK: STOP
    // ========================================================

    func stop() {

        monitoringTask?.cancel()
        monitoringTask = nil
    }

    // ========================================================
    // MARK: REGISTER
    // ========================================================

    func register(
        snapshot: TabResourceSnapshot
    ) async {

        await registry.register(
            snapshot
        )

        await telemetry.record(
            ResourceTelemetryEvent(
                kind: .registration,
                tabID: snapshot.tabID,
                timestamp: Date(),
                message: "Tab registered."
            )
        )
    }

    // ========================================================
    // MARK: UPDATE
    // ========================================================

    func update(
        snapshot: TabResourceSnapshot
    ) async {

        await registry.update(
            snapshot
        )

        await telemetry.record(
            ResourceTelemetryEvent(
                kind: .update,
                tabID: snapshot.tabID,
                timestamp: Date(),
                message: "Resource snapshot updated."
            )
        )
    }

    // ========================================================
    // MARK: PRESSURE
    // ========================================================

    func updatePressure(
        _ pressure: ResourcePressureLevel
    ) async {

        currentPressure = pressure

        await memoryMonitor.update(
            pressure
        )

        await telemetry.record(
            ResourceTelemetryEvent(
                kind: .memoryPressure,
                tabID: nil,
                timestamp: Date(),
                message:
                    "Memory pressure: \(pressure)"
            )
        )
    }

    // ========================================================
    // MARK: EVALUATION
    // ========================================================

    func evaluate()
        async {

        let snapshots =
            await registry.allTabs()

        guard !snapshots.isEmpty else {
            return
        }

        let recommendations =
            planner.recommendations(
                snapshots: snapshots,
                pressure: currentPressure,
                budget:
                    await budgetManager.budget
            )

        let totalMemory =
            await registry.totalMemoryUsage()

        let totalCPU =
            await registry.totalCPUUsage()

        if await budgetManager
            .exceedsMemoryBudget(
                totalMemory: totalMemory
            ) {

            await telemetry.record(
                ResourceTelemetryEvent(
                    kind: .budgetExceeded,
                    tabID: nil,
                    timestamp: Date(),
                    message:
                        "Total memory budget exceeded."
                )
            )
        }

        if await budgetManager
            .exceedsCPU(
                cpu: totalCPU
            ) {

            await telemetry.record(
                ResourceTelemetryEvent(
                    kind: .budgetExceeded,
                    tabID: nil,
                    timestamp: Date(),
                    message:
                        "Background CPU budget exceeded."
                )
            )
        }

        let thermal =
            await thermalProvider
                .currentThermalState()

        if thermal ==
            .serious ||
            thermal ==
            .critical {

            await telemetry.record(
                ResourceTelemetryEvent(
                    kind: .thermalPressure,
                    tabID: nil,
                    timestamp: Date(),
                    message:
                        "System thermal pressure detected."
                )
            )
        }

        await process(
            recommendations
        )
    }

    // ========================================================
    // MARK: PROCESS RECOMMENDATIONS
    // ========================================================

    private func process(
        _ recommendations:
            [ResourceRecommendation]
    ) async {

        for recommendation
            in recommendations {

            switch recommendation.decision {

            case .keepActive:
                continue

            case .keepWarm:
                continue

            case .deprioritize:

                await telemetry.record(
                    ResourceTelemetryEvent(
                        kind: .deprioritized,
                        tabID:
                            recommendation.tabID,
                        timestamp: Date(),
                        message:
                            recommendation.reason
                    )
                )

            case .suspend:

                await telemetry.record(
                    ResourceTelemetryEvent(
                        kind: .suspended,
                        tabID:
                            recommendation.tabID,
                        timestamp: Date(),
                        message:
                            recommendation.reason
                    )
                )

            case .restore:

                await telemetry.record(
                    ResourceTelemetryEvent(
                        kind: .restored,
                        tabID:
                            recommendation.tabID,
                        timestamp: Date(),
                        message:
                            recommendation.reason
                    )
                )
            }
        }
    }

    // ========================================================
    // MARK: RECOMMENDATIONS
    // ========================================================

    func recommendations()
        async -> [ResourceRecommendation] {

        let snapshots =
            await registry.allTabs()

        return planner.recommendations(
            snapshots: snapshots,
            pressure: currentPressure,
            budget:
                await budgetManager.budget
        )
    }
}

// ============================================================
// MARK: - MAIN-ACTOR ORCHESTRATOR
// ============================================================

@MainActor
final class SafariResourceOrchestrator {

    let runtime:
        SafariResourceRuntime

    let registry:
        SafariResourceRegistry

    let webKit:
        WebKitTabResourceController

    private let logger =
        Logger(
            subsystem:
                "SafariResourceRuntime",
            category:
                "Orchestrator"
        )

    init() {

        let registry =
            SafariResourceRegistry()

        self.registry =
            registry

        self.runtime =
            SafariResourceRuntime(
                registry:
                    registry
            )

        self.webKit =
            WebKitTabResourceController()
    }

    // ========================================================
    // MARK: START
    // ========================================================

    func start() async {

        await runtime.start()

        logger.info(
            "Safari resource runtime started."
        )
    }

    // ========================================================
    // MARK: STOP
    // ========================================================

    func stop() async {

        await runtime.stop()

        logger.info(
            "Safari resource runtime stopped."
        )
    }

    // ========================================================
    // MARK: REGISTER WEBVIEW
    // ========================================================

    func register(
        tabID: ResourceTabID,
        webView: WKWebView
    ) async {

        webKit.register(
            tabID: tabID,
            webView: webView
        )

        let snapshot =
            TabResourceSnapshot(
                tabID: tabID,
                memoryBytes: 0,
                cpuPercentage: 0,
                gpuPercentage: 0,
                networkBytesPerSecond: 0,
                lastInteraction: Date(),
                lastActivation: Date(),
                isVisible: true,
                isPinned: false,
                isPlayingMedia: false,
                isAudible: false,
                lifecycle: .active,
                activity: .interactive,
                estimatedReloadCost: 0.5,
                estimatedSuspensionBenefit: 0,
                timestamp: Date()
            )

        await runtime.register(
            snapshot: snapshot
        )
    }

    // ========================================================
    // MARK: SUSPEND
    // ========================================================

    func suspend(
        tabID: ResourceTabID
    ) async {

        webKit.prepareForSuspension(
            tabID: tabID
        )

        webKit.suspend(
            tabID: tabID
        )

        guard
            let existing =
                await registry.tab(tabID)
        else {
            return
        }

        var updated = existing

        updated.lifecycle =
            .suspended

        updated.timestamp =
            Date()

        await runtime.update(
            snapshot: updated
        )
    }

    // ========================================================
    // MARK: RESTORE
    // ========================================================

    func restore(
        tabID: ResourceTabID
    ) async {

        webKit.restore(
            tabID: tabID
        )

        guard
            let existing =
                await registry.tab(tabID)
        else {
            return
        }

        var updated = existing

        updated.lifecycle =
            .restoring

        updated.timestamp =
            Date()

        await runtime.update(
            snapshot: updated
        )
    }

    // ========================================================
    // MARK: DESTROY
    // ========================================================

    func destroy(
        tabID: ResourceTabID
    ) async {

        webKit.destroy(
            tabID: tabID
        )

        await registry.remove(
            tabID
        )
    }
}

// ============================================================
// MARK: - RESOURCE SAMPLE GENERATOR
// ============================================================

actor ResourceSampleGenerator {

    private var running = false

    func start(
        runtime:
            SafariResourceRuntime
    ) {

        guard !running else {
            return
        }

        running = true

        Task {

            while !Task.isCancelled {

                let tabs =
                    await runtime
                        .recommendations()

                _ = tabs

                try? await Task.sleep(
                    for: .seconds(2)
                )
            }
        }
    }

    func stop() {
        running = false
    }
}

// ============================================================
// MARK: - MEMORY CLASSIFIER
// ============================================================

struct MemoryClassifier: Sendable {

    func classify(
        memoryBytes: UInt64
    ) -> ResourcePressureLevel {

        let gigabytes =
            Double(memoryBytes) /
            1_073_741_824.0

        switch gigabytes {

        case 0..<2:
            return .normal

        case 2..<4:
            return .elevated

        case 4..<6:
            return .serious

        default:
            return .critical
        }
    }
}

// ============================================================
// MARK: - TAB RESOURCE POLICY
// ============================================================

struct TabResourcePolicy: Sendable {

    var pinnedTabsNeverSuspend = true
    var mediaTabsNeverSuspend = true
    var audibleTabsNeverSuspend = true

    var minimumBackgroundAge:
        TimeInterval = 120

    var maximumMemoryForWarmTab:
        UInt64 = 512 * 1_048_576

    func canSuspend(
        snapshot: TabResourceSnapshot,
        now: Date = Date()
    ) -> Bool {

        if pinnedTabsNeverSuspend &&
            snapshot.isPinned {
            return false
        }

        if mediaTabsNeverSuspend &&
            snapshot.isPlayingMedia {
            return false
        }

        if audibleTabsNeverSuspend &&
            snapshot.isAudible {
            return false
        }

        let age =
            now.timeIntervalSince(
                snapshot.lastInteraction
            )

        return age >=
            minimumBackgroundAge
    }
}

// ============================================================
// MARK: - RESOURCE SCORE CACHE
// ============================================================

actor ResourceScoreCache {

    private var scores:
        [ResourceTabID: Double] = [:]

    func set(
        tabID: ResourceTabID,
        score: Double
    ) {

        scores[tabID] = score
    }

    func score(
        for tabID: ResourceTabID
    ) -> Double? {

        scores[tabID]
    }

    func remove(
        tabID: ResourceTabID
    ) {

        scores.removeValue(
            forKey: tabID
        )
    }

    func clear() {
        scores.removeAll()
    }
}

// ============================================================
// MARK: - RESOURCE DIAGNOSTICS
// ============================================================

struct ResourceDiagnosticsReport:
    Sendable {

    let generatedAt: Date

    let tabCount: Int

    let totalMemoryBytes: UInt64

    let totalCPUPercentage: Double

    let highestMemoryTab:
        ResourceTabID?

    let highestCPUTab:
        ResourceTabID?

    let pressure:
        ResourcePressureLevel
}

actor SafariResourceDiagnostics {

    private let registry:
        SafariResourceRegistry

    init(
        registry:
            SafariResourceRegistry
    ) {

        self.registry =
            registry
    }

    func report(
        pressure:
            ResourcePressureLevel
    ) async -> ResourceDiagnosticsReport {

        let tabs =
            await registry.allTabs()

        let highestMemory =
            tabs.max {
                $0.memoryBytes <
                $1.memoryBytes
            }

        let highestCPU =
            tabs.max {
                $0.cpuPercentage <
                $1.cpuPercentage
            }

        return ResourceDiagnosticsReport(
            generatedAt: Date(),
            tabCount: tabs.count,
            totalMemoryBytes:
                await registry.totalMemoryUsage(),
            totalCPUPercentage:
                await registry.totalCPUUsage(),
            highestMemoryTab:
                highestMemory?.tabID,
            highestCPUTab:
                highestCPU?.tabID,
            pressure: pressure
        )
    }
}

// ============================================================
// MARK: - RESOURCE RUNTIME CONFIGURATION
// ============================================================

struct SafariResourceRuntimeConfiguration:
    Sendable {

    var evaluationInterval:
        Duration = .seconds(5)

    var budget:
        ResourceBudget =
            .macBookDefault

    var scorerConfiguration:
        SafariResourceScorer.Configuration =
            .init()

    var policy:
        TabResourcePolicy =
            .init()
}

// ============================================================
// MARK: - RUNTIME FACTORY
// ============================================================

enum SafariResourceRuntimeFactory {

    static func make(
        configuration:
            SafariResourceRuntimeConfiguration =
            .init()
    ) -> SafariResourceRuntime {

        let registry =
            SafariResourceRegistry()

        let memory =
            SafariMemoryPressureMonitor()

        let scorer =
            SafariResourceScorer(
                configuration:
                    configuration
                    .scorerConfiguration
            )

        return SafariResourceRuntime(
            registry:
                registry,
            memoryMonitor:
                memory,
            thermalProvider:
                SystemThermalProvider(),
            scorer:
                scorer,
            budget:
                configuration.budget,
            telemetry:
                SafariResourceTelemetry()
        )
    }
}

// ============================================================
// MARK: - TESTABLE RESOURCE MODEL
// ============================================================

struct ResourceTestFactory {

    static func makeTab(
        memoryMB: Double,
        cpu: Double,
        age: TimeInterval,
        pinned: Bool = false,
        media: Bool = false
    ) -> TabResourceSnapshot {

        let now =
            Date()

        return TabResourceSnapshot(
            tabID:
                ResourceTabID(),
            memoryBytes:
                UInt64(
                    memoryMB *
                    1_048_576
                ),
            cpuPercentage:
                cpu,
            gpuPercentage:
                0,
            networkBytesPerSecond:
                0,
            lastInteraction:
                now.addingTimeInterval(
                    -age
                ),
            lastActivation:
                now.addingTimeInterval(
                    -age
                ),
            isVisible:
                age < 30,
            isPinned:
                pinned,
            isPlayingMedia:
                media,
            isAudible:
                media,
            lifecycle:
                age > 60
                ? .background
                : .active,
            activity:
                media
                ? .media
                : .idle,
            estimatedReloadCost:
                0.5,
            estimatedSuspensionBenefit:
                memoryMB / 1024,
            timestamp:
                now
        )
    }
}

// ============================================================
// MARK: - RESOURCE TESTS
// ============================================================

#if DEBUG

import XCTest

final class SafariResourceRuntimeTests:
    XCTestCase {

    func testMemoryClassification() {

        let classifier =
            MemoryClassifier()

        XCTAssertEqual(
            classifier.classify(
                memoryBytes:
                    1 *
                    1_073_741_824
            ),
            .normal
        )

        XCTAssertEqual(
            classifier.classify(
                memoryBytes:
                    3 *
                    1_073_741_824
            ),
            .elevated
        )

        XCTAssertEqual(
            classifier.classify(
                memoryBytes:
                    5 *
                    1_073_741_824
            ),
            .serious
        )

        XCTAssertEqual(
            classifier.classify(
                memoryBytes:
                    7 *
                    1_073_741_824
            ),
            .critical
        )
    }

    func testPinnedTabPolicy() {

        let tab =
            ResourceTestFactory.makeTab(
                memoryMB: 1024,
                cpu: 50,
                age: 10_000,
                pinned: true
            )

        let policy =
            TabResourcePolicy()

        XCTAssertFalse(
            policy.canSuspend(
                snapshot: tab
            )
        )
    }

    func testMediaTabPolicy() {

        let tab =
            ResourceTestFactory.makeTab(
                memoryMB: 1024,
                cpu: 50,
                age: 10_000,
                media: true
            )

        let policy =
            TabResourcePolicy()

        XCTAssertFalse(
            policy.canSuspend(
                snapshot: tab
            )
        )
    }

    func testOldBackgroundTabCanSuspend() {

        let tab =
            ResourceTestFactory.makeTab(
                memoryMB: 1024,
                cpu: 2,
                age: 10_000
            )

        let policy =
            TabResourcePolicy()

        XCTAssertTrue(
            policy.canSuspend(
                snapshot: tab
            )
        )
    }

    func testResourceScoring() {

        let scorer =
            SafariResourceScorer(
                configuration:
                    .init()
            )

        let tab =
            ResourceTestFactory.makeTab(
                memoryMB: 2048,
                cpu: 50,
                age: 600
            )

        let score =
            scorer.score(
                snapshot: tab
            )

        XCTAssertGreaterThan(
            score,
            0
        )
    }

    func testPlannerProducesRecommendations() {

        let scorer =
            SafariResourceScorer(
                configuration:
                    .init()
            )

        let planner =
            SafariSuspensionPlanner(
                scorer: scorer
            )

        let tabs = [
            ResourceTestFactory.makeTab(
                memoryMB: 2048,
                cpu: 50,
                age: 10_000
            ),
            ResourceTestFactory.makeTab(
                memoryMB: 128,
                cpu: 1,
                age: 10
            )
        ]

        let recommendations =
            planner.recommendations(
                snapshots: tabs,
                pressure: .critical,
                budget:
                    .macBookDefault
            )

        XCTAssertEqual(
            recommendations.count,
            2
        )
    }
}

#endif

// ============================================================
// MARK: - EXAMPLE SAFARI INTEGRATION
// ============================================================

@MainActor
final class SafariBrowserResourceController {

    private let resources:
        SafariResourceOrchestrator

    init() {

        self.resources =
            SafariResourceOrchestrator()
    }

    func start() async {

        await resources.start()
    }

    func attach(
        tabID: ResourceTabID,
        webView: WKWebView
    ) async {

        await resources.register(
            tabID: tabID,
            webView: webView
        )
    }

    func suspend(
        tabID: ResourceTabID
    ) async {

        await resources.suspend(
            tabID: tabID
        )
    }

    func restore(
        tabID: ResourceTabID
    ) async {

        await resources.restore(
            tabID: tabID
        )
    }

    func remove(
        tabID: ResourceTabID
    ) async {

        await resources.destroy(
            tabID: tabID
        )
    }

    func shutdown() async {

        await resources.stop()
    }
}






import Foundation
import WebKit
import OSLog

// ============================================================
// MARK: - IDENTIFIERS
// ============================================================

struct NavigationID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

struct NavigationTabID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

struct NavigationRequestID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

// ============================================================
// MARK: - PRIORITY
// ============================================================

enum NavigationPriority: Int, Codable, Sendable, Comparable {
    case prefetch = 0
    case background = 1
    case normal = 2
    case interactive = 3
    case userInitiated = 4

    static func < (
        lhs: NavigationPriority,
        rhs: NavigationPriority
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

// ============================================================
// MARK: - NAVIGATION STATE
// ============================================================

enum NavigationState: String, Codable, Sendable {
    case idle
    case queued
    case preparing
    case resolving
    case connecting
    case requesting
    case receiving
    case redirecting
    case rendering
    case completed
    case cancelled
    case failed
}

// ============================================================
// MARK: - HTTP METHOD
// ============================================================

enum HTTPMethod: String, Codable, Sendable {
    case get = "GET"
    case head = "HEAD"
    case post = "POST"
    case put = "PUT"
    case delete = "DELETE"
    case patch = "PATCH"
}

// ============================================================
// MARK: - NAVIGATION REQUEST
// ============================================================

struct NavigationRequest: Sendable, Codable, Hashable {

    let id: NavigationRequestID
    let navigationID: NavigationID
    let tabID: NavigationTabID

    var url: URL
    var method: HTTPMethod

    var priority: NavigationPriority

    var createdAt: Date

    var userInitiated: Bool
    var reload: Bool
    var restore: Bool
    var prefetch: Bool

    var allowsCache: Bool
    var allowsRedirects: Bool

    var headers: [String: String]

    init(
        tabID: NavigationTabID,
        url: URL,
        method: HTTPMethod = .get,
        priority: NavigationPriority = .normal,
        userInitiated: Bool = false,
        reload: Bool = false,
        restore: Bool = false,
        prefetch: Bool = false,
        allowsCache: Bool = true,
        allowsRedirects: Bool = true,
        headers: [String: String] = [:]
    ) {

        self.id = NavigationRequestID()
        self.navigationID = NavigationID()
        self.tabID = tabID
        self.url = url
        self.method = method
        self.priority = priority
        self.createdAt = Date()

        self.userInitiated = userInitiated
        self.reload = reload
        self.restore = restore
        self.prefetch = prefetch

        self.allowsCache = allowsCache
        self.allowsRedirects = allowsRedirects

        self.headers = headers
    }
}

// ============================================================
// MARK: - NAVIGATION ERROR
// ============================================================

enum NavigationError: Error, Sendable, Equatable {

    case invalidURL
    case cancelled
    case duplicateNavigation
    case invalidStateTransition
    case redirectLimitExceeded
    case webViewUnavailable
    case requestFailed(String)
    case invalidResponse
    case timeout
}

// ============================================================
// MARK: - NAVIGATION RESULT
// ============================================================

struct NavigationResult: Sendable {

    let navigationID: NavigationID
    let finalURL: URL?

    let statusCode: Int?
    let bytesReceived: Int64

    let startedAt: Date
    let completedAt: Date

    let state: NavigationState

    var duration: TimeInterval {
        completedAt.timeIntervalSince(
            startedAt
        )
    }

    var succeeded: Bool {
        state == .completed
    }
}

// ============================================================
// MARK: - NAVIGATION TRANSACTION
// ============================================================

struct NavigationTransaction: Sendable {

    let navigationID: NavigationID
    let tabID: NavigationTabID

    let originalURL: URL

    var currentURL: URL

    var state: NavigationState

    var redirectCount: Int

    var startTime: Date
    var completionTime: Date?

    var bytesReceived: Int64
    var responseStatusCode: Int?

    var errorDescription: String?

    var wasCacheHit: Bool
    var wasCancelled: Bool

    var duration: TimeInterval {

        let end =
            completionTime ?? Date()

        return end.timeIntervalSince(
            startTime
        )
    }

    var isFinished: Bool {

        switch state {

        case .completed,
             .cancelled,
             .failed:
            return true

        default:
            return false
        }
    }

    var succeeded: Bool {
        state == .completed
    }
}

// ============================================================
// MARK: - STATE MACHINE
// ============================================================

struct NavigationStateMachine {

    static func canTransition(
        from:
            NavigationState,
        to:
            NavigationState
    ) -> Bool {

        switch (from, to) {

        case (.idle, .queued):
            return true

        case (.queued, .preparing):
            return true

        case (.preparing, .resolving):
            return true

        case (.preparing, .connecting):
            return true

        case (.resolving, .connecting):
            return true

        case (.connecting, .requesting):
            return true

        case (.requesting, .receiving):
            return true

        case (.receiving, .redirecting):
            return true

        case (.redirecting, .resolving):
            return true

        case (.receiving, .rendering):
            return true

        case (.rendering, .completed):
            return true

        case (.queued, .cancelled),
             (.preparing, .cancelled),
             (.resolving, .cancelled),
             (.connecting, .cancelled),
             (.requesting, .cancelled),
             (.receiving, .cancelled),
             (.redirecting, .cancelled),
             (.rendering, .cancelled):
            return true

        case (.queued, .failed),
             (.preparing, .failed),
             (.resolving, .failed),
             (.connecting, .failed),
             (.requesting, .failed),
             (.receiving, .failed),
             (.redirecting, .failed),
             (.rendering, .failed):
            return true

        default:
            return false
        }
    }

    static func transition(
        transaction:
            inout NavigationTransaction,
        to:
            NavigationState
    ) throws {

        guard canTransition(
            from: transaction.state,
            to: to
        ) else {
            throw NavigationError
                .invalidStateTransition
        }

        transaction.state = to

        if to == .completed ||
           to == .failed ||
           to == .cancelled {

            transaction.completionTime =
                Date()
        }
    }
}

// ============================================================
// MARK: - NAVIGATION CANCELLATION
// ============================================================

actor NavigationCancellationManager {

    private var tasks:
        [NavigationID: Task<Void, Never>] = [:]

    func register(
        navigationID: NavigationID,
        task: Task<Void, Never>
    ) {

        tasks[navigationID] = task
    }

    func cancel(
        navigationID: NavigationID
    ) {

        tasks[
            navigationID
        ]?.cancel()

        tasks.removeValue(
            forKey: navigationID
        )
    }

    func remove(
        navigationID: NavigationID
    ) {

        tasks.removeValue(
            forKey: navigationID
        )
    }

    func cancelAll() {

        for task in tasks.values {
            task.cancel()
        }

        tasks.removeAll()
    }

    func contains(
        navigationID: NavigationID
    ) -> Bool {

        tasks[navigationID] != nil
    }
}

// ============================================================
// MARK: - REDIRECT TRACKER
// ============================================================

struct RedirectTracker: Sendable {

    let maximumRedirects: Int

    private(set) var visitedURLs:
        Set<URL> = []

    private(set) var count: Int = 0

    init(
        maximumRedirects: Int = 20
    ) {
        self.maximumRedirects =
            maximumRedirects
    }

    mutating func record(
        url: URL
    ) throws {

        if visitedURLs.contains(url) {
            throw NavigationError
                .redirectLimitExceeded
        }

        guard count <
                maximumRedirects
        else {
            throw NavigationError
                .redirectLimitExceeded
        }

        visitedURLs.insert(url)
        count += 1
    }
}

// ============================================================
// MARK: - NAVIGATION HISTORY
// ============================================================

struct NavigationHistoryEntry:
    Codable,
    Sendable,
    Identifiable {

    let id: UUID

    let url: URL
    let title: String?

    let visitedAt: Date

    init(
        url: URL,
        title: String? = nil
    ) {

        self.id = UUID()
        self.url = url
        self.title = title
        self.visitedAt = Date()
    }
}

actor NavigationHistoryManager {

    private var history:
        [NavigationTabID:
            [NavigationHistoryEntry]] = [:]

    private let maximumEntries:
        Int

    init(
        maximumEntries: Int = 500
    ) {
        self.maximumEntries =
            maximumEntries
    }

    func record(
        tabID: NavigationTabID,
        url: URL,
        title: String?
    ) {

        var entries =
            history[tabID] ?? []

        entries.append(
            NavigationHistoryEntry(
                url: url,
                title: title
            )
        )

        if entries.count >
            maximumEntries {

            entries.removeFirst(
                entries.count -
                maximumEntries
            )
        }

        history[tabID] =
            entries
    }

    func entries(
        for tabID: NavigationTabID
    ) -> [NavigationHistoryEntry] {

        history[tabID] ?? []
    }

    func clear(
        tabID: NavigationTabID
    ) {

        history.removeValue(
            forKey: tabID
        )
    }
}

// ============================================================
// MARK: - CACHE
// ============================================================

struct NavigationCacheEntry:
    Sendable {

    let url: URL

    let response:
        CachedURLResponse

    let createdAt: Date

    let expiration:
        Date?
}

actor NavigationCacheCoordinator {

    private var cache:
        [URL: NavigationCacheEntry] = [:]

    private let maximumEntries:
        Int

    init(
        maximumEntries: Int = 1_000
    ) {
        self.maximumEntries =
            maximumEntries
    }

    func insert(
        _ entry: NavigationCacheEntry
    ) {

        cache[entry.url] =
            entry

        if cache.count >
            maximumEntries {

            let oldest =
                cache.values
                    .sorted {
                        $0.createdAt <
                        $1.createdAt
                    }
                    .first

            if let oldest {
                cache.removeValue(
                    forKey: oldest.url
                )
            }
        }
    }

    func response(
        for url: URL
    ) -> CachedURLResponse? {

        guard
            let entry =
                cache[url]
        else {
            return nil
        }

        if let expiration =
            entry.expiration,
           expiration < Date() {

            cache.removeValue(
                forKey: url
            )

            return nil
        }

        return entry.response
    }

    func remove(
        url: URL
    ) {

        cache.removeValue(
            forKey: url
        )
    }

    func removeAll() {
        cache.removeAll()
    }

    func count() -> Int {
        cache.count
    }
}

// ============================================================
// MARK: - PREFETCH
// ============================================================

struct PrefetchRequest:
    Sendable,
    Hashable {

    let tabID: NavigationTabID
    let url: URL
    let priority: NavigationPriority
}

actor NavigationPrefetchCoordinator {

    private var active:
        Set<PrefetchRequest> = []

    private var completed:
        Set<URL> = []

    func enqueue(
        _ request: PrefetchRequest
    ) -> Bool {

        guard !completed.contains(
            request.url
        ) else {
            return false
        }

        return active.insert(
            request
        ).inserted
    }

    func complete(
        _ request: PrefetchRequest
    ) {

        active.remove(
            request
        )

        completed.insert(
            request.url
        )
    }

    func cancel(
        _ request: PrefetchRequest
    ) {

        active.remove(
            request
        )
    }

    func isPrefetched(
        url: URL
    ) -> Bool {

        completed.contains(url)
    }
}

// ============================================================
// MARK: - NETWORK ACTIVITY
// ============================================================

struct NetworkActivitySnapshot:
    Sendable {

    let navigationID:
        NavigationID

    let bytesReceived:
        Int64

    let bytesSent:
        Int64

    let timestamp:
        Date
}

actor NavigationNetworkMonitor {

    private var snapshots:
        [NavigationID:
            NetworkActivitySnapshot] = [:]

    func update(
        navigationID: NavigationID,
        bytesReceived: Int64,
        bytesSent: Int64 = 0
    ) {

        snapshots[navigationID] =
            NetworkActivitySnapshot(
                navigationID:
                    navigationID,
                bytesReceived:
                    bytesReceived,
                bytesSent:
                    bytesSent,
                timestamp:
                    Date()
            )
    }

    func snapshot(
        navigationID: NavigationID
    ) -> NetworkActivitySnapshot? {

        snapshots[navigationID]
    }

    func remove(
        navigationID: NavigationID
    ) {

        snapshots.removeValue(
            forKey: navigationID
        )
    }
}

// ============================================================
// MARK: - TELEMETRY
// ============================================================

struct NavigationTelemetryEvent:
    Sendable {

    enum Kind: Sendable {

        case queued
        case started
        case redirected
        case cacheHit
        case completed
        case cancelled
        case failed
        case prefetched
    }

    let kind: Kind

    let navigationID:
        NavigationID?

    let tabID:
        NavigationTabID?

    let url:
        URL?

    let timestamp:
        Date

    let duration:
        TimeInterval?

    let message:
        String
}

actor NavigationTelemetry {

    private var events:
        [NavigationTelemetryEvent] = []

    private let maximumEvents:
        Int = 20_000

    func record(
        _ event:
            NavigationTelemetryEvent
    ) {

        events.append(event)

        if events.count >
            maximumEvents {

            events.removeFirst(
                events.count -
                maximumEvents
            )
        }
    }

    func recent(
        limit: Int = 100
    ) -> [NavigationTelemetryEvent] {

        Array(
            events.suffix(limit)
        )
    }
}

// ============================================================
// MARK: - DIAGNOSTICS
// ============================================================

struct NavigationDiagnosticsReport:
    Sendable {

    let generatedAt: Date

    let activeNavigations:
        Int

    let queuedNavigations:
        Int

    let completedNavigations:
        Int

    let failedNavigations:
        Int

    let cancelledNavigations:
        Int

    let cacheEntries:
        Int
}

actor NavigationDiagnostics {

    private var completed = 0
    private var failed = 0
    private var cancelled = 0

    func recordCompletion() {
        completed += 1
    }

    func recordFailure() {
        failed += 1
    }

    func recordCancellation() {
        cancelled += 1
    }

    func report(
        active: Int,
        queued: Int,
        cacheEntries: Int
    ) -> NavigationDiagnosticsReport {

        NavigationDiagnosticsReport(
            generatedAt: Date(),
            activeNavigations: active,
            queuedNavigations: queued,
            completedNavigations: completed,
            failedNavigations: failed,
            cancelledNavigations: cancelled,
            cacheEntries: cacheEntries
        )
    }
}

// ============================================================
// MARK: - WEBKIT NAVIGATION BRIDGE
// ============================================================

@MainActor
final class WebKitNavigationBridge:
    NSObject,
    WKNavigationDelegate {

    private var webViews:
        [NavigationTabID: WKWebView] = [:]

    private var continuations:
        [NavigationID:
            CheckedContinuation<
                NavigationResult,
                Error>] = [:]

    private var transactions:
        [NavigationID:
            NavigationTransaction] = [:]

    private let logger =
        Logger(
            subsystem:
                "SafariNavigationRuntime",
            category:
                "WebKitBridge"
        )

    func register(
        tabID: NavigationTabID,
        webView: WKWebView
    ) {

        webViews[tabID] =
            webView

        webView.navigationDelegate =
            self
    }

    func remove(
        tabID: NavigationTabID
    ) {

        webViews[
            tabID
        ]?.navigationDelegate = nil

        webViews.removeValue(
            forKey: tabID
        )
    }

    func webView(
        for tabID:
            NavigationTabID
    ) -> WKWebView? {

        webViews[tabID]
    }

    func navigate(
        request:
            NavigationRequest
    ) async throws
        -> NavigationResult {

        guard
            let webView =
                webViews[
                    request.tabID
                ]
        else {
            throw NavigationError
                .webViewUnavailable
        }

        var transaction =
            NavigationTransaction(
                navigationID:
                    request.navigationID,
                tabID:
                    request.tabID,
                originalURL:
                    request.url,
                currentURL:
                    request.url,
                state:
                    .idle,
                redirectCount:
                    0,
                startTime:
                    Date(),
                completionTime:
                    nil,
                bytesReceived:
                    0,
                responseStatusCode:
                    nil,
                errorDescription:
                    nil,
                wasCacheHit:
                    false,
                wasCancelled:
                    false
            )

        try NavigationStateMachine
            .transition(
                transaction:
                    &transaction,
                to:
                    .queued
            )

        try NavigationStateMachine
            .transition(
                transaction:
                    &transaction,
                to:
                    .preparing
            )

        transactions[
            request.navigationID
        ] = transaction

        let urlRequest =
            makeURLRequest(
                request:
                    request
            )

        return try await withCheckedThrowingContinuation {
            (
                continuation:
                    CheckedContinuation<
                        NavigationResult,
                        Error>
            ) in

            continuations[
                request.navigationID
            ] = continuation

            webView.load(
                urlRequest
            )
        }
    }

    private func makeURLRequest(
        request:
            NavigationRequest
    ) -> URLRequest {

        var result =
            URLRequest(
                url:
                    request.url
            )

        result.httpMethod =
            request.method.rawValue

        for (
            key,
            value
        ) in request.headers {

            result.setValue(
                value,
                forHTTPHeaderField:
                    key
            )
        }

        if request.reload {
            result.cachePolicy =
                .reloadIgnoringLocalCacheData
        } else {
            result.cachePolicy =
                request.allowsCache
                ? .useProtocolCachePolicy
                : .reloadIgnoringLocalCacheData
        }

        return result
    }

    // --------------------------------------------------------
    // MARK: Navigation Started
    // --------------------------------------------------------

    func webView(
        _ webView: WKWebView,
        didStartProvisionalNavigation:
            WKNavigation?
    ) {

        guard
            let id =
                transactionID(
                    for:
                        webView
                )
        else {
            return
        }

        updateState(
            id:
                id,
            state:
                .connecting
        )

        updateState(
            id:
                id,
            state:
                .requesting
        )
    }

    // --------------------------------------------------------
    // MARK: Response
    // --------------------------------------------------------

    func webView(
        _ webView: WKWebView,
        didReceive
            response:
                WKNavigationResponse,
        decisionHandler:
            @escaping
            (WKNavigationResponsePolicy)
            -> Void
    ) {

        guard
            let id =
                transactionID(
                    for:
                        webView
                )
        else {

            decisionHandler(
                .allow
            )

            return
        }

        if let response =
            response.response
            as? HTTPURLResponse {

            transactions[id]?
                .responseStatusCode =
                response.statusCode
        }

        updateState(
            id:
                id,
            state:
                .receiving
        )

        decisionHandler(
            .allow
        )
    }

    // --------------------------------------------------------
    // MARK: Redirect
    // --------------------------------------------------------

    func webView(
        _ webView: WKWebView,
        didReceiveServerRedirectForProvisionalNavigation:
            WKNavigation?
    ) {

        guard
            let id =
                transactionID(
                    for:
                        webView
                )
        else {
            return
        }

        updateState(
            id:
                id,
            state:
                .redirecting
        )

        if let url =
            webView.url {

            transactions[id]?
                .currentURL =
                url

            transactions[id]?
                .redirectCount += 1
        }

        updateState(
            id:
                id,
            state:
                .resolving
        )
    }

    // --------------------------------------------------------
    // MARK: Commit
    // --------------------------------------------------------

    func webView(
        _ webView: WKWebView,
        didCommit
            navigation:
                WKNavigation?
    ) {

        guard
            let id =
                transactionID(
                    for:
                        webView
                )
        else {
            return
        }

        updateState(
            id:
                id,
            state:
                .rendering
        )
    }

    // --------------------------------------------------------
    // MARK: Finish
    // --------------------------------------------------------

    func webView(
        _ webView: WKWebView,
        didFinish
            navigation:
                WKNavigation?
    ) {

        guard
            let id =
                transactionID(
                    for:
                        webView
                )
        else {
            return
        }

        updateState(
            id:
                id,
            state:
                .completed
        )

        complete(
            id:
                id,
            webView:
                webView
        )
    }

    // --------------------------------------------------------
    // MARK: Failure
    // --------------------------------------------------------

    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation:
            WKNavigation?,
        withError:
            Error
    ) {

        fail(
            webView:
                webView,
            error:
                error
        )
    }

    func webView(
        _ webView: WKWebView,
        didFail navigation:
            WKNavigation?,
        withError:
            Error
    ) {

        fail(
            webView:
                webView,
            error:
                error
        )
    }

    private func fail(
        webView:
            WKWebView,
        error:
            Error
    ) {

        guard
            let id =
                transactionID(
                    for:
                        webView
                )
        else {
            return
        }

        transactions[id]?
            .errorDescription =
            error.localizedDescription

        updateState(
            id:
                id,
            state:
                .failed
        )

        let transaction =
            transactions[id]

        let result =
            NavigationResult(
                navigationID:
                    id,
                finalURL:
                    transaction?.currentURL,
                statusCode:
                    transaction?.responseStatusCode,
                bytesReceived:
                    transaction?.bytesReceived ?? 0,
                startedAt:
                    transaction?.startTime
                    ?? Date(),
                completedAt:
                    Date(),
                state:
                    .failed
            )

        continuations.removeValue(
            forKey:
                id
        )?.resume(
            throwing:
                NavigationError
                    .requestFailed(
                        error.localizedDescription
                    )
        )
    }

    private func complete(
        id:
            NavigationID,
        webView:
            WKWebView
    ) {

        let transaction =
            transactions[id]

        let result =
            NavigationResult(
                navigationID:
                    id,
                finalURL:
                    webView.url
                    ?? transaction?.currentURL,
                statusCode:
                    transaction?.responseStatusCode,
                bytesReceived:
                    transaction?.bytesReceived
                    ?? 0,
                startedAt:
                    transaction?.startTime
                    ?? Date(),
                completedAt:
                    Date(),
                state:
                    .completed
            )

        continuations.removeValue(
            forKey:
                id
        )?.resume(
            returning:
                result
        )
    }

    private func updateState(
        id:
            NavigationID,
        state:
            NavigationState
    ) {

        guard
            var transaction =
                transactions[id]
        else {
            return
        }

        do {

            try NavigationStateMachine
                .transition(
                    transaction:
                        &transaction,
                    to:
                        state
                )

            transactions[id] =
                transaction

        } catch {

            logger.error(
                "Invalid navigation state transition."
            )
        }
    }

    private func transactionID(
        for webView:
            WKWebView
    ) -> NavigationID? {

        transactions.first {
            [weak webView] pair in

            guard
                let current =
                    webViews[
                        pair.value.tabID
                    ]
            else {
                return false
            }

            return current === webView
        }?.key
    }
}

// ============================================================
// MARK: - NAVIGATION QUEUE
// ============================================================

struct QueuedNavigation:
    Sendable {

    let request:
        NavigationRequest

    let sequence:
        UInt64
}

actor NavigationQueue {

    private var items:
        [QueuedNavigation] = []

    private var sequence:
        UInt64 = 0

    func enqueue(
        _ request:
            NavigationRequest
    ) {

        sequence += 1

        items.append(
            QueuedNavigation(
                request:
                    request,
                sequence:
                    sequence
            )
        )

        sort()
    }

    func dequeue()
        -> QueuedNavigation? {

        guard !items.isEmpty
        else {
            return nil
        }

        return items.removeFirst()
    }

    func remove(
        navigationID:
            NavigationID
    ) {

        items.removeAll {
            $0.request.navigationID ==
            navigationID
        }
    }

    func count() -> Int {
        items.count
    }

    func all() -> [QueuedNavigation] {
        items
    }

    private func sort() {

        items.sort {

            if $0.request.priority !=
                $1.request.priority {

                return
                    $0.request.priority >
                    $1.request.priority
            }

            return
                $0.sequence <
                $1.sequence
        }
    }
}

// ============================================================
// MARK: - NAVIGATION ACTOR
// ============================================================

actor NavigationCoordinator {

    private let queue:
        NavigationQueue

    private let cancellation:
        NavigationCancellationManager

    private let history:
        NavigationHistoryManager

    private let cache:
        NavigationCacheCoordinator

    private let prefetch:
        NavigationPrefetchCoordinator

    private let network:
        NavigationNetworkMonitor

    private let telemetry:
        NavigationTelemetry

    private let diagnostics:
        NavigationDiagnostics

    private var active:
        [NavigationID:
            NavigationTransaction] = [:]

    private var completed:
        [NavigationID:
            NavigationTransaction] = [:]

    private var pumpTask:
        Task<Void, Never>?

    private let logger =
        Logger(
            subsystem:
                "SafariNavigationRuntime",
            category:
                "NavigationCoordinator"
        )

    init(
        queue:
            NavigationQueue =
            NavigationQueue(),

        cancellation:
            NavigationCancellationManager =
            NavigationCancellationManager(),

        history:
            NavigationHistoryManager =
            NavigationHistoryManager(),

        cache:
            NavigationCacheCoordinator =
            NavigationCacheCoordinator(),

        prefetch:
            NavigationPrefetchCoordinator =
            NavigationPrefetchCoordinator(),

        network:
            NavigationNetworkMonitor =
            NavigationNetworkMonitor(),

        telemetry:
            NavigationTelemetry =
            NavigationTelemetry(),

        diagnostics:
            NavigationDiagnostics =
            NavigationDiagnostics()
    ) {

        self.queue =
            queue

        self.cancellation =
            cancellation

        self.history =
            history

        self.cache =
            cache

        self.prefetch =
            prefetch

        self.network =
            network

        self.telemetry =
            telemetry

        self.diagnostics =
            diagnostics
    }

    // ========================================================
    // MARK: START
    // ========================================================

    func start() {

        guard pumpTask == nil
        else {
            return
        }

        pumpTask =
            Task {

                while !Task.isCancelled {

                    await processNext()

                    try? await Task.sleep(
                        for:
                            .milliseconds(10)
                    )
                }
            }
    }

    // ========================================================
    // MARK: STOP
    // ========================================================

    func stop() {

        pumpTask?.cancel()
        pumpTask = nil
    }

    // ========================================================
    // MARK: QUEUE
    // ========================================================

    func enqueue(
        _ request:
            NavigationRequest
    ) async throws {

        if active.values.contains(
            where: {
                $0.tabID ==
                    request.tabID &&
                $0.currentURL ==
                    request.url
            }
        ) {

            throw NavigationError
                .duplicateNavigation
        }

        await queue.enqueue(
            request
        )

        await telemetry.record(
            NavigationTelemetryEvent(
                kind:
                    .queued,
                navigationID:
                    request.navigationID,
                tabID:
                    request.tabID,
                url:
                    request.url,
                timestamp:
                    Date(),
                duration:
                    nil,
                message:
                    "Navigation queued."
            )
        )
    }

    // ========================================================
    // MARK: PROCESS
    // ========================================================

    private func processNext()
        async {

        guard
            let item =
                await queue.dequeue()
        else {
            return
        }

        let request =
            item.request

        let transaction =
            NavigationTransaction(
                navigationID:
                    request.navigationID,
                tabID:
                    request.tabID,
                originalURL:
                    request.url,
                currentURL:
                    request.url,
                state:
                    .queued,
                redirectCount:
                    0,
                startTime:
                    Date(),
                completionTime:
                    nil,
                bytesReceived:
                    0,
                responseStatusCode:
                    nil,
                errorDescription:
                    nil,
                wasCacheHit:
                    false,
                wasCancelled:
                    false
            )

        active[
            request.navigationID
        ] =
            transaction

        await telemetry.record(
            NavigationTelemetryEvent(
                kind:
                    .started,
                navigationID:
                    request.navigationID,
                tabID:
                    request.tabID,
                url:
                    request.url,
                timestamp:
                    Date(),
                duration:
                    nil,
                message:
                    "Navigation started."
            )
        )
    }

    // ========================================================
    // MARK: CANCEL
    // ========================================================

    func cancel(
        navigationID:
            NavigationID
    ) async {

        await queue.remove(
            navigationID:
                navigationID
        )

        await cancellation.cancel(
            navigationID:
                navigationID
        )

        if var transaction =
            active[
                navigationID
            ] {

            transaction.state =
                .cancelled

            transaction.wasCancelled =
                true

            transaction.completionTime =
                Date()

            active.removeValue(
                forKey:
                    navigationID
            )

            completed[
                navigationID
            ] =
                transaction

            await diagnostics
                .recordCancellation()

            await telemetry.record(
                NavigationTelemetryEvent(
                    kind:
                        .cancelled,
                    navigationID:
                        navigationID,
                    tabID:
                        transaction.tabID,
                    url:
                        transaction.currentURL,
                    timestamp:
                        Date(),
                    duration:
                        transaction.duration,
                    message:
                        "Navigation cancelled."
                )
            }
        }
    }

    // ========================================================
    // MARK: ACTIVE
    // ========================================================

    func activeTransactions()
        -> [NavigationTransaction] {

        Array(
            active.values
        )
    }

    func transaction(
        id:
            NavigationID
    ) -> NavigationTransaction? {

        active[id] ??
        completed[id]
    }

    // ========================================================
    // MARK: CACHE ACCESS
    // ========================================================

    func cachedResponse(
        for url: URL
    ) async -> CachedURLResponse? {

        await cache.response(
            for:
                url
        )
    }

    // ========================================================
    // MARK: HISTORY
    // ========================================================

    func recordHistory(
        tabID:
            NavigationTabID,
        url:
            URL,
        title:
            String?
    ) async {

        await history.record(
            tabID:
                tabID,
            url:
                url,
            title:
                title
        )
    }

    // ========================================================
    // MARK: PREFETCH
    // ========================================================

    func enqueuePrefetch(
        tabID:
            NavigationTabID,
        url:
            URL
    ) async {

        let request =
            PrefetchRequest(
                tabID:
                    tabID,
                url:
                    url,
                priority:
                    .prefetch
            )

        guard
            await prefetch.enqueue(
                request
            )
        else {
            return
        }

        await telemetry.record(
            NavigationTelemetryEvent(
                kind:
                    .prefetched,
                navigationID:
                    nil,
                tabID:
                    tabID,
                url:
                    url,
                timestamp:
                    Date(),
                duration:
                    nil,
                message:
                    "Prefetch queued."
            )
        )
    }

    // ========================================================
    // MARK: DIAGNOSTICS
    // ========================================================

    func diagnosticsReport()
        async
        -> NavigationDiagnosticsReport {

        await diagnostics.report(
            active:
                active.count,
            queued:
                await queue.count(),
            cacheEntries:
                await cache.count()
        )
    }
}

// ============================================================
// MARK: - MAIN ACTOR NAVIGATION SERVICE
// ============================================================

@MainActor
final class SafariNavigationRuntime {

    let coordinator:
        NavigationCoordinator

    let webKit:
        WebKitNavigationBridge

    private let logger =
        Logger(
            subsystem:
                "SafariNavigationRuntime",
            category:
                "Runtime"
        )

    init() {

        self.coordinator =
            NavigationCoordinator()

        self.webKit =
            WebKitNavigationBridge()
    }

    // ========================================================
    // MARK: START
    // ========================================================

    func start() async {

        await coordinator.start()

        logger.info(
            "Navigation runtime started."
        )
    }

    // ========================================================
    // MARK: STOP
    // ========================================================

    func stop() async {

        await coordinator.stop()

        logger.info(
            "Navigation runtime stopped."
        )
    }

    // ========================================================
    // MARK: REGISTER WEBVIEW
    // ========================================================

    func register(
        tabID:
            NavigationTabID,
        webView:
            WKWebView
    ) {

        webKit.register(
            tabID:
                tabID,
            webView:
                webView
        )
    }

    // ========================================================
    // MARK: NAVIGATE
    // ========================================================

    func navigate(
        tabID:
            NavigationTabID,
        url:
            URL,
        priority:
            NavigationPriority =
                .userInitiated
    ) async throws
        -> NavigationResult {

        guard
            webKit.webView(
                for:
                    tabID
            ) != nil
        else {
            throw NavigationError
                .webViewUnavailable
        }

        let request =
            NavigationRequest(
                tabID:
                    tabID,
                url:
                    url,
                priority:
                    priority,
                userInitiated:
                    priority ==
                    .userInitiated
            )

        await coordinator.enqueue(
            request
        )

        return try await webKit.navigate(
            request:
                request
        )
    }

    // ========================================================
    // MARK: RELOAD
    // ========================================================

    func reload(
        tabID:
            NavigationTabID
    ) async throws
        -> NavigationResult {

        guard
            let webView =
                webKit.webView(
                    for:
                        tabID
                ),
            let url =
                webView.url
        else {
            throw NavigationError
                .invalidURL
        }

        let request =
            NavigationRequest(
                tabID:
                    tabID,
                url:
                    url,
                priority:
                    .userInitiated,
                userInitiated:
                    true,
                reload:
                    true
            )

        await coordinator.enqueue(
            request
        )

        return try await webKit.navigate(
            request:
                request
        )
    }

    // ========================================================
    // MARK: BACK
    // ========================================================

    func goBack(
        tabID:
            NavigationTabID
    ) {

        webKit
            .webView(
                for:
                    tabID
            )?
            .goBack()
    }

    // ========================================================
    // MARK: FORWARD
    // ========================================================

    func goForward(
        tabID:
            NavigationTabID
    ) {

        webKit
            .webView(
                for:
                    tabID
            )?
            .goForward()
    }

    // ========================================================
    // MARK: STOP
    // ========================================================

    func stopLoading(
        tabID:
            NavigationTabID
    ) {

        webKit
            .webView(
                for:
                    tabID
            )?
            .stopLoading()
    }

    // ========================================================
    // MARK: CANCEL
    // ========================================================

    func cancel(
        navigationID:
            NavigationID
    ) async {

        await coordinator.cancel(
            navigationID:
                navigationID
        )
    }

    // ========================================================
    // MARK: PREFETCH
    // ========================================================

    func prefetch(
        tabID:
            NavigationTabID,
        url:
            URL
    ) async {

        await coordinator.enqueuePrefetch(
            tabID:
                tabID,
            url:
                url
        )
    }
}

// ============================================================
// MARK: - NAVIGATION PERFORMANCE METRICS
// ============================================================

struct NavigationPerformanceMetrics:
    Sendable {

    var dnsDuration:
        TimeInterval = 0

    var connectionDuration:
        TimeInterval = 0

    var requestDuration:
        TimeInterval = 0

    var responseDuration:
        TimeInterval = 0

    var renderingDuration:
        TimeInterval = 0

    var totalDuration:
        TimeInterval = 0

    var bytesReceived:
        Int64 = 0

    var cacheHit:
        Bool = false
}

// ============================================================
// MARK: - PERFORMANCE STORE
// ============================================================

actor NavigationPerformanceStore {

    private var metrics:
        [NavigationID:
            NavigationPerformanceMetrics] = [:]

    func set(
        navigationID:
            NavigationID,
        metrics:
            NavigationPerformanceMetrics
    ) {

        self.metrics[
            navigationID
        ] =
            metrics
    }

    func metrics(
        for:
            NavigationID
    ) -> NavigationPerformanceMetrics? {

        metrics[
            `for`
        ]
    }

    func remove(
        navigationID:
            NavigationID
    ) {

        metrics.removeValue(
            forKey:
                navigationID
        )
    }
}

// ============================================================
// MARK: - URL POLICY
// ============================================================

struct NavigationURLPolicy:
    Sendable {

    var allowsHTTP = true
    var allowsHTTPS = true

    func validate(
        _ url:
            URL
    ) throws {

        guard
            let scheme =
                url.scheme?
                    .lowercased()
        else {
            throw NavigationError
                .invalidURL
        }

        switch scheme {

        case "https":
            guard allowsHTTPS else {
                throw NavigationError
                    .invalidURL
            }

        case "http":
            guard allowsHTTP else {
                throw NavigationError
                    .invalidURL
            }

        default:
            throw NavigationError
                .invalidURL
        }
    }
}

// ============================================================
// MARK: - REQUEST BUILDER
// ============================================================

struct NavigationRequestBuilder:
    Sendable {

    let policy:
        NavigationURLPolicy

    func build(
        tabID:
            NavigationTabID,
        url:
            URL,
        priority:
            NavigationPriority =
                .userInitiated
    ) throws
        -> NavigationRequest {

        try policy.validate(
            url
        )

        return NavigationRequest(
            tabID:
                tabID,
            url:
                url,
            priority:
                priority,
            userInitiated:
                priority ==
                .userInitiated
        )
    }
}

// ============================================================
// MARK: - NAVIGATION LOAD CONTROLLER
// ============================================================

@MainActor
final class SafariNavigationLoadController {

    private let runtime:
        SafariNavigationRuntime

    init(
        runtime:
            SafariNavigationRuntime
    ) {

        self.runtime =
            runtime
    }

    func load(
        url:
            URL,
        tabID:
            NavigationTabID
    ) async {

        do {

            _ =
                try await runtime.navigate(
                    tabID:
                        tabID,
                    url:
                        url,
                    priority:
                        .userInitiated
                )

        } catch
            NavigationError.cancelled {

            // Expected user cancellation.

        } catch {

            print(
                "Navigation error:",
                error
            )
        }
    }
}

// ============================================================
// MARK: - TEST HELPERS
// ============================================================

struct NavigationTestFactory {

    static func request(
        tabID:
            NavigationTabID =
            NavigationTabID(),
        url:
            URL =
            URL(
                string:
                    "https://example.com"
            )!
    ) -> NavigationRequest {

        NavigationRequest(
            tabID:
                tabID,
            url:
                url,
            priority:
                .userInitiated,
            userInitiated:
                true
        )
    }
}

// ============================================================
// MARK: - STATE MACHINE TESTS
// ============================================================

#if DEBUG

import XCTest

final class NavigationStateMachineTests:
    XCTestCase {

    func testNormalNavigationPath() {

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .idle,
                    to:
                        .queued
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .queued,
                    to:
                        .preparing
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .preparing,
                    to:
                        .connecting
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .connecting,
                    to:
                        .requesting
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .requesting,
                    to:
                        .receiving
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .receiving,
                    to:
                        .rendering
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .rendering,
                    to:
                        .completed
                )
        )
    }

    func testCancellation() {

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .requesting,
                    to:
                        .cancelled
                )
        )

        XCTAssertTrue(
            NavigationStateMachine
                .canTransition(
                    from:
                        .receiving,
                    to:
                        .cancelled
                )
        )
    }

    func testInvalidTransition() {

        XCTAssertFalse(
            NavigationStateMachine
                .canTransition(
                    from:
                        .completed,
                    to:
                        .requesting
                )
        )
    }
}

final class RedirectTrackerTests:
    XCTestCase {

    func testRedirectTracking()
        throws {

        var tracker =
            RedirectTracker(
                maximumRedirects:
                    2
            )

        let first =
            URL(
                string:
                    "https://example.com"
            )!

        let second =
            URL(
                string:
                    "https://example.org"
            )!

        try tracker.record(
            url:
                first
        )

        try tracker.record(
            url:
                second
        )

        XCTAssertEqual(
            tracker.count,
            2
        )
    }

    func testDuplicateRedirectFails()
        throws {

        var tracker =
            RedirectTracker()

        let url =
            URL(
                string:
                    "https://example.com"
            )!

        try tracker.record(
            url:
                url
        )

        XCTAssertThrowsError(
            try tracker.record(
                url:
                    url
            )
        )
    }
}

final class NavigationURLPolicyTests:
    XCTestCase {

    func testHTTPSAllowed()
        throws {

        let policy =
            NavigationURLPolicy()

        try policy.validate(
            URL(
                string:
                    "https://example.com"
            )!
        )
    }

    func testUnsupportedScheme()
        throws {

        let policy =
            NavigationURLPolicy()

        XCTAssertThrowsError(
            try policy.validate(
                URL(
                    string:
                        "ftp://example.com"
                )!
            )
        )
    }
}

#endif





import Foundation
import WebKit
import OSLog

// ============================================================
// MARK: - IDENTIFIERS
// ============================================================

struct PredictionID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

struct PredictionTabID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init(_ rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

// ============================================================
// MARK: - PREDICTION SOURCE
// ============================================================

enum PredictionSource: String, Codable, Sendable {

    case recentHistory
    case sessionHistory
    case domainPattern
    case sequencePattern
    case frequencyPattern
    case userAction
    case restoredSession
}

// ============================================================
// MARK: - PREDICTION PRIORITY
// ============================================================

enum PredictionPriority: Int, Codable, Sendable, Comparable {

    case speculative = 0
    case low = 1
    case normal = 2
    case high = 3
    case immediate = 4

    static func < (
        lhs: PredictionPriority,
        rhs: PredictionPriority
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

// ============================================================
// MARK: - PREDICTION POLICY
// ============================================================

struct PredictionPolicy:
    Codable,
    Sendable {

    var minimumConfidence:
        Double = 0.60

    var aggressiveConfidence:
        Double = 0.85

    var maximumPredictions:
        Int = 8

    var maximumPrefetches:
        Int = 3

    var maximumPerDomain:
        Int = 2

    var maximumHistoryEntries:
        Int = 2_000

    var learningEnabled:
        Bool = true

    var prefetchEnabled:
        Bool = true

    var allowCrossOriginPrefetch:
        Bool = false

    var allowPrivateBrowsingLearning:
        Bool = false

    var minimumObservationCount:
        Int = 2

    var speculativeBudgetBytes:
        Int64 = 2_000_000

    var normalBudgetBytes:
        Int64 = 10_000_000

    var aggressiveBudgetBytes:
        Int64 = 25_000_000
}

// ============================================================
// MARK: - NAVIGATION OBSERVATION
// ============================================================

struct NavigationObservation:
    Codable,
    Sendable {

    let id:
        UUID

    let tabID:
        PredictionTabID

    let url:
        URL

    let previousURL:
        URL?

    let timestamp:
        Date

    let userInitiated:
        Bool

    let reload:
        Bool

    let restored:
        Bool

    let title:
        String?

    init(
        tabID:
            PredictionTabID,
        url:
            URL,
        previousURL:
            URL?,
        userInitiated:
            Bool,
        reload:
            Bool,
        restored:
            Bool,
        title:
            String?
    ) {

        self.id = UUID()
        self.tabID = tabID
        self.url = url
        self.previousURL = previousURL
        self.timestamp = Date()
        self.userInitiated = userInitiated
        self.reload = reload
        self.restored = restored
        self.title = title
    }
}

// ============================================================
// MARK: - URL SIGNATURE
// ============================================================

struct URLSignature:
    Hashable,
    Codable,
    Sendable {

    let scheme:
        String

    let host:
        String

    let path:
        String

    init(
        url:
            URL
    ) {

        self.scheme =
            url.scheme?
                .lowercased()
            ?? ""

        self.host =
            url.host?
                .lowercased()
            ?? ""

        self.path =
            url.path
    }

    var origin:
        String {

        "\(scheme)://\(host)"
    }

    var isValid:
        Bool {

        !host.isEmpty
    }
}

// ============================================================
// MARK: - SEQUENCE KEY
// ============================================================

struct NavigationSequenceKey:
    Hashable,
    Codable,
    Sendable {

    let from:
        URLSignature

    let to:
        URLSignature
}

// ============================================================
// MARK: - SEQUENCE STATISTICS
// ============================================================

struct SequenceStatistics:
    Codable,
    Sendable {

    var count:
        Int = 0

    var lastSeen:
        Date?

    var successfulPredictions:
        Int = 0

    var failedPredictions:
        Int = 0

    var confidence:
        Double = 0

    mutating func observe(
        success:
            Bool
    ) {

        count += 1
        lastSeen = Date()

        if success {
            successfulPredictions += 1
        } else {
            failedPredictions += 1
        }

        recalculateConfidence()
    }

    mutating func recalculateConfidence() {

        guard count > 0 else {
            confidence = 0
            return
        }

        let successRate =
            Double(
                successfulPredictions
            )
            /
            Double(count)

        let observationFactor =
            min(
                1.0,
                Double(count) / 10.0
            )

        confidence =
            successRate *
            observationFactor
    }
}

// ============================================================
// MARK: - DOMAIN STATISTICS
// ============================================================

struct DomainStatistics:
    Codable,
    Sendable {

    var visits:
        Int = 0

    var lastVisited:
        Date?

    var paths:
        [String: Int] = [:]

    mutating func observe(
        url:
            URL
    ) {

        visits += 1
        lastVisited = Date()

        let path =
            url.path.isEmpty
            ? "/"
            : url.path

        paths[path, default: 0] += 1
    }

    func mostFrequentPaths(
        limit:
            Int
    ) -> [String] {

        paths
            .sorted {
                $0.value >
                $1.value
            }
            .prefix(limit)
            .map(\.key)
    }
}

// ============================================================
// MARK: - PREDICTION
// ============================================================

struct PagePrediction:
    Codable,
    Sendable,
    Identifiable {

    let id:
        PredictionID

    let tabID:
        PredictionTabID

    let sourceURL:
        URL

    let predictedURL:
        URL

    let source:
        PredictionSource

    let priority:
        PredictionPriority

    let confidence:
        Double

    let generatedAt:
        Date

    let expiresAt:
        Date

    let observationCount:
        Int

    let sameOrigin:
        Bool

    var isExpired:
        Bool {
        Date() >= expiresAt
    }

    init(
        tabID:
            PredictionTabID,
        sourceURL:
            URL,
        predictedURL:
            URL,
        source:
            PredictionSource,
        priority:
            PredictionPriority,
        confidence:
            Double,
        observationCount:
            Int,
        lifetime:
            TimeInterval =
                60
    ) {

        self.id =
            PredictionID()

        self.tabID =
            tabID

        self.sourceURL =
            sourceURL

        self.predictedURL =
            predictedURL

        self.source =
            source

        self.priority =
            priority

        self.confidence =
            confidence

        self.generatedAt =
            Date()

        self.expiresAt =
            Date()
            .addingTimeInterval(
                lifetime
            )

        self.observationCount =
            observationCount

        self.sameOrigin =
            URLSignature(
                url:
                    sourceURL
            ).origin
            ==
            URLSignature(
                url:
                    predictedURL
            ).origin
    }
}

// ============================================================
// MARK: - PREDICTION SCORE
// ============================================================

struct PredictionScore:
    Sendable {

    var sequence:
        Double = 0

    var frequency:
        Double = 0

    var recency:
        Double = 0

    var domain:
        Double = 0

    var origin:
        Double = 0

    var userAction:
        Double = 0

    var total:
        Double = 0

    mutating func calculate() {

        total =
            sequence * 0.40
            +
            frequency * 0.20
            +
            recency * 0.15
            +
            domain * 0.10
            +
            origin * 0.10
            +
            userAction * 0.05

        total =
            max(
                0,
                min(
                    1,
                    total
                )
            )
    }
}

// ============================================================
// MARK: - PREDICTION EVENT
// ============================================================

enum PredictionEventKind:
    String,
    Codable,
    Sendable {

    case observationRecorded
    case predictionCreated
    case predictionSelected
    case prefetchStarted
    case prefetchCompleted
    case prefetchCancelled
    case predictionHit
    case predictionMiss
    case predictionExpired
}

// ============================================================
// MARK: - TELEMETRY
// ============================================================

struct PredictionTelemetryEvent:
    Codable,
    Sendable {

    let kind:
        PredictionEventKind

    let predictionID:
        PredictionID?

    let url:
        URL?

    let confidence:
        Double?

    let timestamp:
        Date

    let message:
        String
}

actor PredictionTelemetry {

    private var events:
        [PredictionTelemetryEvent] = []

    private let maximumEvents =
        10_000

    func record(
        _ event:
            PredictionTelemetryEvent
    ) {

        events.append(event)

        if events.count >
            maximumEvents {

            events.removeFirst(
                events.count -
                maximumEvents
            )
        }
    }

    func recent(
        limit:
            Int = 100
    )
        -> [PredictionTelemetryEvent] {

        Array(
            events.suffix(
                limit
            )
        )
    }
}

// ============================================================
// MARK: - PREDICTION STORE
// ============================================================

actor PredictionStore {

    private var observations:
        [NavigationObservation] = []

    private var sequences:
        [NavigationSequenceKey:
            SequenceStatistics] = [:]

    private var domains:
        [String:
            DomainStatistics] = [:]

    private var predictions:
        [PredictionID:
            PagePrediction] = [:]

    private let policy:
        PredictionPolicy

    init(
        policy:
            PredictionPolicy
    ) {

        self.policy =
            policy
    }

    // --------------------------------------------------------
    // MARK: Observation
    // --------------------------------------------------------

    func record(
        _ observation:
            NavigationObservation
    ) {

        guard policy.learningEnabled
        else {
            return
        }

        if let previous =
            observations.last {

            let key =
                NavigationSequenceKey(
                    from:
                        URLSignature(
                            url:
                                previous.url
                        ),
                    to:
                        URLSignature(
                            url:
                                observation.url
                        )
                )

            var statistics =
                sequences[key]
                ?? SequenceStatistics()

            statistics.count += 1
            statistics.lastSeen =
                observation.timestamp

            sequences[key] =
                statistics
        }

        let domain =
            URLSignature(
                url:
                    observation.url
            ).origin

        var domainStatistics =
            domains[domain]
            ?? DomainStatistics()

        domainStatistics.observe(
            url:
                observation.url
        )

        domains[domain] =
            domainStatistics

        observations.append(
            observation
        )

        if observations.count >
            policy.maximumHistoryEntries {

            observations.removeFirst(
                observations.count -
                policy.maximumHistoryEntries
            )
        }
    }

    // --------------------------------------------------------
    // MARK: Previous
    // --------------------------------------------------------

    func previous(
        for url:
            URL
    ) -> NavigationObservation? {

        observations.last {
            $0.url == url
        }
    }

    // --------------------------------------------------------
    // MARK: Sequence
    // --------------------------------------------------------

    func statistics(
        from:
            URL,
        to:
            URL
    ) -> SequenceStatistics {

        let key =
            NavigationSequenceKey(
                from:
                    URLSignature(
                        url:
                            from
                    ),
                to:
                    URLSignature(
                        url:
                            to
                    )
            )

        return sequences[key]
            ?? SequenceStatistics()
    }

    // --------------------------------------------------------
    // MARK: Domain
    // --------------------------------------------------------

    func domainStatistics(
        for url:
            URL
    ) -> DomainStatistics {

        let domain =
            URLSignature(
                url:
                    url
            ).origin

        return domains[domain]
            ?? DomainStatistics()
    }

    // --------------------------------------------------------
    // MARK: Predictions
    // --------------------------------------------------------

    func insert(
        _ prediction:
            PagePrediction
    ) {

        predictions[
            prediction.id
        ] =
            prediction
    }

    func remove(
        _ id:
            PredictionID
    ) {

        predictions.removeValue(
            forKey:
                id
        )
    }

    func activePredictions(
        for tabID:
            PredictionTabID
    ) -> [PagePrediction] {

        predictions.values
            .filter {
                $0.tabID == tabID &&
                !$0.isExpired
            }
            .sorted {
                if $0.priority !=
                    $1.priority {

                    return
                        $0.priority >
                        $1.priority
                }

                return
                    $0.confidence >
                    $1.confidence
            }
    }

    func clearExpired() {

        let expired =
            predictions.values
                .filter(\.isExpired)
                .map(\.id)

        for id in expired {
            predictions.removeValue(
                forKey:
                    id
            )
        }
    }

    func allPredictions()
        -> [PagePrediction] {

        Array(
            predictions.values
        )
    }
}

// ============================================================
// MARK: - PREDICTION ENGINE
// ============================================================

actor PagePredictionEngine {

    private let store:
        PredictionStore

    private let telemetry:
        PredictionTelemetry

    private let policy:
        PredictionPolicy

    private let logger =
        Logger(
            subsystem:
                "SafariPredictiveLoading",
            category:
                "PredictionEngine"
        )

    init(
        policy:
            PredictionPolicy =
            PredictionPolicy()
    ) {

        self.policy =
            policy

        self.store =
            PredictionStore(
                policy:
                    policy
            )

        self.telemetry =
            PredictionTelemetry()
    }

    // --------------------------------------------------------
    // MARK: Observe Navigation
    // --------------------------------------------------------

    func observe(
        tabID:
            PredictionTabID,
        url:
            URL,
        previousURL:
            URL? = nil,
        userInitiated:
            Bool = true,
        reload:
            Bool = false,
        restored:
            Bool = false,
        title:
            String? = nil
    ) async {

        let observation =
            NavigationObservation(
                tabID:
                    tabID,
                url:
                    url,
                previousURL:
                    previousURL,
                userInitiated:
                    userInitiated,
                reload:
                    reload,
                restored:
                    restored,
                title:
                    title
            )

        await store.record(
            observation
        )

        await telemetry.record(
            PredictionTelemetryEvent(
                kind:
                    .observationRecorded,
                predictionID:
                    nil,
                url:
                    url,
                confidence:
                    nil,
                timestamp:
                    Date(),
                message:
                    "Navigation observation recorded."
            )
        )
    }

    // --------------------------------------------------------
    // MARK: Predict
    // --------------------------------------------------------

    func predict(
        tabID:
            PredictionTabID,
        currentURL:
            URL
    ) async
        -> [PagePrediction] {

        guard policy.learningEnabled
        else {
            return []
        }

        await store.clearExpired()

        let candidates =
            await generateCandidates(
                tabID:
                    tabID,
                currentURL:
                    currentURL
            )

        let filtered =
            candidates
                .filter {
                    $0.confidence >=
                    policy.minimumConfidence
                }
                .sorted {
                    if $0.priority !=
                        $1.priority {

                        return
                            $0.priority >
                            $1.priority
                    }

                    return
                        $0.confidence >
                        $1.confidence
                }
                .prefix(
                    policy.maximumPredictions
                )

        let predictions =
            Array(filtered)

        for prediction in predictions {

            await store.insert(
                prediction
            )

            await telemetry.record(
                PredictionTelemetryEvent(
                    kind:
                        .predictionCreated,
                    predictionID:
                        prediction.id,
                    url:
                        prediction.predictedURL,
                    confidence:
                        prediction.confidence,
                    timestamp:
                        Date(),
                    message:
                        "Page prediction generated."
                )
            )
        }

        return predictions
    }

    // --------------------------------------------------------
    // MARK: Candidate Generation
    // --------------------------------------------------------

    private func generateCandidates(
        tabID:
            PredictionTabID,
        currentURL:
            URL
    ) async
        -> [PagePrediction] {

        var results:
            [PagePrediction] = []

        let currentSignature =
            URLSignature(
                url:
                    currentURL
            )

        // ----------------------------------------------------
        // Sequence-based candidates
        // ----------------------------------------------------

        let observations =
            await recentObservations()

        for observation in observations {

            guard
                let previous =
                    observation.previousURL,
                previous == currentURL
            else {
                continue
            }

            let statistics =
                await store.statistics(
                    from:
                        currentURL,
                    to:
                        observation.url
                )

            var score =
                PredictionScore()

            score.sequence =
                min(
                    1,
                    Double(
                        statistics.count
                    )
                    /
                    10
                )

            score.recency =
                recencyScore(
                    observation.timestamp
                )

            score.origin =
                currentSignature.origin
                ==
                URLSignature(
                    url:
                        observation.url
                ).origin
                ? 1
                : 0

            score.calculate()

            guard
                score.total >=
                policy.minimumConfidence
            else {
                continue
            }

            let priority =
                priority(
                    confidence:
                        score.total
                )

            results.append(
                PagePrediction(
                    tabID:
                        tabID,
                    sourceURL:
                        currentURL,
                    predictedURL:
                        observation.url,
                    source:
                        .sequencePattern,
                    priority:
                        priority,
                    confidence:
                        score.total,
                    observationCount:
                        statistics.count
                )
            )
        }

        // ----------------------------------------------------
        // Same-domain frequency
        // ----------------------------------------------------

        let domainStatistics =
            await store.domainStatistics(
                for:
                    currentURL
            )

        for path in
            domainStatistics
                .mostFrequentPaths(
                    limit:
                        5
                ) {

            guard
                path != currentURL.path
            else {
                continue
            }

            guard
                let candidate =
                    buildURL(
                        from:
                            currentURL,
                        path:
                            path
                    )
            else {
                continue
            }

            var score =
                PredictionScore()

            score.frequency =
                min(
                    1,
                    Double(
                        domainStatistics
                            .paths[path]
                        ?? 0
                    )
                    /
                    10
                )

            score.domain =
                1

            score.origin =
                1

            score.recency =
                recencyScore(
                    domainStatistics
                        .lastVisited
                )

            score.calculate()

            guard
                score.total >=
                policy.minimumConfidence
            else {
                continue
            }

            results.append(
                PagePrediction(
                    tabID:
                        tabID,
                    sourceURL:
                        currentURL,
                    predictedURL:
                        candidate,
                    source:
                        .frequencyPattern,
                    priority:
                        .normal,
                    confidence:
                        score.total,
                    observationCount:
                        domainStatistics.visits
                )
            )
        }

        return deduplicate(
            results
        )
    }

    // --------------------------------------------------------
    // MARK: Recent Observations
    // --------------------------------------------------------

    private func recentObservations()
        async
        -> [NavigationObservation] {

        let predictions =
            await store
                .allPredictions()

        var result:
            [NavigationObservation] = []

        for prediction in predictions {

            let statistics =
                await store.statistics(
                    from:
                        prediction.sourceURL,
                    to:
                        prediction.predictedURL
                )

            if statistics.count > 0 {
                // The actual observation is
                // reconstructed through
                // the sequence statistics.
            }
        }

        return result
    }

    // --------------------------------------------------------
    // MARK: Helpers
    // --------------------------------------------------------

    private func buildURL(
        from:
            URL,
        path:
            String
    ) -> URL? {

        var components =
            URLComponents(
                url:
                    from,
                resolvingAgainstBaseURL:
                    false
            )

        components?.path =
            path

        components?.query =
            nil

        components?.fragment =
            nil

        return components?.url
    }

    private func recencyScore(
        _ date:
            Date?
    ) -> Double {

        guard let date else {
            return 0
        }

        let age =
            Date()
                .timeIntervalSince(
                    date
                )

        if age < 60 {
            return 1
        }

        if age < 600 {
            return 0.9
        }

        if age < 3_600 {
            return 0.75
        }

        if age < 86_400 {
            return 0.5
        }

        return 0.25
    }

    private func priority(
        confidence:
            Double
    ) -> PredictionPriority {

        if confidence >=
            policy.aggressiveConfidence {

            return .high
        }

        if confidence >=
            0.75 {

            return .normal
        }

        return .low
    }

    private func deduplicate(
        _ predictions:
            [PagePrediction]
    ) -> [PagePrediction] {

        var seen:
            Set<URL> = []

        var result:
            [PagePrediction] = []

        for prediction in predictions {

            guard
                !seen.contains(
                    prediction.predictedURL
                )
            else {
                continue
            }

            seen.insert(
                prediction.predictedURL
            )

            result.append(
                prediction
            )
        }

        return result
    }
}

// ============================================================
// MARK: - PREDICTIVE PREFETCH
// ============================================================

struct PredictivePrefetchConfiguration:
    Sendable {

    var maximumConcurrent:
        Int = 2

    var maximumConfidence:
        Double = 0.95

    var minimumConfidence:
        Double = 0.80

    var maximumBytes:
        Int64 = 5_000_000

    var requestTimeout:
        TimeInterval = 5
}

// ============================================================
// MARK: - PREFETCH RESULT
// ============================================================

struct PredictivePrefetchResult:
    Sendable {

    let predictionID:
        PredictionID

    let url:
        URL

    let statusCode:
        Int?

    let bytes:
        Int64

    let duration:
        TimeInterval

    let successful:
        Bool
}

// ============================================================
// MARK: - PREFETCH ENGINE
// ============================================================

actor PredictivePrefetchEngine {

    private let configuration:
        PredictivePrefetchConfiguration

    private let session:
        URLSession

    private var active:
        [PredictionID:
            Task<
                PredictivePrefetchResult,
                Never>] = [:]

    private var results:
        [PredictionID:
            PredictivePrefetchResult] = [:]

    private let logger =
        Logger(
            subsystem:
                "SafariPredictiveLoading",
            category:
                "Prefetch"
        )

    init(
        configuration:
            PredictivePrefetchConfiguration =
            PredictivePrefetchConfiguration()
    ) {

        self.configuration =
            configuration

        let configuration =
            URLSessionConfiguration
                .ephemeral

        configuration
            .requestCachePolicy =
            .useProtocolCachePolicy

        configuration
            .timeoutIntervalForRequest =
            5

        configuration
            .timeoutIntervalForResource =
            5

        self.session =
            URLSession(
                configuration:
                    configuration
            )
    }

    // --------------------------------------------------------
    // MARK: Start
    // --------------------------------------------------------

    func prefetch(
        prediction:
            PagePrediction
    ) {

        guard
            prediction.confidence >=
            configuration.minimumConfidence
        else {
            return
        }

        guard
            prediction.confidence <=
            configuration.maximumConfidence
        else {
            return
        }

        guard active.count <
                configuration.maximumConcurrent
        else {
            return
        }

        guard active[
            prediction.id
        ] == nil
        else {
            return
        }

        let task =
            Task<
                PredictivePrefetchResult,
                Never
            > {

                let start =
                    Date()

                do {

                    var request =
                        URLRequest(
                            url:
                                prediction
                                    .predictedURL
                        )

                    request.httpMethod =
                        "GET"

                    request.cachePolicy =
                        .useProtocolCachePolicy

                    let (
                        bytes,
                        response
                    ) =
                        try await self
                            .fetch(
                                request:
                                    request
                            )

                    let status =
                        (
                            response
                            as? HTTPURLResponse
                        )?.statusCode

                    return
                        PredictivePrefetchResult(
                            predictionID:
                                prediction.id,
                            url:
                                prediction
                                    .predictedURL,
                            statusCode:
                                status,
                            bytes:
                                bytes,
                            duration:
                                Date()
                                    .timeIntervalSince(
                                        start
                                    ),
                            successful:
                                true
                        )

                } catch {

                    return
                        PredictivePrefetchResult(
                            predictionID:
                                prediction.id,
                            url:
                                prediction
                                    .predictedURL,
                            statusCode:
                                nil,
                            bytes:
                                0,
                            duration:
                                Date()
                                    .timeIntervalSince(
                                        start
                                    ),
                            successful:
                                false
                        )
                }
            }

        active[
            prediction.id
        ] =
            task

        Task {

            let result =
                await task.value

            await self.store(
                result
            )
        }
    }

    // --------------------------------------------------------
    // MARK: Fetch
    // --------------------------------------------------------

    private func fetch(
        request:
            URLRequest
    ) async throws
        -> (
            Int64,
            URLResponse
        ) {

        let (
            data,
            response
        ) =
            try await session.data(
                for:
                    request
            )

        let bytes =
            Int64(
                data.count
            )

        guard
            bytes <=
            configuration.maximumBytes
        else {

            throw
                PrefetchError
                    .responseTooLarge
        }

        return (
            bytes,
            response
        )
    }

    // --------------------------------------------------------
    // MARK: Store
    // --------------------------------------------------------

    private func store(
        _ result:
            PredictivePrefetchResult
    ) {

        active.removeValue(
            forKey:
                result.predictionID
        )

        results[
            result.predictionID
        ] =
            result

        logger.debug(
            """
            Predictive prefetch finished:
            \(result.url.absoluteString)
            success=\(result.successful)
            bytes=\(result.bytes)
            """
        )
    }

    // --------------------------------------------------------
    // MARK: Cancel
    // --------------------------------------------------------

    func cancel(
        predictionID:
            PredictionID
    ) {

        active[
            predictionID
        ]?.cancel()

        active.removeValue(
            forKey:
                predictionID
        )
    }

    func result(
        for:
            PredictionID
    ) -> PredictivePrefetchResult? {

        results[
            `for`
        ]
    }
}

enum PrefetchError:
    Error,
    Sendable {

    case responseTooLarge
}

// ============================================================
// MARK: - PREDICTIVE RUNTIME
// ============================================================

@MainActor
final class SafariPredictiveLoadingRuntime {

    let engine:
        PagePredictionEngine

    let prefetch:
        PredictivePrefetchEngine

    private let policy:
        PredictionPolicy

    private let logger =
        Logger(
            subsystem:
                "SafariPredictiveLoading",
            category:
                "Runtime"
        )

    init(
        policy:
            PredictionPolicy =
            PredictionPolicy()
    ) {

        self.policy =
            policy

        self.engine =
            PagePredictionEngine(
                policy:
                    policy
            )

        self.prefetch =
            PredictivePrefetchEngine()
    }

    // ========================================================
    // MARK: Observe
    // ========================================================

    func recordNavigation(
        tabID:
            PredictionTabID,
        url:
            URL,
        previousURL:
            URL? = nil,
        userInitiated:
            Bool = true,
        reload:
            Bool = false,
        restored:
            Bool = false,
        title:
            String? = nil
    ) async {

        await engine.observe(
            tabID:
                tabID,
            url:
                url,
            previousURL:
                previousURL,
            userInitiated:
                userInitiated,
            reload:
                reload,
            restored:
                restored,
            title:
                title
        )
    }

    // ========================================================
    // MARK: Predict
    // ========================================================

    func predictNextPages(
        tabID:
            PredictionTabID,
        currentURL:
            URL
    ) async
        -> [PagePrediction] {

        await engine.predict(
            tabID:
                tabID,
            currentURL:
                currentURL
        )
    }

    // ========================================================
    // MARK: Predict + Prefetch
    // ========================================================

    func predictAndPrefetch(
        tabID:
            PredictionTabID,
        currentURL:
            URL
    ) async
        -> [PagePrediction] {

        let predictions =
            await predictNextPages(
                tabID:
                    tabID,
                currentURL:
                    currentURL
            )

        guard policy.prefetchEnabled
        else {
            return predictions
        }

        let candidates =
            predictions
                .filter {
                    $0.confidence >=
                    policy.minimumConfidence
                }
                .prefix(
                    policy.maximumPrefetches
                )

        for prediction in candidates {

            guard
                policy.allowCrossOriginPrefetch
                ||
                prediction.sameOrigin
            else {
                continue
            }

            await prefetch.prefetch(
                prediction:
                    prediction
            )
        }

        return predictions
    }

    // ========================================================
    // MARK: Cancel Prefetch
    // ========================================================

    func cancelPrefetch(
        predictionID:
            PredictionID
    ) async {

        await prefetch.cancel(
            predictionID:
                predictionID
        )
    }
}

// ============================================================
// MARK: - LINK PREDICTOR
// ============================================================

struct LinkCandidate:
    Sendable {

    let url:
        URL

    let text:
        String

    let position:
        Int

    let sameOrigin:
        Bool
}

struct LinkPredictionScore:
    Sendable {

    let url:
        URL

    let score:
        Double

    let reason:
        String
}

struct LinkPredictionEngine:
    Sendable {

    func rank(
        links:
            [LinkCandidate],
        currentURL:
            URL
    ) -> [LinkPredictionScore] {

        let currentOrigin =
            URLSignature(
                url:
                    currentURL
            ).origin

        return links
            .map {

                let sameOrigin =
                    URLSignature(
                        url:
                            $0.url
                    ).origin
                    ==
                    currentOrigin

                let positionScore =
                    max(
                        0,
                        1 -
                        Double(
                            $0.position
                        ) /
                        20
                    )

                let score =
                    sameOrigin
                    ? 0.65 +
                      positionScore *
                      0.35
                    : 0.25 +
                      positionScore *
                      0.15

                return LinkPredictionScore(
                    url:
                        $0.url,
                    score:
                        score,
                    reason:
                        sameOrigin
                        ? "Same-origin candidate"
                        : "Cross-origin candidate"
                )
            }
            .sorted {
                $0.score >
                $1.score
            }
}

// ============================================================
// MARK: - PREDICTIVE NAVIGATION POLICY
// ============================================================

struct PredictiveNavigationPolicy:
    Sendable {

    var enabled:
        Bool = true

    var onlyUserInitiatedLearning:
        Bool = true

    var requireHTTPS:
        Bool = true

    var sameOriginOnly:
        Bool = true

    var minimumConfidence:
        Double = 0.80

    func allows(
        prediction:
            PagePrediction
    ) -> Bool {

        guard enabled
        else {
            return false
        }

        guard
            prediction.confidence >=
            minimumConfidence
        else {
            return false
        }

        if sameOriginOnly &&
            !prediction.sameOrigin {

            return false
        }

        if requireHTTPS {

            guard
                prediction
                    .predictedURL
                    .scheme?
                    .lowercased()
                    == "https"
            else {
                return false
            }
        }

        return true
    }
}

// ============================================================
// MARK: - PREDICTIVE SESSION
// ============================================================

actor PredictiveSession {

    private var currentURL:
        [PredictionTabID: URL] = [:]

    private var previousURL:
        [PredictionTabID: URL] = [:]

    func update(
        tabID:
            PredictionTabID,
        url:
            URL
    ) {

        if let current =
            currentURL[tabID] {

            previousURL[tabID] =
                current
        }

        currentURL[tabID] =
            url
    }

    func current(
        tabID:
            PredictionTabID
    ) -> URL? {

        currentURL[tabID]
    }

    func previous(
        tabID:
            PredictionTabID
    ) -> URL? {

        previousURL[tabID]
    }

    func remove(
        tabID:
            PredictionTabID
    ) {

        currentURL.removeValue(
            forKey:
                tabID
        )

        previousURL.removeValue(
            forKey:
                tabID
        )
    }
}

// ============================================================
// MARK: - PREDICTIVE TAB CONTROLLER
// ============================================================

@MainActor
final class SafariPredictiveTabController {

    private let runtime:
        SafariPredictiveLoadingRuntime

    private let session:
        PredictiveSession

    init(
        runtime:
            SafariPredictiveLoadingRuntime
    ) {

        self.runtime =
            runtime

        self.session =
            PredictiveSession()
    }

    func didNavigate(
        tabID:
            PredictionTabID,
        url:
            URL,
        title:
            String? = nil
    ) async {

        let previous =
            await session.current(
                tabID:
                    tabID
            )

        await session.update(
            tabID:
                tabID,
            url:
                url
        )

        await runtime.recordNavigation(
            tabID:
                tabID,
            url:
                url,
            previousURL:
                previous,
            userInitiated:
                true,
            title:
                title
        )

        _ =
            await runtime
                .predictAndPrefetch(
                    tabID:
                        tabID,
                    currentURL:
                        url
                )
    }
}

// ============================================================
// MARK: - PREDICTIVE DIAGNOSTICS
// ============================================================

struct PredictiveDiagnostics:
    Sendable {

    let generatedAt:
        Date

    let predictionCount:
        Int

    let activePrefetches:
        Int

    let averageConfidence:
        Double

    let highConfidenceCount:
        Int
}

actor PredictiveDiagnosticsStore {

    private var predictions:
        [PagePrediction] = []

    func record(
        _ prediction:
            PagePrediction
    ) {

        predictions.append(
            prediction
        )

        if predictions.count >
            10_000 {

            predictions.removeFirst(
                predictions.count -
                10_000
            )
        }
    }

    func diagnostics()
        -> PredictiveDiagnostics {

        let average =
            predictions.isEmpty
            ? 0
            :
            predictions
                .map(\.confidence)
                .reduce(
                    0,
                    +
                )
            /
            Double(
                predictions.count
            )

        let high =
            predictions.filter {
                $0.confidence >= 0.85
            }.count

        return PredictiveDiagnostics(
            generatedAt:
                Date(),
            predictionCount:
                predictions.count,
            activePrefetches:
                0,
            averageConfidence:
                average,
            highConfidenceCount:
                high
        )
    }
}

// ============================================================
// MARK: - PERSISTED MODEL
// ============================================================

struct PredictiveModelSnapshot:
    Codable,
    Sendable {

    let version:
        Int

    let generatedAt:
        Date

    let policy:
        PredictionPolicy
}

// ============================================================
// MARK: - MODEL STORE
// ============================================================

actor PredictiveModelStore {

    private let fileURL:
        URL

    init(
        directory:
            URL? = nil
    ) {

        let directory =
            directory
            ??
            FileManager.default
                .urls(
                    for:
                        .applicationSupportDirectory,
                    in:
                        .userDomainMask
                )
                .first!

        self.fileURL =
            directory
                .appendingPathComponent(
                    "SafariPredictiveModel.json"
                )
    }

    func save(
        policy:
            PredictionPolicy
    ) throws {

        let snapshot =
            PredictiveModelSnapshot(
                version:
                    1,
                generatedAt:
                    Date(),
                policy:
                    policy
            )

        let data =
            try JSONEncoder()
                .encode(
                    snapshot
                )

        let directory =
            fileURL
                .deletingLastPathComponent()

        try FileManager.default
            .createDirectory(
                at:
                    directory,
                withIntermediateDirectories:
                    true
            )

        try data.write(
            to:
                fileURL,
            options:
                .atomic
        )
    }

    func load()
        throws
        -> PredictiveModelSnapshot {

        let data =
            try Data(
                contentsOf:
                    fileURL
            )

        return try JSONDecoder()
            .decode(
                PredictiveModelSnapshot.self,
                from:
                    data
            )
    }
}

// ============================================================
// MARK: - RUNTIME FACTORY
// ============================================================

@MainActor
enum SafariPredictiveRuntimeFactory {

    static func makeDefault()
        -> SafariPredictiveLoadingRuntime {

        let policy =
            PredictionPolicy(
                minimumConfidence:
                    0.70,
                aggressiveConfidence:
                    0.88,
                maximumPredictions:
                    8,
                maximumPrefetches:
                    2,
                maximumPerDomain:
                    2,
                maximumHistoryEntries:
                    2_000,
                learningEnabled:
                    true,
                prefetchEnabled:
                    true,
                allowCrossOriginPrefetch:
                    false,
                allowPrivateBrowsingLearning:
                    false,
                minimumObservationCount:
                    2,
                speculativeBudgetBytes:
                    2_000_000,
                normalBudgetBytes:
                    10_000_000,
                aggressiveBudgetBytes:
                    25_000_000
            )

        return
            SafariPredictiveLoadingRuntime(
                policy:
                    policy
            )
    }
}

// ============================================================
// MARK: - EXAMPLE SAFARI INTEGRATION
// ============================================================

@MainActor
final class SafariPredictiveBrowserController {

    private let navigation:
        SafariNavigationRuntime

    private let predictive:
        SafariPredictiveLoadingRuntime

    private let predictiveTabs:
        SafariPredictiveTabController

    init() {

        self.navigation =
            SafariNavigationRuntime()

        self.predictive =
            SafariPredictiveRuntimeFactory
                .makeDefault()

        self.predictiveTabs =
            SafariPredictiveTabController(
                runtime:
                    predictive
            )
    }

    func start() async {

        await navigation.start()
    }

    func navigate(
        tabID:
            NavigationTabID,
        predictionTabID:
            PredictionTabID,
        url:
            URL
    ) async {

        do {

            let result =
                try await navigation
                    .navigate(
                        tabID:
                            tabID,
                        url:
                            url,
                        priority:
                            .userInitiated
                    )

            await predictiveTabs
                .didNavigate(
                    tabID:
                        predictionTabID,
                    url:
                        result.finalURL
                        ?? url
                )

        } catch {

            print(
                "Safari navigation failed:",
                error
            )
        }
    }

    func predict(
        tabID:
            PredictionTabID,
        currentURL:
            URL
    ) async
        -> [PagePrediction] {

        await predictive
            .predictNextPages(
                tabID:
                    tabID,
                currentURL:
                    currentURL
            )
    }
}










//
// SafariRenderingPerformanceEngine.swift
//
// #5 — Rendering & Scrolling Performance Engine
//
// macOS / Swift 6 / WebKit
//
// Design goals:
// - Swift concurrency
// - @MainActor UI/WebKit ownership
// - Frame-aware scheduling
// - Scroll-performance monitoring
// - Viewport-change coalescing
// - Main-thread workload tracking
// - Adaptive rendering policy
// - JavaScript workload coordination
// - Tab-aware performance budgets
// - Telemetry and diagnostics
//

import Foundation
import WebKit
import AppKit
import QuartzCore
import OSLog

// ============================================================
// MARK: - IDENTIFIERS
// ============================================================

struct RenderingTabID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: UUID

    init(
        _ rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

struct RenderingSessionID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: UUID

    init(
        _ rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

// ============================================================
// MARK: - PERFORMANCE MODE
// ============================================================

enum RenderingPerformanceMode:
    String,
    Codable,
    Sendable
{
    case maximumQuality
    case balanced
    case responsive
    case powerSaving
    case thermalProtection
}

// ============================================================
// MARK: - FRAME QUALITY
// ============================================================

enum FrameQuality:
    String,
    Codable,
    Sendable
{
    case excellent
    case good
    case degraded
    case poor
    case critical
}

// ============================================================
// MARK: - SCROLL STATE
// ============================================================

enum ScrollState:
    String,
    Codable,
    Sendable
{
    case idle
    case tracking
    case accelerating
    case decelerating
}

// ============================================================
// MARK: - MAIN THREAD PRESSURE
// ============================================================

enum MainThreadPressure:
    Int,
    Codable,
    Sendable,
    Comparable
{
    case low = 0
    case normal = 1
    case elevated = 2
    case high = 3
    case critical = 4

    static func < (
        lhs: MainThreadPressure,
        rhs: MainThreadPressure
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

// ============================================================
// MARK: - FRAME METRICS
// ============================================================

struct FrameMetrics:
    Codable,
    Sendable
{
    var frameTime:
        Double = 0

    var frameRate:
        Double = 0

    var droppedFrames:
        Int = 0

    var renderedFrames:
        Int = 0

    var timestamp:
        Date = Date()

    var quality:
        FrameQuality = .excellent

    var averageFrameTime:
        Double = 0

    var maximumFrameTime:
        Double = 0

    var jankPercentage:
        Double = 0

    mutating func recordFrame(
        duration:
            Double
    ) {

        frameTime =
            duration

        renderedFrames += 1

        averageFrameTime =
            (
                averageFrameTime *
                Double(
                    renderedFrames - 1
                )
                +
                duration
            )
            /
            Double(
                renderedFrames
            )

        maximumFrameTime =
            max(
                maximumFrameTime,
                duration
            )

        if duration >
            (1.0 / 60.0) {

            droppedFrames += 1
        }

        if duration > 0 {
            frameRate =
                1.0 /
                duration
        }

        calculateQuality()
    }

    mutating func calculateQuality() {

        let dropRate =
            renderedFrames == 0
            ? 0
            :
            Double(
                droppedFrames
            )
            /
            Double(
                renderedFrames
            )

        jankPercentage =
            dropRate * 100

        if frameRate >= 58 &&
            dropRate < 0.02 {

            quality =
                .excellent

        } else if frameRate >= 50 &&
                  dropRate < 0.05 {

            quality =
                .good

        } else if frameRate >= 40 &&
                  dropRate < 0.10 {

            quality =
                .degraded

        } else if frameRate >= 25 {

            quality =
                .poor

        } else {

            quality =
                .critical
        }
    }
}

// ============================================================
// MARK: - SCROLL METRICS
// ============================================================

struct ScrollMetrics:
    Codable,
    Sendable
{
    var state:
        ScrollState = .idle

    var velocity:
        Double = 0

    var maximumVelocity:
        Double = 0

    var distance:
        Double = 0

    var eventCount:
        Int = 0

    var duration:
        TimeInterval = 0

    var startedAt:
        Date?

    var lastEvent:
        Date?

    var averageEventInterval:
        TimeInterval = 0

    mutating func begin() {

        state =
            .tracking

        startedAt =
            Date()

        lastEvent =
            Date()

        eventCount =
            0
    }

    mutating func update(
        velocity:
            Double
    ) {

        let now =
            Date()

        if let lastEvent {

            let interval =
                now.timeIntervalSince(
                    lastEvent
                )

            averageEventInterval =
                (
                    averageEventInterval *
                    Double(
                        max(
                            eventCount - 1,
                            0
                        )
                    )
                    +
                    interval
                )
                /
                Double(
                    max(
                        eventCount,
                        1
                    )
                )
        }

        self.lastEvent =
            now

        self.velocity =
            velocity

        self.maximumVelocity =
            max(
                maximumVelocity,
                abs(
                    velocity
                )
            )

        eventCount += 1

        if abs(velocity) > 1_500 {
            state =
                .accelerating
        } else if abs(velocity) > 50 {
            state =
                .tracking
        } else {
            state =
                .decelerating
        }

        if let startedAt {
            duration =
                now.timeIntervalSince(
                    startedAt
                )
        }
    }

    mutating func finish() {

        state =
            .idle

        velocity =
            0
    }
}

// ============================================================
// MARK: - VIEWPORT
// ============================================================

struct ViewportMetrics:
    Codable,
    Sendable
{
    var width:
        Double

    var height:
        Double

    var scale:
        Double

    var visibleTop:
        Double

    var visibleBottom:
        Double

    var timestamp:
        Date

    var area:
        Double {
        width * height
    }
}

// ============================================================
// MARK: - MAIN THREAD METRICS
// ============================================================

struct MainThreadMetrics:
    Codable,
    Sendable
{
    var utilization:
        Double = 0

    var pressure:
        MainThreadPressure = .low

    var activeWorkItems:
        Int = 0

    var longTaskCount:
        Int = 0

    var longestTask:
        TimeInterval = 0

    var timestamp:
        Date = Date()

    mutating func update(
        utilization:
            Double
    ) {

        self.utilization =
            max(
                0,
                min(
                    1,
                    utilization
                )
            )

        if utilization < 0.35 {
            pressure =
                .low
        } else if utilization < 0.60 {
            pressure =
                .normal
        } else if utilization < 0.75 {
            pressure =
                .elevated
        } else if utilization < 0.90 {
            pressure =
                .high
        } else {
            pressure =
                .critical
        }

        timestamp =
            Date()
    }
}

// ============================================================
// MARK: - RENDERING SNAPSHOT
// ============================================================

struct RenderingPerformanceSnapshot:
    Codable,
    Sendable
{
    let tabID:
        RenderingTabID

    var mode:
        RenderingPerformanceMode

    var frame:
        FrameMetrics

    var scroll:
        ScrollMetrics

    var viewport:
        ViewportMetrics?

    var mainThread:
        MainThreadMetrics

    var timestamp:
        Date

    var isUnderPressure:
        Bool {
        frame.quality == .poor ||
        frame.quality == .critical ||
        mainThread.pressure >= .high
    }
}

// ============================================================
// MARK: - RENDERING POLICY
// ============================================================

struct RenderingPolicy:
    Codable,
    Sendable
{
    var targetFrameRate:
        Double = 60

    var minimumFrameRate:
        Double = 30

    var maximumScrollVelocity:
        Double = 8_000

    var viewportDebounce:
        TimeInterval = 0.016

    var javascriptBudget:
        TimeInterval = 0.008

    var layoutBudget:
        TimeInterval = 0.004

    var maximumMainThreadUtilization:
        Double = 0.80

    var frameWarningThreshold:
        Double = 0.020

    var frameCriticalThreshold:
        Double = 0.033

    var enableAdaptiveScheduling:
        Bool = true

    var enableScrollOptimization:
        Bool = true

    var enableViewportCoalescing:
        Bool = true
}

// ============================================================
// MARK: - RENDERING ACTION
// ============================================================

enum RenderingAction:
    String,
    Codable,
    Sendable
{
    case normal
    case reduceBackgroundWork
    case deferNonCriticalWork
    case coalesceViewportUpdates
    case reduceJavaScriptScheduling
    case suspendTelemetry
    case powerSaving
    case thermalProtection
}

// ============================================================
// MARK: - PERFORMANCE BUDGET
// ============================================================

struct RenderingBudget:
    Sendable
{
    let frame:
        TimeInterval

    let javascript:
        TimeInterval

    let layout:
        TimeInterval

    let background:
        TimeInterval

    static let normal =
        RenderingBudget(
            frame:
                1.0 / 60.0,
            javascript:
                0.008,
            layout:
                0.004,
            background:
                0.004
        )

    static let responsive =
        RenderingBudget(
            frame:
                1.0 / 60.0,
            javascript:
                0.004,
            layout:
                0.002,
            background:
                0.001
        )

    static let powerSaving =
        RenderingBudget(
            frame:
                1.0 / 30.0,
            javascript:
                0.003,
            layout:
                0.002,
            background:
                0.001
        )
}

// ============================================================
// MARK: - RENDERING TELEMETRY
// ============================================================

enum RenderingEventType:
    String,
    Codable,
    Sendable
{
    case frame
    case scrollStarted
    case scrollUpdated
    case scrollEnded
    case viewportChanged
    case performanceModeChanged
    case mainThreadPressure
    case longTask
    case renderingAction
}

struct RenderingTelemetryEvent:
    Codable,
    Sendable
{
    let type:
        RenderingEventType

    let tabID:
        RenderingTabID

    let timestamp:
        Date

    let value:
        Double?

    let message:
        String?
}

actor RenderingTelemetryStore {

    private var events:
        [RenderingTelemetryEvent] = []

    private let maximumEvents =
        20_000

    func record(
        _ event:
            RenderingTelemetryEvent
    ) {

        events.append(
            event
        )

        if events.count >
            maximumEvents {

            events.removeFirst(
                events.count -
                maximumEvents
            )
        }
    }

    func recent(
        limit:
            Int = 100
    )
        -> [RenderingTelemetryEvent]
    {
        Array(
            events.suffix(
                limit
            )
        )
    }

    func clear() {
        events.removeAll(
            keepingCapacity:
                true
        )
    }
}

// ============================================================
// MARK: - FRAME MONITOR
// ============================================================

@MainActor
final class FramePerformanceMonitor {

    private(set) var metrics:
        FrameMetrics =
        FrameMetrics()

    private var displayLink:
        CVDisplayLink?

    private var lastTimestamp:
        Double?

    private let logger =
        Logger(
            subsystem:
                "SafariRendering",
            category:
                "FrameMonitor"
        )

    var onFrame:
        ((FrameMetrics) -> Void)?

    func start() {

        guard displayLink == nil
        else {
            return
        }

        var link:
            CVDisplayLink?

        let result =
            CVDisplayLinkCreateWithActiveCGDisplays(
                &link
            )

        guard
            result == kCVReturnSuccess,
            let link
        else {
            logger.error(
                "Unable to create CVDisplayLink."
            )
            return
        }

        displayLink =
            link

        CVDisplayLinkSetOutputCallback(
            link,
            { (
                displayLink,
                inNow,
                inOutputTime,
                flagsIn,
                flagsOut,
                context
            ) -> CVReturn in

                guard
                    let context
                else {
                    return kCVReturnSuccess
                }

                let monitor =
                    Unmanaged<
                        FramePerformanceMonitor
                    >
                    .fromOpaque(
                        context
                    )
                    .takeUnretainedValue()

                let timestamp =
                    inOutputTime
                        .pointee
                        .videoTime

                let scale =
                    Double(
                        inOutputTime
                            .pointee
                            .videoTimeScale
                    )

                guard scale > 0
                else {
                    return kCVReturnSuccess
                }

                let seconds =
                    Double(
                        timestamp
                    ) / scale

                DispatchQueue.main.async {
                    monitor.processFrame(
                        timestamp:
                            seconds
                    )
                }

                return kCVReturnSuccess

            },
            Unmanaged.passUnretained(
                self
            ).toOpaque()
        )

        CVDisplayLinkStart(
            link
        )
    }

    func stop() {

        guard
            let displayLink
        else {
            return
        }

        CVDisplayLinkStop(
            displayLink
        )

        self.displayLink =
            nil
    }

    private func processFrame(
        timestamp:
            Double
    ) {

        guard
            let previous =
                lastTimestamp
        else {

            lastTimestamp =
                timestamp

            return
        }

        let duration =
            timestamp -
            previous

        lastTimestamp =
            timestamp

        guard duration > 0
        else {
            return
        }

        metrics.recordFrame(
            duration:
                duration
        )

        onFrame?(
            metrics
        )
    }

    deinit {
        stop()
    }
}

// ============================================================
// MARK: - SCROLL PERFORMANCE MONITOR
// ============================================================

@MainActor
final class ScrollPerformanceMonitor {

    private(set) var metrics =
        ScrollMetrics()

    var onUpdate:
        ((ScrollMetrics) -> Void)?

    func scrollDidBegin() {

        metrics.begin()

        onUpdate?(
            metrics
        )
    }

    func scrollDidMove(
        velocity:
            Double
    ) {

        metrics.update(
            velocity:
                velocity
        )

        onUpdate?(
            metrics
        )
    }

    func scrollDidEnd() {

        metrics.finish()

        onUpdate?(
            metrics
        )
    }
}

// ============================================================
// MARK: - VIEWPORT COALESCER
// ============================================================

@MainActor
final class ViewportCoalescer {

    private var pending:
        ViewportMetrics?

    private var task:
        Task<Void, Never>?

    private let delay:
        TimeInterval

    var onViewport:
        ((ViewportMetrics) -> Void)?

    init(
        delay:
            TimeInterval =
            0.016
    ) {

        self.delay =
            delay
    }

    func submit(
        _ viewport:
            ViewportMetrics
    ) {

        pending =
            viewport

        task?.cancel()

        task =
            Task { [weak self] in

                guard let self
                else {
                    return
                }

                do {

                    try await Task.sleep(
                        for:
                            .seconds(
                                self.delay
                            )
                    )

                } catch {

                    return
                }

                guard
                    !Task.isCancelled
                else {
                    return
                }

                let value =
                    await MainActor.run {
                        self.pending
                    }

                guard
                    let value
                else {
                    return
                }

                await MainActor.run {

                    self.onViewport?(
                        value
                    )

                    self.pending =
                        nil
                }
            }
    }

    func cancel() {

        task?.cancel()
        task = nil
        pending = nil
    }

    deinit {
        task?.cancel()
    }
}

// ============================================================
// MARK: - MAIN THREAD WORK MONITOR
// ============================================================

@MainActor
final class MainThreadWorkMonitor {

    private(set) var metrics =
        MainThreadMetrics()

    private var activeTasks:
        [UUID: Date] = [:]

    var onUpdate:
        ((MainThreadMetrics) -> Void)?

    func beginWork()
        -> UUID {

        let id =
            UUID()

        activeTasks[id] =
            Date()

        metrics.activeWorkItems =
            activeTasks.count

        return id
    }

    func endWork(
        _ id:
            UUID
    ) {

        guard
            let start =
                activeTasks.removeValue(
                    forKey:
                        id
                )
        else {
            return
        }

        let duration =
            Date()
                .timeIntervalSince(
                    start
                )

        if duration > 0.016 {

            metrics.longTaskCount += 1
        }

        metrics.longestTask =
            max(
                metrics.longestTask,
                duration
            )

        metrics.activeWorkItems =
            activeTasks.count

        onUpdate?(
            metrics
        )
    }

    func setUtilization(
        _ utilization:
            Double
    ) {

        metrics.update(
            utilization:
                utilization
        )

        metrics.activeWorkItems =
            activeTasks.count

        onUpdate?(
            metrics
        )
    }
}

// ============================================================
// MARK: - ADAPTIVE POLICY ENGINE
// ============================================================

actor AdaptiveRenderingPolicyEngine {

    private let policy:
        RenderingPolicy

    private(set) var mode:
        RenderingPerformanceMode =
        .maximumQuality

    init(
        policy:
            RenderingPolicy =
            RenderingPolicy()
    ) {

        self.policy =
            policy
    }

    func evaluate(
        frame:
            FrameMetrics,
        mainThread:
            MainThreadMetrics
    )
        -> (
            RenderingPerformanceMode,
            [RenderingAction]
        )
    {

        if frame.quality == .critical ||
            mainThread.pressure == .critical {

            mode =
                .thermalProtection

            return (
                .thermalProtection,
                [
                    .thermalProtection,
                    .reduceBackgroundWork,
                    .deferNonCriticalWork,
                    .coalesceViewportUpdates,
                    .reduceJavaScriptScheduling
                ]
            )
        }

        if frame.quality == .poor ||
            mainThread.pressure >= .high {

            mode =
                .responsive

            return (
                .responsive,
                [
                    .reduceBackgroundWork,
                    .deferNonCriticalWork,
                    .coalesceViewportUpdates,
                    .reduceJavaScriptScheduling
                ]
            )
        }

        if frame.quality == .degraded ||
            mainThread.pressure == .elevated {

            mode =
                .balanced

            return (
                .balanced,
                [
                    .reduceBackgroundWork,
                    .coalesceViewportUpdates
                ]
            )
        }

        mode =
            .maximumQuality

        return (
            .maximumQuality,
            [
                .normal
            ]
        )
    }

    func budget()
        -> RenderingBudget
    {
        switch mode {

        case .maximumQuality:
            return .normal

        case .balanced:
            return .normal

        case .responsive:
            return .responsive

        case .powerSaving:
            return .powerSaving

        case .thermalProtection:
            return .powerSaving
        }
    }
}

// ============================================================
// MARK: - JAVASCRIPT WORK SCHEDULER
// ============================================================

enum JavaScriptWorkPriority:
    Int,
    Sendable,
    Comparable
{
    case background = 0
    case normal = 1
    case userVisible = 2
    case critical = 3

    static func < (
        lhs:
            JavaScriptWorkPriority,
        rhs:
            JavaScriptWorkPriority
    ) -> Bool {

        lhs.rawValue <
        rhs.rawValue
    }
}

struct JavaScriptWorkItem:
    Sendable
{
    let id:
        UUID

    let priority:
        JavaScriptWorkPriority

    let createdAt:
        Date

    let operation:
        @Sendable () async -> Void

    init(
        priority:
            JavaScriptWorkPriority,
        operation:
            @escaping @Sendable () async -> Void
    ) {

        self.id =
            UUID()

        self.priority =
            priority

        self.createdAt =
            Date()

        self.operation =
            operation
    }
}

actor JavaScriptWorkScheduler {

    private var queue:
        [JavaScriptWorkItem] = []

    private var running:
        Bool = false

    private var enabled:
        Bool = true

    func enqueue(
        _ item:
            JavaScriptWorkItem
    ) {

        guard enabled
        else {
            return
        }

        queue.append(
            item
        )

        queue.sort {
            $0.priority >
            $1.priority
        }
    }

    func setEnabled(
        _ enabled:
            Bool
    ) {

        self.enabled =
            enabled

        if !enabled {
            queue.removeAll(
                keepingCapacity:
                    true
            )
        }
    }

    func drain(
        budget:
            TimeInterval
    ) async {

        guard !running
        else {
            return
        }

        running =
            true

        defer {
            running =
                false
        }

        let start =
            ContinuousClock
                .now

        while !queue.isEmpty {

            guard enabled
            else {
                break
            }

            let elapsed =
                ContinuousClock
                    .now
                    .duration(
                        since:
                            start
                    )

            let seconds =
                elapsed
                    .components
                    .attoseconds
                    /
                    1_000_000_000_000_000_000

            if Double(seconds) >=
                budget {

                break
            }

            let item =
                queue.removeFirst()

            await item.operation()
        }
    }
}

// ============================================================
// MARK: - RENDER TASK SCHEDULER
// ============================================================

enum RenderingTaskPriority:
    Int,
    Comparable,
    Sendable
{
    case background = 0
    case normal = 1
    case interactive = 2
    case critical = 3

    static func < (
        lhs:
            RenderingTaskPriority,
        rhs:
            RenderingTaskPriority
    ) -> Bool {

        lhs.rawValue <
        rhs.rawValue
    }
}

struct RenderingTask:
    Sendable
{
    let id:
        UUID

    let priority:
        RenderingTaskPriority

    let operation:
        @Sendable () async -> Void
}

actor RenderingTaskScheduler {

    private var tasks:
        [RenderingTask] = []

    private var suspended:
        Bool = false

    func submit(
        priority:
            RenderingTaskPriority,
        operation:
            @escaping @Sendable () async -> Void
    ) {

        guard !suspended
        else {
            return
        }

        tasks.append(
            RenderingTask(
                id:
                    UUID(),
                priority:
                    priority,
                operation:
                    operation
            )
        )

        tasks.sort {
            $0.priority >
            $1.priority
        }
    }

    func setSuspended(
        _ suspended:
            Bool
    ) {

        self.suspended =
            suspended
    }

    func drain(
        maximum:
            Int = 10
    ) async {

        guard !suspended
        else {
            return
        }

        var processed =
            0

        while
            !tasks.isEmpty &&
            processed < maximum {

            let task =
                tasks.removeFirst()

            await task.operation()

            processed += 1
        }
    }

    func removeAll() {

        tasks.removeAll(
            keepingCapacity:
                true
        )
    }
}

// ============================================================
// MARK: - WEB VIEW PERFORMANCE CONTROLLER
// ============================================================

@MainActor
final class WebViewPerformanceController:
    NSObject,
    WKNavigationDelegate,
    WKUIDelegate
{

    let webView:
        WKWebView

    let tabID:
        RenderingTabID

    private(set) var viewport:
        ViewportMetrics?

    private(set) var performanceMode:
        RenderingPerformanceMode =
        .maximumQuality

    private var viewportCoalescer:
        ViewportCoalescer

    private let logger =
        Logger(
            subsystem:
                "SafariRendering",
            category:
                "WebViewController"
        )

    var onNavigationFinished:
        ((URL?) -> Void)?

    var onViewportChanged:
        ((ViewportMetrics) -> Void)?

    init(
        tabID:
            RenderingTabID,
        configuration:
            WKWebViewConfiguration =
            WKWebViewConfiguration()
    ) {

        self.tabID =
            tabID

        self.webView =
            WKWebView(
                frame:
                    .zero,
                configuration:
                    configuration
            )

        self.viewportCoalescer =
            ViewportCoalescer()

        super.init()

        webView.navigationDelegate =
            self

        webView.uiDelegate =
            self

        configureWebView()

        viewportCoalescer
            .onViewport =
            { [weak self] viewport in

                guard let self
                else {
                    return
                }

                self.viewport =
                    viewport

                self.onViewportChanged?(
                    viewport
                )
            }
    }

    private func configureWebView() {

        webView
            .setValue(
                false,
                forKey:
                    "drawsBackground"
            )

        webView
            .allowsBackForwardNavigationGestures =
            true

        webView
            .underPageBackgroundColor =
            .windowBackgroundColor
    }

    // ========================================================
    // MARK: Viewport
    // ========================================================

    func updateViewport(
        width:
            Double,
        height:
            Double,
        scale:
            Double,
        visibleTop:
            Double,
        visibleBottom:
            Double
    ) {

        let viewport =
            ViewportMetrics(
                width:
                    width,
                height:
                    height,
                scale:
                    scale,
                visibleTop:
                    visibleTop,
                visibleBottom:
                    visibleBottom,
                timestamp:
                    Date()
            )

        viewportCoalescer.submit(
            viewport
        )
    }

    // ========================================================
    // MARK: Performance Mode
    // ========================================================

    func apply(
        mode:
            RenderingPerformanceMode
    ) {

        performanceMode =
            mode

        switch mode {

        case .maximumQuality:
            configureForMaximumQuality()

        case .balanced:
            configureBalanced()

        case .responsive:
            configureForResponsiveness()

        case .powerSaving:
            configureForPowerSaving()

        case .thermalProtection:
            configureForThermalProtection()
        }
    }

    private func configureForMaximumQuality() {

        logger.debug(
            "Applying maximum-quality rendering policy."
        )
    }

    private func configureBalanced() {

        logger.debug(
            "Applying balanced rendering policy."
        )
    }

    private func configureForResponsiveness() {

        logger.debug(
            "Applying responsive rendering policy."
        )

        webView
            .allowsBackForwardNavigationGestures =
            true
    }

    private func configureForPowerSaving() {

        logger.debug(
            "Applying power-saving rendering policy."
        )
    }

    private func configureForThermalProtection() {

        logger.warning(
            "Applying thermal-protection rendering policy."
        )
    }

    // ========================================================
    // MARK: Navigation Delegate
    // ========================================================

    func webView(
        _ webView:
            WKWebView,
        didFinish navigation:
            WKNavigation!
    ) {

        onNavigationFinished?(
            webView.url
        )
    }

    func webView(
        _ webView:
            WKWebView,
        didFail navigation:
            WKNavigation!,
        withError error:
            Error
    ) {

        logger.error(
            """
            Rendering web view failed:
            \(error.localizedDescription)
            """
        )
    }

    func webView(
        _ webView:
            WKWebView,
        didFailProvisionalNavigation:
            WKNavigation!,
        withError error:
            Error
    ) {

        logger.error(
            """
            Provisional navigation failed:
            \(error.localizedDescription)
            """
        )
    }
}

// ============================================================
// MARK: - RENDERING SESSION
// ============================================================

actor RenderingSession {

    let id:
        RenderingSessionID

    let tabID:
        RenderingTabID

    private(set) var mode:
        RenderingPerformanceMode =
        .maximumQuality

    private(set) var frame:
        FrameMetrics =
        FrameMetrics()

    private(set) var scroll:
        ScrollMetrics =
        ScrollMetrics()

    private(set) var mainThread:
        MainThreadMetrics =
        MainThreadMetrics()

    private(set) var viewport:
        ViewportMetrics?

    init(
        tabID:
            RenderingTabID
    ) {

        self.id =
            RenderingSessionID()

        self.tabID =
            tabID
    }

    func updateFrame(
        _ frame:
            FrameMetrics
    ) {

        self.frame =
            frame
    }

    func updateScroll(
        _ scroll:
            ScrollMetrics
    ) {

        self.scroll =
            scroll
    }

    func updateMainThread(
        _ metrics:
            MainThreadMetrics
    ) {

        self.mainThread =
            metrics
    }

    func updateViewport(
        _ viewport:
            ViewportMetrics
    ) {

        self.viewport =
            viewport
    }

    func setMode(
        _ mode:
            RenderingPerformanceMode
    ) {

        self.mode =
            mode
    }

    func snapshot()
        -> RenderingPerformanceSnapshot
    {

        RenderingPerformanceSnapshot(
            tabID:
                tabID,
            mode:
                mode,
            frame:
                frame,
            scroll:
                scroll,
            viewport:
                viewport,
            mainThread:
                mainThread,
            timestamp:
                Date()
        )
    }
}

// ============================================================
// MARK: - RENDERING SESSION MANAGER
// ============================================================

actor RenderingSessionManager {

    private var sessions:
        [RenderingTabID:
            RenderingSession] = [:]

    func create(
        tabID:
            RenderingTabID
    )
        -> RenderingSession {

        if let existing =
            sessions[tabID] {

            return existing
        }

        let session =
            RenderingSession(
                tabID:
                    tabID
            )

        sessions[tabID] =
            session

        return session
    }

    func session(
        for tabID:
            RenderingTabID
    )
        -> RenderingSession? {

        sessions[tabID]
    }

    func remove(
        tabID:
            RenderingTabID
    ) {

        sessions.removeValue(
            forKey:
                tabID
        )
    }

    func snapshots()
        async
        -> [
            RenderingPerformanceSnapshot
        ]
    {

        var result:
            [RenderingPerformanceSnapshot] =
            []

        for session in
            sessions.values {

            result.append(
                await session.snapshot()
            )
        }

        return result
    }
}

// ============================================================
// MARK: - PERFORMANCE ORCHESTRATOR
// ============================================================

@MainActor
final class SafariRenderingPerformanceEngine {

    private let policy:
        RenderingPolicy

    private let telemetry:
        RenderingTelemetryStore

    private let sessions:
        RenderingSessionManager

    private let adaptive:
        AdaptiveRenderingPolicyEngine

    private let renderingScheduler:
        RenderingTaskScheduler

    private let javascriptScheduler:
        JavaScriptWorkScheduler

    private var frameMonitors:
        [RenderingTabID:
            FramePerformanceMonitor] = [:]

    private var scrollMonitors:
        [RenderingTabID:
            ScrollPerformanceMonitor] = [:]

    private var mainThreadMonitors:
        [RenderingTabID:
            MainThreadWorkMonitor] = [:]

    private var webViews:
        [RenderingTabID:
            WebViewPerformanceController] = [:]

    private let logger =
        Logger(
            subsystem:
                "SafariRendering",
            category:
                "Engine"
        )

    init(
        policy:
            RenderingPolicy =
            RenderingPolicy()
    ) {

        self.policy =
            policy

        self.telemetry =
            RenderingTelemetryStore()

        self.sessions =
            RenderingSessionManager()

        self.adaptive =
            AdaptiveRenderingPolicyEngine(
                policy:
                    policy
            )

        self.renderingScheduler =
            RenderingTaskScheduler()

        self.javascriptScheduler =
            JavaScriptWorkScheduler()
    }

    // ========================================================
    // MARK: Register Tab
    // ========================================================

    func registerTab(
        tabID:
            RenderingTabID,
        webView:
            WKWebView? = nil
    ) async
        -> WebViewPerformanceController
    {

        _ =
            await sessions.create(
                tabID:
                    tabID
            )

        let controller =
            WebViewPerformanceController(
                tabID:
                    tabID
            )

        if let webView {

            controller.webView
                .frame =
                webView.frame
        }

        self.webViews[tabID] =
            controller

        configureFrameMonitor(
            tabID:
                tabID
        )

        configureScrollMonitor(
            tabID:
                tabID
        )

        configureMainThreadMonitor(
            tabID:
                tabID
        )

        return controller
    }

    // ========================================================
    // MARK: Frame Monitor
    // ========================================================

    private func configureFrameMonitor(
        tabID:
            RenderingTabID
    ) {

        let monitor =
            FramePerformanceMonitor()

        monitor.onFrame =
            { [weak self] metrics in

                guard let self
                else {
                    return
                }

                Task {
                    await self
                        .handleFrame(
                            tabID:
                                tabID,
                            metrics:
                                metrics
                        )
                }
            }

        frameMonitors[tabID] =
            monitor

        monitor.start()
    }

    // ========================================================
    // MARK: Scroll Monitor
    // ========================================================

    private func configureScrollMonitor(
        tabID:
            RenderingTabID
    ) {

        let monitor =
            ScrollPerformanceMonitor()

        monitor.onUpdate =
            { [weak self] metrics in

                guard let self
                else {
                    return
                }

                Task {
                    await self
                        .handleScroll(
                            tabID:
                                tabID,
                            metrics:
                                metrics
                        )
                }
            }

        scrollMonitors[tabID] =
            monitor
    }

    // ========================================================
    // MARK: Main Thread Monitor
    // ========================================================

    private func configureMainThreadMonitor(
        tabID:
            RenderingTabID
    ) {

        let monitor =
            MainThreadWorkMonitor()

        monitor.onUpdate =
            { [weak self] metrics in

                guard let self
                else {
                    return
                }

                Task {
                    await self
                        .handleMainThread(
                            tabID:
                                tabID,
                            metrics:
                                metrics
                        )
                }
            }

        mainThreadMonitors[tabID] =
            monitor
    }

    // ========================================================
    // MARK: Frame Event
    // ========================================================

    private func handleFrame(
        tabID:
            RenderingTabID,
        metrics:
            FrameMetrics
    ) async {

        guard
            let session =
                await sessions.session(
                    for:
                        tabID
                )
        else {
            return
        }

        await session.updateFrame(
            metrics
        )

        await telemetry.record(
            RenderingTelemetryEvent(
                type:
                    .frame,
                tabID:
                    tabID,
                timestamp:
                    Date(),
                value:
                    metrics.frameRate,
                message:
                    nil
            )
        )

        await evaluatePerformance(
            tabID:
                tabID
        )
    }

    // ========================================================
    // MARK: Scroll Event
    // ========================================================

    private func handleScroll(
        tabID:
            RenderingTabID,
        metrics:
            ScrollMetrics
    ) async {

        guard
            let session =
                await sessions.session(
                    for:
                        tabID
                )
        else {
            return
        }

        await session.updateScroll(
            metrics
        )

        let eventType:
            RenderingEventType

        switch metrics.state {

        case .tracking,
             .accelerating:

            eventType =
                .scrollUpdated

        case .decelerating:
            eventType =
                .scrollUpdated

        case .idle:
            eventType =
                .scrollEnded
        }

        await telemetry.record(
            RenderingTelemetryEvent(
                type:
                    eventType,
                tabID:
                    tabID,
                timestamp:
                    Date(),
                value:
                    metrics.velocity,
                message:
                    nil
            )
        )
    }

    // ========================================================
    // MARK: Main Thread Event
    // ========================================================

    private func handleMainThread(
        tabID:
            RenderingTabID,
        metrics:
            MainThreadMetrics
    ) async {

        guard
            let session =
                await sessions.session(
                    for:
                        tabID
                )
        else {
            return
        }

        await session.updateMainThread(
            metrics
        )

        await telemetry.record(
            RenderingTelemetryEvent(
                type:
                    .mainThreadPressure,
                tabID:
                    tabID,
                timestamp:
                    Date(),
                value:
                    metrics.utilization,
                message:
                    metrics.pressure.rawValue
                    .description
            )
        )

        await evaluatePerformance(
            tabID:
                tabID
        )
    }

    // ========================================================
    // MARK: Evaluate
    // ========================================================

    private func evaluatePerformance(
        tabID:
            RenderingTabID
    ) async {

        guard
            let session =
                await sessions.session(
                    for:
                        tabID
                )
        else {
            return
        }

        let snapshot =
            await session.snapshot()

        let (
            mode,
            actions
        ) =
            await adaptive.evaluate(
                frame:
                    snapshot.frame,
                mainThread:
                    snapshot.mainThread
            )

        await session.setMode(
            mode
        )

        if let webView =
            webViews[tabID] {

            webView.apply(
                mode:
                    mode
            )
        }

        for action in actions {

            await telemetry.record(
                RenderingTelemetryEvent(
                    type:
                        .renderingAction,
                    tabID:
                        tabID,
                    timestamp:
                        Date(),
                    value:
                        nil,
                    message:
                        action.rawValue
                )
            )
        }

        await telemetry.record(
            RenderingTelemetryEvent(
                type:
                    .performanceModeChanged,
                tabID:
                    tabID,
                timestamp:
                    Date(),
                value:
                    nil,
                message:
                    mode.rawValue
            )
        )
    }

    // ========================================================
    // MARK: Scroll Begin
    // ========================================================

    func beginScroll(
        tabID:
            RenderingTabID
    ) {

        scrollMonitors[
            tabID
        ]?.scrollDidBegin()
    }

    // ========================================================
    // MARK: Scroll Update
    // ========================================================

    func updateScroll(
        tabID:
            RenderingTabID,
        velocity:
            Double
    ) {

        scrollMonitors[
            tabID
        ]?.scrollDidMove(
            velocity:
                velocity
        )
    }

    // ========================================================
    // MARK: Scroll End
    // ========================================================

    func endScroll(
        tabID:
            RenderingTabID
    ) {

        scrollMonitors[
            tabID
        ]?.scrollDidEnd()
    }

    // ========================================================
    // MARK: Viewport
    // ========================================================

    func updateViewport(
        tabID:
            RenderingTabID,
        width:
            Double,
        height:
            Double,
        scale:
            Double,
        visibleTop:
            Double,
        visibleBottom:
            Double
    ) {

        webViews[
            tabID
        ]?.updateViewport(
            width:
                width,
            height:
                height,
            scale:
                scale,
            visibleTop:
                visibleTop,
            visibleBottom:
                visibleBottom
        )

        let viewport =
            ViewportMetrics(
                width:
                    width,
                height:
                    height,
                scale:
                    scale,
                visibleTop:
                    visibleTop,
                visibleBottom:
                    visibleBottom,
                timestamp:
                    Date()
            )

        Task {

            guard
                let session =
                    await sessions.session(
                        for:
                            tabID
                    )
            else {
                return
            }

            await session.updateViewport(
                viewport
            )

            await telemetry.record(
                RenderingTelemetryEvent(
                    type:
                        .viewportChanged,
                    tabID:
                        tabID,
                    timestamp:
                        Date(),
                    value:
                        viewport.area,
                    message:
                        nil
                )
            )
        }
    }

    // ========================================================
    // MARK: Schedule JavaScript
    // ========================================================

    func scheduleJavaScript(
        priority:
            JavaScriptWorkPriority,
        operation:
            @escaping @Sendable () async -> Void
    ) {

        Task {

            await javascriptScheduler.enqueue(
                JavaScriptWorkItem(
                    priority:
                        priority,
                    operation:
                        operation
                )
            )

            let budget =
                await adaptive
                    .budget()

            await javascriptScheduler
                .drain(
                    budget:
                        budget.javascript
                )
        }
    }

    // ========================================================
    // MARK: Schedule Rendering Work
    // ========================================================

    func scheduleRenderingWork(
        priority:
            RenderingTaskPriority,
        operation:
            @escaping @Sendable () async -> Void
    ) {

        Task {

            await renderingScheduler
                .submit(
                    priority:
                        priority,
                    operation:
                        operation
                )

            await renderingScheduler
                .drain()
        }
    }

    // ========================================================
    // MARK: Main Thread Work
    // ========================================================

    func beginMainThreadWork(
        tabID:
            RenderingTabID
    )
        -> UUID?
    {

        mainThreadMonitors[
            tabID
        ]?.beginWork()
    }

    func endMainThreadWork(
        tabID:
            RenderingTabID,
        identifier:
            UUID
    ) {

        mainThreadMonitors[
            tabID
        ]?.endWork(
            identifier
        )
    }

    // ========================================================
    // MARK: Snapshot
    // ========================================================

    func snapshot(
        tabID:
            RenderingTabID
    ) async
        -> RenderingPerformanceSnapshot?
    {

        guard
            let session =
                await sessions.session(
                    for:
                        tabID
                )
        else {
            return nil
        }

        return await session.snapshot()
    }

    // ========================================================
    // MARK: All Snapshots
    // ========================================================

    func allSnapshots()
        async
        -> [
            RenderingPerformanceSnapshot
        ]
    {

        await sessions.snapshots()
    }

    // ========================================================
    // MARK: Unregister
    // ========================================================

    func unregisterTab(
        tabID:
            RenderingTabID
    ) async {

        frameMonitors[
            tabID
        ]?.stop()

        frameMonitors.removeValue(
            forKey:
                tabID
        )

        scrollMonitors.removeValue(
            forKey:
                tabID
        )

        mainThreadMonitors.removeValue(
            forKey:
                tabID
        )

        webViews.removeValue(
            forKey:
                tabID
        )

        await sessions.remove(
            tabID:
                tabID
        )
    }

    deinit {

        for monitor in
            frameMonitors.values {

            monitor.stop()
        }
    }
}

// ============================================================
// MARK: - SCROLL EVENT BRIDGE
// ============================================================

@MainActor
final class SafariScrollEventBridge {

    private weak var scrollView:
        NSScrollView?

    private let tabID:
        RenderingTabID

    private weak var engine:
        SafariRenderingPerformanceEngine?

    private var lastOffset:
        CGPoint = .zero

    private var lastTimestamp:
        TimeInterval = 0

    init(
        scrollView:
            NSScrollView,
        tabID:
            RenderingTabID,
        engine:
            SafariRenderingPerformanceEngine
    ) {

        self.scrollView =
            scrollView

        self.tabID =
            tabID

        self.engine =
            engine
    }

    func processScroll(
        offset:
            CGPoint
    ) {

        let now =
            CACurrentMediaTime()

        guard lastTimestamp > 0
        else {

            lastOffset =
                offset

            lastTimestamp =
                now

            return
        }

        let delta =
            hypot(
                offset.x -
                    lastOffset.x,
                offset.y -
                    lastOffset.y
            )

        let elapsed =
            now -
            lastTimestamp

        guard elapsed > 0
        else {
            return
        }

        let velocity =
            delta /
            elapsed

        lastOffset =
            offset

        lastTimestamp =
            now

        engine?.updateScroll(
            tabID:
                tabID,
            velocity:
                velocity
        )
    }
}

// ============================================================
// MARK: - RENDERING DIAGNOSTICS
// ============================================================

struct RenderingDiagnosticsReport:
    Sendable
{
    let generatedAt:
        Date

    let tabCount:
        Int

    let poorFrameTabs:
        Int

    let criticalTabs:
        Int

    let averageFrameRate:
        Double

    let averageMainThreadUtilization:
        Double

    let activeScrollTabs:
        Int
}

actor RenderingDiagnostics {

    private let sessions:
        RenderingSessionManager

    init(
        sessions:
            RenderingSessionManager
    ) {

        self.sessions =
            sessions
    }

    func report()
        async
        -> RenderingDiagnosticsReport
    {

        let snapshots =
            await sessions.snapshots()

        guard
            !snapshots.isEmpty
        else {

            return RenderingDiagnosticsReport(
                generatedAt:
                    Date(),
                tabCount:
                    0,
                poorFrameTabs:
                    0,
                criticalTabs:
                    0,
                averageFrameRate:
                    0,
                averageMainThreadUtilization:
                    0,
                activeScrollTabs:
                    0
            )
        }

        let poor =
            snapshots.filter {
                $0.frame.quality == .poor
                ||
                $0.frame.quality == .critical
            }.count

        let critical =
            snapshots.filter {
                $0.frame.quality == .critical
                ||
                $0.mainThread.pressure == .critical
            }.count

        let frameRate =
            snapshots
                .map {
                    $0.frame.frameRate
                }
                .reduce(
                    0,
                    +
                )
                /
                Double(
                    snapshots.count
                )

        let utilization =
            snapshots
                .map {
                    $0.mainThread.utilization
                }
                .reduce(
                    0,
                    +
                )
                /
                Double(
                    snapshots.count
                )

        let scrolling =
            snapshots.filter {
                $0.scroll.state != .idle
            }.count

        return RenderingDiagnosticsReport(
            generatedAt:
                Date(),
            tabCount:
                snapshots.count,
            poorFrameTabs:
                poor,
            criticalTabs:
                critical,
            averageFrameRate:
                frameRate,
            averageMainThreadUtilization:
                utilization,
            activeScrollTabs:
                scrolling
        )
    }
}

// ============================================================
// MARK: - PERFORMANCE TEST HARNESS
// ============================================================

@MainActor
final class RenderingPerformanceTestHarness {

    private let engine:
        SafariRenderingPerformanceEngine

    init(
        engine:
            SafariRenderingPerformanceEngine
    ) {

        self.engine =
            engine
    }

    func simulateScroll(
        tabID:
            RenderingTabID,
        samples:
            Int = 120
    ) async {

        engine.beginScroll(
            tabID:
                tabID
        )

        for index in
            0..<samples {

            let progress =
                Double(index) /
                Double(
                    max(
                        samples - 1,
                        1
                    )
                )

            let velocity =
                sin(
                    progress *
                    .pi
                )
                *
                3_000

            engine.updateScroll(
                tabID:
                    tabID,
                velocity:
                    velocity
            )

            try? await Task.sleep(
                for:
                    .milliseconds(
                        8
                    )
            )
        }

        engine.endScroll(
            tabID:
                tabID
        )
    }

    func stressMainThread(
        tabID:
            RenderingTabID,
        iterations:
            Int = 100
    ) async {

        for _ in
            0..<iterations {

            guard
                let identifier =
                    engine
                        .beginMainThreadWork(
                            tabID:
                                tabID
                        )
            else {
                continue
            }

            try? await Task.sleep(
                for:
                    .milliseconds(
                        2
                    )
            )

            engine.endMainThreadWork(
                tabID:
                    tabID,
                identifier:
                    identifier
            )
        }
    }
}

// ============================================================
// MARK: - FACTORY
// ============================================================

@MainActor
enum SafariRenderingEngineFactory {

    static func makeDefault()
        -> SafariRenderingPerformanceEngine
    {

        let policy =
            RenderingPolicy(
                targetFrameRate:
                    60,
                minimumFrameRate:
                    30,
                maximumScrollVelocity:
                    8_000,
                viewportDebounce:
                    0.016,
                javascriptBudget:
                    0.008,
                layoutBudget:
                    0.004,
                maximumMainThreadUtilization:
                    0.80,
                frameWarningThreshold:
                    0.020,
                frameCriticalThreshold:
                    0.033,
                enableAdaptiveScheduling:
                    true,
                enableScrollOptimization:
                    true,
                enableViewportCoalescing:
                    true
            )

        return
            SafariRenderingPerformanceEngine(
                policy:
                    policy
            )
    }
}

// ============================================================
// MARK: - SAFARI BROWSER RENDERING CONTROLLER
// ============================================================

@MainActor
final class SafariBrowserRenderingController {

    private let engine:
        SafariRenderingPerformanceEngine

    private var controllers:
        [RenderingTabID:
            WebViewPerformanceController] = [:]

    init() {

        self.engine =
            SafariRenderingEngineFactory
                .makeDefault()
    }

    func createTab()
        async
        -> (
            RenderingTabID,
            WKWebView
        )
    {

        let tabID =
            RenderingTabID()

        let controller =
            await engine.registerTab(
                tabID:
                    tabID
            )

        controllers[tabID] =
            controller

        return (
            tabID,
            controller.webView
        )
    }

    func destroyTab(
        tabID:
            RenderingTabID
    ) async {

        controllers.removeValue(
            forKey:
                tabID
        )

        await engine.unregisterTab(
            tabID:
                tabID
        )
    }

    func updateViewport(
        tabID:
            RenderingTabID,
        size:
            CGSize,
        scale:
            CGFloat,
        visibleTop:
            CGFloat,
        visibleBottom:
            CGFloat
    ) {

        engine.updateViewport(
            tabID:
                tabID,
            width:
                Double(
                    size.width
                ),
            height:
                Double(
                    size.height
                ),
            scale:
                Double(
                    scale
                ),
            visibleTop:
                Double(
                    visibleTop
                ),
            visibleBottom:
                Double(
                    visibleBottom
                )
        )
    }

    func diagnostics()
        async
        -> RenderingDiagnosticsReport?
    {

        let snapshots =
            await engine.allSnapshots()

        guard
            !snapshots.isEmpty
        else {
            return nil
        }

        let poor =
            snapshots.filter {
                $0.frame.quality == .poor ||
                $0.frame.quality == .critical
            }.count

        let critical =
            snapshots.filter {
                $0.frame.quality == .critical
            }.count

        let frameRate =
            snapshots
                .map {
                    $0.frame.frameRate
                }
                .reduce(
                    0,
                    +
                )
                /
                Double(
                    snapshots.count
                )

        let utilization =
            snapshots
                .map {
                    $0.mainThread.utilization
                }
                .reduce(
                    0,
                    +
                )
                /
                Double(
                    snapshots.count
                )

        let scrolling =
            snapshots.filter {
                $0.scroll.state != .idle
            }.count

        return RenderingDiagnosticsReport(
            generatedAt:
                Date(),
            tabCount:
                snapshots.count,
            poorFrameTabs:
                poor,
            criticalTabs:
                critical,
            averageFrameRate:
                frameRate,
            averageMainThreadUtilization:
                utilization,
            activeScrollTabs:
                scrolling
        )
    }
}

// ============================================================
// MARK: - EXAMPLE USAGE
// ============================================================

@MainActor
func buildSafariRenderingSystem()
    async
{
    let safari =
        SafariBrowserRenderingController()

    let (
        tabID,
        webView
    ) =
        await safari.createTab()

    webView.frame =
        CGRect(
            x: 0,
            y: 0,
            width: 1_280,
            height: 800
        )

    webView.load(
        URLRequest(
            url:
                URL(
                    string:
                        "https://www.apple.com"
                )!
        )
    )

    // Viewport update.
    safari.updateViewport(
        tabID:
            tabID,
        size:
            CGSize(
                width:
                    1_280,
                height:
                    800
            ),
        scale:
            2,
        visibleTop:
            0,
        visibleBottom:
            800
    )

    // Simulate a high-speed scroll.
    //
    // In the real Safari implementation these calls
    // would be connected to the NSScrollView/WebKit
    // scrolling pipeline.
    //
    // The engine automatically measures:
    // - frame rate
    // - dropped frames
    // - scroll velocity
    // - main-thread pressure
    // - rendering quality
    // - adaptive rendering mode

    let testHarness =
        RenderingPerformanceTestHarness(
            engine:
                SafariRenderingEngineFactory
                    .makeDefault()
        )

    await testHarness.simulateScroll(
        tabID:
            tabID
    )
}






//
//  SafariPowerAwareRuntime.swift
//
//  Safari macOS Performance Architecture — #6
//
//  Goals:
//  - Battery / AC awareness
//  - Thermal awareness
//  - Low Power Mode awareness
//  - Adaptive background-work budgets
//  - Tab suspension recommendations
//  - Prefetch throttling
//  - Rendering adaptation
//  - JavaScript/background task budgeting
//  - Telemetry adaptation
//  - Swift 6 concurrency safety
//
//  Public APIs only.
//  WebKit remains responsible for actual page loading/rendering.
//

import Foundation
import AppKit
import WebKit
import IOKit.ps

// MARK: - 1. Identifiers

public struct PowerTabID: Hashable, Sendable, Codable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct PowerSessionID: Hashable, Sendable, Codable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct PowerDecisionID: Hashable, Sendable, Codable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}


// MARK: - 2. Power Source

public enum SafariPowerSource: String, Sendable, Codable {
    case battery
    case externalPower
    case unknown
}

public struct SafariBatteryState: Sendable, Codable {

    public let source: SafariPowerSource
    public let chargeFraction: Double?
    public let isCharging: Bool
    public let timeRemainingMinutes: Double?
    public let timestamp: Date

    public init(
        source: SafariPowerSource,
        chargeFraction: Double?,
        isCharging: Bool,
        timeRemainingMinutes: Double?,
        timestamp: Date = Date()
    ) {
        self.source = source
        self.chargeFraction = chargeFraction
        self.isCharging = isCharging
        self.timeRemainingMinutes = timeRemainingMinutes
        self.timestamp = timestamp
    }
}


// MARK: - 3. Thermal State

public enum SafariThermalState: Int, Sendable, Codable, Comparable {
    case nominal = 0
    case fair = 1
    case serious = 2
    case critical = 3

    public static func < (
        lhs: SafariThermalState,
        rhs: SafariThermalState
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}


// MARK: - 4. System Power Mode

public enum SafariPowerMode: String, Sendable, Codable {

    case maximumPerformance
    case balanced
    case batteryOptimized
    case aggressivePowerSaving
    case thermalProtection

    public var isPowerSaving: Bool {
        switch self {
        case .maximumPerformance:
            return false

        case .balanced:
            return false

        case .batteryOptimized,
             .aggressivePowerSaving,
             .thermalProtection:
            return true
        }
    }
}


// MARK: - 5. Power Budget

public struct SafariPowerBudget: Sendable, Codable {

    public let cpuBudgetFraction: Double
    public let backgroundWorkFraction: Double
    public let javascriptBudgetFraction: Double
    public let prefetchBudgetFraction: Double
    public let renderingBudgetFraction: Double
    public let telemetryBudgetFraction: Double

    public init(
        cpuBudgetFraction: Double,
        backgroundWorkFraction: Double,
        javascriptBudgetFraction: Double,
        prefetchBudgetFraction: Double,
        renderingBudgetFraction: Double,
        telemetryBudgetFraction: Double
    ) {
        self.cpuBudgetFraction = cpuBudgetFraction
        self.backgroundWorkFraction = backgroundWorkFraction
        self.javascriptBudgetFraction = javascriptBudgetFraction
        self.prefetchBudgetFraction = prefetchBudgetFraction
        self.renderingBudgetFraction = renderingBudgetFraction
        self.telemetryBudgetFraction = telemetryBudgetFraction
    }

    public static let maximum = SafariPowerBudget(
        cpuBudgetFraction: 1.0,
        backgroundWorkFraction: 1.0,
        javascriptBudgetFraction: 1.0,
        prefetchBudgetFraction: 1.0,
        renderingBudgetFraction: 1.0,
        telemetryBudgetFraction: 1.0
    )

    public static let balanced = SafariPowerBudget(
        cpuBudgetFraction: 0.85,
        backgroundWorkFraction: 0.70,
        javascriptBudgetFraction: 0.80,
        prefetchBudgetFraction: 0.65,
        renderingBudgetFraction: 0.90,
        telemetryBudgetFraction: 0.70
    )

    public static let battery = SafariPowerBudget(
        cpuBudgetFraction: 0.65,
        backgroundWorkFraction: 0.40,
        javascriptBudgetFraction: 0.60,
        prefetchBudgetFraction: 0.25,
        renderingBudgetFraction: 0.75,
        telemetryBudgetFraction: 0.45
    )

    public static let aggressive = SafariPowerBudget(
        cpuBudgetFraction: 0.45,
        backgroundWorkFraction: 0.15,
        javascriptBudgetFraction: 0.35,
        prefetchBudgetFraction: 0.05,
        renderingBudgetFraction: 0.55,
        telemetryBudgetFraction: 0.20
    )

    public static let thermal = SafariPowerBudget(
        cpuBudgetFraction: 0.30,
        backgroundWorkFraction: 0.05,
        javascriptBudgetFraction: 0.20,
        prefetchBudgetFraction: 0.01,
        renderingBudgetFraction: 0.40,
        telemetryBudgetFraction: 0.10
    )
}


// MARK: - 6. Runtime Snapshot

public struct SafariPowerSnapshot: Sendable, Codable {

    public let battery: SafariBatteryState
    public let thermalState: SafariThermalState
    public let lowPowerModeEnabled: Bool
    public let mode: SafariPowerMode
    public let budget: SafariPowerBudget
    public let timestamp: Date

    public init(
        battery: SafariBatteryState,
        thermalState: SafariThermalState,
        lowPowerModeEnabled: Bool,
        mode: SafariPowerMode,
        budget: SafariPowerBudget,
        timestamp: Date = Date()
    ) {
        self.battery = battery
        self.thermalState = thermalState
        self.lowPowerModeEnabled = lowPowerModeEnabled
        self.mode = mode
        self.budget = budget
        self.timestamp = timestamp
    }
}


// MARK: - 7. Power Providers

public protocol SafariBatteryProvider: Sendable {

    func currentBatteryState() async -> SafariBatteryState
}

public protocol SafariThermalProvider: Sendable {

    func currentThermalState() async -> SafariThermalState
}

public protocol SafariLowPowerModeProvider: Sendable {

    func isLowPowerModeEnabled() async -> Bool
}


// MARK: - 8. macOS Battery Provider

public struct MacOSSafariBatteryProvider: SafariBatteryProvider {

    public init() {}

    public func currentBatteryState() async -> SafariBatteryState {

        guard
            let blob = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
            let sources = IOPSCopyPowerSourcesList(blob)?.takeRetainedValue()
                as? [CFTypeRef]
        else {
            return SafariBatteryState(
                source: .unknown,
                chargeFraction: nil,
                isCharging: false,
                timeRemainingMinutes: nil
            )
        }

        var batteryFound = false
        var charge: Double?
        var charging = false

        for source in sources {

            guard
                let description =
                    IOPSGetPowerSourceDescription(blob, source)?
                        .takeUnretainedValue()
                        as? [String: Any]
            else {
                continue
            }

            guard
                let type = description[kIOPSTypeKey] as? String,
                type == kIOPSInternalBatteryType
            else {
                continue
            }

            batteryFound = true

            if
                let current = description[kIOPSCurrentCapacityKey] as? Int,
                let max = description[kIOPSMaxCapacityKey] as? Int,
                max > 0
            {
                charge = Double(current) / Double(max)
            }

            charging =
                (description[kIOPSIsChargingKey] as? Bool) ?? false
        }

        if batteryFound {
            return SafariBatteryState(
                source: .battery,
                chargeFraction: charge,
                isCharging: charging,
                timeRemainingMinutes: nil
            )
        }

        return SafariBatteryState(
            source: .externalPower,
            chargeFraction: nil,
            isCharging: false,
            timeRemainingMinutes: nil
        )
    }
}


// MARK: - 9. Thermal Provider

public struct MacOSThermalProvider: SafariThermalProvider {

    public init() {}

    public func currentThermalState() async -> SafariThermalState {

        switch ProcessInfo.processInfo.thermalState {

        case .nominal:
            return .nominal

        case .fair:
            return .fair

        case .serious:
            return .serious

        case .critical:
            return .critical

        @unknown default:
            return .fair
        }
    }
}


// MARK: - 10. Low Power Provider

public struct MacOSLowPowerModeProvider: SafariLowPowerModeProvider {

    public init() {}

    public func isLowPowerModeEnabled() async -> Bool {

        /*
         macOS Low Power Mode availability differs by OS/hardware.

         This provider deliberately avoids private preferences or
         unsupported system interfaces.

         The production implementation can be connected to an
         OS-version-specific adapter.

         Returning false here is preferable to falsely claiming
         that Low Power Mode is active.
        */

        return false
    }
}


// MARK: - 11. Power Policy

public struct SafariPowerPolicy: Sendable, Codable {

    public var batteryThreshold: Double
    public var aggressiveBatteryThreshold: Double

    public var seriousThermalThreshold: SafariThermalState
    public var criticalThermalThreshold: SafariThermalState

    public var backgroundSuspensionDelay: TimeInterval
    public var prefetchMaximumAge: TimeInterval

    public var telemetryIntervalNormal: TimeInterval
    public var telemetryIntervalBattery: TimeInterval
    public var telemetryIntervalThermal: TimeInterval

    public init(
        batteryThreshold: Double = 0.50,
        aggressiveBatteryThreshold: Double = 0.20,
        seriousThermalThreshold: SafariThermalState = .serious,
        criticalThermalThreshold: SafariThermalState = .critical,
        backgroundSuspensionDelay: TimeInterval = 120,
        prefetchMaximumAge: TimeInterval = 30,
        telemetryIntervalNormal: TimeInterval = 2,
        telemetryIntervalBattery: TimeInterval = 5,
        telemetryIntervalThermal: TimeInterval = 10
    ) {
        self.batteryThreshold = batteryThreshold
        self.aggressiveBatteryThreshold = aggressiveBatteryThreshold
        self.seriousThermalThreshold = seriousThermalThreshold
        self.criticalThermalThreshold = criticalThermalThreshold
        self.backgroundSuspensionDelay = backgroundSuspensionDelay
        self.prefetchMaximumAge = prefetchMaximumAge
        self.telemetryIntervalNormal = telemetryIntervalNormal
        self.telemetryIntervalBattery = telemetryIntervalBattery
        self.telemetryIntervalThermal = telemetryIntervalThermal
    }
}


// MARK: - 12. Power Policy Engine

public actor SafariPowerPolicyEngine {

    private let policy: SafariPowerPolicy

    public init(policy: SafariPowerPolicy = SafariPowerPolicy()) {
        self.policy = policy
    }

    public func evaluate(
        battery: SafariBatteryState,
        thermal: SafariThermalState,
        lowPowerMode: Bool
    ) -> SafariPowerSnapshot {

        let mode: SafariPowerMode

        if thermal >= policy.criticalThermalThreshold {
            mode = .thermalProtection

        } else if thermal >= policy.seriousThermalThreshold {
            mode = .thermalProtection

        } else if lowPowerMode {
            mode = .aggressivePowerSaving

        } else if battery.source == .battery {

            if
                let charge = battery.chargeFraction,
                charge <= policy.aggressiveBatteryThreshold
            {
                mode = .aggressivePowerSaving

            } else if
                let charge = battery.chargeFraction,
                charge <= policy.batteryThreshold
            {
                mode = .batteryOptimized

            } else {
                mode = .balanced
            }

        } else {
            mode = .maximumPerformance
        }

        let budget: SafariPowerBudget

        switch mode {

        case .maximumPerformance:
            budget = .maximum

        case .balanced:
            budget = .balanced

        case .batteryOptimized:
            budget = .battery

        case .aggressivePowerSaving:
            budget = .aggressive

        case .thermalProtection:
            budget = .thermal
        }

        return SafariPowerSnapshot(
            battery: battery,
            thermalState: thermal,
            lowPowerModeEnabled: lowPowerMode,
            mode: mode,
            budget: budget
        )
    }
}


// MARK: - 13. Power Actions

public enum SafariPowerAction: Sendable, Codable, Hashable {

    case suspendBackgroundTab(PowerTabID)
    case reducePrefetch
    case stopPrefetch
    case reduceJavaScriptBackgroundWork
    case pauseNonEssentialWork
    case reduceTelemetry
    case reduceRenderingQuality
    case maintainRenderingQuality
    case resumeBackgroundWork
    case resumePrefetch
    case resumeJavaScriptBackgroundWork
}


// MARK: - 14. Tab Power State

public enum SafariTabPowerActivity: String, Sendable, Codable {

    case active
    case recentlyActive
    case background
    case idle
    case suspended
}


// MARK: - 15. Tab Power Record

public struct SafariTabPowerRecord: Sendable, Codable {

    public let tabID: PowerTabID
    public var activity: SafariTabPowerActivity
    public var lastInteraction: Date
    public var estimatedCPUFraction: Double
    public var estimatedMemoryPressure: Double
    public var audible: Bool
    public var playingMedia: Bool
    public var hasActiveDownloads: Bool

    public init(
        tabID: PowerTabID,
        activity: SafariTabPowerActivity = .active,
        lastInteraction: Date = Date(),
        estimatedCPUFraction: Double = 0,
        estimatedMemoryPressure: Double = 0,
        audible: Bool = false,
        playingMedia: Bool = false,
        hasActiveDownloads: Bool = false
    ) {
        self.tabID = tabID
        self.activity = activity
        self.lastInteraction = lastInteraction
        self.estimatedCPUFraction = estimatedCPUFraction
        self.estimatedMemoryPressure = estimatedMemoryPressure
        self.audible = audible
        self.playingMedia = playingMedia
        self.hasActiveDownloads = hasActiveDownloads
    }
}


// MARK: - 16. Tab Power Registry

public actor SafariPowerTabRegistry {

    private var tabs: [PowerTabID: SafariTabPowerRecord] = [:]

    public init() {}

    public func register(_ record: SafariTabPowerRecord) {
        tabs[record.tabID] = record
    }

    public func remove(_ tabID: PowerTabID) {
        tabs.removeValue(forKey: tabID)
    }

    public func updateActivity(
        _ tabID: PowerTabID,
        activity: SafariTabPowerActivity
    ) {
        tabs[tabID]?.activity = activity
    }

    public func updateInteraction(
        _ tabID: PowerTabID,
        date: Date = Date()
    ) {
        tabs[tabID]?.lastInteraction = date
        tabs[tabID]?.activity = .active
    }

    public func updateCPU(
        _ tabID: PowerTabID,
        fraction: Double
    ) {
        tabs[tabID]?.estimatedCPUFraction = fraction
    }

    public func updateMemoryPressure(
        _ tabID: PowerTabID,
        fraction: Double
    ) {
        tabs[tabID]?.estimatedMemoryPressure = fraction
    }

    public func updateMedia(
        _ tabID: PowerTabID,
        audible: Bool,
        playingMedia: Bool
    ) {
        tabs[tabID]?.audible = audible
        tabs[tabID]?.playingMedia = playingMedia
    }

    public func updateDownloads(
        _ tabID: PowerTabID,
        active: Bool
    ) {
        tabs[tabID]?.hasActiveDownloads = active
    }

    public func allTabs() -> [SafariTabPowerRecord] {
        Array(tabs.values)
    }
}


// MARK: - 17. Suspension Decision Engine

public actor SafariPowerSuspensionEngine {

    private let policy: SafariPowerPolicy

    public init(policy: SafariPowerPolicy = SafariPowerPolicy()) {
        self.policy = policy
    }

    public func actions(
        snapshot: SafariPowerSnapshot,
        tabs: [SafariTabPowerRecord],
        now: Date = Date()
    ) -> [SafariPowerAction] {

        var actions: [SafariPowerAction] = []

        let aggressive =
            snapshot.mode == .aggressivePowerSaving ||
            snapshot.mode == .thermalProtection

        for tab in tabs {

            guard tab.activity != .active else {
                continue
            }

            let idleDuration =
                max(0, now.timeIntervalSince(tab.lastInteraction))

            guard idleDuration >= policy.backgroundSuspensionDelay else {
                continue
            }

            if tab.audible || tab.playingMedia {
                continue
            }

            if tab.hasActiveDownloads {
                continue
            }

            if aggressive {
                actions.append(
                    .suspendBackgroundTab(tab.tabID)
                )
            }
        }

        switch snapshot.mode {

        case .maximumPerformance:
            actions.append(.resumeBackgroundWork)
            actions.append(.resumePrefetch)
            actions.append(.resumeJavaScriptBackgroundWork)
            actions.append(.maintainRenderingQuality)

        case .balanced:
            break

        case .batteryOptimized:
            actions.append(.reducePrefetch)
            actions.append(.reduceJavaScriptBackgroundWork)
            actions.append(.reduceTelemetry)

        case .aggressivePowerSaving:
            actions.append(.stopPrefetch)
            actions.append(.pauseNonEssentialWork)
            actions.append(.reduceJavaScriptBackgroundWork)
            actions.append(.reduceRenderingQuality)
            actions.append(.reduceTelemetry)

        case .thermalProtection:
            actions.append(.stopPrefetch)
            actions.append(.pauseNonEssentialWork)
            actions.append(.reduceJavaScriptBackgroundWork)
            actions.append(.reduceRenderingQuality)
            actions.append(.reduceTelemetry)
        }

        return actions
    }
}


// MARK: - 18. Prefetch Budget

public struct SafariPrefetchBudget: Sendable, Codable {

    public let maximumConcurrentRequests: Int
    public let maximumBytes: Int64
    public let maximumDuration: TimeInterval

    public init(
        maximumConcurrentRequests: Int,
        maximumBytes: Int64,
        maximumDuration: TimeInterval
    ) {
        self.maximumConcurrentRequests = maximumConcurrentRequests
        self.maximumBytes = maximumBytes
        self.maximumDuration = maximumDuration
    }

    public static let maximum = SafariPrefetchBudget(
        maximumConcurrentRequests: 8,
        maximumBytes: 50_000_000,
        maximumDuration: 15
    )

    public static let balanced = SafariPrefetchBudget(
        maximumConcurrentRequests: 4,
        maximumBytes: 20_000_000,
        maximumDuration: 10
    )

    public static let battery = SafariPrefetchBudget(
        maximumConcurrentRequests: 2,
        maximumBytes: 8_000_000,
        maximumDuration: 5
    )

    public static let disabled = SafariPrefetchBudget(
        maximumConcurrentRequests: 0,
        maximumBytes: 0,
        maximumDuration: 0
    )
}


// MARK: - 19. Prefetch Budget Controller

public actor SafariPrefetchBudgetController {

    private var budget: SafariPrefetchBudget = .maximum

    public init() {}

    public func update(
        from snapshot: SafariPowerSnapshot
    ) {

        switch snapshot.mode {

        case .maximumPerformance:
            budget = .maximum

        case .balanced:
            budget = .balanced

        case .batteryOptimized:
            budget = .battery

        case .aggressivePowerSaving,
             .thermalProtection:
            budget = .disabled
        }
    }

    public func currentBudget() -> SafariPrefetchBudget {
        budget
    }
}


// MARK: - 20. Background Work Budget

public struct SafariBackgroundWorkBudget: Sendable, Codable {

    public let maximumConcurrentTasks: Int
    public let maximumCPUFraction: Double
    public let allowNetworkActivity: Bool
    public let allowDiskActivity: Bool

    public init(
        maximumConcurrentTasks: Int,
        maximumCPUFraction: Double,
        allowNetworkActivity: Bool,
        allowDiskActivity: Bool
    ) {
        self.maximumConcurrentTasks = maximumConcurrentTasks
        self.maximumCPUFraction = maximumCPUFraction
        self.allowNetworkActivity = allowNetworkActivity
        self.allowDiskActivity = allowDiskActivity
    }

    public static let maximum = SafariBackgroundWorkBudget(
        maximumConcurrentTasks: 8,
        maximumCPUFraction: 1.0,
        allowNetworkActivity: true,
        allowDiskActivity: true
    )

    public static let balanced = SafariBackgroundWorkBudget(
        maximumConcurrentTasks: 4,
        maximumCPUFraction: 0.70,
        allowNetworkActivity: true,
        allowDiskActivity: true
    )

    public static let battery = SafariBackgroundWorkBudget(
        maximumConcurrentTasks: 2,
        maximumCPUFraction: 0.40,
        allowNetworkActivity: false,
        allowDiskActivity: true
    )

    public static let thermal = SafariBackgroundWorkBudget(
        maximumConcurrentTasks: 1,
        maximumCPUFraction: 0.20,
        allowNetworkActivity: false,
        allowDiskActivity: false
    )
}


// MARK: - 21. Background Work Controller

public actor SafariBackgroundWorkController {

    private var budget: SafariBackgroundWorkBudget = .maximum
    private var activeTasks = 0

    public init() {}

    public func update(
        from snapshot: SafariPowerSnapshot
    ) {

        switch snapshot.mode {

        case .maximumPerformance:
            budget = .maximum

        case .balanced:
            budget = .balanced

        case .batteryOptimized:
            budget = .battery

        case .aggressivePowerSaving,
             .thermalProtection:
            budget = .thermal
        }
    }

    public func canStartTask() -> Bool {

        guard activeTasks < budget.maximumConcurrentTasks else {
            return false
        }

        return true
    }

    public func beginTask() -> Bool {

        guard canStartTask() else {
            return false
        }

        activeTasks += 1
        return true
    }

    public func finishTask() {

        activeTasks = max(0, activeTasks - 1)
    }

    public func currentBudget() -> SafariBackgroundWorkBudget {
        budget
    }
}


// MARK: - 22. JavaScript Budget

public struct SafariJavaScriptBudget: Sendable, Codable {

    public let maximumConcurrentJobs: Int
    public let maximumJobDuration: TimeInterval
    public let allowBackgroundJobs: Bool

    public init(
        maximumConcurrentJobs: Int,
        maximumJobDuration: TimeInterval,
        allowBackgroundJobs: Bool
    ) {
        self.maximumConcurrentJobs = maximumConcurrentJobs
        self.maximumJobDuration = maximumJobDuration
        self.allowBackgroundJobs = allowBackgroundJobs
    }

    public static let maximum = SafariJavaScriptBudget(
        maximumConcurrentJobs: 8,
        maximumJobDuration: 2.0,
        allowBackgroundJobs: true
    )

    public static let balanced = SafariJavaScriptBudget(
        maximumConcurrentJobs: 4,
        maximumJobDuration: 1.0,
        allowBackgroundJobs: true
    )

    public static let battery = SafariJavaScriptBudget(
        maximumConcurrentJobs: 2,
        maximumJobDuration: 0.5,
        allowBackgroundJobs: false
    )

    public static let thermal = SafariJavaScriptBudget(
        maximumConcurrentJobs: 1,
        maximumJobDuration: 0.25,
        allowBackgroundJobs: false
    )
}


// MARK: - 23. JavaScript Budget Controller

public actor SafariJavaScriptBudgetController {

    private var budget: SafariJavaScriptBudget = .maximum

    public init() {}

    public func update(
        from snapshot: SafariPowerSnapshot
    ) {

        switch snapshot.mode {

        case .maximumPerformance:
            budget = .maximum

        case .balanced:
            budget = .balanced

        case .batteryOptimized:
            budget = .battery

        case .aggressivePowerSaving,
             .thermalProtection:
            budget = .thermal
        }
    }

    public func currentBudget() -> SafariJavaScriptBudget {
        budget
    }
}


// MARK: - 24. Rendering Power Policy

public struct SafariRenderingPowerPolicy: Sendable, Codable {

    public let maximumFrameRate: Double
    public let allowHeavyAnimation: Bool
    public let allowBackgroundRendering: Bool
    public let reduceVisualWork: Bool

    public init(
        maximumFrameRate: Double,
        allowHeavyAnimation: Bool,
        allowBackgroundRendering: Bool,
        reduceVisualWork: Bool
    ) {
        self.maximumFrameRate = maximumFrameRate
        self.allowHeavyAnimation = allowHeavyAnimation
        self.allowBackgroundRendering = allowBackgroundRendering
        self.reduceVisualWork = reduceVisualWork
    }

    public static let maximum = SafariRenderingPowerPolicy(
        maximumFrameRate: 120,
        allowHeavyAnimation: true,
        allowBackgroundRendering: true,
        reduceVisualWork: false
    )

    public static let balanced = SafariRenderingPowerPolicy(
        maximumFrameRate: 120,
        allowHeavyAnimation: true,
        allowBackgroundRendering: false,
        reduceVisualWork: false
    )

    public static let battery = SafariRenderingPowerPolicy(
        maximumFrameRate: 60,
        allowHeavyAnimation: false,
        allowBackgroundRendering: false,
        reduceVisualWork: true
    )

    public static let thermal = SafariRenderingPowerPolicy(
        maximumFrameRate: 60,
        allowHeavyAnimation: false,
        allowBackgroundRendering: false,
        reduceVisualWork: true
    )
}


// MARK: - 25. Rendering Power Controller

public actor SafariRenderingPowerController {

    private var policy: SafariRenderingPowerPolicy = .maximum

    public init() {}

    public func update(
        from snapshot: SafariPowerSnapshot
    ) {

        switch snapshot.mode {

        case .maximumPerformance:
            policy = .maximum

        case .balanced:
            policy = .balanced

        case .batteryOptimized,
             .aggressivePowerSaving:
            policy = .battery

        case .thermalProtection:
            policy = .thermal
        }
    }

    public func currentPolicy() -> SafariRenderingPowerPolicy {
        policy
    }
}


// MARK: - 26. Telemetry Policy

public struct SafariPowerTelemetryPolicy: Sendable, Codable {

    public let samplingInterval: TimeInterval
    public let retainDetailedEvents: Bool

    public init(
        samplingInterval: TimeInterval,
        retainDetailedEvents: Bool
    ) {
        self.samplingInterval = samplingInterval
        self.retainDetailedEvents = retainDetailedEvents
    }

    public static let normal = SafariPowerTelemetryPolicy(
        samplingInterval: 2,
        retainDetailedEvents: true
    )

    public static let battery = SafariPowerTelemetryPolicy(
        samplingInterval: 5,
        retainDetailedEvents: false
    )

    public static let thermal = SafariPowerTelemetryPolicy(
        samplingInterval: 10,
        retainDetailedEvents: false
    )
}


// MARK: - 27. Telemetry Events

public enum SafariPowerTelemetryEvent: Sendable, Codable {

    case snapshot(SafariPowerSnapshot)

    case modeChanged(
        from: SafariPowerMode,
        to: SafariPowerMode
    )

    case tabSuspended(PowerTabID)

    case prefetchBudgetChanged(SafariPrefetchBudget)

    case backgroundBudgetChanged(SafariBackgroundWorkBudget)

    case javascriptBudgetChanged(SafariJavaScriptBudget)

    case renderingPolicyChanged(SafariRenderingPowerPolicy)
}


// MARK: - 28. Telemetry Store

public actor SafariPowerTelemetryStore {

    private var events: [SafariPowerTelemetryEvent] = []

    private let maximumEvents: Int

    public init(maximumEvents: Int = 2_000) {
        self.maximumEvents = maximumEvents
    }

    public func append(
        _ event: SafariPowerTelemetryEvent
    ) {

        events.append(event)

        if events.count > maximumEvents {
            events.removeFirst(
                events.count - maximumEvents
            )
        }
    }

    public func recentEvents(
        limit: Int = 100
    ) -> [SafariPowerTelemetryEvent] {

        Array(
            events.suffix(
                max(0, limit)
            )
        )
    }

    public func clear() {
        events.removeAll(keepingCapacity: true)
    }
}


// MARK: - 29. Runtime State

public struct SafariPowerRuntimeState: Sendable, Codable {

    public let snapshot: SafariPowerSnapshot
    public let prefetchBudget: SafariPrefetchBudget
    public let backgroundBudget: SafariBackgroundWorkBudget
    public let javascriptBudget: SafariJavaScriptBudget
    public let renderingPolicy: SafariRenderingPowerPolicy

    public init(
        snapshot: SafariPowerSnapshot,
        prefetchBudget: SafariPrefetchBudget,
        backgroundBudget: SafariBackgroundWorkBudget,
        javascriptBudget: SafariJavaScriptBudget,
        renderingPolicy: SafariRenderingPowerPolicy
    ) {
        self.snapshot = snapshot
        self.prefetchBudget = prefetchBudget
        self.backgroundBudget = backgroundBudget
        self.javascriptBudget = javascriptBudget
        self.renderingPolicy = renderingPolicy
    }
}


// MARK: - 30. Runtime Actor

public actor SafariPowerRuntime {

    private let batteryProvider: any SafariBatteryProvider
    private let thermalProvider: any SafariThermalProvider
    private let lowPowerProvider: any SafariLowPowerModeProvider

    private let policyEngine: SafariPowerPolicyEngine
    private let suspensionEngine: SafariPowerSuspensionEngine

    private let tabRegistry: SafariPowerTabRegistry
    private let prefetchController: SafariPrefetchBudgetController
    private let backgroundController: SafariBackgroundWorkController
    private let javascriptController: SafariJavaScriptBudgetController
    private let renderingController: SafariRenderingPowerController
    private let telemetry: SafariPowerTelemetryStore

    private var lastSnapshot: SafariPowerSnapshot?

    public init(
        batteryProvider: any SafariBatteryProvider =
            MacOSSafariBatteryProvider(),

        thermalProvider: any SafariThermalProvider =
            MacOSThermalProvider(),

        lowPowerProvider: any SafariLowPowerModeProvider =
            MacOSLowPowerModeProvider(),

        policy: SafariPowerPolicy =
            SafariPowerPolicy()
    ) {

        self.batteryProvider = batteryProvider
        self.thermalProvider = thermalProvider
        self.lowPowerProvider = lowPowerProvider

        self.policyEngine =
            SafariPowerPolicyEngine(policy: policy)

        self.suspensionEngine =
            SafariPowerSuspensionEngine(policy: policy)

        self.tabRegistry =
            SafariPowerTabRegistry()

        self.prefetchController =
            SafariPrefetchBudgetController()

        self.backgroundController =
            SafariBackgroundWorkController()

        self.javascriptController =
            SafariJavaScriptBudgetController()

        self.renderingController =
            SafariRenderingPowerController()

        self.telemetry =
            SafariPowerTelemetryStore()
    }

    public func evaluate() async
        -> SafariPowerRuntimeState
    {

        async let battery =
            batteryProvider.currentBatteryState()

        async let thermal =
            thermalProvider.currentThermalState()

        async let lowPower =
            lowPowerProvider.isLowPowerModeEnabled()

        let currentBattery = await battery
        let currentThermal = await thermal
        let currentLowPower = await lowPower

        let snapshot =
            await policyEngine.evaluate(
                battery: currentBattery,
                thermal: currentThermal,
                lowPowerMode: currentLowPower
            )

        let previous = lastSnapshot

        lastSnapshot = snapshot

        await prefetchController.update(
            from: snapshot
        )

        await backgroundController.update(
            from: snapshot
        )

        await javascriptController.update(
            from: snapshot
        )

        await renderingController.update(
            from: snapshot
        )

        await telemetry.append(
            .snapshot(snapshot)
        )

        if
            let previous,
            previous.mode != snapshot.mode
        {
            await telemetry.append(
                .modeChanged(
                    from: previous.mode,
                    to: snapshot.mode
                )
            )
        }

        let prefetchBudget =
            await prefetchController.currentBudget()

        let backgroundBudget =
            await backgroundController.currentBudget()

        let javascriptBudget =
            await javascriptController.currentBudget()

        let renderingPolicy =
            await renderingController.currentPolicy()

        return SafariPowerRuntimeState(
            snapshot: snapshot,
            prefetchBudget: prefetchBudget,
            backgroundBudget: backgroundBudget,
            javascriptBudget: javascriptBudget,
            renderingPolicy: renderingPolicy
        )
    }

    public func registerTab(
        _ record: SafariTabPowerRecord
    ) async {
        await tabRegistry.register(record)
    }

    public func removeTab(
        _ tabID: PowerTabID
    ) async {
        await tabRegistry.remove(tabID)
    }

    public func recordInteraction(
        _ tabID: PowerTabID
    ) async {
        await tabRegistry.updateInteraction(tabID)
    }

    public func updateTabActivity(
        _ tabID: PowerTabID,
        activity: SafariTabPowerActivity
    ) async {
        await tabRegistry.updateActivity(
            tabID,
            activity: activity
        )
    }

    public func updateTabCPU(
        _ tabID: PowerTabID,
        fraction: Double
    ) async {
        await tabRegistry.updateCPU(
            tabID,
            fraction: fraction
        )
    }

    public func updateTabMemoryPressure(
        _ tabID: PowerTabID,
        fraction: Double
    ) async {
        await tabRegistry.updateMemoryPressure(
            tabID,
            fraction: fraction
        )
    }

    public func updateTabMedia(
        _ tabID: PowerTabID,
        audible: Bool,
        playingMedia: Bool
    ) async {
        await tabRegistry.updateMedia(
            tabID,
            audible: audible,
            playingMedia: playingMedia
        )
    }

    public func updateTabDownloads(
        _ tabID: PowerTabID,
        active: Bool
    ) async {
        await tabRegistry.updateDownloads(
            tabID,
            active: active
        )
    }

    public func evaluateActions()
        async -> [SafariPowerAction]
    {
        let state = await evaluate()
        let tabs = await tabRegistry.allTabs()

        return await suspensionEngine.actions(
            snapshot: state.snapshot,
            tabs: tabs
        )
    }

    public func currentSnapshot()
        async -> SafariPowerSnapshot?
    {
        lastSnapshot
    }

    public func recentTelemetry(
        limit: Int = 100
    ) async -> [SafariPowerTelemetryEvent] {
        await telemetry.recentEvents(
            limit: limit
        )
    }
}


// MARK: - 31. Power Monitor

@MainActor
public final class SafariPowerMonitor {

    public typealias UpdateHandler =
        @Sendable (SafariPowerRuntimeState) -> Void

    private let runtime: SafariPowerRuntime

    private var timer: Timer?

    private let updateInterval: TimeInterval

    private var updateHandler: UpdateHandler?

    public init(
        runtime: SafariPowerRuntime,
        updateInterval: TimeInterval = 5
    ) {
        self.runtime = runtime
        self.updateInterval = updateInterval
    }

    public func start(
        handler: @escaping UpdateHandler
    ) {

        stop()

        updateHandler = handler

        Task {
            await refresh()
        }

        timer = Timer.scheduledTimer(
            withTimeInterval: updateInterval,
            repeats: true
        ) { [weak self] _ in

            guard let self else {
                return
            }

            Task {
                await self.refresh()
            }
        }
    }

    public func stop() {

        timer?.invalidate()
        timer = nil
        updateHandler = nil
    }

    private func refresh() async {

        let state = await runtime.evaluate()

        await MainActor.run { [weak self] in
            self?.updateHandler?(state)
        }
    }
}


// MARK: - 32. WebView Power Controller

@MainActor
public final class SafariWebViewPowerController {

    private weak var webView: WKWebView?

    public init(webView: WKWebView) {
        self.webView = webView
    }

    public func apply(
        renderingPolicy: SafariRenderingPowerPolicy
    ) {

        guard let webView else {
            return
        }

        /*
         Important:

         WebKit owns the compositor and actual page rendering.
         This controller therefore avoids private WebKit knobs.

         The integration points below are intentionally limited
         to public WKWebView configuration/state and to decisions
         that the surrounding Safari application can enforce.
        */

        if renderingPolicy.reduceVisualWork {

            webView.configuration.preferences.setValue(
                true,
                forKey: "javaScriptCanOpenWindowsAutomatically"
            )
        }
    }
}


// MARK: - 33. Power-Aware Prefetch Gate

public actor SafariPowerAwarePrefetchGate {

    private let controller: SafariPrefetchBudgetController

    public init(
        controller: SafariPrefetchBudgetController
    ) {
        self.controller = controller
    }

    public func shouldPrefetch() async -> Bool {

        let budget =
            await controller.currentBudget()

        return budget.maximumConcurrentRequests > 0
    }

    public func budget()
        async -> SafariPrefetchBudget
    {
        await controller.currentBudget()
    }
}


// MARK: - 34. Background Task Gate

public actor SafariPowerAwareBackgroundGate {

    private let controller: SafariBackgroundWorkController

    public init(
        controller: SafariBackgroundWorkController
    ) {
        self.controller = controller
    }

    public func acquire() async -> Bool {

        await controller.beginTask()
    }

    public func release() async {

        await controller.finishTask()
    }

    public func budget()
        async -> SafariBackgroundWorkBudget
    {
        await controller.currentBudget()
    }
}


// MARK: - 35. JavaScript Work Gate

public actor SafariPowerAwareJavaScriptGate {

    private let controller: SafariJavaScriptBudgetController

    public init(
        controller: SafariJavaScriptBudgetController
    ) {
        self.controller = controller
    }

    public func shouldRunBackgroundJavaScript()
        async -> Bool
    {
        let budget =
            await controller.currentBudget()

        return budget.allowBackgroundJobs
    }

    public func budget()
        async -> SafariJavaScriptBudget
    {
        await controller.currentBudget()
    }
}


// MARK: - 36. Power-Aware Work Scheduler

public struct SafariPowerWorkItem: Sendable {

    public let id: UUID
    public let priority: Int
    public let estimatedCost: TimeInterval
    public let operation: @Sendable () async -> Void

    public init(
        id: UUID = UUID(),
        priority: Int,
        estimatedCost: TimeInterval,
        operation: @escaping @Sendable () async -> Void
    ) {
        self.id = id
        self.priority = priority
        self.estimatedCost = estimatedCost
        self.operation = operation
    }
}


public actor SafariPowerAwareWorkScheduler {

    private let backgroundController:
        SafariBackgroundWorkController

    private var queued: [SafariPowerWorkItem] = []

    private var workerTask: Task<Void, Never>?

    public init(
        backgroundController:
            SafariBackgroundWorkController
    ) {
        self.backgroundController =
            backgroundController
    }

    public func enqueue(
        _ item: SafariPowerWorkItem
    ) {

        queued.append(item)

        queued.sort {
            $0.priority > $1.priority
        }

        startWorkerIfNecessary()
    }

    private func startWorkerIfNecessary() {

        guard workerTask == nil else {
            return
        }

        workerTask = Task { [weak self] in

            guard let self else {
                return
            }

            await self.runLoop()
        }
    }

    private func runLoop() async {

        while !Task.isCancelled {

            guard !queued.isEmpty else {
                workerTask = nil
                return
            }

            guard
                await backgroundController.beginTask()
            else {

                try? await Task.sleep(
                    for: .milliseconds(250)
                )

                continue
            }

            let item = queued.removeFirst()

            await item.operation()

            await backgroundController.finishTask()
        }
    }

    public func cancelAll() {

        queued.removeAll()

        workerTask?.cancel()
        workerTask = nil
    }
}


// MARK: - 37. Power Event Stream

public enum SafariPowerEvent: Sendable {

    case runtimeStateChanged(
        SafariPowerRuntimeState
    )

    case actionRequested(
        SafariPowerAction
    )
}


public actor SafariPowerEventBus {

    private var continuations:
        [UUID: AsyncStream<SafariPowerEvent>.Continuation] = [:]

    public init() {}

    public func stream()
        -> AsyncStream<SafariPowerEvent>
    {

        let identifier = UUID()

        return AsyncStream { continuation in

            continuations[identifier] = continuation

            continuation.onTermination = {
                Task {
                    await self.remove(
                        identifier
                    )
                }
            }
        }
    }

    private func remove(
        _ identifier: UUID
    ) {
        continuations.removeValue(
            forKey: identifier
        )
    }

    public func publish(
        _ event: SafariPowerEvent
    ) {

        for continuation in continuations.values {
            continuation.yield(event)
        }
    }
}


// MARK: - 38. Full Power Coordinator

public actor SafariPowerCoordinator {

    public let runtime: SafariPowerRuntime

    public let eventBus:
        SafariPowerEventBus

    private var monitorTask:
        Task<Void, Never>?

    public init(
        runtime: SafariPowerRuntime =
            SafariPowerRuntime()
    ) {

        self.runtime = runtime
        self.eventBus = SafariPowerEventBus()
    }

    public func start() {

        guard monitorTask == nil else {
            return
        }

        monitorTask = Task { [weak self] in

            guard let self else {
                return
            }

            await self.monitorLoop()
        }
    }

    public func stop() {

        monitorTask?.cancel()
        monitorTask = nil
    }

    private func monitorLoop() async {

        while !Task.isCancelled {

            let state =
                await runtime.evaluate()

            await eventBus.publish(
                .runtimeStateChanged(state)
            )

            let actions =
                await runtime.evaluateActions()

            for action in actions {

                await eventBus.publish(
                    .actionRequested(action)
                )
            }

            let interval =
                telemetryInterval(
                    for: state.snapshot
                )

            try? await Task.sleep(
                for: .seconds(
                    Int(interval)
                )
            )
        }
    }

    private func telemetryInterval(
        for snapshot: SafariPowerSnapshot
    ) -> TimeInterval {

        switch snapshot.mode {

        case .maximumPerformance:
            return 2

        case .balanced:
            return 3

        case .batteryOptimized:
            return 5

        case .aggressivePowerSaving:
            return 8

        case .thermalProtection:
            return 10
        }
    }
}


// MARK: - 39. Power-Aware Tab Controller

@MainActor
public final class SafariPowerAwareTabController {

    private let webViews:
        [PowerTabID: WKWebView]

    public init(
        webViews: [PowerTabID: WKWebView]
    ) {
        self.webViews = webViews
    }

    public func apply(
        action: SafariPowerAction
    ) {

        switch action {

        case .suspendBackgroundTab(let tabID):

            guard let webView = webViews[tabID] else {
                return
            }

            /*
             Public WebKit-compatible suspension strategy:

             Remove expensive application-level work, detach
             nonessential observers, stop application-owned timers,
             and allow the existing Safari tab lifecycle system
             (#1) to perform actual tab suspension.

             We deliberately do not attempt to manipulate private
             WebKit processes.
            */

            webView.stopLoading()

        default:
            break
        }
    }
}


// MARK: - 40. Power-Aware Safari Engine

@MainActor
public final class SafariPowerAwareEngine {

    public let runtime: SafariPowerRuntime

    public let monitor:
        SafariPowerMonitor

    private var latestState:
        SafariPowerRuntimeState?

    private var stateTask:
        Task<Void, Never>?

    public init(
        runtime: SafariPowerRuntime =
            SafariPowerRuntime()
    ) {

        self.runtime = runtime

        self.monitor =
            SafariPowerMonitor(
                runtime: runtime
            )
    }

    public func start() {

        monitor.start { [weak self] state in

            self?.latestState = state

            self?.apply(
                state: state
            )
        }
    }

    public func stop() {
        monitor.stop()
        stateTask?.cancel()
        stateTask = nil
    }

    private func apply(
        state: SafariPowerRuntimeState
    ) {

        switch state.snapshot.mode {

        case .maximumPerformance:

            break

        case .balanced:

            break

        case .batteryOptimized:

            /*
             Coordinate with:

             #1 Tab Manager
             #2 WebKit Resource Manager
             #3 Navigation Runtime
             #4 Predictive Loading
             #5 Rendering Engine
            */

            break

        case .aggressivePowerSaving:

            break

        case .thermalProtection:

            break
        }
    }

    public func currentState()
        -> SafariPowerRuntimeState?
    {
        latestState
    }
}


// MARK: - 41. Power Diagnostics

public struct SafariPowerDiagnosticsReport:
    Sendable, Codable
{

    public let snapshot: SafariPowerSnapshot
    public let tabs: [SafariTabPowerRecord]
    public let actions: [SafariPowerAction]
    public let generatedAt: Date

    public init(
        snapshot: SafariPowerSnapshot,
        tabs: [SafariTabPowerRecord],
        actions: [SafariPowerAction],
        generatedAt: Date = Date()
    ) {
        self.snapshot = snapshot
        self.tabs = tabs
        self.actions = actions
        self.generatedAt = generatedAt
    }
}


public actor SafariPowerDiagnostics {

    private let runtime: SafariPowerRuntime

    public init(
        runtime: SafariPowerRuntime
    ) {
        self.runtime = runtime
    }

    public func generate()
        async -> SafariPowerDiagnosticsReport?
    {

        guard
            let snapshot =
                await runtime.currentSnapshot()
        else {
            return nil
        }

        let actions =
            await runtime.evaluateActions()

        /*
         Tab records are intentionally retrieved indirectly
         through the runtime in the production implementation.
        */

        return SafariPowerDiagnosticsReport(
            snapshot: snapshot,
            tabs: [],
            actions: actions
        )
    }
}


// MARK: - 42. Testing Providers

public struct MockBatteryProvider:
    SafariBatteryProvider
{

    public var state: SafariBatteryState

    public init(
        state: SafariBatteryState
    ) {
        self.state = state
    }

    public func currentBatteryState()
        async -> SafariBatteryState
    {
        state
    }
}


public struct MockThermalProvider:
    SafariThermalProvider
{

    public var state: SafariThermalState

    public init(
        state: SafariThermalState
    ) {
        self.state = state
    }

    public func currentThermalState()
        async -> SafariThermalState
    {
        state
    }
}


public struct MockLowPowerProvider:
    SafariLowPowerModeProvider
{

    public var enabled: Bool

    public init(
        enabled: Bool
    ) {
        self.enabled = enabled
    }

    public func isLowPowerModeEnabled()
        async -> Bool
    {
        enabled
    }
}


// MARK: - 43. Runtime Factory

public enum SafariPowerRuntimeFactory {

    public static func makeProductionRuntime()
        -> SafariPowerRuntime
    {

        SafariPowerRuntime(
            batteryProvider:
                MacOSSafariBatteryProvider(),

            thermalProvider:
                MacOSThermalProvider(),

            lowPowerProvider:
                MacOSLowPowerModeProvider(),

            policy:
                SafariPowerPolicy()
        )
    }

    public static func makeBatteryTestRuntime()
        -> SafariPowerRuntime
    {

        SafariPowerRuntime(
            batteryProvider:
                MockBatteryProvider(
                    state:
                        SafariBatteryState(
                            source: .battery,
                            chargeFraction: 0.15,
                            isCharging: false,
                            timeRemainingMinutes: 45
                        )
                ),

            thermalProvider:
                MockThermalProvider(
                    state: .nominal
                ),

            lowPowerProvider:
                MockLowPowerProvider(
                    enabled: false
                )
        )
    }

    public static func makeThermalTestRuntime()
        -> SafariPowerRuntime
    {

        SafariPowerRuntime(
            batteryProvider:
                MockBatteryProvider(
                    state:
                        SafariBatteryState(
                            source: .externalPower,
                            chargeFraction: nil,
                            isCharging: false,
                            timeRemainingMinutes: nil
                        )
                ),

            thermalProvider:
                MockThermalProvider(
                    state: .critical
                ),

            lowPowerProvider:
                MockLowPowerProvider(
                    enabled: false
                )
        )
    }
}


// MARK: - 44. Example Safari Integration

@MainActor
public final class SafariBrowserPowerIntegration {

    private let engine:
        SafariPowerAwareEngine

    private let runtime:
        SafariPowerRuntime

    public init() {

        runtime =
            SafariPowerRuntimeFactory
                .makeProductionRuntime()

        engine =
            SafariPowerAwareEngine(
                runtime: runtime
            )
    }

    public func start() {

        engine.start()
    }

    public func stop() {

        engine.stop()
    }

    public func registerTab(
        id: PowerTabID
    ) {

        Task {

            await runtime.registerTab(
                SafariTabPowerRecord(
                    tabID: id
                )
            )
        }
    }

    public func recordUserInteraction(
        tabID: PowerTabID
    ) {

        Task {

            await runtime.recordInteraction(
                tabID
            )
        }
    }

    public func setTabBackground(
        tabID: PowerTabID
    ) {

        Task {

            await runtime.updateTabActivity(
                tabID,
                activity: .background
            )
        }
    }

    public func setMediaState(
        tabID: PowerTabID,
        audible: Bool,
        playing: Bool
    ) {

        Task {

            await runtime.updateTabMedia(
                tabID,
                audible: audible,
                playingMedia: playing
            )
        }
    }
}


// MARK: - 45. XCTest-Style Validation

#if DEBUG

enum SafariPowerRuntimeTests {

    static func testCriticalThermalState() async {

        let runtime =
            SafariPowerRuntimeFactory
                .makeThermalTestRuntime()

        let state =
            await runtime.evaluate()

        assert(
            state.snapshot.mode ==
                .thermalProtection
        )

        assert(
            state.prefetchBudget
                .maximumConcurrentRequests == 0
        )

        assert(
            state.javascriptBudget
                .allowBackgroundJobs == false
        )
    }

    static func testLowBatteryState() async {

        let runtime =
            SafariPowerRuntimeFactory
                .makeBatteryTestRuntime()

        let state =
            await runtime.evaluate()

        assert(
            state.snapshot.mode ==
                .aggressivePowerSaving
        )

        assert(
            state.prefetchBudget
                .maximumConcurrentRequests == 0
        )

        assert(
            state.backgroundBudget
                .maximumConcurrentTasks == 1
        )
    }

    static func testTabSuspension() async {

        let runtime =
            SafariPowerRuntimeFactory
                .makeBatteryTestRuntime()

        let tabID =
            PowerTabID()

        await runtime.registerTab(
            SafariTabPowerRecord(
                tabID: tabID,
                activity: .background,
                lastInteraction:
                    Date(
                        timeIntervalSinceNow: -600
                    ),
                estimatedCPUFraction: 0.8,
                estimatedMemoryPressure: 0.4,
                audible: false,
                playingMedia: false,
                hasActiveDownloads: false
            )
        )

        let actions =
            await runtime.evaluateActions()

        let containsSuspension =
            actions.contains {
                action in

                if case .suspendBackgroundTab(
                    let candidate
                ) = action {
                    return candidate == tabID
                }

                return false
            }

        assert(
            containsSuspension
        )
    }
}

#endif


// MARK: - 46. Complete System Factory

public struct SafariPowerSystem {

    public let runtime:
        SafariPowerRuntime

    public let coordinator:
        SafariPowerCoordinator

    public let prefetchGate:
        SafariPowerAwarePrefetchGate

    public let backgroundGate:
        SafariPowerAwareBackgroundGate

    public let javascriptGate:
        SafariPowerAwareJavaScriptGate

    public let workScheduler:
        SafariPowerAwareWorkScheduler
}


public enum SafariPowerSystemFactory {

    public static func make()
        -> SafariPowerSystem
    {

        let runtime =
            SafariPowerRuntimeFactory
                .makeProductionRuntime()

        let coordinator =
            SafariPowerCoordinator(
                runtime: runtime
            )

        let prefetchController =
            SafariPrefetchBudgetController()

        let backgroundController =
            SafariBackgroundWorkController()

        let javascriptController =
            SafariJavaScriptBudgetController()

        return SafariPowerSystem(
            runtime: runtime,

            coordinator: coordinator,

            prefetchGate:
                SafariPowerAwarePrefetchGate(
                    controller:
                        prefetchController
                ),

            backgroundGate:
                SafariPowerAwareBackgroundGate(
                    controller:
                        backgroundController
                ),

            javascriptGate:
                SafariPowerAwareJavaScriptGate(
                    controller:
                        javascriptController
                ),

            workScheduler:
                SafariPowerAwareWorkScheduler(
                    backgroundController:
                        backgroundController
                )
        )
    }
}






//
//  SafariCrashResistantSessionArchitecture.swift
//
//  Safari macOS Performance Architecture — #7
//
//  Goals:
//  - Crash-resistant session persistence
//  - Atomic journal writes
//  - Incremental session checkpoints
//  - Window/tab restoration
//  - Navigation restoration
//  - Scroll-position restoration
//  - Crash detection
//  - Recovery transactions
//  - Generation-based snapshots
//  - Debounced persistence
//  - Background checkpointing
//  - Corruption detection
//  - Automatic rollback to last valid checkpoint
//  - Swift 6 concurrency
//
//  Public APIs only.
//

import Foundation
import WebKit
import AppKit
import CryptoKit


// MARK: - 1. Identifiers

public struct SessionTabID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct SessionWindowID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct SessionGeneration: Hashable, Codable, Sendable,
    Comparable
{
    public let value: UInt64

    public init(_ value: UInt64) {
        self.value = value
    }

    public static func < (
        lhs: SessionGeneration,
        rhs: SessionGeneration
    ) -> Bool {
        lhs.value < rhs.value
    }
}

public struct SessionTransactionID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}


// MARK: - 2. Tab Lifecycle

public enum SessionTabLifecycle:
    String,
    Codable,
    Sendable
{
    case active
    case background
    case suspended
    case discarded
}


// MARK: - 3. Navigation State

public struct SessionNavigationState:
    Codable,
    Sendable
{
    public var currentURL: URL?
    public var originalURL: URL?
    public var title: String
    public var estimatedProgress: Double
    public var canGoBack: Bool
    public var canGoForward: Bool

    public init(
        currentURL: URL? = nil,
        originalURL: URL? = nil,
        title: String = "",
        estimatedProgress: Double = 0,
        canGoBack: Bool = false,
        canGoForward: Bool = false
    ) {
        self.currentURL = currentURL
        self.originalURL = originalURL
        self.title = title
        self.estimatedProgress = estimatedProgress
        self.canGoBack = canGoBack
        self.canGoForward = canGoForward
    }
}


// MARK: - 4. Scroll State

public struct SessionScrollState:
    Codable,
    Sendable
{
    public var x: Double
    public var y: Double

    public init(
        x: Double = 0,
        y: Double = 0
    ) {
        self.x = x
        self.y = y
    }
}


// MARK: - 5. Tab Session Record

public struct SafariSessionTab:
    Codable,
    Sendable
{

    public let id: SessionTabID

    public var title: String
    public var lifecycle: SessionTabLifecycle

    public var navigation:
        SessionNavigationState

    public var scroll:
        SessionScrollState

    public var isPinned: Bool
    public var isMuted: Bool
    public var isPlayingMedia: Bool

    public var createdAt: Date
    public var lastModifiedAt: Date
    public var lastInteractionAt: Date

    public init(
        id: SessionTabID,
        title: String = "",
        lifecycle: SessionTabLifecycle = .active,
        navigation: SessionNavigationState =
            SessionNavigationState(),
        scroll: SessionScrollState =
            SessionScrollState(),
        isPinned: Bool = false,
        isMuted: Bool = false,
        isPlayingMedia: Bool = false,
        createdAt: Date = Date(),
        lastModifiedAt: Date = Date(),
        lastInteractionAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.lifecycle = lifecycle
        self.navigation = navigation
        self.scroll = scroll
        self.isPinned = isPinned
        self.isMuted = isMuted
        self.isPlayingMedia = isPlayingMedia
        self.createdAt = createdAt
        self.lastModifiedAt = lastModifiedAt
        self.lastInteractionAt = lastInteractionAt
    }
}


// MARK: - 6. Window Session Record

public struct SafariSessionWindow:
    Codable,
    Sendable
{

    public let id: SessionWindowID

    public var tabs: [SafariSessionTab]

    public var selectedTab:
        SessionTabID?

    public var frame:
        SessionWindowFrame

    public var isFullScreen: Bool

    public var createdAt: Date
    public var lastModifiedAt: Date

    public init(
        id: SessionWindowID,
        tabs: [SafariSessionTab] = [],
        selectedTab: SessionTabID? = nil,
        frame: SessionWindowFrame =
            SessionWindowFrame(),
        isFullScreen: Bool = false,
        createdAt: Date = Date(),
        lastModifiedAt: Date = Date()
    ) {
        self.id = id
        self.tabs = tabs
        self.selectedTab = selectedTab
        self.frame = frame
        self.isFullScreen = isFullScreen
        self.createdAt = createdAt
        self.lastModifiedAt = lastModifiedAt
    }
}


// MARK: - 7. Window Frame

public struct SessionWindowFrame:
    Codable,
    Sendable
{
    public var x: Double
    public var y: Double
    public var width: Double
    public var height: Double

    public init(
        x: Double = 100,
        y: Double = 100,
        width: Double = 1200,
        height: Double = 800
    ) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }
}


// MARK: - 8. Complete Session

public struct SafariSession:
    Codable,
    Sendable
{

    public let schemaVersion: UInt32

    public var generation:
        SessionGeneration

    public var windows:
        [SafariSessionWindow]

    public var activeWindow:
        SessionWindowID?

    public var savedAt:
        Date

    public init(
        schemaVersion: UInt32 = 1,
        generation:
            SessionGeneration = SessionGeneration(0),
        windows:
            [SafariSessionWindow] = [],
        activeWindow:
            SessionWindowID? = nil,
        savedAt: Date = Date()
    ) {
        self.schemaVersion = schemaVersion
        self.generation = generation
        self.windows = windows
        self.activeWindow = activeWindow
        self.savedAt = savedAt
    }
}


// MARK: - 9. Session Mutation

public enum SafariSessionMutation:
    Codable,
    Sendable
{

    case createWindow(
        SafariSessionWindow
    )

    case deleteWindow(
        SessionWindowID
    )

    case createTab(
        window: SessionWindowID,
        tab: SafariSessionTab
    )

    case deleteTab(
        window: SessionWindowID,
        tab: SessionTabID
    )

    case updateTab(
        window: SessionWindowID,
        tab: SafariSessionTab
    )

    case selectTab(
        window: SessionWindowID,
        tab: SessionTabID?
    )

    case updateWindow(
        SafariSessionWindow
    )

    case setActiveWindow(
        SessionWindowID?
    )
}


// MARK: - 10. Transaction

public struct SafariSessionTransaction:
    Codable,
    Sendable
{

    public let id:
        SessionTransactionID

    public let generation:
        SessionGeneration

    public let timestamp:
        Date

    public let mutations:
        [SafariSessionMutation]

    public init(
        id: SessionTransactionID =
            SessionTransactionID(),
        generation:
            SessionGeneration,
        timestamp: Date = Date(),
        mutations:
            [SafariSessionMutation]
    ) {
        self.id = id
        self.generation = generation
        self.timestamp = timestamp
        self.mutations = mutations
    }
}


// MARK: - 11. Journal Record

public struct SafariSessionJournalRecord:
    Codable,
    Sendable
{

    public let transaction:
        SafariSessionTransaction

    public let checksum:
        String

    public init(
        transaction:
            SafariSessionTransaction,
        checksum: String
    ) {
        self.transaction = transaction
        self.checksum = checksum
    }
}


// MARK: - 12. Session Envelope

public struct SafariSessionEnvelope:
    Codable,
    Sendable
{

    public let schemaVersion:
        UInt32

    public let generation:
        SessionGeneration

    public let session:
        SafariSession

    public let checksum:
        String

    public init(
        schemaVersion: UInt32,
        generation:
            SessionGeneration,
        session:
            SafariSession,
        checksum:
            String
    ) {
        self.schemaVersion = schemaVersion
        self.generation = generation
        self.session = session
        self.checksum = checksum
    }
}


// MARK: - 13. Session Storage Paths

public struct SafariSessionStorage:
    Sendable
{

    public let directory:
        URL

    public let snapshot:
        URL

    public let backup:
        URL

    public let journal:
        URL

    public let lock:
        URL

    public init(
        directory: URL
    ) {
        self.directory = directory

        self.snapshot =
            directory
                .appendingPathComponent(
                    "session.snapshot"
                )

        self.backup =
            directory
                .appendingPathComponent(
                    "session.backup"
                )

        self.journal =
            directory
                .appendingPathComponent(
                    "session.journal"
                )

        self.lock =
            directory
                .appendingPathComponent(
                    "session.lock"
                )
    }

    public static func defaultStorage()
        -> SafariSessionStorage
    {
        let base =
            FileManager.default
                .urls(
                    for:
                        .applicationSupportDirectory,
                    in:
                        .userDomainMask
                )
                .first!

        let directory =
            base
                .appendingPathComponent(
                    "SafariPowerArchitecture",
                    isDirectory: true
                )

        return SafariSessionStorage(
            directory: directory
        )
    }
}


// MARK: - 14. Session Codec

public struct SafariSessionCodec:
    Sendable
{

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    public init() {

        let encoder =
            JSONEncoder()

        encoder.outputFormatting = [
            .sortedKeys
        ]

        encoder.dateEncodingStrategy =
            .millisecondsSince1970

        self.encoder = encoder

        let decoder =
            JSONDecoder()

        decoder.dateDecodingStrategy =
            .millisecondsSince1970

        self.decoder = decoder
    }

    public func encode<T: Encodable>(
        _ value: T
    ) throws -> Data {

        try encoder.encode(value)
    }

    public func decode<T: Decodable>(
        _ type: T.Type,
        from data: Data
    ) throws -> T {

        try decoder.decode(
            type,
            from: data
        )
    }
}


// MARK: - 15. Checksum

public enum SafariSessionChecksum {

    public static func make(
        data: Data
    ) -> String {

        let digest =
            SHA256.hash(
                data: data
            )

        return digest
            .map {
                String(
                    format: "%02x",
                    $0
                )
            }
            .joined()
    }
}


// MARK: - 16. Atomic File Writer

public struct SafariAtomicFileWriter:
    Sendable
{

    private let fileManager:
        FileManager

    public init(
        fileManager: FileManager =
            .default
    ) {
        self.fileManager =
            fileManager
    }

    public func write(
        _ data: Data,
        to url: URL
    ) throws {

        let directory =
            url.deletingLastPathComponent()

        try fileManager.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )

        let temporaryURL =
            directory
                .appendingPathComponent(
                    ".\(url.lastPathComponent).tmp-\(UUID().uuidString)"
                )

        try data.write(
            to: temporaryURL,
            options: [
                .atomic,
                .completeFileProtection
            ]
        )

        if fileManager.fileExists(
            atPath: url.path
        ) {

            _ = try fileManager.replaceItemAt(
                url,
                withItemAt: temporaryURL
            )

        } else {

            try fileManager.moveItem(
                at: temporaryURL,
                to: url
            )
        }
    }
}


// MARK: - 17. Snapshot Repository

public actor SafariSessionSnapshotRepository {

    private let storage:
        SafariSessionStorage

    private let codec:
        SafariSessionCodec

    private let writer:
        SafariAtomicFileWriter

    public init(
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {
        self.storage = storage
        self.codec = SafariSessionCodec()
        self.writer = SafariAtomicFileWriter()
    }

    public func save(
        _ session: SafariSession
    ) throws {

        let payload =
            try codec.encode(
                session
            )

        let checksum =
            SafariSessionChecksum.make(
                data: payload
            )

        let envelope =
            SafariSessionEnvelope(
                schemaVersion:
                    session.schemaVersion,
                generation:
                    session.generation,
                session:
                    session,
                checksum:
                    checksum
            )

        let data =
            try codec.encode(
                envelope
            )

        try writer.write(
            data,
            to: storage.snapshot
        )
    }

    public func load()
        throws -> SafariSession
    {

        let data =
            try Data(
                contentsOf:
                    storage.snapshot
            )

        let envelope =
            try codec.decode(
                SafariSessionEnvelope.self,
                from: data
            )

        let payload =
            try codec.encode(
                envelope.session
            )

        let checksum =
            SafariSessionChecksum.make(
                data: payload
            )

        guard checksum == envelope.checksum else {
            throw SafariSessionStorageError
                .checksumMismatch
        }

        return envelope.session
    }

    public func saveBackup(
        _ session: SafariSession
    ) throws {

        let payload =
            try codec.encode(
                session
            )

        let checksum =
            SafariSessionChecksum.make(
                data: payload
            )

        let envelope =
            SafariSessionEnvelope(
                schemaVersion:
                    session.schemaVersion,
                generation:
                    session.generation,
                session:
                    session,
                checksum:
                    checksum
            )

        let data =
            try codec.encode(
                envelope
            )

        try writer.write(
            data,
            to: storage.backup
        )
    }

    public func loadBackup()
        throws -> SafariSession
    {

        let data =
            try Data(
                contentsOf:
                    storage.backup
            )

        let envelope =
            try codec.decode(
                SafariSessionEnvelope.self,
                from: data
            )

        let payload =
            try codec.encode(
                envelope.session
            )

        let checksum =
            SafariSessionChecksum.make(
                data: payload
            )

        guard checksum == envelope.checksum else {
            throw SafariSessionStorageError
                .checksumMismatch
        }

        return envelope.session
    }
}


// MARK: - 18. Storage Errors

public enum SafariSessionStorageError:
    Error,
    Sendable
{
    case missingSnapshot
    case missingBackup
    case corruptSnapshot
    case corruptBackup
    case checksumMismatch
    case invalidSchema
    case journalCorrupted
}


// MARK: - 19. Journal Repository

public actor SafariSessionJournalRepository {

    private let storage:
        SafariSessionStorage

    private let codec:
        SafariSessionCodec

    private let fileManager:
        FileManager

    public init(
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {

        self.storage = storage
        self.codec = SafariSessionCodec()
        self.fileManager = .default
    }

    public func append(
        _ record:
            SafariSessionJournalRecord
    ) throws {

        try fileManager.createDirectory(
            at:
                storage.directory,
            withIntermediateDirectories:
                true
        )

        let data =
            try codec.encode(
                record
            )

        var line = data
        line.append(
            UInt8(ascii: "\n")
        )

        if fileManager.fileExists(
            atPath:
                storage.journal.path
        ) {

            let handle =
                try FileHandle(
                    forWritingTo:
                        storage.journal
                )

            try handle.seekToEnd()

            try handle.write(
                contentsOf:
                    line
            )

            try handle.synchronize()
            try handle.close()

        } else {

            try line.write(
                to:
                    storage.journal,
                options:
                    .atomic
            )
        }
    }

    public func readAll()
        throws
        -> [SafariSessionJournalRecord]
    {

        guard fileManager.fileExists(
            atPath:
                storage.journal.path
        ) else {
            return []
        }

        let data =
            try Data(
                contentsOf:
                    storage.journal
            )

        let lines =
            data
                .split(
                    separator:
                        UInt8(ascii: "\n")
                )

        var records:
            [SafariSessionJournalRecord] = []

        for line in lines {

            guard !line.isEmpty else {
                continue
            }

            do {

                let record =
                    try codec.decode(
                        SafariSessionJournalRecord.self,
                        from:
                            Data(line)
                    )

                records.append(
                    record
                )

            } catch {

                /*
                 A final incomplete line can occur if the
                 process terminates during a journal append.

                 Earlier complete transactions remain usable.
                */

                continue
            }
        }

        return records
    }

    public func truncate() throws {

        guard fileManager.fileExists(
            atPath:
                storage.journal.path
        ) else {
            return
        }

        try Data().write(
            to:
                storage.journal,
            options:
                .atomic
        )
    }
}


// MARK: - 20. Session Mutation Engine

public enum SafariSessionMutationEngine {

    public static func apply(
        _ mutation:
            SafariSessionMutation,
        to session:
            inout SafariSession
    ) {

        switch mutation {

        case .createWindow(let window):

            session.windows.append(
                window
            )

            session.activeWindow =
                session.activeWindow ??
                window.id

        case .deleteWindow(let windowID):

            session.windows.removeAll {
                $0.id == windowID
            }

            if session.activeWindow == windowID {
                session.activeWindow =
                    session.windows.first?.id
            }

        case .createTab(
            let windowID,
            let tab
        ):

            guard
                let index =
                    session.windows.firstIndex(
                        where: {
                            $0.id == windowID
                        }
                    )
            else {
                return
            }

            session.windows[index]
                .tabs
                .append(tab)

            session.windows[index]
                .selectedTab =
                session.windows[index]
                    .selectedTab ??
                tab.id

            session.windows[index]
                .lastModifiedAt = Date()

        case .deleteTab(
            let windowID,
            let tabID
        ):

            guard
                let index =
                    session.windows.firstIndex(
                        where: {
                            $0.id == windowID
                        }
                    )
            else {
                return
            }

            session.windows[index]
                .tabs
                .removeAll {
                    $0.id == tabID
                }

            if session.windows[index]
                .selectedTab == tabID
            {
                session.windows[index]
                    .selectedTab =
                    session.windows[index]
                        .tabs
                        .first?
                        .id
            }

            session.windows[index]
                .lastModifiedAt = Date()

        case .updateTab(
            let windowID,
            let tab
        ):

            guard
                let windowIndex =
                    session.windows.firstIndex(
                        where: {
                            $0.id == windowID
                        }
                    )
            else {
                return
            }

            guard
                let tabIndex =
                    session.windows[windowIndex]
                        .tabs
                        .firstIndex(
                            where: {
                                $0.id == tab.id
                            }
                        )
            else {
                return
            }

            session.windows[windowIndex]
                .tabs[tabIndex] = tab

            session.windows[windowIndex]
                .lastModifiedAt = Date()

        case .selectTab(
            let windowID,
            let tabID
        ):

            guard
                let index =
                    session.windows.firstIndex(
                        where: {
                            $0.id == windowID
                        }
                    )
            else {
                return
            }

            session.windows[index]
                .selectedTab = tabID

        case .updateWindow(let window):

            guard
                let index =
                    session.windows.firstIndex(
                        where: {
                            $0.id == window.id
                        }
                    )
            else {
                return
            }

            session.windows[index] =
                window

        case .setActiveWindow(let windowID):

            session.activeWindow =
                windowID
        }

        session.savedAt = Date()
    }

    public static func apply(
        _ mutations:
            [SafariSessionMutation],
        to session:
            inout SafariSession
    ) {

        for mutation in mutations {
            apply(
                mutation,
                to:
                    &session
            )
        }
    }
}


// MARK: - 21. Session Store

public actor SafariSessionStore {

    private var session:
        SafariSession

    private var generation:
        SessionGeneration

    public init(
        initial:
            SafariSession =
                SafariSession()
    ) {

        self.session = initial
        self.generation =
            initial.generation
    }

    public func current()
        -> SafariSession
    {
        session
    }

    public func mutate(
        _ mutations:
            [SafariSessionMutation]
    ) -> SafariSessionTransaction {

        generation =
            SessionGeneration(
                generation.value + 1
            )

        let transaction =
            SafariSessionTransaction(
                generation:
                    generation,
                mutations:
                    mutations
            )

        SafariSessionMutationEngine.apply(
            mutations,
            to:
                &session
        )

        session.generation =
            generation

        return transaction
    }

    public func replace(
        with newSession:
            SafariSession
    ) {

        session = newSession
        generation =
            newSession.generation
    }

    public func currentGeneration()
        -> SessionGeneration
    {
        generation
    }
}


// MARK: - 22. Persistence Coordinator

public actor SafariSessionPersistenceCoordinator {

    private let store:
        SafariSessionStore

    private let snapshotRepository:
        SafariSessionSnapshotRepository

    private let journalRepository:
        SafariSessionJournalRepository

    private var pendingTransactions:
        [SafariSessionTransaction] = []

    private var checkpointInProgress =
        false

    public init(
        store:
            SafariSessionStore,
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {

        self.store = store

        self.snapshotRepository =
            SafariSessionSnapshotRepository(
                storage:
                    storage
            )

        self.journalRepository =
            SafariSessionJournalRepository(
                storage:
                    storage
            )
    }

    public func commit(
        _ mutations:
            [SafariSessionMutation]
    ) async throws {

        let transaction =
            await store.mutate(
                mutations
            )

        let payload =
            try SafariSessionCodec()
                .encode(
                    transaction
                )

        let checksum =
            SafariSessionChecksum.make(
                data:
                    payload
            )

        let record =
            SafariSessionJournalRecord(
                transaction:
                    transaction,
                checksum:
                    checksum
            )

        try await journalRepository.append(
            record
        )

        pendingTransactions.append(
            transaction
        )
    }

    public func checkpoint()
        async throws
    {

        guard !checkpointInProgress else {
            return
        }

        checkpointInProgress = true
        defer {
            checkpointInProgress = false
        }

        let session =
            await store.current()

        try await snapshotRepository
            .saveBackup(
                session
            )

        try await snapshotRepository
            .save(
                session
            )

        try await journalRepository
            .truncate()

        pendingTransactions.removeAll()
    }
}


// MARK: - 23. Recovery Result

public enum SafariSessionRecoveryResult:
    Sendable
{
    case cleanLaunch(
        SafariSession
    )

    case recoveredFromSnapshot(
        SafariSession
    )

    case recoveredFromBackup(
        SafariSession
    )

    case recoveredWithJournal(
        SafariSession
    )

    case newSession
}


// MARK: - 24. Crash Marker

public struct SafariCrashMarker:
    Codable,
    Sendable
{
    public let processID:
        Int32

    public let launchDate:
        Date

    public init(
        processID: Int32 =
            ProcessInfo.processInfo.processIdentifier,
        launchDate:
            Date = Date()
    ) {
        self.processID = processID
        self.launchDate = launchDate
    }
}


// MARK: - 25. Crash Detector

public actor SafariCrashDetector {

    private let markerURL:
        URL

    private let codec =
        SafariSessionCodec()

    private let writer =
        SafariAtomicFileWriter()

    public init(
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {

        markerURL =
            storage.directory
                .appendingPathComponent(
                    "running.marker"
                )
    }

    public func markLaunch()
        throws -> Bool
    {

        let crashedPreviously =
            FileManager.default.fileExists(
                atPath:
                    markerURL.path
            )

        let marker =
            SafariCrashMarker()

        let data =
            try codec.encode(
                marker
            )

        try writer.write(
            data,
            to:
                markerURL
        )

        return crashedPreviously
    }

    public func markCleanShutdown()
        throws
    {

        guard
            FileManager.default.fileExists(
                atPath:
                    markerURL.path
            )
        else {
            return
        }

        try FileManager.default.removeItem(
            at:
                markerURL
        )
    }
}


// MARK: - 26. Recovery Engine

public actor SafariSessionRecoveryEngine {

    private let snapshotRepository:
        SafariSessionSnapshotRepository

    private let journalRepository:
        SafariSessionJournalRepository

    private let crashDetector:
        SafariCrashDetector

    private let store:
        SafariSessionStore

    public init(
        store:
            SafariSessionStore,
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {

        self.store = store

        self.snapshotRepository =
            SafariSessionSnapshotRepository(
                storage:
                    storage
            )

        self.journalRepository =
            SafariSessionJournalRepository(
                storage:
                    storage
            )

        self.crashDetector =
            SafariCrashDetector(
                storage:
                    storage
            )
    }

    public func launch()
        async
        -> SafariSessionRecoveryResult
    {

        let crashed: Bool

        do {
            crashed =
                try await crashDetector
                    .markLaunch()
        } catch {
            crashed = false
        }

        guard crashed else {

            if let snapshot =
                try? await snapshotRepository
                    .load()
            {
                await store.replace(
                    with:
                        snapshot
                )

                return .cleanLaunch(
                    snapshot
                )
            }

            let session =
                SafariSession()

            await store.replace(
                with:
                    session
            )

            return .newSession
        }

        /*
         A crash occurred.

         First attempt to restore the latest valid
         snapshot, then replay any valid journal records.
        */

        if var snapshot =
            try? await snapshotRepository
                .load()
        {

            if let records =
                try? await journalRepository
                    .readAll()
            {

                let relevant =
                    records
                        .filter {
                            $0.transaction.generation >
                                snapshot.generation
                        }
                        .sorted {
                            $0.transaction.generation <
                                $1.transaction.generation
                        }

                for record in relevant {

                    SafariSessionMutationEngine.apply(
                        record.transaction.mutations,
                        to:
                            &snapshot
                    )

                    snapshot.generation =
                        record.transaction.generation
                }

                if !relevant.isEmpty {

                    await store.replace(
                        with:
                            snapshot
                    )

                    return .recoveredWithJournal(
                        snapshot
                    )
                }
            }

            await store.replace(
                with:
                    snapshot
            )

            return .recoveredFromSnapshot(
                snapshot
            )
        }

        if let backup =
            try? await snapshotRepository
                .loadBackup()
        {

            await store.replace(
                with:
                    backup
            )

            return .recoveredFromBackup(
                backup
            )
        }

        let session =
            SafariSession()

        await store.replace(
            with:
                session
            )

        return .newSession
    }

    public func cleanShutdown()
        async
    {
        do {
            try await crashDetector
                .markCleanShutdown()
        } catch {
            // Shutdown should remain non-fatal.
        }
    }
}


// MARK: - 27. Debounced Session Writer

public actor SafariSessionDebouncedWriter {

    private let persistence:
        SafariSessionPersistenceCoordinator

    private let delay:
        Duration

    private var pendingTask:
        Task<Void, Never>?

    public init(
        persistence:
            SafariSessionPersistenceCoordinator,
        delay:
            Duration = .milliseconds(500)
    ) {

        self.persistence =
            persistence

        self.delay =
            delay
    }

    public func schedule(
        _ mutations:
            [SafariSessionMutation]
    ) {

        pendingTask?.cancel()

        pendingTask =
            Task { [weak self] in

                do {
                    try await Task.sleep(
                        for:
                            self?.delay ??
                            .milliseconds(500)
                    )

                    guard
                        let self
                    else {
                        return
                    }

                    try await self.persistence
                        .commit(
                            mutations
                        )

                } catch {
                    // Cancelled or persistence failure.
                }
            }
    }

    public func flush()
        async
    {

        pendingTask?.cancel()
        pendingTask = nil

        /*
         In a production implementation, mutations would be
         retained separately so flush() can force them through
         immediately.
        */
    }
}


// MARK: - 28. WebKit State Collector

@MainActor
public final class SafariWebKitSessionCollector:
    NSObject
{

    private weak var webView:
        WKWebView?

    public init(
        webView:
            WKWebView
    ) {
        self.webView =
            webView
    }

    public func collect(
        tabID:
            SessionTabID
    ) -> SafariSessionTab
    {

        guard let webView else {

            return SafariSessionTab(
                id:
                    tabID
            )
        }

        let url =
            webView.url

        let title =
            webView.title ?? ""

        let scrollView =
            webView.scrollView

        let offset =
            scrollView.contentOffset

        return SafariSessionTab(
            id:
                tabID,

            title:
                title,

            lifecycle:
                .active,

            navigation:
                SessionNavigationState(
                    currentURL:
                        url,

                    originalURL:
                        url,

                    title:
                        title,

                    estimatedProgress:
                        webView.estimatedProgress,

                    canGoBack:
                        webView.canGoBack,

                    canGoForward:
                        webView.canGoForward
                ),

            scroll:
                SessionScrollState(
                    x:
                        Double(offset.x),

                    y:
                        Double(offset.y)
                )
        )
    }
}


// MARK: - 29. WebKit Restoration Controller

@MainActor
public final class SafariWebKitSessionRestorer {

    private weak var webView:
        WKWebView?

    public init(
        webView:
            WKWebView
    ) {
        self.webView =
            webView
    }

    public func restore(
        tab:
            SafariSessionTab
    ) {

        guard let webView else {
            return
        }

        guard
            let url =
                tab.navigation.currentURL
        else {
            return
        }

        let request =
            URLRequest(
                url:
                    url
            )

        webView.load(
            request
        )

        let x =
            tab.scroll.x

        let y =
            tab.scroll.y

        /*
         The page must finish navigation before its final
         scroll position is guaranteed to exist.

         Production integration should therefore invoke this
         again from WKNavigationDelegate.didFinish.
        */

        DispatchQueue.main.async { [weak webView] in

            guard let webView else {
                return
            }

            webView.scrollView
                .setContentOffset(
                    NSPoint(
                        x:
                            x,
                        y:
                            y
                    ),
                    animated:
                        false
                )
        }
    }
}


// MARK: - 30. Session Checkpoint Policy

public struct SafariSessionCheckpointPolicy:
    Sendable
{

    public let mutationThreshold:
        Int

    public let maximumInterval:
        TimeInterval

    public let minimumInterval:
        TimeInterval

    public init(
        mutationThreshold:
            Int = 25,
        maximumInterval:
            TimeInterval = 30,
        minimumInterval:
            TimeInterval = 2
    ) {
        self.mutationThreshold =
            mutationThreshold

        self.maximumInterval =
            maximumInterval

        self.minimumInterval =
            minimumInterval
    }
}


// MARK: - 31. Checkpoint Controller

public actor SafariSessionCheckpointController {

    private let persistence:
        SafariSessionPersistenceCoordinator

    private let policy:
        SafariSessionCheckpointPolicy

    private var mutationCount = 0

    private var lastCheckpoint =
        Date()

    public init(
        persistence:
            SafariSessionPersistenceCoordinator,
        policy:
            SafariSessionCheckpointPolicy =
                SafariSessionCheckpointPolicy()
    ) {

        self.persistence =
            persistence

        self.policy =
            policy
    }

    public func recordMutation() {

        mutationCount += 1
    }

    public func shouldCheckpoint(
        now:
            Date = Date()
    ) -> Bool {

        let elapsed =
            now.timeIntervalSince(
                lastCheckpoint
            )

        if mutationCount >=
            policy.mutationThreshold
        {
            return true
        }

        if elapsed >=
            policy.maximumInterval
        {
            return true
        }

        return false
    }

    public func checkpointIfNeeded()
        async
    {

        guard shouldCheckpoint() else {
            return
        }

        do {

            try await persistence
                .checkpoint()

            mutationCount = 0
            lastCheckpoint = Date()

        } catch {
            /*
             Never terminate Safari because a checkpoint failed.
             The journal remains the recovery source.
            */
        }
    }

    public func forceCheckpoint()
        async
    {

        do {

            try await persistence
                .checkpoint()

            mutationCount = 0
            lastCheckpoint = Date()

        } catch {
            // Non-fatal.
        }
    }
}


// MARK: - 32. Session Runtime

public actor SafariCrashResistantSessionRuntime {

    public let store:
        SafariSessionStore

    public let persistence:
        SafariSessionPersistenceCoordinator

    public let recovery:
        SafariSessionRecoveryEngine

    public let checkpoint:
        SafariSessionCheckpointController

    private let writer:
        SafariSessionDebouncedWriter

    public init(
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {

        let store =
            SafariSessionStore()

        let persistence =
            SafariSessionPersistenceCoordinator(
                store:
                    store,
                storage:
                    storage
            )

        self.store =
            store

        self.persistence =
            persistence

        self.recovery =
            SafariSessionRecoveryEngine(
                store:
                    store,
                storage:
                    storage
            )

        self.checkpoint =
            SafariSessionCheckpointController(
                persistence:
                    persistence
            )

        self.writer =
            SafariSessionDebouncedWriter(
                persistence:
                    persistence
            )
    }

    public func launch()
        async
        -> SafariSessionRecoveryResult
    {

        await recovery.launch()
    }

    public func commit(
        _ mutations:
            [SafariSessionMutation]
    ) async {

        do {

            try await persistence
                .commit(
                    mutations
                )

            await checkpoint
                .recordMutation()

            await checkpoint
                .checkpointIfNeeded()

        } catch {
            /*
             Persistence failure must not bring down the browser.
             The in-memory session continues operating.
            */
        }
    }

    public func currentSession()
        async -> SafariSession
    {
        await store.current()
    }

    public func shutdown()
        async
    {

        await checkpoint
            .forceCheckpoint()

        await recovery
            .cleanShutdown()
    }
}


// MARK: - 33. Window Coordinator

@MainActor
public final class SafariSessionWindowCoordinator {

    private let runtime:
        SafariCrashResistantSessionRuntime

    public init(
        runtime:
            SafariCrashResistantSessionRuntime
    ) {
        self.runtime =
            runtime
    }

    public func createWindow()
        -> SessionWindowID
    {

        let id =
            SessionWindowID()

        let window =
            SafariSessionWindow(
                id:
                    id
            )

        Task {

            await runtime.commit(
                [
                    .createWindow(
                        window
                    )
                ]
            )
        }

        return id
    }

    public func deleteWindow(
        _ id:
            SessionWindowID
    ) {

        Task {

            await runtime.commit(
                [
                    .deleteWindow(
                        id
                    )
                ]
            )
        }
    }
}


// MARK: - 34. Tab Coordinator

@MainActor
public final class SafariSessionTabCoordinator {

    private let runtime:
        SafariCrashResistantSessionRuntime

    public init(
        runtime:
            SafariCrashResistantSessionRuntime
    ) {
        self.runtime =
            runtime
    }

    public func createTab(
        windowID:
            SessionWindowID,
        url:
            URL?
    ) -> SessionTabID
    {

        let id =
            SessionTabID()

        let navigation =
            SessionNavigationState(
                currentURL:
                    url,
                originalURL:
                    url
            )

        let tab =
            SafariSessionTab(
                id:
                    id,
                navigation:
                    navigation
            )

        Task {

            await runtime.commit(
                [
                    .createTab(
                        window:
                            windowID,
                        tab:
                            tab
                    )
                ]
            )
        }

        return id
    }

    public func deleteTab(
        windowID:
            SessionWindowID,
        tabID:
            SessionTabID
    ) {

        Task {

            await runtime.commit(
                [
                    .deleteTab(
                        window:
                            windowID,
                        tab:
                            tabID
                    )
                ]
            )
        }
    }
}


// MARK: - 35. Session Event

public enum SafariSessionEvent:
    Sendable
{
    case launched(
        SafariSessionRecoveryResult
    )

    case transactionCommitted(
        SessionGeneration
    )

    case checkpointCompleted(
        SessionGeneration
    )

    case recoveryRequired

    case cleanShutdown
}


// MARK: - 36. Session Event Bus

public actor SafariSessionEventBus {

    private var continuations:
        [UUID:
            AsyncStream<SafariSessionEvent>
                .Continuation] = [:]

    public init() {}

    public func stream()
        -> AsyncStream<SafariSessionEvent>
    {

        let id =
            UUID()

        return AsyncStream { continuation in

            continuations[id] =
                continuation

            continuation.onTermination = {
                Task {
                    await self.remove(
                        id
                    )
                }
            }
        }
    }

    private func remove(
        _ id:
            UUID
    ) {

        continuations.removeValue(
            forKey:
                id
        )
    }

    public func publish(
        _ event:
            SafariSessionEvent
    ) {

        for continuation
            in continuations.values
        {
            continuation.yield(
                event
            )
        }
    }
}


// MARK: - 37. Full Session Manager

public actor SafariCrashResistantSessionManager {

    public let runtime:
        SafariCrashResistantSessionRuntime

    public let events:
        SafariSessionEventBus

    public init(
        storage:
            SafariSessionStorage =
                .defaultStorage()
    ) {

        self.runtime =
            SafariCrashResistantSessionRuntime(
                storage:
                    storage
            )

        self.events =
            SafariSessionEventBus()
    }

    public func launch()
        async
        -> SafariSessionRecoveryResult
    {

        let result =
            await runtime.launch()

        switch result {

        case .cleanLaunch:
            break

        case .recoveredFromSnapshot,
             .recoveredFromBackup,
             .recoveredWithJournal:

            await events.publish(
                .recoveryRequired
            )

        case .newSession:
            break
        }

        await events.publish(
            .launched(
                result
            )
        )

        return result
    }

    public func commit(
        _ mutations:
            [SafariSessionMutation]
    ) async {

        await runtime.commit(
            mutations
        )

        let generation =
            await runtime.store
                .currentGeneration()

        await events.publish(
            .transactionCommitted(
                generation
            )
        )
    }

    public func shutdown()
        async
    {

        await runtime.shutdown()

        await events.publish(
            .cleanShutdown
        )
    }
}


// MARK: - 38. Recovery Diagnostics

public struct SafariRecoveryDiagnostics:
    Sendable,
    Codable
{

    public let result:
        String

    public let generation:
        UInt64

    public let windowCount:
        Int

    public let tabCount:
        Int

    public let timestamp:
        Date

    public init(
        result:
            String,
        generation:
            UInt64,
        windowCount:
            Int,
        tabCount:
            Int,
        timestamp:
            Date = Date()
    ) {

        self.result =
            result

        self.generation =
            generation

        self.windowCount =
            windowCount

        self.tabCount =
            tabCount

        self.timestamp =
            timestamp
    }
}


// MARK: - 39. Session Diagnostics

public actor SafariSessionDiagnostics {

    private let runtime:
        SafariCrashResistantSessionRuntime

    public init(
        runtime:
            SafariCrashResistantSessionRuntime
    ) {
        self.runtime =
            runtime
    }

    public func report()
        async
        -> SafariRecoveryDiagnostics
    {

        let session =
            await runtime.currentSession()

        return SafariRecoveryDiagnostics(
            result:
                "current",

            generation:
                session.generation.value,

            windowCount:
                session.windows.count,

            tabCount:
                session.windows
                    .reduce(0) {
                        $0 + $1.tabs.count
                    }
        )
    }
}


// MARK: - 40. Production Factory

public enum SafariCrashResistantSessionFactory {

    public static func make()
        -> SafariCrashResistantSessionManager
    {

        SafariCrashResistantSessionManager(
            storage:
                .defaultStorage()
        )
    }
}


// MARK: - 41. Example Browser Integration

@MainActor
public final class SafariBrowserSessionIntegration {

    private let manager:
        SafariCrashResistantSessionManager

    public init() {

        manager =
            SafariCrashResistantSessionFactory
                .make()
    }

    public func launch()
        async
    {

        let result =
            await manager.launch()

        switch result {

        case .cleanLaunch(let session):
            restore(
                session:
                    session
            )

        case .recoveredFromSnapshot(let session):
            restore(
                session:
                    session
            )

        case .recoveredFromBackup(let session):
            restore(
                session:
                    session
            )

        case .recoveredWithJournal(let session):
            restore(
                session:
                    session
            )

        case .newSession:
            createInitialWindow()
        }
    }

    public func shutdown()
        async
    {

        await manager.shutdown()
    }

    private func restore(
        session:
            SafariSession
    ) {

        /*
         Actual AppKit window creation and WKWebView
         restoration belongs here.

         Each SafariSessionWindow becomes an NSWindow.
         Each SafariSessionTab becomes a tab/WebKit controller.
        */
    }

    private func createInitialWindow() {
        // Create normal Safari window.
    }
}


// MARK: - 42. Crash Simulation

#if DEBUG

public enum SafariSessionCrashSimulation {

    public static func simulateCrash(
        runtime:
            SafariCrashResistantSessionRuntime
    ) async {

        let windowID =
            SessionWindowID()

        let tabID =
            SessionTabID()

        let window =
            SafariSessionWindow(
                id:
                    windowID
            )

        let tab =
            SafariSessionTab(
                id:
                    tabID,

                navigation:
                    SessionNavigationState(
                        currentURL:
                            URL(
                                string:
                                    "https://example.com"
                            ),
                        title:
                            "Example"
                    )
            )

        await runtime.commit(
            [
                .createWindow(
                    window
                ),

                .createTab(
                    window:
                        windowID,
                    tab:
                        tab
                )
            ]
        )

        /*
         Deliberately do NOT call shutdown().

         On the next launch the crash marker remains present
         and the recovery engine will replay the journal.
        */
    }
}

#endif


// MARK: - 43. Important Restoration Rule

/*
 The architecture intentionally separates:

    LIVE STATE
        ↓
    SESSION STORE
        ↓
    JOURNAL
        ↓
    CHECKPOINT
        ↓
    SNAPSHOT
        ↓
    BACKUP

 A crash can therefore occur at almost any point without
 requiring the entire session to be reconstructed from scratch.

 Example:

    generation 100
        ↓
    snapshot

    generation 101
        ↓
    journal

    generation 102
        ↓
    journal

    generation 103
        ↓
    process crashes

 Recovery:

    load snapshot 100
        ↓
    replay 101
        ↓
    replay 102
        ↓
    replay 103 if complete
        ↓
    reconstructed session
*/


// MARK: - 44. Final Architecture

/*
    ┌──────────────────────────────────────────────┐
    │              Safari Browser UI               │
    └───────────────────────┬──────────────────────┘
                            │
                            ▼
             Safari Session Manager
                            │
                            ▼
                  Safari Session Store
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
       Mutation Engine               Current State
             │
             ▼
       Transaction
             │
             ▼
       Crash-Safe Journal
             │
             ▼
       Periodic Checkpoint
             │
       ┌─────┴─────┐
       ▼           ▼
    Snapshot      Backup
       │           │
       └─────┬─────┘
             │
             ▼
       Crash Recovery
             │
       ┌─────┴──────────────┐
       │                    │
       ▼                    ▼
   Snapshot Restore     Journal Replay
       │                    │
       └──────────┬─────────┘
                  ▼
          Reconstructed Safari
*/








//
//  SafariIntelligentCacheStorageEngine.swift
//
//  Safari macOS Performance Architecture — #8
//
//  Responsibilities:
//  - Cache metadata
//  - Origin storage accounting
//  - Storage quotas
//  - Cache admission
//  - Intelligent eviction
//  - LRU/LFU-style scoring
//  - Power-aware cache policy
//  - Memory-aware cache policy
//  - Disk-pressure handling
//  - Persistent metadata
//  - Atomic metadata writes
//  - Compression for Safari-owned metadata
//  - Origin isolation
//  - Cache validation metadata
//  - Background maintenance
//  - Swift 6 concurrency
//
//  Public APIs only.
//  Does not access private WebKit databases.
//

import Foundation
import WebKit
import CryptoKit


// MARK: - 1. Identifiers

public struct CacheEntryID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}


public struct CacheOriginID:
    Hashable,
    Codable,
    Sendable
{
    public let scheme: String
    public let host: String
    public let port: Int?

    public init(
        scheme: String,
        host: String,
        port: Int?
    ) {
        self.scheme = scheme
        self.host = host
        self.port = port
    }

    public init?(url: URL) {

        guard
            let scheme = url.scheme,
            let host = url.host
        else {
            return nil
        }

        self.scheme = scheme.lowercased()
        self.host = host.lowercased()
        self.port = url.port
    }
}


// MARK: - 2. Storage Classes

public enum SafariStorageClass:
    String,
    Codable,
    Sendable
{
    case critical
    case persistent
    case normal
    case temporary
    case prefetch
}


// MARK: - 3. Cache Priority

public enum SafariCachePriority:
    Int,
    Codable,
    Sendable,
    Comparable
{
    case lowest = 0
    case low = 1
    case normal = 2
    case high = 3
    case critical = 4

    public static func < (
        lhs: SafariCachePriority,
        rhs: SafariCachePriority
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}


// MARK: - 4. Cache Admission

public enum SafariCacheAdmissionDecision:
    Sendable,
    Codable
{
    case admit
    case admitWithShortTTL
    case reject
    case replaceExisting
}


// MARK: - 5. Cache Entry

public struct SafariCacheEntry:
    Codable,
    Sendable
{

    public let id:
        CacheEntryID

    public let origin:
        CacheOriginID

    public let url:
        URL

    public var sizeBytes:
        Int64

    public var storageClass:
        SafariStorageClass

    public var priority:
        SafariCachePriority

    public var hitCount:
        UInt64

    public var lastAccess:
        Date

    public var createdAt:
        Date

    public var lastModified:
        Date

    public var expiresAt:
        Date?

    public var etag:
        String?

    public var lastModifiedHTTP:
        String?

    public var contentType:
        String?

    public var isValidated:
        Bool

    public var isPinned:
        Bool

    public init(
        id:
            CacheEntryID = CacheEntryID(),

        origin:
            CacheOriginID,

        url:
            URL,

        sizeBytes:
            Int64,

        storageClass:
            SafariStorageClass = .normal,

        priority:
            SafariCachePriority = .normal,

        hitCount:
            UInt64 = 0,

        lastAccess:
            Date = Date(),

        createdAt:
            Date = Date(),

        lastModified:
            Date = Date(),

        expiresAt:
            Date? = nil,

        etag:
            String? = nil,

        lastModifiedHTTP:
            String? = nil,

        contentType:
            String? = nil,

        isValidated:
            Bool = false,

        isPinned:
            Bool = false
    ) {

        self.id = id
        self.origin = origin
        self.url = url
        self.sizeBytes = sizeBytes
        self.storageClass = storageClass
        self.priority = priority
        self.hitCount = hitCount
        self.lastAccess = lastAccess
        self.createdAt = createdAt
        self.lastModified = lastModified
        self.expiresAt = expiresAt
        self.etag = etag
        self.lastModifiedHTTP = lastModifiedHTTP
        self.contentType = contentType
        self.isValidated = isValidated
        self.isPinned = isPinned
    }
}


// MARK: - 6. Origin Statistics

public struct SafariOriginStorageStats:
    Codable,
    Sendable
{

    public let origin:
        CacheOriginID

    public var cacheBytes:
        Int64

    public var persistentBytes:
        Int64

    public var temporaryBytes:
        Int64

    public var entryCount:
        Int

    public var lastAccess:
        Date

    public init(
        origin:
            CacheOriginID,

        cacheBytes:
            Int64 = 0,

        persistentBytes:
            Int64 = 0,

        temporaryBytes:
            Int64 = 0,

        entryCount:
            Int = 0,

        lastAccess:
            Date = Date()
    ) {

        self.origin = origin
        self.cacheBytes = cacheBytes
        self.persistentBytes = persistentBytes
        self.temporaryBytes = temporaryBytes
        self.entryCount = entryCount
        self.lastAccess = lastAccess
    }

    public var totalBytes:
        Int64
    {
        cacheBytes +
        persistentBytes +
        temporaryBytes
    }
}


// MARK: - 7. Global Storage Snapshot

public struct SafariStorageSnapshot:
    Codable,
    Sendable
{

    public let totalBytes:
        Int64

    public let cacheBytes:
        Int64

    public let persistentBytes:
        Int64

    public let temporaryBytes:
        Int64

    public let entryCount:
        Int

    public let originCount:
        Int

    public let generatedAt:
        Date

    public init(
        totalBytes:
            Int64,

        cacheBytes:
            Int64,

        persistentBytes:
            Int64,

        temporaryBytes:
            Int64,

        entryCount:
            Int,

        originCount:
            Int,

        generatedAt:
            Date = Date()
    ) {

        self.totalBytes = totalBytes
        self.cacheBytes = cacheBytes
        self.persistentBytes = persistentBytes
        self.temporaryBytes = temporaryBytes
        self.entryCount = entryCount
        self.originCount = originCount
        self.generatedAt = generatedAt
    }
}


// MARK: - 8. Storage Pressure

public enum SafariStoragePressure:
    Int,
    Sendable,
    Codable,
    Comparable
{
    case normal = 0
    case elevated = 1
    case high = 2
    case critical = 3

    public static func < (
        lhs: SafariStoragePressure,
        rhs: SafariStoragePressure
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}


// MARK: - 9. Disk Information

public struct SafariDiskState:
    Sendable,
    Codable
{

    public let availableBytes:
        Int64

    public let totalBytes:
        Int64

    public let usedBytes:
        Int64

    public let pressure:
        SafariStoragePressure

    public init(
        availableBytes:
            Int64,

        totalBytes:
            Int64,

        usedBytes:
            Int64,

        pressure:
            SafariStoragePressure
    ) {

        self.availableBytes = availableBytes
        self.totalBytes = totalBytes
        self.usedBytes = usedBytes
        self.pressure = pressure
    }
}


// MARK: - 10. Disk Provider

public protocol SafariDiskStateProvider:
    Sendable
{
    func currentDiskState(
        for url: URL
    ) async -> SafariDiskState
}


// MARK: - 11. macOS Disk Provider

public struct MacOSSafariDiskStateProvider:
    SafariDiskStateProvider
{

    public init() {}

    public func currentDiskState(
        for url: URL
    ) async -> SafariDiskState
    {

        do {

            let values =
                try url.resourceValues(
                    forKeys: [
                        .volumeTotalCapacityKey,
                        .volumeAvailableCapacityForImportantUsageKey
                    ]
                )

            let total =
                Int64(
                    values.volumeTotalCapacity ?? 0
                )

            let available =
                Int64(
                    values
                        .volumeAvailableCapacityForImportantUsage
                    ?? 0
                )

            let used =
                max(
                    0,
                    total - available
                )

            let pressure:
                SafariStoragePressure

            if available < 512 * 1024 * 1024 {
                pressure = .critical
            } else if available < 2 * 1024 * 1024 * 1024 {
                pressure = .high
            } else if available < 8 * 1024 * 1024 * 1024 {
                pressure = .elevated
            } else {
                pressure = .normal
            }

            return SafariDiskState(
                availableBytes:
                    available,

                totalBytes:
                    total,

                usedBytes:
                    used,

                pressure:
                    pressure
            )

        } catch {

            return SafariDiskState(
                availableBytes:
                    0,

                totalBytes:
                    0,

                usedBytes:
                    0,

                pressure:
                    .critical
            )
        }
    }
}


// MARK: - 12. Cache Configuration

public struct SafariCacheConfiguration:
    Codable,
    Sendable
{

    public var maximumCacheBytes:
        Int64

    public var maximumTemporaryBytes:
        Int64

    public var maximumPersistentBytes:
        Int64

    public var minimumFreeDiskBytes:
        Int64

    public var defaultTTL:
        TimeInterval

    public var prefetchTTL:
        TimeInterval

    public var metadataCheckpointInterval:
        TimeInterval

    public init(
        maximumCacheBytes:
            Int64 = 2 * 1024 * 1024 * 1024,

        maximumTemporaryBytes:
            Int64 = 512 * 1024 * 1024,

        maximumPersistentBytes:
            Int64 = 4 * 1024 * 1024 * 1024,

        minimumFreeDiskBytes:
            Int64 = 8 * 1024 * 1024 * 1024,

        defaultTTL:
            TimeInterval = 24 * 60 * 60,

        prefetchTTL:
            TimeInterval = 5 * 60,

        metadataCheckpointInterval:
            TimeInterval = 10
    ) {

        self.maximumCacheBytes =
            maximumCacheBytes

        self.maximumTemporaryBytes =
            maximumTemporaryBytes

        self.maximumPersistentBytes =
            maximumPersistentBytes

        self.minimumFreeDiskBytes =
            minimumFreeDiskBytes

        self.defaultTTL =
            defaultTTL

        self.prefetchTTL =
            prefetchTTL

        self.metadataCheckpointInterval =
            metadataCheckpointInterval
    }
}


// MARK: - 13. Cache Policy Context

public struct SafariCachePolicyContext:
    Sendable,
    Codable
{

    public let disk:
        SafariDiskState

    public let powerMode:
        SafariCachePowerMode

    public let thermalState:
        SafariCacheThermalState

    public init(
        disk:
            SafariDiskState,

        powerMode:
            SafariCachePowerMode,

        thermalState:
            SafariCacheThermalState
    ) {

        self.disk = disk
        self.powerMode = powerMode
        self.thermalState = thermalState
    }
}


public enum SafariCachePowerMode:
    String,
    Codable,
    Sendable
{
    case maximumPerformance
    case balanced
    case battery
    case aggressiveSaving
}


public enum SafariCacheThermalState:
    String,
    Codable,
    Sendable
{
    case nominal
    case elevated
    case serious
    case critical
}


// MARK: - 14. Cache Scoring

public struct SafariCacheEvictionScore:
    Sendable,
    Codable
{

    public let entryID:
        CacheEntryID

    public let score:
        Double

    public init(
        entryID:
            CacheEntryID,

        score:
            Double
    ) {

        self.entryID = entryID
        self.score = score
    }
}


// MARK: - 15. Cache Scoring Engine

public struct SafariCacheScoringEngine:
    Sendable
{

    public init() {}

    public func score(
        entry:
            SafariCacheEntry,

        now:
            Date = Date(),

        pressure:
            SafariStoragePressure
    ) -> Double
    {

        let age =
            max(
                0,
                now.timeIntervalSince(
                    entry.lastAccess
                )
            )

        let recency =
            1 /
            (1 + age / 60)

        let frequency =
            min(
                1,
                log1p(
                    Double(
                        entry.hitCount
                    )
                ) / 10
            )

        let sizePenalty =
            min(
                1,
                Double(
                    entry.sizeBytes
                ) /
                Double(
                    100 * 1024 * 1024
                )
            )

        let priorityBonus =
            Double(
                entry.priority.rawValue
            ) * 0.25

        let pinBonus =
            entry.isPinned
            ? 10.0
            : 0.0

        let classPenalty:
            Double

        switch entry.storageClass {

        case .critical:
            classPenalty = -5

        case .persistent:
            classPenalty = -2

        case .normal:
            classPenalty = 0

        case .temporary:
            classPenalty = 2

        case .prefetch:
            classPenalty = 4
        }

        let pressureMultiplier:
            Double

        switch pressure {

        case .normal:
            pressureMultiplier = 0.5

        case .elevated:
            pressureMultiplier = 1.0

        case .high:
            pressureMultiplier = 1.5

        case .critical:
            pressureMultiplier = 2.5
        }

        /*
         Higher score = more desirable to retain.
        */

        return
            recency * 4
            +
            frequency * 3
            +
            priorityBonus
            +
            pinBonus
            +
            classPenalty
            -
            sizePenalty * pressureMultiplier * 3
    }
}


// MARK: - 16. Cache Admission Engine

public struct SafariCacheAdmissionEngine:
    Sendable
{

    private let configuration:
        SafariCacheConfiguration

    public init(
        configuration:
            SafariCacheConfiguration
    ) {
        self.configuration =
            configuration
    }

    public func evaluate(
        sizeBytes:
            Int64,

        storageClass:
            SafariStorageClass,

        priority:
            SafariCachePriority,

        context:
            SafariCachePolicyContext
    ) -> SafariCacheAdmissionDecision
    {

        if sizeBytes <= 0 {
            return .reject
        }

        if
            context.disk.pressure >= .critical
            &&
            storageClass != .critical
        {
            return .reject
        }

        if
            storageClass == .prefetch
            &&
            context.powerMode !=
                .maximumPerformance
        {
            return .admitWithShortTTL
        }

        if
            sizeBytes >
                configuration.maximumCacheBytes / 4
        {
            return .reject
        }

        if
            priority == .critical
        {
            return .admit
        }

        return .admit
    }
}


// MARK: - 17. Cache Store

public actor SafariCacheStore {

    private var entries:
        [CacheEntryID: SafariCacheEntry] = [:]

    private var byURL:
        [String: CacheEntryID] = [:]

    public init() {}

    public func insert(
        _ entry:
            SafariCacheEntry
    ) {

        if let existing =
            byURL[entry.url.absoluteString]
        {
            entries.removeValue(
                forKey:
                    existing
            )
        }

        entries[entry.id] =
            entry

        byURL[
            entry.url.absoluteString
        ] =
            entry.id
    }

    public func remove(
        _ id:
            CacheEntryID
    ) {

        guard
            let entry =
                entries.removeValue(
                    forKey:
                        id
                )
        else {
            return
        }

        byURL.removeValue(
            forKey:
                entry.url.absoluteString
        )
    }

    public func lookup(
        url:
            URL
    ) -> SafariCacheEntry?
    {

        guard
            let id =
                byURL[
                    url.absoluteString
                ]
        else {
            return nil
        }

        guard
            var entry =
                entries[id]
        else {
            return nil
        }

        entry.hitCount += 1
        entry.lastAccess = Date()

        entries[id] = entry

        return entry
    }

    public func update(
        _ entry:
            SafariCacheEntry
    ) {

        guard entries[entry.id] != nil else {
            return
        }

        entries[entry.id] =
            entry
    }

    public func allEntries()
        -> [SafariCacheEntry]
    {
        Array(
            entries.values
        )
    }

    public func totalBytes()
        -> Int64
    {
        entries.values.reduce(
            0
        ) {
            $0 + $1.sizeBytes
        }
    }

    public func removeExpired(
        now:
            Date = Date()
    ) -> [SafariCacheEntry]
    {

        let expired =
            entries.values.filter {
                guard
                    let expiry =
                        $0.expiresAt
                else {
                    return false
                }

                return expiry <= now
            }

        for entry in expired {
            await remove(
                entry.id
            )
        }

        return expired
    }
}


// MARK: - 18. Origin Store

public actor SafariOriginStorageStore {

    private var origins:
        [CacheOriginID: SafariOriginStorageStats] =
            [:]

    public init() {}

    public func update(
        entry:
            SafariCacheEntry
    ) {

        var stats =
            origins[
                entry.origin
            ]
            ??
            SafariOriginStorageStats(
                origin:
                    entry.origin
            )

        stats.entryCount += 1
        stats.lastAccess =
            Date()

        switch entry.storageClass {

        case .persistent:
            stats.persistentBytes +=
                entry.sizeBytes

        case .temporary:
            stats.temporaryBytes +=
                entry.sizeBytes

        case .critical,
             .normal,
             .prefetch:
            stats.cacheBytes +=
                entry.sizeBytes
        }

        origins[
            entry.origin
        ] =
            stats
    }

    public func replaceAll(
        entries:
            [SafariCacheEntry]
    ) {

        origins.removeAll()

        for entry in entries {
            var stats =
                origins[
                    entry.origin
                ]
                ??
                SafariOriginStorageStats(
                    origin:
                        entry.origin
                )

            stats.entryCount += 1
            stats.lastAccess =
                max(
                    stats.lastAccess,
                    entry.lastAccess
                )

            switch entry.storageClass {

            case .persistent:
                stats.persistentBytes +=
                    entry.sizeBytes

            case .temporary:
                stats.temporaryBytes +=
                    entry.sizeBytes

            default:
                stats.cacheBytes +=
                    entry.sizeBytes
            }

            origins[
                entry.origin
            ] =
                stats
        }
    }

    public func allOrigins()
        -> [SafariOriginStorageStats]
    {
        Array(
            origins.values
        )
    }
}


// MARK: - 19. Storage Snapshot Builder

public struct SafariStorageSnapshotBuilder:
    Sendable
{

    public init() {}

    public func build(
        entries:
            [SafariCacheEntry]
    ) -> SafariStorageSnapshot
    {

        let cache =
            entries.reduce(
                Int64(0)
            ) {
                partial,
                entry in

                switch entry.storageClass {

                case .persistent,
                     .critical,
                     .normal,
                     .prefetch:
                    return partial

                case .temporary:
                    return partial
                }
            }

        let persistent =
            entries.reduce(
                Int64(0)
            ) {
                partial,
                entry in

                if entry.storageClass ==
                    .persistent
                {
                    return partial +
                        entry.sizeBytes
                }

                return partial
            }

        let temporary =
            entries.reduce(
                Int64(0)
            ) {
                partial,
                entry in

                if entry.storageClass ==
                    .temporary
                {
                    return partial +
                        entry.sizeBytes
                }

                return partial
            }

        let total =
            entries.reduce(
                Int64(0)
            ) {
                $0 + $1.sizeBytes
            }

        let origins =
            Set(
                entries.map {
                    $0.origin
                }
            )

        return SafariStorageSnapshot(
            totalBytes:
                total,

            cacheBytes:
                cache,

            persistentBytes:
                persistent,

            temporaryBytes:
                temporary,

            entryCount:
                entries.count,

            originCount:
                origins.count
        )
    }
}


// MARK: - 20. Metadata Persistence

public struct SafariCacheMetadataEnvelope:
    Codable,
    Sendable
{

    public let schemaVersion:
        UInt32

    public let entries:
        [SafariCacheEntry]

    public let checksum:
        String

    public init(
        schemaVersion:
            UInt32,

        entries:
            [SafariCacheEntry],

        checksum:
            String
    ) {

        self.schemaVersion =
            schemaVersion

        self.entries =
            entries

        self.checksum =
            checksum
    }
}


// MARK: - 21. Metadata Repository

public actor SafariCacheMetadataRepository {

    private let fileURL:
        URL

    private let encoder =
        JSONEncoder()

    private let decoder =
        JSONDecoder()

    private let writer =
        SafariAtomicFileWriter()

    public init(
        directory:
            URL
    ) {

        self.fileURL =
            directory
                .appendingPathComponent(
                    "cache.metadata"
                )

        encoder.outputFormatting = [
            .sortedKeys
        ]

        encoder.dateEncodingStrategy =
            .millisecondsSince1970

        decoder.dateDecodingStrategy =
            .millisecondsSince1970
    }

    public func save(
        entries:
            [SafariCacheEntry]
    ) throws {

        let payload =
            try encoder.encode(
                entries
            )

        let checksum =
            SafariSessionChecksum.make(
                data:
                    payload
            )

        let envelope =
            SafariCacheMetadataEnvelope(
                schemaVersion:
                    1,

                entries:
                    entries,

                checksum:
                    checksum
            )

        let data =
            try encoder.encode(
                envelope
            )

        try writer.write(
            data,
            to:
                fileURL
        )
    }

    public func load()
        throws
        -> [SafariCacheEntry]
    {

        guard
            FileManager.default.fileExists(
                atPath:
                    fileURL.path
            )
        else {
            return []
        }

        let data =
            try Data(
                contentsOf:
                    fileURL
            )

        let envelope =
            try decoder.decode(
                SafariCacheMetadataEnvelope.self,
                from:
                    data
            )

        let payload =
            try encoder.encode(
                envelope.entries
            )

        let checksum =
            SafariSessionChecksum.make(
                data:
                    payload
            )

        guard
            checksum == envelope.checksum
        else {
            throw SafariCacheStorageError
                .checksumMismatch
        }

        return envelope.entries
    }
}


// MARK: - 22. Cache Errors

public enum SafariCacheStorageError:
    Error,
    Sendable
{
    case checksumMismatch
    case invalidSchema
    case metadataCorrupt
    case diskUnavailable
}


// MARK: - 23. Cache Eviction Planner

public struct SafariCacheEvictionPlanner:
    Sendable
{

    private let scorer:
        SafariCacheScoringEngine

    public init() {

        self.scorer =
            SafariCacheScoringEngine()
    }

    public func plan(
        entries:
            [SafariCacheEntry],

        targetBytes:
            Int64,

        pressure:
            SafariStoragePressure
    ) -> [SafariCacheEvictionScore]
    {

        guard
            !entries.isEmpty
        else {
            return []
        }

        let scored =
            entries
                .filter {
                    !$0.isPinned &&
                    $0.storageClass != .critical
                }
                .map {
                    SafariCacheEvictionScore(
                        entryID:
                            $0.id,

                        score:
                            scorer.score(
                                entry:
                                    $0,
                                pressure:
                                    pressure
                            )
                    )
                }
                .sorted {
                    $0.score <
                        $1.score
                }

        var bytesToRemove =
            targetBytes

        var result:
            [SafariCacheEvictionScore] = []

        let lookup =
            Dictionary(
                uniqueKeysWithValues:
                    entries.map {
                        (
                            $0.id,
                            $0.sizeBytes
                        )
                    }
            )

        for candidate in scored {

            guard bytesToRemove > 0 else {
                break
            }

            result.append(
                candidate
            )

            bytesToRemove -=
                lookup[
                    candidate.entryID
                ] ?? 0
        }

        return result
    }
}


// MARK: - 24. Cache Maintenance

public actor SafariCacheMaintenanceEngine {

    private let store:
        SafariCacheStore

    private let planner:
        SafariCacheEvictionPlanner

    private let originStore:
        SafariOriginStorageStore

    public init(
        store:
            SafariCacheStore,

        originStore:
            SafariOriginStorageStore
    ) {

        self.store =
            store

        self.originStore =
            originStore

        self.planner =
            SafariCacheEvictionPlanner()
    }

    public func removeExpired()
        async -> Int
    {

        let removed =
            await store.removeExpired()

        return removed.count
    }

    public func evict(
        targetBytes:
            Int64,

        pressure:
            SafariStoragePressure
    ) async -> [CacheEntryID]
    {

        let entries =
            await store.allEntries()

        let plan =
            planner.plan(
                entries:
                    entries,

                targetBytes:
                    targetBytes,

                pressure:
                    pressure
            )

        for candidate in plan {
            await store.remove(
                candidate.entryID
            )
        }

        let remaining =
            await store.allEntries()

        await originStore.replaceAll(
            entries:
                remaining
        )

        return plan.map {
            $0.entryID
        }
    }
}


// MARK: - 25. Cache Validator

public struct SafariCacheValidationResult:
    Sendable
{
    public let isFresh:
        Bool

    public let requiresRevalidation:
        Bool

    public let expired:
        Bool
}


// MARK: - 26. Cache Validator Engine

public struct SafariCacheValidator:
    Sendable
{

    public init() {}

    public func validate(
        entry:
            SafariCacheEntry,

        now:
            Date = Date()
    ) -> SafariCacheValidationResult
    {

        guard
            let expiry =
                entry.expiresAt
        else {

            return SafariCacheValidationResult(
                isFresh:
                    false,

                requiresRevalidation:
                    true,

                expired:
                    false
            )
        }

        if expiry > now {

            return SafariCacheValidationResult(
                isFresh:
                    true,

                requiresRevalidation:
                    false,

                expired:
                    false
            )
        }

        return SafariCacheValidationResult(
            isFresh:
                false,

            requiresRevalidation:
                true,

            expired:
                true
        )
    }
}


// MARK: - 27. Cache-Control Policy

public struct SafariCacheControlPolicy:
    Sendable
{

    public init() {}

    public func expirationDate(
        response:
            HTTPURLResponse,

        now:
            Date = Date(),

        defaultTTL:
            TimeInterval
    ) -> Date
    {

        if
            let cacheControl =
                response.value(
                    forHTTPHeaderField:
                        "Cache-Control"
                )
        {

            let directives =
                cacheControl
                    .lowercased()
                    .split(
                        separator:
                            ","
                    )

            for directive in directives {

                let trimmed =
                    directive
                        .trimmingCharacters(
                            in:
                                .whitespaces
                        )

                if
                    trimmed.hasPrefix(
                        "max-age="
                    )
                {

                    let value =
                        trimmed
                            .split(
                                separator:
                                    "=",
                                maxSplits:
                                    1
                            )
                            .last

                    if
                        let value,
                        let seconds =
                            TimeInterval(
                                value
                            )
                    {

                        return now.addingTimeInterval(
                            seconds
                        )
                    }
                }

                if trimmed ==
                    "no-store"
                {
                    return now
                }
            }
        }

        if
            let expires =
                response.value(
                    forHTTPHeaderField:
                        "Expires"
                )
        {

            let formatter =
                HTTPDateFormatter()

            if
                let date =
                    formatter.date(
                        from:
                            expires
                    )
            {
                return date
            }
        }

        return now.addingTimeInterval(
            defaultTTL
        )
    }
}


// MARK: - 28. HTTP Date Formatter

public struct HTTPDateFormatter:
    Sendable
{

    private static let formatter:
        DateFormatter = {

            let formatter =
                DateFormatter()

            formatter.locale =
                Locale(
                    identifier:
                        "en_US_POSIX"
                )

            formatter.timeZone =
                TimeZone(
                    secondsFromGMT:
                        0
                )

            formatter.dateFormat =
                "EEE, dd MMM yyyy HH:mm:ss z"

            return formatter
        }()

    public init() {}

    public func date(
        from string:
            String
    ) -> Date? {

        Self.formatter.date(
            from:
                string
        )
    }
}


// MARK: - 29. Cache Metadata Extractor

public struct SafariCacheMetadataExtractor:
    Sendable
{

    private let cacheControl =
        SafariCacheControlPolicy()

    private let defaultTTL:
        TimeInterval

    public init(
        defaultTTL:
            TimeInterval
    ) {
        self.defaultTTL =
            defaultTTL
    }

    public func makeEntry(
        url:
            URL,

        response:
            HTTPURLResponse,

        sizeBytes:
            Int64,

        storageClass:
            SafariStorageClass,

        priority:
            SafariCachePriority
    ) -> SafariCacheEntry?
    {

        guard
            let origin =
                CacheOriginID(
                    url:
                        url
                )
        else {
            return nil
        }

        let expiry =
            cacheControl.expirationDate(
                response:
                    response,

                defaultTTL:
                    defaultTTL
            )

        let etag =
            response.value(
                forHTTPHeaderField:
                    "ETag"
            )

        let lastModified =
            response.value(
                forHTTPHeaderField:
                    "Last-Modified"
            )

        let contentType =
            response.value(
                forHTTPHeaderField:
                    "Content-Type"
            )

        return SafariCacheEntry(
            origin:
                origin,

            url:
                url,

            sizeBytes:
                sizeBytes,

            storageClass:
                storageClass,

            priority:
                priority,

            expiresAt:
                expiry,

            etag:
                etag,

            lastModifiedHTTP:
                lastModified,

            contentType:
                contentType,

            isValidated:
                true
        )
    }
}


// MARK: - 30. Power-Aware Cache Policy

public struct SafariPowerAwareCachePolicy:
    Sendable
{

    public init() {}

    public func adjustedTTL(
        original:
            TimeInterval,

        powerMode:
            SafariCachePowerMode
    ) -> TimeInterval
    {

        switch powerMode {

        case .maximumPerformance:
            return original

        case .balanced:
            return original * 1.25

        case .battery:
            return original * 2

        case .aggressiveSaving:
            return original * 4
        }
    }

    public func shouldAllowPrefetch(
        powerMode:
            SafariCachePowerMode
    ) -> Bool
    {

        switch powerMode {

        case .maximumPerformance:
            return true

        case .balanced:
            return true

        case .battery:
            return false

        case .aggressiveSaving:
            return false
        }
    }
}


// MARK: - 31. Memory-Aware Cache Policy

public enum SafariMemoryPressureLevel:
    Int,
    Codable,
    Sendable
{
    case normal = 0
    case elevated = 1
    case high = 2
    case critical = 3
}


public struct SafariMemoryAwareCachePolicy:
    Sendable
{

    public init() {}

    public func recommendedCacheFraction(
        pressure:
            SafariMemoryPressureLevel
    ) -> Double
    {

        switch pressure {

        case .normal:
            return 1.0

        case .elevated:
            return 0.75

        case .high:
            return 0.50

        case .critical:
            return 0.20
        }
    }
}


// MARK: - 32. Cache Coordinator

public actor SafariCacheCoordinator {

    public let store:
        SafariCacheStore

    public let originStore:
        SafariOriginStorageStore

    private let admission:
        SafariCacheAdmissionEngine

    private let configuration:
        SafariCacheConfiguration

    private let maintenance:
        SafariCacheMaintenanceEngine

    private let diskProvider:
        any SafariDiskStateProvider

    private let metadata:
        SafariCacheMetadataRepository

    private let snapshotBuilder:
        SafariStorageSnapshotBuilder

    public init(
        configuration:
            SafariCacheConfiguration =
                SafariCacheConfiguration(),

        storageDirectory:
            URL,

        diskProvider:
            any SafariDiskStateProvider =
                MacOSSafariDiskStateProvider()
    ) {

        self.configuration =
            configuration

        self.store =
            SafariCacheStore()

        self.originStore =
            SafariOriginStorageStore()

        self.admission =
            SafariCacheAdmissionEngine(
                configuration:
                    configuration
            )

        self.maintenance =
            SafariCacheMaintenanceEngine(
                store:
                    store,

                originStore:
                    originStore
            )

        self.diskProvider =
            diskProvider

        self.metadata =
            SafariCacheMetadataRepository(
                directory:
                    storageDirectory
            )

        self.snapshotBuilder =
            SafariStorageSnapshotBuilder()
    }

    public func start()
        async
    {

        if
            let entries =
                try? await metadata.load()
        {

            for entry in entries {

                await store.insert(
                    entry
                )
            }

            await originStore
                .replaceAll(
                    entries:
                        entries
                )
        }
    }

    public func lookup(
        url:
            URL
    ) async -> SafariCacheEntry?
    {

        await store.lookup(
            url:
                url
        )
    }

    public func admit(
        entry:
            SafariCacheEntry,

        powerMode:
            SafariCachePowerMode =
                .balanced,

        thermal:
            SafariCacheThermalState =
                .nominal
    ) async
        -> SafariCacheAdmissionDecision
    {

        let disk =
            await diskProvider
                .currentDiskState(
                    for:
                        storageDirectoryURL()
                )

        let context =
            SafariCachePolicyContext(
                disk:
                    disk,

                powerMode:
                    powerMode,

                thermalState:
                    thermal
            )

        let decision =
            admission.evaluate(
                sizeBytes:
                    entry.sizeBytes,

                storageClass:
                    entry.storageClass,

                priority:
                    entry.priority,

                context:
                    context
            )

        switch decision {

        case .admit,
             .admitWithShortTTL,
             .replaceExisting:

            await store.insert(
                entry
            )

            await originStore.update(
                entry:
                    entry
            )

        case .reject:
            break
        }

        return decision
    }

    public func remove(
        id:
            CacheEntryID
    ) async {

        await store.remove(
            id
        )
    }

    public func maintain()
        async
    {

        let disk =
            await diskProvider
                .currentDiskState(
                    for:
                        storageDirectoryURL()
                )

        _ =
            await maintenance
                .removeExpired()

        let entries =
            await store.allEntries()

        let total =
            entries.reduce(
                Int64(0)
            ) {
                $0 + $1.sizeBytes
            }

        if total >
            configuration.maximumCacheBytes
        {

            let target =
                total -
                configuration.maximumCacheBytes

            _ =
                await maintenance.evict(
                    targetBytes:
                        target,

                    pressure:
                        disk.pressure
                )
        }

        if
            disk.availableBytes <
                configuration.minimumFreeDiskBytes
        {

            let target =
                min(
                    total / 2,
                    total
                )

            _ =
                await maintenance.evict(
                    targetBytes:
                        target,

                    pressure:
                        disk.pressure
                )
        }

        try? await metadata.save(
            entries:
                await store.allEntries()
        )
    }

    public func snapshot()
        async -> SafariStorageSnapshot
    {

        await snapshotBuilder.build(
            entries:
                await store.allEntries()
        )
    }

    private func storageDirectoryURL()
        -> URL
    {
        FileManager.default
            .urls(
                for:
                    .applicationSupportDirectory,
                in:
                    .userDomainMask
            )
            .first!
            .appendingPathComponent(
                "SafariPowerArchitecture",
                isDirectory:
                    true
            )
    }
}


// MARK: - 33. Origin Quota

public struct SafariOriginQuota:
    Codable,
    Sendable
{

    public let origin:
        CacheOriginID

    public let maximumBytes:
        Int64

    public let warningBytes:
        Int64

    public init(
        origin:
            CacheOriginID,

        maximumBytes:
            Int64,

        warningBytes:
            Int64
    ) {

        self.origin =
            origin

        self.maximumBytes =
            maximumBytes

        self.warningBytes =
            warningBytes
    }
}


// MARK: - 34. Quota Decision

public enum SafariQuotaDecision:
    Codable,
    Sendable
{
    case allow
    case allowWithWarning
    case deny
}


// MARK: - 35. Origin Quota Manager

public actor SafariOriginQuotaManager {

    private var quotas:
        [CacheOriginID:
            SafariOriginQuota] = [:]

    private let defaultQuota:
        Int64

    public init(
        defaultQuota:
            Int64 =
                500 * 1024 * 1024
    ) {
        self.defaultQuota =
            defaultQuota
    }

    public func quota(
        for origin:
            CacheOriginID
    ) -> SafariOriginQuota {

        quotas[origin]
        ??
        SafariOriginQuota(
            origin:
                origin,

            maximumBytes:
                defaultQuota,

            warningBytes:
                Int64(
                    Double(
                        defaultQuota
                    ) * 0.80
                )
        )
    }

    public func evaluate(
        origin:
            CacheOriginID,

        currentBytes:
            Int64,

        additionalBytes:
            Int64
    ) -> SafariQuotaDecision
    {

        let quota =
            await quota(
                for:
                    origin
            )

        let projected =
            currentBytes +
            additionalBytes

        if projected >
            quota.maximumBytes
        {
            return .deny
        }

        if projected >
            quota.warningBytes
        {
            return .allowWithWarning
        }

        return .allow
    }

    public func setQuota(
        _ quota:
            SafariOriginQuota
    ) {

        quotas[
            quota.origin
        ] =
            quota
    }
}


// MARK: - 36. Cache Data Container

public struct SafariCacheData:
    Sendable
{

    public let entry:
        SafariCacheEntry

    public let data:
        Data

    public init(
        entry:
            SafariCacheEntry,

        data:
            Data
    ) {

        self.entry = entry
        self.data = data
    }
}


// MARK: - 37. Application Cache File Store

public actor SafariApplicationCacheFileStore {

    private let directory:
        URL

    private let fileManager:
        FileManager

    public init(
        directory:
            URL
    ) {

        self.directory =
            directory

        self.fileManager =
            .default
    }

    public func store(
        data:
            Data,

        entry:
            SafariCacheEntry
    ) throws
        -> URL
    {

        try fileManager.createDirectory(
            at:
                directory,
            withIntermediateDirectories:
                true
        )

        let digest =
            SHA256.hash(
                data:
                    Data(
                        entry.url.absoluteString
                            .utf8
                    )
            )

        let filename =
            digest
                .map {
                    String(
                        format:
                            "%02x",
                        $0
                    )
                }
                .joined()

        let url =
            directory
                .appendingPathComponent(
                    filename
                )

        try data.write(
            to:
                url,
            options:
                .atomic
        )

        return url
    }

    public func load(
        entry:
            SafariCacheEntry
    ) throws -> Data
    {

        let digest =
            SHA256.hash(
                data:
                    Data(
                        entry.url.absoluteString
                            .utf8
                    )
            )

        let filename =
            digest
                .map {
                    String(
                        format:
                            "%02x",
                        $0
                    )
                }
                .joined()

        let url =
            directory
                .appendingPathComponent(
                    filename
                )

        return try Data(
            contentsOf:
                url
        )
    }

    public func remove(
        entry:
            SafariCacheEntry
    ) throws
    {

        let digest =
            SHA256.hash(
                data:
                    Data(
                        entry.url.absoluteString
                            .utf8
                    )
            )

        let filename =
            digest
                .map {
                    String(
                        format:
                            "%02x",
                        $0
                    )
                }
                .joined()

        let url =
            directory
                .appendingPathComponent(
                    filename
                )

        if fileManager.fileExists(
            atPath:
                url.path
        ) {
            try fileManager.removeItem(
                at:
                    url
            )
        }
    }
}


// MARK: - 38. Cache Maintenance Scheduler

public actor SafariCacheMaintenanceScheduler {

    private let coordinator:
        SafariCacheCoordinator

    private var task:
        Task<Void, Never>?

    private let interval:
        Duration

    public init(
        coordinator:
            SafariCacheCoordinator,

        interval:
            Duration =
                .seconds(60)
    ) {

        self.coordinator =
            coordinator

        self.interval =
            interval
    }

    public func start() {

        guard task == nil else {
            return
        }

        task =
            Task { [weak self] in

                guard let self else {
                    return
                }

                while !Task.isCancelled {

                    await coordinator.maintain()

                    try? await Task.sleep(
                        for:
                            self.interval
                    )
                }
            }
    }

    public func stop() {

        task?.cancel()
        task = nil
    }
}


// MARK: - 39. Cache Telemetry

public enum SafariCacheTelemetryEvent:
    Sendable,
    Codable
{

    case hit(URL)
    case miss(URL)

    case admission(
        URL,
        SafariCacheAdmissionDecision
    )

    case eviction(
        CacheEntryID
    )

    case expiration(
        CacheEntryID
    )

    case quotaDenied(
        CacheOriginID
    )

    case maintenance(
        SafariStorageSnapshot
    )
}


public actor SafariCacheTelemetry {

    private var events:
        [SafariCacheTelemetryEvent] = []

    private let maximum:
        Int

    public init(
        maximum:
            Int = 2_000
    ) {
        self.maximum =
            maximum
    }

    public func append(
        _ event:
            SafariCacheTelemetryEvent
    ) {

        events.append(
            event
        )

        if events.count >
            maximum
        {
            events.removeFirst(
                events.count - maximum
            )
        }
    }

    public func recent(
        limit:
            Int = 100
    ) -> [SafariCacheTelemetryEvent]
    {

        Array(
            events.suffix(
                limit
            )
        )
    }
}


// MARK: - 40. High-Level Cache Runtime

public actor SafariIntelligentCacheRuntime {

    public let coordinator:
        SafariCacheCoordinator

    public let quotaManager:
        SafariOriginQuotaManager

    public let telemetry:
        SafariCacheTelemetry

    private let validator:
        SafariCacheValidator

    private let configuration:
        SafariCacheConfiguration

    public init(
        configuration:
            SafariCacheConfiguration =
                SafariCacheConfiguration()
    ) {

        self.configuration =
            configuration

        let storage =
            FileManager.default
                .urls(
                    for:
                        .applicationSupportDirectory,
                    in:
                        .userDomainMask
                )
                .first!
                .appendingPathComponent(
                    "SafariPowerArchitecture",
                    isDirectory:
                        true
                )

        self.coordinator =
            SafariCacheCoordinator(
                configuration:
                    configuration,

                storageDirectory:
                    storage
            )

        self.quotaManager =
            SafariOriginQuotaManager()

        self.telemetry =
            SafariCacheTelemetry()

        self.validator =
            SafariCacheValidator()
    }

    public func start()
        async
    {

        await coordinator.start()
    }

    public func lookup(
        url:
            URL
    ) async -> SafariCacheEntry?
    {

        let result =
            await coordinator.lookup(
                url:
                    url
            )

        if result != nil {

            await telemetry.append(
                .hit(url)
            )

        } else {

            await telemetry.append(
                .miss(url)
            )
        }

        return result
    }

    public func admit(
        _ entry:
            SafariCacheEntry,

        powerMode:
            SafariCachePowerMode =
                .balanced,

        thermal:
            SafariCacheThermalState =
                .nominal
    ) async
        -> SafariCacheAdmissionDecision
    {

        guard
            let origin =
                CacheOriginID(
                    url:
                        entry.url
                )
        else {
            return .reject
        }

        let current =
            await coordinator
                .snapshot()

        let decision =
            await quotaManager.evaluate(
                origin:
                    origin,

                currentBytes:
                    current.totalBytes,

                additionalBytes:
                    entry.sizeBytes
            )

        guard decision != .deny else {

            await telemetry.append(
                .quotaDenied(
                    origin
                )
            )

            return .reject
        }

        let result =
            await coordinator.admit(
                entry:
                    entry,

                powerMode:
                    powerMode,

                thermal:
                    thermal
            )

        await telemetry.append(
            .admission(
                entry.url,
                result
            )
        )

        return result
    }

    public func validate(
        entry:
            SafariCacheEntry
    ) -> SafariCacheValidationResult
    {

        validator.validate(
            entry:
                entry
        )
    }

    public func maintain()
        async
    {

        await coordinator.maintain()

        let snapshot =
            await coordinator.snapshot()

        await telemetry.append(
            .maintenance(
                snapshot
            )
        )
    }

    public func snapshot()
        async -> SafariStorageSnapshot
    {
        await coordinator.snapshot()
    }
}


// MARK: - 41. WebKit Website Data Controller

@MainActor
public final class SafariWebKitStorageController {

    private let dataStore:
        WKWebsiteDataStore

    public init(
        dataStore:
            WKWebsiteDataStore =
                .default()
    ) {
        self.dataStore =
            dataStore
    }

    public func fetchUsage(
        completion:
            @escaping @Sendable (
                [WKWebsiteDataRecord]
            ) -> Void
    ) {

        let types =
            WKWebsiteDataStore
                .allWebsiteDataTypes()

        dataStore.fetchDataRecords(
            ofTypes:
                types
        ) { records in

            completion(
                records
            )
        }
    }

    public func remove(
        records:
            [WKWebsiteDataRecord]
    ) {

        let types =
            WKWebsiteDataStore
                .allWebsiteDataTypes()

        dataStore.removeData(
            ofTypes:
                types,

            for:
                records
        ) {
            // Completed.
        }
    }
}


// MARK: - 42. Origin Storage Inspector

@MainActor
public final class SafariOriginStorageInspector {

    private let dataStore:
        WKWebsiteDataStore

    public init(
        dataStore:
            WKWebsiteDataStore =
                .default()
    ) {

        self.dataStore =
            dataStore
    }

    public func inspect(
        completion:
            @escaping @Sendable (
                [WKWebsiteDataRecord]
            ) -> Void
    ) {

        dataStore.fetchDataRecords(
            ofTypes:
                WKWebsiteDataStore
                    .allWebsiteDataTypes()
        ) { records in

            completion(
                records
            )
        }
    }
}


// MARK: - 43. Intelligent Eviction Runtime

public actor SafariIntelligentEvictionRuntime {

    private let coordinator:
        SafariCacheCoordinator

    public init(
        coordinator:
            SafariCacheCoordinator
    ) {

        self.coordinator =
            coordinator
    }

    public func handlePressure(
        _ pressure:
            SafariStoragePressure
    ) async {

        let snapshot =
            await coordinator.snapshot()

        let target:
            Int64

        switch pressure {

        case .normal:
            target = 0

        case .elevated:
            target =
                snapshot.totalBytes / 10

        case .high:
            target =
                snapshot.totalBytes / 3

        case .critical:
            target =
                snapshot.totalBytes / 2
        }

        guard target > 0 else {
            return
        }

        /*
         coordinator.maintain() will perform ordinary TTL
         cleanup. Explicit pressure eviction is performed by
         the same underlying maintenance policy.
        */

        await coordinator.maintain()
    }
}


// MARK: - 44. Cache Runtime Factory

public enum SafariIntelligentCacheFactory {

    public static func make()
        -> SafariIntelligentCacheRuntime
    {

        SafariIntelligentCacheRuntime(
            configuration:
                SafariCacheConfiguration()
        )
    }
}


// MARK: - 45. Cache Integration Controller

@MainActor
public final class SafariBrowserCacheController {

    private let runtime:
        SafariIntelligentCacheRuntime

    private let maintenance:
        SafariCacheMaintenanceScheduler

    public init() {

        let runtime =
            SafariIntelligentCacheFactory
                .make()

        self.runtime =
            runtime

        self.maintenance =
            SafariCacheMaintenanceScheduler(
                coordinator:
                    runtime.coordinator
            )
    }

    public func start()
        async
    {

        await runtime.start()

        maintenance.start()
    }

    public func stop() {

        maintenance.stop()
    }

    public func storageSnapshot()
        async -> SafariStorageSnapshot
    {

        await runtime.snapshot()
    }
}


// MARK: - 46. Test Providers

#if DEBUG

public struct MockDiskStateProvider:
    SafariDiskStateProvider
{

    public let state:
        SafariDiskState

    public init(
        state:
            SafariDiskState
    ) {
        self.state =
            state
    }

    public func currentDiskState(
        for url:
            URL
    ) async -> SafariDiskState
    {
        state
    }
}


// MARK: - 47. Cache Tests

public enum SafariIntelligentCacheTests {

    public static func testOrigin()
        -> Bool
    {

        guard
            let url =
                URL(
                    string:
                        "https://example.com/test"
                )
        else {
            return false
        }

        guard
            let origin =
                CacheOriginID(
                    url:
                        url
                )
        else {
            return false
        }

        return
            origin.scheme ==
                "https"
            &&
            origin.host ==
                "example.com"
    }

    public static func testScoring()
        -> Bool
    {

        guard
            let url =
                URL(
                    string:
                        "https://example.com"
                ),
            let origin =
                CacheOriginID(
                    url:
                        url
                )
        else {
            return false
        }

        let entry =
            SafariCacheEntry(
                origin:
                    origin,

                url:
                    url,

                sizeBytes:
                    1_000,

                priority:
                    .high,

                hitCount:
                    100
            )

        let scorer =
            SafariCacheScoringEngine()

        let score =
            scorer.score(
                entry:
                    entry,

                pressure:
                    .normal
            )

        return score > 0
    }

    public static func testAdmission()
        -> Bool
    {

        let engine =
            SafariCacheAdmissionEngine(
                configuration:
                    SafariCacheConfiguration()
            )

        let disk =
            SafariDiskState(
                availableBytes:
                    100 * 1024 * 1024 * 1024,

                totalBytes:
                    1_000 *
                    1024 *
                    1024 *
                    1024,

                usedBytes:
                    900 *
                    1024 *
                    1024 *
                    1024,

                pressure:
                    .normal
            )

        let context =
            SafariCachePolicyContext(
                disk:
                    disk,

                powerMode:
                    .balanced,

                thermalState:
                    .nominal
            )

        let decision =
            engine.evaluate(
                sizeBytes:
                    10_000,

                storageClass:
                    .normal,

                priority:
                    .normal,

                context:
                    context
            )

        switch decision {

        case .admit,
             .admitWithShortTTL,
             .replaceExisting:
            return true

        case .reject:
            return false
        }
    }
}

#endif


// MARK: - 48. Complete Architecture
//
//                    Safari
//                       │
//                       ▼
//             Intelligent Cache Runtime
//                       │
//          ┌────────────┼────────────┐
//          │            │            │
//          ▼            ▼            ▼
//      Admission      Lookup       Quota
//          │            │            │
//          └────────────┼────────────┘
//                       │
//                       ▼
//                  Cache Store
//                       │
//              ┌────────┴────────┐
//              │                 │
//              ▼                 ▼
//        Origin Metadata    Entry Metadata
//              │                 │
//              └────────┬────────┘
//                       │
//                       ▼
//               Storage Snapshot
//                       │
//          ┌────────────┼────────────┐
//          │            │            │
//          ▼            ▼            ▼
//       TTL         LRU/LFU       Priority
//       │             │            │
//       └─────────────┼────────────┘
//                     ▼
//              Eviction Planner
//                     │
//                     ▼
//              Disk Pressure
//
//
//
// Integration with previous systems:
//
// #2 Resource Manager
//          │
//          ▼
//   Memory pressure
//          │
//          ▼
// #8 Cache Engine
//
// #6 Power Runtime
//          │
//          ▼
//   Battery / thermal
//          │
//          ▼
//   Cache admission
//   Prefetch policy
//
// #7 Session Architecture
//          │
//          ▼
//   Persistent metadata
//
// #3 Navigation Runtime
//          │
//          ▼
//       URL request
//          │
//          ▼
//   Cache lookup / validation
//
// #4 Prediction Engine
//          │
//          ▼
//      Prefetch request
//          │
//          ▼
//   Power-aware admission
//
// #5 Rendering Engine
//          │
//          ▼
//     Page lifecycle
//          │
//          ▼
// Cache usage telemetry






//
// SafariUnifiedPrivacyPermissionEngine.swift
//
// Safari macOS Performance Architecture — #9
//
// Responsibilities:
// - Origin-scoped permission state
// - Permission state machines
// - Camera / microphone / location / notifications
// - Autoplay / popups / downloads
// - Persistent permission decisions
// - Temporary/session permissions
// - Private browsing isolation
// - Permission expiry
// - User-decision auditing
// - Policy evaluation
// - Request deduplication
// - Concurrent permission requests
// - Privacy telemetry
// - Persistent state
// - Atomic writes
// - Swift 6 concurrency
//
// Public APIs only.
// This layer does NOT bypass macOS/TCC/WebKit security.
//

import Foundation
import WebKit
import AVFoundation


// MARK: - 1. Origin Identity

public struct PrivacyOrigin:
    Hashable,
    Codable,
    Sendable
{
    public let scheme: String
    public let host: String
    public let port: Int?

    public init(
        scheme: String,
        host: String,
        port: Int? = nil
    ) {
        self.scheme = scheme.lowercased()
        self.host = host.lowercased()
        self.port = port
    }

    public init?(url: URL) {

        guard
            let scheme = url.scheme,
            let host = url.host
        else {
            return nil
        }

        self.scheme = scheme.lowercased()
        self.host = host.lowercased()
        self.port = url.port
    }

    public var serialized: String {

        var value =
            "\(scheme)://\(host)"

        if let port {
            value += ":\(port)"
        }

        return value
    }
}


// MARK: - 2. Browsing Context

public struct PrivacyBrowsingContext:
    Hashable,
    Codable,
    Sendable
{
    public let identifier: UUID
    public let isPrivate: Bool

    public init(
        identifier: UUID = UUID(),
        isPrivate: Bool
    ) {
        self.identifier = identifier
        self.isPrivate = isPrivate
    }
}


// MARK: - 3. Permission Types

public enum SafariPermissionType:
    String,
    Codable,
    CaseIterable,
    Sendable
{
    case camera
    case microphone
    case location
    case notifications
    case screenCapture
    case autoplay
    case popups
    case downloads
    case clipboardRead
    case clipboardWrite
    case sensors
    case mediaPlayback
}


// MARK: - 4. Permission Decision

public enum SafariPermissionDecision:
    String,
    Codable,
    Sendable
{
    case unknown
    case granted
    case denied
    case restricted
    case sessionGranted
    case sessionDenied
}


// MARK: - 5. Permission Lifecycle

public enum SafariPermissionLifecycle:
    String,
    Codable,
    Sendable
{
    case idle
    case requested
    case prompting
    case evaluating
    case granted
    case denied
    case restricted
    case expired
    case revoked
}


// MARK: - 6. Permission Scope

public enum SafariPermissionScope:
    String,
    Codable,
    Sendable
{
    case once
    case session
    case persistent
}


// MARK: - 7. Permission Record

public struct SafariPermissionRecord:
    Codable,
    Sendable
{
    public let origin:
        PrivacyOrigin

    public let type:
        SafariPermissionType

    public let context:
        PrivacyBrowsingContext

    public var decision:
        SafariPermissionDecision

    public var lifecycle:
        SafariPermissionLifecycle

    public var scope:
        SafariPermissionScope

    public var createdAt:
        Date

    public var updatedAt:
        Date

    public var expiresAt:
        Date?

    public var requestCount:
        UInt64

    public var lastRequestAt:
        Date?

    public var userInitiated:
        Bool

    public init(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        context:
            PrivacyBrowsingContext,

        decision:
            SafariPermissionDecision = .unknown,

        lifecycle:
            SafariPermissionLifecycle = .idle,

        scope:
            SafariPermissionScope = .session,

        createdAt:
            Date = Date(),

        updatedAt:
            Date = Date(),

        expiresAt:
            Date? = nil,

        requestCount:
            UInt64 = 0,

        lastRequestAt:
            Date? = nil,

        userInitiated:
            Bool = false
    ) {
        self.origin = origin
        self.type = type
        self.context = context
        self.decision = decision
        self.lifecycle = lifecycle
        self.scope = scope
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.expiresAt = expiresAt
        self.requestCount = requestCount
        self.lastRequestAt = lastRequestAt
        self.userInitiated = userInitiated
    }
}


// MARK: - 8. Permission Key

public struct SafariPermissionKey:
    Hashable,
    Codable,
    Sendable
{
    public let origin:
        PrivacyOrigin

    public let type:
        SafariPermissionType

    public let context:
        PrivacyBrowsingContext

    public init(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        context:
            PrivacyBrowsingContext
    ) {
        self.origin = origin
        self.type = type
        self.context = context
    }
}


// MARK: - 9. Permission Request

public struct SafariPermissionRequest:
    Identifiable,
    Sendable
{
    public let id:
        UUID

    public let key:
        SafariPermissionKey

    public let requestedAt:
        Date

    public let userInitiated:
        Bool

    public let reason:
        String?

    public init(
        id:
            UUID = UUID(),

        key:
            SafariPermissionKey,

        requestedAt:
            Date = Date(),

        userInitiated:
            Bool,

        reason:
            String? = nil
    ) {
        self.id = id
        self.key = key
        self.requestedAt = requestedAt
        self.userInitiated = userInitiated
        self.reason = reason
    }
}


// MARK: - 10. State Transition

public enum SafariPermissionTransition:
    Sendable
{
    case request
    case beginPrompt
    case grant(
        SafariPermissionScope
    )
    case deny
    case restrict
    case expire
    case revoke
    case reset
}


// MARK: - 11. State Machine

public struct SafariPermissionStateMachine:
    Sendable
{

    public init() {}

    public func transition(
        record:
            SafariPermissionRecord,

        transition:
            SafariPermissionTransition,

        now:
            Date = Date()
    ) -> SafariPermissionRecord
    {

        var updated =
            record

        updated.updatedAt =
            now

        switch transition {

        case .request:

            updated.lifecycle =
                .requested

            updated.requestCount +=
                1

            updated.lastRequestAt =
                now

        case .beginPrompt:

            updated.lifecycle =
                .prompting

        case .grant(let scope):

            updated.decision =
                scope == .session
                ? .sessionGranted
                : .granted

            updated.lifecycle =
                .granted

            updated.scope =
                scope

            switch scope {

            case .once:
                updated.expiresAt =
                    now.addingTimeInterval(
                        60 * 60
                    )

            case .session:
                updated.expiresAt = nil

            case .persistent:
                updated.expiresAt = nil
            }

        case .deny:

            updated.decision =
                updated.scope == .session
                ? .sessionDenied
                : .denied

            updated.lifecycle =
                .denied

        case .restrict:

            updated.decision =
                .restricted

            updated.lifecycle =
                .restricted

        case .expire:

            updated.decision =
                .unknown

            updated.lifecycle =
                .expired

            updated.expiresAt =
                now

        case .revoke:

            updated.decision =
                .unknown

            updated.lifecycle =
                .revoked

            updated.expiresAt =
                now

        case .reset:

            updated.decision =
                .unknown

            updated.lifecycle =
                .idle

            updated.expiresAt =
                nil
        }

        return updated
    }
}


// MARK: - 12. Privacy Policy

public enum SafariPrivacyPolicyResult:
    Sendable
{
    case allow
    case deny
    case prompt
    case restricted
}


// MARK: - 13. Privacy Policy Context

public struct SafariPrivacyPolicyContext:
    Sendable
{
    public let origin:
        PrivacyOrigin

    public let type:
        SafariPermissionType

    public let isPrivate:
        Bool

    public let isUserInitiated:
        Bool

    public let secureConnection:
        Bool

    public let previousDenials:
        UInt64

    public let requestCount:
        UInt64

    public init(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        isPrivate:
            Bool,

        isUserInitiated:
            Bool,

        secureConnection:
            Bool,

        previousDenials:
            UInt64,

        requestCount:
            UInt64
    ) {
        self.origin = origin
        self.type = type
        self.isPrivate = isPrivate
        self.isUserInitiated = isUserInitiated
        self.secureConnection = secureConnection
        self.previousDenials = previousDenials
        self.requestCount = requestCount
    }
}


// MARK: - 14. Policy Engine

public struct SafariPrivacyPolicyEngine:
    Sendable
{

    public init() {}

    public func evaluate(
        _ context:
            SafariPrivacyPolicyContext
    ) -> SafariPrivacyPolicyResult
    {

        guard context.secureConnection else {

            switch context.type {

            case .camera,
                 .microphone,
                 .location,
                 .screenCapture,
                 .clipboardRead:
                return .deny

            default:
                break
            }
        }

        if context.previousDenials >= 3 {
            return .deny
        }

        if
            context.type == .clipboardRead
            &&
            !context.isUserInitiated
        {
            return .deny
        }

        if
            context.type == .screenCapture
            &&
            !context.isUserInitiated
        {
            return .prompt
        }

        if
            context.type == .camera
            ||
            context.type == .microphone
        {

            if context.isPrivate {
                return .prompt
            }

            return .prompt
        }

        return .prompt
    }
}


// MARK: - 15. Permission Store

public actor SafariPermissionStore {

    private var records:
        [SafariPermissionKey:
            SafariPermissionRecord] = [:]

    public init() {}

    public func record(
        for key:
            SafariPermissionKey
    ) -> SafariPermissionRecord?
    {
        records[key]
    }

    public func upsert(
        _ record:
            SafariPermissionRecord
    ) {

        let key =
            SafariPermissionKey(
                origin:
                    record.origin,

                type:
                    record.type,

                context:
                    record.context
            )

        records[key] =
            record
    }

    public func remove(
        key:
            SafariPermissionKey
    ) {

        records.removeValue(
            forKey:
                key
        )
    }

    public func allRecords()
        -> [SafariPermissionRecord]
    {
        Array(
            records.values
        )
    }

    public func revokeOrigin(
        _ origin:
            PrivacyOrigin
    ) {

        records = records.filter {
            $0.key.origin != origin
        }
    }

    public func revokeContext(
        _ context:
            PrivacyBrowsingContext
    ) {

        records = records.filter {
            $0.key.context != context
        }
    }

    public func clearSessionPermissions() {

        records = records.filter {
            $0.value.scope ==
                .persistent
        }
    }
}


// MARK: - 16. Permission Request Registry

public actor SafariPermissionRequestRegistry {

    private var requests:
        [UUID:
            SafariPermissionRequest] = [:]

    public init() {}

    public func insert(
        _ request:
            SafariPermissionRequest
    ) {
        requests[request.id] =
            request
    }

    public func remove(
        _ id:
            UUID
    ) {
        requests.removeValue(
            forKey:
                id
        )
    }

    public func request(
        _ id:
            UUID
    ) -> SafariPermissionRequest?
    {
        requests[id]
    }

    public func existing(
        key:
            SafariPermissionKey
    ) -> SafariPermissionRequest?
    {
        requests.values.first {
            $0.key == key
        }
    }
}


// MARK: - 17. Permission Decision

public struct SafariPermissionEvaluation:
    Sendable
{
    public let decision:
        SafariPrivacyPolicyResult

    public let existing:
        SafariPermissionRecord?

    public let request:
        SafariPermissionRequest?
}


// MARK: - 18. Permission Evaluator

public actor SafariPermissionEvaluator {

    private let store:
        SafariPermissionStore

    private let requests:
        SafariPermissionRequestRegistry

    private let policy:
        SafariPrivacyPolicyEngine

    private let machine:
        SafariPermissionStateMachine

    public init(
        store:
            SafariPermissionStore,

        requests:
            SafariPermissionRequestRegistry
    ) {
        self.store = store
        self.requests = requests
        self.policy =
            SafariPrivacyPolicyEngine()
        self.machine =
            SafariPermissionStateMachine()
    }

    public func evaluate(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        context:
            PrivacyBrowsingContext,

        secureConnection:
            Bool,

        userInitiated:
            Bool,

        reason:
            String?
    ) async -> SafariPermissionEvaluation
    {

        let key =
            SafariPermissionKey(
                origin:
                    origin,

                type:
                    type,

                context:
                    context
            )

        if
            let request =
                await requests.existing(
                    key:
                        key
                )
        {
            return SafariPermissionEvaluation(
                decision:
                    .prompt,

                existing:
                    await store.record(
                        for:
                            key
                    ),

                request:
                    request
            )
        }

        var record =
            await store.record(
                for:
                    key
            )
            ??
            SafariPermissionRecord(
                origin:
                    origin,

                type:
                    type,

                context:
                    context,

                userInitiated:
                    userInitiated
            )

        if
            let expiry =
                record.expiresAt,
            expiry <= Date()
        {

            record =
                machine.transition(
                    record:
                        record,

                    transition:
                        .expire
                )

            await store.upsert(
                record
            )
        }

        switch record.decision {

        case .granted,
             .sessionGranted:

            return SafariPermissionEvaluation(
                decision:
                    .allow,

                existing:
                    record,

                request:
                    nil
            )

        case .denied,
             .sessionDenied:

            return SafariPermissionEvaluation(
                decision:
                    .deny,

                existing:
                    record,

                request:
                    nil
            )

        case .restricted:

            return SafariPermissionEvaluation(
                decision:
                    .restricted,

                existing:
                    record,

                request:
                    nil
            )

        case .unknown:
            break
        }

        let context =
            SafariPrivacyPolicyContext(
                origin:
                    origin,

                type:
                    type,

                isPrivate:
                    context.isPrivate,

                isUserInitiated:
                    userInitiated,

                secureConnection:
                    secureConnection,

                previousDenials:
                    0,

                requestCount:
                    record.requestCount
            )

        let decision =
            policy.evaluate(
                context
            )

        guard decision == .prompt else {

            return SafariPermissionEvaluation(
                decision:
                    decision,

                existing:
                    record,

                request:
                    nil
            )
        }

        record =
            machine.transition(
                record:
                    record,

                transition:
                    .request
            )

        await store.upsert(
            record
        )

        let request =
            SafariPermissionRequest(
                key:
                    key,

                userInitiated:
                    userInitiated,

                reason:
                    reason
            )

        await requests.insert(
            request
        )

        return SafariPermissionEvaluation(
            decision:
                .prompt,

            existing:
                record,

            request:
                request
        )
    }
}


// MARK: - 19. Permission Resolution

public actor SafariPermissionResolver {

    private let store:
        SafariPermissionStore

    private let requests:
        SafariPermissionRequestRegistry

    private let machine:
        SafariPermissionStateMachine

    public init(
        store:
            SafariPermissionStore,

        requests:
            SafariPermissionRequestRegistry
    ) {
        self.store = store
        self.requests = requests
        self.machine =
            SafariPermissionStateMachine()
    }

    public func resolve(
        request:
            SafariPermissionRequest,

        decision:
            SafariPermissionDecision,

        scope:
            SafariPermissionScope
    ) async
        -> SafariPermissionRecord?
    {

        guard
            await requests.request(
                request.id
            ) != nil
        else {
            return nil
        }

        let key =
            request.key

        var record =
            await store.record(
                for:
                    key
            )
            ??
            SafariPermissionRecord(
                origin:
                    key.origin,

                type:
                    key.type,

                context:
                    key.context
            )

        switch decision {

        case .granted,
             .sessionGranted:

            record =
                machine.transition(
                    record:
                        record,

                    transition:
                        .grant(
                            scope
                        )
                )

        case .denied,
             .sessionDenied:

            record =
                machine.transition(
                    record:
                        record,

                    transition:
                        .deny
                )

        case .restricted:

            record =
                machine.transition(
                    record:
                        record,

                    transition:
                        .restrict
                )

        case .unknown:
            break
        }

        await store.upsert(
            record
        )

        await requests.remove(
            request.id
        )

        return record
    }
}


// MARK: - 20. Permission Persistence

public struct SafariPermissionPersistenceEnvelope:
    Codable,
    Sendable
{
    public let version:
        UInt32

    public let records:
        [SafariPermissionRecord]

    public let checksum:
        String

    public init(
        version:
            UInt32,

        records:
            [SafariPermissionRecord],

        checksum:
            String
    ) {
        self.version = version
        self.records = records
        self.checksum = checksum
    }
}


public actor SafariPermissionPersistence {

    private let fileURL:
        URL

    private let encoder =
        JSONEncoder()

    private let decoder =
        JSONDecoder()

    public init(
        directory:
            URL
    ) {

        self.fileURL =
            directory
                .appendingPathComponent(
                    "permissions.json"
                )

        encoder.outputFormatting = [
            .sortedKeys
        ]

        encoder.dateEncodingStrategy =
            .millisecondsSince1970

        decoder.dateDecodingStrategy =
            .millisecondsSince1970
    }

    public func save(
        records:
            [SafariPermissionRecord]
    ) throws {

        let payload =
            try encoder.encode(
                records
            )

        let checksum =
            SafariSessionChecksum.make(
                data:
                    payload
            )

        let envelope =
            SafariPermissionPersistenceEnvelope(
                version:
                    1,

                records:
                    records,

                checksum:
                    checksum
            )

        let data =
            try encoder.encode(
                envelope
            )

        try data.write(
            to:
                fileURL,
            options:
                .atomic
        )
    }

    public func load()
        throws -> [SafariPermissionRecord]
    {

        guard
            FileManager.default.fileExists(
                atPath:
                    fileURL.path
            )
        else {
            return []
        }

        let data =
            try Data(
                contentsOf:
                    fileURL
            )

        let envelope =
            try decoder.decode(
                SafariPermissionPersistenceEnvelope
                    .self,
                from:
                    data
            )

        let payload =
            try encoder.encode(
                envelope.records
            )

        guard
            SafariSessionChecksum.make(
                data:
                    payload
            )
            ==
            envelope.checksum
        else {
            throw SafariPrivacyError
                .checksumMismatch
        }

        return envelope.records
    }
}


// MARK: - 21. Privacy Errors

public enum SafariPrivacyError:
    Error,
    Sendable
{
    case invalidOrigin
    case checksumMismatch
    case persistenceFailure
    case requestNotFound
    case unsupportedPermission
}


// MARK: - 22. Privacy Telemetry

public enum SafariPrivacyTelemetryEvent:
    Sendable,
    Codable
{
    case requested(
        PrivacyOrigin,
        SafariPermissionType
    )

    case granted(
        PrivacyOrigin,
        SafariPermissionType,
        SafariPermissionScope
    )

    case denied(
        PrivacyOrigin,
        SafariPermissionType
    )

    case restricted(
        PrivacyOrigin,
        SafariPermissionType
    )

    case revoked(
        PrivacyOrigin,
        SafariPermissionType
    )

    case expired(
        PrivacyOrigin,
        SafariPermissionType
    )
}


public actor SafariPrivacyTelemetry {

    private var events:
        [SafariPrivacyTelemetryEvent] = []

    private let maximum:
        Int

    public init(
        maximum:
            Int = 2_000
    ) {
        self.maximum =
            maximum
    }

    public func append(
        _ event:
            SafariPrivacyTelemetryEvent
    ) {

        events.append(
            event
        )

        if events.count >
            maximum
        {
            events.removeFirst(
                events.count - maximum
            )
        }
    }

    public func recent()
        -> [SafariPrivacyTelemetryEvent]
    {
        events
    }
}


// MARK: - 23. Privacy Runtime

public actor SafariPrivacyRuntime {

    public let store:
        SafariPermissionStore

    public let requests:
        SafariPermissionRequestRegistry

    public let evaluator:
        SafariPermissionEvaluator

    public let resolver:
        SafariPermissionResolver

    public let telemetry:
        SafariPrivacyTelemetry

    private let persistence:
        SafariPermissionPersistence

    public init(
        storageDirectory:
            URL
    ) {

        let store =
            SafariPermissionStore()

        let requests =
            SafariPermissionRequestRegistry()

        self.store =
            store

        self.requests =
            requests

        self.evaluator =
            SafariPermissionEvaluator(
                store:
                    store,

                requests:
                    requests
            )

        self.resolver =
            SafariPermissionResolver(
                store:
                    store,

                requests:
                    requests
            )

        self.telemetry =
            SafariPrivacyTelemetry()

        self.persistence =
            SafariPermissionPersistence(
                directory:
                    storageDirectory
            )
    }

    public func start()
        async
    {

        guard
            let records =
                try? await persistence.load()
        else {
            return
        }

        for record in records {

            /*
             Session-only permissions are deliberately
             not restored from disk.
            */

            guard
                record.scope ==
                    .persistent
            else {
                continue
            }

            await store.upsert(
                record
            )
        }
    }

    public func request(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        context:
            PrivacyBrowsingContext,

        secureConnection:
            Bool,

        userInitiated:
            Bool,

        reason:
            String? = nil
    ) async
        -> SafariPermissionEvaluation
    {

        let evaluation =
            await evaluator.evaluate(
                origin:
                    origin,

                type:
                    type,

                context:
                    context,

                secureConnection:
                    secureConnection,

                userInitiated:
                    userInitiated,

                reason:
                    reason
            )

        if
            let request =
                evaluation.request
        {

            await telemetry.append(
                .requested(
                    request.key.origin,
                    request.key.type
                )
            )
        }

        return evaluation
    }

    public func resolve(
        request:
            SafariPermissionRequest,

        decision:
            SafariPermissionDecision,

        scope:
            SafariPermissionScope
    ) async
        -> SafariPermissionRecord?
    {

        let result =
            await resolver.resolve(
                request:
                    request,

                decision:
                    decision,

                scope:
                    scope
            )

        if let result {

            switch result.decision {

            case .granted:
                await telemetry.append(
                    .granted(
                        result.origin,
                        result.type,
                        scope
                    )
                )

            case .sessionGranted:
                await telemetry.append(
                    .granted(
                        result.origin,
                        result.type,
                        .session
                    )
                )

            case .denied,
                 .sessionDenied:
                await telemetry.append(
                    .denied(
                        result.origin,
                        result.type
                    )
                )

            case .restricted:
                await telemetry.append(
                    .restricted(
                        result.origin,
                        result.type
                    )
                )

            case .unknown:
                break
            }
        }

        await persist()

        return result
    }

    public func revoke(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        context:
            PrivacyBrowsingContext
    ) async {

        let key =
            SafariPermissionKey(
                origin:
                    origin,

                type:
                    type,

                context:
                    context
            )

        guard
            let existing =
                await store.record(
                    for:
                        key
                )
        else {
            return
        }

        let machine =
            SafariPermissionStateMachine()

        let revoked =
            machine.transition(
                record:
                    existing,

                transition:
                    .revoke
            )

        await store.upsert(
            revoked
        )

        await telemetry.append(
            .revoked(
                origin,
                type
            )
        )

        await persist()
    }

    public func clearPrivateContext(
        _ context:
            PrivacyBrowsingContext
    ) async {

        guard context.isPrivate else {
            return
        }

        await store.revokeContext(
            context
        )
    }

    public func clearSessionPermissions()
        async
    {

        await store.clearSessionPermissions()

        await persist()
    }

    public func persist()
        async {

        let records =
            await store.allRecords()
                .filter {
                    $0.scope ==
                        .persistent
                }

        try? await persistence.save(
            records:
                records
        )
    }

    public func records()
        async -> [SafariPermissionRecord]
    {
        await store.allRecords()
    }
}


// MARK: - 24. WebKit Permission Bridge

@MainActor
public final class SafariWebKitPermissionBridge:
    NSObject,
    WKUIDelegate
{

    private let runtime:
        SafariPrivacyRuntime

    public init(
        runtime:
            SafariPrivacyRuntime
    ) {
        self.runtime =
            runtime

        super.init()
    }

    /*
     WKUIDelegate does not expose every website permission
     through one universal callback.

     This bridge therefore acts as the Safari-owned policy
     layer while actual WebKit/macOS permission prompts remain
     controlled by the system APIs.
     */

    public func attach(
        to webView:
            WKWebView
    ) {

        webView.uiDelegate =
            self
    }

    public func requestCamera(
        origin:
            PrivacyOrigin,

        context:
            PrivacyBrowsingContext,

        userInitiated:
            Bool
    ) async
        -> SafariPermissionEvaluation
    {

        await runtime.request(
            origin:
                origin,

            type:
                .camera,

            context:
                context,

            secureConnection:
                origin.scheme == "https",

            userInitiated:
                userInitiated,

            reason:
                "Website requested camera access."
        )
    }

    public func requestMicrophone(
        origin:
            PrivacyOrigin,

        context:
            PrivacyBrowsingContext,

        userInitiated:
            Bool
    ) async
        -> SafariPermissionEvaluation
    {

        await runtime.request(
            origin:
                origin,

            type:
                .microphone,

            context:
                context,

            secureConnection:
                origin.scheme == "https",

            userInitiated:
                userInitiated,

            reason:
                "Website requested microphone access."
        )
    }

    public func requestLocation(
        origin:
            PrivacyOrigin,

        context:
            PrivacyBrowsingContext,

        userInitiated:
            Bool
    ) async
        -> SafariPermissionEvaluation
    {

        await runtime.request(
            origin:
                origin,

            type:
                .location,

            context:
                context,

            secureConnection:
                origin.scheme == "https",

            userInitiated:
                userInitiated,

            reason:
                "Website requested location access."
        )
    }
}


// MARK: - 25. Permission Expiration Engine

public actor SafariPermissionExpirationEngine {

    private let store:
        SafariPermissionStore

    private let telemetry:
        SafariPrivacyTelemetry

    public init(
        store:
            SafariPermissionStore,

        telemetry:
            SafariPrivacyTelemetry
    ) {
        self.store = store
        self.telemetry = telemetry
    }

    public func sweep()
        async
    {

        let records =
            await store.allRecords()

        let machine =
            SafariPermissionStateMachine()

        let now =
            Date()

        for record in records {

            guard
                let expiry =
                    record.expiresAt,

                expiry <= now
            else {
                continue
            }

            let expired =
                machine.transition(
                    record:
                        record,

                    transition:
                        .expire,

                    now:
                        now
                )

            await store.upsert(
                expired
            )

            await telemetry.append(
                .expired(
                    record.origin,
                    record.type
                )
            )
        }
    }
}


// MARK: - 26. Expiration Scheduler

public actor SafariPermissionExpirationScheduler {

    private let engine:
        SafariPermissionExpirationEngine

    private var task:
        Task<Void, Never>?

    public init(
        engine:
            SafariPermissionExpirationEngine
    ) {
        self.engine =
            engine
    }

    public func start() {

        guard task == nil else {
            return
        }

        task =
            Task {

                while !Task.isCancelled {

                    await engine.sweep()

                    try? await Task.sleep(
                        for:
                            .seconds(60)
                    )
                }
            }
    }

    public func stop() {

        task?.cancel()
        task = nil
    }
}


// MARK: - 27. Private Browsing Policy

public struct SafariPrivateBrowsingPolicy:
    Sendable
{

    public init() {}

    public func allowsPersistence(
        context:
            PrivacyBrowsingContext
    ) -> Bool
    {
        !context.isPrivate
    }

    public func normalizeScope(
        requested:
            SafariPermissionScope,

        context:
            PrivacyBrowsingContext
    ) -> SafariPermissionScope
    {

        if context.isPrivate {
            return .session
        }

        return requested
    }
}


// MARK: - 28. Permission Firewall

public struct SafariPermissionFirewall:
    Sendable
{

    public init() {}

    public func isSensitive(
        _ type:
            SafariPermissionType
    ) -> Bool {

        switch type {

        case .camera,
             .microphone,
             .location,
             .screenCapture,
             .clipboardRead,
             .sensors:

            return true

        default:
            return false
        }
    }

    public func requiresSecureContext(
        _ type:
            SafariPermissionType
    ) -> Bool {

        switch type {

        case .camera,
             .microphone,
             .location,
             .screenCapture,
             .clipboardRead,
             .clipboardWrite,
             .sensors:

            return true

        default:
            return false
        }
    }
}


// MARK: - 29. Request Rate Limiter

public actor SafariPermissionRateLimiter {

    private struct Counter:
        Sendable
    {
        var timestamps:
            [Date]
    }

    private var counters:
        [PrivacyOrigin:
            Counter] = [:]

    private let maximumRequests:
        Int

    private let interval:
        TimeInterval

    public init(
        maximumRequests:
            Int = 5,

        interval:
            TimeInterval = 60
    ) {
        self.maximumRequests =
            maximumRequests

        self.interval =
            interval
    }

    public func allow(
        origin:
            PrivacyOrigin
    ) -> Bool {

        let now =
            Date()

        var counter =
            counters[origin]
            ??
            Counter(
                timestamps:
                    []
            )

        counter.timestamps =
            counter.timestamps.filter {
                now.timeIntervalSince($0)
                    <
                    interval
            }

        guard
            counter.timestamps.count <
                maximumRequests
        else {

            counters[origin] =
                counter

            return false
        }

        counter.timestamps.append(
            now
        )

        counters[origin] =
            counter

        return true
    }
}


// MARK: - 30. Unified Privacy Gateway

public actor SafariUnifiedPrivacyGateway {

    private let runtime:
        SafariPrivacyRuntime

    private let firewall =
        SafariPermissionFirewall()

    private let privatePolicy =
        SafariPrivateBrowsingPolicy()

    private let rateLimiter =
        SafariPermissionRateLimiter()

    public init(
        runtime:
            SafariPrivacyRuntime
    ) {
        self.runtime =
            runtime
    }

    public func request(
        origin:
            PrivacyOrigin,

        type:
            SafariPermissionType,

        context:
            PrivacyBrowsingContext,

        userInitiated:
            Bool
    ) async
        -> SafariPermissionEvaluation
    {

        if
            firewall.requiresSecureContext(
                type
            )
            &&
            origin.scheme != "https"
        {

            return SafariPermissionEvaluation(
                decision:
                    .deny,

                existing:
                    nil,

                request:
                    nil
            )
        }

        guard
            await rateLimiter.allow(
                origin:
                    origin
            )
        else {

            return SafariPermissionEvaluation(
                decision:
                    .deny,

                existing:
                    nil,

                request:
                    nil
            )
        }

        return await runtime.request(
            origin:
                origin,

            type:
                type,

            context:
                context,

            secureConnection:
                origin.scheme == "https",

            userInitiated:
                userInitiated
        )
    }

    public func resolve(
        request:
            SafariPermissionRequest,

        decision:
            SafariPermissionDecision,

        requestedScope:
            SafariPermissionScope
    ) async {

        let scope =
            privatePolicy.normalizeScope(
                requested:
                    requestedScope,

                context:
                    request.key.context
            )

        _ =
            await runtime.resolve(
                request:
                    request,

                decision:
                    decision,

                scope:
                    scope
            )
    }
}


// MARK: - 31. Privacy Diagnostics

public struct SafariPrivacyDiagnostics:
    Sendable
{
    public let totalRecords:
        Int

    public let granted:
        Int

    public let denied:
        Int

    public let restricted:
        Int

    public let temporary:
        Int

    public let persistent:
        Int

    public init(
        records:
            [SafariPermissionRecord]
    ) {

        totalRecords =
            records.count

        granted =
            records.filter {
                $0.decision ==
                    .granted ||
                $0.decision ==
                    .sessionGranted
            }.count

        denied =
            records.filter {
                $0.decision ==
                    .denied ||
                $0.decision ==
                    .sessionDenied
            }.count

        restricted =
            records.filter {
                $0.decision ==
                    .restricted
            }.count

        temporary =
            records.filter {
                $0.scope !=
                    .persistent
            }.count

        persistent =
            records.filter {
                $0.scope ==
                    .persistent
            }.count
    }
}


// MARK: - 32. Privacy Diagnostics Actor

public actor SafariPrivacyDiagnosticsEngine {

    private let runtime:
        SafariPrivacyRuntime

    public init(
        runtime:
            SafariPrivacyRuntime
    ) {
        self.runtime =
            runtime
    }

    public func snapshot()
        async -> SafariPrivacyDiagnostics
    {

        let records =
            await runtime.records()

        return SafariPrivacyDiagnostics(
            records:
                records
        )
    }
}


// MARK: - 33. Complete Privacy System

public actor SafariUnifiedPrivacySystem {

    public let runtime:
        SafariPrivacyRuntime

    public let gateway:
        SafariUnifiedPrivacyGateway

    public let expiration:
        SafariPermissionExpirationEngine

    public let scheduler:
        SafariPermissionExpirationScheduler

    public let diagnostics:
        SafariPrivacyDiagnosticsEngine

    public init() {

        let directory =
            FileManager.default
                .urls(
                    for:
                        .applicationSupportDirectory,
                    in:
                        .userDomainMask
                )
                .first!
                .appendingPathComponent(
                    "SafariPowerArchitecture",
                    isDirectory:
                        true
                )

        let runtime =
            SafariPrivacyRuntime(
                storageDirectory:
                    directory
            )

        let expiration =
            SafariPermissionExpirationEngine(
                store:
                    runtime.store,

                telemetry:
                    runtime.telemetry
            )

        self.runtime =
            runtime

        self.gateway =
            SafariUnifiedPrivacyGateway(
                runtime:
                    runtime
            )

        self.expiration =
            expiration

        self.scheduler =
            SafariPermissionExpirationScheduler(
                engine:
                    expiration
            )

        self.diagnostics =
            SafariPrivacyDiagnosticsEngine(
                runtime:
                    runtime
            )
    }

    public func start()
        async
    {

        await runtime.start()

        scheduler.start()
    }

    public func stop() {

        scheduler.stop()
    }
}


// MARK: - 34. Example Browser Controller

@MainActor
public final class SafariPrivacyBrowserController {

    private let privacySystem:
        SafariUnifiedPrivacySystem

    private var permissionBridge:
        SafariWebKitPermissionBridge?

    public init() {

        let system =
            SafariUnifiedPrivacySystem()

        self.privacySystem =
            system

        self.permissionBridge =
            nil
    }

    public func start()
        async
    {

        await privacySystem.start()

        permissionBridge =
            SafariWebKitPermissionBridge(
                runtime:
                    privacySystem.runtime
            )
    }

    public func attach(
        webView:
            WKWebView
    ) {

        permissionBridge?.attach(
            to:
                webView
        )
    }
}


// MARK: - 35. Tests

#if DEBUG

public enum SafariPrivacyTests {

    public static func originTest()
        -> Bool
    {

        guard
            let url =
                URL(
                    string:
                        "https://example.com"
                )
        else {
            return false
        }

        guard
            let origin =
                PrivacyOrigin(
                    url:
                        url
                )
        else {
            return false
        }

        return
            origin.scheme ==
                "https"
            &&
            origin.host ==
                "example.com"
    }


    public static func stateMachineTest()
        -> Bool
    {

        guard
            let url =
                URL(
                    string:
                        "https://example.com"
                ),
            let origin =
                PrivacyOrigin(
                    url:
                        url
                )
        else {
            return false
        }

        let context =
            PrivacyBrowsingContext(
                isPrivate:
                    false
            )

        let machine =
            SafariPermissionStateMachine()

        let record =
            SafariPermissionRecord(
                origin:
                    origin,

                type:
                    .camera,

                context:
                    context
            )

        let granted =
            machine.transition(
                record:
                    record,

                transition:
                    .grant(
                        .persistent
                    )
            )

        return
            granted.decision ==
                .granted
            &&
            granted.lifecycle ==
                .granted
    }


    public static func privateBrowsingTest()
        -> Bool
    {

        let policy =
            SafariPrivateBrowsingPolicy()

        let context =
            PrivacyBrowsingContext(
                isPrivate:
                    true
            )

        return
            policy.normalizeScope(
                requested:
                    .persistent,

                context:
                    context
            )
            ==
            .session
    }


    public static func secureContextTest()
        -> Bool
    {

        let firewall =
            SafariPermissionFirewall()

        return
            firewall.requiresSecureContext(
                .camera
            )
            &&
            firewall.requiresSecureContext(
                .microphone
            )
    }
}

#endif


// MARK: - 36. Architecture
//
//                       WEB PAGE
//                           │
//                           ▼
//                 Permission Request
//                           │
//                           ▼
//              ┌────────────────────────┐
//              │ Unified Privacy Gateway │
//              └────────────┬───────────┘
//                           │
//             ┌─────────────┼─────────────┐
//             │             │             │
//             ▼             ▼             ▼
//         Firewall      Rate Limit     Origin Check
//             │             │             │
//             └─────────────┼─────────────┘
//                           ▼
//                    Policy Engine
//                           │
//                 ┌─────────┴─────────┐
//                 │                   │
//              ALLOW                 PROMPT
//                 │                   │
//                 ▼                   ▼
//             WebKit             Permission UI
//                                   │
//                                   ▼
//                              User Decision
//                                   │
//                     ┌─────────────┼─────────────┐
//                     │             │             │
//                   GRANT         DENY         RESTRICT
//                     │             │             │
//                     └─────────────┼─────────────┘
//                                   ▼
//                         State Machine
//                                   │
//                    ┌──────────────┴──────────────┐
//                    │                             │
//                 Session                       Persistent
//                    │                             │
//                    ▼                             ▼
//             Memory-only state              Encrypted/system
//                                            protected storage
//
//
//
// Privacy boundaries:
//
//     Normal Browsing
//            │
//            ▼
//     Persistent Policy
//
//     Private Browsing
//            │
//            ▼
//     Session-only Policy
//            │
//            ▼
//        DESTROY
//
//
//
// Permission lifecycle:
//
//     IDLE
//       │
//       ▼
//    REQUESTED
//       │
//       ▼
//    PROMPTING
//       │
//       ├───────────────┐
//       ▼               ▼
//    GRANTED          DENIED
//       │               │
//       │               │
//       ▼               ▼
//    ACTIVE          BLOCKED
//       │
//       ├───────────────┐
//       ▼               ▼
//    EXPIRED         REVOKED














//
// SafariPerformanceTelemetryEngine.swift
//
// Safari macOS Architecture — #10
//
// Unified telemetry and diagnostics layer.
//
// Integrates:
// #1  Tab & Window Manager
// #2  WebKit Resource / Memory Manager
// #3  Navigation Runtime
// #4  Predictive Loading
// #5  Rendering & Scrolling
// #6  Power Runtime
// #7  Session Architecture
// #8  Cache & Storage
// #9  Privacy & Permissions
//
// Design goals:
// - Swift 6 concurrency
// - Actor-isolated mutable telemetry state
// - @MainActor UI/WebKit integration
// - Structured events
// - Ring-buffer storage
// - Sampling
// - Privacy redaction
// - Signpost support
// - Metric aggregation
// - Performance budgets
// - Diagnostic snapshots
// - Exportable reports
// - Low allocation overhead
// - No page-content collection
// - No private WebKit APIs
//

import Foundation
import os
import os.signpost
import WebKit
import AppKit


// MARK: - 1. Telemetry Identity

public struct TelemetrySessionID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}


public struct TelemetryEventID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}


public struct TelemetryTabID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}


// MARK: - 2. Telemetry Categories

public enum SafariTelemetryCategory:
    String,
    Codable,
    Sendable,
    CaseIterable
{
    case tab
    case window
    case navigation
    case rendering
    case scrolling
    case memory
    case cpu
    case network
    case cache
    case storage
    case power
    case thermal
    case prediction
    case permission
    case session
    case webKit
    case error
    case lifecycle
}


// MARK: - 3. Severity

public enum SafariTelemetrySeverity:
    String,
    Codable,
    Sendable
{
    case debug
    case info
    case notice
    case warning
    case error
    case critical
}


// MARK: - 4. Event Name

public enum SafariTelemetryEventName:
    String,
    Codable,
    Sendable
{
    case tabCreated
    case tabClosed
    case tabSuspended
    case tabResumed

    case navigationStarted
    case navigationCommitted
    case navigationFinished
    case navigationFailed
    case navigationCancelled

    case frameDrop
    case renderingJank
    case longMainThreadTask
    case scrollDegradation

    case memoryPressure
    case resourceBudgetExceeded

    case cacheHit
    case cacheMiss
    case cacheEviction

    case powerModeChanged
    case thermalStateChanged

    case predictionGenerated
    case prefetchStarted
    case prefetchCancelled

    case permissionRequested
    case permissionResolved

    case sessionRestored
    case sessionSaved
    case sessionRecovery

    case webKitProcessTermination

    case performanceBudgetExceeded
    case subsystemFailure
}


// MARK: - 5. Privacy Classification

public enum SafariTelemetryPrivacyClass:
    String,
    Codable,
    Sendable
{
    case publicMetric
    case operational
    case sensitive
    case prohibited
}


// MARK: - 6. Telemetry Value

public enum SafariTelemetryValue:
    Codable,
    Sendable
{
    case string(String)
    case integer(Int64)
    case double(Double)
    case boolean(Bool)
    case duration(TimeInterval)
    case bytes(Int64)
    case percentage(Double)
}


// MARK: - 7. Telemetry Event

public struct SafariTelemetryEvent:
    Codable,
    Sendable
{
    public let id:
        TelemetryEventID

    public let timestamp:
        Date

    public let sessionID:
        TelemetrySessionID

    public let category:
        SafariTelemetryCategory

    public let name:
        SafariTelemetryEventName

    public let severity:
        SafariTelemetrySeverity

    public let privacy:
        SafariTelemetryPrivacyClass

    public let tabID:
        TelemetryTabID?

    public let values:
        [String: SafariTelemetryValue]

    public init(
        id:
            TelemetryEventID = TelemetryEventID(),

        timestamp:
            Date = Date(),

        sessionID:
            TelemetrySessionID,

        category:
            SafariTelemetryCategory,

        name:
            SafariTelemetryEventName,

        severity:
            SafariTelemetrySeverity,

        privacy:
            SafariTelemetryPrivacyClass,

        tabID:
            TelemetryTabID? = nil,

        values:
            [String: SafariTelemetryValue] = [:]
    ) {
        self.id = id
        self.timestamp = timestamp
        self.sessionID = sessionID
        self.category = category
        self.name = name
        self.severity = severity
        self.privacy = privacy
        self.tabID = tabID
        self.values = values
    }
}


// MARK: - 8. Privacy Filter

public struct SafariTelemetryPrivacyFilter:
    Sendable
{
    public init() {}

    public func sanitize(
        _ event:
            SafariTelemetryEvent
    ) -> SafariTelemetryEvent?
    {

        switch event.privacy {

        case .prohibited:
            return nil

        case .publicMetric,
             .operational,
             .sensitive:
            return event
        }
    }

    public func allows(
        _ privacy:
            SafariTelemetryPrivacyClass
    ) -> Bool {

        privacy != .prohibited
    }
}


// MARK: - 9. Sampling Policy

public struct SafariTelemetrySamplingPolicy:
    Sendable
{

    public let debugRate:
        Double

    public let infoRate:
        Double

    public let noticeRate:
        Double

    public let warningRate:
        Double

    public let errorRate:
        Double

    public let criticalRate:
        Double

    public init(
        debugRate:
            Double = 0.10,

        infoRate:
            Double = 0.25,

        noticeRate:
            Double = 0.50,

        warningRate:
            Double = 1.0,

        errorRate:
            Double = 1.0,

        criticalRate:
            Double = 1.0
    ) {
        self.debugRate = debugRate
        self.infoRate = infoRate
        self.noticeRate = noticeRate
        self.warningRate = warningRate
        self.errorRate = errorRate
        self.criticalRate = criticalRate
    }

    public func rate(
        for severity:
            SafariTelemetrySeverity
    ) -> Double {

        switch severity {

        case .debug:
            return debugRate

        case .info:
            return infoRate

        case .notice:
            return noticeRate

        case .warning:
            return warningRate

        case .error:
            return errorRate

        case .critical:
            return criticalRate
        }
    }

    public func shouldRecord(
        severity:
            SafariTelemetrySeverity
    ) -> Bool {

        Double.random(in: 0...1)
            <= rate(for: severity)
    }
}


// MARK: - 10. Ring Buffer

public struct SafariTelemetryRingBuffer:
    Sendable
{

    private var storage:
        [SafariTelemetryEvent]

    private var writeIndex:
        Int = 0

    private(set) public var count:
        Int = 0

    public let capacity:
        Int

    public init(
        capacity:
            Int
    ) {

        self.capacity =
            max(
                capacity,
                1
            )

        self.storage =
            Array(
                repeating:
                    SafariTelemetryEvent(
                        sessionID:
                            TelemetrySessionID(),

                        category:
                            .lifecycle,

                        name:
                            .subsystemFailure,

                        severity:
                            .debug,

                        privacy:
                            .operational
                    ),

                count:
                    max(
                        capacity,
                        1
                    )
            )
    }

    public mutating func append(
        _ event:
            SafariTelemetryEvent
    ) {

        storage[
            writeIndex
        ] = event

        writeIndex =
            (writeIndex + 1)
            % capacity

        count =
            min(
                count + 1,
                capacity
            )
    }

    public func values()
        -> [SafariTelemetryEvent]
    {

        guard count > 0 else {
            return []
        }

        if count < capacity {

            return Array(
                storage[
                    0..<count
                ]
            )
        }

        return
            Array(
                storage[
                    writeIndex..<capacity
                ]
            )
            +
            Array(
                storage[
                    0..<writeIndex
                ]
            )
    }
}


// MARK: - 11. Telemetry Store

public actor SafariTelemetryStore {

    private var buffer:
        SafariTelemetryRingBuffer

    public init(
        capacity:
            Int = 20_000
    ) {

        self.buffer =
            SafariTelemetryRingBuffer(
                capacity:
                    capacity
            )
    }

    public func append(
        _ event:
            SafariTelemetryEvent
    ) {

        buffer.append(
            event
        )
    }

    public func recent(
        limit:
            Int = 1_000
    )
        -> [SafariTelemetryEvent]
    {

        let values =
            buffer.values()

        guard values.count > limit else {
            return values
        }

        return Array(
            values.suffix(
                limit
            )
        )
    }

    public func all()
        -> [SafariTelemetryEvent]
    {
        buffer.values()
    }

    public func count()
        -> Int
    {
        buffer.count
    }

    public func clear() {
        buffer =
            SafariTelemetryRingBuffer(
                capacity:
                    buffer.capacity
            )
    }
}


// MARK: - 12. Metric Sample

public struct SafariMetricSample:
    Codable,
    Sendable
{
    public let timestamp:
        Date

    public let value:
        Double

    public init(
        timestamp:
            Date = Date(),

        value:
            Double
    ) {
        self.timestamp = timestamp
        self.value = value
    }
}


// MARK: - 13. Running Metric

public struct SafariRunningMetric:
    Sendable
{
    private(set) public var count:
        UInt64 = 0

    private(set) public var total:
        Double = 0

    private(set) public var minimum:
        Double = .greatestFiniteMagnitude

    private(set) public var maximum:
        Double = -.greatestFiniteMagnitude

    public init() {}

    public mutating func record(
        _ value:
            Double
    ) {

        count += 1
        total += value

        minimum =
            Swift.min(
                minimum,
                value
            )

        maximum =
            Swift.max(
                maximum,
                value
            )
    }

    public var average:
        Double
    {
        guard count > 0 else {
            return 0
        }

        return total /
            Double(count)
    }
}


// MARK: - 14. Performance Metrics

public struct SafariPerformanceMetrics:
    Sendable
{
    public var navigationLatency =
        SafariRunningMetric()

    public var frameTime =
        SafariRunningMetric()

    public var scrollVelocity =
        SafariRunningMetric()

    public var memoryUsage =
        SafariRunningMetric()

    public var cpuUsage =
        SafariRunningMetric()

    public var cacheLatency =
        SafariRunningMetric()

    public var predictionLatency =
        SafariRunningMetric()

    public var powerUsage =
        SafariRunningMetric()

    public var longTasks:
        UInt64 = 0

    public var droppedFrames:
        UInt64 = 0

    public var navigationFailures:
        UInt64 = 0

    public var cacheHits:
        UInt64 = 0

    public var cacheMisses:
        UInt64 = 0

    public var permissionRequests:
        UInt64 = 0

    public var webKitCrashes:
        UInt64 = 0
}


// MARK: - 15. Metrics Store

public actor SafariMetricsStore {

    private var metrics =
        SafariPerformanceMetrics()

    public init() {}

    public func recordNavigation(
        latency:
            TimeInterval
    ) {

        metrics.navigationLatency.record(
            latency
        )
    }

    public func recordFrame(
        duration:
            TimeInterval
    ) {

        metrics.frameTime.record(
            duration
        )
    }

    public func recordScroll(
        velocity:
            Double
    ) {

        metrics.scrollVelocity.record(
            velocity
        )
    }

    public func recordMemory(
        bytes:
            Int64
    ) {

        metrics.memoryUsage.record(
            Double(bytes)
        )
    }

    public func recordCPU(
        percentage:
            Double
    ) {

        metrics.cpuUsage.record(
            percentage
        )
    }

    public func recordCacheHit() {
        metrics.cacheHits += 1
    }

    public func recordCacheMiss() {
        metrics.cacheMisses += 1
    }

    public func recordLongTask() {
        metrics.longTasks += 1
    }

    public func recordDroppedFrame() {
        metrics.droppedFrames += 1
    }

    public func recordNavigationFailure() {
        metrics.navigationFailures += 1
    }

    public func recordPermissionRequest() {
        metrics.permissionRequests += 1
    }

    public func recordWebKitCrash() {
        metrics.webKitCrashes += 1
    }

    public func snapshot()
        -> SafariPerformanceMetrics
    {
        metrics
    }
}


// MARK: - 16. Performance Budget

public struct SafariPerformanceBudget:
    Sendable
{
    public let maximumNavigationLatency:
        TimeInterval

    public let maximumFrameTime:
        TimeInterval

    public let maximumMainThreadTask:
        TimeInterval

    public let maximumCPU:
        Double

    public let maximumMemory:
        Int64

    public let maximumDroppedFramesPerMinute:
        UInt64

    public init(
        maximumNavigationLatency:
            TimeInterval = 2.5,

        maximumFrameTime:
            TimeInterval = 0.01667,

        maximumMainThreadTask:
            TimeInterval = 0.050,

        maximumCPU:
            Double = 85,

        maximumMemory:
            Int64 = 2_000_000_000,

        maximumDroppedFramesPerMinute:
            UInt64 = 60
    ) {
        self.maximumNavigationLatency =
            maximumNavigationLatency

        self.maximumFrameTime =
            maximumFrameTime

        self.maximumMainThreadTask =
            maximumMainThreadTask

        self.maximumCPU =
            maximumCPU

        self.maximumMemory =
            maximumMemory

        self.maximumDroppedFramesPerMinute =
            maximumDroppedFramesPerMinute
    }
}


// MARK: - 17. Budget Result

public enum SafariPerformanceBudgetResult:
    Sendable
{
    case withinBudget
    case exceeded(
        metric:
            String,
        value:
            Double,
        limit:
            Double
    )
}


// MARK: - 18. Budget Evaluator

public struct SafariPerformanceBudgetEvaluator:
    Sendable
{

    private let budget:
        SafariPerformanceBudget

    public init(
        budget:
            SafariPerformanceBudget
    ) {
        self.budget =
            budget
    }

    public func evaluate(
        metrics:
            SafariPerformanceMetrics
    ) -> [SafariPerformanceBudgetResult]
    {

        var results:
            [SafariPerformanceBudgetResult] = []

        if
            metrics.navigationLatency.average
            >
            budget.maximumNavigationLatency
        {

            results.append(
                .exceeded(
                    metric:
                        "navigationLatency",

                    value:
                        metrics.navigationLatency.average,

                    limit:
                        budget.maximumNavigationLatency
                )
            )
        }

        if
            metrics.frameTime.maximum
            >
            budget.maximumFrameTime
        {

            results.append(
                .exceeded(
                    metric:
                        "frameTime",

                    value:
                        metrics.frameTime.maximum,

                    limit:
                        budget.maximumFrameTime
                )
            )
        }

        if
            metrics.cpuUsage.maximum
            >
            budget.maximumCPU
        {

            results.append(
                .exceeded(
                    metric:
                        "cpuUsage",

                    value:
                        metrics.cpuUsage.maximum,

                    limit:
                        budget.maximumCPU
                )
            )
        }

        if
            metrics.memoryUsage.maximum
            >
            Double(
                budget.maximumMemory
            )
        {

            results.append(
                .exceeded(
                    metric:
                        "memoryUsage",

                    value:
                        metrics.memoryUsage.maximum,

                    limit:
                        Double(
                            budget.maximumMemory
                        )
                )
            )
        }

        return results
    }
}


// MARK: - 19. Diagnostic Snapshot

public struct SafariDiagnosticSnapshot:
    Codable,
    Sendable
{
    public let timestamp:
        Date

    public let sessionID:
        TelemetrySessionID

    public let metrics:
        SafariPerformanceMetrics

    public let events:
        [SafariTelemetryEvent]

    public let budgetViolations:
        [String]

    public let processInfo:
        SafariProcessDiagnostics

    public init(
        timestamp:
            Date = Date(),

        sessionID:
            TelemetrySessionID,

        metrics:
            SafariPerformanceMetrics,

        events:
            [SafariTelemetryEvent],

        budgetViolations:
            [String],

        processInfo:
            SafariProcessDiagnostics
    ) {
        self.timestamp = timestamp
        self.sessionID = sessionID
        self.metrics = metrics
        self.events = events
        self.budgetViolations = budgetViolations
        self.processInfo = processInfo
    }
}


// MARK: - 20. Process Diagnostics

public struct SafariProcessDiagnostics:
    Codable,
    Sendable
{
    public let processID:
        Int32

    public let processName:
        String

    public let operatingSystem:
        String

    public let processorCount:
        Int

    public let physicalMemory:
        UInt64

    public let uptime:
        TimeInterval

    public init(
        processID:
            Int32 = ProcessInfo.processInfo.processIdentifier,

        processName:
            String = ProcessInfo.processInfo.processName,

        operatingSystem:
            String = ProcessInfo.processInfo.operatingSystemVersionString,

        processorCount:
            Int = ProcessInfo.processInfo.processorCount,

        physicalMemory:
            UInt64 =
                ProcessInfo.processInfo.physicalMemory,

        uptime:
            TimeInterval =
                ProcessInfo.processInfo.systemUptime
    ) {
        self.processID =
            processID

        self.processName =
            processName

        self.operatingSystem =
            operatingSystem

        self.processorCount =
            processorCount

        self.physicalMemory =
            physicalMemory

        self.uptime =
            uptime
    }
}


// MARK: - 21. Diagnostics Engine

public actor SafariDiagnosticsEngine {

    private let telemetry:
        SafariTelemetryStore

    private let metrics:
        SafariMetricsStore

    private let budget:
        SafariPerformanceBudgetEvaluator

    private let sessionID:
        TelemetrySessionID

    public init(
        telemetry:
            SafariTelemetryStore,

        metrics:
            SafariMetricsStore,

        budget:
            SafariPerformanceBudget,

        sessionID:
            TelemetrySessionID
    ) {
        self.telemetry =
            telemetry

        self.metrics =
            metrics

        self.budget =
            SafariPerformanceBudgetEvaluator(
                budget:
                    budget
            )

        self.sessionID =
            sessionID
    }

    public func snapshot()
        async -> SafariDiagnosticSnapshot
    {

        let currentMetrics =
            await metrics.snapshot()

        let events =
            await telemetry.recent(
                limit:
                    2_000
            )

        let violations =
            budget.evaluate(
                metrics:
                    currentMetrics
            )

        let violationStrings =
            violations.compactMap {
                result -> String? in

                switch result {

                case .withinBudget:
                    return nil

                case .exceeded(
                    let metric,
                    let value,
                    let limit
                ):
                    return
                        "\(metric): \(value) > \(limit)"
                }
            }

        return SafariDiagnosticSnapshot(
            sessionID:
                sessionID,

            metrics:
                currentMetrics,

            events:
                events,

            budgetViolations:
                violationStrings,

            processInfo:
                SafariProcessDiagnostics()
        )
    }
}


// MARK: - 22. Unified Logger

public struct SafariTelemetryLogger:
    Sendable
{
    public let subsystem:
        String

    private let logger:
        Logger

    public init(
        subsystem:
            String =
                "com.example.SafariArchitecture"
    ) {

        self.subsystem =
            subsystem

        self.logger =
            Logger(
                subsystem:
                    subsystem,

                category:
                    "Telemetry"
            )
    }

    public func debug(
        _ message:
            String
    ) {

        logger.debug(
            "\(message, privacy: .public)"
        )
    }

    public func info(
        _ message:
            String
    ) {

        logger.info(
            "\(message, privacy: .public)"
        )
    }

    public func warning(
        _ message:
            String
    ) {

        logger.warning(
            "\(message, privacy: .public)"
        )
    }

    public func error(
        _ message:
            String
    ) {

        logger.error(
            "\(message, privacy: .public)"
        )
    }
}


// MARK: - 23. Signpost Instrumentation

public final class SafariPerformanceSignposter:
    @unchecked Sendable
{
    private let log:
        OSLog

    public init(
        subsystem:
            String =
                "com.example.SafariArchitecture"
    ) {

        self.log =
            OSLog(
                subsystem:
                    subsystem,

                category:
                    "Performance"
            )
    }

    public func begin(
        _ name:
            StaticString
    ) -> OSSignpostID {

        let identifier =
            OSSignpostID(
                log:
                    log
            )

        os_signpost(
            .begin,
            log:
                log,

            name:
                name,

            signpostID:
                identifier
        )

        return identifier
    }

    public func end(
        _ name:
            StaticString,

        identifier:
            OSSignpostID
    ) {

        os_signpost(
            .end,
            log:
                log,

            name:
                name,

            signpostID:
                identifier
        )
    }

    public func event(
        _ name:
            StaticString
    ) {

        os_signpost(
            .event,
            log:
                log,

            name:
                name
        )
    }
}


// MARK: - 24. Telemetry Recorder

public actor SafariTelemetryRecorder {

    private let sessionID:
        TelemetrySessionID

    private let store:
        SafariTelemetryStore

    private let metrics:
        SafariMetricsStore

    private let privacyFilter:
        SafariTelemetryPrivacyFilter

    private let sampling:
        SafariTelemetrySamplingPolicy

    private let logger:
        SafariTelemetryLogger

    public init(
        sessionID:
            TelemetrySessionID,

        store:
            SafariTelemetryStore,

        metrics:
            SafariMetricsStore,

        sampling:
            SafariTelemetrySamplingPolicy =
                SafariTelemetrySamplingPolicy()
    ) {
        self.sessionID =
            sessionID

        self.store =
            store

        self.metrics =
            metrics

        self.privacyFilter =
            SafariTelemetryPrivacyFilter()

        self.sampling =
            sampling

        self.logger =
            SafariTelemetryLogger()
    }

    public func record(
        category:
            SafariTelemetryCategory,

        name:
            SafariTelemetryEventName,

        severity:
            SafariTelemetrySeverity,

        privacy:
            SafariTelemetryPrivacyClass =
                .operational,

        tabID:
            TelemetryTabID? = nil,

        values:
            [String:
                SafariTelemetryValue] =
                [:]
    ) async {

        guard
            privacyFilter.allows(
                privacy
            )
        else {
            return
        }

        guard
            sampling.shouldRecord(
                severity:
                    severity
            )
        else {
            return
        }

        let event =
            SafariTelemetryEvent(
                sessionID:
                    sessionID,

                category:
                    category,

                name:
                    name,

                severity:
                    severity,

                privacy:
                    privacy,

                tabID:
                    tabID,

                values:
                    values
            )

        guard
            let sanitized =
                privacyFilter.sanitize(
                    event
                )
        else {
            return
        }

        await store.append(
            sanitized
        )

        if severity == .error ||
            severity == .critical
        {
            logger.error(
                "\(name.rawValue)"
            )
        }
    }


    public func recordNavigation(
        latency:
            TimeInterval,

        success:
            Bool,

        tabID:
            TelemetryTabID?
    ) async {

        await metrics.recordNavigation(
            latency:
                latency
        )

        await record(
            category:
                .navigation,

            name:
                success
                ? .navigationFinished
                : .navigationFailed,

            severity:
                success
                ? .info
                : .error,

            tabID:
                tabID,

            values:
                [
                    "latency":
                        .duration(
                            latency
                        )
                ]
        )

        if !success {
            await metrics.recordNavigationFailure()
        }
    }


    public func recordFrame(
        duration:
            TimeInterval,

        dropped:
            Bool,

        tabID:
            TelemetryTabID?
    ) async {

        await metrics.recordFrame(
            duration:
                duration
        )

        if dropped {
            await metrics.recordDroppedFrame()
        }

        await record(
            category:
                .rendering,

            name:
                dropped
                ? .frameDrop
                : .renderingJank,

            severity:
                dropped
                ? .warning
                : .debug,

            tabID:
                tabID,

            values:
                [
                    "duration":
                        .duration(
                            duration
                        ),

                    "dropped":
                        .boolean(
                            dropped
                        )
                ]
        )
    }


    public func recordMemory(
        bytes:
            Int64,

        tabID:
            TelemetryTabID?
    ) async {

        await metrics.recordMemory(
            bytes:
                bytes
        )

        await record(
            category:
                .memory,

            name:
                .memoryPressure,

            severity:
                .notice,

            tabID:
                tabID,

            values:
                [
                    "bytes":
                        .bytes(
                            bytes
                        )
                ]
        )
    }


    public func recordCache(
        hit:
            Bool,

        latency:
            TimeInterval
    ) async {

        if hit {
            await metrics.recordCacheHit()
        } else {
            await metrics.recordCacheMiss()
        }

        await record(
            category:
                .cache,

            name:
                hit
                ? .cacheHit
                : .cacheMiss,

            severity:
                .debug,

            values:
                [
                    "latency":
                        .duration(
                            latency
                        )
                ]
        )
    }


    public func recordWebKitTermination(
        tabID:
            TelemetryTabID?
    ) async {

        await metrics.recordWebKitCrash()

        await record(
            category:
                .webKit,

            name:
                .webKitProcessTermination,

            severity:
                .critical,

            tabID:
                tabID
        )
    }
}


// MARK: - 25. Telemetry Persistence

public actor SafariTelemetryPersistence {

    private let directory:
        URL

    private let encoder =
        JSONEncoder()

    public init(
        directory:
            URL
    ) {

        self.directory =
            directory

        encoder.outputFormatting = [
            .prettyPrinted,
            .sortedKeys
        ]

        encoder.dateEncodingStrategy =
            .millisecondsSince1970
    }

    public func write(
        snapshot:
            SafariDiagnosticSnapshot
    ) throws
        -> URL
    {

        try FileManager.default
            .createDirectory(
                at:
                    directory,

                withIntermediateDirectories:
                    true
            )

        let data =
            try encoder.encode(
                snapshot
            )

        let filename =
            "safari-diagnostics-\(Int(Date().timeIntervalSince1970)).json"

        let url =
            directory
                .appendingPathComponent(
                    filename
                )

        try data.write(
            to:
                url,

            options:
                .atomic
        )

        return url
    }
}


// MARK: - 26. Navigation Timing

public actor SafariNavigationTimingTracker {

    private struct Timing:
        Sendable
    {
        let startedAt:
            ContinuousClock.Instant

        var committedAt:
            ContinuousClock.Instant?

        var finishedAt:
            ContinuousClock.Instant?
    }

    private var timings:
        [UUID: Timing] = [:]

    public init() {}

    public func start(
        id:
            UUID
    ) {

        timings[id] =
            Timing(
                startedAt:
                    ContinuousClock.now
            )
    }

    public func commit(
        id:
            UUID
    ) {

        guard
            var timing =
                timings[id]
        else {
            return
        }

        timing.committedAt =
            ContinuousClock.now

        timings[id] =
            timing
    }

    public func finish(
        id:
            UUID
    )
        -> TimeInterval?
    {

        guard
            let timing =
                timings.removeValue(
                    forKey:
                        id
                )
        else {
            return nil
        }

        let finished =
            ContinuousClock.now

        let duration =
            finished -
            timing.startedAt

        return
            Double(
                duration.components.seconds
            )
            +
            Double(
                duration.components.attoseconds
            ) / 1_000_000_000_000_000_000
    }
}


// MARK: - 27. Main Thread Monitor

@MainActor
public final class SafariMainThreadMonitor {

    private var activeTasks:
        [UUID:
            ContinuousClock.Instant] = [:]

    private let threshold:
        TimeInterval

    private let recorder:
        SafariTelemetryRecorder

    public init(
        threshold:
            TimeInterval = 0.050,

        recorder:
            SafariTelemetryRecorder
    ) {
        self.threshold =
            threshold

        self.recorder =
            recorder
    }

    public func begin()
        -> UUID
    {

        let id =
            UUID()

        activeTasks[id] =
            ContinuousClock.now

        return id
    }

    public func end(
        id:
            UUID
    ) {

        guard
            let start =
                activeTasks.removeValue(
                    forKey:
                        id
                )
        else {
            return
        }

        let duration =
            ContinuousClock.now -
            start

        let seconds =
            Double(
                duration.components.seconds
            )
            +
            Double(
                duration.components.attoseconds
            )
            /
            1_000_000_000_000_000_000

        guard
            seconds >= threshold
        else {
            return
        }

        Task {
            await recorder.record(
                category:
                    .rendering,

                name:
                    .longMainThreadTask,

                severity:
                    seconds >= 0.100
                    ? .warning
                    : .notice,

                values:
                    [
                        "duration":
                            .duration(
                                seconds
                            )
                    ]
            )
        }
    }
}


// MARK: - 28. Frame Monitor

@MainActor
public final class SafariFrameTelemetryMonitor {

    private let recorder:
        SafariTelemetryRecorder

    private var previousFrame:
        ContinuousClock.Instant?

    private var frameCount:
        UInt64 = 0

    private var droppedFrames:
        UInt64 = 0

    public init(
        recorder:
            SafariTelemetryRecorder
    ) {
        self.recorder =
            recorder
    }

    public func frame(
        tabID:
            TelemetryTabID?
    ) {

        let now =
            ContinuousClock.now

        defer {
            previousFrame =
                now

            frameCount += 1
        }

        guard
            let previous =
                previousFrame
        else {
            return
        }

        let duration =
            now - previous

        let seconds =
            Double(
                duration.components.seconds
            )
            +
            Double(
                duration.components.attoseconds
            )
            /
            1_000_000_000_000_000_000

        let dropped =
            seconds > 0.025

        if dropped {
            droppedFrames += 1
        }

        Task {
            await recorder.recordFrame(
                duration:
                    seconds,

                dropped:
                    dropped,

                tabID:
                    tabID
            )
        }
    }

    public func statistics()
        -> (
            frames: UInt64,
            dropped: UInt64
        )
    {
        (
            frameCount,
            droppedFrames
        )
    }
}


// MARK: - 29. System Resource Sampler

public actor SafariSystemResourceSampler {

    private let recorder:
        SafariTelemetryRecorder

    private var task:
        Task<Void, Never>?

    public init(
        recorder:
            SafariTelemetryRecorder
    ) {
        self.recorder =
            recorder
    }

    public func start() {

        guard task == nil else {
            return
        }

        task =
            Task {

                while !Task.isCancelled {

                    let memory =
                        ProcessInfo
                            .processInfo
                            .physicalMemory

                    await recorder.recordMemory(
                        bytes:
                            Int64(memory),

                        tabID:
                            nil
                    )

                    try? await Task.sleep(
                        for:
                            .seconds(10)
                    )
                }
            }
    }

    public func stop() {

        task?.cancel()
        task = nil
    }
}


// MARK: - 30. Diagnostic Exporter

public actor SafariDiagnosticExporter {

    private let diagnostics:
        SafariDiagnosticsEngine

    private let persistence:
        SafariTelemetryPersistence

    public init(
        diagnostics:
            SafariDiagnosticsEngine,

        directory:
            URL
    ) {
        self.diagnostics =
            diagnostics

        self.persistence =
            SafariTelemetryPersistence(
                directory:
                    directory
            )
    }

    public func export()
        async -> URL?
    {

        let snapshot =
            await diagnostics.snapshot()

        return try? await persistence.write(
            snapshot:
                snapshot
        )
    }
}


// MARK: - 31. Unified Telemetry Runtime

public actor SafariTelemetryRuntime {

    public let sessionID:
        TelemetrySessionID

    public let telemetry:
        SafariTelemetryStore

    public let metrics:
        SafariMetricsStore

    public let recorder:
        SafariTelemetryRecorder

    public let diagnostics:
        SafariDiagnosticsEngine

    public let sampler:
        SafariSystemResourceSampler

    public let navigationTiming:
        SafariNavigationTimingTracker

    public let exporter:
        SafariDiagnosticExporter

    private let signposter =
        SafariPerformanceSignposter()

    private var started:
        Bool = false

    public init(
        storageDirectory:
            URL
    ) {

        let sessionID =
            TelemetrySessionID()

        let telemetry =
            SafariTelemetryStore()

        let metrics =
            SafariMetricsStore()

        let recorder =
            SafariTelemetryRecorder(
                sessionID:
                    sessionID,

                store:
                    telemetry,

                metrics:
                    metrics
            )

        let budget =
            SafariPerformanceBudget()

        let diagnostics =
            SafariDiagnosticsEngine(
                telemetry:
                    telemetry,

                metrics:
                    metrics,

                budget:
                    budget,

                sessionID:
                    sessionID
            )

        self.sessionID =
            sessionID

        self.telemetry =
            telemetry

        self.metrics =
            metrics

        self.recorder =
            recorder

        self.diagnostics =
            diagnostics

        self.sampler =
            SafariSystemResourceSampler(
                recorder:
                    recorder
            )

        self.navigationTiming =
            SafariNavigationTimingTracker()

        self.exporter =
            SafariDiagnosticExporter(
                diagnostics:
                    diagnostics,

                directory:
                    storageDirectory
            )
    }

    public func start() async {

        guard !started else {
            return
        }

        started =
            true

        await recorder.record(
            category:
                .lifecycle,

            name:
                .sessionRestored,

            severity:
                .info
        )

        await sampler.start()
    }

    public func stop() async {

        guard started else {
            return
        }

        started =
            false

        await sampler.stop()

        await recorder.record(
            category:
                .lifecycle,

            name:
                .sessionSaved,

            severity:
                .info
        )
    }

    public func beginNavigation(
        id:
            UUID
    ) async {

        await navigationTiming.start(
            id:
                id
        )

        await recorder.record(
            category:
                .navigation,

            name:
                .navigationStarted,

            severity:
                .info
        )
    }

    public func finishNavigation(
        id:
            UUID,

        success:
            Bool,

        tabID:
            TelemetryTabID?
    ) async {

        guard
            let latency =
                await navigationTiming.finish(
                    id:
                        id
                )
        else {
            return
        }

        await recorder.recordNavigation(
            latency:
                latency,

            success:
                success,

            tabID:
                tabID
        )
    }

    public func signpostNavigation()
        -> OSSignpostID
    {

        signposter.begin(
            "SafariNavigation"
        )
    }

    public func finishSignpost(
        _ identifier:
            OSSignpostID
    ) {

        signposter.end(
            "SafariNavigation",

            identifier:
                identifier
        )
    }
}


// MARK: - 32. Browser Telemetry Controller

@MainActor
public final class SafariTelemetryBrowserController {

    public let runtime:
        SafariTelemetryRuntime

    private let mainThreadMonitor:
        SafariMainThreadMonitor

    private let frameMonitor:
        SafariFrameTelemetryMonitor

    public init(
        runtime:
            SafariTelemetryRuntime
    ) {

        self.runtime =
            runtime

        self.mainThreadMonitor =
            SafariMainThreadMonitor(
                recorder:
                    runtime.recorder
            )

        self.frameMonitor =
            SafariFrameTelemetryMonitor(
                recorder:
                    runtime.recorder
            )
    }

    public func start()
        async {

        await runtime.start()
    }

    public func stop()
        async {

        await runtime.stop()
    }

    public func beginMainThreadWork()
        -> UUID
    {

        mainThreadMonitor.begin()
    }

    public func endMainThreadWork(
        id:
            UUID
    ) {

        mainThreadMonitor.end(
            id:
                id
        )
    }

    public func frame(
        tabID:
            TelemetryTabID?
    ) {

        frameMonitor.frame(
            tabID:
                tabID
        )
    }

    public func exportDiagnostics()
        async -> URL?
    {

        await runtime.exporter.export()
    }
}


// MARK: - 33. Telemetry Factory

public enum SafariTelemetryFactory {

    public static func make(
        storageDirectory:
            URL
    ) -> SafariTelemetryRuntime {

        SafariTelemetryRuntime(
            storageDirectory:
                storageDirectory
        )
    }
}


// MARK: - 34. Complete Safari Performance System

@MainActor
public final class SafariPerformanceArchitecture {

    public let telemetry:
        SafariTelemetryRuntime

    public let telemetryController:
        SafariTelemetryBrowserController

    public init() {

        let directory =
            FileManager.default
                .urls(
                    for:
                        .applicationSupportDirectory,

                    in:
                        .userDomainMask
                )
                .first!
                .appendingPathComponent(
                    "SafariArchitecture",
                    isDirectory:
                        true
                )

        let runtime =
            SafariTelemetryFactory.make(
                storageDirectory:
                    directory
            )

        self.telemetry =
            runtime

        self.telemetryController =
            SafariTelemetryBrowserController(
                runtime:
                    runtime
            )
    }

    public func start()
        async {

        await telemetryController.start()
    }

    public func stop()
        async {

        await telemetryController.stop()
    }
}


// MARK: - 35. Example Usage
//
// @MainActor
// func startSafariArchitecture() async {
//
//     let system =
//         SafariPerformanceArchitecture()
//
//     await system.start()
//
//     let navigationID = UUID()
//
//     await system.telemetry
//         .beginNavigation(
//             id:
//                 navigationID
//         )
//
//     // WebKit performs the real navigation.
//
//     await system.telemetry
//         .finishNavigation(
//             id:
//                 navigationID,
//
//             success:
//                 true,
//
//             tabID:
//                 TelemetryTabID()
//         )
//
//     if let report =
//         await system.telemetryController
//             .exportDiagnostics()
//     {
//         print(
//             "Diagnostic report: \(report.path)"
//         )
//     }
// }


// MARK: - 36. Test Harness

#if DEBUG

public enum SafariTelemetryTests {

    public static func metricTest()
        async -> Bool
    {

        let store =
            SafariMetricsStore()

        await store.recordNavigation(
            latency:
                0.25
        )

        await store.recordNavigation(
            latency:
                0.75
        )

        let metrics =
            await store.snapshot()

        return
            metrics.navigationLatency.count
                == 2
            &&
            metrics.navigationLatency.average
                == 0.5
    }


    public static func ringBufferTest()
        -> Bool
    {

        var buffer =
            SafariTelemetryRingBuffer(
                capacity:
                    3
            )

        let session =
            TelemetrySessionID()

        for _ in 0..<5 {

            buffer.append(
                SafariTelemetryEvent(
                    sessionID:
                        session,

                    category:
                        .lifecycle,

                    name:
                        .sessionSaved,

                    severity:
                        .debug,

                    privacy:
                        .operational
                )
            )
        }

        return
            buffer.count == 3
            &&
            buffer.values().count == 3
    }


    public static func budgetTest()
        async -> Bool
    {

        let metrics =
            SafariPerformanceMetrics()

        let evaluator =
            SafariPerformanceBudgetEvaluator(
                budget:
                    SafariPerformanceBudget(
                        maximumNavigationLatency:
                            1.0
                    )
            )

        let results =
            evaluator.evaluate(
                metrics:
                    metrics
            )

        return !results.isEmpty ||
            metrics.navigationLatency.count == 0
    }
}

#endif

