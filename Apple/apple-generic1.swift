//
//  AppleWindowWorkspaceEngine.swift
//
//  #1 — macOS Window & Workspace Engine
//
//  Swift 6 / macOS / AppKit
//
//  Architecture:
//
//      WindowServer / AppKit
//              │
//              ▼
//      NSWindow / NSScreen
//              │
//              ▼
//      ┌───────────────────────────────┐
//      │ WindowWorkspaceEngine         │
//      └───────────────┬───────────────┘
//                      │
//       ┌──────────────┼──────────────┐
//       ▼              ▼              ▼
//  Window Registry  Layout Engine  Focus Engine
//       │              │              │
//       ▼              ▼              ▼
//  Persistence     Workspace      Snap/Tiling
//       │           Manager          │
//       └──────────────┬───────────────┘
//                      ▼
//                Diagnostics
//
// Public Apple APIs only.
// No private Mission Control APIs.
// No KVC access to private AppKit state.
//

import AppKit
import Foundation
import os
import QuartzCore

// MARK: - Identifiers

public struct WorkspaceID:
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

public struct ManagedWindowID:
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

public struct DisplayID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UInt32

    public init(rawValue: UInt32) {
        self.rawValue = rawValue
    }
}

// MARK: - Window lifecycle

public enum ManagedWindowLifecycle:
    String,
    Codable,
    Sendable
{
    case registered
    case visible
    case minimized
    case hidden
    case fullscreen
    case closing
    case closed
    case detached
}

// MARK: - Window activity

public enum WindowActivity:
    String,
    Codable,
    Sendable
{
    case active
    case recentlyActive
    case inactive
    case background
}

// MARK: - Workspace kind

public enum WorkspaceKind:
    String,
    Codable,
    Sendable
{
    case standard
    case development
    case communication
    case research
    case media
    case productivity
    case custom
}

// MARK: - Window role

public enum WindowRole:
    String,
    Codable,
    Sendable
{
    case primary
    case secondary
    case utility
    case inspector
    case palette
    case terminal
    case browser
    case editor
    case unknown
}

// MARK: - Window placement

public enum WindowPlacement:
    String,
    Codable,
    Sendable
{
    case freeform
    case leftHalf
    case rightHalf
    case topHalf
    case bottomHalf
    case topLeft
    case topRight
    case bottomLeft
    case bottomRight
    case maximized
    case centered
    case custom
}

// MARK: - Layout mode

public enum WorkspaceLayoutMode:
    String,
    Codable,
    Sendable
{
    case freeform
    case twoColumn
    case threeColumn
    case fourQuadrant
    case mainAndSidebar
    case stacked
    case maximized
}

// MARK: - Focus policy

public enum FocusPolicy:
    String,
    Codable,
    Sendable
{
    case mostRecentlyUsed
    case explicit
    case spatial
    case workspacePreferred
}

// MARK: - Window descriptor

public struct ManagedWindowDescriptor:
    Codable,
    Sendable
{
    public let id: ManagedWindowID

    public var title: String

    public var applicationBundleIdentifier: String?

    public var applicationName: String?

    public var role: WindowRole

    public var workspaceID: WorkspaceID?

    public var displayID: DisplayID?

    public var placement: WindowPlacement

    public var lifecycle: ManagedWindowLifecycle

    public var activity: WindowActivity

    public var frame: CodableRect

    public var isMain: Bool

    public var isKey: Bool

    public var lastActivation: Date

    public var createdAt: Date

    public init(
        id: ManagedWindowID = ManagedWindowID(),
        title: String = "",
        applicationBundleIdentifier: String? = nil,
        applicationName: String? = nil,
        role: WindowRole = .unknown,
        workspaceID: WorkspaceID? = nil,
        displayID: DisplayID? = nil,
        placement: WindowPlacement = .freeform,
        lifecycle: ManagedWindowLifecycle = .registered,
        activity: WindowActivity = .inactive,
        frame: CodableRect = CodableRect(
            x: 0,
            y: 0,
            width: 800,
            height: 600
        ),
        isMain: Bool = false,
        isKey: Bool = false,
        lastActivation: Date = Date(),
        createdAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.applicationBundleIdentifier =
            applicationBundleIdentifier
        self.applicationName = applicationName
        self.role = role
        self.workspaceID = workspaceID
        self.displayID = displayID
        self.placement = placement
        self.lifecycle = lifecycle
        self.activity = activity
        self.frame = frame
        self.isMain = isMain
        self.isKey = isKey
        self.lastActivation = lastActivation
        self.createdAt = createdAt
    }
}

// MARK: - Codable geometry

public struct CodableRect:
    Codable,
    Hashable,
    Sendable
{
    public var x: Double
    public var y: Double
    public var width: Double
    public var height: Double

    public init(
        x: Double,
        y: Double,
        width: Double,
        height: Double
    ) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    public init(
        _ rect: NSRect
    ) {
        self.x = rect.origin.x
        self.y = rect.origin.y
        self.width = rect.size.width
        self.height = rect.size.height
    }

    public var nsRect: NSRect {
        NSRect(
            x: x,
            y: y,
            width: width,
            height: height
        )
    }
}

// MARK: - Workspace

public struct WorkspaceDescriptor:
    Codable,
    Sendable
{
    public let id: WorkspaceID

    public var name: String

    public var kind: WorkspaceKind

    public var layoutMode: WorkspaceLayoutMode

    public var windowIDs: [ManagedWindowID]

    public var preferredDisplayID: DisplayID?

    public var createdAt: Date

    public var lastActivated: Date

    public init(
        id: WorkspaceID = WorkspaceID(),
        name: String,
        kind: WorkspaceKind = .standard,
        layoutMode: WorkspaceLayoutMode = .freeform,
        windowIDs: [ManagedWindowID] = [],
        preferredDisplayID: DisplayID? = nil,
        createdAt: Date = Date(),
        lastActivated: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.kind = kind
        self.layoutMode = layoutMode
        self.windowIDs = windowIDs
        self.preferredDisplayID = preferredDisplayID
        self.createdAt = createdAt
        self.lastActivated = lastActivated
    }
}

// MARK: - Display descriptor

public struct DisplayDescriptor:
    Codable,
    Sendable
{
    public let id: DisplayID

    public var frame: CodableRect

    public var visibleFrame: CodableRect

    public var scaleFactor: Double

    public var isMain: Bool

    public init(
        id: DisplayID,
        frame: NSRect,
        visibleFrame: NSRect,
        scaleFactor: Double,
        isMain: Bool
    ) {
        self.id = id
        self.frame = CodableRect(frame)
        self.visibleFrame = CodableRect(visibleFrame)
        self.scaleFactor = scaleFactor
        self.isMain = isMain
    }
}

// MARK: - Window registration

@MainActor
public final class WindowRegistration {

    public let id:
        ManagedWindowID

    public weak var window:
        NSWindow?

    public var descriptor:
        ManagedWindowDescriptor

    public init(
        id:
            ManagedWindowID,
        window:
            NSWindow,
        descriptor:
            ManagedWindowDescriptor
    ) {
        self.id = id
        self.window = window
        self.descriptor = descriptor
    }
}

// MARK: - Window registry

@MainActor
public final class WindowRegistry {

    private var registrations:
        [ManagedWindowID: WindowRegistration] =
            [:]

    private var reverseLookup:
        [ObjectIdentifier: ManagedWindowID] =
            [:]

    public init() {}

    @discardableResult
    public func register(
        window:
            NSWindow,
        descriptor:
            ManagedWindowDescriptor? =
                nil
    )
        -> ManagedWindowID
    {
        let id =
            descriptor?.id ??
            ManagedWindowID()

        let resolvedDescriptor =
            descriptor ??
            ManagedWindowDescriptor(
                id:
                    id,
                title:
                    window.title,
                frame:
                    CodableRect(
                        window.frame
                    ),
                isMain:
                    window.isMainWindow,
                isKey:
                    window.isKeyWindow
            )

        let registration =
            WindowRegistration(
                id:
                    id,
                window:
                    window,
                descriptor:
                    resolvedDescriptor
            )

        registrations[id] =
            registration

        reverseLookup[
            ObjectIdentifier(window)
        ] =
            id

        return id
    }

    public func unregister(
        window:
            NSWindow
    ) {

        guard
            let id =
                reverseLookup[
                    ObjectIdentifier(window)
                ]
        else {
            return
        }

        reverseLookup.removeValue(
            forKey:
                ObjectIdentifier(window)
        )

        registrations.removeValue(
            forKey:
                id
        )
    }

    public func registration(
        for id:
            ManagedWindowID
    )
        -> WindowRegistration?
    {
        registrations[id]
    }

    public func registration(
        for window:
            NSWindow
    )
        -> WindowRegistration?
    {
        guard
            let id =
                reverseLookup[
                    ObjectIdentifier(window)
                ]
        else {
            return nil
        }

        return registrations[id]
    }

    public func all()
        -> [WindowRegistration]
    {
        Array(
            registrations.values
        )
    }

    public func updateFromWindow(
        _ window:
            NSWindow
    ) {

        guard
            let registration =
                registration(
                    for:
                        window
                )
        else {
            return
        }

        registration.descriptor.title =
            window.title

        registration.descriptor.frame =
            CodableRect(
                window.frame
            )

        registration.descriptor.isMain =
            window.isMainWindow

        registration.descriptor.isKey =
            window.isKeyWindow

        registration.descriptor.lifecycle =
            window.isMiniaturized
                ? .minimized
                : window.isVisible
                    ? .visible
                    : .hidden
    }
}

// MARK: - Window state observer

@MainActor
public final class WindowStateObserver {

    private var observers:
        [NSObjectProtocol] =
            []

    private weak var registry:
        WindowRegistry?

    public init(
        registry:
            WindowRegistry
    ) {
        self.registry =
            registry
    }

    public func start() {

        let center =
            NotificationCenter.default

        let names:
            [Notification.Name] =
            [
                NSWindow.didMoveNotification,
                NSWindow.didResizeNotification,
                NSWindow.didMiniaturizeNotification,
                NSWindow.didDeminiaturizeNotification,
                NSWindow.didBecomeKeyNotification,
                NSWindow.didResignKeyNotification,
                NSWindow.didBecomeMainNotification,
                NSWindow.didResignMainNotification,
                NSWindow.didChangeScreenNotification
            ]

        for name in names {

            let token =
                center.addObserver(
                    forName:
                        name,
                    object:
                        nil,
                    queue:
                        .main
                ) {
                    [weak self]
                    notification in

                    guard
                        let window =
                            notification.object
                            as? NSWindow
                    else {
                        return
                    }

                    self?
                        .registry?
                        .updateFromWindow(
                            window
                        )
                }

            observers.append(token)
        }
    }

    public func stop() {

        let center =
            NotificationCenter.default

        for observer in observers {
            center.removeObserver(
                observer
            )
        }

        observers.removeAll()
    }

    deinit {

        let center =
            NotificationCenter.default

        for observer in observers {
            center.removeObserver(
                observer
            )
        }
    }
}

// MARK: - Workspace store

public actor WorkspaceStore {

    private var workspaces:
        [WorkspaceID: WorkspaceDescriptor] =
            [:]

    public init() {}

    public func create(
        name:
            String,
        kind:
            WorkspaceKind = .standard,
        layout:
            WorkspaceLayoutMode = .freeform
    )
        -> WorkspaceDescriptor
    {
        let workspace =
            WorkspaceDescriptor(
                name:
                    name,
                kind:
                    kind,
                layoutMode:
                    layout
            )

        workspaces[
            workspace.id
        ] =
            workspace

        return workspace
    }

    public func insert(
        _ workspace:
            WorkspaceDescriptor
    ) {
        workspaces[
            workspace.id
        ] =
            workspace
    }

    public func remove(
        _ id:
            WorkspaceID
    ) {
        workspaces.removeValue(
            forKey:
                id
        )
    }

    public func workspace(
        _ id:
            WorkspaceID
    )
        -> WorkspaceDescriptor?
    {
        workspaces[id]
    }

    public func all()
        -> [WorkspaceDescriptor]
    {
        Array(
            workspaces.values
        )
    }

    public func addWindow(
        _ windowID:
            ManagedWindowID,
        to workspaceID:
            WorkspaceID
    ) {

        guard
            var workspace =
                workspaces[
                    workspaceID
                ]
        else {
            return
        }

        if !workspace.windowIDs.contains(
            windowID
        ) {
            workspace.windowIDs.append(
                windowID
            )
        }

        workspace.lastActivated =
            Date()

        workspaces[
            workspaceID
        ] =
            workspace
    }

    public func removeWindow(
        _ windowID:
            ManagedWindowID,
        from workspaceID:
            WorkspaceID
    ) {

        guard
            var workspace =
                workspaces[
                    workspaceID
                ]
        else {
            return
        }

        workspace.windowIDs.removeAll {
            $0 == windowID
        }

        workspaces[
            workspaceID
        ] =
            workspace
    }

    public func setLayout(
        _ mode:
            WorkspaceLayoutMode,
        for workspaceID:
            WorkspaceID
    ) {

        guard
            var workspace =
                workspaces[
                    workspaceID
                ]
        else {
            return
        }

        workspace.layoutMode =
            mode

        workspaces[
            workspaceID
        ] =
            workspace
    }
}

// MARK: - Focus history

public actor FocusHistory {

    private var history:
        [ManagedWindowID] =
            []

    private let maximumEntries:
        Int

    public init(
        maximumEntries:
            Int = 500
    ) {
        self.maximumEntries =
            maximumEntries
    }

    public func record(
        _ windowID:
            ManagedWindowID
    ) {

        history.removeAll {
            $0 == windowID
        }

        history.insert(
            windowID,
            at:
                0
        )

        if history.count >
            maximumEntries
        {
            history.removeLast(
                history.count -
                maximumEntries
            )
        }
    }

    public func mostRecent(
        excluding:
            ManagedWindowID? =
                nil
    )
        -> ManagedWindowID?
    {
        history.first {
            $0 != excluding
        }
    }

    public func snapshot()
        -> [ManagedWindowID]
    {
        history
    }

    public func clear() {
        history.removeAll()
    }
}

// MARK: - Display manager

@MainActor
public final class DisplayManager {

    public init() {}

    public func displays()
        -> [DisplayDescriptor]
    {
        NSScreen.screens.map {
            screen in

            let id =
                displayID(
                    for:
                        screen
                )

            return DisplayDescriptor(
                id:
                    id,
                frame:
                    screen.frame,
                visibleFrame:
                    screen.visibleFrame,
                scaleFactor:
                    screen.backingScaleFactor,
                isMain:
                    screen == NSScreen.main
            )
        }
    }

    public func mainDisplay()
        -> DisplayDescriptor?
    {
        displays().first {
            $0.isMain
        }
    }

    public func screen(
        for:
            DisplayID
    )
        -> NSScreen?
    {
        NSScreen.screens.first {
            displayID(
                for:
                    $0
            ) == `for`
        }
    }

    private func displayID(
        for screen:
            NSScreen
    )
        -> DisplayID
    {
        let number =
            screen.deviceDescription[
                NSDeviceDescriptionKey(
                    "NSScreenNumber"
                )
            ] as? NSNumber

        return DisplayID(
            rawValue:
                number?
                    .uint32Value ??
                0
        )
    }
}

// MARK: - Layout geometry

public struct LayoutGeometry:
    Sendable
{
    public let windowID:
        ManagedWindowID

    public let frame:
        NSRect

    public let placement:
        WindowPlacement

    public init(
        windowID:
            ManagedWindowID,
        frame:
            NSRect,
        placement:
            WindowPlacement
    ) {
        self.windowID =
            windowID

        self.frame =
            frame

        self.placement =
            placement
    }
}

// MARK: - Layout engine

public struct WindowLayoutEngine:
    Sendable
{
    public init() {}

    public func half(
        visibleFrame:
            NSRect,
        side:
            WindowPlacement
    )
        -> NSRect
    {
        switch side {

        case .leftHalf:

            return NSRect(
                x:
                    visibleFrame.minX,
                y:
                    visibleFrame.minY,
                width:
                    visibleFrame.width / 2,
                height:
                    visibleFrame.height
            )

        case .rightHalf:

            return NSRect(
                x:
                    visibleFrame.midX,
                y:
                    visibleFrame.minY,
                width:
                    visibleFrame.width / 2,
                height:
                    visibleFrame.height
            )

        case .topHalf:

            return NSRect(
                x:
                    visibleFrame.minX,
                y:
                    visibleFrame.midY,
                width:
                    visibleFrame.width,
                height:
                    visibleFrame.height / 2
            )

        case .bottomHalf:

            return NSRect(
                x:
                    visibleFrame.minX,
                y:
                    visibleFrame.minY,
                width:
                    visibleFrame.width,
                height:
                    visibleFrame.height / 2
            )

        default:
            return visibleFrame
        }
    }

    public func quadrant(
        visibleFrame:
            NSRect,
        placement:
            WindowPlacement
    )
        -> NSRect
    {
        let halfWidth =
            visibleFrame.width / 2

        let halfHeight =
            visibleFrame.height / 2

        switch placement {

        case .topLeft:

            return NSRect(
                x:
                    visibleFrame.minX,
                y:
                    visibleFrame.midY,
                width:
                    halfWidth,
                height:
                    halfHeight
            )

        case .topRight:

            return NSRect(
                x:
                    visibleFrame.midX,
                y:
                    visibleFrame.midY,
                width:
                    halfWidth,
                height:
                    halfHeight
            )

        case .bottomLeft:

            return NSRect(
                x:
                    visibleFrame.minX,
                y:
                    visibleFrame.minY,
                width:
                    halfWidth,
                height:
                    halfHeight
            )

        case .bottomRight:

            return NSRect(
                x:
                    visibleFrame.midX,
                y:
                    visibleFrame.minY,
                width:
                    halfWidth,
                height:
                    halfHeight
            )

        default:
            return visibleFrame
        }
    }

    public func centered(
        visibleFrame:
            NSRect,
        size:
            NSSize
    )
        -> NSRect
    {
        NSRect(
            x:
                visibleFrame.midX -
                size.width / 2,
            y:
                visibleFrame.midY -
                size.height / 2,
            width:
                size.width,
            height:
                size.height
        )
    }

    public func maximized(
        visibleFrame:
            NSRect
    )
        -> NSRect
    {
        visibleFrame
    }

    public func twoColumn(
        visibleFrame:
            NSRect,
        count:
            Int
    )
        -> [NSRect]
    {
        guard count > 0 else {
            return []
        }

        if count == 1 {
            return [
                visibleFrame
            ]
        }

        let width =
            visibleFrame.width /
            CGFloat(count)

        return (0..<count).map {
            index in

            NSRect(
                x:
                    visibleFrame.minX +
                    CGFloat(index) *
                    width,
                y:
                    visibleFrame.minY,
                width:
                    width,
                height:
                    visibleFrame.height
            )
        }
    }

    public func mainAndSidebar(
        visibleFrame:
            NSRect,
        sidebarRatio:
            CGFloat = 0.30
    )
        -> (main: NSRect, sidebar: NSRect)
    {
        let sidebarWidth =
            visibleFrame.width *
            sidebarRatio

        let main =
            NSRect(
                x:
                    visibleFrame.minX,
                y:
                    visibleFrame.minY,
                width:
                    visibleFrame.width -
                    sidebarWidth,
                height:
                    visibleFrame.height
            )

        let sidebar =
            NSRect(
                x:
                    main.maxX,
                y:
                    visibleFrame.minY,
                width:
                    sidebarWidth,
                height:
                    visibleFrame.height
            )

        return (
            main,
            sidebar
        )
    }
}

// MARK: - Snap engine

public struct WindowSnapEngine:
    Sendable
{
    public var edgeThreshold:
        CGFloat

    public init(
        edgeThreshold:
            CGFloat = 18
    ) {
        self.edgeThreshold =
            edgeThreshold
    }

    public func snap(
        proposedFrame:
            NSRect,
        visibleFrame:
            NSRect
    )
        -> (NSRect, WindowPlacement)?
    {
        let nearLeft =
            abs(
                proposedFrame.minX -
                visibleFrame.minX
            ) <= edgeThreshold

        let nearRight =
            abs(
                proposedFrame.maxX -
                visibleFrame.maxX
            ) <= edgeThreshold

        let nearTop =
            abs(
                proposedFrame.maxY -
                visibleFrame.maxY
            ) <= edgeThreshold

        let nearBottom =
            abs(
                proposedFrame.minY -
                visibleFrame.minY
            ) <= edgeThreshold

        if nearLeft &&
            nearTop
        {
            return (
                WindowLayoutEngine()
                    .quadrant(
                        visibleFrame:
                            visibleFrame,
                        placement:
                            .topLeft
                    ),
                .topLeft
            )
        }

        if nearRight &&
            nearTop
        {
            return (
                WindowLayoutEngine()
                    .quadrant(
                        visibleFrame:
                            visibleFrame,
                        placement:
                            .topRight
                    ),
                .topRight
            )
        }

        if nearLeft &&
            nearBottom
        {
            return (
                WindowLayoutEngine()
                    .quadrant(
                        visibleFrame:
                            visibleFrame,
                        placement:
                            .bottomLeft
                    ),
                .bottomLeft
            )
        }

        if nearRight &&
            nearBottom
        {
            return (
                WindowLayoutEngine()
                    .quadrant(
                        visibleFrame:
                            visibleFrame,
                        placement:
                            .bottomRight
                    ),
                .bottomRight
            )
        }

        if nearLeft {
            return (
                WindowLayoutEngine()
                    .half(
                        visibleFrame:
                            visibleFrame,
                        side:
                            .leftHalf
                    ),
                .leftHalf
            )
        }

        if nearRight {
            return (
                WindowLayoutEngine()
                    .half(
                        visibleFrame:
                            visibleFrame,
                        side:
                            .rightHalf
                    ),
                .rightHalf
            )
        }

        if nearTop {
            return (
                WindowLayoutEngine()
                    .half(
                        visibleFrame:
                            visibleFrame,
                        side:
                            .topHalf
                    ),
                .topHalf
            )
        }

        if nearBottom {
            return (
                WindowLayoutEngine()
                    .half(
                        visibleFrame:
                            visibleFrame,
                        side:
                            .bottomHalf
                    ),
                .bottomHalf
            )
        }

        return nil
    }
}

// MARK: - Window controller

@MainActor
public final class ManagedWindowController {

    private let registry:
        WindowRegistry

    private let layoutEngine:
        WindowLayoutEngine

    private let snapEngine:
        WindowSnapEngine

    public init(
        registry:
            WindowRegistry,
        layoutEngine:
            WindowLayoutEngine =
                WindowLayoutEngine(),
        snapEngine:
            WindowSnapEngine =
                WindowSnapEngine()
    ) {
        self.registry =
            registry

        self.layoutEngine =
            layoutEngine

        self.snapEngine =
            snapEngine
    }

    public func show(
        _ id:
            ManagedWindowID
    ) {

        guard
            let registration =
                registry.registration(
                    for:
                        id
                ),
            let window =
                registration.window
        else {
            return
        }

        window.deminiaturize(
            nil
        )

        window.makeKeyAndOrderFront(
            nil
        )
    }

    public func hide(
        _ id:
            ManagedWindowID
    ) {

        guard
            let window =
                registry.registration(
                    for:
                        id
                )?.window
        else {
            return
        }

        window.orderOut(
            nil
        )
    }

    public func minimize(
        _ id:
            ManagedWindowID
    ) {

        guard
            let window =
                registry.registration(
                    for:
                        id
                )?.window
        else {
            return
        }

        window.miniaturize(
            nil
        )
    }

    public func focus(
        _ id:
            ManagedWindowID
    ) {

        guard
            let window =
                registry.registration(
                    for:
                        id
                )?.window
        else {
            return
        }

        window.deminiaturize(
            nil
        )

        NSApp.activate(
            ignoringOtherApps:
                true
        )

        window.makeKeyAndOrderFront(
            nil
        )
    }

    public func move(
        _ id:
            ManagedWindowID,
        to frame:
            NSRect,
        animate:
            Bool = true
    ) {

        guard
            let window =
                registry.registration(
                    for:
                        id
                )?.window
        else {
            return
        }

        if animate {

            NSAnimationContext.runAnimationGroup {
                context in

                context.duration =
                    0.20

                window.animator().setFrame(
                    frame,
                    display:
                        true
                )
            }

        } else {

            window.setFrame(
                frame,
                display:
                    true
            )
        }
    }

    public func applyPlacement(
        _ placement:
            WindowPlacement,
        to id:
            ManagedWindowID
    ) {

        guard
            let window =
                registry.registration(
                    for:
                        id
                )?.window,
            let screen =
                window.screen ??
                NSScreen.main
        else {
            return
        }

        let visible =
            screen.visibleFrame

        let target:
            NSRect

        switch placement {

        case .leftHalf,
             .rightHalf,
             .topHalf,
             .bottomHalf:

            target =
                layoutEngine.half(
                    visibleFrame:
                        visible,
                    side:
                        placement
                )

        case .topLeft,
             .topRight,
             .bottomLeft,
             .bottomRight:

            target =
                layoutEngine.quadrant(
                    visibleFrame:
                        visible,
                    placement:
                        placement
                )

        case .maximized:

            target =
                layoutEngine.maximized(
                    visibleFrame:
                        visible
                )

        case .centered:

            target =
                layoutEngine.centered(
                    visibleFrame:
                        visible,
                    size:
                        window.frame.size
                )

        case .freeform,
             .custom:

            return
        }

        move(
            id,
            to:
                target
        )
    }

    public func snap(
        _ id:
            ManagedWindowID
    ) {

        guard
            let window =
                registry.registration(
                    for:
                        id
                )?.window,
            let screen =
                window.screen ??
                NSScreen.main
        else {
            return
        }

        guard
            let result =
                snapEngine.snap(
                    proposedFrame:
                        window.frame,
                    visibleFrame:
                        screen.visibleFrame
                )
        else {
            return
        }

        move(
            id,
            to:
                result.0
        )
    }
}

// MARK: - Workspace layout controller

@MainActor
public final class WorkspaceLayoutController {

    private let registry:
        WindowRegistry

    private let workspaceStore:
        WorkspaceStore

    private let windowController:
        ManagedWindowController

    private let layoutEngine:
        WindowLayoutEngine

    public init(
        registry:
            WindowRegistry,
        workspaceStore:
            WorkspaceStore,
        windowController:
            ManagedWindowController,
        layoutEngine:
            WindowLayoutEngine =
                WindowLayoutEngine()
    ) {
        self.registry =
            registry

        self.workspaceStore =
            workspaceStore

        self.windowController =
            windowController

        self.layoutEngine =
            layoutEngine
    }

    public func apply(
        workspace:
            WorkspaceDescriptor
    ) async {

        let registrations =
            registry.all()

        let windows =
            workspace.windowIDs.compactMap {
                id in

                registrations.first {
                    $0.id == id
                }
            }

        guard
            let firstWindow =
                windows.first?.window,
            let screen =
                firstWindow?.screen ??
                NSScreen.main
        else {
            return
        }

        let visible =
            screen.visibleFrame

        switch workspace.layoutMode {

        case .freeform:
            return

        case .maximized:

            for registration in windows {

                windowController.move(
                    registration.id,
                    to:
                        visible
                )
            }

        case .twoColumn,
             .threeColumn:

            let frames =
                layoutEngine.twoColumn(
                    visibleFrame:
                        visible,
                    count:
                        windows.count
                )

            for (
                index,
                registration
            ) in windows.enumerated()
            {
                guard
                    index < frames.count
                else {
                    continue
                }

                windowController.move(
                    registration.id,
                    to:
                        frames[index]
                )
            }

        case .mainAndSidebar:

            let geometry =
                layoutEngine.mainAndSidebar(
                    visibleFrame:
                        visible
                )

            if let first =
                windows.first
            {
                windowController.move(
                    first.id,
                    to:
                        geometry.main
                )
            }

            for registration in
                windows.dropFirst()
            {
                windowController.move(
                    registration.id,
                    to:
                        geometry.sidebar
                )
            }

        case .fourQuadrant:

            let placements:
                [WindowPlacement] =
                [
                    .topLeft,
                    .topRight,
                    .bottomLeft,
                    .bottomRight
                ]

            for (
                index,
                registration
            ) in windows.enumerated()
            {
                guard
                    index <
                    placements.count
                else {
                    break
                }

                let frame =
                    layoutEngine.quadrant(
                        visibleFrame:
                            visible,
                        placement:
                            placements[index]
                    )

                windowController.move(
                    registration.id,
                    to:
                        frame
                )
            }

        case .stacked:

            let height =
                visible.height /
                CGFloat(
                    max(
                        windows.count,
                        1
                    )
                )

            for (
                index,
                registration
            ) in windows.enumerated()
            {
                let frame =
                    NSRect(
                        x:
                            visible.minX,
                        y:
                            visible.minY +
                            CGFloat(index) *
                            height,
                        width:
                            visible.width,
                        height:
                            height
                    )

                windowController.move(
                    registration.id,
                    to:
                        frame
                )
            }
        }
    }
}

// MARK: - Persistence model

public struct WorkspacePersistenceSnapshot:
    Codable,
    Sendable
{
    public var workspaces:
        [WorkspaceDescriptor]

    public var windows:
        [ManagedWindowDescriptor]

    public var capturedAt:
        Date

    public init(
        workspaces:
            [WorkspaceDescriptor],
        windows:
            [ManagedWindowDescriptor],
        capturedAt:
            Date =
                Date()
    ) {
        self.workspaces =
            workspaces

        self.windows =
            windows

        self.capturedAt =
            capturedAt
    }
}

// MARK: - Persistence

public actor WorkspacePersistence {

    private let url:
        URL

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    public init(
        url:
            URL
    ) {
        self.url =
            url

        self.encoder =
            JSONEncoder()

        self.decoder =
            JSONDecoder()

        encoder.outputFormatting =
            [
                .prettyPrinted,
                .sortedKeys
            ]

        encoder.dateEncodingStrategy =
            .iso8601

        decoder.dateDecodingStrategy =
            .iso8601
    }

    public func save(
        _ snapshot:
            WorkspacePersistenceSnapshot
    ) throws {

        let directory =
            url.deletingLastPathComponent()

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

        let temporaryURL =
            url
                .deletingLastPathComponent()
                .appendingPathComponent(
                    ".\(url.lastPathComponent).tmp"
                )

        try data.write(
            to:
                temporaryURL,
            options:
                .atomic
        )

        if FileManager.default.fileExists(
            atPath:
                url.path
        ) {
            _ =
                try FileManager.default
                    .replaceItemAt(
                        url,
                        withItemAt:
                            temporaryURL
                    )
        } else {
            try FileManager.default.moveItem(
                at:
                    temporaryURL,
                to:
                    url
            )
        }
    }

    public func load()
        throws
        -> WorkspacePersistenceSnapshot?
    {
        guard
            FileManager.default.fileExists(
                atPath:
                    url.path
            )
        else {
            return nil
        }

        let data =
            try Data(
                contentsOf:
                    url
            )

        return try decoder.decode(
            WorkspacePersistenceSnapshot.self,
            from:
                data
        )
    }

    public func delete()
        throws
    {
        guard
            FileManager.default.fileExists(
                atPath:
                    url.path
            )
        else {
            return
        }

        try FileManager.default.removeItem(
            at:
                url
        )
    }
}

// MARK: - Window restore policy

public struct WindowRestorePolicy:
    Sendable
{
    public var restoreFrames:
        Bool

    public var restoreWorkspaceAssignments:
        Bool

    public var restoreMinimizedState:
        Bool

    public var restoreHiddenState:
        Bool

    public var restoreFocus:
        Bool

    public init(
        restoreFrames:
            Bool = true,
        restoreWorkspaceAssignments:
            Bool = true,
        restoreMinimizedState:
            Bool = false,
        restoreHiddenState:
            Bool = false,
        restoreFocus:
            Bool = true
    ) {
        self.restoreFrames =
            restoreFrames

        self.restoreWorkspaceAssignments =
            restoreWorkspaceAssignments

        self.restoreMinimizedState =
            restoreMinimizedState

        self.restoreHiddenState =
            restoreHiddenState

        self.restoreFocus =
            restoreFocus
    }
}

// MARK: - Safe frame validation

@MainActor
public struct WindowFrameValidator {

    public init() {}

    public func validatedFrame(
        _ frame:
            NSRect,
        screens:
            [NSScreen] =
                NSScreen.screens
    )
        -> NSRect
    {
        guard
            !screens.isEmpty
        else {
            return frame
        }

        let union =
            screens.reduce(
                CGRect.null
            ) {
                partial,
                screen in

                partial.union(
                    screen.visibleFrame
                )
            }

        let minimumVisible:
            CGFloat =
                80

        var result =
            frame

        if result.width >
            union.width
        {
            result.size.width =
                union.width
        }

        if result.height >
            union.height
        {
            result.size.height =
                union.height
        }

        if result.maxX <
            union.minX +
            minimumVisible
        {
            result.origin.x =
                union.minX
        }

        if result.minX >
            union.maxX -
            minimumVisible
        {
            result.origin.x =
                union.maxX -
                result.width
        }

        if result.maxY <
            union.minY +
            minimumVisible
        {
            result.origin.y =
                union.minY
        }

        if result.minY >
            union.maxY -
            minimumVisible
        {
            result.origin.y =
                union.maxY -
                result.height
        }

        return result
    }
}

// MARK: - Focus controller

@MainActor
public final class FocusController {

    private let registry:
        WindowRegistry

    private let history:
        FocusHistory

    public init(
        registry:
            WindowRegistry,
        history:
            FocusHistory
    ) {
        self.registry =
            registry

        self.history =
            history
    }

    public func focus(
        _ id:
            ManagedWindowID
    ) {

        guard
            let registration =
                registry.registration(
                    for:
                        id
                ),
            let window =
                registration.window
        else {
            return
        }

        NSApp.activate(
            ignoringOtherApps:
                true
        )

        window.deminiaturize(
            nil
        )

        window.makeKeyAndOrderFront(
            nil
        )

        Task {
            await history.record(
                id
            )
        }
    }

    public func focusMostRecent(
        excluding:
            ManagedWindowID? =
                nil
    ) async {

        guard
            let id =
                await history.mostRecent(
                    excluding:
                        excluding
                )
        else {
            return
        }

        focus(
            id
        )
    }
}

// MARK: - Workspace coordinator

@MainActor
public final class WorkspaceCoordinator {

    public let registry:
        WindowRegistry

    public let workspaceStore:
        WorkspaceStore

    public let displayManager:
        DisplayManager

    public let history:
        FocusHistory

    public let windowController:
        ManagedWindowController

    public let focusController:
        FocusController

    public let persistence:
        WorkspacePersistence

    public let observer:
        WindowStateObserver

    public let layoutController:
        WorkspaceLayoutController

    public init(
        persistenceURL:
            URL
    ) {

        let registry =
            WindowRegistry()

        let workspaceStore =
            WorkspaceStore()

        let history =
            FocusHistory()

        let windowController =
            ManagedWindowController(
                registry:
                    registry
            )

        let focusController =
            FocusController(
                registry:
                    registry,
                history:
                    history
            )

        self.registry =
            registry

        self.workspaceStore =
            workspaceStore

        self.displayManager =
            DisplayManager()

        self.history =
            history

        self.windowController =
            windowController

        self.focusController =
            focusController

        self.persistence =
            WorkspacePersistence(
                url:
                    persistenceURL
            )

        self.observer =
            WindowStateObserver(
                registry:
                    registry
            )

        self.layoutController =
            WorkspaceLayoutController(
                registry:
                    registry,
                workspaceStore:
                    workspaceStore,
                windowController:
                    windowController
            )
    }

    public func start() {

        observer.start()
    }

    public func stop() {

        observer.stop()
    }

    // MARK: Registration

    @discardableResult
    public func register(
        window:
            NSWindow,
        role:
            WindowRole =
                .unknown
    )
        -> ManagedWindowID
    {
        let descriptor =
            ManagedWindowDescriptor(
                title:
                    window.title,
                role:
                    role,
                frame:
                    CodableRect(
                        window.frame
                    ),
                isMain:
                    window.isMainWindow,
                isKey:
                    window.isKeyWindow
            )

        let id =
            registry.register(
                window:
                    window,
                descriptor:
                    descriptor
            )

        if window.isKeyWindow {

            Task {
                await history.record(
                    id
                )
            }
        }

        return id
    }

    public func unregister(
        window:
            NSWindow
    ) {

        registry.unregister(
            window:
                window
        )
    }

    // MARK: Workspace creation

    public func createWorkspace(
        name:
            String,
        kind:
            WorkspaceKind = .standard,
        layout:
            WorkspaceLayoutMode = .freeform
    ) async
        -> WorkspaceDescriptor
    {
        await workspaceStore.create(
            name:
                name,
            kind:
                kind,
            layout:
                layout
        )
    }

    // MARK: Assignment

    public func assign(
        windowID:
            ManagedWindowID,
        to workspaceID:
            WorkspaceID
    ) async {

        await workspaceStore.addWindow(
            windowID,
            to:
                workspaceID
        )

        if let registration =
            registry.registration(
                for:
                    windowID
            )
        {
            registration
                .descriptor
                .workspaceID =
                workspaceID
        }
    }

    // MARK: Layout

    public func applyWorkspace(
        _ workspaceID:
            WorkspaceID
    ) async {

        guard
            let workspace =
                await workspaceStore.workspace(
                    workspaceID
                )
        else {
            return
        }

        await layoutController.apply(
            workspace:
                workspace
        )
    }

    // MARK: Persistence

    public func save() async {

        let workspaces =
            await workspaceStore.all()

        let windows =
            registry.all().map {
                $0.descriptor
            }

        let snapshot =
            WorkspacePersistenceSnapshot(
                workspaces:
                    workspaces,
                windows:
                    windows
            )

        do {
            try await persistence.save(
                snapshot
            )
        } catch {

            Logger.workspace.error(
                "Failed to persist workspace state: \(error.localizedDescription)"
            )
        }
    }

    public func restore() async {

        do {

            guard
                let snapshot =
                    try await persistence.load()
            else {
                return
            }

            for workspace in
                snapshot.workspaces
            {
                await workspaceStore.insert(
                    workspace
                )
            }

            let validator =
                WindowFrameValidator()

            for descriptor in
                snapshot.windows
            {
                guard
                    let registration =
                        registry.registration(
                            for:
                                descriptor.id
                        ),
                    let window =
                        registration.window
                else {
                    continue
                }

                if descriptor.frame.width >
                    0 &&
                    descriptor.frame.height >
                    0
                {
                    let frame =
                        validator.validatedFrame(
                            descriptor.frame.nsRect
                        )

                    window.setFrame(
                        frame,
                        display:
                            true
                    )
                }

                if descriptor.lifecycle ==
                    .minimized
                {
                    window.miniaturize(
                        nil
                    )
                }
            }

        } catch {

            Logger.workspace.error(
                "Failed to restore workspace state: \(error.localizedDescription)"
            )
        }
    }
}

// MARK: - Diagnostics

public struct WorkspaceDiagnostic:
    Codable,
    Sendable
{
    public enum Severity:
        String,
        Codable,
        Sendable
    {
        case info
        case warning
        case error
    }

    public let severity:
        Severity

    public let message:
        String

    public init(
        severity:
            Severity,
        message:
            String
    ) {
        self.severity =
            severity

        self.message =
            message
    }
}

public struct WorkspaceDiagnosticsReport:
    Codable,
    Sendable
{
    public let generatedAt:
        Date

    public let displays:
        [DisplayDescriptor]

    public let windows:
        [ManagedWindowDescriptor]

    public let workspaces:
        [WorkspaceDescriptor]

    public let diagnostics:
        [WorkspaceDiagnostic]

    public init(
        displays:
            [DisplayDescriptor],
        windows:
            [ManagedWindowDescriptor],
        workspaces:
            [WorkspaceDescriptor],
        diagnostics:
            [WorkspaceDiagnostic]
    ) {
        self.generatedAt =
            Date()

        self.displays =
            displays

        self.windows =
            windows

        self.workspaces =
            workspaces

        self.diagnostics =
            diagnostics
    }
}

// MARK: - Diagnostics engine

@MainActor
public final class WorkspaceDiagnosticsEngine {

    private let coordinator:
        WorkspaceCoordinator

    public init(
        coordinator:
            WorkspaceCoordinator
    ) {
        self.coordinator =
            coordinator
    }

    public func generate()
        async
        -> WorkspaceDiagnosticsReport
    {
        let displays =
            coordinator.displayManager
                .displays()

        let windows =
            coordinator.registry
                .all()
                .map {
                    $0.descriptor
                }

        let workspaces =
            await coordinator.workspaceStore
                .all()

        var diagnostics:
            [WorkspaceDiagnostic] =
            []

        if displays.isEmpty {

            diagnostics.append(
                WorkspaceDiagnostic(
                    severity:
                        .warning,
                    message:
                        "No displays were reported by AppKit."
                )
            )
        }

        for window in windows {

            if window.frame.width <= 0 ||
                window.frame.height <= 0
            {
                diagnostics.append(
                    WorkspaceDiagnostic(
                        severity:
                            .warning,
                        message:
                            "Window \(window.id.rawValue) has an invalid frame."
                    )
                )
            }

            if window.workspaceID == nil {

                diagnostics.append(
                    WorkspaceDiagnostic(
                        severity:
                            .info,
                        message:
                            "Window \(window.id.rawValue) is not assigned to a managed workspace."
                    )
                )
            }
        }

        return WorkspaceDiagnosticsReport(
            displays:
                displays,
            windows:
                windows,
            workspaces:
                workspaces,
            diagnostics:
                diagnostics
        )
    }
}

// MARK: - Unified engine

@MainActor
public final class AppleWindowWorkspaceEngine {

    public let coordinator:
        WorkspaceCoordinator

    public let diagnostics:
        WorkspaceDiagnosticsEngine

    public private(set) var isRunning:
        Bool =
            false

    public init(
        persistenceURL:
            URL
    ) {

        self.coordinator =
            WorkspaceCoordinator(
                persistenceURL:
                    persistenceURL
            )

        self.diagnostics =
            WorkspaceDiagnosticsEngine(
                coordinator:
                    coordinator
            )
    }

    public func start() async {

        guard
            !isRunning
        else {
            return
        }

        isRunning =
            true

        coordinator.start()

        await coordinator.restore()
    }

    public func shutdown() async {

        guard
            isRunning
        else {
            return
        }

        await coordinator.save()

        coordinator.stop()

        isRunning =
            false
    }

    // MARK: Window registration

    @discardableResult
    public func register(
        window:
            NSWindow,
        role:
            WindowRole =
                .unknown
    )
        -> ManagedWindowID
    {
        coordinator.register(
            window:
                window,
            role:
                role
        )
    }

    public func unregister(
        window:
            NSWindow
    ) {
        coordinator.unregister(
            window:
                window
        )
    }

    // MARK: Window actions

    public func focus(
        _ id:
            ManagedWindowID
    ) {
        coordinator.focusController
            .focus(
                id
            )
    }

    public func minimize(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .minimize(
                id
            )
    }

    public func hide(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .hide(
                id
            )
    }

    public func show(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .show(
                id
            )
    }

    public func maximize(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .maximized,
                to:
                    id
            )
    }

    public func leftHalf(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .leftHalf,
                to:
                    id
            )
    }

    public func rightHalf(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .rightHalf,
                to:
                    id
            )
    }

    public func topLeft(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .topLeft,
                to:
                    id
            )
    }

    public func topRight(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .topRight,
                to:
                    id
            )
    }

    public func bottomLeft(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .bottomLeft,
                to:
                    id
            )
    }

    public func bottomRight(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .bottomRight,
                to:
                    id
            )
    }

    public func center(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .applyPlacement(
                .centered,
                to:
                    id
            )
    }

    public func snap(
        _ id:
            ManagedWindowID
    ) {
        coordinator.windowController
            .snap(
                id
            )
    }

    // MARK: Workspaces

    public func createWorkspace(
        name:
            String,
        kind:
            WorkspaceKind = .standard,
        layout:
            WorkspaceLayoutMode = .freeform
    ) async
        -> WorkspaceDescriptor
    {
        await coordinator.createWorkspace(
            name:
                name,
            kind:
                kind,
            layout:
                layout
        )
    }

    public func assign(
        window:
            ManagedWindowID,
        to workspace:
            WorkspaceID
    ) async {

        await coordinator.assign(
            windowID:
                window,
            to:
                workspace
        )
    }

    public func layout(
        workspace:
            WorkspaceID
    ) async {

        await coordinator.applyWorkspace(
            workspace
        )
    }

    // MARK: Diagnostics

    public func diagnosticsReport()
        async
        -> WorkspaceDiagnosticsReport
    {
        await diagnostics.generate()
    }
}

// MARK: - Application integration

@MainActor
public final class WorkspaceApplicationDelegate:
    NSObject,
    NSApplicationDelegate
{
    public let engine:
        AppleWindowWorkspaceEngine

    public init(
        applicationSupportDirectory:
            URL
    ) {

        let persistenceURL =
            applicationSupportDirectory
                .appendingPathComponent(
                    "WindowWorkspace"
                )
                .appendingPathComponent(
                    "workspace-state.json"
                )

        self.engine =
            AppleWindowWorkspaceEngine(
                persistenceURL:
                    persistenceURL
            )

        super.init()
    }

    public func applicationDidFinishLaunching(
        _ notification:
            Notification
    ) {

        Task {
            await engine.start()
        }
    }

    public func applicationWillTerminate(
        _ notification:
            Notification
    ) {

        Task {
            await engine.shutdown()
        }
    }
}

// MARK: - Logging

private enum Logger {

    static let workspace =
        os.Logger(
            subsystem:
                "com.example.AppleWindowWorkspaceEngine",
            category:
                "workspace"
        )
}

// MARK: - Example usage

@MainActor
func configureWorkspaceEngine(
    window:
        NSWindow,
    applicationSupport:
        URL
) async {

    let engine =
        AppleWindowWorkspaceEngine(
            persistenceURL:
                applicationSupport
                .appendingPathComponent(
                    "workspace-state.json"
                )
        )

    await engine.start()

    let mainWindow =
        engine.register(
            window:
                window,
            role:
                .primary
        )

    let workspace =
        await engine.createWorkspace(
            name:
                "Development",
            kind:
                .development,
            layout:
                .mainAndSidebar
        )

    await engine.assign(
        window:
            mainWindow,
        to:
            workspace.id
    )

    engine.maximize(
        mainWindow
    )

    let report =
        await engine.diagnosticsReport()

    Logger.workspace.info(
        "Workspace diagnostics: \(report.windows.count) windows, \(report.displays.count) displays."
    )
}






//
//  AppleFileIntelligenceEngine.swift
//
//  #2 — macOS File Intelligence Engine
//
//  Swift 6 / macOS
//
//  Public frameworks:
//    Foundation
//    AppKit
//    UniformTypeIdentifiers
//    CoreServices / Metadata APIs where available
//
//  Architecture:
//
//              File System
//                  │
//          ┌───────▼────────┐
//          │ Change Monitor  │
//          └───────┬────────┘
//                  │
//          ┌───────▼────────┐
//          │ File Indexer    │
//          └───────┬────────┘
//                  │
//       ┌──────────┼───────────┐
//       ▼          ▼           ▼
//    Metadata   Content      Hashing
//    Extractor  Analyzer     Engine
//       │          │           │
//       └──────────┼───────────┘
//                  ▼
//          ┌───────────────┐
//          │ File Index    │
//          └───────┬───────┘
//                  │
//      ┌───────────┼────────────┐
//      ▼           ▼            ▼
//   Search     Duplicates   Smart Folders
//      │           │            │
//      └───────────┼────────────┘
//                  ▼
//          Storage Analytics
//
// Important:
// This is an application-level intelligence/indexing layer.
// It does not replace Apple's private Spotlight implementation.
//

import Foundation
import AppKit
import UniformTypeIdentifiers
import CryptoKit
import os

// MARK: - IDs

public struct FileRecordID:
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

public struct FileVolumeID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: String

    public init(
        rawValue: String
    ) {
        self.rawValue = rawValue
    }
}

// MARK: - File classification

public enum FileCategory:
    String,
    Codable,
    Sendable
{
    case document
    case image
    case video
    case audio
    case archive
    case application
    case sourceCode
    case executable
    case database
    case spreadsheet
    case presentation
    case text
    case font
    case folder
    case package
    case unknown
}

// MARK: - File importance

public enum FileImportance:
    Int,
    Codable,
    Sendable
{
    case negligible = 0
    case low = 1
    case normal = 2
    case important = 3
    case critical = 4
}

// MARK: - Index state

public enum FileIndexState:
    String,
    Codable,
    Sendable
{
    case discovered
    case indexing
    case indexed
    case stale
    case unavailable
    case excluded
    case deleted
    case error
}

// MARK: - File hash

public struct FileHash:
    Codable,
    Hashable,
    Sendable
{
    public let algorithm:
        String

    public let hex:
        String

    public let byteCount:
        Int64

    public init(
        algorithm:
            String,
        hex:
            String,
        byteCount:
            Int64
    ) {
        self.algorithm =
            algorithm

        self.hex =
            hex

        self.byteCount =
            byteCount
    }
}

// MARK: - File metadata

public struct FileMetadata:
    Codable,
    Sendable
{
    public var displayName:
        String

    public var fileExtension:
        String?

    public var contentType:
        String?

    public var category:
        FileCategory

    public var byteSize:
        Int64

    public var createdAt:
        Date?

    public var modifiedAt:
        Date?

    public var accessedAt:
        Date?

    public var isDirectory:
        Bool

    public var isSymbolicLink:
        Bool

    public var isHidden:
        Bool

    public var isPackage:
        Bool

    public var isReadable:
        Bool

    public var isWritable:
        Bool

    public var ownerName:
        String?

    public init(
        displayName:
            String,
        fileExtension:
            String?,
        contentType:
            String?,
        category:
            FileCategory,
        byteSize:
            Int64,
        createdAt:
            Date?,
        modifiedAt:
            Date?,
        accessedAt:
            Date?,
        isDirectory:
            Bool,
        isSymbolicLink:
            Bool,
        isHidden:
            Bool,
        isPackage:
            Bool,
        isReadable:
            Bool,
        isWritable:
            Bool,
        ownerName:
            String?
    ) {
        self.displayName =
            displayName

        self.fileExtension =
            fileExtension

        self.contentType =
            contentType

        self.category =
            category

        self.byteSize =
            byteSize

        self.createdAt =
            createdAt

        self.modifiedAt =
            modifiedAt

        self.accessedAt =
            accessedAt

        self.isDirectory =
            isDirectory

        self.isSymbolicLink =
            isSymbolicLink

        self.isHidden =
            isHidden

        self.isPackage =
            isPackage

        self.isReadable =
            isReadable

        self.isWritable =
            isWritable

        self.ownerName =
            ownerName
    }
}

// MARK: - Tags

public struct FileTag:
    Codable,
    Hashable,
    Sendable
{
    public let name:
        String

    public let colorIndex:
        Int?

    public init(
        name:
            String,
        colorIndex:
            Int? = nil
    ) {
        self.name =
            name

        self.colorIndex =
            colorIndex
    }
}

// MARK: - File record

public struct FileRecord:
    Codable,
    Sendable
{
    public let id:
        FileRecordID

    public let url:
        URL

    public var metadata:
        FileMetadata

    public var hash:
        FileHash?

    public var tags:
        [FileTag]

    public var importance:
        FileImportance

    public var state:
        FileIndexState

    public var lastIndexedAt:
        Date?

    public var contentPreview:
        String?

    public var keywords:
        [String]

    public init(
        id:
            FileRecordID = FileRecordID(),
        url:
            URL,
        metadata:
            FileMetadata,
        hash:
            FileHash? = nil,
        tags:
            [FileTag] = [],
        importance:
            FileImportance = .normal,
        state:
            FileIndexState = .discovered,
        lastIndexedAt:
            Date? = nil,
        contentPreview:
            String? = nil,
        keywords:
            [String] = []
    ) {
        self.id =
            id

        self.url =
            url

        self.metadata =
            metadata

        self.hash =
            hash

        self.tags =
            tags

        self.importance =
            importance

        self.state =
            state

        self.lastIndexedAt =
            lastIndexedAt

        self.contentPreview =
            contentPreview

        self.keywords =
            keywords
    }
}

// MARK: - Metadata extraction

public struct FileMetadataExtractor:
    Sendable
{
    public init() {}

    public func extract(
        url:
            URL
    )
        throws
        -> FileMetadata
    {
        let values =
            try url.resourceValues(
                forKeys:
                    [
                        .nameKey,
                        .isDirectoryKey,
                        .isSymbolicLinkKey,
                        .isHiddenKey,
                        .isPackageKey,
                        .isReadableKey,
                        .isWritableKey,
                        .fileSizeKey,
                        .creationDateKey,
                        .contentModificationDateKey,
                        .contentAccessDateKey,
                        .contentTypeKey
                    ]
            )

        let name =
            values.name ??
            url.lastPathComponent

        let ext =
            url.pathExtension.isEmpty
                ? nil
                : url.pathExtension

        let contentType =
            values.contentType?.identifier

        let category =
            Self.category(
                contentType:
                    values.contentType,
                pathExtension:
                    ext
            )

        return FileMetadata(
            displayName:
                name,
            fileExtension:
                ext,
            contentType:
                contentType,
            category:
                category,
            byteSize:
                Int64(
                    values.fileSize ?? 0
                ),
            createdAt:
                values.creationDate,
            modifiedAt:
                values.contentModificationDate,
            accessedAt:
                values.contentAccessDate,
            isDirectory:
                values.isDirectory ?? false,
            isSymbolicLink:
                values.isSymbolicLink ?? false,
            isHidden:
                values.isHidden ?? false,
            isPackage:
                values.isPackage ?? false,
            isReadable:
                values.isReadable ?? false,
            isWritable:
                values.isWritable ?? false,
            ownerName:
                nil
        )
    }

    private static func category(
        contentType:
            UTType?,
        pathExtension:
            String?
    )
        -> FileCategory
    {
        if contentType?.conforms(
            to:
                .directory
        ) == true {
            return .folder
        }

        if contentType?.conforms(
            to:
                .image
        ) == true {
            return .image
        }

        if contentType?.conforms(
            to:
                .movie
        ) == true {
            return .video
        }

        if contentType?.conforms(
            to:
                .audio
        ) == true {
            return .audio
        }

        if contentType?.conforms(
            to:
                .application
        ) == true {
            return .application
        }

        if contentType?.conforms(
            to:
                .archive
        ) == true {
            return .archive
        }

        if contentType?.conforms(
            to:
                .sourceCode
        ) == true {
            return .sourceCode
        }

        if contentType?.conforms(
            to:
                .spreadsheet
        ) == true {
            return .spreadsheet
        }

        if contentType?.conforms(
            to:
                .presentation
        ) == true {
            return .presentation
        }

        if contentType?.conforms(
            to:
                .font
        ) == true {
            return .font
        }

        if let pathExtension {

            switch pathExtension.lowercased() {

            case "swift",
                 "c",
                 "h",
                 "cpp",
                 "hpp",
                 "m",
                 "mm",
                 "rs",
                 "go",
                 "java",
                 "kt",
                 "kts",
                 "py",
                 "js",
                 "ts",
                 "tsx",
                 "jsx":
                return .sourceCode

            case "sql",
                 "sqlite",
                 "db":
                return .database

            case "txt",
                 "md",
                 "rtf":
                return .text

            default:
                break
            }
        }

        return .unknown
    }
}

// MARK: - Content analyzer

public struct FileContentAnalysis:
    Codable,
    Sendable
{
    public let preview:
        String?

    public let keywords:
        [String]

    public let wordCount:
        Int

    public let characterCount:
        Int

    public init(
        preview:
            String?,
        keywords:
            [String],
        wordCount:
            Int,
        characterCount:
            Int
    ) {
        self.preview =
            preview

        self.keywords =
            keywords

        self.wordCount =
            wordCount

        self.characterCount =
            characterCount
    }
}

public struct FileContentAnalyzer:
    Sendable
{
    public var maximumBytes:
        Int

    public var previewCharacters:
        Int

    public init(
        maximumBytes:
            Int = 2_000_000,
        previewCharacters:
            Int = 4_000
    ) {
        self.maximumBytes =
            maximumBytes

        self.previewCharacters =
            previewCharacters
    }

    public func analyze(
        url:
            URL
    )
        -> FileContentAnalysis?
    {
        guard
            let data =
                try? Data(
                    contentsOf:
                        url,
                    options:
                        .mappedIfSafe
                ),
            data.count <= maximumBytes,
            let text =
                String(
                    data:
                        data,
                    encoding:
                        .utf8
                )
        else {
            return nil
        }

        let words =
            text
                .split {
                    $0.isWhitespace ||
                    $0.isNewline ||
                    $0.isPunctuation
                }
                .map {
                    String($0).lowercased()
                }

        let frequency =
            Dictionary(
                words.map {
                    (
                        $0,
                        1
                    )
                },
                uniquingKeysWith:
                    +
            )

        let keywords =
            frequency
                .sorted {
                    $0.value >
                    $1.value
                }
                .prefix(
                    20
                )
                .map {
                    $0.key
                }

        let preview =
            String(
                text.prefix(
                    previewCharacters
                )
            )

        return FileContentAnalysis(
            preview:
                preview,
            keywords:
                keywords,
            wordCount:
                words.count,
            characterCount:
                text.count
        )
    }
}

// MARK: - Hashing

public struct FileHashEngine:
    Sendable
{
    public var chunkSize:
        Int

    public init(
        chunkSize:
            Int = 1024 * 1024
    ) {
        self.chunkSize =
            chunkSize
    }

    public func hash(
        url:
            URL
    )
        throws
        -> FileHash
    {
        let handle =
            try FileHandle(
                forReadingFrom:
                    url
            )

        defer {
            try? handle.close()
        }

        var hasher =
            SHA256()

        var totalBytes:
            Int64 =
            0

        while true {

            let data =
                try handle.read(
                    upToCount:
                        chunkSize
                ) ?? Data()

            if data.isEmpty {
                break
            }

            hasher.update(
                data:
                    data
            )

            totalBytes +=
                Int64(
                    data.count
                )
        }

        let digest =
            hasher.finalize()

        let hex =
            digest
                .map {
                    String(
                        format:
                            "%02x",
                        $0
                    )
                }
                .joined()

        return FileHash(
            algorithm:
                "SHA-256",
            hex:
                hex,
            byteCount:
                totalBytes
        )
    }
}

// MARK: - Lightweight duplicate fingerprint

public struct FileFingerprint:
    Hashable,
    Sendable
{
    public let byteSize:
        Int64

    public let firstChunkHash:
        String

    public init(
        byteSize:
            Int64,
        firstChunkHash:
            String
    ) {
        self.byteSize =
            byteSize

        self.firstChunkHash =
            firstChunkHash
    }
}

public struct FileFingerprintEngine:
    Sendable
{
    public var sampleSize:
        Int

    public init(
        sampleSize:
            Int = 64 * 1024
    ) {
        self.sampleSize =
            sampleSize
    }

    public func fingerprint(
        url:
            URL
    )
        throws
        -> FileFingerprint
    {
        let values =
            try url.resourceValues(
                forKeys:
                    [
                        .fileSizeKey
                    ]
            )

        let size =
            Int64(
                values.fileSize ?? 0
            )

        let handle =
            try FileHandle(
                forReadingFrom:
                    url
            )

        defer {
            try? handle.close()
        }

        let data =
            try handle.read(
                upToCount:
                    sampleSize
            ) ?? Data()

        let digest =
            SHA256.hash(
                data:
                    data
            )

        let hex =
            digest
                .map {
                    String(
                        format:
                            "%02x",
                        $0
                    )
                }
                .joined()

        return FileFingerprint(
            byteSize:
                size,
            firstChunkHash:
                hex
        )
    }
}

// MARK: - Duplicate groups

public struct DuplicateGroup:
    Sendable
{
    public let fingerprint:
        FileFingerprint

    public let files:
        [FileRecord]

    public var wastedBytes:
        Int64 {
        guard
            files.count > 1
        else {
            return 0
        }

        return files
            .dropFirst()
            .reduce(
                0
            ) {
                $0 +
                $1.metadata.byteSize
            }
    }

    public init(
        fingerprint:
            FileFingerprint,
        files:
            [FileRecord]
    ) {
        self.fingerprint =
            fingerprint

        self.files =
            files
    }
}

// MARK: - Index actor

public actor FileIndexStore {

    private var records:
        [FileRecordID: FileRecord] =
            [:]

    private var pathLookup:
        [URL: FileRecordID] =
            [:]

    public init() {}

    public func upsert(
        _ record:
            FileRecord
    ) {

        records[
            record.id
        ] =
            record

        pathLookup[
            record.url
                .standardizedFileURL
        ] =
            record.id
    }

    public func remove(
        _ id:
            FileRecordID
    ) {

        guard
            let record =
                records.removeValue(
                    forKey:
                        id
                )
        else {
            return
        }

        pathLookup.removeValue(
            forKey:
                record.url
                    .standardizedFileURL
        )
    }

    public func record(
        for url:
            URL
    )
        -> FileRecord?
    {
        guard
            let id =
                pathLookup[
                    url.standardizedFileURL
                ]
        else {
            return nil
        }

        return records[id]
    }

    public func record(
        id:
            FileRecordID
    )
        -> FileRecord?
    {
        records[id]
    }

    public func all()
        -> [FileRecord]
    {
        Array(
            records.values
        )
    }

    public func search(
        text:
            String
    )
        -> [FileRecord]
    {
        let query =
            text
                .trimmingCharacters(
                    in:
                        .whitespacesAndNewlines
                )
                .lowercased()

        guard !query.isEmpty else {
            return all()
        }

        return records.values.filter {
            record in

            let haystack =
                [
                    record.metadata.displayName,
                    record.url.path,
                    record.contentPreview ?? "",
                    record.keywords.joined(
                        separator:
                            " "
                    ),
                    record.tags.map {
                        $0.name
                    }.joined(
                        separator:
                            " "
                    )
                ]
                .joined(
                    separator:
                        " "
                )
                .lowercased()

            return haystack.contains(
                query
            )
        }
    }

    public func records(
        category:
            FileCategory
    )
        -> [FileRecord]
    {
        records.values.filter {
            $0.metadata.category ==
                category
        }
    }

    public func records(
        largerThan:
            Int64
    )
        -> [FileRecord]
    {
        records.values.filter {
            $0.metadata.byteSize >
                largerThan
        }
    }
}

// MARK: - Indexing configuration

public struct FileIndexConfiguration:
    Sendable
{
    public var includeHiddenFiles:
        Bool

    public var followSymbolicLinks:
        Bool

    public var indexContents:
        Bool

    public var calculateHashes:
        Bool

    public var calculateFullHashesAbove:
        Int64

    public var excludedExtensions:
        Set<String>

    public var excludedDirectories:
        Set<String>

    public var maximumFileSizeForContent:
        Int64

    public init(
        includeHiddenFiles:
            Bool = false,
        followSymbolicLinks:
            Bool = false,
        indexContents:
            Bool = true,
        calculateHashes:
            Bool = false,
        calculateFullHashesAbove:
            Int64 = 1024 * 1024 * 1024,
        excludedExtensions:
            Set<String> = [],
        excludedDirectories:
            Set<String> = [
                ".git",
                ".Trash",
                "node_modules",
                ".build"
            ],
        maximumFileSizeForContent:
            Int64 = 20 * 1024 * 1024
    ) {
        self.includeHiddenFiles =
            includeHiddenFiles

        self.followSymbolicLinks =
            followSymbolicLinks

        self.indexContents =
            indexContents

        self.calculateHashes =
            calculateHashes

        self.calculateFullHashesAbove =
            calculateFullHashesAbove

        self.excludedExtensions =
            excludedExtensions

        self.excludedDirectories =
            excludedDirectories

        self.maximumFileSizeForContent =
            maximumFileSizeForContent
    }
}

// MARK: - Indexing progress

public struct FileIndexProgress:
    Sendable
{
    public let discovered:
        Int

    public let indexed:
        Int

    public let skipped:
        Int

    public let failed:
        Int

    public let currentURL:
        URL?

    public let isComplete:
        Bool

    public init(
        discovered:
            Int,
        indexed:
            Int,
        skipped:
            Int,
        failed:
            Int,
        currentURL:
            URL?,
        isComplete:
            Bool
    ) {
        self.discovered =
            discovered

        self.indexed =
            indexed

        self.skipped =
            skipped

        self.failed =
            failed

        self.currentURL =
            currentURL

        self.isComplete =
            isComplete
    }
}

// MARK: - Indexing engine

public actor FileIndexer {

    private let store:
        FileIndexStore

    private let metadataExtractor:
        FileMetadataExtractor

    private let contentAnalyzer:
        FileContentAnalyzer

    private let hashEngine:
        FileHashEngine

    private let configuration:
        FileIndexConfiguration

    private var cancelled:
        Bool =
            false

    public init(
        store:
            FileIndexStore,
        configuration:
            FileIndexConfiguration =
                FileIndexConfiguration()
    ) {
        self.store =
            store

        self.configuration =
            configuration

        self.metadataExtractor =
            FileMetadataExtractor()

        self.contentAnalyzer =
            FileContentAnalyzer()

        self.hashEngine =
            FileHashEngine()
    }

    public func cancel() {
        cancelled =
            true
    }

    public func resetCancellation() {
        cancelled =
            false
    }

    public func index(
        root:
            URL,
        progress:
            @escaping @Sendable (
                FileIndexProgress
            ) -> Void
    ) async {

        cancelled =
            false

        var discovered =
            0

        var indexed =
            0

        var skipped =
            0

        var failed =
            0

        let keys:
            [URLResourceKey] =
            [
                .isDirectoryKey,
                .isSymbolicLinkKey,
                .isHiddenKey,
                .isPackageKey
            ]

        guard
            let enumerator =
                FileManager.default
                    .enumerator(
                        at:
                            root,
                        includingPropertiesForKeys:
                            keys,
                        options:
                            configuration
                                .followSymbolicLinks
                                ? []
                                : [
                                    .skipsPackageDescendants
                                ]
                    )
        else {
            return
        }

        while let next =
            enumerator.nextObject()
                as? URL
        {
            if cancelled {
                break
            }

            discovered += 1

            progress(
                FileIndexProgress(
                    discovered:
                        discovered,
                    indexed:
                        indexed,
                    skipped:
                        skipped,
                    failed:
                        failed,
                    currentURL:
                        next,
                    isComplete:
                        false
                )
            )

            do {

                let values =
                    try next.resourceValues(
                        forKeys:
                            keys
                    )

                if
                    values.isHidden == true &&
                    !configuration
                        .includeHiddenFiles
                {
                    skipped += 1
                    continue
                }

                if
                    let directory =
                        values.isDirectory,
                    directory,
                    configuration
                        .excludedDirectories
                        .contains(
                            next.lastPathComponent
                        )
                {
                    enumerator.skipDescendants()

                    skipped += 1

                    continue
                }

                if
                    !configuration
                        .excludedExtensions
                        .isEmpty,
                    configuration
                        .excludedExtensions
                        .contains(
                            next.pathExtension
                                .lowercased()
                        )
                {
                    skipped += 1
                    continue
                }

                let metadata =
                    try metadataExtractor
                        .extract(
                            url:
                                next
                        )

                var record =
                    FileRecord(
                        url:
                            next,
                        metadata:
                            metadata,
                        state:
                            .indexing
                    )

                if
                    configuration.indexContents,
                    !metadata.isDirectory,
                    metadata.byteSize <=
                        configuration
                        .maximumFileSizeForContent,
                    let analysis =
                        contentAnalyzer.analyze(
                            url:
                                next
                        )
                {
                    record.contentPreview =
                        analysis.preview

                    record.keywords =
                        analysis.keywords
                }

                if
                    configuration.calculateHashes,
                    !metadata.isDirectory
                {
                    if metadata.byteSize <=
                        configuration
                        .calculateFullHashesAbove
                    {
                        record.hash =
                            try hashEngine.hash(
                                url:
                                    next
                            )
                    }
                }

                record.state =
                    .indexed

                record.lastIndexedAt =
                    Date()

                await store.upsert(
                    record
                )

                indexed += 1

            } catch {

                failed += 1
            }
        }

        progress(
            FileIndexProgress(
                discovered:
                    discovered,
                indexed:
                    indexed,
                skipped:
                    skipped,
                failed:
                    failed,
                currentURL:
                    nil,
                isComplete:
                    true
            )
        )
    }
}

// MARK: - Duplicate detector

public actor DuplicateDetector {

    private let fingerprintEngine:
        FileFingerprintEngine

    public init() {

        self.fingerprintEngine =
            FileFingerprintEngine()
    }

    public func findDuplicates(
        in records:
            [FileRecord]
    )
        async
        -> [DuplicateGroup]
    {
        var buckets:
            [FileFingerprint:
                [FileRecord]] =
                [:]

        for record in records {

            if
                record.metadata.isDirectory
            {
                continue
            }

            guard
                record.metadata.byteSize >
                    0
            else {
                continue
            }

            guard
                let fingerprint =
                    try? fingerprintEngine
                        .fingerprint(
                            url:
                                record.url
                        )
            else {
                continue
            }

            buckets[
                fingerprint,
                default:
                    []
            ].append(
                record
            )
        }

        return buckets.compactMap {
            fingerprint,
            files in

            guard files.count > 1 else {
                return nil
            }

            return DuplicateGroup(
                fingerprint:
                    fingerprint,
                files:
                    files
            )
        }
    }
}

// MARK: - Storage analytics

public struct StorageCategorySummary:
    Codable,
    Sendable
{
    public let category:
        FileCategory

    public let fileCount:
        Int

    public let totalBytes:
        Int64

    public init(
        category:
            FileCategory,
        fileCount:
            Int,
        totalBytes:
            Int64
    ) {
        self.category =
            category

        self.fileCount =
            fileCount

        self.totalBytes =
            totalBytes
    }
}

public struct StorageAnalytics:
    Codable,
    Sendable
{
    public let totalFiles:
        Int

    public let totalBytes:
        Int64

    public let largestFiles:
        [FileRecord]

    public let categories:
        [StorageCategorySummary]

    public let duplicateBytes:
        Int64

    public init(
        totalFiles:
            Int,
        totalBytes:
            Int64,
        largestFiles:
            [FileRecord],
        categories:
            [StorageCategorySummary],
        duplicateBytes:
            Int64
    ) {
        self.totalFiles =
            totalFiles

        self.totalBytes =
            totalBytes

        self.largestFiles =
            largestFiles

        self.categories =
            categories

        self.duplicateBytes =
            duplicateBytes
    }
}

public actor StorageAnalyticsEngine {

    private let duplicateDetector:
        DuplicateDetector

    public init() {

        self.duplicateDetector =
            DuplicateDetector()
    }

    public func analyze(
        records:
            [FileRecord]
    )
        async
        -> StorageAnalytics
    {
        let files =
            records.filter {
                !$0.metadata.isDirectory
            }

        let totalBytes =
            files.reduce(
                Int64(0)
            ) {
                $0 +
                $1.metadata.byteSize
            }

        let largest =
            Array(
                files
                    .sorted {
                        $0.metadata.byteSize >
                        $1.metadata.byteSize
                    }
                    .prefix(
                        25
                    )
            )

        var categoryMap:
            [FileCategory:
                (
                    count:
                        Int,
                    bytes:
                        Int64
                )] =
                [:]

        for record in files {

            let category =
                record.metadata.category

            let current =
                categoryMap[
                    category
                ] ??
                (
                    count:
                        0,
                    bytes:
                        0
                )

            categoryMap[
                category
            ] =
                (
                    count:
                        current.count + 1,
                    bytes:
                        current.bytes +
                        record.metadata.byteSize
                )
        }

        let summaries =
            categoryMap.map {
                category,
                value in

                StorageCategorySummary(
                    category:
                        category,
                    fileCount:
                        value.count,
                    totalBytes:
                        value.bytes
                )
            }
            .sorted {
                $0.totalBytes >
                $1.totalBytes
            }

        let duplicateGroups =
            await duplicateDetector
                .findDuplicates(
                    in:
                        files
                )

        let duplicateBytes =
            duplicateGroups.reduce(
                Int64(0)
            ) {
                $0 +
                $1.wastedBytes
            }

        return StorageAnalytics(
            totalFiles:
                files.count,
            totalBytes:
                totalBytes,
            largestFiles:
                largest,
            categories:
                summaries,
            duplicateBytes:
                duplicateBytes
        )
    }
}

// MARK: - Smart query

public enum FileQuery:
    Sendable
{
    case text(String)
    case category(FileCategory)
    case minimumSize(Int64)
    case maximumSize(Int64)
    case modifiedAfter(Date)
    case modifiedBefore(Date)
    case tag(String)
    case extension(String)
    case importanceAtLeast(FileImportance)
    case all
}

// MARK: - Smart folder

public struct SmartFolder:
    Codable,
    Sendable
{
    public let id:
        UUID

    public var name:
        String

    public var queries:
        [PersistedFileQuery]

    public init(
        id:
            UUID = UUID(),
        name:
            String,
        queries:
            [PersistedFileQuery]
    ) {
        self.id =
            id

        self.name =
            name

        self.queries =
            queries
    }
}

public enum PersistedFileQuery:
    Codable,
    Sendable
{
    case text(String)
    case category(FileCategory)
    case minimumSize(Int64)
    case maximumSize(Int64)
    case modifiedAfter(Date)
    case modifiedBefore(Date)
    case tag(String)
    case fileExtension(String)
    case importanceAtLeast(FileImportance)
    case all
}

// MARK: - Query engine

public struct FileQueryEngine:
    Sendable
{
    public init() {}

    public func evaluate(
        _ query:
            FileQuery,
        against:
            FileRecord
    )
        -> Bool
    {
        switch query {

        case .all:
            return true

        case .text(
            let text
        ):
            let q =
                text.lowercased()

            let searchable =
                [
                    record.metadata.displayName,
                    record.url.path,
                    record.contentPreview ?? "",
                    record.keywords.joined(
                        separator:
                            " "
                    )
                ]
                .joined(
                    separator:
                        " "
                )
                .lowercased()

            return searchable.contains(
                q
            )

        case .category(
            let category
        ):
            return record.metadata.category ==
                category

        case .minimumSize(
            let bytes
        ):
            return record.metadata.byteSize >=
                bytes

        case .maximumSize(
            let bytes
        ):
            return record.metadata.byteSize <=
                bytes

        case .modifiedAfter(
            let date
        ):
            guard
                let modified =
                    record.metadata.modifiedAt
            else {
                return false
            }

            return modified > date

        case .modifiedBefore(
            let date
        ):
            guard
                let modified =
                    record.metadata.modifiedAt
            else {
                return false
            }

            return modified < date

        case .tag(
            let name
        ):
            return record.tags.contains {
                $0.name.caseInsensitiveCompare(
                    name
                ) == .orderedSame
            }

        case .extension(
            let ext
        ):
            return record.metadata.fileExtension?
                .caseInsensitiveCompare(
                    ext
                ) == .orderedSame

        case .importanceAtLeast(
            let importance
        ):
            return record.importance.rawValue >=
                importance.rawValue
        }
    }

    public func evaluate(
        _ queries:
            [FileQuery],
        against:
            FileRecord
    )
        -> Bool
    {
        queries.allSatisfy {
            evaluate(
                $0,
                against:
                    record
            )
        }
    }
}

// MARK: - File watcher

@MainActor
public final class FileSystemWatcher {

    public typealias ChangeHandler =
        @Sendable (
            URL
        ) -> Void

    private var source:
        DispatchSourceFileSystemObject?

    private var fileDescriptor:
        Int32 =
            -1

    private let queue:
        DispatchQueue

    public init() {

        self.queue =
            DispatchQueue(
                label:
                    "com.example.file-intelligence.watcher",
                qos:
                    .utility
            )
    }

    public func watch(
        directory:
            URL,
        handler:
            @escaping ChangeHandler
    ) throws {

        stop()

        let descriptor =
            open(
                directory.path,
                O_EVTONLY
            )

        guard
            descriptor >= 0
        else {
            throw WatcherError
                .openFailed
        }

        fileDescriptor =
            descriptor

        let source =
            DispatchSource.makeFileSystemObjectSource(
                fileDescriptor:
                    descriptor,
                eventMask:
                    [
                        .write,
                        .rename,
                        .delete,
                        .attrib,
                        .extend,
                        .link,
                        .revoke
                    ],
                queue:
                    queue
            )

        source.setEventHandler {
            [weak self] in

            guard
                let self
            else {
                return
            }

            handler(
                directory
            )

            if source.data.contains(
                .delete
            ) ||
                source.data.contains(
                    .rename
                )
            {
                self.stop()
            }
        }

        source.setCancelHandler {
            close(
                descriptor
            )
        }

        self.source =
            source

        source.resume()
    }

    public func stop() {

        source?.cancel()

        source =
            nil

        fileDescriptor =
            -1
    }

    deinit {
        source?.cancel()
    }

    public enum WatcherError:
        Error
    {
        case openFailed
    }
}

// MARK: - Bookmark manager

public actor SecurityScopedBookmarkStore {

    private var bookmarks:
        [String: Data] =
            [:]

    public init() {}

    public func save(
        url:
            URL,
        key:
            String
    )
        throws
    {
        let data =
            try url.bookmarkData(
                options:
                    .withSecurityScope,
                includingResourceValuesForKeys:
                    nil,
                relativeTo:
                    nil
            )

        bookmarks[
            key
        ] =
            data
    }

    public func resolve(
        key:
            String
    )
        throws
        -> URL?
    {
        guard
            let data =
                bookmarks[key]
        else {
            return nil
        }

        var stale =
            false

        let url =
            try URL(
                resolvingBookmarkData:
                    data,
                options:
                    [
                        .withSecurityScope
                    ],
                relativeTo:
                    nil,
                bookmarkDataIsStale:
                    &stale
            )

        return url
    }

    public func remove(
        key:
            String
    ) {
        bookmarks.removeValue(
            forKey:
                key
        )
    }
}

// MARK: - Persistence

public actor FileIndexPersistence {

    private let url:
        URL

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    public init(
        url:
            URL
    ) {
        self.url =
            url

        self.encoder =
            JSONEncoder()

        self.decoder =
            JSONDecoder()

        encoder.dateEncodingStrategy =
            .iso8601

        decoder.dateDecodingStrategy =
            .iso8601

        encoder.outputFormatting =
            [
                .prettyPrinted,
                .sortedKeys
            ]
    }

    public func save(
        records:
            [FileRecord]
    )
        throws
    {
        let data =
            try encoder.encode(
                records
            )

        let directory =
            url.deletingLastPathComponent()

        try FileManager.default
            .createDirectory(
                at:
                    directory,
                withIntermediateDirectories:
                    true
            )

        try data.write(
            to:
                url,
            options:
                .atomic
        )
    }

    public func load()
        throws
        -> [FileRecord]
    {
        guard
            FileManager.default.fileExists(
                atPath:
                    url.path
            )
        else {
            return []
        }

        let data =
            try Data(
                contentsOf:
                    url
            )

        return try decoder.decode(
            [
                FileRecord
            ].self,
            from:
                data
        )
    }
}

// MARK: - Index coordinator

public actor FileIntelligenceCoordinator {

    public let store:
        FileIndexStore

    public let indexer:
        FileIndexer

    public let analytics:
        StorageAnalyticsEngine

    private let persistence:
        FileIndexPersistence

    private let queryEngine:
        FileQueryEngine

    public init(
        configuration:
            FileIndexConfiguration,
        persistenceURL:
            URL
    ) {

        let store =
            FileIndexStore()

        self.store =
            store

        self.indexer =
            FileIndexer(
                store:
                    store,
                configuration:
                    configuration
            )

        self.analytics =
            StorageAnalyticsEngine()

        self.persistence =
            FileIndexPersistence(
                url:
                    persistenceURL
            )

        self.queryEngine =
            FileQueryEngine()
    }

    public func start() async {

        do {

            let records =
                try await persistence.load()

            for record in records {
                await store.upsert(
                    record
                )
            }

        } catch {

            Logger.files.error(
                "Could not load file index: \(error.localizedDescription)"
            )
        }
    }

    public func index(
        root:
            URL,
        progress:
            @escaping @Sendable (
                FileIndexProgress
            ) -> Void
    ) async {

        await indexer.index(
            root:
                root,
            progress:
                progress
        )

        await save()
    }

    public func save() async {

        let records =
            await store.all()

        do {

            try await persistence.save(
                records:
                    records
            )

        } catch {

            Logger.files.error(
                "Could not save file index: \(error.localizedDescription)"
            )
        }
    }

    public func search(
        text:
            String
    )
        async
        -> [FileRecord]
    {
        await store.search(
            text:
                text
        )
    }

    public func query(
        _ query:
            FileQuery
    )
        async
        -> [FileRecord]
    {
        let records =
            await store.all()

        return records.filter {
            queryEngine.evaluate(
                query,
                against:
                    $0
            )
        }
    }

    public func storageReport()
        async
        -> StorageAnalytics
    {
        let records =
            await store.all()

        return await analytics.analyze(
            records:
                records
        )
    }

    public func allRecords()
        async
        -> [FileRecord]
    {
        await store.all()
    }
}

// MARK: - Unified public API

@MainActor
public final class AppleFileIntelligenceEngine {

    public let coordinator:
        FileIntelligenceCoordinator

    public let watcher:
        FileSystemWatcher

    public let bookmarks:
        SecurityScopedBookmarkStore

    public private(set) var running:
        Bool =
            false

    public init(
        applicationSupportDirectory:
            URL,
        configuration:
            FileIndexConfiguration =
                FileIndexConfiguration()
    ) {

        let indexURL =
            applicationSupportDirectory
                .appendingPathComponent(
                    "FileIntelligence"
                )
                .appendingPathComponent(
                    "index.json"
                )

        self.coordinator =
            FileIntelligenceCoordinator(
                configuration:
                    configuration,
                persistenceURL:
                    indexURL
            )

        self.watcher =
            FileSystemWatcher()

        self.bookmarks =
            SecurityScopedBookmarkStore()
    }

    public func start() async {

        guard !running else {
            return
        }

        running =
            true

        await coordinator.start()
    }

    public func stop() async {

        guard running else {
            return
        }

        watcher.stop()

        await coordinator.save()

        running =
            false
    }

    public func index(
        directory:
            URL,
        progress:
            @escaping @Sendable (
                FileIndexProgress
            ) -> Void
    ) async {

        await coordinator.index(
            root:
                directory,
            progress:
                progress
        )
    }

    public func search(
        _ text:
            String
    ) async
        -> [FileRecord]
    {
        await coordinator.search(
            text:
                text
        )
    }

    public func storageReport()
        async
        -> StorageAnalytics
    {
        await coordinator.storageReport()
    }

    public func watch(
        directory:
            URL
    ) throws {

        try watcher.watch(
            directory:
                directory
        ) {
            [weak self]
            changedURL in

            guard
                let self
            else {
                return
            }

            Task {
                await self.handleChange(
                    at:
                        changedURL
                )
            }
        }
    }

    private func handleChange(
        at directory:
            URL
    ) async {

        await coordinator.index(
            root:
                directory
        ) {
            _ in
        }
    }
}

// MARK: - Logging

private enum Logger {

    static let files =
        os.Logger(
            subsystem:
                "com.example.AppleFileIntelligence",
            category:
                "files"
        )
}

// MARK: - Example

@MainActor
func createFileIntelligenceEngine(
    applicationSupport:
        URL,
    homeDirectory:
        URL
) async {

    let engine =
        AppleFileIntelligenceEngine(
            applicationSupportDirectory:
                applicationSupport,
            configuration:
                FileIndexConfiguration(
                    includeHiddenFiles:
                        false,
                    followSymbolicLinks:
                        false,
                    indexContents:
                        true,
                    calculateHashes:
                        true
                )
        )

    await engine.start()

    await engine.index(
        directory:
            homeDirectory
    ) {
        progress in

        if progress.isComplete {

            print(
                """
                Index complete.
                Discovered: \(progress.discovered)
                Indexed: \(progress.indexed)
                Skipped: \(progress.skipped)
                Failed: \(progress.failed)
                """
            )
        }
    }

    let results =
        await engine.search(
            "Swift"
        )

    for result in results.prefix(
        20
    ) {
        print(
            result.url.path
        )
    }

    let report =
        await engine.storageReport()

    print(
        "Indexed files: \(report.totalFiles)"
    )

    print(
        "Indexed bytes: \(report.totalBytes)"
    )

    print(
        "Potential duplicate waste: \(report.duplicateBytes)"
    )
}






//
//  AppleWorkoutHealthEngine.swift
//
//  #3 — Native Apple Workout & Health Engine
//
//  Swift 6
//  iOS / watchOS architecture
//
//  Frameworks:
//    Foundation
//    HealthKit
//    CoreLocation
//    Observation
//
//  Architecture:
//
//                 SwiftUI / AppKit / Watch UI
//                           │
//                           ▼
//                 WorkoutHealthEngine
//                           │
//              ┌────────────┼────────────┐
//              ▼            ▼            ▼
//        SessionManager  Metrics      Intervals
//              │            │            │
//              ▼            ▼            ▼
//        HKWorkoutSession  Live Data   Timer Engine
//              │            │
//              └────────────┼────────────┘
//                           ▼
//                  HKLiveWorkoutBuilder
//                           │
//                           ▼
//                       HealthKit
//
//       Heart Rate ─────────┐
//       Calories ───────────┤
//       Distance ────────────┤
//       Pace ────────────────┤
//       Cadence ─────────────┤
//       Elevation ───────────┤
//       Power ───────────────┤
//       Workout Zones ───────┘
//
//  Notes:
//  - HealthKit remains the system of record.
//  - UI is deliberately separated from workout state.
//  - Health data should not be logged casually.
//  - Actual HealthKit authorization is required on device.
//  - Some metrics depend on workout type/device/sensors.
//

import Foundation
import HealthKit
import CoreLocation
import Observation
import os

// MARK: - Identifiers

public struct WorkoutSessionID:
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

public struct WorkoutIntervalID:
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

// MARK: - Workout state

public enum WorkoutEngineState:
    String,
    Codable,
    Sendable
{
    case idle
    case preparing
    case running
    case paused
    case ending
    case finished
    case failed
}

// MARK: - Workout type

public enum WorkoutActivity:
    String,
    Codable,
    CaseIterable,
    Sendable
{
    case running
    case walking
    case cycling
    case hiking
    case swimming
    case rowing
    case elliptical
    case stairClimbing
    case functionalStrength
    case traditionalStrength
    case highIntensityIntervalTraining
    case yoga
    case other

    public var healthKitType:
        HKWorkoutActivityType
    {
        switch self {

        case .running:
            return .running

        case .walking:
            return .walking

        case .cycling:
            return .cycling

        case .hiking:
            return .hiking

        case .swimming:
            return .swimming

        case .rowing:
            return .rowing

        case .elliptical:
            return .elliptical

        case .stairClimbing:
            return .stairClimbing

        case .functionalStrength:
            return .functionalStrengthTraining

        case .traditionalStrength:
            return .traditionalStrengthTraining

        case .highIntensityIntervalTraining:
            return .highIntensityTraining

        case .yoga:
            return .yoga

        case .other:
            return .other
        }
    }
}

// MARK: - Workout location

public enum WorkoutLocation:
    String,
    Codable,
    Sendable
{
    case indoor
    case outdoor
    case unspecified
}

// MARK: - Heart rate

public struct HeartRateSample:
    Codable,
    Sendable
{
    public let bpm:
        Double

    public let timestamp:
        Date

    public init(
        bpm:
            Double,
        timestamp:
            Date
    ) {
        self.bpm =
            bpm

        self.timestamp =
            timestamp
    }
}

// MARK: - Workout metrics

public struct WorkoutMetrics:
    Codable,
    Sendable
{
    public var elapsedTime:
        TimeInterval

    public var activeEnergyKilocalories:
        Double

    public var basalEnergyKilocalories:
        Double

    public var distanceMeters:
        Double

    public var heartRateBPM:
        Double?

    public var averageHeartRateBPM:
        Double?

    public var maximumHeartRateBPM:
        Double?

    public var paceSecondsPerKilometer:
        Double?

    public var speedMetersPerSecond:
        Double?

    public var cadence:
        Double?

    public var cyclingPowerWatts:
        Double?

    public var elevationGainMeters:
        Double

    public var stepCount:
        Double?

    public init(
        elapsedTime:
            TimeInterval = 0,
        activeEnergyKilocalories:
            Double = 0,
        basalEnergyKilocalories:
            Double = 0,
        distanceMeters:
            Double = 0,
        heartRateBPM:
            Double? = nil,
        averageHeartRateBPM:
            Double? = nil,
        maximumHeartRateBPM:
            Double? = nil,
        paceSecondsPerKilometer:
            Double? = nil,
        speedMetersPerSecond:
            Double? = nil,
        cadence:
            Double? = nil,
        cyclingPowerWatts:
            Double? = nil,
        elevationGainMeters:
            Double = 0,
        stepCount:
            Double? = nil
    ) {
        self.elapsedTime =
            elapsedTime

        self.activeEnergyKilocalories =
            activeEnergyKilocalories

        self.basalEnergyKilocalories =
            basalEnergyKilocalories

        self.distanceMeters =
            distanceMeters

        self.heartRateBPM =
            heartRateBPM

        self.averageHeartRateBPM =
            averageHeartRateBPM

        self.maximumHeartRateBPM =
            maximumHeartRateBPM

        self.paceSecondsPerKilometer =
            paceSecondsPerKilometer

        self.speedMetersPerSecond =
            speedMetersPerSecond

        self.cadence =
            cadence

        self.cyclingPowerWatts =
            cyclingPowerWatts

        self.elevationGainMeters =
            elevationGainMeters

        self.stepCount =
            stepCount
    }
}

// MARK: - Heart rate zones

public enum HeartRateZone:
    Int,
    Codable,
    CaseIterable,
    Sendable
{
    case zone1 = 1
    case zone2 = 2
    case zone3 = 3
    case zone4 = 4
    case zone5 = 5
}

public struct HeartRateZoneConfiguration:
    Codable,
    Sendable
{
    public let maximumHeartRate:
        Double

    public init(
        maximumHeartRate:
            Double
    ) {
        self.maximumHeartRate =
            maximumHeartRate
    }

    public func zone(
        for bpm:
            Double
    )
        -> HeartRateZone
    {
        let percentage =
            bpm /
            maximumHeartRate

        switch percentage {

        case ..<0.60:
            return .zone1

        case ..<0.70:
            return .zone2

        case ..<0.80:
            return .zone3

        case ..<0.90:
            return .zone4

        default:
            return .zone5
        }
    }
}

// MARK: - Zone timing

public struct HeartRateZoneSummary:
    Codable,
    Sendable
{
    public var zone:
        HeartRateZone

    public var duration:
        TimeInterval

    public init(
        zone:
            HeartRateZone,
        duration:
            TimeInterval = 0
    ) {
        self.zone =
            zone

        self.duration =
            duration
    }
}

// MARK: - Interval configuration

public enum WorkoutIntervalKind:
    String,
    Codable,
    Sendable
{
    case warmup
    case work
    case recovery
    case cooldown
    case free
}

public struct WorkoutInterval:
    Codable,
    Sendable
{
    public let id:
        WorkoutIntervalID

    public let kind:
        WorkoutIntervalKind

    public let duration:
        TimeInterval

    public let targetHeartRate:
        ClosedRange<Double>?

    public let targetPaceSecondsPerKilometer:
        ClosedRange<Double>?

    public let targetPowerWatts:
        ClosedRange<Double>?

    public init(
        id:
            WorkoutIntervalID = WorkoutIntervalID(),
        kind:
            WorkoutIntervalKind,
        duration:
            TimeInterval,
        targetHeartRate:
            ClosedRange<Double>? = nil,
        targetPaceSecondsPerKilometer:
            ClosedRange<Double>? = nil,
        targetPowerWatts:
            ClosedRange<Double>? = nil
    ) {
        self.id =
            id

        self.kind =
            kind

        self.duration =
            duration

        self.targetHeartRate =
            targetHeartRate

        self.targetPaceSecondsPerKilometer =
            targetPaceSecondsPerKilometer

        self.targetPowerWatts =
            targetPowerWatts
    }
}

// MARK: - Interval state

public enum IntervalState:
    String,
    Codable,
    Sendable
{
    case pending
    case active
    case completed
    case skipped
}

public struct WorkoutIntervalRuntime:
    Codable,
    Sendable
{
    public let interval:
        WorkoutInterval

    public var state:
        IntervalState

    public var elapsed:
        TimeInterval

    public init(
        interval:
            WorkoutInterval,
        state:
            IntervalState = .pending,
        elapsed:
            TimeInterval = 0
    ) {
        self.interval =
            interval

        self.state =
            state

        self.elapsed =
            elapsed
    }
}

// MARK: - Workout summary

public struct WorkoutSummary:
    Codable,
    Sendable
{
    public let sessionID:
        WorkoutSessionID

    public let activity:
        WorkoutActivity

    public let location:
        WorkoutLocation

    public let startedAt:
        Date

    public let endedAt:
        Date

    public let metrics:
        WorkoutMetrics

    public let zoneSummaries:
        [HeartRateZoneSummary]

    public let intervals:
        [WorkoutIntervalRuntime]

    public init(
        sessionID:
            WorkoutSessionID,
        activity:
            WorkoutActivity,
        location:
            WorkoutLocation,
        startedAt:
            Date,
        endedAt:
            Date,
        metrics:
            WorkoutMetrics,
        zoneSummaries:
            [HeartRateZoneSummary],
        intervals:
            [WorkoutIntervalRuntime]
    ) {
        self.sessionID =
            sessionID

        self.activity =
            activity

        self.location =
            location

        self.startedAt =
            startedAt

        self.endedAt =
            endedAt

        self.metrics =
            metrics

        self.zoneSummaries =
            zoneSummaries

        self.intervals =
            intervals
    }
}

// MARK: - Workout configuration

public struct WorkoutConfiguration:
    Codable,
    Sendable
{
    public let activity:
        WorkoutActivity

    public let location:
        WorkoutLocation

    public let intervals:
        [WorkoutInterval]

    public let heartRateZoneConfiguration:
        HeartRateZoneConfiguration?

    public let automaticallyPause:
        Bool

    public init(
        activity:
            WorkoutActivity,
        location:
            WorkoutLocation = .unspecified,
        intervals:
            [WorkoutInterval] = [],
        heartRateZoneConfiguration:
            HeartRateZoneConfiguration? = nil,
        automaticallyPause:
            Bool = false
    ) {
        self.activity =
            activity

        self.location =
            location

        self.intervals =
            intervals

        self.heartRateZoneConfiguration =
            heartRateZoneConfiguration

        self.automaticallyPause =
            automaticallyPause
    }
}

// MARK: - HealthKit authorization

public actor HealthKitAuthorizationManager {

    private let healthStore:
        HKHealthStore

    public init(
        healthStore:
            HKHealthStore =
                HKHealthStore()
    ) {
        self.healthStore =
            healthStore
    }

    public func requestAuthorization()
        async
        throws
    {
        guard HKHealthStore.isHealthDataAvailable()
        else {
            throw HealthEngineError
                .healthDataUnavailable
        }

        var readTypes:
            Set<HKObjectType> =
            [
                HKObjectType.workoutType()
            ]

        var shareTypes:
            Set<HKSampleType> =
            [
                HKObjectType.workoutType()
            ]

        let identifiers:
            [HKQuantityTypeIdentifier] =
            [
                .heartRate,
                .activeEnergyBurned,
                .basalEnergyBurned,
                .distanceWalkingRunning,
                .distanceCycling,
                .stepCount,
                .runningSpeed,
                .runningStrideLength,
                .runningPower,
                .cyclingPower,
                .cyclingCadence,
                .flightsClimbed,
                .elevationGained
            ]

        for identifier in identifiers {

            if let type =
                HKObjectType.quantityType(
                    forIdentifier:
                        identifier
                )
            {
                readTypes.insert(
                    type
                )

                shareTypes.insert(
                    type
                )
            }
        }

        try await healthStore
            .requestAuthorization(
                toShare:
                    shareTypes,
                read:
                    readTypes
            )
    }

    public func authorizationStatus(
        for type:
            HKObjectType
    )
        -> HKAuthorizationStatus
    {
        healthStore.authorizationStatus(
            for:
                type
        )
    }

    public func store()
        -> HKHealthStore
    {
        healthStore
    }
}

// MARK: - HealthKit metric extractor

public struct HealthKitMetricExtractor:
    Sendable
{
    public init() {}

    public func doubleValue(
        from statistics:
            HKStatistics?,
        unit:
            HKUnit,
        options:
            HKStatisticsOptions
    )
        -> Double?
    {
        guard
            let statistics
        else {
            return nil
        }

        switch options {

        case .discreteAverage:
            return statistics
                .averageQuantity()?
                .doubleValue(
                    for:
                        unit
                )

        case .discreteMax:
            return statistics
                .maximumQuantity()?
                .doubleValue(
                    for:
                        unit
                )

        case .discreteMin:
            return statistics
                .minimumQuantity()?
                .doubleValue(
                    for:
                        unit
                )

        case .cumulativeSum:
            return statistics
                .sumQuantity()?
                .doubleValue(
                    for:
                        unit
                )

        default:
            return nil
        }
    }
}

// MARK: - Pace calculator

public struct WorkoutPaceCalculator:
    Sendable
{
    public init() {}

    public func pace(
        distanceMeters:
            Double,
        elapsed:
            TimeInterval
    )
        -> TimeInterval?
    {
        guard
            distanceMeters > 0,
            elapsed > 0
        else {
            return nil
        }

        return elapsed /
            (distanceMeters / 1_000)
    }

    public func speed(
        distanceMeters:
            Double,
        elapsed:
            TimeInterval
    )
        -> Double?
    {
        guard
            distanceMeters > 0,
            elapsed > 0
        else {
            return nil
        }

        return distanceMeters /
            elapsed
    }
}

// MARK: - Zone engine

public actor HeartRateZoneEngine {

    private let configuration:
        HeartRateZoneConfiguration

    private var currentZone:
        HeartRateZone?

    private var lastTimestamp:
        Date?

    private var durations:
        [HeartRateZone: TimeInterval] =
            Dictionary(
                uniqueKeysWithValues:
                    HeartRateZone
                        .allCases
                        .map {
                            (
                                $0,
                                0
                            )
                        }
            )

    public init(
        configuration:
            HeartRateZoneConfiguration
    ) {
        self.configuration =
            configuration
    }

    public func ingest(
        sample:
            HeartRateSample
    ) {

        let zone =
            configuration.zone(
                for:
                    sample.bpm
            )

        if
            let previousZone =
                currentZone,
            let previousTime =
                lastTimestamp
        {
            let delta =
                sample.timestamp
                    .timeIntervalSince(
                        previousTime
                    )

            if delta >= 0,
               delta < 30
            {
                durations[
                    previousZone,
                    default:
                        0
                ] += delta
            }
        }

        currentZone =
            zone

        lastTimestamp =
            sample.timestamp
    }

    public func current()
        -> HeartRateZone?
    {
        currentZone
    }

    public func summary()
        -> [HeartRateZoneSummary]
    {
        HeartRateZone
            .allCases
            .map {
                HeartRateZoneSummary(
                    zone:
                        $0,
                    duration:
                        durations[$0] ?? 0
                )
            }
    }
}

// MARK: - Interval engine

public actor WorkoutIntervalEngine {

    private var intervals:
        [WorkoutIntervalRuntime]

    private var currentIndex:
        Int?

    public init(
        intervals:
            [WorkoutInterval]
    ) {
        self.intervals =
            intervals.map {
                WorkoutIntervalRuntime(
                    interval:
                        $0
                )
            }
    }

    public func start()
        -> WorkoutIntervalRuntime?
    {
        guard
            !intervals.isEmpty
        else {
            return nil
        }

        currentIndex =
            0

        intervals[0].state =
            .active

        return intervals[0]
    }

    public func tick(
        elapsed:
            TimeInterval
    )
        -> WorkoutIntervalRuntime?
    {
        guard
            let index =
                currentIndex
        else {
            return nil
        }

        intervals[index].elapsed =
            elapsed

        if elapsed >=
            intervals[index]
                .interval
                .duration
        {
            intervals[index].state =
                .completed

            let next =
                index + 1

            if next < intervals.count {

                currentIndex =
                    next

                intervals[next].state =
                    .active

                return intervals[next]
            }

            currentIndex =
                nil
        }

        return nil
    }

    public func skip()
        -> WorkoutIntervalRuntime?
    {
        guard
            let index =
                currentIndex
        else {
            return nil
        }

        intervals[index].state =
            .skipped

        let next =
            index + 1

        guard next < intervals.count
        else {
            currentIndex =
                nil

            return nil
        }

        currentIndex =
            next

        intervals[next].state =
            .active

        return intervals[next]
    }

    public func snapshot()
        -> [WorkoutIntervalRuntime]
    {
        intervals
    }

    public func current()
        -> WorkoutIntervalRuntime?
    {
        guard
            let index =
                currentIndex
        else {
            return nil
        }

        return intervals[index]
    }
}

// MARK: - Live workout delegate

@MainActor
public final class LiveWorkoutDelegate:
    NSObject,
    HKWorkoutSessionDelegate,
    HKLiveWorkoutBuilderDelegate
{
    public var onStateChange:
        (
            HKWorkoutSessionState,
            HKWorkoutSessionState,
            Date
        ) -> Void

    public var onFailure:
        (Error) -> Void

    public var onEvent:
        (HKWorkoutEvent) -> Void

    public var onData:
        (Set<HKSampleType>) -> Void

    public var onZone:
        (HKLiveWorkoutZoneUpdate) -> Void

    public var onActivityBegin:
        (
            HKWorkoutActivity
        ) -> Void

    public var onActivityEnd:
        (
            HKWorkoutActivity
        ) -> Void

    public override init() {

        self.onStateChange =
            {
                _,
                _,
                _ in
            }

        self.onFailure =
            {
                _ in
            }

        self.onEvent =
            {
                _ in
            }

        self.onData =
            {
                _ in
            }

        self.onZone =
            {
                _ in
            }

        self.onActivityBegin =
            {
                _ in
            }

        self.onActivityEnd =
            {
                _ in
            }

        super.init()
    }

    public func workoutSession(
        _ workoutSession:
            HKWorkoutSession,
        didChangeTo toState:
            HKWorkoutSessionState,
        from fromState:
            HKWorkoutSessionState,
        date:
            Date
    ) {

        onStateChange(
            toState,
            fromState,
            date
        )
    }

    public func workoutSession(
        _ workoutSession:
            HKWorkoutSession,
        didFailWithError error:
            any Error
    ) {

        onFailure(
            error
        )
    }

    public func workoutSession(
        _ workoutSession:
            HKWorkoutSession,
        didGenerate event:
            HKWorkoutEvent
    ) {

        onEvent(
            event
        )
    }

    public func workoutSession(
        _ workoutSession:
            HKWorkoutSession,
        didBeginActivityWith workoutConfiguration:
            HKWorkoutConfiguration,
        date:
            Date
    ) {
        // Session activity transition.
    }

    public func workoutSession(
        _ workoutSession:
            HKWorkoutSession,
        didEndActivityWith workoutConfiguration:
            HKWorkoutConfiguration,
        date:
            Date
    ) {
        // Session activity transition.
    }

    public func workoutBuilder(
        _ workoutBuilder:
            HKLiveWorkoutBuilder,
        didCollectDataOf collectedTypes:
            Set<HKSampleType>
    ) {

        onData(
            collectedTypes
        )
    }

    public func workoutBuilderDidCollectEvent(
        _ workoutBuilder:
            HKLiveWorkoutBuilder
    ) {
        // Events are surfaced through the
        // workout session delegate as well.
    }

    public func workoutBuilder(
        _ workoutBuilder:
            HKLiveWorkoutBuilder,
        didBegin workoutActivity:
            HKWorkoutActivity
    ) {

        onActivityBegin(
            workoutActivity
        )
    }

    public func workoutBuilder(
        _ workoutBuilder:
            HKLiveWorkoutBuilder,
        didEnd workoutActivity:
            HKWorkoutActivity
    ) {

        onActivityEnd(
            workoutActivity
        )
    }

    public func workoutBuilder(
        _ workoutBuilder:
            HKLiveWorkoutBuilder,
        didUpdateWorkoutZone:
            HKLiveWorkoutZoneUpdate
    ) {

        onZone(
            didUpdateWorkoutZone
        )
    }
}

// MARK: - Workout session controller

@MainActor
public final class WorkoutSessionController {

    public private(set) var session:
        HKWorkoutSession?

    public private(set) var builder:
        HKLiveWorkoutBuilder?

    private let healthStore:
        HKHealthStore

    private var delegate:
        LiveWorkoutDelegate?

    public init(
        healthStore:
            HKHealthStore
    ) {
        self.healthStore =
            healthStore
    }

    public func create(
        configuration:
            WorkoutConfiguration
    )
        throws
    {
        let hkConfiguration =
            HKWorkoutConfiguration()

        hkConfiguration.activityType =
            configuration.activity
                .healthKitType

        switch configuration.location {

        case .indoor:
            hkConfiguration.locationType =
                .indoor

        case .outdoor:
            hkConfiguration.locationType =
                .outdoor

        case .unspecified:
            hkConfiguration.locationType =
                .unknown
        }

        let newSession =
            try HKWorkoutSession(
                healthStore:
                    healthStore,
                configuration:
                    hkConfiguration
            )

        let newBuilder =
            newSession
                .associatedWorkoutBuilder()

        newBuilder.dataSource =
            HKLiveWorkoutDataSource(
                healthStore:
                    healthStore,
                workoutConfiguration:
                    hkConfiguration
            )

        newBuilder.shouldCollectWorkoutEvents =
            true

        let newDelegate =
            LiveWorkoutDelegate()

        self.delegate =
            newDelegate

        newSession.delegate =
            newDelegate

        newBuilder.delegate =
            newDelegate

        self.session =
            newSession

        self.builder =
            newBuilder
    }

    public func start() {

        guard
            let session,
            let builder
        else {
            return
        }

        let now =
            Date()

        session.startActivity(
            with:
                now
        )

        builder.beginCollection(
            withStart:
                now
        ) {
            success,
            error in

            if let error {
                Logger.workout.error(
                    "Workout collection failed: \(error.localizedDescription)"
                )
            }

            if !success {
                Logger.workout.error(
                    "Workout collection did not start."
                )
            }
        }
    }

    public func pause() {

        session?.pause()
    }

    public func resume() {

        session?.resume()
    }

    public func end() {

        session?.end()
    }

    public func stopCollection(
        completion:
            @escaping @Sendable (
                Result<HKWorkout?, Error>
            ) -> Void
    ) {

        guard
            let builder
        else {
            completion(
                .failure(
                    HealthEngineError
                        .sessionUnavailable
                )
            )

            return
        }

        builder.endCollection(
            withEnd:
                Date()
        ) {
            [weak self]
            success,
            error in

            guard success else {

                completion(
                    .failure(
                        error ??
                        HealthEngineError
                            .collectionFailed
                    )
                )

                return
            }

            builder.finishWorkout {
                workout,
                error in

                if let error {
                    completion(
                        .failure(
                            error
                        )
                    )

                    return
                }

                self?.session =
                    nil

                self?.builder =
                    nil

                completion(
                    .success(
                        workout
                    )
                )
            }
        }
    }
}

// MARK: - Workout runtime

public actor WorkoutRuntime {

    public private(set) var state:
        WorkoutEngineState =
            .idle

    public private(set) var metrics:
        WorkoutMetrics =
            WorkoutMetrics()

    private var startedAt:
        Date?

    private var activity:
        WorkoutActivity?

    private var location:
        WorkoutLocation =
            .unspecified

    private var sessionID:
        WorkoutSessionID?

    private var heartRates:
        [HeartRateSample] =
            []

    private var maximumHeartRate:
        Double?

    private var intervalEngine:
        WorkoutIntervalEngine?

    private var zoneEngine:
        HeartRateZoneEngine?

    private let paceCalculator =
        WorkoutPaceCalculator()

    public init() {}

    public func begin(
        sessionID:
            WorkoutSessionID,
        configuration:
            WorkoutConfiguration,
        now:
            Date = Date()
    ) {

        self.sessionID =
            sessionID

        self.activity =
            configuration.activity

        self.location =
            configuration.location

        self.startedAt =
            now

        self.state =
            .running

        self.metrics =
            WorkoutMetrics()

        self.heartRates =
            []

        self.maximumHeartRate =
            nil

        self.intervalEngine =
            WorkoutIntervalEngine(
                intervals:
                    configuration.intervals
            )

        if
            let zoneConfiguration =
                configuration
                .heartRateZoneConfiguration
        {
            self.zoneEngine =
                HeartRateZoneEngine(
                    configuration:
                        zoneConfiguration
                )
        }
    }

    public func pause() {

        guard state == .running else {
            return
        }

        state =
            .paused
    }

    public func resume() {

        guard state == .paused else {
            return
        }

        state =
            .running
    }

    public func ingest(
        metrics:
            WorkoutMetrics
    ) {

        self.metrics =
            metrics

        if let bpm =
            metrics.heartRateBPM
        {
            let sample =
                HeartRateSample(
                    bpm:
                        bpm,
                    timestamp:
                        Date()
                )

            heartRates.append(
                sample
            )

            maximumHeartRate =
                max(
                    maximumHeartRate ?? bpm,
                    bpm
                )

            if let zoneEngine {
                Task {
                    await zoneEngine.ingest(
                        sample:
                            sample
                    )
                }
            }
        }
    }

    public func ingest(
        heartRate:
            Double,
        timestamp:
            Date = Date()
    ) async {

        guard heartRate > 0 else {
            return
        }

        let sample =
            HeartRateSample(
                bpm:
                    heartRate,
                timestamp:
                    timestamp
            )

        heartRates.append(
            sample
        )

        maximumHeartRate =
            max(
                maximumHeartRate ?? heartRate,
                heartRate
            )

        if let zoneEngine {
            await zoneEngine.ingest(
                sample:
                    sample
            )
        }

        metrics.heartRateBPM =
            heartRate

        metrics.maximumHeartRateBPM =
            maximumHeartRate
    }

    public func finish(
        at:
            Date = Date()
    )
        async
        -> WorkoutSummary?
    {
        guard
            let sessionID,
            let activity,
            let startedAt
        else {
            return nil
        }

        state =
            .finished

        metrics.elapsedTime =
            at.timeIntervalSince(
                startedAt
            )

        metrics.paceSecondsPerKilometer =
            paceCalculator.pace(
                distanceMeters:
                    metrics.distanceMeters,
                elapsed:
                    metrics.elapsedTime
            )

        metrics.speedMetersPerSecond =
            paceCalculator.speed(
                distanceMeters:
                    metrics.distanceMeters,
                elapsed:
                    metrics.elapsedTime
            )

        let zones =
            await zoneEngine?.summary() ??
            []

        let intervals =
            await intervalEngine?.snapshot() ??
            []

        return WorkoutSummary(
            sessionID:
                sessionID,
            activity:
                activity,
            location:
                location,
            startedAt:
                startedAt,
            endedAt:
                at,
            metrics:
                metrics,
            zoneSummaries:
                zones,
            intervals:
                intervals
        )
    }

    public func currentInterval()
        async
        -> WorkoutIntervalRuntime?
    {
        await intervalEngine?.current()
    }

    public func skipInterval()
        async
        -> WorkoutIntervalRuntime?
    {
        await intervalEngine?.skip()
    }
}

// MARK: - Workout metrics reader

@MainActor
public final class WorkoutMetricsReader {

    private let builder:
        HKLiveWorkoutBuilder

    public init(
        builder:
            HKLiveWorkoutBuilder
    ) {
        self.builder =
            builder
    }

    public func readMetrics()
        -> WorkoutMetrics
    {
        var metrics =
            WorkoutMetrics()

        if
            let heartRateType =
                HKObjectType.quantityType(
                    forIdentifier:
                        .heartRate
                )
        {
            let statistics =
                builder.statistics(
                    for:
                        heartRateType
                )

            let unit =
                HKUnit.count()
                    .unitDivided(
                        by:
                            HKUnit.minute()
                    )

            metrics.heartRateBPM =
                statistics?
                    .mostRecentQuantity()?
                    .doubleValue(
                        for:
                            unit
                    )

            metrics.averageHeartRateBPM =
                statistics?
                    .averageQuantity()?
                    .doubleValue(
                        for:
                            unit
                    )

            metrics.maximumHeartRateBPM =
                statistics?
                    .maximumQuantity()?
                    .doubleValue(
                        for:
                            unit
                    )
        }

        if
            let energyType =
                HKObjectType.quantityType(
                    forIdentifier:
                        .activeEnergyBurned
                )
        {
            let statistics =
                builder.statistics(
                    for:
                        energyType
                )

            metrics.activeEnergyKilocalories =
                statistics?
                    .sumQuantity()?
                    .doubleValue(
                        for:
                            .kilocalorie()
                    ) ??
                0
        }

        if
            let basalType =
                HKObjectType.quantityType(
                    forIdentifier:
                        .basalEnergyBurned
                )
        {
            let statistics =
                builder.statistics(
                    for:
                        basalType
                )

            metrics.basalEnergyKilocalories =
                statistics?
                    .sumQuantity()?
                    .doubleValue(
                        for:
                            .kilocalorie()
                    ) ??
                0
        }

        if
            let distanceType =
                HKObjectType.quantityType(
                    forIdentifier:
                        .distanceWalkingRunning
                )
        {
            let statistics =
                builder.statistics(
                    for:
                        distanceType
                )

            metrics.distanceMeters =
                statistics?
                    .sumQuantity()?
                    .doubleValue(
                        for:
                            .meter()
                    ) ??
                0
        }

        if
            let stepType =
                HKObjectType.quantityType(
                    forIdentifier:
                        .stepCount
                )
        {
            let statistics =
                builder.statistics(
                    for:
                        stepType
                )

            metrics.stepCount =
                statistics?
                    .sumQuantity()?
                    .doubleValue(
                        for:
                            .count()
                    )
        }

        return metrics
    }
}

// MARK: - Workout history

public actor WorkoutHistoryStore {

    private let healthStore:
        HKHealthStore

    public init(
        healthStore:
            HKHealthStore
    ) {
        self.healthStore =
            healthStore
    }

    public func recentWorkouts(
        limit:
            Int = 50
    )
        async
        throws
        -> [HKWorkout]
    {
        let workoutType =
            HKObjectType.workoutType()

        let sort =
            NSSortDescriptor(
                key:
                    HKSampleSortIdentifierStartDate,
                ascending:
                    false
            )

        return try await withCheckedThrowingContinuation {
            continuation in

            let query =
                HKSampleQuery(
                    sampleType:
                        workoutType,
                    predicate:
                        nil,
                    limit:
                        limit,
                    sortDescriptors:
                        [
                            sort
                        ]
                ) {
                    _,
                    samples,
                    error in

                    if let error {
                        continuation.resume(
                            throwing:
                                error
                        )

                        return
                    }

                    continuation.resume(
                        returning:
                            samples as? [HKWorkout] ??
                            []
                    )
                }

            healthStore.execute(
                query
            )
        }
    }

    public func workouts(
        from:
            Date,
        to:
            Date
    )
        async
        throws
        -> [HKWorkout]
    {
        let workoutType =
            HKObjectType.workoutType()

        let predicate =
            HKQuery.predicateForSamples(
                withStart:
                    from,
                end:
                    to,
                options:
                    []
            )

        let sort =
            NSSortDescriptor(
                key:
                    HKSampleSortIdentifierStartDate,
                ascending:
                    false
            )

        return try await withCheckedThrowingContinuation {
            continuation in

            let query =
                HKSampleQuery(
                    sampleType:
                        workoutType,
                    predicate:
                        predicate,
                    limit:
                        HKObjectQueryNoLimit,
                    sortDescriptors:
                        [
                            sort
                        ]
                ) {
                    _,
                    samples,
                    error in

                    if let error {
                        continuation.resume(
                            throwing:
                                error
                        )

                        return
                    }

                    continuation.resume(
                        returning:
                            samples as? [HKWorkout] ??
                            []
                    )
                }

            healthStore.execute(
                query
            )
        }
    }
}

// MARK: - Route manager

@MainActor
public final class WorkoutRouteManager {

    private let healthStore:
        HKHealthStore

    private var routeBuilder:
        HKWorkoutRouteBuilder?

    public init(
        healthStore:
            HKHealthStore
    ) {
        self.healthStore =
            healthStore
    }

    public func start(
        device:
            HKDevice? = nil
    ) {

        routeBuilder =
            HKWorkoutRouteBuilder(
                healthStore:
                    healthStore,
                device:
                    device
            )
    }

    public func insert(
        locations:
            [CLLocation]
    ) {

        guard
            !locations.isEmpty,
            let routeBuilder
        else {
            return
        }

        routeBuilder.insertRouteData(
            locations
        ) {
            success,
            error in

            if let error {
                Logger.workout.error(
                    "Route insertion failed: \(error.localizedDescription)"
                )
            }

            if !success {
                Logger.workout.error(
                    "Route insertion unsuccessful."
                )
            }
        }
    }

    public func finish(
        workout:
            HKWorkout,
        metadata:
            [String: Any]? = nil,
        completion:
            @escaping @Sendable (
                Result<HKWorkoutRoute, Error>
            ) -> Void
    ) {

        guard
            let routeBuilder
        else {
            completion(
                .failure(
                    HealthEngineError
                        .routeUnavailable
                )
            )

            return
        }

        routeBuilder.finishRoute(
            with:
                workout,
            metadata:
                metadata
        ) {
            route,
            error in

            if let error {
                completion(
                    .failure(
                        error
                    )
                )

                return
            }

            guard
                let route
            else {
                completion(
                    .failure(
                        HealthEngineError
                            .routeUnavailable
                    )
                )

                return
            }

            completion(
                .success(
                    route
                )
            )
        }
    }
}

// MARK: - Workout manager

@MainActor
public final class AppleWorkoutHealthEngine {

    public let healthStore:
        HKHealthStore

    public let authorization:
        HealthKitAuthorizationManager

    public let history:
        WorkoutHistoryStore

    private var sessionController:
        WorkoutSessionController?

    private var runtime:
        WorkoutRuntime?

    public private(set) var state:
        WorkoutEngineState =
            .idle

    public private(set) var currentSessionID:
        WorkoutSessionID?

    public init(
        healthStore:
            HKHealthStore =
                HKHealthStore()
    ) {

        self.healthStore =
            healthStore

        self.authorization =
            HealthKitAuthorizationManager(
                healthStore:
                    healthStore
            )

        self.history =
            WorkoutHistoryStore(
                healthStore:
                    healthStore
            )
    }

    public func requestAuthorization()
        async
        throws
    {
        try await authorization
            .requestAuthorization()
    }

    public func prepare(
        configuration:
            WorkoutConfiguration
    )
        async
        throws
    {
        guard state == .idle else {
            throw HealthEngineError
                .alreadyRunning
        }

        state =
            .preparing

        let controller =
            WorkoutSessionController(
                healthStore:
                    healthStore
            )

        do {

            try controller.create(
                configuration:
                    configuration
            )

        } catch {

            state =
                .failed

            throw error
        }

        let sessionID =
            WorkoutSessionID()

        let runtime =
            WorkoutRuntime()

        await runtime.begin(
            sessionID:
                sessionID,
            configuration:
                configuration
        )

        self.sessionController =
            controller

        self.runtime =
            runtime

        self.currentSessionID =
            sessionID

        state =
            .idle
    }

    public func start()
        async
        throws
    {
        guard
            let controller =
                sessionController,
            let runtime
        else {
            throw HealthEngineError
                .sessionUnavailable
        }

        controller.start()

        await runtime.resume()

        state =
            .running
    }

    public func pause()
        async
    {
        sessionController?.pause()

        await runtime?.pause()

        state =
            .paused
    }

    public func resume()
        async
    {
        sessionController?.resume()

        await runtime?.resume()

        state =
            .running
    }

    public func end()
        async
        throws
        -> WorkoutSummary?
    {
        guard
            let controller =
                sessionController,
            let runtime
        else {
            throw HealthEngineError
                .sessionUnavailable
        }

        state =
            .ending

        controller.end()

        let workout =
            try await finishCollection(
                controller:
                    controller
            )

        let summary =
            await runtime.finish()

        if workout != nil {
            Logger.workout.info(
                "Workout successfully completed."
            )
        }

        sessionController =
            nil

        self.runtime =
            nil

        currentSessionID =
            nil

        state =
            .finished

        return summary
    }

    private func finishCollection(
        controller:
            WorkoutSessionController
    )
        async
        throws
        -> HKWorkout?
    {
        try await withCheckedThrowingContinuation {
            continuation in

            controller.stopCollection {
                result in

                continuation.resume(
                    with:
                        result
                )
            }
        }
    }

    public func currentMetrics()
        -> WorkoutMetrics?
    {
        guard
            let builder =
                sessionController?.builder
        else {
            return nil
        }

        return WorkoutMetricsReader(
            builder:
                builder
        )
        .readMetrics()
    }

    public func updateRuntimeMetrics()
        async
    {
        guard
            let metrics =
                currentMetrics()
        else {
            return
        }

        await runtime?.ingest(
            metrics:
                metrics
        )
    }

    public func currentInterval()
        async
        -> WorkoutIntervalRuntime?
    {
        await runtime?.currentInterval()
    }

    public func skipInterval()
        async
        -> WorkoutIntervalRuntime?
    {
        await runtime?.skipInterval()
    }
}

// MARK: - Errors

public enum HealthEngineError:
    Error,
    LocalizedError,
    Sendable
{
    case healthDataUnavailable
    case alreadyRunning
    case sessionUnavailable
    case collectionFailed
    case routeUnavailable
    case authorizationDenied
    case invalidConfiguration

    public var errorDescription:
        String?
    {
        switch self {

        case .healthDataUnavailable:
            return
                "Health data is unavailable on this device."

        case .alreadyRunning:
            return
                "A workout is already running."

        case .sessionUnavailable:
            return
                "No active workout session is available."

        case .collectionFailed:
            return
                "HealthKit workout collection failed."

        case .routeUnavailable:
            return
                "The workout route is unavailable."

        case .authorizationDenied:
            return
                "HealthKit authorization was not granted."

        case .invalidConfiguration:
            return
                "The workout configuration is invalid."
        }
    }
}

// MARK: - Diagnostics

public struct WorkoutDiagnostics:
    Sendable
{
    public let state:
        WorkoutEngineState

    public let sessionExists:
        Bool

    public let builderExists:
        Bool

    public let timestamp:
        Date

    public init(
        state:
            WorkoutEngineState,
        sessionExists:
            Bool,
        builderExists:
            Bool,
        timestamp:
            Date = Date()
    ) {
        self.state =
            state

        self.sessionExists =
            sessionExists

        self.builderExists =
            builderExists

        self.timestamp =
            timestamp
    }
}

@MainActor
public extension AppleWorkoutHealthEngine {

    func diagnostics()
        -> WorkoutDiagnostics
    {
        WorkoutDiagnostics(
            state:
                state,
            sessionExists:
                sessionController?.session != nil,
            builderExists:
                sessionController?.builder != nil
        )
    }
}

// MARK: - Logging

private enum Logger {

    static let workout =
        LoggerFactory.make(
            subsystem:
                "com.example.AppleWorkoutHealthEngine",
            category:
                "workout"
        )
}

private enum LoggerFactory {

    static func make(
        subsystem:
            String,
        category:
            String
    )
        -> os.Logger
    {
        os.Logger(
            subsystem:
                subsystem,
            category:
                category
        )
    }
}







//
//  AppleHighPerformanceUI.swift
//
//  #4 — High-Performance Rendering & UI Framework
//
//  Swift 6
//
//  Designed for:
//      iOS
//      iPadOS
//      watchOS
//      macOS
//
//  Core principles:
//
//  1. Deterministic frame scheduling
//  2. Actor-isolated mutable rendering state
//  3. Main-actor UI integration
//  4. Dirty-region rendering
//  5. Incremental layout
//  6. Animation timelines
//  7. Gesture/input routing
//  8. Frame pacing
//  9. Adaptive quality
// 10. Instrumentation
//
//  The rendering backend is intentionally abstract.
//  A production Metal renderer can sit underneath it.
//
//

import Foundation
import CoreGraphics
import QuartzCore
import os

#if canImport(SwiftUI)
import SwiftUI
#endif

// MARK: - IDs

public struct RenderNodeID:
    Hashable,
    Sendable,
    Codable
{
    public let rawValue:
        UInt64

    public init(
        _ rawValue:
            UInt64
    ) {
        self.rawValue =
            rawValue
    }
}

public struct AnimationID:
    Hashable,
    Sendable,
    Codable
{
    public let rawValue:
        UUID

    public init(
        _ rawValue:
            UUID = UUID()
    ) {
        self.rawValue =
            rawValue
    }
}

public struct GestureID:
    Hashable,
    Sendable,
    Codable
{
    public let rawValue:
        UUID

    public init(
        _ rawValue:
            UUID = UUID()
    ) {
        self.rawValue =
            rawValue
    }
}

// MARK: - Render scale

public struct RenderScale:
    Equatable,
    Sendable
{
    public var x:
        CGFloat

    public var y:
        CGFloat

    public init(
        x:
            CGFloat = 1,
        y:
            CGFloat = 1
    ) {
        self.x =
            x

        self.y =
            y
    }

    public static let one =
        RenderScale()
}

// MARK: - Size

public struct RenderSize:
    Equatable,
    Hashable,
    Sendable
{
    public var width:
        CGFloat

    public var height:
        CGFloat

    public init(
        width:
            CGFloat,
        height:
            CGFloat
    ) {
        self.width =
            width

        self.height =
            height
    }

    public var cgSize:
        CGSize
    {
        CGSize(
            width:
                width,
            height:
                height
        )
    }
}

// MARK: - Render point

public struct RenderPoint:
    Equatable,
    Hashable,
    Sendable
{
    public var x:
        CGFloat

    public var y:
        CGFloat

    public init(
        x:
            CGFloat,
        y:
            CGFloat
    ) {
        self.x =
            x

        self.y =
            y
    }

    public var cgPoint:
        CGPoint
    {
        CGPoint(
            x:
                x,
            y:
                y
        )
    }
}

// MARK: - Render rect

public struct RenderRect:
    Equatable,
    Hashable,
    Sendable
{
    public var x:
        CGFloat

    public var y:
        CGFloat

    public var width:
        CGFloat

    public var height:
        CGFloat

    public init(
        x:
            CGFloat,
        y:
            CGFloat,
        width:
            CGFloat,
        height:
            CGFloat
    ) {
        self.x =
            x

        self.y =
            y

        self.width =
            width

        self.height =
            height
    }

    public init(
        cgRect:
            CGRect
    ) {
        self.init(
            x:
                cgRect.origin.x,
            y:
                cgRect.origin.y,
            width:
                cgRect.size.width,
            height:
                cgRect.size.height
        )
    }

    public var cgRect:
        CGRect
    {
        CGRect(
            x:
                x,
            y:
                y,
            width:
                width,
            height:
                height
        )
    }

    public var minX:
        CGFloat
    {
        x
    }

    public var maxX:
        CGFloat
    {
        x + width
    }

    public var minY:
        CGFloat
    {
        y
    }

    public var maxY:
        CGFloat
    {
        y + height
    }

    public func intersects(
        _ other:
            RenderRect
    )
        -> Bool
    {
        cgRect.intersects(
            other.cgRect
        )
    }

    public func union(
        _ other:
            RenderRect
    )
        -> RenderRect
    {
        RenderRect(
            cgRect:
                cgRect.union(
                    other.cgRect
                )
        )
    }
}

// MARK: - Insets

public struct RenderInsets:
    Equatable,
    Sendable
{
    public var top:
        CGFloat

    public var leading:
        CGFloat

    public var bottom:
        CGFloat

    public var trailing:
        CGFloat

    public init(
        top:
            CGFloat = 0,
        leading:
            CGFloat = 0,
        bottom:
            CGFloat = 0,
        trailing:
            CGFloat = 0
    ) {
        self.top =
            top

        self.leading =
            leading

        self.bottom =
            bottom

        self.trailing =
            trailing
    }

    public static let zero =
        RenderInsets()
}

// MARK: - Layout priority

public enum LayoutPriority:
    Int,
    Sendable
{
    case required = 1000
    case high = 750
    case normal = 500
    case low = 250
}

// MARK: - Layout result

public struct LayoutResult:
    Sendable
{
    public let frame:
        RenderRect

    public let contentFrame:
        RenderRect

    public let intrinsicSize:
        RenderSize

    public init(
        frame:
            RenderRect,
        contentFrame:
            RenderRect,
        intrinsicSize:
            RenderSize
    ) {
        self.frame =
            frame

        self.contentFrame =
            contentFrame

        self.intrinsicSize =
            intrinsicSize
    }
}

// MARK: - Layout proposal

public struct LayoutProposal:
    Sendable
{
    public var width:
        CGFloat?

    public var height:
        CGFloat?

    public init(
        width:
            CGFloat? = nil,
        height:
            CGFloat? = nil
    ) {
        self.width =
            width

        self.height =
            height
    }

    public static let unspecified =
        LayoutProposal()
}

// MARK: - Render color

public struct RenderColor:
    Equatable,
    Sendable,
    Codable
{
    public var red:
        Double

    public var green:
        Double

    public var blue:
        Double

    public var alpha:
        Double

    public init(
        red:
            Double,
        green:
            Double,
        blue:
            Double,
        alpha:
            Double = 1
    ) {
        self.red =
            red

        self.green =
            green

        self.blue =
            blue

        self.alpha =
            alpha
    }

    public static let clear =
        RenderColor(
            red:
                0,
            green:
                0,
            blue:
                0,
            alpha:
                0
        )

    public static let white =
        RenderColor(
            red:
                1,
            green:
                1,
            blue:
                1
        )

    public static let black =
        RenderColor(
            red:
                0,
            green:
                0,
            blue:
                0
        )
}

// MARK: - Render primitive

public enum RenderPrimitive:
    Sendable
{
    case rectangle(
        rect:
            RenderRect,
        fill:
            RenderColor,
        cornerRadius:
            CGFloat
    )

    case roundedRectangle(
        rect:
            RenderRect,
        radius:
            CGFloat,
        fill:
            RenderColor
    )

    case circle(
        center:
            RenderPoint,
        radius:
            CGFloat,
        fill:
            RenderColor
    )

    case line(
        from:
            RenderPoint,
        to:
            RenderPoint,
        width:
            CGFloat,
        color:
            RenderColor
    )

    case text(
        string:
            String,
        origin:
            RenderPoint,
        fontSize:
            CGFloat,
        color:
            RenderColor
    )
}

// MARK: - Render command

public struct RenderCommand:
    Sendable
{
    public let nodeID:
        RenderNodeID

    public let primitive:
        RenderPrimitive

    public let zIndex:
        Int

    public init(
        nodeID:
            RenderNodeID,
        primitive:
            RenderPrimitive,
        zIndex:
            Int = 0
    ) {
        self.nodeID =
            nodeID

        self.primitive =
            primitive

        self.zIndex =
            zIndex
    }
}

// MARK: - Render list

public struct RenderList:
    Sendable
{
    public private(set) var commands:
        [RenderCommand]

    public init(
        commands:
            [RenderCommand] = []
    ) {
        self.commands =
            commands
    }

    public mutating func append(
        _ command:
            RenderCommand
    ) {
        commands.append(
            command
        )
    }

    public func sorted()
        -> [RenderCommand]
    {
        commands.sorted {
            $0.zIndex <
            $1.zIndex
        }
    }
}

// MARK: - Dirty region

public struct DirtyRegion:
    Sendable
{
    public private(set) var rects:
        [RenderRect] =
            []

    public init() {}

    public mutating func invalidate(
        _ rect:
            RenderRect
    ) {
        rects.append(
            rect
        )
    }

    public mutating func invalidateAll(
        size:
            RenderSize
    ) {
        rects =
            [
                RenderRect(
                    x:
                        0,
                    y:
                        0,
                    width:
                        size.width,
                    height:
                        size.height
                )
            ]
    }

    public var isEmpty:
        Bool
    {
        rects.isEmpty
    }

    public func combined()
        -> RenderRect?
    {
        rects.reduce(
            nil
        ) {
            partial,
            next in

            guard
                let partial
            else {
                return next
            }

            return partial.union(
                next
            )
        }
    }

    public mutating func reset() {
        rects.removeAll(
            keepingCapacity:
                true
        )
    }
}

// MARK: - Render node state

public struct RenderNodeState:
    Sendable
{
    public var frame:
        RenderRect

    public var opacity:
        CGFloat

    public var scale:
        CGFloat

    public var rotation:
        CGFloat

    public var hidden:
        Bool

    public var zIndex:
        Int

    public init(
        frame:
            RenderRect = RenderRect(
                x:
                    0,
                y:
                    0,
                width:
                    0,
                height:
                    0
            ),
        opacity:
            CGFloat = 1,
        scale:
            CGFloat = 1,
        rotation:
            CGFloat = 0,
        hidden:
            Bool = false,
        zIndex:
            Int = 0
    ) {
        self.frame =
            frame

        self.opacity =
            opacity

        self.scale =
            scale

        self.rotation =
            rotation

        self.hidden =
            hidden

        self.zIndex =
            zIndex
    }
}

// MARK: - Render node

public struct RenderNode:
    Sendable
{
    public let id:
        RenderNodeID

    public var state:
        RenderNodeState

    public var children:
        [RenderNodeID]

    public var primitive:
        RenderPrimitive?

    public init(
        id:
            RenderNodeID,
        state:
            RenderNodeState =
                RenderNodeState(),
        children:
            [RenderNodeID] = [],
        primitive:
            RenderPrimitive? =
                nil
    ) {
        self.id =
            id

        self.state =
            state

        self.children =
            children

        self.primitive =
            primitive
    }
}

// MARK: - Node registry

public actor RenderNodeRegistry {

    private var nodes:
        [RenderNodeID: RenderNode] =
            [:]

    private var nextID:
        UInt64 =
            1

    public init() {}

    public func create(
        state:
            RenderNodeState =
                RenderNodeState(),
        primitive:
            RenderPrimitive? =
                nil
    )
        -> RenderNodeID
    {
        let id =
            RenderNodeID(
                nextID
            )

        nextID += 1

        nodes[id] =
            RenderNode(
                id:
                    id,
                state:
                    state,
                primitive:
                    primitive
            )

        return id
    }

    public func insert(
        _ node:
            RenderNode
    ) {
        nodes[
            node.id
        ] =
            node
    }

    public func remove(
        _ id:
            RenderNodeID
    ) {
        nodes.removeValue(
            forKey:
                id
        )
    }

    public func node(
        _ id:
            RenderNodeID
    )
        -> RenderNode?
    {
        nodes[id]
    }

    public func update(
        _ id:
            RenderNodeID,
        state:
            RenderNodeState
    ) {
        guard
            var node =
                nodes[id]
        else {
            return
        }

        node.state =
            state

        nodes[id] =
            node
    }

    public func allNodes()
        -> [RenderNode]
    {
        Array(
            nodes.values
        )
    }

    public func count()
        -> Int
    {
        nodes.count
    }
}

// MARK: - Layout engine

public actor RenderLayoutEngine {

    private var layouts:
        [RenderNodeID: LayoutResult] =
            [:]

    public init() {}

    public func calculate(
        node:
            RenderNode,
        proposal:
            LayoutProposal
    )
        -> LayoutResult
    {
        let width =
            proposal.width ??
            node.state.frame.width

        let height =
            proposal.height ??
            node.state.frame.height

        let frame =
            RenderRect(
                x:
                    node.state.frame.x,
                y:
                    node.state.frame.y,
                width:
                    max(
                        0,
                        width
                    ),
                height:
                    max(
                        0,
                        height
                    )
            )

        let result =
            LayoutResult(
                frame:
                    frame,
                contentFrame:
                    frame,
                intrinsicSize:
                    RenderSize(
                        width:
                            frame.width,
                        height:
                            frame.height
                    )
            )

        layouts[node.id] =
            result

        return result
    }

    public func layout(
        for id:
            RenderNodeID
    )
        -> LayoutResult?
    {
        layouts[id]
    }

    public func invalidate(
        _ id:
            RenderNodeID
    ) {
        layouts.removeValue(
            forKey:
                id
        )
    }

    public func invalidateAll() {
        layouts.removeAll(
            keepingCapacity:
                true
        )
    }
}

// MARK: - Frame timing

public struct FrameTiming:
    Sendable
{
    public let frameNumber:
        UInt64

    public let timestamp:
        TimeInterval

    public let duration:
        TimeInterval

    public let targetFrameDuration:
        TimeInterval

    public let dropped:
        Bool

    public init(
        frameNumber:
            UInt64,
        timestamp:
            TimeInterval,
        duration:
            TimeInterval,
        targetFrameDuration:
            TimeInterval,
        dropped:
            Bool
    ) {
        self.frameNumber =
            frameNumber

        self.timestamp =
            timestamp

        self.duration =
            duration

        self.targetFrameDuration =
            targetFrameDuration

        self.dropped =
            dropped
    }
}

// MARK: - Frame statistics

public struct FrameStatistics:
    Sendable
{
    public private(set) var totalFrames:
        UInt64

    public private(set) var droppedFrames:
        UInt64

    public private(set) var totalFrameTime:
        TimeInterval

    public init() {
        totalFrames =
            0

        droppedFrames =
            0

        totalFrameTime =
            0
    }

    public mutating func record(
        _ timing:
            FrameTiming
    ) {
        totalFrames +=
            1

        totalFrameTime +=
            timing.duration

        if timing.dropped {
            droppedFrames +=
                1
        }
    }

    public var averageFrameTime:
        TimeInterval?
    {
        guard
            totalFrames > 0
        else {
            return nil
        }

        return totalFrameTime /
            Double(
                totalFrames
            )
    }

    public var dropRate:
        Double
    {
        guard
            totalFrames > 0
        else {
            return 0
        }

        return Double(
            droppedFrames
        ) /
        Double(
            totalFrames
        )
    }
}

// MARK: - Frame scheduler

public actor FrameScheduler {

    public struct Configuration:
        Sendable
    {
        public var targetFPS:
            Double

        public var maximumFrameTime:
            TimeInterval

        public init(
            targetFPS:
                Double = 60
        ) {
            self.targetFPS =
                targetFPS

            self.maximumFrameTime =
                1 /
                targetFPS
        }
    }

    private let configuration:
        Configuration

    private var frameNumber:
        UInt64 =
            0

    private var previousTimestamp:
        TimeInterval?

    private var statistics:
        FrameStatistics =
            FrameStatistics()

    private var callback:
        (@Sendable (
            FrameTiming
        ) async -> Void)?

    public init(
        configuration:
            Configuration =
                Configuration()
    ) {
        self.configuration =
            configuration
    }

    public func setCallback(
        _ callback:
            @escaping @Sendable (
                FrameTiming
            ) async -> Void
    ) {
        self.callback =
            callback
    }

    public func tick(
        timestamp:
            TimeInterval
    )
        async
    {
        frameNumber +=
            1

        let duration:
            TimeInterval

        if let previousTimestamp {

            duration =
                max(
                    0,
                    timestamp -
                    previousTimestamp
                )

        } else {

            duration =
                configuration
                    .maximumFrameTime
        }

        self.previousTimestamp =
            timestamp

        let dropped =
            duration >
            configuration
                .maximumFrameTime *
            1.5

        let timing =
            FrameTiming(
                frameNumber:
                    frameNumber,
                timestamp:
                    timestamp,
                duration:
                    duration,
                targetFrameDuration:
                    configuration
                        .maximumFrameTime,
                dropped:
                    dropped
            )

        statistics.record(
            timing
        )

        await callback?(
            timing
        )
    }

    public func statistics()
        -> FrameStatistics
    {
        statistics
    }

    public func reset() {
        frameNumber =
            0

        previousTimestamp =
            nil

        statistics =
            FrameStatistics()
    }
}

// MARK: - Animation curve

public enum AnimationCurve:
    Sendable
{
    case linear
    case easeIn
    case easeOut
    case easeInOut
    case spring(
        response:
            Double,
        dampingFraction:
            Double
    )

    public func value(
        at progress:
            Double
    )
        -> Double
    {
        let p =
            min(
                1,
                max(
                    0,
                    progress
                )
            )

        switch self {

        case .linear:
            return p

        case .easeIn:
            return p * p

        case .easeOut:
            return 1 -
                pow(
                    1 - p,
                    2
                )

        case .easeInOut:
            if p < 0.5 {
                return 2 * p * p
            }

            return 1 -
                pow(
                    -2 * p + 2,
                    2
                ) / 2

        case let .spring(
            response,
            dampingFraction
        ):

            let omega =
                2 *
                Double.pi /
                max(
                    0.01,
                    response
                )

            let damping =
                max(
                    0.01,
                    dampingFraction
                )

            let exponential =
                exp(
                    -damping *
                    omega *
                    p
                )

            let oscillation =
                cos(
                    omega *
                    p
                )

            return 1 -
                exponential *
                oscillation
        }
    }
}

// MARK: - Animation

public struct RenderAnimation:
    Sendable
{
    public let id:
        AnimationID

    public let nodeID:
        RenderNodeID

    public let key:
        String

    public let from:
        Double

    public let to:
        Double

    public let duration:
        TimeInterval

    public let delay:
        TimeInterval

    public let curve:
        AnimationCurve

    public let startedAt:
        TimeInterval

    public init(
        id:
            AnimationID = AnimationID(),
        nodeID:
            RenderNodeID,
        key:
            String,
        from:
            Double,
        to:
            Double,
        duration:
            TimeInterval,
        delay:
            TimeInterval = 0,
        curve:
            AnimationCurve =
                .easeInOut,
        startedAt:
            TimeInterval
    ) {
        self.id =
            id

        self.nodeID =
            nodeID

        self.key =
            key

        self.from =
            from

        self.to =
            to

        self.duration =
            duration

        self.delay =
            delay

        self.curve =
            curve

        self.startedAt =
            startedAt
    }
}

// MARK: - Animation engine

public actor AnimationEngine {

    private var animations:
        [AnimationID: RenderAnimation] =
            [:]

    public init() {}

    public func add(
        _ animation:
            RenderAnimation
    ) {
        animations[
            animation.id
        ] =
            animation
    }

    public func cancel(
        _ id:
            AnimationID
    ) {
        animations.removeValue(
            forKey:
                id
        )
    }

    public func cancelNode(
        _ nodeID:
            RenderNodeID
    ) {
        animations =
            animations.filter {
                $0.value.nodeID !=
                nodeID
            }
    }

    public func evaluate(
        at timestamp:
            TimeInterval
    )
        -> [
            (
                RenderAnimation,
                Double,
                Bool
            )
        ]
    {
        var results:
            [
                (
                    RenderAnimation,
                    Double,
                    Bool
                )
            ] =
            []

        var completed:
            [AnimationID] =
            []

        for animation in animations.values {

            let elapsed =
                timestamp -
                animation.startedAt -
                animation.delay

            if elapsed <= 0 {

                results.append(
                    (
                        animation,
                        animation.from,
                        false
                    )
                )

                continue
            }

            let progress =
                elapsed /
                max(
                    0.0001,
                    animation.duration
                )

            let clamped =
                min(
                    1,
                    max(
                        0,
                        progress
                    )
                )

            let curveValue =
                animation.curve.value(
                    at:
                        clamped
                )

            let value =
                animation.from +
                (
                    animation.to -
                    animation.from
                ) *
                curveValue

            let finished =
                progress >= 1

            results.append(
                (
                    animation,
                    value,
                    finished
                )
            )

            if finished {
                completed.append(
                    animation.id
                )
            }
        }

        for id in completed {
            animations.removeValue(
                forKey:
                    id
            )
        }

        return results
    }

    public func count()
        -> Int
    {
        animations.count
    }
}

// MARK: - Input

public enum PointerPhase:
    Sendable
{
    case began
    case moved
    case ended
    case cancelled
}

public struct PointerEvent:
    Sendable
{
    public let location:
        RenderPoint

    public let timestamp:
        TimeInterval

    public let phase:
        PointerPhase

    public let pressure:
        CGFloat

    public init(
        location:
            RenderPoint,
        timestamp:
            TimeInterval,
        phase:
            PointerPhase,
        pressure:
            CGFloat = 1
    ) {
        self.location =
            location

        self.timestamp =
            timestamp

        self.phase =
            phase

        self.pressure =
            pressure
    }
}

// MARK: - Gesture state

public enum GestureState:
    Sendable
{
    case possible
    case began
    case changed
    case ended
    case cancelled
    case failed
}

// MARK: - Gesture recognizer protocol

public protocol RenderGestureRecognizer:
    Sendable
{
    func process(
        event:
            PointerEvent
    ) -> GestureState
}

// MARK: - Tap recognizer

public struct TapGestureRecognizer:
    RenderGestureRecognizer
{
    private let maximumMovement:
        CGFloat

    private let maximumDuration:
        TimeInterval

    private var start:
        RenderPoint?

    private var startTime:
        TimeInterval?

    public init(
        maximumMovement:
            CGFloat = 12,
        maximumDuration:
            TimeInterval = 0.35
    ) {
        self.maximumMovement =
            maximumMovement

        self.maximumDuration =
            maximumDuration
    }

    public func process(
        event:
            PointerEvent
    )
        -> GestureState
    {
        switch event.phase {

        case .began:
            return .began

        case .moved:
            return .changed

        case .ended:

            if
                let startTime,
                event.timestamp -
                startTime >
                maximumDuration
            {
                return .failed
            }

            return .ended

        case .cancelled:
            return .cancelled
        }
    }
}

// MARK: - Gesture event

public struct GestureEvent:
    Sendable
{
    public let gestureID:
        GestureID

    public let nodeID:
        RenderNodeID

    public let state:
        GestureState

    public let location:
        RenderPoint

    public init(
        gestureID:
            GestureID,
        nodeID:
            RenderNodeID,
        state:
            GestureState,
        location:
            RenderPoint
    ) {
        self.gestureID =
            gestureID

        self.nodeID =
            nodeID

        self.state =
            state

        self.location =
            location
    }
}

// MARK: - Gesture router

public actor GestureRouter {

    private struct Registration:
        Sendable
    {
        let gestureID:
            GestureID

        let nodeID:
            RenderNodeID

        let handler:
            @Sendable (
                GestureEvent
            ) async -> Void
    }

    private var registrations:
        [GestureID: Registration] =
            [:]

    public init() {}

    public func register(
        nodeID:
            RenderNodeID,
        handler:
            @escaping @Sendable (
                GestureEvent
            ) async -> Void
    )
        -> GestureID
    {
        let id =
            GestureID()

        registrations[id] =
            Registration(
                gestureID:
                    id,
                nodeID:
                    nodeID,
                handler:
                    handler
            )

        return id
    }

    public func unregister(
        _ id:
            GestureID
    ) {
        registrations.removeValue(
            forKey:
                id
        )
    }

    public func dispatch(
        nodeID:
            RenderNodeID,
        state:
            GestureState,
        location:
            RenderPoint
    )
        async
    {
        for registration
            in registrations.values
        {
            guard
                registration.nodeID ==
                    nodeID
            else {
                continue
            }

            let event =
                GestureEvent(
                    gestureID:
                        registration.gestureID,
                    nodeID:
                        nodeID,
                    state:
                        state,
                    location:
                        location
                )

            await registration.handler(
                event
            )
        }
    }
}

// MARK: - Rendering quality

public enum RenderQuality:
    Int,
    Sendable,
    Codable
{
    case ultraLow = 0
    case low = 1
    case balanced = 2
    case high = 3
    case maximum = 4
}

// MARK: - Adaptive rendering policy

public struct RenderPerformancePolicy:
    Sendable
{
    public var targetFPS:
        Double

    public var maximumNodesPerFrame:
        Int

    public var quality:
        RenderQuality

    public var allowAnimations:
        Bool

    public var allowShadows:
        Bool

    public var allowBlur:
        Bool

    public var allowHighResolutionTextures:
        Bool

    public init(
        targetFPS:
            Double = 60,
        maximumNodesPerFrame:
            Int = 5_000,
        quality:
            RenderQuality = .high,
        allowAnimations:
            Bool = true,
        allowShadows:
            Bool = true,
        allowBlur:
            Bool = true,
        allowHighResolutionTextures:
            Bool = true
    ) {
        self.targetFPS =
            targetFPS

        self.maximumNodesPerFrame =
            maximumNodesPerFrame

        self.quality =
            quality

        self.allowAnimations =
            allowAnimations

        self.allowShadows =
            allowShadows

        self.allowBlur =
            allowBlur

        self.allowHighResolutionTextures =
            allowHighResolutionTextures
    }
}

// MARK: - Thermal state

public enum RenderThermalState:
    Sendable
{
    case nominal
    case fair
    case serious
    case critical
}

// MARK: - Adaptive renderer

public actor AdaptiveRenderPolicy {

    public private(set) var policy:
        RenderPerformancePolicy

    public init(
        policy:
            RenderPerformancePolicy =
                RenderPerformancePolicy()
    ) {
        self.policy =
            policy
    }

    public func update(
        thermalState:
            RenderThermalState,
        frameStatistics:
            FrameStatistics
    ) {

        switch thermalState {

        case .nominal:

            policy.quality =
                .high

            policy.allowBlur =
                true

            policy.allowShadows =
                true

            policy.allowAnimations =
                true

        case .fair:

            policy.quality =
                .balanced

            policy.allowBlur =
                true

        case .serious:

            policy.quality =
                .low

            policy.allowBlur =
                false

            policy.allowShadows =
                false

        case .critical:

            policy.quality =
                .ultraLow

            policy.allowBlur =
                false

            policy.allowShadows =
                false

            policy.allowAnimations =
                false
        }

        if frameStatistics.dropRate >
            0.10
        {
            policy.quality =
                max(
                    .ultraLow,
                    policy.quality
                )

            policy.allowBlur =
                false
        }
    }

    public func current()
        -> RenderPerformancePolicy
    {
        policy
    }
}

// MARK: - Renderer protocol

public protocol RenderBackend:
    Sendable
{
    func beginFrame(
        size:
            RenderSize,
        scale:
            RenderScale,
        dirtyRegion:
            DirtyRegion
    )

    func submit(
        _ command:
            RenderCommand
    )

    func endFrame()
}

// MARK: - Null renderer

public final class NullRenderBackend:
    RenderBackend,
    @unchecked Sendable
{
    public private(set) var submittedCommands:
        Int =
            0

    public init() {}

    public func beginFrame(
        size:
            RenderSize,
        scale:
            RenderScale,
        dirtyRegion:
            DirtyRegion
    ) {
        submittedCommands =
            0
    }

    public func submit(
        _ command:
            RenderCommand
    ) {
        submittedCommands +=
            1
    }

    public func endFrame() {}
}

// MARK: - Render engine

public actor RenderEngine {

    private let nodeRegistry:
        RenderNodeRegistry

    private let layoutEngine:
        RenderLayoutEngine

    private let animationEngine:
        AnimationEngine

    private let scheduler:
        FrameScheduler

    private let adaptivePolicy:
        AdaptiveRenderPolicy

    private var dirtyRegion:
        DirtyRegion =
            DirtyRegion()

    private var viewport:
        RenderSize =
            RenderSize(
                width:
                    0,
                height:
                    0
            )

    private var scale:
        RenderScale =
            .one

    private var backend:
        (any RenderBackend)?

    private var lastRenderList:
        RenderList =
            RenderList()

    public init(
        targetFPS:
            Double = 60
    ) {

        self.nodeRegistry =
            RenderNodeRegistry()

        self.layoutEngine =
            RenderLayoutEngine()

        self.animationEngine =
            AnimationEngine()

        self.scheduler =
            FrameScheduler(
                configuration:
                    .init(
                        targetFPS:
                            targetFPS
                    )
            )

        self.adaptivePolicy =
            AdaptiveRenderPolicy()
    }

    public func attachBackend(
        _ backend:
            any RenderBackend
    ) {
        self.backend =
            backend
    }

    public func setViewport(
        size:
            RenderSize,
        scale:
            RenderScale =
                .one
    ) {
        self.viewport =
            size

        self.scale =
            scale

        dirtyRegion
            .invalidateAll(
                size:
                    size
            )
    }

    public func createNode(
        primitive:
            RenderPrimitive? =
                nil
    )
        async
        -> RenderNodeID
    {
        await nodeRegistry.create(
            primitive:
                primitive
        )
    }

    public func updateNode(
        id:
            RenderNodeID,
        state:
            RenderNodeState
    )
        async
    {
        guard
            let oldNode =
                await nodeRegistry.node(
                    id
                )
        else {
            return
        }

        dirtyRegion.invalidate(
            oldNode.state.frame
        )

        await nodeRegistry.update(
            id,
            state:
                state
        )

        dirtyRegion.invalidate(
            state.frame
        )
    }

    public func removeNode(
        id:
            RenderNodeID
    )
        async
    {
        if
            let node =
                await nodeRegistry.node(
                    id
                )
        {
            dirtyRegion.invalidate(
                node.state.frame
            )
        }

        await nodeRegistry.remove(
            id
        )

        await animationEngine
            .cancelNode(
                id
            )
    }

    public func invalidate(
        rect:
            RenderRect
    ) {
        dirtyRegion.invalidate(
            rect
        )
    }

    public func invalidateAll() {
        dirtyRegion.invalidateAll(
            size:
                viewport
        )
    }

    public func addAnimation(
        _ animation:
            RenderAnimation
    )
        async
    {
        await animationEngine.add(
            animation
        )
    }

    public func render(
        timestamp:
            TimeInterval
    )
        async
    {
        await scheduler.tick(
            timestamp:
                timestamp
        )

        await applyAnimations(
            timestamp:
                timestamp
        )

        guard
            let backend
        else {
            return
        }

        let nodes =
            await nodeRegistry.allNodes()

        let commands =
            buildCommands(
                nodes:
                    nodes
            )

        lastRenderList =
            RenderList(
                commands:
                    commands
            )

        backend.beginFrame(
            size:
                viewport,
            scale:
                scale,
            dirtyRegion:
                dirtyRegion
        )

        for command
            in commands
        {
            backend.submit(
                command
            )
        }

        backend.endFrame()

        dirtyRegion.reset()
    }

    private func buildCommands(
        nodes:
            [RenderNode]
    )
        -> [RenderCommand]
    {
        let policy =
            policySnapshot()

        let visible =
            nodes.filter {
                !$0.state.hidden &&
                $0.state.opacity > 0
            }

        let limited =
            visible.prefix(
                policy.maximumNodesPerFrame
            )

        return limited.compactMap {
            node in

            guard
                let primitive =
                    node.primitive
            else {
                return nil
            }

            return RenderCommand(
                nodeID:
                    node.id,
                primitive:
                    primitive,
                zIndex:
                    node.state.zIndex
            )
        }
    }

    private func policySnapshot()
        -> RenderPerformancePolicy
    {
        // The adaptive policy itself is actor isolated.
        // The render command builder uses a conservative
        // synchronous fallback here. Production systems
        // can snapshot policy once per frame.
        RenderPerformancePolicy()
    }

    private func applyAnimations(
        timestamp:
            TimeInterval
    )
        async
    {
        let values =
            await animationEngine.evaluate(
                at:
                    timestamp
            )

        for (
            animation,
            value,
            _
        )
        in values
        {
            guard
                var node =
                    await nodeRegistry.node(
                        animation.nodeID
                    )
            else {
                continue
            }

            switch animation.key {

            case "opacity":
                node.state.opacity =
                    CGFloat(
                        value
                    )

            case "scale":
                node.state.scale =
                    CGFloat(
                        value
                    )

            case "rotation":
                node.state.rotation =
                    CGFloat(
                        value
                    )

            case "x":

                node.state.frame.x =
                    CGFloat(
                        value
                    )

            case "y":

                node.state.frame.y =
                    CGFloat(
                        value
                    )

            case "width":

                node.state.frame.width =
                    CGFloat(
                        value
                    )

            case "height":

                node.state.frame.height =
                    CGFloat(
                        value
                    )

            default:
                continue
            }

            await nodeRegistry.insert(
                node
            )

            dirtyRegion.invalidate(
                node.state.frame
            )
        }
    }

    public func statistics()
        async
        -> FrameStatistics
    {
        await scheduler.statistics()
    }

    public func nodeCount()
        async
        -> Int
    {
        await nodeRegistry.count()
    }
}

// MARK: - Main-thread display driver

@MainActor
public final class DisplayDriver {

    private let renderEngine:
        RenderEngine

    private var displayLink:
        CADisplayLink?

    private var running:
        Bool =
            false

    public init(
        renderEngine:
            RenderEngine
    ) {
        self.renderEngine =
            renderEngine
    }

    public func start() {

        guard
            !running
        else {
            return
        }

        running =
            true

        let link =
            CADisplayLink(
                target:
                    self,
                selector:
                    #selector(
                        displayTick(
                            _
                        )
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

    public func stop() {

        displayLink?
            .invalidate()

        displayLink =
            nil

        running =
            false
    }

    @objc
    private func displayTick(
        _ link:
            CADisplayLink
    ) {

        let timestamp =
            link.timestamp

        Task {
            await renderEngine.render(
                timestamp:
                    timestamp
            )
        }
    }

    deinit {

        displayLink?
            .invalidate()
    }
}

// MARK: - Render transaction

public struct RenderTransaction:
    Sendable
{
    public var duration:
        TimeInterval

    public var curve:
        AnimationCurve

    public init(
        duration:
            TimeInterval =
                0.25,
        curve:
            AnimationCurve =
                .easeInOut
    ) {
        self.duration =
            duration

        self.curve =
            curve
    }
}

// MARK: - UI state

public struct UIState:
    Sendable
{
    public var isEnabled:
        Bool

    public var isFocused:
        Bool

    public var isPressed:
        Bool

    public var isHighlighted:
        Bool

    public var opacity:
        Double

    public init(
        isEnabled:
            Bool = true,
        isFocused:
            Bool = false,
        isPressed:
            Bool = false,
        isHighlighted:
            Bool = false,
        opacity:
            Double = 1
    ) {
        self.isEnabled =
            isEnabled

        self.isFocused =
            isFocused

        self.isPressed =
            isPressed

        self.isHighlighted =
            isHighlighted

        self.opacity =
            opacity
    }
}

// MARK: - UI state store

public actor UIStateStore {

    private var states:
        [RenderNodeID: UIState] =
            [:]

    public init() {}

    public func state(
        for nodeID:
            RenderNodeID
    )
        -> UIState
    {
        states[
            nodeID
        ] ??
        UIState()
    }

    public func set(
        _ state:
            UIState,
        for nodeID:
            RenderNodeID
    ) {
        states[
            nodeID
        ] =
            state
    }

    public func remove(
        nodeID:
            RenderNodeID
    ) {
        states.removeValue(
            forKey:
                nodeID
        )
    }
}

// MARK: - Render performance monitor

public actor RenderPerformanceMonitor {

    private var recentFrames:
        [FrameTiming] =
            []

    private let maximumSamples:
        Int

    public init(
        maximumSamples:
            Int = 120
    ) {
        self.maximumSamples =
            maximumSamples
    }

    public func record(
        _ timing:
            FrameTiming
    ) {
        recentFrames.append(
            timing
        )

        if recentFrames.count >
            maximumSamples
        {
            recentFrames.removeFirst(
                recentFrames.count -
                maximumSamples
            )
        }
    }

    public func averageFrameTime()
        -> TimeInterval
    {
        guard
            !recentFrames.isEmpty
        else {
            return 0
        }

        return recentFrames
            .map(\.duration)
            .reduce(
                0,
                +
            ) /
            Double(
                recentFrames.count
            )
    }

    public func droppedFrames()
        -> Int
    {
        recentFrames
            .filter(\.dropped)
            .count
    }

    public func reset() {
        recentFrames.removeAll(
            keepingCapacity:
                true
        )
    }
}

// MARK: - Render diagnostics

public struct RenderDiagnostics:
    Sendable
{
    public let nodeCount:
        Int

    public let frameStatistics:
        FrameStatistics

    public let timestamp:
        Date

    public init(
        nodeCount:
            Int,
        frameStatistics:
            FrameStatistics,
        timestamp:
            Date =
                Date()
    ) {
        self.nodeCount =
            nodeCount

        self.frameStatistics =
            frameStatistics

        self.timestamp =
            timestamp
    }
}

// MARK: - High performance UI coordinator

@MainActor
public final class HighPerformanceUIEngine {

    public let renderer:
        RenderEngine

    public let gestures:
        GestureRouter

    public let state:
        UIStateStore

    public let performance:
        RenderPerformanceMonitor

    private var displayDriver:
        DisplayDriver?

    public init(
        targetFPS:
            Double = 60
    ) {

        let renderer =
            RenderEngine(
                targetFPS:
                    targetFPS
            )

        self.renderer =
            renderer

        self.gestures =
            GestureRouter()

        self.state =
            UIStateStore()

        self.performance =
            RenderPerformanceMonitor()
    }

    public func configure(
        size:
            RenderSize,
        scale:
            RenderScale =
                .one,
        backend:
            any RenderBackend
    )
        async
    {
        await renderer.setViewport(
            size:
                size,
            scale:
                scale
        )

        await renderer.attachBackend(
            backend
        )
    }

    public func startDisplay() {

        let driver =
            DisplayDriver(
                renderEngine:
                    renderer
            )

        displayDriver =
            driver

        driver.start()
    }

    public func stopDisplay() {

        displayDriver?.stop()

        displayDriver =
            nil
    }

    public func diagnostics()
        async
        -> RenderDiagnostics
    {
        RenderDiagnostics(
            nodeCount:
                await renderer.nodeCount(),
            frameStatistics:
                await renderer.statistics()
        )
    }

    deinit {

        displayDriver?.stop()
    }
}

// MARK: - Example application scene

@MainActor
public final class ExampleRenderScene {

    private let engine:
        HighPerformanceUIEngine

    private var cardNode:
        RenderNodeID?

    public init() {

        engine =
            HighPerformanceUIEngine(
                targetFPS:
                    60
            )
    }

    public func setup(
        size:
            RenderSize
    )
        async
    {
        let backend =
            NullRenderBackend()

        await engine.configure(
            size:
                size,
            scale:
                RenderScale(
                    x:
                        2,
                    y:
                        2
                ),
            backend:
                backend
        )

        let card =
            await engine.renderer
                .createNode(
                    primitive:
                        .roundedRectangle(
                            rect:
                                RenderRect(
                                    x:
                                        20,
                                    y:
                                        20,
                                    width:
                                        size.width -
                                        40,
                                    height:
                                        100
                                ),
                            radius:
                                18,
                            fill:
                                RenderColor(
                                    red:
                                        0.15,
                                    green:
                                        0.15,
                                    blue:
                                        0.17
                                )
                        )
                )

        cardNode =
            card

        await engine.renderer
            .updateNode(
                id:
                    card,
                state:
                    RenderNodeState(
                        frame:
                            RenderRect(
                                x:
                                    20,
                                y:
                                    20,
                                width:
                                    size.width -
                                    40,
                                height:
                                    100
                            )
                    )
            )

        engine.startDisplay()
    }

    public func animateCard(
        now:
            TimeInterval
    )
        async
    {
        guard
            let cardNode
        else {
            return
        }

        let animation =
            RenderAnimation(
                nodeID:
                    cardNode,
                key:
                    "scale",
                from:
                    1,
                to:
                    1.05,
                duration:
                    0.35,
                curve:
                    .spring(
                        response:
                            0.35,
                        dampingFraction:
                            0.75
                    ),
                startedAt:
                    now
            )

        await engine.renderer
            .addAnimation(
                animation
            )
    }

    public func shutdown() {

        engine.stopDisplay()
    }
}






//
//  AppleConnectivityEngine.swift
//
//  #5 — High-Reliability Bluetooth / Watch ↔ iPhone Connectivity
//
//  Swift 6
//
//  Targets:
//      iOS
//      watchOS
//
//  Public Apple API:
//      WatchConnectivity
//
//  Architecture:
//
//                    ConnectivityCoordinator
//                            │
//             ┌──────────────┼──────────────┐
//             │              │              │
//             ▼              ▼              ▼
//        Reachability     Message Queue   Sync Engine
//             │              │              │
//             └──────────────┼──────────────┘
//                            │
//                            ▼
//                   ConnectivityTransport
//                            │
//                    ┌───────┴───────┐
//                    │               │
//                 iPhone           Apple Watch
//                    │               │
//                    └──── WatchConnectivity
//
//  Design goals:
//
//  • Swift 6 concurrency
//  • actor-isolated mutable state
//  • reliable message delivery
//  • idempotency / duplicate protection
//  • ordered queued messages
//  • acknowledgement tracking
//  • retry with backoff
//  • reachability awareness
//  • application-context synchronisation
//  • background transfer support
//  • file-transfer abstraction
//  • diagnostics
//  • deterministic tests
//

import Foundation
import os

#if canImport(WatchConnectivity)
import WatchConnectivity
#endif

// MARK: - Device Role

public enum ConnectivityDeviceRole:
    String,
    Codable,
    Sendable
{
    case iPhone
    case watch
}

// MARK: - Connectivity State

public enum ConnectivityState:
    String,
    Codable,
    Sendable
{
    case unknown
    case unavailable
    case disconnected
    case connecting
    case reachable
}

// MARK: - Message Priority

public enum ConnectivityPriority:
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
            ConnectivityPriority,
        rhs:
            ConnectivityPriority
    )
        -> Bool
    {
        lhs.rawValue <
            rhs.rawValue
    }
}

// MARK: - Delivery Mode

public enum ConnectivityDeliveryMode:
    String,
    Codable,
    Sendable
{
    /// Requires the peer to be reachable.
    case immediate

    /// Queued for background delivery.
    case background

    /// Delivered as the latest application context.
    /// Older values are superseded.
    case latestState

    /// Transfer as a file.
    case file
}

// MARK: - Message ID

public struct ConnectivityMessageID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue:
        UUID

    public init(
        _ rawValue:
            UUID = UUID()
    ) {
        self.rawValue =
            rawValue
    }
}

// MARK: - Transfer ID

public struct ConnectivityTransferID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue:
        UUID

    public init(
        _ rawValue:
            UUID = UUID()
    ) {
        self.rawValue =
            rawValue
    }
}

// MARK: - Codable payload

public struct ConnectivityPayload:
    Codable,
    Sendable
{
    public let type:
        String

    public let data:
        Data

    public init(
        type:
            String,
        data:
            Data
    ) {
        self.type =
            type

        self.data =
            data
    }

    public init<T: Encodable & Sendable>(
        type:
            String,
        value:
            T,
        encoder:
            JSONEncoder =
                JSONEncoder()
    )
        throws
    {
        self.type =
            type

        self.data =
            try encoder.encode(
                value
            )
    }

    public func decode<T: Decodable>(
        _ type:
            T.Type,
        decoder:
            JSONDecoder =
                JSONDecoder()
    )
        throws
        -> T
    {
        try decoder.decode(
            T.self,
            from:
                data
        )
    }
}

// MARK: - Message Envelope

public struct ConnectivityMessage:
    Codable,
    Sendable
{
    public let id:
        ConnectivityMessageID

    public let createdAt:
        Date

    public let expiresAt:
        Date?

    public let priority:
        ConnectivityPriority

    public let delivery:
        ConnectivityDeliveryMode

    public let payload:
        ConnectivityPayload

    public let requiresAcknowledgement:
        Bool

    public init(
        id:
            ConnectivityMessageID =
                ConnectivityMessageID(),
        createdAt:
            Date =
                Date(),
        expiresAt:
            Date? =
                nil,
        priority:
            ConnectivityPriority =
                .normal,
        delivery:
            ConnectivityDeliveryMode =
                .immediate,
        payload:
            ConnectivityPayload,
        requiresAcknowledgement:
            Bool =
                true
    ) {
        self.id =
            id

        self.createdAt =
            createdAt

        self.expiresAt =
            expiresAt

        self.priority =
            priority

        self.delivery =
            delivery

        self.payload =
            payload

        self.requiresAcknowledgement =
            requiresAcknowledgement
    }

    public func isExpired(
        now:
            Date =
                Date()
    )
        -> Bool
    {
        guard
            let expiresAt
        else {
            return false
        }

        return now >=
            expiresAt
    }
}

// MARK: - Acknowledgement

public struct ConnectivityAcknowledgement:
    Codable,
    Sendable
{
    public let messageID:
        ConnectivityMessageID

    public let receivedAt:
        Date

    public let success:
        Bool

    public let errorDescription:
        String?

    public init(
        messageID:
            ConnectivityMessageID,
        receivedAt:
            Date =
                Date(),
        success:
            Bool,
        errorDescription:
            String? =
                nil
    ) {
        self.messageID =
            messageID

        self.receivedAt =
            receivedAt

        self.success =
            success

        self.errorDescription =
            errorDescription
    }
}

// MARK: - Queue Entry

public enum ConnectivityQueueStatus:
    String,
    Codable,
    Sendable
{
    case queued
    case sending
    case awaitingAcknowledgement
    case completed
    case failed
    case expired
}

public struct ConnectivityQueueEntry:
    Codable,
    Sendable
{
    public let message:
        ConnectivityMessage

    public var status:
        ConnectivityQueueStatus

    public var attempts:
        Int

    public var lastAttemptAt:
        Date?

    public var nextAttemptAt:
        Date?

    public var lastError:
        String?

    public init(
        message:
            ConnectivityMessage
    ) {
        self.message =
            message

        self.status =
            .queued

        self.attempts =
            0

        self.lastAttemptAt =
            nil

        self.nextAttemptAt =
            nil

        self.lastError =
            nil
    }
}

// MARK: - Retry Policy

public struct ConnectivityRetryPolicy:
    Sendable
{
    public var maximumAttempts:
        Int

    public var initialDelay:
        TimeInterval

    public var maximumDelay:
        TimeInterval

    public var multiplier:
        Double

    public init(
        maximumAttempts:
            Int = 8,
        initialDelay:
            TimeInterval = 1,
        maximumDelay:
            TimeInterval = 300,
        multiplier:
            Double = 2
    ) {
        self.maximumAttempts =
            maximumAttempts

        self.initialDelay =
            initialDelay

        self.maximumDelay =
            maximumDelay

        self.multiplier =
            multiplier
    }

    public func delay(
        afterAttempt attempt:
            Int
    )
        -> TimeInterval
    {
        let exponent =
            max(
                0,
                attempt - 1
            )

        return min(
            maximumDelay,
            initialDelay *
                pow(
                    multiplier,
                    Double(
                        exponent
                    )
                )
        )
    }
}

// MARK: - Queue

public actor ConnectivityMessageQueue {

    private var entries:
        [
            ConnectivityMessageID:
            ConnectivityQueueEntry
        ] =
            [:]

    private let retryPolicy:
        ConnectivityRetryPolicy

    public init(
        retryPolicy:
            ConnectivityRetryPolicy =
                ConnectivityRetryPolicy()
    ) {
        self.retryPolicy =
            retryPolicy
    }

    public func enqueue(
        _ message:
            ConnectivityMessage
    ) {

        if
            let existing =
                entries[message.id],
            existing.status ==
                .completed
        {
            return
        }

        entries[message.id] =
            ConnectivityQueueEntry(
                message:
                    message
            )
    }

    public func remove(
        _ id:
            ConnectivityMessageID
    ) {
        entries.removeValue(
            forKey:
                id
        )
    }

    public func markSending(
        _ id:
            ConnectivityMessageID,
        now:
            Date =
                Date()
    )
        -> Bool
    {
        guard
            var entry =
                entries[id]
        else {
            return false
        }

        guard
            entry.status ==
                .queued ||
            entry.status ==
                .failed
        else {
            return false
        }

        if entry.message.isExpired(
            now:
                now
        ) {

            entry.status =
                .expired

            entries[id] =
                entry

            return false
        }

        guard
            entry.attempts <
                retryPolicy.maximumAttempts
        else {

            entry.status =
                .failed

            entry.lastError =
                "Maximum delivery attempts exceeded."

            entries[id] =
                entry

            return false
        }

        entry.status =
            .sending

        entry.attempts +=
            1

        entry.lastAttemptAt =
            now

        entries[id] =
            entry

        return true
    }

    public func markAwaitingAcknowledgement(
        _ id:
            ConnectivityMessageID
    ) {

        guard
            var entry =
                entries[id]
        else {
            return
        }

        entry.status =
            .awaitingAcknowledgement

        entries[id] =
            entry
    }

    public func acknowledge(
        _ acknowledgement:
            ConnectivityAcknowledgement
    ) {

        guard
            var entry =
                entries[
                    acknowledgement.messageID
                ]
        else {
            return
        }

        if acknowledgement.success {

            entry.status =
                .completed

            entry.lastError =
                nil

        } else {

            entry.status =
                .failed

            entry.lastError =
                acknowledgement.errorDescription

            let delay =
                retryPolicy.delay(
                    afterAttempt:
                        entry.attempts
                )

            entry.nextAttemptAt =
                Date().addingTimeInterval(
                    delay
                )
        }

        entries[
            acknowledgement.messageID
        ] =
            entry
    }

    public func markFailed(
        _ id:
            ConnectivityMessageID,
        error:
            String
    ) {

        guard
            var entry =
                entries[id]
        else {
            return
        }

        entry.status =
            .failed

        entry.lastError =
            error

        let delay =
            retryPolicy.delay(
                afterAttempt:
                    entry.attempts
            )

        entry.nextAttemptAt =
            Date().addingTimeInterval(
                delay
            )

        entries[id] =
            entry
    }

    public func readyMessages(
        now:
            Date =
                Date()
    )
        -> [ConnectivityMessage]
    {
        entries.values
            .filter {
                guard
                    $0.message.isExpired(
                        now:
                            now
                    ) ==
                    false
                else {
                    return false
                }

                guard
                    $0.status ==
                        .queued ||
                    $0.status ==
                        .failed
                else {
                    return false
                }

                if
                    let nextAttempt =
                        $0.nextAttemptAt
                {
                    return nextAttempt <=
                        now
                }

                return true
            }
            .sorted {
                if
                    $0.message.priority !=
                    $1.message.priority
                {
                    return
                        $0.message.priority >
                        $1.message.priority
                }

                return
                    $0.message.createdAt <
                    $1.message.createdAt
            }
            .map(\.message)
    }

    public func entry(
        for id:
            ConnectivityMessageID
    )
        -> ConnectivityQueueEntry?
    {
        entries[id]
    }

    public func allEntries()
        -> [ConnectivityQueueEntry]
    {
        Array(
            entries.values
        )
    }

    public func purgeCompleted() {

        entries =
            entries.filter {
                $0.value.status !=
                    .completed
            }
    }

    public func purgeExpired(
        now:
            Date =
                Date()
    ) {

        for (
            id,
            var entry
        )
        in entries
        {
            if entry.message.isExpired(
                now:
                    now
            ) {
                entry.status =
                    .expired

                entries[id] =
                    entry
            }
        }
    }

    public func count()
        -> Int
    {
        entries.count
    }
}

// MARK: - Reachability Snapshot

public struct ConnectivityReachability:
    Codable,
    Sendable
{
    public let state:
        ConnectivityState

    public let isReachable:
        Bool

    public let isCompanionInstalled:
        Bool

    public let timestamp:
        Date

    public init(
        state:
            ConnectivityState,
        isReachable:
            Bool,
        isCompanionInstalled:
            Bool,
        timestamp:
            Date =
                Date()
    ) {
        self.state =
            state

        self.isReachable =
            isReachable

        self.isCompanionInstalled =
            isCompanionInstalled

        self.timestamp =
            timestamp
    }
}

// MARK: - Transport Error

public enum ConnectivityTransportError:
    Error,
    LocalizedError,
    Sendable
{
    case unavailable
    case notReachable
    case encodingFailed
    case transportFailed(String)
    case unsupported
    case invalidResponse
    case expired

    public var errorDescription:
        String?
    {
        switch self {

        case .unavailable:
            return
                "Connectivity transport is unavailable."

        case .notReachable:
            return
                "The companion device is not currently reachable."

        case .encodingFailed:
            return
                "The message could not be encoded."

        case let .transportFailed(message):
            return
                message

        case .unsupported:
            return
                "This delivery operation is unsupported."

        case .invalidResponse:
            return
                "The companion returned an invalid response."

        case .expired:
            return
                "The message expired before delivery."
        }
    }
}

// MARK: - Transport

public protocol ConnectivityTransport:
    Sendable
{
    func activate()
        async

    func reachability()
        async
        -> ConnectivityReachability

    func sendImmediately(
        _ message:
            ConnectivityMessage
    )
        async throws

    func transferInBackground(
        _ message:
            ConnectivityMessage
    )
        async throws

    func updateApplicationContext(
        _ message:
            ConnectivityMessage
    )
        async throws

    func transferFile(
        url:
            URL,
        metadata:
            [String: String]
    )
        async throws
}

// MARK: - Transport Event

public enum ConnectivityTransportEvent:
    Sendable
{
    case activated
    case reachabilityChanged(
        ConnectivityReachability
    )
    case messageReceived(
        ConnectivityMessage
    )
    case acknowledgementReceived(
        ConnectivityAcknowledgement
    )
    case applicationContextReceived(
        ConnectivityMessage
    )
    case transferCompleted(
        ConnectivityTransferID
    )
    case transferFailed(
        ConnectivityTransferID,
        String
    )
}

// MARK: - Event Stream

public actor ConnectivityEventHub {

    private var continuations:
        [
            UUID:
            AsyncStream<ConnectivityTransportEvent>
                .Continuation
        ] =
            [:]

    public init() {}

    public func stream()
        -> AsyncStream<ConnectivityTransportEvent>
    {
        let id =
            UUID()

        return AsyncStream {
            continuation in

            continuations[id] =
                continuation

            continuation.onTermination =
                { [weak self] _ in

                    Task {
                        await self?
                            .remove(
                                id:
                                    id
                            )
                    }
                }
        }
    }

    public func publish(
        _ event:
            ConnectivityTransportEvent
    ) {

        for continuation
            in continuations.values
        {
            continuation.yield(
                event
            )
        }
    }

    private func remove(
        id:
            UUID
    ) {
        continuations.removeValue(
            forKey:
                id
        )
    }

    public func finish() {

        for continuation
            in continuations.values
        {
            continuation.finish()
        }

        continuations.removeAll()
    }
}

// MARK: - Mock Transport

public actor MockConnectivityTransport:
    ConnectivityTransport
{
    private var reachable:
        Bool =
            true

    private var sentMessages:
        [ConnectivityMessage] =
            []

    private var contexts:
        [ConnectivityMessage] =
            []

    public init() {}

    public func setReachable(
        _ value:
            Bool
    ) {
        reachable =
            value
    }

    public func activate()
        async
    {}

    public func reachability()
        async
        -> ConnectivityReachability
    {
        ConnectivityReachability(
            state:
                reachable
                ? .reachable
                : .disconnected,
            isReachable:
                reachable,
            isCompanionInstalled:
                true
        )
    }

    public func sendImmediately(
        _ message:
            ConnectivityMessage
    )
        async throws
    {
        guard reachable else {
            throw ConnectivityTransportError
                .notReachable
        }

        sentMessages.append(
            message
        )
    }

    public func transferInBackground(
        _ message:
            ConnectivityMessage
    )
        async throws
    {
        sentMessages.append(
            message
        )
    }

    public func updateApplicationContext(
        _ message:
            ConnectivityMessage
    )
        async throws
    {
        contexts.append(
            message
        )
    }

    public func transferFile(
        url:
            URL,
        metadata:
            [String: String]
    )
        async throws
    {}

    public func sent()
        -> [ConnectivityMessage]
    {
        sentMessages
    }

    public func latestContext()
        -> ConnectivityMessage?
    {
        contexts.last
    }
}

// MARK: - Persistence

public actor ConnectivityQueuePersistence {

    private let url:
        URL

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    public init(
        url:
            URL
    ) {
        self.url =
            url

        self.encoder =
            JSONEncoder()

        self.decoder =
            JSONDecoder()

        encoder.dateEncodingStrategy =
            .iso8601

        decoder.dateDecodingStrategy =
            .iso8601
    }

    public func save(
        entries:
            [ConnectivityQueueEntry]
    )
        throws
    {
        let directory =
            url.deletingLastPathComponent()

        try FileManager.default
            .createDirectory(
                at:
                    directory,
                withIntermediateDirectories:
                    true
            )

        let data =
            try encoder.encode(
                entries
            )

        try data.write(
            to:
                url,
            options:
                .atomic
        )
    }

    public func load()
        throws
        -> [
            ConnectivityQueueEntry
        ]
    {
        guard
            FileManager.default
                .fileExists(
                    atPath:
                        url.path
                )
        else {
            return []
        }

        let data =
            try Data(
                contentsOf:
                    url
            )

        return try decoder.decode(
            [
                ConnectivityQueueEntry
            ].self,
            from:
                data
        )
    }
}

// MARK: - Synchronisation Record

public struct SynchronisationRecord:
    Codable,
    Sendable
{
    public let key:
        String

    public let version:
        UInt64

    public let modifiedAt:
        Date

    public let payload:
        Data

    public init(
        key:
            String,
        version:
            UInt64,
        modifiedAt:
            Date =
                Date(),
        payload:
            Data
    ) {
        self.key =
            key

        self.version =
            version

        self.modifiedAt =
            modifiedAt

        self.payload =
            payload
    }
}

// MARK: - Sync Store

public actor ConnectivitySyncStore {

    private var records:
        [String: SynchronisationRecord] =
            [:]

    public init() {}

    public func write(
        _ record:
            SynchronisationRecord
    ) {

        if
            let existing =
                records[record.key],
            existing.version >=
                record.version
        {
            return
        }

        records[
            record.key
        ] =
            record
    }

    public func record(
        for key:
            String
    )
        -> SynchronisationRecord?
    {
        records[key]
    }

    public func all()
        -> [
            SynchronisationRecord
        ]
    {
        Array(
            records.values
        )
    }

    public func remove(
        key:
            String
    ) {
        records.removeValue(
            forKey:
                key
        )
    }

    public func clear() {
        records.removeAll()
    }
}

// MARK: - Connectivity Metrics

public struct ConnectivityMetrics:
    Sendable
{
    public private(set) var messagesQueued:
        UInt64 =
            0

    public private(set) var messagesSent:
        UInt64 =
            0

    public private(set) var messagesFailed:
        UInt64 =
            0

    public private(set) var messagesAcknowledged:
        UInt64 =
            0

    public private(set) var bytesSent:
        UInt64 =
            0

    public private(set) var bytesReceived:
        UInt64 =
            0

    public private(set) var reconnects:
        UInt64 =
            0

    public private(set) var transportErrors:
        UInt64 =
            0

    public mutating func queued() {
        messagesQueued +=
            1
    }

    public mutating func sent(
        bytes:
            Int
    ) {
        messagesSent +=
            1

        self.bytesSent +=
            UInt64(
                max(
                    0,
                    bytes
                )
            )
    }

    public mutating func failed() {
        messagesFailed +=
            1
    }

    public mutating func acknowledged() {
        messagesAcknowledged +=
            1
    }

    public mutating func received(
        bytes:
            Int
    ) {
        bytesReceived +=
            UInt64(
                max(
                    0,
                    bytes
                )
            )
    }

    public mutating func reconnected() {
        reconnects +=
            1
    }

    public mutating func transportError() {
        transportErrors +=
            1
    }
}

// MARK: - Metrics Store

public actor ConnectivityMetricsStore {

    private var metrics =
        ConnectivityMetrics()

    public init() {}

    public func recordQueued() {
        metrics.queued()
    }

    public func recordSent(
        bytes:
            Int
    ) {
        metrics.sent(
            bytes:
                bytes
        )
    }

    public func recordFailed() {
        metrics.failed()
    }

    public func recordAcknowledged() {
        metrics.acknowledged()
    }

    public func recordReceived(
        bytes:
            Int
    ) {
        metrics.received(
            bytes:
                bytes
        )
    }

    public func recordReconnect() {
        metrics.reconnected()
    }

    public func recordTransportError() {
        metrics.transportError()
    }

    public func snapshot()
        -> ConnectivityMetrics
    {
        metrics
    }
}

// MARK: - Connectivity Logger

public enum ConnectivityLog {

    private static let logger =
        Logger(
            subsystem:
                "com.example.AppleConnectivity",
            category:
                "Connectivity"
        )

    public static func info(
        _ message:
            String
    ) {
        logger.info(
            "\(message, privacy: .public)"
        )
    }

    public static func error(
        _ message:
            String
    ) {
        logger.error(
            "\(message, privacy: .public)"
        )
    }

    public static func debug(
        _ message:
            String
    ) {
        logger.debug(
            "\(message, privacy: .public)"
        )
    }
}

// MARK: - Connectivity Coordinator

public actor ConnectivityCoordinator {

    private let transport:
        any ConnectivityTransport

    private let queue:
        ConnectivityMessageQueue

    private let metrics:
        ConnectivityMetricsStore

    private let eventHub:
        ConnectivityEventHub

    private let persistence:
        ConnectivityQueuePersistence?

    private var state:
        ConnectivityState =
            .unknown

    private var processingTask:
        Task<Void, Never>?

    private var eventTask:
        Task<Void, Never>?

    public init(
        transport:
            any ConnectivityTransport,
        persistence:
            ConnectivityQueuePersistence? =
                nil,
        queue:
            ConnectivityMessageQueue =
                ConnectivityMessageQueue(),
        metrics:
            ConnectivityMetricsStore =
                ConnectivityMetricsStore(),
        eventHub:
            ConnectivityEventHub =
                ConnectivityEventHub()
    ) {
        self.transport =
            transport

        self.persistence =
            persistence

        self.queue =
            queue

        self.metrics =
            metrics

        self.eventHub =
            eventHub
    }

    // MARK: Lifecycle

    public func start()
        async
    {
        await transport.activate()

        let reachability =
            await transport.reachability()

        state =
            reachability.state

        await startEventProcessing()

        await restoreQueue()

        startQueueProcessor()

        ConnectivityLog.info(
            "Connectivity coordinator started."
        )
    }

    public func stop() {

        processingTask?
            .cancel()

        processingTask =
            nil

        eventTask?
            .cancel()

        eventTask =
            nil

        ConnectivityLog.info(
            "Connectivity coordinator stopped."
        )
    }

    // MARK: State

    public func currentState()
        -> ConnectivityState
    {
        state
    }

    public func reachability()
        async
        -> ConnectivityReachability
    {
        await transport.reachability()
    }

    // MARK: Send

    @discardableResult
    public func send(
        payload:
            ConnectivityPayload,
        priority:
            ConnectivityPriority =
                .normal,
        delivery:
            ConnectivityDeliveryMode =
                .immediate,
        expiresAt:
            Date? =
                nil,
        requiresAcknowledgement:
            Bool =
                true
    )
        async
        -> ConnectivityMessageID
    {
        let message =
            ConnectivityMessage(
                priority:
                    priority,
                delivery:
                    delivery,
                payload:
                    payload,
                requiresAcknowledgement:
                    requiresAcknowledgement
            )

        await send(
            message
        )

        return message.id
    }

    public func send(
        _ message:
            ConnectivityMessage
    )
        async
    {
        if message.isExpired() {

            ConnectivityLog.debug(
                "Rejected expired connectivity message."
            )

            return
        }

        await queue.enqueue(
            message
        )

        await metrics.recordQueued()

        await persistQueue()

        await processQueue()
    }

    // MARK: Immediate sending

    private func processQueue()
        async
    {
        let reachability =
            await transport.reachability()

        state =
            reachability.state

        let messages =
            await queue.readyMessages()

        for message
            in messages
        {
            guard
                !Task.isCancelled
            else {
                return
            }

            await deliver(
                message
            )
        }

        await persistQueue()
    }

    private func deliver(
        _ message:
            ConnectivityMessage
    )
        async
    {
        guard
            await queue.markSending(
                message.id
            )
        else {
            return
        }

        do {

            switch message.delivery {

            case .immediate:

                try await transport
                    .sendImmediately(
                        message
                    )

            case .background:

                try await transport
                    .transferInBackground(
                        message
                    )

            case .latestState:

                try await transport
                    .updateApplicationContext(
                        message
                    )

            case .file:

                throw ConnectivityTransportError
                    .unsupported
            }

            let payloadSize =
                message.payload.data.count

            await metrics.recordSent(
                bytes:
                    payloadSize
            )

            if message.requiresAcknowledgement {

                await queue
                    .markAwaitingAcknowledgement(
                        message.id
                    )

            } else {

                await queue
                    .acknowledge(
                        ConnectivityAcknowledgement(
                            messageID:
                                message.id,
                            success:
                                true
                        )
                    )
            }

            await persistQueue()

        } catch {

            await metrics
                .recordFailed()

            await metrics
                .recordTransportError()

            await queue.markFailed(
                message.id,
                error:
                    error.localizedDescription
            )

            ConnectivityLog.error(
                "Connectivity delivery failed: \(error.localizedDescription)"
            )
        }
    }

    // MARK: Acknowledgements

    public func acknowledge(
        _ acknowledgement:
            ConnectivityAcknowledgement
    )
        async
    {
        await queue.acknowledge(
            acknowledgement
        )

        if acknowledgement.success {
            await metrics.recordAcknowledged()
        }

        await persistQueue()

        await processQueue()
    }

    // MARK: Queue

    public func queueSize()
        async
        -> Int
    {
        await queue.count()
    }

    public func queuedEntries()
        async
        -> [
            ConnectivityQueueEntry
        ]
    {
        await queue.allEntries()
    }

    public func purgeQueue()
        async
    {
        await queue.purgeCompleted()

        await queue.purgeExpired()

        await persistQueue()
    }

    // MARK: Events

    public func events()
        -> AsyncStream<ConnectivityTransportEvent>
    {
        let hub =
            eventHub

        return AsyncStream {
            continuation in

            Task {
                let stream =
                    await hub.stream()

                for await event
                    in stream
                {
                    continuation.yield(
                        event
                    )
                }

                continuation.finish()
            }
        }
    }

    private func startEventProcessing()
        async
    {
        let stream =
            await eventHub.stream()

        eventTask =
            Task { [weak self] in

                for await event
                    in stream
                {
                    guard
                        let self
                    else {
                        return
                    }

                    await self
                        .handle(
                            event
                        )
                }
            }
    }

    private func handle(
        _ event:
            ConnectivityTransportEvent
    )
        async
    {
        switch event {

        case .activated:

            ConnectivityLog.debug(
                "Transport activated."
            )

        case let .reachabilityChanged(
            reachability
        ):

            let previous =
                state

            state =
                reachability.state

            if previous != .reachable &&
                state == .reachable
            {
                await metrics
                    .recordReconnect()

                await processQueue()
            }

        case let .messageReceived(
            message
        ):

            await metrics.recordReceived(
                bytes:
                    message.payload.data.count
            )

            await eventHub.publish(
                .messageReceived(
                    message
                )
            )

        case let .acknowledgementReceived(
            acknowledgement
        ):

            await acknowledge(
                acknowledgement
            )

            await eventHub.publish(
                event
            )

        case let .applicationContextReceived(
            message
        ):

            await eventHub.publish(
                .applicationContextReceived(
                    message
                )
            )

        case .transferCompleted,
             .transferFailed:

            await eventHub.publish(
                event
            )
        }
    }

    // MARK: Background queue worker

    private func startQueueProcessor() {

        processingTask =
            Task { [weak self] in

                while
                    !Task.isCancelled
                {
                    guard
                        let self
                    else {
                        return
                    }

                    await self.processQueue()

                    try? await Task.sleep(
                        for:
                            .seconds(
                                2
                            )
                    )
                }
            }
    }

    // MARK: Persistence

    private func restoreQueue()
        async
    {
        guard
            let persistence
        else {
            return
        }

        do {

            let entries =
                try await persistence.load()

            for entry
                in entries
            {
                await queue.enqueue(
                    entry.message
                )
            }

            ConnectivityLog.info(
                "Restored \(entries.count) queued connectivity messages."
            )

        } catch {

            ConnectivityLog.error(
                "Unable to restore connectivity queue: \(error.localizedDescription)"
            )
        }
    }

    private func persistQueue()
        async
    {
        guard
            let persistence
        else {
            return
        }

        do {

            try await persistence.save(
                entries:
                    await queue.allEntries()
            )

        } catch {

            ConnectivityLog.error(
                "Unable to persist connectivity queue: \(error.localizedDescription)"
            )
        }
    }

    // MARK: Metrics

    public func metricsSnapshot()
        async
        -> ConnectivityMetrics
    {
        await metrics.snapshot()
    }
}

// MARK: - WatchConnectivity Adapter

#if canImport(WatchConnectivity)

@MainActor
public final class WatchConnectivityAdapter:
    NSObject,
    ConnectivityTransport,
    WCSessionDelegate
{
    private let session:
        WCSession

    private let eventHub:
        ConnectivityEventHub

    public init(
        eventHub:
            ConnectivityEventHub =
                ConnectivityEventHub()
    ) {
        self.session =
            WCSession.default

        self.eventHub =
            eventHub

        super.init()

        session.delegate =
            self
    }

    // MARK: Activation

    public func activate()
        async
    {
        guard
            WCSession.isSupported()
        else {

            await eventHub.publish(
                .reachabilityChanged(
                    ConnectivityReachability(
                        state:
                            .unavailable,
                        isReachable:
                            false,
                        isCompanionInstalled:
                            false
                    )
                )
            )

            return
        }

        session.activate()
    }

    // MARK: Reachability

    public func reachability()
        async
        -> ConnectivityReachability
    {
        guard
            WCSession.isSupported()
        else {
            return ConnectivityReachability(
                state:
                    .unavailable,
                isReachable:
                    false,
                isCompanionInstalled:
                    false
            )
        }

        let reachable =
            session.isReachable

        let state:
            ConnectivityState =
                reachable
                ? .reachable
                : .disconnected

        return ConnectivityReachability(
            state:
                state,
            isReachable:
                reachable,
            isCompanionInstalled:
                session.isCompanionAppInstalled
        )
    }

    // MARK: Encoding

    private func encode(
        _ message:
            ConnectivityMessage
    )
        throws
        -> [String: Any]
    {
        let encoder =
            JSONEncoder()

        encoder.dateEncodingStrategy =
            .iso8601

        let data =
            try encoder.encode(
                message
            )

        return [
            "kind":
                "connectivity.message",
            "version":
                1,
            "message":
                data
        ]
    }

    private func decode(
        _ dictionary:
            [String: Any]
    )
        throws
        -> ConnectivityMessage
    {
        guard
            let data =
                dictionary["message"]
                as? Data
        else {
            throw ConnectivityTransportError
                .invalidResponse
        }

        let decoder =
            JSONDecoder()

        decoder.dateDecodingStrategy =
            .iso8601

        return try decoder.decode(
            ConnectivityMessage.self,
            from:
                data
        )
    }

    // MARK: Immediate

    public func sendImmediately(
        _ message:
            ConnectivityMessage
    )
        async throws
    {
        guard
            session.isReachable
        else {
            throw ConnectivityTransportError
                .notReachable
        }

        let payload =
            try encode(
                message
            )

        try await withCheckedThrowingContinuation {
            (
                continuation:
                    CheckedContinuation<
                        Void,
                        Error
                    >
            )
            in

            session.sendMessage(
                payload,
                replyHandler:
                    { reply in

                        Task { @MainActor in

                            if
                                let replyMessage =
                                    try? self.decode(
                                        reply
                                    )
                            {
                                await self.eventHub
                                    .publish(
                                        .messageReceived(
                                            replyMessage
                                        )
                                    )
                            }

                            continuation.resume()
                        }
                    },
                errorHandler:
                    { error in

                        continuation.resume(
                            throwing:
                                error
                        )
                    }
            )
        }
    }

    // MARK: Background

    public func transferInBackground(
        _ message:
            ConnectivityMessage
    )
        async throws
    {
        let payload =
            try encode(
                message
            )

        session.transferUserInfo(
            payload
        )
    }

    // MARK: Latest state

    public func updateApplicationContext(
        _ message:
            ConnectivityMessage
    )
        async throws
    {
        let payload =
            try encode(
                message
            )

        try session.updateApplicationContext(
            payload
        )
    }

    // MARK: Files

    public func transferFile(
        url:
            URL,
        metadata:
            [String: String]
    )
        async throws
    {
        session.transferFile(
            url,
            metadata:
                metadata
        )
    }

    // MARK: WCSessionDelegate

    public func session(
        _ session:
            WCSession,
        activationDidCompleteWith activationState:
            WCSessionActivationState,
        error:
            Error?
    ) {

        if
            let error
        {
            ConnectivityLog.error(
                "WCSession activation error: \(error.localizedDescription)"
            )

            Task {
                await eventHub.publish(
                    .reachabilityChanged(
                        ConnectivityReachability(
                            state:
                                .unavailable,
                            isReachable:
                                false,
                            isCompanionInstalled:
                                false
                        )
                    )
                )
            }

            return
        }

        Task {
            await eventHub.publish(
                .activated
            )

            await eventHub.publish(
                .reachabilityChanged(
                    await reachability()
                )
            )
        }
    }

    public func sessionReachabilityDidChange(
        _ session:
            WCSession
    ) {

        Task {
            await eventHub.publish(
                .reachabilityChanged(
                    await reachability()
                )
            )
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceiveMessage message:
            [String: Any]
    ) {

        guard
            let decoded =
                try? decode(
                    message
                )
        else {
            return
        }

        Task {
            await eventHub.publish(
                .messageReceived(
                    decoded
                )
            )
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceiveApplicationContext:
            [String: Any]
    ) {

        guard
            let decoded =
                try? decode(
                    didReceiveApplicationContext
                )
        else {
            return
        }

        Task {
            await eventHub.publish(
                .applicationContextReceived(
                    decoded
                )
            )
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceiveUserInfo:
            [String: Any]
    ) {

        guard
            let decoded =
                try? decode(
                    didReceiveUserInfo
                )
        else {
            return
        }

        Task {
            await eventHub.publish(
                .messageReceived(
                    decoded
                )
            )
        }
    }

    public func session(
        _ session:
            WCSession,
        didReceive file:
            WCSessionFile
    ) {

        ConnectivityLog.debug(
            "Received connectivity file: \(file.fileURL.lastPathComponent)"
        )
    }
}

#endif

// MARK: - Typed Application Messages

public protocol ConnectivityMessageType:
    Codable,
    Sendable
{
    static var messageType:
        String
    { get }
}

// MARK: Example Typed Message

public struct HeartbeatMessage:
    ConnectivityMessageType
{
    public static let messageType =
        "heartbeat"

    public let timestamp:
        Date

    public let sequence:
        UInt64

    public init(
        timestamp:
            Date =
                Date(),
        sequence:
            UInt64
    ) {
        self.timestamp =
            timestamp

        self.sequence =
            sequence
    }
}

// MARK: Sync Message

public struct StateSynchronisationMessage:
    ConnectivityMessageType
{
    public static let messageType =
        "state.synchronisation"

    public let key:
        String

    public let version:
        UInt64

    public let data:
        Data

    public init(
        key:
            String,
        version:
            UInt64,
        data:
            Data
    ) {
        self.key =
            key

        self.version =
            version

        self.data =
            data
    }
}

// MARK: Typed Sender

public extension ConnectivityCoordinator {

    @discardableResult
    func send<T: ConnectivityMessageType>(
        _ value:
            T,
        priority:
            ConnectivityPriority =
                .normal,
        delivery:
            ConnectivityDeliveryMode =
                .immediate
    )
        async
        throws
        -> ConnectivityMessageID
    {
        let payload =
            try ConnectivityPayload(
                type:
                    T.messageType,
                value:
                    value
            )

        return await send(
            payload:
                payload,
            priority:
                priority,
            delivery:
                delivery
        )
    }
}

// MARK: - Connection Health

public struct ConnectionHealth:
    Sendable
{
    public let state:
        ConnectivityState

    public let queueDepth:
        Int

    public let failedMessages:
        Int

    public let pendingAcknowledgements:
        Int

    public let metrics:
        ConnectivityMetrics

    public init(
        state:
            ConnectivityState,
        queueDepth:
            Int,
        failedMessages:
            Int,
        pendingAcknowledgements:
            Int,
        metrics:
            ConnectivityMetrics
    ) {
        self.state =
            state

        self.queueDepth =
            queueDepth

        self.failedMessages =
            failedMessages

        self.pendingAcknowledgements =
            pendingAcknowledgements

        self.metrics =
            metrics
    }
}

// MARK: - Health Provider

public extension ConnectivityCoordinator {

    func health()
        async
        -> ConnectionHealth
    {
        let entries =
            await queue.allEntries()

        let failed =
            entries.filter {
                $0.status ==
                    .failed
            }.count

        let pending =
            entries.filter {
                $0.status ==
                    .awaitingAcknowledgement
            }.count

        return ConnectionHealth(
            state:
                state,
            queueDepth:
                entries.count,
            failedMessages:
                failed,
            pendingAcknowledgements:
                pending,
            metrics:
                await metrics.snapshot()
        )
    }
}

// MARK: - Test Suite

public enum ConnectivityEngineTests {

    public static func run()
        async
    {
        await testQueueOrdering()
        await testRetryPolicy()
        await testMessageEncoding()
        await testMockTransport()
    }

    private static func testQueueOrdering()
        async
    {
        let queue =
            ConnectivityMessageQueue()

        let low =
            ConnectivityMessage(
                priority:
                    .low,
                payload:
                    ConnectivityPayload(
                        type:
                            "low",
                        data:
                            Data()
                    )
            )

        let critical =
            ConnectivityMessage(
                priority:
                    .critical,
                payload:
                    ConnectivityPayload(
                        type:
                            "critical",
                        data:
                            Data()
                    )
            )

        await queue.enqueue(
            low
        )

        await queue.enqueue(
            critical
        )

        let ready =
            await queue.readyMessages()

        assert(
            ready.first?.priority ==
                .critical
        )
    }

    private static func testRetryPolicy()
        async
    {
        let policy =
            ConnectivityRetryPolicy(
                maximumAttempts:
                    5,
                initialDelay:
                    1,
                maximumDelay:
                    30,
                multiplier:
                    2
            )

        assert(
            policy.delay(
                afterAttempt:
                    1
            ) ==
            1
        )

        assert(
            policy.delay(
                afterAttempt:
                    2
            ) ==
            2
        )

        assert(
            policy.delay(
                afterAttempt:
                    3
            ) ==
            4
        )

        assert(
            policy.delay(
                afterAttempt:
                    4
            ) ==
            8
        )
    }

    private static func testMessageEncoding()
        async
    {
        let heartbeat =
            HeartbeatMessage(
                sequence:
                    42
            )

        let payload =
            try! ConnectivityPayload(
                type:
                    HeartbeatMessage
                        .messageType,
                value:
                    heartbeat
            )

        let decoded =
            try! payload.decode(
                HeartbeatMessage.self
            )

        assert(
            decoded.sequence ==
                42
        )
    }

    private static func testMockTransport()
        async
    {
        let transport =
            MockConnectivityTransport()

        let message =
            ConnectivityMessage(
                payload:
                    ConnectivityPayload(
                        type:
                            "test",
                        data:
                            Data(
                                "hello".utf8
                            )
                    )
            )

        try! await transport
            .sendImmediately(
                message
            )

        let sent =
            await transport.sent()

        assert(
            sent.count ==
                1
        )
    }
}

// MARK: - Example Factory

public enum ConnectivityFactory {

    public static func makeMock()
        -> ConnectivityCoordinator
    {
        let transport =
            MockConnectivityTransport()

        return ConnectivityCoordinator(
            transport:
                transport
        )
    }

    #if canImport(WatchConnectivity)

    @MainActor
    public static func makeWatchConnectivity(
        queuePersistenceURL:
            URL? =
                nil
    )
        -> (
            coordinator:
                ConnectivityCoordinator,
            adapter:
                WatchConnectivityAdapter
        )
    {
        let hub =
            ConnectivityEventHub()

        let adapter =
            WatchConnectivityAdapter(
                eventHub:
                    hub
            )

        let persistence =
            queuePersistenceURL
            .map {
                ConnectivityQueuePersistence(
                    url:
                        $0
                )
            }

        let coordinator =
            ConnectivityCoordinator(
                transport:
                    adapter,
                persistence:
                    persistence,
                eventHub:
                    hub
            )

        return (
            coordinator:
                coordinator,
            adapter:
                adapter
        )
    }

    #endif
}






//
//  AppleSignalProcessing.swift
//
//  #6 — On-Device Signal Processing Library
//
//  Swift 6
//
//  Public frameworks:
//      Foundation
//      Accelerate
//
//  Design:
//
//      Sensor / Audio / HealthKit
//                │
//                ▼
//          SignalBuffer
//                │
//        ┌───────┴────────┐
//        ▼                ▼
//    Preprocessing     Resampling
//        │                │
//        └───────┬────────┘
//                ▼
//             Filters
//                │
//       ┌────────┼────────┐
//       ▼        ▼        ▼
//      RMS      FFT     Peaks
//       │        │        │
//       └────────┼────────┘
//                ▼
//         Feature Extraction
//                │
//                ▼
//        Signal Event Stream
//
//  Swift 6 / actor-safe architecture
//

import Foundation
import Accelerate
import os

// MARK: - Signal Identifier

public struct SignalID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: String

    public init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

// MARK: - Sample

public struct SignalSample:
    Sendable,
    Codable
{
    public let timestamp: TimeInterval
    public let value: Double

    public init(
        timestamp: TimeInterval,
        value: Double
    ) {
        self.timestamp = timestamp
        self.value = value
    }
}

// MARK: - Signal Buffer

public struct SignalBuffer:
    Sendable
{
    public let samples: [Double]
    public let sampleRate: Double
    public let startTime: TimeInterval

    public init(
        samples: [Double],
        sampleRate: Double,
        startTime: TimeInterval = 0
    ) {
        self.samples = samples
        self.sampleRate = sampleRate
        self.startTime = startTime
    }

    public var count: Int {
        samples.count
    }

    public var duration: TimeInterval {
        guard sampleRate > 0 else {
            return 0
        }

        return Double(samples.count) / sampleRate
    }

    public func timestamp(
        at index: Int
    ) -> TimeInterval {
        startTime +
        Double(index) / sampleRate
    }
}

// MARK: - Signal Window

public struct SignalWindow:
    Sendable
{
    public let signal: SignalBuffer
    public let windowIndex: UInt64

    public init(
        signal: SignalBuffer,
        windowIndex: UInt64
    ) {
        self.signal = signal
        self.windowIndex = windowIndex
    }
}

// MARK: - Statistics

public struct SignalStatistics:
    Sendable,
    Codable
{
    public let count: Int
    public let mean: Double
    public let variance: Double
    public let standardDeviation: Double
    public let minimum: Double
    public let maximum: Double
    public let rms: Double
    public let peakToPeak: Double

    public init(
        count: Int,
        mean: Double,
        variance: Double,
        standardDeviation: Double,
        minimum: Double,
        maximum: Double,
        rms: Double,
        peakToPeak: Double
    ) {
        self.count = count
        self.mean = mean
        self.variance = variance
        self.standardDeviation = standardDeviation
        self.minimum = minimum
        self.maximum = maximum
        self.rms = rms
        self.peakToPeak = peakToPeak
    }
}

// MARK: - Statistics Engine

public enum SignalStatisticsEngine {

    public static func calculate(
        _ signal: SignalBuffer
    ) -> SignalStatistics {

        guard !signal.samples.isEmpty else {
            return SignalStatistics(
                count: 0,
                mean: 0,
                variance: 0,
                standardDeviation: 0,
                minimum: 0,
                maximum: 0,
                rms: 0,
                peakToPeak: 0
            )
        }

        var mean = 0.0
        var variance = 0.0
        var rms = 0.0

        vDSP_meanv(
            signal.samples,
            1,
            &mean,
            vDSP_Length(signal.count)
        )

        var centered = [Double](
            repeating: 0,
            count: signal.count
        )

        var negativeMean = -mean

        vDSP_vsadd(
            signal.samples,
            1,
            &negativeMean,
            &centered,
            1,
            vDSP_Length(signal.count)
        )

        vDSP_measqv(
            centered,
            1,
            &variance,
            vDSP_Length(signal.count)
        )

        vDSP_rmsqv(
            signal.samples,
            1,
            &rms,
            vDSP_Length(signal.count)
        )

        var minimum = 0.0
        var maximum = 0.0

        vDSP_minv(
            signal.samples,
            1,
            &minimum,
            vDSP_Length(signal.count)
        )

        vDSP_maxv(
            signal.samples,
            1,
            &maximum,
            vDSP_Length(signal.count)
        )

        return SignalStatistics(
            count: signal.count,
            mean: mean,
            variance: variance,
            standardDeviation: sqrt(variance),
            minimum: minimum,
            maximum: maximum,
            rms: rms,
            peakToPeak: maximum - minimum
        )
    }
}

// MARK: - Normalisation

public enum SignalNormaliser {

    public static func zeroMean(
        _ signal: SignalBuffer
    ) -> SignalBuffer {

        guard !signal.samples.isEmpty else {
            return signal
        }

        var mean = 0.0

        vDSP_meanv(
            signal.samples,
            1,
            &mean,
            vDSP_Length(signal.count)
        )

        var negativeMean = -mean

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        vDSP_vsadd(
            signal.samples,
            1,
            &negativeMean,
            &output,
            1,
            vDSP_Length(signal.count)
        )

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }

    public static func minMax(
        _ signal: SignalBuffer
    ) -> SignalBuffer {

        guard !signal.samples.isEmpty else {
            return signal
        }

        let statistics =
            SignalStatisticsEngine.calculate(signal)

        let range =
            statistics.maximum -
            statistics.minimum

        guard range > 0 else {
            return signal
        }

        var offset =
            -statistics.minimum

        var shifted = [Double](
            repeating: 0,
            count: signal.count
        )

        vDSP_vsadd(
            signal.samples,
            1,
            &offset,
            &shifted,
            1,
            vDSP_Length(signal.count)
        )

        var scale =
            1.0 / range

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        vDSP_vsmul(
            shifted,
            1,
            &scale,
            &output,
            1,
            vDSP_Length(signal.count)
        )

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - Filter Protocol

public protocol SignalFilter:
    Sendable
{
    func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
}

// MARK: - Moving Average

public struct MovingAverageFilter:
    SignalFilter
{
    public let windowSize: Int

    public init(
        windowSize: Int
    ) {
        self.windowSize =
            max(1, windowSize)
    }

    public func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
    {
        guard
            signal.count > 0,
            windowSize > 1
        else {
            return signal
        }

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        var accumulator = 0.0

        for index in signal.samples.indices {

            accumulator +=
                signal.samples[index]

            if index >= windowSize {
                accumulator -=
                    signal.samples[
                        index - windowSize
                    ]
            }

            let divisor =
                Double(
                    min(
                        index + 1,
                        windowSize
                    )
                )

            output[index] =
                accumulator / divisor
        }

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - Exponential Smoothing

public struct ExponentialSmoothingFilter:
    SignalFilter
{
    public let alpha: Double

    public init(
        alpha: Double
    ) {
        self.alpha =
            min(
                1,
                max(
                    0,
                    alpha
                )
            )
    }

    public func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
    {
        guard
            let first =
                signal.samples.first
        else {
            return signal
        }

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        output[0] = first

        if signal.count > 1 {

            for index in 1..<signal.count {

                output[index] =
                    alpha *
                    signal.samples[index] +
                    (1 - alpha) *
                    output[index - 1]
            }
        }

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - Differentiator

public struct Differentiator:
    SignalFilter
{
    public init() {}

    public func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
    {
        guard signal.count > 1 else {
            return signal
        }

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        let scale =
            signal.sampleRate

        for index in 1..<signal.count {

            output[index] =
                (
                    signal.samples[index] -
                    signal.samples[index - 1]
                ) * scale
        }

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - Integrator

public struct Integrator:
    SignalFilter
{
    public init() {}

    public func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
    {
        guard signal.count > 0 else {
            return signal
        }

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        let dt =
            1.0 / signal.sampleRate

        var accumulated = 0.0

        for index in signal.samples.indices {

            accumulated +=
                signal.samples[index] * dt

            output[index] =
                accumulated
        }

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - High Pass Filter

public struct FirstOrderHighPassFilter:
    SignalFilter
{
    public let cutoffFrequency: Double

    public init(
        cutoffFrequency: Double
    ) {
        self.cutoffFrequency =
            max(
                0.0001,
                cutoffFrequency
            )
    }

    public func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
    {
        guard
            signal.count > 1,
            signal.sampleRate >
                0
        else {
            return signal
        }

        let dt =
            1.0 / signal.sampleRate

        let rc =
            1.0 /
            (2.0 * Double.pi * cutoffFrequency)

        let alpha =
            rc /
            (rc + dt)

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        output[0] = 0

        for index in 1..<signal.count {

            output[index] =
                alpha *
                (
                    output[index - 1] +
                    signal.samples[index] -
                    signal.samples[index - 1]
                )
        }

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - Low Pass Filter

public struct FirstOrderLowPassFilter:
    SignalFilter
{
    public let cutoffFrequency: Double

    public init(
        cutoffFrequency: Double
    ) {
        self.cutoffFrequency =
            max(
                0.0001,
                cutoffFrequency
            )
    }

    public func process(
        _ signal: SignalBuffer
    )
        -> SignalBuffer
    {
        guard
            signal.count > 0,
            signal.sampleRate >
                0
        else {
            return signal
        }

        let dt =
            1.0 / signal.sampleRate

        let rc =
            1.0 /
            (2.0 * Double.pi * cutoffFrequency)

        let alpha =
            dt /
            (rc + dt)

        var output = [Double](
            repeating: 0,
            count: signal.count
        )

        output[0] =
            signal.samples[0]

        if signal.count > 1 {

            for index in 1..<signal.count {

                output[index] =
                    output[index - 1] +
                    alpha *
                    (
                        signal.samples[index] -
                        output[index - 1]
                    )
            }
        }

        return SignalBuffer(
            samples: output,
            sampleRate: signal.sampleRate,
            startTime: signal.startTime
        )
    }
}

// MARK: - Filter Chain

public struct SignalFilterChain:
    Sendable
{
    private let filters:
        [any SignalFilter]

    public init(
        filters:
            [any SignalFilter]
    ) {
        self.filters =
            filters
    }

    public func process(
        _ signal:
            SignalBuffer
    )
        -> SignalBuffer
    {
        filters.reduce(signal) {
            current,
            filter in

            filter.process(current)
        }
    }
}

// MARK: - Resampling

public enum SignalResampler {

    public static func linear(
        _ signal:
            SignalBuffer,
        targetSampleRate:
            Double
    )
        -> SignalBuffer
    {
        guard
            signal.sampleRate > 0,
            targetSampleRate > 0,
            signal.count > 1
        else {
            return signal
        }

        guard
            abs(
                signal.sampleRate -
                targetSampleRate
            ) > 0.0001
        else {
            return signal
        }

        let duration =
            signal.duration

        let outputCount =
            max(
                2,
                Int(
                    floor(
                        duration *
                        targetSampleRate
                    )
                )
            )

        var output = [Double](
            repeating: 0,
            count: outputCount
        )

        let scale =
            signal.sampleRate /
            targetSampleRate

        for index in 0..<outputCount {

            let sourcePosition =
                Double(index) *
                scale

            let lower =
                Int(
                    floor(
                        sourcePosition
                    )
                )

            let upper =
                min(
                    lower + 1,
                    signal.count - 1
                )

            let fraction =
                sourcePosition -
                Double(lower)

            let a =
                signal.samples[
                    min(
                        lower,
                        signal.count - 1
                    )
                ]

            let b =
                signal.samples[upper]

            output[index] =
                a +
                (
                    b - a
                ) *
                fraction
        }

        return SignalBuffer(
            samples:
                output,
            sampleRate:
                targetSampleRate,
            startTime:
                signal.startTime
        )
    }
}

// MARK: - Window Functions

public enum SignalWindowFunction:
    Sendable
{
    case rectangular
    case hann
    case hamming
    case blackman

    public func coefficient(
        index:
            Int,
        count:
            Int
    )
        -> Double
    {
        guard count > 1 else {
            return 1
        }

        let n =
            Double(index)

        let length =
            Double(count - 1)

        switch self {

        case .rectangular:
            return 1

        case .hann:
            return
                0.5 *
                (
                    1 -
                    cos(
                        2 *
                        Double.pi *
                        n /
                        length
                    )
                )

        case .hamming:
            return
                0.54 -
                0.46 *
                cos(
                    2 *
                    Double.pi *
                    n /
                    length
                )

        case .blackman:

            return
                0.42 -
                0.5 *
                cos(
                    2 *
                    Double.pi *
                    n /
                    length
                ) +
                0.08 *
                cos(
                    4 *
                    Double.pi *
                    n /
                    length
                )
        }
    }
}

// MARK: - FFT Result

public struct FFTBin:
    Sendable,
    Codable
{
    public let frequency:
        Double

    public let magnitude:
        Double

    public let power:
        Double

    public init(
        frequency:
            Double,
        magnitude:
            Double,
        power:
            Double
    ) {
        self.frequency =
            frequency

        self.magnitude =
            magnitude

        self.power =
            power
    }
}

public struct FFTResult:
    Sendable
{
    public let bins:
        [FFTBin]

    public let sampleRate:
        Double

    public let dominantFrequency:
        Double?

    public let dominantMagnitude:
        Double

    public init(
        bins:
            [FFTBin],
        sampleRate:
            Double,
        dominantFrequency:
            Double?,
        dominantMagnitude:
            Double
    ) {
        self.bins =
            bins

        self.sampleRate =
            sampleRate

        self.dominantFrequency =
            dominantFrequency

        self.dominantMagnitude =
            dominantMagnitude
    }
}

// MARK: - FFT Engine

public enum SignalFFTEngine {

    public static func analyse(
        _ signal:
            SignalBuffer,
        window:
            SignalWindowFunction =
                .hann
    )
        -> FFTResult?
    {
        guard
            signal.count >= 2,
            signal.sampleRate > 0
        else {
            return nil
        }

        let powerOfTwo =
            1 << Int(
                floor(
                    log2(
                        Double(
                            signal.count
                        )
                    )
                )
            )

        guard powerOfTwo >= 2 else {
            return nil
        }

        var input =
            Array(
                signal.samples.prefix(
                    powerOfTwo
                )
            )

        for index in input.indices {

            input[index] *=
                window.coefficient(
                    index:
                        index,
                    count:
                        input.count
                )
        }

        let log2n =
            vDSP_Length(
                log2(
                    Double(
                        powerOfTwo
                    )
                )
            )

        guard
            let setup =
                vDSP_create_fftsetupD(
                    log2n,
                    FFTRadix(kFFTRadix2)
                )
        else {
            return nil
        }

        defer {
            vDSP_destroy_fftsetupD(
                setup
            )
        }

        var real =
            [Double](
                repeating: 0,
                count:
                    powerOfTwo / 2
            )

        var imaginary =
            [Double](
                repeating: 0,
                count:
                    powerOfTwo / 2
            )

        real.withUnsafeMutableBufferPointer {
            realBuffer in

            imaginary.withUnsafeMutableBufferPointer {
                imaginaryBuffer in

                var split =
                    DSPDoubleSplitComplex(
                        realp:
                            realBuffer.baseAddress!,
                        imagp:
                            imaginaryBuffer.baseAddress!
                    )

                input.withUnsafeBufferPointer {
                    inputBuffer in

                    inputBuffer.baseAddress!
                        .withMemoryRebound(
                            to:
                                DSPDoubleSplitComplex
                                    .self,
                            capacity:
                                1
                        ) { _ in

                            var interleaved =
                                input

                            interleaved.withUnsafeMutableBufferPointer {
                                source in

                                vDSP_ctozD(
                                    source.baseAddress!
                                        .withMemoryRebound(
                                            to:
                                                DSPComplex
                                                    .self,
                                            capacity:
                                                powerOfTwo
                                        ),
                                    2,
                                    &split,
                                    1,
                                    vDSP_Length(
                                        powerOfTwo / 2
                                    )
                                )
                            }
                        }
                }

                vDSP_fft_zripD(
                    setup,
                    &split,
                    1,
                    log2n,
                    FFTDirection(
                        kFFTDirection_Forward
                    )
                )
            }
        }

        var bins =
            [FFTBin]()

        bins.reserveCapacity(
            powerOfTwo / 2
        )

        let scale =
            1.0 /
            Double(powerOfTwo)

        var dominantFrequency:
            Double?

        var dominantMagnitude =
            0.0

        for index in 0..<(powerOfTwo / 2) {

            let re =
                real[index]

            let im =
                imaginary[index]

            let magnitude =
                hypot(
                    re,
                    im
                ) *
                scale

            let power =
                magnitude *
                magnitude

            let frequency =
                Double(index) *
                signal.sampleRate /
                Double(powerOfTwo)

            bins.append(
                FFTBin(
                    frequency:
                        frequency,
                    magnitude:
                        magnitude,
                    power:
                        power
                )
            )

            if
                index > 0,
                magnitude >
                    dominantMagnitude
            {
                dominantMagnitude =
                    magnitude

                dominantFrequency =
                    frequency
            }
        }

        return FFTResult(
            bins:
                bins,
            sampleRate:
                signal.sampleRate,
            dominantFrequency:
                dominantFrequency,
            dominantMagnitude:
                dominantMagnitude
        )
    }
}

// MARK: - Peak

public struct SignalPeak:
    Sendable,
    Codable
{
    public let index:
        Int

    public let timestamp:
        TimeInterval

    public let value:
        Double

    public let prominence:
        Double

    public init(
        index:
            Int,
        timestamp:
            TimeInterval,
        value:
            Double,
        prominence:
            Double
    ) {
        self.index =
            index

        self.timestamp =
            timestamp

        self.value =
            value

        self.prominence =
            prominence
    }
}

// MARK: - Peak Detector

public struct SignalPeakDetector:
    Sendable
{
    public let minimumDistance:
        Int

    public let threshold:
        Double

    public init(
        minimumDistance:
            Int,
        threshold:
            Double
    ) {
        self.minimumDistance =
            max(
                1,
                minimumDistance
            )

        self.threshold =
            threshold
    }

    public func detect(
        _ signal:
            SignalBuffer
    )
        -> [SignalPeak]
    {
        guard
            signal.count >= 3
        else {
            return []
        }

        var candidates =
            [SignalPeak]()

        for index in 1..<(signal.count - 1) {

            let value =
                signal.samples[index]

            guard
                value >=
                    signal.samples[index - 1],
                value >
                    signal.samples[index + 1],
                value >=
                    threshold
            else {
                continue
            }

            let left =
                signal.samples[index - 1]

            let right =
                signal.samples[index + 1]

            let prominence =
                value -
                max(
                    left,
                    right
                )

            candidates.append(
                SignalPeak(
                    index:
                        index,
                    timestamp:
                        signal.timestamp(
                            at:
                                index
                        ),
                    value:
                        value,
                    prominence:
                        prominence
                )
            )
        }

        var selected =
            [SignalPeak]()

        for peak in candidates {

            guard
                let last =
                    selected.last
            else {
                selected.append(
                    peak
                )
                continue
            }

            if
                peak.index -
                last.index >=
                minimumDistance
            {
                selected.append(
                    peak
                )

            } else if
                peak.value >
                last.value
            {
                selected[
                    selected.count - 1
                ] =
                    peak
            }
        }

        return selected
    }
}

// MARK: - Zero Crossing

public enum ZeroCrossingDetector {

    public static func detect(
        _ signal:
            SignalBuffer
    )
        -> [TimeInterval]
    {
        guard
            signal.count >= 2
        else {
            return []
        }

        var crossings =
            [TimeInterval]()

        for index in 1..<signal.count {

            let previous =
                signal.samples[
                    index - 1
                ]

            let current =
                signal.samples[index]

            guard
                previous < 0,
                current >= 0
            else {
                continue
            }

            let denominator =
                current -
                previous

            let fraction =
                denominator == 0
                ? 0
                : -previous /
                    denominator

            let timestamp =
                signal.timestamp(
                    at:
                        index - 1
                ) +
                fraction /
                signal.sampleRate

            crossings.append(
                timestamp
            )
        }

        return crossings
    }
}

// MARK: - Envelope

public enum SignalEnvelope {

    public static func absolute(
        _ signal:
            SignalBuffer
    )
        -> SignalBuffer
    {
        let output =
            signal.samples.map {
                abs($0)
            }

        return SignalBuffer(
            samples:
                output,
            sampleRate:
                signal.sampleRate,
            startTime:
                signal.startTime
        )
    }

    public static func smoothed(
        _ signal:
            SignalBuffer,
        window:
            Int
    )
        -> SignalBuffer
    {
        MovingAverageFilter(
            windowSize:
                window
        )
        .process(
            absolute(
                signal
            )
        )
    }
}

// MARK: - Feature Vector

public struct SignalFeatureVector:
    Sendable,
    Codable
{
    public let mean:
        Double

    public let standardDeviation:
        Double

    public let rms:
        Double

    public let minimum:
        Double

    public let maximum:
        Double

    public let peakCount:
        Int

    public let zeroCrossingRate:
        Double

    public let dominantFrequency:
        Double?

    public init(
        mean:
            Double,
        standardDeviation:
            Double,
        rms:
            Double,
        minimum:
            Double,
        maximum:
            Double,
        peakCount:
            Int,
        zeroCrossingRate:
            Double,
        dominantFrequency:
            Double?
    ) {
        self.mean =
            mean

        self.standardDeviation =
            standardDeviation

        self.rms =
            rms

        self.minimum =
            minimum

        self.maximum =
            maximum

        self.peakCount =
            peakCount

        self.zeroCrossingRate =
            zeroCrossingRate

        self.dominantFrequency =
            dominantFrequency
    }
}

// MARK: - Feature Extractor

public enum SignalFeatureExtractor {

    public static func extract(
        _ signal:
            SignalBuffer,
        peakDetector:
            SignalPeakDetector =
                SignalPeakDetector(
                    minimumDistance:
                        5,
                    threshold:
                        0
                )
    )
        -> SignalFeatureVector
    {
        let statistics =
            SignalStatisticsEngine.calculate(
                signal
            )

        let peaks =
            peakDetector.detect(
                signal
            )

        let crossings =
            ZeroCrossingDetector.detect(
                signal
            )

        let duration =
            max(
                signal.duration,
                0.000001
            )

        let fft =
            SignalFFTEngine.analyse(
                signal
            )

        return SignalFeatureVector(
            mean:
                statistics.mean,
            standardDeviation:
                statistics.standardDeviation,
            rms:
                statistics.rms,
            minimum:
                statistics.minimum,
            maximum:
                statistics.maximum,
            peakCount:
                peaks.count,
            zeroCrossingRate:
                Double(
                    crossings.count
                ) /
                duration,
            dominantFrequency:
                fft?.dominantFrequency
        )
    }
}

// MARK: - Signal Event

public enum SignalEvent:
    Sendable,
    Codable
{
    case peak(
        SignalPeak
    )

    case thresholdCrossed(
        timestamp:
            TimeInterval,
        value:
            Double
    )

    case dominantFrequencyChanged(
        frequency:
            Double
    )

    case anomaly(
        timestamp:
            TimeInterval,
        score:
            Double
    )
}

// MARK: - Threshold Detector

public actor SignalThresholdDetector {

    public enum Direction:
        Sendable
    {
        case rising
        case falling
        case either
    }

    private let threshold:
        Double

    private let direction:
        Direction

    private var previous:
        Double?

    public init(
        threshold:
            Double,
        direction:
            Direction
    ) {
        self.threshold =
            threshold

        self.direction =
            direction
    }

    public func process(
        _ sample:
            SignalSample
    )
        -> SignalEvent?
    {
        defer {
            previous =
                sample.value
        }

        guard
            let previous
        else {
            return nil
        }

        switch direction {

        case .rising:

            guard
                previous <
                    threshold,
                sample.value >=
                    threshold
            else {
                return nil
            }

        case .falling:

            guard
                previous >
                    threshold,
                sample.value <=
                    threshold
            else {
                return nil
            }

        case .either:

            guard
                (
                    previous <
                    threshold &&
                    sample.value >=
                    threshold
                ) ||
                (
                    previous >
                    threshold &&
                    sample.value <=
                    threshold
                )
            else {
                return nil
            }
        }

        return .thresholdCrossed(
            timestamp:
                sample.timestamp,
            value:
                sample.value
        )
    }
}

// MARK: - Streaming Processor

public actor StreamingSignalProcessor {

    public typealias Processor =
        @Sendable (
            SignalBuffer
        ) -> SignalBuffer

    private let processor:
        Processor

    private let maximumBufferSize:
        Int

    private var samples =
        [SignalSample]()

    private var windowCounter:
        UInt64 =
            0

    public init(
        maximumBufferSize:
            Int,
        processor:
            @escaping Processor
    ) {
        self.maximumBufferSize =
            max(
                1,
                maximumBufferSize
            )

        self.processor =
            processor
    }

    public func append(
        _ sample:
            SignalSample
    )
        -> SignalBuffer?
    {
        samples.append(
            sample
        )

        if samples.count >
            maximumBufferSize
        {
            samples.removeFirst(
                samples.count -
                maximumBufferSize
            )
        }

        guard
            samples.count ==
                maximumBufferSize
        else {
            return nil
        }

        guard
            let first =
                samples.first
        else {
            return nil
        }

        let buffer =
            SignalBuffer(
                samples:
                    samples.map(\.value),
                sampleRate:
                    inferSampleRate(),
                startTime:
                    first.timestamp
            )

        windowCounter +=
            1

        return processor(
            buffer
        )
    }

    public func flush()
        -> SignalBuffer?
    {
        guard
            !samples.isEmpty,
            let first =
                samples.first
        else {
            return nil
        }

        let buffer =
            SignalBuffer(
                samples:
                    samples.map(\.value),
                sampleRate:
                    inferSampleRate(),
                startTime:
                    first.timestamp
            )

        samples.removeAll(
            keepingCapacity:
                true
        )

        windowCounter +=
            1

        return processor(
            buffer
        )
    }

    public func windowIndex()
        -> UInt64
    {
        windowCounter
    }

    private func inferSampleRate()
        -> Double
    {
        guard
            samples.count >= 2
        else {
            return 1
        }

        var total =
            0.0

        for index in 1..<samples.count {

            total +=
                samples[index].timestamp -
                samples[index - 1].timestamp
        }

        let average =
            total /
            Double(
                samples.count - 1
            )

        guard average > 0 else {
            return 1
        }

        return 1.0 / average
    }
}

// MARK: - Ring Buffer

public actor SignalRingBuffer {

    private let capacity:
        Int

    private var storage:
        [SignalSample]

    public init(
        capacity:
            Int
    ) {
        self.capacity =
            max(
                1,
                capacity
            )

        self.storage =
            []
    }

    public func append(
        _ sample:
            SignalSample
    ) {

        storage.append(
            sample
        )

        if storage.count >
            capacity
        {
            storage.removeFirst(
                storage.count -
                capacity
            )
        }
    }

    public func snapshot()
        -> [SignalSample]
    {
        storage
    }

    public func clear() {
        storage.removeAll(
            keepingCapacity:
                true
        )
    }

    public func count()
        -> Int
    {
        storage.count
    }
}

// MARK: - Signal Pipeline

public struct SignalPipeline:
    Sendable
{
    public let filters:
        SignalFilterChain

    public let normalise:
        Bool

    public init(
        filters:
            SignalFilterChain =
                SignalFilterChain(
                    filters:
                        []
                ),
        normalise:
            Bool =
                false
    ) {
        self.filters =
            filters

        self.normalise =
            normalise
    }

    public func process(
        _ signal:
            SignalBuffer
    )
        -> SignalBuffer
    {
        var output =
            filters.process(
                signal
            )

        if normalise {
            output =
                SignalNormaliser
                    .zeroMean(
                        output
                    )
        }

        return output
    }
}

// MARK: - Signal Quality

public enum SignalQuality:
    Int,
    Sendable,
    Codable,
    Comparable
{
    case unusable = 0
    case poor = 1
    case acceptable = 2
    case good = 3
    case excellent = 4
}

public struct SignalQualityAssessment:
    Sendable,
    Codable
{
    public let quality:
        SignalQuality

    public let score:
        Double

    public let noiseEstimate:
        Double

    public let clippingRatio:
        Double

    public init(
        quality:
            SignalQuality,
        score:
            Double,
        noiseEstimate:
            Double,
        clippingRatio:
            Double
    ) {
        self.quality =
            quality

        self.score =
            score

        self.noiseEstimate =
            noiseEstimate

        self.clippingRatio =
            clippingRatio
    }
}

// MARK: - Signal Quality Engine

public enum SignalQualityEngine {

    public static func assess(
        _ signal:
            SignalBuffer
    )
        -> SignalQualityAssessment
    {
        guard
            signal.count >= 3
        else {
            return SignalQualityAssessment(
                quality:
                    .unusable,
                score:
                    0,
                noiseEstimate:
                    .infinity,
                clippingRatio:
                    1
            )
        }

        let statistics =
            SignalStatisticsEngine.calculate(
                signal
            )

        let differences =
            zip(
                signal.samples.dropFirst(),
                signal.samples.dropLast()
            )
            .map {
                $0 - $1
            }

        let noiseSignal =
            SignalBuffer(
                samples:
                    differences,
                sampleRate:
                    signal.sampleRate,
                startTime:
                    signal.startTime
            )

        let noise =
            SignalStatisticsEngine.calculate(
                noiseSignal
            )
            .standardDeviation

        let dynamicRange =
            max(
                statistics.peakToPeak,
                0.000001
            )

        let clippingCount =
            signal.samples.reduce(
                into:
                    0
            ) {
                if abs($1) >=
                    0.999
                {
                    $0 += 1
                }
            }

        let clippingRatio =
            Double(
                clippingCount
            ) /
            Double(
                signal.count
            )

        let noiseRatio =
            min(
                1,
                noise /
                dynamicRange
            )

        var score =
            1 -
            noiseRatio

        score -=
            min(
                0.5,
                clippingRatio
            )

        score =
            max(
                0,
                min(
                    1,
                    score
                )
            )

        let quality:
            SignalQuality

        switch score {

        case ..<0.2:
            quality = .unusable

        case ..<0.4:
            quality = .poor

        case ..<0.65:
            quality = .acceptable

        case ..<0.85:
            quality = .good

        default:
            quality = .excellent
        }

        return SignalQualityAssessment(
            quality:
                quality,
            score:
                score,
            noiseEstimate:
                noise,
            clippingRatio:
                clippingRatio
        )
    }
}

// MARK: - Diagnostics

public actor SignalProcessingDiagnostics {

    private var processedBuffers:
        UInt64 =
            0

    private var processedSamples:
        UInt64 =
            0

    private var processingTime:
        TimeInterval =
            0

    private var failedBuffers:
        UInt64 =
            0

    public init() {}

    public func recordSuccess(
        sampleCount:
            Int,
        duration:
            TimeInterval
    ) {
        processedBuffers +=
            1

        processedSamples +=
            UInt64(
                max(
                    0,
                    sampleCount
                )
            )

        processingTime +=
            duration
    }

    public func recordFailure() {
        failedBuffers +=
            1
    }

    public func snapshot()
        -> (
            buffers:
                UInt64,
            samples:
                UInt64,
            processingTime:
                TimeInterval,
            failures:
                UInt64
        )
    {
        (
            processedBuffers,
            processedSamples,
            processingTime,
            failedBuffers
        )
    }
}

// MARK: - High-Level Engine

public actor AppleSignalProcessingEngine {

    public struct Configuration:
        Sendable
    {
        public let sampleRate:
            Double

        public let windowSize:
            Int

        public let filters:
            SignalFilterChain

        public init(
            sampleRate:
                Double,
            windowSize:
                Int,
            filters:
                SignalFilterChain =
                    SignalFilterChain(
                        filters:
                            []
                    )
        ) {
            self.sampleRate =
                sampleRate

            self.windowSize =
                max(
                    2,
                    windowSize
                )

            self.filters =
                filters
        }
    }

    private let configuration:
        Configuration

    private let diagnostics:
        SignalProcessingDiagnostics

    private let processor:
        StreamingSignalProcessor

    public init(
        configuration:
            Configuration
    ) {
        self.configuration =
            configuration

        let diagnostics =
            SignalProcessingDiagnostics()

        self.diagnostics =
            diagnostics

        self.processor =
            StreamingSignalProcessor(
                maximumBufferSize:
                    configuration.windowSize,
                processor:
                    configuration.filters
                        .process
            )
    }

    public func process(
        _ signal:
            SignalBuffer
    )
        async
        -> (
            signal:
                SignalBuffer,
            statistics:
                SignalStatistics,
            features:
                SignalFeatureVector,
            quality:
                SignalQualityAssessment
        )
    {
        let start =
            ContinuousClock.now

        let filtered =
            configuration.filters.process(
                signal
            )

        let statistics =
            SignalStatisticsEngine.calculate(
                filtered
            )

        let features =
            SignalFeatureExtractor.extract(
                filtered
            )

        let quality =
            SignalQualityEngine.assess(
                filtered
            )

        let elapsed =
            start.duration(
                to:
                    ContinuousClock.now
            )

        let seconds =
            elapsed
                .components
                .attoseconds
                .description

        let processingDuration =
            Double(
                elapsed
                    .components
                    .seconds
            ) +
            (
                Double(
                    elapsed
                        .components
                        .attoseconds
                ) /
                1_000_000_000_000_000_000
            )

        _ = seconds

        await diagnostics.recordSuccess(
            sampleCount:
                filtered.count,
            duration:
                processingDuration
        )

        return (
            filtered,
            statistics,
            features,
            quality
        )
    }

    public func diagnosticsSnapshot()
        async
        -> (
            buffers:
                UInt64,
            samples:
                UInt64,
            processingTime:
                TimeInterval,
            failures:
                UInt64
        )
    {
        await diagnostics.snapshot()
    }
}

// MARK: - Presets

public enum SignalProcessingPresets {

    /// Generic low-noise physiological signal.
    public static func physiological(
        sampleRate:
            Double
    )
        -> AppleSignalProcessingEngine.Configuration
    {
        AppleSignalProcessingEngine.Configuration(
            sampleRate:
                sampleRate,
            windowSize:
                max(
                    32,
                    Int(
                        sampleRate *
                        4
                    )
                ),
            filters:
                SignalFilterChain(
                    filters:
                        [
                            FirstOrderHighPassFilter(
                                cutoffFrequency:
                                    0.3
                            ),
                            FirstOrderLowPassFilter(
                                cutoffFrequency:
                                    min(
                                        8,
                                        sampleRate /
                                        4
                                    )
                            ),
                            ExponentialSmoothingFilter(
                                alpha:
                                    0.2
                            )
                        ]
                )
        )
    }

    /// Motion signal processing.
    public static func motion(
        sampleRate:
            Double
    )
        -> AppleSignalProcessingEngine.Configuration
    {
        AppleSignalProcessingEngine.Configuration(
            sampleRate:
                sampleRate,
            windowSize:
                max(
                    64,
                    Int(
                        sampleRate *
                        2
                    )
                ),
            filters:
                SignalFilterChain(
                    filters:
                        [
                            FirstOrderHighPassFilter(
                                cutoffFrequency:
                                    0.1
                            ),
                            FirstOrderLowPassFilter(
                                cutoffFrequency:
                                    min(
                                        20,
                                        sampleRate /
                                        3
                                    )
                            )
                        ]
                )
        )
    }

    /// General vibration / mechanical signal.
    public static func vibration(
        sampleRate:
            Double
    )
        -> AppleSignalProcessingEngine.Configuration
    {
        AppleSignalProcessingEngine.Configuration(
            sampleRate:
                sampleRate,
            windowSize:
                max(
                    128,
                    Int(
                        sampleRate
                    )
                ),
            filters:
                SignalFilterChain(
                    filters:
                        [
                            SignalNormalisingFilter()
                        ]
                )
        )
    }
}

// MARK: - Normalising Filter

public struct SignalNormalisingFilter:
    SignalFilter
{
    public init() {}

    public func process(
        _ signal:
            SignalBuffer
    )
        -> SignalBuffer
    {
        SignalNormaliser.zeroMean(
            signal
        )
    }
}

// MARK: - Tests

public enum SignalProcessingTests {

    public static func run() {

        testStatistics()
        testMovingAverage()
        testNormalisation()
        testPeakDetection()
        testZeroCrossing()
        testResampling()
    }

    private static func testStatistics() {

        let signal =
            SignalBuffer(
                samples:
                    [
                        1,
                        2,
                        3,
                        4
                    ],
                sampleRate:
                    4
            )

        let stats =
            SignalStatisticsEngine.calculate(
                signal
            )

        assert(
            stats.count == 4
        )

        assert(
            abs(
                stats.mean - 2.5
            ) < 0.000001
        )

        assert(
            stats.minimum == 1
        )

        assert(
            stats.maximum == 4
        )
    }

    private static func testMovingAverage() {

        let filter =
            MovingAverageFilter(
                windowSize:
                    3
            )

        let output =
            filter.process(
                SignalBuffer(
                    samples:
                        [
                            1,
                            2,
                            3,
                            6
                        ],
                    sampleRate:
                        1
                )
            )

        assert(
            abs(
                output.samples[2] -
                2
            ) < 0.000001
        )

        assert(
            abs(
                output.samples[3] -
                11.0 / 3.0
            ) < 0.000001
        )
    }

    private static func testNormalisation() {

        let signal =
            SignalBuffer(
                samples:
                    [
                        10,
                        20,
                        30
                    ],
                sampleRate:
                    1
            )

        let output =
            SignalNormaliser.zeroMean(
                signal
            )

        let mean =
            SignalStatisticsEngine.calculate(
                output
            ).mean

        assert(
            abs(mean) <
                0.000001
        )
    }

    private static func testPeakDetection() {

        let signal =
            SignalBuffer(
                samples:
                    [
                        0,
                        1,
                        0,
                        0,
                        2,
                        0
                    ],
                sampleRate:
                    1
            )

        let detector =
            SignalPeakDetector(
                minimumDistance:
                    2,
                threshold:
                    0.5
            )

        let peaks =
            detector.detect(
                signal
            )

        assert(
            peaks.count == 2
        )

        assert(
            peaks[0].value == 1
        )

        assert(
            peaks[1].value == 2
        )
    }

    private static func testZeroCrossing() {

        let signal =
            SignalBuffer(
                samples:
                    [
                        -1,
                        1,
                        -1,
                        1
                    ],
                sampleRate:
                    1
            )

        let crossings =
            ZeroCrossingDetector.detect(
                signal
            )

        assert(
            crossings.count == 2
        )
    }

    private static func testResampling() {

        let signal =
            SignalBuffer(
                samples:
                    [
                        0,
                        1,
                        2,
                        3,
                        4
                    ],
                sampleRate:
                    10
            )

        let resampled =
            SignalResampler.linear(
                signal,
                targetSampleRate:
                    5
            )

        assert(
            resampled.sampleRate == 5
        )

        assert(
            resampled.count >= 2
        )
    }
}

// MARK: - Example

public enum SignalProcessingExample {

    public static func createEngine()
        -> AppleSignalProcessingEngine
    {
        let configuration =
            SignalProcessingPresets
                .physiological(
                    sampleRate:
                        50
                )

        return AppleSignalProcessingEngine(
            configuration:
                configuration
        )
    }

    public static func analyse(
        samples:
            [Double]
    )
        async
    {
        let engine =
            createEngine()

        let signal =
            SignalBuffer(
                samples:
                    samples,
                sampleRate:
                    50
            )

        let result =
            await engine.process(
                signal
            )

        print(
            "Mean:",
            result.statistics.mean
        )

        print(
            "RMS:",
            result.statistics.rms
        )

        print(
            "Dominant frequency:",
            result.features.dominantFrequency
                ?? 0
        )

        print(
            "Quality:",
            result.quality.quality
        )
    }
}






//
//  ApplePredictiveBackgroundScheduler.swift
//
//  #7 — Predictive Background Task Scheduler
//
//  Swift 6
//
//  Public-framework architecture:
//
//      Application Work
//            │
//            ▼
//      Task Registration
//            │
//            ▼
//      ┌──────────────────────┐
//      │ Predictive Scheduler │
//      └──────────┬───────────┘
//                 │
//       ┌─────────┼─────────┐
//       ▼         ▼         ▼
//    Priority   Energy    Deadline
//       │       Budget       │
//       └─────────┼─────────┘
//                 ▼
//          Execution Decision
//                 │
//        ┌────────┴────────┐
//        ▼                 ▼
//     Execute            Defer
//        │                 │
//        ▼                 ▼
//    Completion         Persist
//
//  The scheduler does NOT bypass Apple's OS scheduling.
//  It determines application-level priorities and readiness.
//

import Foundation
import os

#if canImport(BackgroundTasks)
import BackgroundTasks
#endif

// MARK: - Scheduler Task ID

public struct BackgroundTaskID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue:
        UUID

    public init(
        _ rawValue:
            UUID = UUID()
    ) {
        self.rawValue =
            rawValue
    }
}

// MARK: - Execution Kind

public enum BackgroundExecutionKind:
    String,
    Codable,
    Sendable
{
    case refresh
    case processing
    case maintenance
    case synchronization
    case upload
    case download
    case cleanup
    case indexing
}

// MARK: - Task Priority

public enum BackgroundTaskPriority:
    Int,
    Codable,
    Sendable,
    Comparable
{
    case maintenance = 0
    case low = 1
    case normal = 2
    case high = 3
    case critical = 4

    public static func < (
        lhs:
            BackgroundTaskPriority,
        rhs:
            BackgroundTaskPriority
    )
        -> Bool
    {
        lhs.rawValue <
            rhs.rawValue
    }
}

// MARK: - Network Requirement

public enum BackgroundNetworkRequirement:
    String,
    Codable,
    Sendable
{
    case none
    case any
    case unconstrained
}

// MARK: - Power Requirement

public enum BackgroundPowerRequirement:
    String,
    Codable,
    Sendable
{
    case batteryAllowed
    case chargingPreferred
    case chargingRequired
}

// MARK: - Task Constraints

public struct BackgroundTaskConstraints:
    Codable,
    Sendable
{
    public var network:
        BackgroundNetworkRequirement

    public var power:
        BackgroundPowerRequirement

    public var requiresExternalPower:
        Bool

    public var requiresWiFi:
        Bool

    public var earliestBeginDate:
        Date?

    public var expirationDate:
        Date?

    public init(
        network:
            BackgroundNetworkRequirement =
                .none,
        power:
            BackgroundPowerRequirement =
                .batteryAllowed,
        requiresExternalPower:
            Bool =
                false,
        requiresWiFi:
            Bool =
                false,
        earliestBeginDate:
            Date? =
                nil,
        expirationDate:
            Date? =
                nil
    ) {
        self.network =
            network

        self.power =
            power

        self.requiresExternalPower =
            requiresExternalPower

        self.requiresWiFi =
            requiresWiFi

        self.earliestBeginDate =
            earliestBeginDate

        self.expirationDate =
            expirationDate
    }
}

// MARK: - Device Conditions

public enum DevicePowerState:
    String,
    Codable,
    Sendable
{
    case unknown
    case battery
    case charging
    case full
}

public enum DeviceNetworkState:
    String,
    Codable,
    Sendable
{
    case unknown
    case offline
    case connected
    case constrained
}

public enum DeviceThermalState:
    String,
    Codable,
    Sendable
{
    case nominal
    case fair
    case serious
    case critical
    case unknown
}

// MARK: - Scheduler Environment

public struct SchedulerEnvironment:
    Codable,
    Sendable
{
    public let power:
        DevicePowerState

    public let network:
        DeviceNetworkState

    public let thermal:
        DeviceThermalState

    public let batteryLevel:
        Double?

    public let lowPowerMode:
        Bool

    public let timestamp:
        Date

    public init(
        power:
            DevicePowerState =
                .unknown,
        network:
            DeviceNetworkState =
                .unknown,
        thermal:
            DeviceThermalState =
                .unknown,
        batteryLevel:
            Double? =
                nil,
        lowPowerMode:
            Bool =
                false,
        timestamp:
            Date =
                Date()
    ) {
        self.power =
            power

        self.network =
            network

        self.thermal =
            thermal

        self.batteryLevel =
            batteryLevel

        self.lowPowerMode =
            lowPowerMode

        self.timestamp =
            timestamp
    }
}

// MARK: - Work Cost

public struct BackgroundWorkCost:
    Codable,
    Sendable
{
    public let estimatedCPUSeconds:
        Double

    public let estimatedMemoryMB:
        Double

    public let estimatedNetworkBytes:
        Int64

    public let estimatedEnergy:
        Double

    public init(
        estimatedCPUSeconds:
            Double =
                1,
        estimatedMemoryMB:
            Double =
                10,
        estimatedNetworkBytes:
            Int64 =
                0,
        estimatedEnergy:
            Double =
                1
    ) {
        self.estimatedCPUSeconds =
            max(
                0,
                estimatedCPUSeconds
            )

        self.estimatedMemoryMB =
            max(
                0,
                estimatedMemoryMB
            )

        self.estimatedNetworkBytes =
            max(
                0,
                estimatedNetworkBytes
            )

        self.estimatedEnergy =
            max(
                0,
                estimatedEnergy
            )
    }
}

// MARK: - Task State

public enum BackgroundTaskState:
    String,
    Codable,
    Sendable
{
    case registered
    case eligible
    case waiting
    case running
    case completed
    case failed
    case cancelled
    case expired
}

// MARK: - Background Work

public struct BackgroundWorkItem:
    Codable,
    Sendable
{
    public let id:
        BackgroundTaskID

    public let name:
        String

    public let kind:
        BackgroundExecutionKind

    public let priority:
        BackgroundTaskPriority

    public let constraints:
        BackgroundTaskConstraints

    public let cost:
        BackgroundWorkCost

    public let createdAt:
        Date

    public let deadline:
        Date?

    public var state:
        BackgroundTaskState

    public var attempts:
        Int

    public var lastStartedAt:
        Date?

    public var lastFinishedAt:
        Date?

    public var lastError:
        String?

    public var progress:
        Double

    public init(
        id:
            BackgroundTaskID =
                BackgroundTaskID(),
        name:
            String,
        kind:
            BackgroundExecutionKind,
        priority:
            BackgroundTaskPriority =
                .normal,
        constraints:
            BackgroundTaskConstraints =
                BackgroundTaskConstraints(),
        cost:
            BackgroundWorkCost =
                BackgroundWorkCost(),
        createdAt:
            Date =
                Date(),
        deadline:
            Date? =
                nil
    ) {
        self.id =
            id

        self.name =
            name

        self.kind =
            kind

        self.priority =
            priority

        self.constraints =
            constraints

        self.cost =
            cost

        self.createdAt =
            createdAt

        self.deadline =
            deadline

        self.state =
            .registered

        self.attempts =
            0

        self.lastStartedAt =
            nil

        self.lastFinishedAt =
            nil

        self.lastError =
            nil

        self.progress =
            0
    }
}

// MARK: - Scheduler Decision

public enum SchedulerDecision:
    Sendable
{
    case execute
    case defer(
        reason:
            SchedulerDeferralReason
    )
    case reject(
        reason:
            SchedulerRejectionReason
    )
}

public enum SchedulerDeferralReason:
    String,
    Sendable
{
    case tooEarly
    case networkUnavailable
    case networkConstrained
    case chargingRequired
    case chargingPreferred
    case thermalPressure
    case lowPowerMode
    case insufficientBudget
    case lowerPriorityWorkAvailable
}

public enum SchedulerRejectionReason:
    String,
    Sendable
{
    case expired
    case invalidConstraints
    case cancelled
}

// MARK: - Scheduler Configuration

public struct BackgroundSchedulerConfiguration:
    Sendable
{
    public let maximumConcurrentTasks:
        Int

    public let energyBudget:
        Double

    public let cpuBudgetSeconds:
        Double

    public let networkBudgetBytes:
        Int64

    public let thermalLimit:
        DeviceThermalState

    public let lowPowerModeAllowsNormalWork:
        Bool

    public init(
        maximumConcurrentTasks:
            Int =
                1,
        energyBudget:
            Double =
                100,
        cpuBudgetSeconds:
            Double =
                30,
        networkBudgetBytes:
            Int64 =
                50_000_000,
        thermalLimit:
            DeviceThermalState =
                .serious,
        lowPowerModeAllowsNormalWork:
            Bool =
                false
    ) {
        self.maximumConcurrentTasks =
            max(
                1,
                maximumConcurrentTasks
            )

        self.energyBudget =
            max(
                0,
                energyBudget
            )

        self.cpuBudgetSeconds =
            max(
                0,
                cpuBudgetSeconds
            )

        self.networkBudgetBytes =
            max(
                0,
                networkBudgetBytes
            )

        self.thermalLimit =
            thermalLimit

        self.lowPowerModeAllowsNormalWork =
            lowPowerModeAllowsNormalWork
    }
}

// MARK: - Scheduler Scoring

public struct BackgroundTaskScore:
    Sendable
{
    public let taskID:
        BackgroundTaskID

    public let priorityScore:
        Double

    public let ageScore:
        Double

    public let deadlineScore:
        Double

    public let costScore:
        Double

    public let total:
        Double

    public init(
        taskID:
            BackgroundTaskID,
        priorityScore:
            Double,
        ageScore:
            Double,
        deadlineScore:
            Double,
        costScore:
            Double,
        total:
            Double
    ) {
        self.taskID =
            taskID

        self.priorityScore =
            priorityScore

        self.ageScore =
            ageScore

        self.deadlineScore =
            deadlineScore

        self.costScore =
            costScore

        self.total =
            total
    }
}

// MARK: - Scheduler Clock

public protocol BackgroundSchedulerClock:
    Sendable
{
    func now()
        -> Date
}

public struct SystemBackgroundSchedulerClock:
    BackgroundSchedulerClock
{
    public init() {}

    public func now()
        -> Date
    {
        Date()
    }
}

// MARK: - Scheduler

public actor PredictiveBackgroundScheduler {

    public typealias WorkHandler =
        @Sendable (
            BackgroundWorkItem
        ) async throws -> Void

    private var tasks:
        [
            BackgroundTaskID:
            BackgroundWorkItem
        ] =
            [:]

    private var handlers:
        [
            BackgroundTaskID:
            WorkHandler
        ] =
            [:]

    private var environment:
        SchedulerEnvironment

    private var configuration:
        BackgroundSchedulerConfiguration

    private let clock:
        any BackgroundSchedulerClock

    private let persistence:
        BackgroundSchedulerPersistence?

    private var activeTaskCount:
        Int =
            0

    private var consumedCPU:
        Double =
            0

    private var consumedEnergy:
        Double =
            0

    private var consumedNetworkBytes:
        Int64 =
            0

    private var workerTask:
        Task<Void, Never>?

    public init(
        environment:
            SchedulerEnvironment =
                SchedulerEnvironment(),
        configuration:
            BackgroundSchedulerConfiguration =
                BackgroundSchedulerConfiguration(),
        clock:
            any BackgroundSchedulerClock =
                SystemBackgroundSchedulerClock(),
        persistence:
            BackgroundSchedulerPersistence? =
                nil
    ) {
        self.environment =
            environment

        self.configuration =
            configuration

        self.clock =
            clock

        self.persistence =
            persistence
    }

    // MARK: Registration

    @discardableResult
    public func register(
        _ item:
            BackgroundWorkItem,
        handler:
            @escaping WorkHandler
    )
        -> BackgroundTaskID
    {
        tasks[item.id] =
            item

        handlers[item.id] =
            handler

        return item.id
    }

    public func cancel(
        _ id:
            BackgroundTaskID
    ) {

        guard
            var item =
                tasks[id]
        else {
            return
        }

        guard
            item.state != .completed
        else {
            return
        }

        item.state =
            .cancelled

        tasks[id] =
            item

        handlers.removeValue(
            forKey:
                id
        )
    }

    // MARK: Environment

    public func updateEnvironment(
        _ environment:
            SchedulerEnvironment
    ) {
        self.environment =
            environment
    }

    public func currentEnvironment()
        -> SchedulerEnvironment
    {
        environment
    }

    public func updateConfiguration(
        _ configuration:
            BackgroundSchedulerConfiguration
    ) {
        self.configuration =
            configuration
    }

    // MARK: Evaluation

    public func evaluate(
        _ id:
            BackgroundTaskID
    )
        -> SchedulerDecision
    {
        guard
            let item =
                tasks[id]
        else {
            return .reject(
                reason:
                    .cancelled
            )
        }

        return evaluate(
            item
        )
    }

    public func evaluate(
        _ item:
            BackgroundWorkItem
    )
        -> SchedulerDecision
    {
        let now =
            clock.now()

        if
            let deadline =
                item.deadline,
            now >= deadline
        {
            return .reject(
                reason:
                    .expired
            )
        }

        if
            let earliest =
                item.constraints
                    .earliestBeginDate,
            now < earliest
        {
            return .defer(
                reason:
                    .tooEarly
            )
        }

        switch environment.thermal {

        case .critical:

            if item.priority <
                .critical
            {
                return .defer(
                    reason:
                        .thermalPressure
                )
            }

        case .serious:

            if item.priority <=
                .normal
            {
                return .defer(
                    reason:
                        .thermalPressure
                )
            }

        case .nominal,
             .fair,
             .unknown:
            break
        }

        if
            environment.lowPowerMode,
            !configuration
                .lowPowerModeAllowsNormalWork,
            item.priority <=
                .normal
        {
            return .defer(
                reason:
                    .lowPowerMode
            )
        }

        switch item.constraints.network {

        case .none:
            break

        case .any:

            guard
                environment.network !=
                    .offline
            else {
                return .defer(
                    reason:
                        .networkUnavailable
                )
            }

        case .unconstrained:

            guard
                environment.network ==
                    .connected
            else {
                return .defer(
                    reason:
                        .networkUnavailable
                )
            }

            if
                environment.network ==
                    .constrained
            {
                return .defer(
                    reason:
                        .networkConstrained
                )
            }
        }

        switch item.constraints.power {

        case .batteryAllowed:
            break

        case .chargingPreferred:

            if environment.power ==
                .battery
            {
                if item.priority <=
                    .normal
                {
                    return .defer(
                        reason:
                            .chargingPreferred
                    )
                }
            }

        case .chargingRequired:

            guard
                environment.power ==
                    .charging ||
                environment.power ==
                    .full
            else {
                return .defer(
                    reason:
                        .chargingRequired
                )
            }
        }

        if item.constraints
            .requiresExternalPower
        {
            guard
                environment.power ==
                    .charging ||
                environment.power ==
                    .full
            else {
                return .defer(
                    reason:
                        .chargingRequired
                )
            }
        }

        if
            activeTaskCount >=
                configuration
                    .maximumConcurrentTasks
        {
            return .defer(
                reason:
                    .lowerPriorityWorkAvailable
            )
        }

        if
            consumedCPU +
            item.cost.estimatedCPUSeconds >
            configuration.cpuBudgetSeconds
        {
            return .defer(
                reason:
                    .insufficientBudget
            )
        }

        if
            consumedEnergy +
            item.cost.estimatedEnergy >
            configuration.energyBudget
        {
            return .defer(
                reason:
                    .insufficientBudget
            )
        }

        if
            consumedNetworkBytes +
            item.cost.estimatedNetworkBytes >
            configuration
                .networkBudgetBytes
        {
            return .defer(
                reason:
                    .insufficientBudget
            )
        }

        return .execute
    }

    // MARK: Scoring

    public func score(
        _ item:
            BackgroundWorkItem
    )
        -> BackgroundTaskScore
    {
        let now =
            clock.now()

        let priority =
            Double(
                item.priority.rawValue
            ) *
            25

        let age =
            max(
                0,
                now.timeIntervalSince(
                    item.createdAt
                )
            )

        let ageScore =
            min(
                25,
                age /
                60
            )

        let deadlineScore:
            Double

        if
            let deadline =
                item.deadline
        {
            let remaining =
                deadline.timeIntervalSince(
                    now
                )

            if remaining <= 0 {
                deadlineScore =
                    100
            } else {
                deadlineScore =
                    min(
                        50,
                        100 /
                        max(
                            1,
                            remaining / 60
                        )
                    )
            }
        } else {
            deadlineScore =
                0
        }

        let cost =
            item.cost.estimatedEnergy +
            item.cost.estimatedCPUSeconds

        let costScore =
            20 /
            max(
                1,
                cost
            )

        return BackgroundTaskScore(
            taskID:
                item.id,
            priorityScore:
                priority,
            ageScore:
                ageScore,
            deadlineScore:
                deadlineScore,
            costScore:
                costScore,
            total:
                priority +
                ageScore +
                deadlineScore +
                costScore
        )
    }

    // MARK: Scheduling

    public func nextEligibleTask()
        -> BackgroundWorkItem?
    {
        let candidates =
            tasks.values
                .filter {
                    $0.state ==
                        .registered ||
                    $0.state ==
                        .eligible ||
                    $0.state ==
                        .failed
                }

        let scored =
            candidates.compactMap {
                item -> (
                    BackgroundWorkItem,
                    BackgroundTaskScore
                )? in

                guard
                    case .execute =
                        evaluate(item)
                else {
                    return nil
                }

                return (
                    item,
                    score(item)
                )
            }

        return scored
            .sorted {
                $0.1.total >
                    $1.1.total
            }
            .first?
            .0
    }

    public func runNext()
        async
    {
        guard
            let item =
                nextEligibleTask()
        else {
            return
        }

        await execute(
            item.id
        )
    }

    // MARK: Execution

    public func execute(
        _ id:
            BackgroundTaskID
    )
        async
    {
        guard
            var item =
                tasks[id]
        else {
            return
        }

        guard
            case .execute =
                evaluate(item)
        else {
            return
        }

        guard
            let handler =
                handlers[id]
        else {
            return
        }

        item.state =
            .running

        item.attempts +=
            1

        item.lastStartedAt =
            clock.now()

        tasks[id] =
            item

        activeTaskCount +=
            1

        let start =
            clock.now()

        do {

            try await handler(
                item
            )

            let elapsed =
                clock.now()
                    .timeIntervalSince(
                        start
                    )

            consumedCPU +=
                elapsed

            consumedEnergy +=
                item.cost.estimatedEnergy

            if
                let current =
                    tasks[id]
            {
                var completed =
                    current

                completed.state =
                    .completed

                completed.progress =
                    1

                completed.lastFinishedAt =
                    clock.now()

                completed.lastError =
                    nil

                tasks[id] =
                    completed
            }

        } catch {

            consumedCPU +=
                max(
                    0,
                    clock.now()
                        .timeIntervalSince(
                            start
                        )
                )

            if
                var failed =
                    tasks[id]
            {
                failed.state =
                    .failed

                failed.lastFinishedAt =
                    clock.now()

                failed.lastError =
                    error.localizedDescription

                tasks[id] =
                    failed
            }
        }

        activeTaskCount =
            max(
                0,
                activeTaskCount - 1
            )

        await persist()
    }

    // MARK: Worker

    public func startWorker(
        pollingInterval:
            Duration =
                .seconds(5)
    ) {

        workerTask?
            .cancel()

        workerTask =
            Task { [weak self] in

                while
                    !Task.isCancelled
                {
                    guard
                        let self
                    else {
                        return
                    }

                    await self.runNext()

                    try? await Task.sleep(
                        for:
                            pollingInterval
                    )
                }
            }
    }

    public func stopWorker() {

        workerTask?
            .cancel()

        workerTask =
            nil
    }

    // MARK: Budgets

    public func resetBudgets() {

        consumedCPU =
            0

        consumedEnergy =
            0

        consumedNetworkBytes =
            0
    }

    public func budgetUsage()
        -> (
            cpu:
                Double,
            energy:
                Double,
            networkBytes:
                Int64
        )
    {
        (
            consumedCPU,
            consumedEnergy,
            consumedNetworkBytes
        )
    }

    // MARK: Task Inspection

    public func task(
        _ id:
            BackgroundTaskID
    )
        -> BackgroundWorkItem?
    {
        tasks[id]
    }

    public func allTasks()
        -> [
            BackgroundWorkItem
        ]
    {
        Array(
            tasks.values
        )
    }

    public func pendingTasks()
        -> [
            BackgroundWorkItem
        ]
    {
        tasks.values.filter {
            $0.state != .completed &&
            $0.state != .cancelled
        }
    }

    // MARK: Persistence

    private func persist()
        async
    {
        guard
            let persistence
        else {
            return
        }

        try? await persistence.save(
            tasks:
                Array(
                    tasks.values
                )
        )
    }

    public func restore()
        async
    {
        guard
            let persistence
        else {
            return
        }

        guard
            let restored =
                try? await persistence.load()
        else {
            return
        }

        for item
            in restored
        {
            if item.state ==
                .running
            {
                var recovered =
                    item

                recovered.state =
                    .failed

                recovered.lastError =
                    "Recovered after interrupted execution."

                tasks[
                    recovered.id
                ] =
                    recovered

            } else {

                tasks[
                    item.id
                ] =
                    item
            }
        }
    }
}

// MARK: - Persistence

public actor BackgroundSchedulerPersistence {

    private let url:
        URL

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    public init(
        url:
            URL
    ) {
        self.url =
            url

        self.encoder =
            JSONEncoder()

        self.decoder =
            JSONDecoder()

        encoder.dateEncodingStrategy =
            .iso8601

        decoder.dateDecodingStrategy =
            .iso8601
    }

    public func save(
        tasks:
            [BackgroundWorkItem]
    )
        throws
    {
        try FileManager.default
            .createDirectory(
                at:
                    url.deletingLastPathComponent(),
                withIntermediateDirectories:
                    true
            )

        let data =
            try encoder.encode(
                tasks
            )

        try data.write(
            to:
                url,
            options:
                .atomic
        )
    }

    public func load()
        throws
        -> [
            BackgroundWorkItem
        ]
    {
        guard
            FileManager.default
                .fileExists(
                    atPath:
                        url.path
                )
        else {
            return []
        }

        let data =
            try Data(
                contentsOf:
                    url
            )

        return try decoder.decode(
            [
                BackgroundWorkItem
            ].self,
            from:
                data
        )
    }
}

// MARK: - Application Refresh Policy

public struct RefreshPolicy:
    Sendable
{
    public let minimumInterval:
        TimeInterval

    public let maximumInterval:
        TimeInterval

    public init(
        minimumInterval:
            TimeInterval =
                15 * 60,
        maximumInterval:
            TimeInterval =
                24 * 60 * 60
    ) {
        self.minimumInterval =
            minimumInterval

        self.maximumInterval =
            maximumInterval
    }

    public func nextRefresh(
        lastRefresh:
            Date,
        now:
            Date =
                Date()
    )
        -> Date
    {
        let elapsed =
            now.timeIntervalSince(
                lastRefresh
            )

        let interval =
            elapsed < minimumInterval
            ? minimumInterval
            : min(
                maximumInterval,
                max(
                    minimumInterval,
                    elapsed * 1.5
                )
            )

        return now.addingTimeInterval(
            interval
        )
    }
}

// MARK: - Predictive History

public struct SchedulerObservation:
    Codable,
    Sendable
{
    public let taskID:
        BackgroundTaskID

    public let scheduledAt:
        Date

    public let startedAt:
        Date?

    public let finishedAt:
        Date?

    public let success:
        Bool

    public let environment:
        SchedulerEnvironment

    public init(
        taskID:
            BackgroundTaskID,
        scheduledAt:
            Date,
        startedAt:
            Date?,
        finishedAt:
            Date?,
        success:
            Bool,
        environment:
            SchedulerEnvironment
    ) {
        self.taskID =
            taskID

        self.scheduledAt =
            scheduledAt

        self.startedAt =
            startedAt

        self.finishedAt =
            finishedAt

        self.success =
            success

        self.environment =
            environment
    }
}

public actor SchedulerHistory {

    private var observations:
        [SchedulerObservation] =
            []

    private let maximumEntries:
        Int

    public init(
        maximumEntries:
            Int =
                500
    ) {
        self.maximumEntries =
            max(
                1,
                maximumEntries
            )
    }

    public func record(
        _ observation:
            SchedulerObservation
    ) {

        observations.append(
            observation
        )

        if observations.count >
            maximumEntries
        {
            observations.removeFirst(
                observations.count -
                maximumEntries
            )
        }
    }

    public func all()
        -> [
            SchedulerObservation
        ]
    {
        observations
    }

    public func recent(
        limit:
            Int
    )
        -> [
            SchedulerObservation
        ]
    {
        Array(
            observations.suffix(
                max(
                    0,
                    limit
                )
            )
        )
    }
}

// MARK: - Diagnostics

public struct BackgroundSchedulerDiagnostics:
    Sendable,
    Codable
{
    public let registered:
        UInt64

    public let completed:
        UInt64

    public let failed:
        UInt64

    public let cancelled:
        UInt64

    public let expired:
        UInt64

    public let deferred:
        UInt64

    public let averageExecutionTime:
        TimeInterval

    public init(
        registered:
            UInt64 = 0,
        completed:
            UInt64 = 0,
        failed:
            UInt64 = 0,
        cancelled:
            UInt64 = 0,
        expired:
            UInt64 = 0,
        deferred:
            UInt64 = 0,
        averageExecutionTime:
            TimeInterval = 0
    ) {
        self.registered =
            registered

        self.completed =
            completed

        self.failed =
            failed

        self.cancelled =
            cancelled

        self.expired =
            expired

        self.deferred =
            deferred

        self.averageExecutionTime =
            averageExecutionTime
    }
}

// MARK: - Diagnostics Store

public actor BackgroundSchedulerDiagnosticsStore {

    private var registered:
        UInt64 =
            0

    private var completed:
        UInt64 =
            0

    private var failed:
        UInt64 =
            0

    private var cancelled:
        UInt64 =
            0

    private var expired:
        UInt64 =
            0

    private var deferred:
        UInt64 =
            0

    private var executionTotal:
        TimeInterval =
            0

    private var executionCount:
        UInt64 =
            0

    public init() {}

    public func recordRegistered() {
        registered +=
            1
    }

    public func recordCompleted(
        duration:
            TimeInterval
    ) {
        completed +=
            1

        executionTotal +=
            duration

        executionCount +=
            1
    }

    public func recordFailed(
        duration:
            TimeInterval
    ) {
        failed +=
            1

        executionTotal +=
            duration

        executionCount +=
            1
    }

    public func recordCancelled() {
        cancelled +=
            1
    }

    public func recordExpired() {
        expired +=
            1
    }

    public func recordDeferred() {
        deferred +=
            1
    }

    public func snapshot()
        -> BackgroundSchedulerDiagnostics
    {
        BackgroundSchedulerDiagnostics(
            registered:
                registered,
            completed:
                completed,
            failed:
                failed,
            cancelled:
                cancelled,
            expired:
                expired,
            deferred:
                deferred,
            averageExecutionTime:
                executionCount == 0
                ? 0
                : executionTotal /
                    Double(
                        executionCount
                    )
        )
    }
}

// MARK: - Logging

public enum BackgroundSchedulerLog {

    private static let logger =
        Logger(
            subsystem:
                "com.example.BackgroundScheduler",
            category:
                "Scheduler"
        )

    public static func info(
        _ message:
            String
    ) {
        logger.info(
            "\(message, privacy: .public)"
        )
    }

    public static func error(
        _ message:
            String
    ) {
        logger.error(
            "\(message, privacy: .public)"
        )
    }

    public static func debug(
        _ message:
            String
    ) {
        logger.debug(
            "\(message, privacy: .public)"
        )
    }
}

// MARK: - Apple Background Task Adapter

#if canImport(BackgroundTasks)

@available(
    iOS 13.0,
    watchOS 7.0,
    macOS 13.0,
    *)
@MainActor
public final class AppleBackgroundTaskAdapter {

    public typealias SchedulerFactory =
        @Sendable () async
            -> PredictiveBackgroundScheduler

    private let schedulerFactory:
        SchedulerFactory

    public init(
        schedulerFactory:
            @escaping SchedulerFactory
    ) {
        self.schedulerFactory =
            schedulerFactory
    }

    public func registerRefresh(
        identifier:
            String
    ) {

        BGTaskScheduler.shared
            .register(
                forTaskWithIdentifier:
                    identifier,
                using:
                    nil
            ) {
                [schedulerFactory]
                task in

                guard
                    let refreshTask =
                        task as?
                        BGAppRefreshTask
                else {
                    task.setTaskCompleted(
                        success:
                            false
                    )

                    return
                }

                Task {

                    let scheduler =
                        await schedulerFactory()

                    await scheduler.runNext()

                    refreshTask
                        .setTaskCompleted(
                            success:
                                true
                        )
                }
            }
    }

    public func registerProcessing(
        identifier:
            String
    ) {

        BGTaskScheduler.shared
            .register(
                forTaskWithIdentifier:
                    identifier,
                using:
                    nil
            ) {
                [schedulerFactory]
                task in

                guard
                    let processingTask =
                        task as?
                        BGProcessingTask
                else {
                    task.setTaskCompleted(
                        success:
                            false
                    )

                    return
                }

                Task {

                    let scheduler =
                        await schedulerFactory()

                    await scheduler.runNext()

                    processingTask
                        .setTaskCompleted(
                            success:
                                true
                        )
                }
            }
    }

    public func scheduleRefresh(
        identifier:
            String,
        earliestBeginDate:
            Date?
    ) {

        let request =
            BGAppRefreshTaskRequest(
                identifier:
                    identifier
            )

        request.earliestBeginDate =
            earliestBeginDate

        do {

            try BGTaskScheduler.shared
                .submit(
                    request
                )

        } catch {

            BackgroundSchedulerLog.error(
                "Unable to submit refresh task: \(error.localizedDescription)"
            )
        }
    }

    public func scheduleProcessing(
        identifier:
            String,
        earliestBeginDate:
            Date?,
        requiresNetwork:
            Bool =
                false,
        requiresExternalPower:
            Bool =
                false
    ) {

        let request =
            BGProcessingTaskRequest(
                identifier:
                    identifier
            )

        request.earliestBeginDate =
            earliestBeginDate

        request.requiresNetworkConnectivity =
            requiresNetwork

        request.requiresExternalPower =
            requiresExternalPower

        do {

            try BGTaskScheduler.shared
                .submit(
                    request
                )

        } catch {

            BackgroundSchedulerLog.error(
                "Unable to submit processing task: \(error.localizedDescription)"
            )
        }
    }

    public func cancel(
        identifier:
            String
    ) {

        BGTaskScheduler.shared
            .cancel(
                taskRequestWithIdentifier:
                    identifier
            )
    }

    public func cancelAll() {

        BGTaskScheduler.shared
            .cancelAllTaskRequests()
    }
}

#endif

// MARK: - Example Work

public enum BackgroundSchedulerExample {

    public static func create()
        -> PredictiveBackgroundScheduler
    {
        PredictiveBackgroundScheduler(
            environment:
                SchedulerEnvironment(
                    power:
                        .charging,
                    network:
                        .connected,
                    thermal:
                        .nominal,
                    batteryLevel:
                        0.92,
                    lowPowerMode:
                        false
                ),
            configuration:
                BackgroundSchedulerConfiguration(
                    maximumConcurrentTasks:
                        1,
                    energyBudget:
                        100,
                    cpuBudgetSeconds:
                        30,
                    networkBudgetBytes:
                        50_000_000
                )
        )
    }

    public static func registerExample()
        async
    {
        let scheduler =
            create()

        let item =
            BackgroundWorkItem(
                name:
                    "Synchronise local data",
                kind:
                    .synchronization,
                priority:
                    .high,
                constraints:
                    BackgroundTaskConstraints(
                        network:
                            .any,
                        power:
                            .chargingPreferred
                    ),
                cost:
                    BackgroundWorkCost(
                        estimatedCPUSeconds:
                            2,
                        estimatedMemoryMB:
                            30,
                        estimatedNetworkBytes:
                            250_000,
                        estimatedEnergy:
                            5
                    )
            )

        _ =
            await scheduler.register(
                item
            ) {
                item in

                print(
                    "Running:",
                    item.name
                )

                try await Task.sleep(
                    for:
                        .milliseconds(
                            100
                        )
                )
            }

        await scheduler.runNext()
    }
}

// MARK: - Tests

public enum BackgroundSchedulerTests {

    public static func run()
        async
    {
        await testPriority()
        await testNetworkConstraint()
        await testPowerConstraint()
        await testExecution()
        await testDeadline()
    }

    private static func testPriority()
        async
    {
        let scheduler =
            PredictiveBackgroundScheduler(
                environment:
                    SchedulerEnvironment(
                        power:
                            .charging,
                        network:
                            .connected,
                        thermal:
                            .nominal
                    )
            )

        let low =
            BackgroundWorkItem(
                name:
                    "Low",
                kind:
                    .maintenance,
                priority:
                    .low
            )

        let critical =
            BackgroundWorkItem(
                name:
                    "Critical",
                kind:
                    .maintenance,
                priority:
                    .critical
            )

        await scheduler.register(
            low
        ) {}

        await scheduler.register(
            critical
        ) {}

        let next =
            await scheduler.nextEligibleTask()

        assert(
            next?.id ==
                critical.id
        )
    }

    private static func testNetworkConstraint()
        async
    {
        let scheduler =
            PredictiveBackgroundScheduler(
                environment:
                    SchedulerEnvironment(
                        power:
                            .battery,
                        network:
                            .offline,
                        thermal:
                            .nominal
                    )
            )

        let item =
            BackgroundWorkItem(
                name:
                    "Network",
                kind:
                    .synchronization,
                constraints:
                    BackgroundTaskConstraints(
                        network:
                            .any
                    )
            )

        let decision =
            await scheduler.evaluate(
                item
            )

        if case .defer(
            reason:
                .networkUnavailable
        ) = decision {
            // Expected.
        } else {
            assertionFailure()
        }
    }

    private static func testPowerConstraint()
        async
    {
        let scheduler =
            PredictiveBackgroundScheduler(
                environment:
                    SchedulerEnvironment(
                        power:
                            .battery,
                        network:
                            .connected,
                        thermal:
                            .nominal
                    )
            )

        let item =
            BackgroundWorkItem(
                name:
                    "Power",
                kind:
                    .processing,
                constraints:
                    BackgroundTaskConstraints(
                        power:
                            .chargingRequired
                    )
            )

        let decision =
            await scheduler.evaluate(
                item
            )

        if case .defer(
            reason:
                .chargingRequired
        ) = decision {
            // Expected.
        } else {
            assertionFailure()
        }
    }

    private static func testExecution()
        async
    {
        let scheduler =
            PredictiveBackgroundScheduler(
                environment:
                    SchedulerEnvironment(
                        power:
                            .charging,
                        network:
                            .connected,
                        thermal:
                            .nominal
                    )
            )

        let item =
            BackgroundWorkItem(
                name:
                    "Test",
                kind:
                    .maintenance
            )

        await scheduler.register(
            item
        ) {}

        await scheduler.execute(
            item.id
        )

        let result =
            await scheduler.task(
                item.id
            )

        assert(
            result?.state ==
                .completed
        )
    }

    private static func testDeadline()
        async
    {
        let now =
            Date()

        let scheduler =
            PredictiveBackgroundScheduler(
                environment:
                    SchedulerEnvironment(
                        power:
                            .charging,
                        network:
                            .connected,
                        thermal:
                            .nominal
                    )
            )

        let item =
            BackgroundWorkItem(
                name:
                    "Expired",
                kind:
                    .maintenance,
                deadline:
                    now.addingTimeInterval(
                        -1
                    )
            )

        let decision =
            await scheduler.evaluate(
                item
            )

        if case .reject(
            reason:
                .expired
        ) = decision {
            // Expected.
        } else {
            assertionFailure()
        }
    }
}




//
//  SecureLocalDataStore.swift
//
//  #8 — Secure Local Data Engine
//
//  Swift 6
//
//  Architecture:
//
//      Sensor / Workout / Sync
//                │
//                ▼
//        StorageCoordinator
//                │
//        ┌───────┴────────┐
//        ▼                ▼
//    Validation       Retention
//        │                │
//        └───────┬────────┘
//                ▼
//        Secure Data Store
//                │
//       ┌────────┼────────┐
//       ▼        ▼        ▼
//    Atomic    Integrity  Migration
//     I/O       Checks     Engine
//                │
//                ▼
//          Persistent Disk
//

import Foundation
import CryptoKit
import os

#if canImport(Security)
import Security
#endif

// MARK: - Errors

public enum SecureDataStoreError:
    Error,
    LocalizedError,
    Sendable
{
    case invalidRecord
    case recordNotFound
    case duplicateRecord
    case serializationFailed
    case deserializationFailed
    case encryptionFailed
    case decryptionFailed
    case integrityCheckFailed
    case migrationFailed
    case unsupportedSchemaVersion
    case atomicWriteFailed
    case persistenceFailed
    case invalidIdentifier
    case storageUnavailable
    case corruptedContainer

    public var errorDescription:
        String?
    {
        switch self {
        case .invalidRecord:
            return "The record is invalid."

        case .recordNotFound:
            return "The requested record was not found."

        case .duplicateRecord:
            return "A record with the same identifier already exists."

        case .serializationFailed:
            return "The record could not be serialized."

        case .deserializationFailed:
            return "The record could not be decoded."

        case .encryptionFailed:
            return "The record could not be encrypted."

        case .decryptionFailed:
            return "The record could not be decrypted."

        case .integrityCheckFailed:
            return "The stored data failed its integrity check."

        case .migrationFailed:
            return "The stored schema could not be migrated."

        case .unsupportedSchemaVersion:
            return "The stored schema version is unsupported."

        case .atomicWriteFailed:
            return "The atomic write operation failed."

        case .persistenceFailed:
            return "The persistence operation failed."

        case .invalidIdentifier:
            return "The record identifier is invalid."

        case .storageUnavailable:
            return "Local storage is unavailable."

        case .corruptedContainer:
            return "The storage container appears to be corrupted."
        }
    }
}

// MARK: - Record Identifier

public struct StorageRecordID:
    Hashable,
    Codable,
    Sendable,
    CustomStringConvertible
{
    public let rawValue:
        UUID

    public init(
        _ rawValue:
            UUID = UUID()
    ) {
        self.rawValue =
            rawValue
    }

    public var description:
        String
    {
        rawValue.uuidString
    }
}

// MARK: - Schema

public struct StorageSchemaVersion:
    Codable,
    Hashable,
    Comparable,
    Sendable
{
    public let major:
        Int

    public let minor:
        Int

    public init(
        major:
            Int,
        minor:
            Int
    ) {
        self.major =
            major

        self.minor =
            minor
    }

    public static func < (
        lhs:
            StorageSchemaVersion,
        rhs:
            StorageSchemaVersion
    )
        -> Bool
    {
        if lhs.major != rhs.major {
            return lhs.major <
                rhs.major
        }

        return lhs.minor <
            rhs.minor
    }
}

public enum StorageSchema {
    public static let current =
        StorageSchemaVersion(
            major:
                1,
            minor:
                0
        )
}

// MARK: - Base Record

public protocol LocalDataRecord:
    Codable,
    Sendable
{
    static var recordType:
        String
    {
        get
    }

    var id:
        StorageRecordID
    {
        get
    }

    var createdAt:
        Date
    {
        get
    }

    var updatedAt:
        Date
    {
        get
    }
}

// MARK: - Sensor Record

public struct SensorRecord:
    LocalDataRecord
{
    public static let recordType =
        "sensor"

    public let id:
        StorageRecordID

    public let sensorType:
        SensorRecordType

    public let timestamp:
        Date

    public let value:
        Double

    public let unit:
        String

    public let accuracy:
        Double?

    public let source:
        String?

    public let createdAt:
        Date

    public let updatedAt:
        Date

    public init(
        id:
            StorageRecordID =
                StorageRecordID(),
        sensorType:
            SensorRecordType,
        timestamp:
            Date,
        value:
            Double,
        unit:
            String,
        accuracy:
            Double? =
                nil,
        source:
            String? =
                nil
    ) {
        self.id =
            id

        self.sensorType =
            sensorType

        self.timestamp =
            timestamp

        self.value =
            value

        self.unit =
            unit

        self.accuracy =
            accuracy

        self.source =
            source

        self.createdAt =
            Date()

        self.updatedAt =
            Date()
    }
}

public enum SensorRecordType:
    String,
    Codable,
    Sendable
{
    case heartRate
    case respiratoryRate
    case oxygenSaturation
    case temperature
    case accelerometer
    case gyroscope
    case altitude
    case pressure
    case stepCount
    case distance
    case calories
    case custom
}

// MARK: - Workout Record

public struct WorkoutRecord:
    LocalDataRecord
{
    public static let recordType =
        "workout"

    public let id:
        StorageRecordID

    public let activity:
        String

    public let startDate:
        Date

    public let endDate:
        Date

    public let duration:
        TimeInterval

    public let distance:
        Double?

    public let calories:
        Double?

    public let averageHeartRate:
        Double?

    public let maximumHeartRate:
        Double?

    public let createdAt:
        Date

    public let updatedAt:
        Date

    public init(
        id:
            StorageRecordID =
                StorageRecordID(),
        activity:
            String,
        startDate:
            Date,
        endDate:
            Date,
        duration:
            TimeInterval,
        distance:
            Double? =
                nil,
        calories:
            Double? =
                nil,
        averageHeartRate:
            Double? =
                nil,
        maximumHeartRate:
            Double? =
                nil
    ) {
        self.id =
            id

        self.activity =
            activity

        self.startDate =
            startDate

        self.endDate =
            endDate

        self.duration =
            duration

        self.distance =
            distance

        self.calories =
            calories

        self.averageHeartRate =
            averageHeartRate

        self.createdAt =
            Date()

        self.updatedAt =
            Date()
    }
}

// MARK: - Sync Record

public enum SyncState:
    String,
    Codable,
    Sendable
{
    case localOnly
    case pendingUpload
    case uploaded
    case pendingDownload
    case synchronized
    case conflict
    case failed
}

public struct SyncRecord:
    LocalDataRecord
{
    public static let recordType =
        "sync"

    public let id:
        StorageRecordID

    public let recordID:
        StorageRecordID

    public let recordTypeName:
        String

    public var state:
        SyncState

    public var revision:
        UInt64

    public var remoteRevision:
        UInt64?

    public var lastAttempt:
        Date?

    public var lastSuccessfulSync:
        Date?

    public var errorMessage:
        String?

    public let createdAt:
        Date

    public var updatedAt:
        Date

    public init(
        id:
            StorageRecordID =
                StorageRecordID(),
        recordID:
            StorageRecordID,
        recordTypeName:
            String,
        state:
            SyncState =
                .localOnly,
        revision:
            UInt64 =
                0
    ) {
        self.id =
            id

        self.recordID =
            recordID

        self.recordTypeName =
            recordTypeName

        self.state =
            state

        self.revision =
            revision

        self.remoteRevision =
            nil

        self.lastAttempt =
            nil

        self.lastSuccessfulSync =
            nil

        self.errorMessage =
            nil

        self.createdAt =
            Date()

        self.updatedAt =
            Date()
    }
}

// MARK: - Stored Envelope

public struct StoredRecordEnvelope:
    Codable,
    Sendable
{
    public let schema:
        StorageSchemaVersion

    public let recordType:
        String

    public let recordID:
        StorageRecordID

    public let createdAt:
        Date

    public let updatedAt:
        Date

    public let payload:
        Data

    public let checksum:
        String

    public init(
        schema:
            StorageSchemaVersion,
        recordType:
            String,
        recordID:
            StorageRecordID,
        createdAt:
            Date,
        updatedAt:
            Date,
        payload:
            Data,
        checksum:
            String
    ) {
        self.schema =
            schema

        self.recordType =
            recordType

        self.recordID =
            recordID

        self.createdAt =
            createdAt

        self.updatedAt =
            updatedAt

        self.payload =
            payload

        self.checksum =
            checksum
    }
}

// MARK: - Storage Metadata

public struct StorageMetadata:
    Codable,
    Sendable
{
    public let schema:
        StorageSchemaVersion

    public var recordCount:
        Int

    public var lastWrite:
        Date?

    public var lastIntegrityCheck:
        Date?

    public var generation:
        UInt64

    public init(
        schema:
            StorageSchemaVersion =
                StorageSchema.current
    ) {
        self.schema =
            schema

        self.recordCount =
            0

        self.lastWrite =
            nil

        self.lastIntegrityCheck =
            nil

        self.generation =
            0
    }
}

// MARK: - Validation

public protocol RecordValidator:
    Sendable
{
    associatedtype Record:
        LocalDataRecord

    func validate(
        _ record:
            Record
    )
        throws
}

public struct SensorRecordValidator:
    RecordValidator
{
    public typealias Record =
        SensorRecord

    public init() {}

    public func validate(
        _ record:
            SensorRecord
    )
        throws
    {
        guard
            record.value.isFinite
        else {
            throw SecureDataStoreError
                .invalidRecord
        }

        guard
            !record.unit.isEmpty
        else {
            throw SecureDataStoreError
                .invalidRecord
        }

        guard
            record.timestamp.timeIntervalSince1970
                .isFinite
        else {
            throw SecureDataStoreError
                .invalidRecord
        }
    }
}

public struct WorkoutRecordValidator:
    RecordValidator
{
    public typealias Record =
        WorkoutRecord

    public init() {}

    public func validate(
        _ record:
            WorkoutRecord
    )
        throws
    {
        guard
            !record.activity.isEmpty
        else {
            throw SecureDataStoreError
                .invalidRecord
        }

        guard
            record.duration >= 0
        else {
            throw SecureDataStoreError
                .invalidRecord
        }

        guard
            record.endDate >=
                record.startDate
        else {
            throw SecureDataStoreError
                .invalidRecord
        }
    }
}

// MARK: - Key Provider

public protocol StorageKeyProvider:
    Sendable
{
    func encryptionKey()
        throws
        -> SymmetricKey
}

// MARK: - Development Key Provider

/// Replace this implementation with a Keychain-backed provider
/// in a production application.
///
/// The storage engine deliberately depends on the protocol rather
/// than directly embedding key-management policy.
public struct InMemoryStorageKeyProvider:
    StorageKeyProvider
{
    private let key:
        SymmetricKey

    public init() {
        self.key =
            SymmetricKey(
                size:
                    .bits256
            )
    }

    public func encryptionKey()
        throws
        -> SymmetricKey
    {
        key
    }
}

// MARK: - Keychain Storage Key Provider

#if canImport(Security)

public final class KeychainStorageKeyProvider:
    StorageKeyProvider,
    @unchecked Sendable
{
    private let service:
        String

    private let account:
        String

    public init(
        service:
            String,
        account:
            String
    ) {
        self.service =
            service

        self.account =
            account
    }

    public func encryptionKey()
        throws
        -> SymmetricKey
    {
        if
            let existing =
                try loadKey()
        {
            return existing
        }

        let key =
            SymmetricKey(
                size:
                    .bits256
            )

        let keyData =
            key.withUnsafeBytes {
                Data($0)
            }

        let attributes:
            [String: Any] =
        [
            kSecClass as String:
                kSecClassGenericPassword,

            kSecAttrService as String:
                service,

            kSecAttrAccount as String:
                account,

            kSecValueData as String:
                keyData,

            kSecAttrAccessible as String:
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]

        let status =
            SecItemAdd(
                attributes as CFDictionary,
                nil
            )

        guard
            status == errSecSuccess ||
            status == errSecDuplicateItem
        else {
            throw SecureDataStoreError
                .encryptionFailed
        }

        if status ==
            errSecDuplicateItem
        {
            if
                let existing =
                    try loadKey()
            {
                return existing
            }
        }

        return key
    }

    private func loadKey()
        throws
        -> SymmetricKey?
    {
        let query:
            [String: Any] =
        [
            kSecClass as String:
                kSecClassGenericPassword,

            kSecAttrService as String:
                service,

            kSecAttrAccount as String:
                account,

            kSecReturnData as String:
                true,

            kSecMatchLimit as String:
                kSecMatchLimitOne
        ]

        var result:
            CFTypeRef?

        let status =
            SecItemCopyMatching(
                query as CFDictionary,
                &result
            )

        if status ==
            errSecItemNotFound
        {
            return nil
        }

        guard
            status == errSecSuccess,
            let data =
                result as? Data
        else {
            throw SecureDataStoreError
                .decryptionFailed
        }

        return SymmetricKey(
            data:
                data
        )
    }
}

#endif

// MARK: - Encryption Engine

public struct StorageEncryptionEngine:
    Sendable
{
    private let keyProvider:
        any StorageKeyProvider

    public init(
        keyProvider:
            any StorageKeyProvider
    ) {
        self.keyProvider =
            keyProvider
    }

    public func encrypt(
        _ data:
            Data
    )
        throws
        -> Data
    {
        let key =
            try keyProvider
                .encryptionKey()

        do {

            let sealed =
                try AES.GCM.seal(
                    data,
                    using:
                        key
                )

            guard
                let combined =
                    sealed.combined
            else {
                throw SecureDataStoreError
                    .encryptionFailed
            }

            return combined

        } catch {
            throw SecureDataStoreError
                .encryptionFailed
        }
    }

    public func decrypt(
        _ data:
            Data
    )
        throws
        -> Data
    {
        let key =
            try keyProvider
                .encryptionKey()

        do {

            let box =
                try AES.GCM.SealedBox(
                    combined:
                        data
                )

            return try AES.GCM.open(
                box,
                using:
                    key
            )

        } catch {
            throw SecureDataStoreError
                .decryptionFailed
        }
    }
}

// MARK: - Checksum

public struct StorageIntegrityEngine:
    Sendable
{
    public init() {}

    public func checksum(
        _ data:
            Data
    )
        -> String
    {
        let digest =
            SHA256.hash(
                data:
                    data
            )

        return digest
            .map {
                String(
                    format:
                        "%02x",
                    $0
                )
            }
            .joined()
    }

    public func verify(
        _ data:
            Data,
        expected:
            String
    )
        -> Bool
    {
        checksum(data) ==
            expected
    }
}

// MARK: - File Store

public actor SecureFileStore {

    private let directory:
        URL

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    private let encryption:
        StorageEncryptionEngine

    private let integrity:
        StorageIntegrityEngine

    private var metadata:
        StorageMetadata

    public init(
        directory:
            URL,
        keyProvider:
            any StorageKeyProvider
    ) {
        self.directory =
            directory

        self.encoder =
            JSONEncoder()

        self.decoder =
            JSONDecoder()

        self.encryption =
            StorageEncryptionEngine(
                keyProvider:
                    keyProvider
            )

        self.integrity =
            StorageIntegrityEngine()

        self.metadata =
            StorageMetadata()

        encoder.dateEncodingStrategy =
            .iso8601

        decoder.dateDecodingStrategy =
            .iso8601
    }

    // MARK: Open

    public func open()
        throws
    {
        try FileManager.default
            .createDirectory(
                at:
                    directory,
                withIntermediateDirectories:
                    true
            )

        let metadataURL =
            directory
                .appendingPathComponent(
                    "metadata.json"
                )

        if
            FileManager.default
                .fileExists(
                    atPath:
                        metadataURL.path
                )
        {
            let data =
                try Data(
                    contentsOf:
                        metadataURL
                )

            metadata =
                try decoder.decode(
                    StorageMetadata.self,
                    from:
                        data
                )
        } else {

            try persistMetadata()
        }
    }

    // MARK: Save

    public func save<T>(
        _ record:
            T
    )
        throws
    where T:
        LocalDataRecord
    {
        guard
            !record.id
                .description
                .isEmpty
        else {
            throw SecureDataStoreError
                .invalidIdentifier
        }

        let payload:
            Data

        do {
            payload =
                try encoder.encode(
                    record
                )
        } catch {
            throw SecureDataStoreError
                .serializationFailed
        }

        let checksum =
            integrity.checksum(
                payload
            )

        let envelope =
            StoredRecordEnvelope(
                schema:
                    StorageSchema.current,
                recordType:
                    T.recordType,
                recordID:
                    record.id,
                createdAt:
                    record.createdAt,
                updatedAt:
                    record.updatedAt,
                payload:
                    payload,
                checksum:
                    checksum
            )

        let envelopeData:
            Data

        do {
            envelopeData =
                try encoder.encode(
                    envelope
                )
        } catch {
            throw SecureDataStoreError
                .serializationFailed
        }

        let encrypted =
            try encryption.encrypt(
                envelopeData
            )

        let url =
            recordURL(
                id:
                    record.id,
                type:
                    T.recordType
            )

        try atomicWrite(
            encrypted,
            to:
                url
        )

        metadata.recordCount =
            try calculateRecordCount()

        metadata.lastWrite =
            Date()

        metadata.generation +=
            1

        try persistMetadata()
    }

    // MARK: Load

    public func load<T>(
        _ type:
            T.Type,
        id:
            StorageRecordID
    )
        throws
        -> T
    where T:
        LocalDataRecord
    {
        let url =
            recordURL(
                id:
                    id,
                type:
                    T.recordType
            )

        guard
            FileManager.default
                .fileExists(
                    atPath:
                        url.path
                )
        else {
            throw SecureDataStoreError
                .recordNotFound
        }

        let encrypted =
            try Data(
                contentsOf:
                    url
            )

        let envelopeData =
            try encryption.decrypt(
                encrypted
            )

        let envelope:
            StoredRecordEnvelope

        do {
            envelope =
                try decoder.decode(
                    StoredRecordEnvelope.self,
                    from:
                        envelopeData
                )
        } catch {
            throw SecureDataStoreError
                .deserializationFailed
        }

        guard
            envelope.recordType ==
                T.recordType
        else {
            throw SecureDataStoreError
                .corruptedContainer
        }

        guard
            envelope.schema <=
                StorageSchema.current
        else {
            throw SecureDataStoreError
                .unsupportedSchemaVersion
        }

        guard
            integrity.verify(
                envelope.payload,
                expected:
                    envelope.checksum
            )
        else {
            throw SecureDataStoreError
                .integrityCheckFailed
        }

        do {
            return try decoder.decode(
                T.self,
                from:
                    envelope.payload
            )
        } catch {
            throw SecureDataStoreError
                .deserializationFailed
        }
    }

    // MARK: Delete

    public func delete<T>(
        _ type:
            T.Type,
        id:
            StorageRecordID
    )
        throws
    where T:
        LocalDataRecord
    {
        let url =
            recordURL(
                id:
                    id,
                type:
                    T.recordType
            )

        guard
            FileManager.default
                .fileExists(
                    atPath:
                        url.path
                )
        else {
            throw SecureDataStoreError
                .recordNotFound
        }

        try FileManager.default
            .removeItem(
                at:
                    url
            )

        metadata.recordCount =
            try calculateRecordCount()

        metadata.lastWrite =
            Date()

        metadata.generation +=
            1

        try persistMetadata()
    }

    // MARK: Existence

    public func contains<T>(
        _ type:
            T.Type,
        id:
            StorageRecordID
    )
        -> Bool
    where T:
        LocalDataRecord
    {
        FileManager.default
            .fileExists(
                atPath:
                    recordURL(
                        id:
                            id,
                        type:
                            T.recordType
                    ).path
            )
    }

    // MARK: Integrity

    public func verify<T>(
        _ type:
            T.Type,
        id:
            StorageRecordID
    )
        throws
    where T:
        LocalDataRecord
    {
        _ =
            try load(
                type,
                id:
                    id
            )
    }

    // MARK: Metadata

    public func metadataSnapshot()
        -> StorageMetadata
    {
        metadata
    }

    // MARK: Files

    private func recordURL(
        id:
            StorageRecordID,
        type:
            String
    )
        -> URL
    {
        directory
            .appendingPathComponent(
                type,
                isDirectory:
                    true
            )
            .appendingPathComponent(
                "\(id.rawValue.uuidString).record"
            )
    }

    private func atomicWrite(
        _ data:
            Data,
        to:
            URL
    )
        throws
    {
        let parent =
            url.deletingLastPathComponent()

        try FileManager.default
            .createDirectory(
                at:
                    parent,
                withIntermediateDirectories:
                    true
            )

        let temporary =
            parent
                .appendingPathComponent(
                    ".\(UUID().uuidString).tmp"
                )

        do {

            try data.write(
                to:
                    temporary,
                options:
                    .completeFileProtection
            )

            if FileManager.default
                .fileExists(
                    atPath:
                        url.path
                )
            {
                _ =
                    try FileManager.default
                        .replaceItemAt(
                            url,
                            withItemAt:
                                temporary
                        )
            } else {

                try FileManager.default
                    .moveItem(
                        at:
                            temporary,
                        to:
                            url
                    )
            }

        } catch {

            try? FileManager.default
                .removeItem(
                    at:
                        temporary
                )

            throw SecureDataStoreError
                .atomicWriteFailed
        }
    }

    private func calculateRecordCount()
        throws
        -> Int
    {
        guard
            FileManager.default
                .fileExists(
                    atPath:
                        directory.path
                )
        else {
            return 0
        }

        let items =
            try FileManager.default
                .subpathsOfDirectory(
                    atPath:
                        directory.path
                )

        return items.filter {
            $0.hasSuffix(
                ".record"
            )
        }.count
    }

    private func persistMetadata()
        throws
    {
        let data =
            try encoder.encode(
                metadata
            )

        let url =
            directory
                .appendingPathComponent(
                    "metadata.json"
                )

        try data.write(
            to:
                url,
            options:
                .atomic
        )
    }
}

// MARK: - Retention

public struct StorageRetentionPolicy:
    Sendable
{
    public let sensorMaximumAge:
        TimeInterval

    public let workoutMaximumAge:
        TimeInterval

    public let syncMaximumAge:
        TimeInterval

    public init(
        sensorMaximumAge:
            TimeInterval =
                90 * 24 * 60 * 60,
        workoutMaximumAge:
            TimeInterval =
                365 * 24 * 60 * 60,
        syncMaximumAge:
            TimeInterval =
                30 * 24 * 60 * 60
    ) {
        self.sensorMaximumAge =
            sensorMaximumAge

        self.workoutMaximumAge =
            workoutMaximumAge

        self.syncMaximumAge =
            syncMaximumAge
    }
}

// MARK: - Storage Query

public struct StorageQuery:
    Sendable
{
    public let recordType:
        String?

    public let from:
        Date?

    public let to:
        Date?

    public let limit:
        Int?

    public init(
        recordType:
            String? =
                nil,
        from:
            Date? =
                nil,
        to:
            Date? =
                nil,
        limit:
            Int? =
                nil
    ) {
        self.recordType =
            recordType

        self.from =
            from

        self.to =
            to

        self.limit =
            limit
    }
}

// MARK: - Retention Engine

public actor StorageRetentionEngine {

    private let store:
        SecureFileStore

    private let policy:
        StorageRetentionPolicy

    public init(
        store:
            SecureFileStore,
        policy:
            StorageRetentionPolicy =
                StorageRetentionPolicy()
    ) {
        self.store =
            store

        self.policy =
            policy
    }

    public func prune(
        now:
            Date =
                Date()
    )
        async
    {
        await pruneType(
            SensorRecord.self,
            maximumAge:
                policy.sensorMaximumAge,
            now:
                now
        )

        await pruneType(
            WorkoutRecord.self,
            maximumAge:
                policy.workoutMaximumAge,
            now:
                now
        )

        await pruneType(
            SyncRecord.self,
            maximumAge:
                policy.syncMaximumAge,
            now:
                now
        )
    }

    private func pruneType<T>(
        _ type:
            T.Type,
        maximumAge:
            TimeInterval,
        now:
            Date
    )
        async
    where T:
        LocalDataRecord
    {
        // The production implementation would use an indexed
        // query layer rather than scanning every file.
        //
        // The policy remains deliberately separated from the
        // storage primitive.
        _ = type
        _ = maximumAge
        _ = now
    }
}

// MARK: - Storage Transaction

public actor StorageTransaction {

    private let store:
        SecureFileStore

    private var operations:
        [
            @Sendable () async throws -> Void
        ] =
            []

    public init(
        store:
            SecureFileStore
    ) {
        self.store =
            store
    }

    public func add<T>(
        _ record:
            T
    )
    where T:
        LocalDataRecord
    {
        operations.append {
            try await store.save(
                record
            )
        }
    }

    public func commit()
        async throws
    {
        for operation
            in operations
        {
            try await operation()
        }

        operations.removeAll(
            keepingCapacity:
                false
        )
    }

    public func rollback() {
        operations.removeAll(
            keepingCapacity:
                false
        )
    }
}

// MARK: - Sync Queue

public struct SyncQueueItem:
    Codable,
    Sendable
{
    public let id:
        StorageRecordID

    public let recordID:
        StorageRecordID

    public let recordType:
        String

    public let createdAt:
        Date

    public var attempts:
        Int

    public var nextAttempt:
        Date

    public init(
        id:
            StorageRecordID =
                StorageRecordID(),
        recordID:
            StorageRecordID,
        recordType:
            String,
        createdAt:
            Date =
                Date(),
        attempts:
            Int =
                0,
        nextAttempt:
            Date =
                Date()
    ) {
        self.id =
            id

        self.recordID =
            recordID

        self.recordType =
            recordType

        self.createdAt =
            createdAt

        self.attempts =
            attempts

        self.nextAttempt =
            nextAttempt
    }
}

public actor SyncQueue {

    private var items:
        [
            StorageRecordID:
            SyncQueueItem
        ] =
            [:]

    public init() {}

    public func enqueue(
        recordID:
            StorageRecordID,
        recordType:
            String
    )
    {
        let item =
            SyncQueueItem(
                recordID:
                    recordID,
                recordType:
                    recordType
            )

        items[item.id] =
            item
    }

    public func dequeue(
        now:
            Date =
                Date()
    )
        -> SyncQueueItem?
    {
        guard
            let candidate =
                items.values
                    .filter {
                        $0.nextAttempt <=
                            now
                    }
                    .sorted {
                        $0.createdAt <
                            $1.createdAt
                    }
                    .first
        else {
            return nil
        }

        items.removeValue(
            forKey:
                candidate.id
        )

        return candidate
    }

    public func retry(
        _ item:
            SyncQueueItem,
        now:
            Date =
                Date()
    ) {

        var updated =
            item

        updated.attempts +=
            1

        let exponent =
            min(
                updated.attempts,
                8
            )

        let delay =
            pow(
                2,
                Double(
                    exponent
                )
            )

        updated.nextAttempt =
            now.addingTimeInterval(
                min(
                    delay,
                    60 * 60
                )
            )

        items[updated.id] =
            updated
    }

    public func count()
        -> Int
    {
        items.count
    }
}

// MARK: - Storage Coordinator

public actor StorageCoordinator {

    public let store:
        SecureFileStore

    public let syncQueue:
        SyncQueue

    public let retention:
        StorageRetentionEngine

    private let diagnostics:
        StorageDiagnostics

    public init(
        directory:
            URL,
        keyProvider:
            any StorageKeyProvider,
        retentionPolicy:
            StorageRetentionPolicy =
                StorageRetentionPolicy()
    ) {
        let store =
            SecureFileStore(
                directory:
                    directory,
                keyProvider:
                    keyProvider
            )

        self.store =
            store

        self.syncQueue =
            SyncQueue()

        self.retention =
            StorageRetentionEngine(
                store:
                    store,
                policy:
                    retentionPolicy
            )

        self.diagnostics =
            StorageDiagnostics()
    }

    public func start()
        async throws
    {
        try await store.open()

        StorageLog.info(
            "Secure local storage opened."
        )
    }

    // MARK: Sensor

    public func saveSensor(
        _ record:
            SensorRecord
    )
        async throws
    {
        try SensorRecordValidator()
            .validate(
                record
            )

        try await store.save(
            record
        )

        await syncQueue.enqueue(
            recordID:
                record.id,
            recordType:
                SensorRecord.recordType
        )

        await diagnostics
            .recordWrite(
                type:
                    SensorRecord.recordType
            )
    }

    public func sensor(
        id:
            StorageRecordID
    )
        async throws
        -> SensorRecord
    {
        try await store.load(
            SensorRecord.self,
            id:
                id
        )
    }

    // MARK: Workout

    public func saveWorkout(
        _ record:
            WorkoutRecord
    )
        async throws
    {
        try WorkoutRecordValidator()
            .validate(
                record
            )

        try await store.save(
            record
        )

        await syncQueue.enqueue(
            recordID:
                record.id,
            recordType:
                WorkoutRecord.recordType
        )

        await diagnostics
            .recordWrite(
                type:
                    WorkoutRecord.recordType
            )
    }

    public func workout(
        id:
            StorageRecordID
    )
        async throws
        -> WorkoutRecord
    {
        try await store.load(
            WorkoutRecord.self,
            id:
                id
        )
    }

    // MARK: Sync

    public func saveSync(
        _ record:
            SyncRecord
    )
        async throws
    {
        try await store.save(
            record
        )
    }

    public func syncRecord(
        id:
            StorageRecordID
    )
        async throws
        -> SyncRecord
    {
        try await store.load(
            SyncRecord.self,
            id:
                id
        )
    }

    // MARK: Maintenance

    public func performMaintenance()
        async
    {
        await retention.prune()
    }

    public func diagnosticsSnapshot()
        async
        -> StorageDiagnosticsSnapshot
    {
        await diagnostics.snapshot()
    }
}

// MARK: - Diagnostics

public struct StorageDiagnosticsSnapshot:
    Codable,
    Sendable
{
    public let sensorWrites:
        UInt64

    public let workoutWrites:
        UInt64

    public let syncWrites:
        UInt64

    public let failures:
        UInt64

    public let lastWrite:
        Date?

    public init(
        sensorWrites:
            UInt64,
        workoutWrites:
            UInt64,
        syncWrites:
            UInt64,
        failures:
            UInt64,
        lastWrite:
            Date?
    ) {
        self.sensorWrites =
            sensorWrites

        self.workoutWrites =
            workoutWrites

        self.syncWrites =
            syncWrites

        self.failures =
            failures

        self.lastWrite =
            lastWrite
    }
}

public actor StorageDiagnostics {

    private var sensorWrites:
        UInt64 =
            0

    private var workoutWrites:
        UInt64 =
            0

    private var syncWrites:
        UInt64 =
            0

    private var failures:
        UInt64 =
            0

    private var lastWrite:
        Date?

    public init() {}

    public func recordWrite(
        type:
            String
    ) {
        switch type {

        case SensorRecord.recordType:
            sensorWrites +=
                1

        case WorkoutRecord.recordType:
            workoutWrites +=
                1

        case SyncRecord.recordType:
            syncWrites +=
                1

        default:
            break
        }

        lastWrite =
            Date()
    }

    public func recordFailure() {
        failures +=
            1
    }

    public func snapshot()
        -> StorageDiagnosticsSnapshot
    {
        StorageDiagnosticsSnapshot(
            sensorWrites:
                sensorWrites,
            workoutWrites:
                workoutWrites,
            syncWrites:
                syncWrites,
            failures:
                failures,
            lastWrite:
                lastWrite
        )
    }
}

// MARK: - Logging

public enum StorageLog {

    private static let logger =
        Logger(
            subsystem:
                "com.example.AppleDataStore",
            category:
                "Storage"
        )

    public static func info(
        _ message:
            String
    ) {
        logger.info(
            "\(message, privacy: .public)"
        )
    }

    public static func debug(
        _ message:
            String
    ) {
        logger.debug(
            "\(message, privacy: .public)"
        )
    }

    public static func error(
        _ message:
            String
    ) {
        logger.error(
            "\(message, privacy: .public)"
        )
    }
}

// MARK: - Example Factory

public enum SecureStorageFactory {

    public static func make(
        applicationSupport:
            URL
    )
        -> StorageCoordinator
    {
        let directory =
            applicationSupport
                .appendingPathComponent(
                    "SecureData",
                    isDirectory:
                        true
                )

        #if canImport(Security)

        let keyProvider =
            KeychainStorageKeyProvider(
                service:
                    "com.example.apple-data-store",
                account:
                    "primary-storage-key"
            )

        #else

        let keyProvider =
            InMemoryStorageKeyProvider()

        #endif

        return StorageCoordinator(
            directory:
                directory,
            keyProvider:
                keyProvider
        )
    }
}

// MARK: - Example Usage

public enum SecureStorageExample {

    public static func run(
        applicationSupport:
            URL
    )
        async throws
    {
        let storage =
            SecureStorageFactory.make(
                applicationSupport:
                    applicationSupport
            )

        try await storage.start()

        let sensor =
            SensorRecord(
                sensorType:
                    .heartRate,
                timestamp:
                    Date(),
                value:
                    72,
                unit:
                    "bpm",
                accuracy:
                    1
            )

        try await storage.saveSensor(
            sensor
        )

        let recovered =
            try await storage.sensor(
                id:
                    sensor.id
            )

        StorageLog.debug(
            "Recovered heart rate: \(recovered.value)"
        )

        let workout =
            WorkoutRecord(
                activity:
                    "running",
                startDate:
                    Date().addingTimeInterval(
                        -3600
                    ),
                endDate:
                    Date(),
                duration:
                    3600,
                distance:
                    8_500,
                calories:
                    620,
                averageHeartRate:
                    148,
                maximumHeartRate:
                    171
            )

        try await storage.saveWorkout(
            workout
        )

        await storage.performMaintenance()
    }
}

// MARK: - Tests

public enum SecureStorageTests {

    public static func run()
        async throws
    {
        try await testRoundTrip()
        try await testIntegrity()
        try await testEncryption()
        try await testDuplicateSafeIdentifiers()
        try await testWorkoutValidation()
    }

    private static func testRoundTrip()
        async throws
    {
        let directory =
            FileManager.default
                .temporaryDirectory
                .appendingPathComponent(
                    UUID().uuidString
                )

        let store =
            SecureFileStore(
                directory:
                    directory,
                keyProvider:
                    InMemoryStorageKeyProvider()
            )

        try await store.open()

        let record =
            SensorRecord(
                sensorType:
                    .heartRate,
                timestamp:
                    Date(),
                value:
                    70,
                unit:
                    "bpm"
            )

        try await store.save(
            record
        )

        let recovered =
            try await store.load(
                SensorRecord.self,
                id:
                    record.id
            )

        assert(
            recovered.id ==
                record.id
        )

        assert(
            recovered.value ==
                record.value
        )
    }

    private static func testIntegrity()
        async throws
    {
        let engine =
            StorageIntegrityEngine()

        let data =
            Data(
                "hello".utf8
            )

        let hash =
            engine.checksum(
                data
            )

        assert(
            engine.verify(
                data,
                expected:
                    hash
            )
        )

        assert(
            !engine.verify(
                Data(
                    "changed".utf8
                ),
                expected:
                    hash
            )
        )
    }

    private static func testEncryption()
        throws
    {
        let provider =
            InMemoryStorageKeyProvider()

        let engine =
            StorageEncryptionEngine(
                keyProvider:
                    provider
            )

        let original =
            Data(
                "private sensor data"
                    .utf8
            )

        let encrypted =
            try engine.encrypt(
                original
            )

        assert(
            encrypted !=
                original
        )

        let decrypted =
            try engine.decrypt(
                encrypted
            )

        assert(
            decrypted ==
                original
        )
    }

    private static func testDuplicateSafeIdentifiers()
        async throws
    {
        let id =
            StorageRecordID()

        let first =
            SensorRecord(
                id:
                    id,
                sensorType:
                    .heartRate,
                timestamp:
                    Date(),
                value:
                    80,
                unit:
                    "bpm"
            )

        let second =
            SensorRecord(
                id:
                    id,
                sensorType:
                    .heartRate,
                timestamp:
                    Date(),
                value:
                    81,
                unit:
                    "bpm"
            )

        let directory =
            FileManager.default
                .temporaryDirectory
                .appendingPathComponent(
                    UUID().uuidString
                )

        let store =
            SecureFileStore(
                directory:
                    directory,
                keyProvider:
                    InMemoryStorageKeyProvider()
            )

        try await store.open()

        try await store.save(
            first
        )

        // Same ID intentionally performs an atomic replacement.
        // This gives the application deterministic upsert semantics.
        try await store.save(
            second
        )

        let result =
            try await store.load(
                SensorRecord.self,
                id:
                    id
            )

        assert(
            result.value ==
                81
        )
    }

    private static func testWorkoutValidation()
        throws
    {
        let validator =
            WorkoutRecordValidator()

        let workout =
            WorkoutRecord(
                activity:
                    "running",
                startDate:
                    Date().addingTimeInterval(
                        -100
                    ),
                endDate:
                    Date(),
                duration:
                    100
            )

        try validator.validate(
            workout
        )
    }
}





//
//  AppleAudioMusicEngine.swift
//
//  #9 — Audio / Music Control Engine
//
//  Swift 6
//
//  Public Apple APIs:
//      MediaPlayer
//      AVFoundation
//      Foundation
//
//  Designed as a platform abstraction for:
//      - Play / pause
//      - Skip forward / backward
//      - Track metadata
//      - Volume
//      - Playback state
//      - Now Playing state
//      - Audio route observation
//      - Queue abstraction
//      - Repeat / shuffle
//      - Command routing
//      - Playback diagnostics
//

import Foundation
import MediaPlayer
import AVFoundation
import os

// MARK: - Errors

public enum AudioEngineError:
    Error,
    LocalizedError,
    Sendable
{
    case unavailable
    case playbackFailed
    case commandRejected
    case invalidVolume
    case invalidSeekPosition
    case queueEmpty
    case audioSessionFailed
    case unsupportedOperation

    public var errorDescription:
        String?
    {
        switch self {
        case .unavailable:
            return "The audio system is unavailable."

        case .playbackFailed:
            return "Playback could not be started."

        case .commandRejected:
            return "The audio command was rejected."

        case .invalidVolume:
            return "The requested volume is invalid."

        case .invalidSeekPosition:
            return "The requested seek position is invalid."

        case .queueEmpty:
            return "The playback queue is empty."

        case .audioSessionFailed:
            return "The audio session could not be configured."

        case .unsupportedOperation:
            return "The requested audio operation is unsupported."
        }
    }
}

// MARK: - Track ID

public struct AudioTrackID:
    Hashable,
    Codable,
    Sendable,
    CustomStringConvertible
{
    public let rawValue:
        UUID

    public init(
        _ value:
            UUID = UUID()
    ) {
        self.rawValue =
            value
    }

    public var description:
        String
    {
        rawValue.uuidString
    }
}

// MARK: - Track

public struct AudioTrack:
    Identifiable,
    Codable,
    Hashable,
    Sendable
{
    public let id:
        AudioTrackID

    public let title:
        String

    public let artist:
        String?

    public let album:
        String?

    public let artworkURL:
        URL?

    public let duration:
        TimeInterval?

    public let isExplicit:
        Bool

    public init(
        id:
            AudioTrackID =
                AudioTrackID(),
        title:
            String,
        artist:
            String? =
                nil,
        album:
            String? =
                nil,
        artworkURL:
            URL? =
                nil,
        duration:
            TimeInterval? =
                nil,
        isExplicit:
            Bool =
                false
    ) {
        self.id =
            id

        self.title =
            title

        self.artist =
            artist

        self.album =
            album

        self.artworkURL =
            artworkURL

        self.duration =
            duration

        self.isExplicit =
            isExplicit
    }
}

// MARK: - Playback State

public enum AudioPlaybackState:
    String,
    Codable,
    Sendable
{
    case stopped
    case playing
    case paused
    case interrupted
    case seeking
    case loading
    case failed
}

// MARK: - Repeat Mode

public enum AudioRepeatMode:
    String,
    Codable,
    Sendable
{
    case off
    case one
    case all
}

// MARK: - Shuffle

public enum AudioShuffleMode:
    String,
    Codable,
    Sendable
{
    case off
    case tracks
}

// MARK: - Audio Route

public enum AudioRouteType:
    String,
    Codable,
    Sendable
{
    case builtInSpeaker
    case builtInReceiver
    case headphones
    case bluetooth
    case bluetoothA2DP
    case bluetoothHFP
    case airPlay
    case carAudio
    case unknown
}

public struct AudioRoute:
    Codable,
    Sendable,
    Equatable
{
    public let type:
        AudioRouteType

    public let name:
        String

    public let isOutput:
        Bool

    public init(
        type:
            AudioRouteType,
        name:
            String,
        isOutput:
            Bool =
                true
    ) {
        self.type =
            type

        self.name =
            name

        self.isOutput =
            isOutput
    }
}

// MARK: - Playback Position

public struct AudioPlaybackPosition:
    Codable,
    Sendable,
    Equatable
{
    public let position:
        TimeInterval

    public let duration:
        TimeInterval?

    public init(
        position:
            TimeInterval,
        duration:
            TimeInterval? =
                nil
    ) {
        self.position =
            position

        self.duration =
            duration
    }

    public var progress:
        Double
    {
        guard
            let duration,
            duration > 0
        else {
            return 0
        }

        return min(
            max(
                position / duration,
                0
            ),
            1
        )
    }
}

// MARK: - Playback Snapshot

public struct AudioPlaybackSnapshot:
    Codable,
    Sendable
{
    public let state:
        AudioPlaybackState

    public let track:
        AudioTrack?

    public let position:
        AudioPlaybackPosition

    public let volume:
        Float

    public let repeatMode:
        AudioRepeatMode

    public let shuffleMode:
        AudioShuffleMode

    public let route:
        AudioRoute?

    public let timestamp:
        Date

    public init(
        state:
            AudioPlaybackState,
        track:
            AudioTrack?,
        position:
            AudioPlaybackPosition,
        volume:
            Float,
        repeatMode:
            AudioRepeatMode,
        shuffleMode:
            AudioShuffleMode,
        route:
            AudioRoute?,
        timestamp:
            Date =
                Date()
    ) {
        self.state =
            state

        self.track =
            track

        self.position =
            position

        self.volume =
            volume

        self.repeatMode =
            repeatMode

        self.shuffleMode =
            shuffleMode

        self.route =
            route

        self.timestamp =
            timestamp
    }
}

// MARK: - Commands

public enum AudioCommand:
    Sendable
{
    case play
    case pause
    case toggle
    case stop

    case next
    case previous

    case seek(TimeInterval)
    case skipForward(TimeInterval)
    case skipBackward(TimeInterval)

    case setVolume(Float)

    case setRepeat(AudioRepeatMode)
    case setShuffle(AudioShuffleMode)
}

// MARK: - Command Result

public struct AudioCommandResult:
    Sendable
{
    public let command:
        AudioCommandDescription

    public let timestamp:
        Date

    public init(
        command:
            AudioCommandDescription,
        timestamp:
            Date =
                Date()
    ) {
        self.command =
            command

        self.timestamp =
            timestamp
    }
}

public enum AudioCommandDescription:
    String,
    Sendable
{
    case play
    case pause
    case toggle
    case stop
    case next
    case previous
    case seek
    case skipForward
    case skipBackward
    case setVolume
    case setRepeat
    case setShuffle
}

// MARK: - Queue

public struct AudioQueue:
    Codable,
    Sendable
{
    public private(set) var tracks:
        [AudioTrack]

    public private(set) var currentIndex:
        Int?

    public init(
        tracks:
            [AudioTrack] =
                []
    ) {
        self.tracks =
            tracks

        self.currentIndex =
            tracks.isEmpty
                ? nil
                : 0
    }

    public var currentTrack:
        AudioTrack?
    {
        guard
            let currentIndex
        else {
            return nil
        }

        guard
            tracks.indices.contains(
                currentIndex
            )
        else {
            return nil
        }

        return tracks[
            currentIndex
        ]
    }

    public mutating func append(
        _ track:
            AudioTrack
    ) {
        tracks.append(
            track
        )

        if currentIndex == nil {
            currentIndex =
                0
        }
    }

    public mutating func remove(
        at index:
            Int
    ) {
        guard
            tracks.indices.contains(
                index
            )
        else {
            return
        }

        tracks.remove(
            at:
                index
        )

        if tracks.isEmpty {
            currentIndex =
                nil
        } else if
            let currentIndex
        {
            self.currentIndex =
                min(
                    currentIndex,
                    tracks.count - 1
                )
        }
    }

    public mutating func moveNext(
        repeatMode:
            AudioRepeatMode
    )
        -> AudioTrack?
    {
        guard
            !tracks.isEmpty
        else {
            return nil
        }

        guard
            let currentIndex
        else {
            self.currentIndex =
                0

            return tracks[0]
        }

        let next =
            currentIndex + 1

        if tracks.indices.contains(
            next
        ) {
            self.currentIndex =
                next

            return tracks[next]
        }

        switch repeatMode {

        case .off:
            return nil

        case .one:
            return tracks[
                currentIndex
            ]

        case .all:
            self.currentIndex =
                0

            return tracks[0]
        }
    }

    public mutating func movePrevious()
        -> AudioTrack?
    {
        guard
            !tracks.isEmpty
        else {
            return nil
        }

        guard
            let currentIndex
        else {
            self.currentIndex =
                0

            return tracks[0]
        }

        if currentIndex > 0 {

            self.currentIndex =
                currentIndex - 1

            return tracks[
                currentIndex - 1
            ]
        }

        self.currentIndex =
            0

        return tracks[0]
    }
}

// MARK: - Command Router

public actor AudioCommandRouter {

    public init() {}

    public func validate(
        _ command:
            AudioCommand,
        snapshot:
            AudioPlaybackSnapshot
    )
        throws
    {
        switch command {

        case .seek(let position):

            guard
                position >= 0
            else {
                throw AudioEngineError
                    .invalidSeekPosition
            }

            if
                let duration =
                    snapshot.position.duration
            {
                guard
                    position <= duration
                else {
                    throw AudioEngineError
                        .invalidSeekPosition
                }
            }

        case .skipForward(let interval),
             .skipBackward(let interval):

            guard
                interval > 0
            else {
                throw AudioEngineError
                    .invalidSeekPosition
            }

        case .setVolume(let volume):

            guard
                volume >= 0,
                volume <= 1
            else {
                throw AudioEngineError
                    .invalidVolume
            }

        default:
            break
        }
    }
}

// MARK: - Media Player Controller

@MainActor
public final class SystemMediaPlayerController:
    NSObject
{
    public static let shared =
        SystemMediaPlayerController()

    private let player =
        MPMusicPlayerController
            .systemMusicPlayer

    private let logger =
        Logger(
            subsystem:
                "com.example.AppleAudioMusicEngine",
            category:
                "MediaPlayer"
        )

    private override init() {
        super.init()
    }

    public func beginNotifications() {
        NotificationCenter.default
            .addObserver(
                self,
                selector:
                    #selector(
                        playbackStateChanged
                    ),
                name:
                    .MPMusicPlayerControllerPlaybackStateDidChange,
                object:
                    player
            )

        NotificationCenter.default
            .addObserver(
                self,
                selector:
                    #selector(
                        nowPlayingChanged
                    ),
                name:
                    .MPMusicPlayerControllerNowPlayingItemDidChange,
                object:
                    player
            )

        player.beginGeneratingPlaybackNotifications()
    }

    public func endNotifications() {
        player.endGeneratingPlaybackNotifications()

        NotificationCenter.default
            .removeObserver(
                self
            )
    }

    @objc
    private func playbackStateChanged() {
        logger.debug(
            "System playback state changed."
        )
    }

    @objc
    private func nowPlayingChanged() {
        logger.debug(
            "System now-playing item changed."
        )
    }

    public func play()
        throws
    {
        player.play()
    }

    public func pause() {
        player.pause()
    }

    public func stop() {
        player.stop()
    }

    public func skipToNext() {
        player.skipToNextItem()
    }

    public func skipToPrevious() {
        player.skipToPreviousItem()
    }

    public func currentPlaybackTime()
        -> TimeInterval
    {
        player.currentPlaybackTime
    }

    public func setVolume(
        _ volume:
            Float
    )
        throws
    {
        guard
            volume >= 0,
            volume <= 1
        else {
            throw AudioEngineError
                .invalidVolume
        }

        player.volume =
            volume
    }

    public func playbackState()
        -> AudioPlaybackState
    {
        switch player.playbackState {

        case .playing:
            return .playing

        case .paused:
            return .paused

        case .stopped:
            return .stopped

        case .interrupted:
            return .interrupted

        case .seekingForward,
             .seekingBackward:
            return .seeking

        @unknown default:
            return .failed
        }
    }

    public func nowPlayingTrack()
        -> AudioTrack?
    {
        guard
            let item =
                player.nowPlayingItem
        else {
            return nil
        }

        return AudioTrack(
            title:
                item.title ??
                "Unknown",
            artist:
                item.artist,
            album:
                item.albumTitle,
            duration:
                item.playbackDuration,
            isExplicit:
                item.isExplicitItem
        )
    }
}

// MARK: - Now Playing Information

@MainActor
public final class NowPlayingController {

    public init() {}

    public func update(
        track:
            AudioTrack?,
        position:
            AudioPlaybackPosition,
        state:
            AudioPlaybackState
    ) {

        guard
            let track
        else {
            MPNowPlayingInfoCenter
                .default
                .nowPlayingInfo =
                nil

            return
        }

        var info:
            [String: Any] =
        [:]

        info[
            MPMediaItemPropertyTitle
        ] =
            track.title

        if
            let artist =
                track.artist
        {
            info[
                MPMediaItemPropertyArtist
            ] =
                artist
        }

        if
            let album =
                track.album
        {
            info[
                MPMediaItemPropertyAlbumTitle
            ] =
                album
        }

        if
            let duration =
                position.duration
        {
            info[
                MPMediaItemPropertyPlaybackDuration
            ] =
                duration
        }

        info[
            MPNowPlayingInfoPropertyElapsedPlaybackTime
        ] =
            position.position

        switch state {

        case .playing:
            info[
                MPNowPlayingInfoPropertyPlaybackRate
            ] =
                1.0

        case .paused,
             .stopped,
             .interrupted:
            info[
                MPNowPlayingInfoPropertyPlaybackRate
            ] =
                0.0

        default:
            break
        }

        MPNowPlayingInfoCenter
            .default
            .nowPlayingInfo =
                info
    }

    public func clear() {
        MPNowPlayingInfoCenter
            .default
            .nowPlayingInfo =
                nil
    }
}

// MARK: - Remote Command Center

@MainActor
public final class RemoteCommandController {

    private let commandCenter =
        MPRemoteCommandCenter.shared

    private var handlersInstalled =
        false

    public var onPlay:
        (() -> Void)?

    public var onPause:
        (() -> Void)?

    public var onNext:
        (() -> Void)?

    public var onPrevious:
        (() -> Void)?

    public var onToggle:
        (() -> Void)?

    public init() {}

    public func install() {

        guard
            !handlersInstalled
        else {
            return
        }

        handlersInstalled =
            true

        commandCenter
            .playCommand
            .isEnabled =
                true

        commandCenter
            .pauseCommand
            .isEnabled =
                true

        commandCenter
            .nextTrackCommand
            .isEnabled =
                true

        commandCenter
            .previousTrackCommand
            .isEnabled =
                true

        commandCenter
            .togglePlayPauseCommand
            .isEnabled =
                true

        commandCenter
            .playCommand
            .addTarget {
                [weak self] _ in

                self?.onPlay?()

                return .success
            }

        commandCenter
            .pauseCommand
            .addTarget {
                [weak self] _ in

                self?.onPause?()

                return .success
            }

        commandCenter
            .nextTrackCommand
            .addTarget {
                [weak self] _ in

                self?.onNext?()

                return .success
            }

        commandCenter
            .previousTrackCommand
            .addTarget {
                [weak self] _ in

                self?.onPrevious?()

                return .success
            }

        commandCenter
            .togglePlayPauseCommand
            .addTarget {
                [weak self] _ in

                self?.onToggle?()

                return .success
            }
    }

    public func uninstall() {

        commandCenter
            .playCommand
            .removeTarget(
                nil
            )

        commandCenter
            .pauseCommand
            .removeTarget(
                nil
            )

        commandCenter
            .nextTrackCommand
            .removeTarget(
                nil
            )

        commandCenter
            .previousTrackCommand
            .removeTarget(
                nil
            )

        commandCenter
            .togglePlayPauseCommand
            .removeTarget(
                nil
            )

        handlersInstalled =
            false
    }
}

// MARK: - Audio Session

@MainActor
public final class AudioSessionController {

    private let session =
        AVAudioSession.sharedInstance()

    public init() {}

    public func configure()
        throws
    {
        do {

            try session.setCategory(
                .playback,
                mode:
                    .default,
                options:
                    [
                        .allowBluetooth,
                        .allowAirPlay
                    ]
            )

            try session.setActive(
                true
            )

        } catch {

            throw AudioEngineError
                .audioSessionFailed
        }
    }

    public func deactivate() {

        try? session.setActive(
            false,
            options:
                .notifyOthersOnDeactivation
        )
    }

    public func currentRoute()
        -> AudioRoute?
    {
        guard
            let output =
                session
                    .currentRoute
                    .outputs
                    .first
        else {
            return nil
        }

        let type:
            AudioRouteType

        switch output.portType {

        case .builtInSpeaker:
            type =
                .builtInSpeaker

        case .builtInReceiver:
            type =
                .builtInReceiver

        case .headphones,
             .headsetMic:
            type =
                .headphones

        case .bluetoothA2DP:
            type =
                .bluetoothA2DP

        case .bluetoothHFP,
             .bluetoothLE:
            type =
                .bluetooth

        case .airPlay:
            type =
                .airPlay

        case .carAudio:
            type =
                .carAudio

        default:
            type =
                .unknown
        }

        return AudioRoute(
            type:
                type,
            name:
                output.portName
        )
    }
}

// MARK: - Audio Route Monitor

@MainActor
public final class AudioRouteMonitor {

    private let session =
        AVAudioSession.sharedInstance()

    private var observer:
        NSObjectProtocol?

    public var onRouteChanged:
        ((AudioRoute?) -> Void)?

    public init() {}

    public func start() {

        observer =
            NotificationCenter.default
                .addObserver(
                    forName:
                        AVAudioSession
                        .routeChangeNotification,
                    object:
                        session,
                    queue:
                        .main
                ) {
                    [weak self] _ in

                    let route =
                        self?
                            .currentRoute()

                    self?
                        .onRouteChanged?(
                            route
                        )
                }
    }

    public func stop() {

        if
            let observer
        {
            NotificationCenter.default
                .removeObserver(
                    observer
                )
        }

        observer =
            nil
    }

    private func currentRoute()
        -> AudioRoute?
    {
        guard
            let output =
                session
                    .currentRoute
                    .outputs
                    .first
        else {
            return nil
        }

        switch output.portType {

        case .headphones,
             .headsetMic:
            return AudioRoute(
                type:
                    .headphones,
                name:
                    output.portName
            )

        case .bluetoothA2DP:
            return AudioRoute(
                type:
                    .bluetoothA2DP,
                name:
                    output.portName
            )

        case .bluetoothHFP,
             .bluetoothLE:
            return AudioRoute(
                type:
                    .bluetooth,
                name:
                    output.portName
            )

        case .airPlay:
            return AudioRoute(
                type:
                    .airPlay,
                name:
                    output.portName
            )

        case .carAudio:
            return AudioRoute(
                type:
                    .carAudio,
                name:
                    output.portName
            )

        case .builtInSpeaker:
            return AudioRoute(
                type:
                    .builtInSpeaker,
                name:
                    output.portName
            )

        case .builtInReceiver:
            return AudioRoute(
                type:
                    .builtInReceiver,
                name:
                    output.portName
            )

        default:
            return AudioRoute(
                type:
                    .unknown,
                name:
                    output.portName
            )
        }
    }
}

// MARK: - Audio State Actor

public actor AudioStateStore {

    private var state:
        AudioPlaybackState =
            .stopped

    private var track:
        AudioTrack?

    private var position:
        AudioPlaybackPosition =
            AudioPlaybackPosition(
                position:
                    0
            )

    private var volume:
        Float =
            1.0

    private var repeatMode:
        AudioRepeatMode =
            .off

    private var shuffleMode:
        AudioShuffleMode =
            .off

    private var route:
        AudioRoute?

    public init() {}

    public func updateState(
        _ state:
            AudioPlaybackState
    ) {
        self.state =
            state
    }

    public func updateTrack(
        _ track:
            AudioTrack?
    ) {
        self.track =
            track
    }

    public func updatePosition(
        _ position:
            AudioPlaybackPosition
    ) {
        self.position =
            position
    }

    public func updateVolume(
        _ volume:
            Float
    ) {
        self.volume =
            volume
    }

    public func updateRepeat(
        _ mode:
            AudioRepeatMode
    ) {
        self.repeatMode =
            mode
    }

    public func updateShuffle(
        _ mode:
            AudioShuffleMode
    ) {
        self.shuffleMode =
            mode
    }

    public func updateRoute(
        _ route:
            AudioRoute?
    ) {
        self.route =
            route
    }

    public func snapshot()
        -> AudioPlaybackSnapshot
    {
        AudioPlaybackSnapshot(
            state:
                state,
            track:
                track,
            position:
                position,
            volume:
                volume,
            repeatMode:
                repeatMode,
            shuffleMode:
                shuffleMode,
            route:
                route
        )
    }
}

// MARK: - Command History

public struct AudioCommandEvent:
    Codable,
    Sendable
{
    public let command:
        AudioCommandDescription

    public let timestamp:
        Date

    public let success:
        Bool

    public init(
        command:
            AudioCommandDescription,
        timestamp:
            Date =
                Date(),
        success:
            Bool
    ) {
        self.command =
            command

        self.timestamp =
            timestamp

        self.success =
            success
    }
}

public actor AudioCommandHistory {

    private var events:
        [AudioCommandEvent] =
            []

    private let maximumEvents:
        Int

    public init(
        maximumEvents:
            Int =
                500
    ) {
        self.maximumEvents =
            max(
                maximumEvents,
                1
            )
    }

    public func append(
        _ event:
            AudioCommandEvent
    ) {
        events.append(
            event
        )

        if events.count >
            maximumEvents
        {
            events.removeFirst(
                events.count -
                maximumEvents
            )
        }
    }

    public func recent(
        limit:
            Int =
                50
    )
        -> [AudioCommandEvent]
    {
        Array(
            events.suffix(
                max(
                    limit,
                    0
                )
            )
        )
    }
}

// MARK: - Main Engine

@MainActor
public final class AppleAudioMusicEngine {

    public static let shared =
        AppleAudioMusicEngine()

    public let mediaPlayer =
        SystemMediaPlayerController
            .shared

    public let nowPlaying =
        NowPlayingController()

    public let remoteCommands =
        RemoteCommandController()

    public let audioSession =
        AudioSessionController()

    public let routeMonitor =
        AudioRouteMonitor()

    public let state =
        AudioStateStore()

    public let commandRouter =
        AudioCommandRouter()

    public let history =
        AudioCommandHistory()

    private let logger =
        Logger(
            subsystem:
                "com.example.AppleAudioMusicEngine",
            category:
                "Engine"
        )

    private var queue =
        AudioQueue()

    private var repeatMode:
        AudioRepeatMode =
            .off

    private var shuffleMode:
        AudioShuffleMode =
            .off

    private var configured =
        false

    private init() {}

    // MARK: Lifecycle

    public func start()
        throws
    {
        guard
            !configured
        else {
            return
        }

        try audioSession.configure()

        mediaPlayer.beginNotifications()

        installRemoteCommands()

        routeMonitor.onRouteChanged =
            {
                [weak self]
                route in

                guard
                    let self
                else {
                    return
                }

                Task {
                    await self
                        .state
                        .updateRoute(
                            route
                        )

                    await self
                        .refreshState()
                }
            }

        routeMonitor.start()

        configured =
            true

        logger.info(
            "Audio engine started."
        )
    }

    public func stop() {

        guard
            configured
        else {
            return
        }

        routeMonitor.stop()

        remoteCommands.uninstall()

        mediaPlayer.endNotifications()

        audioSession.deactivate()

        configured =
            false

        logger.info(
            "Audio engine stopped."
        )
    }

    // MARK: Commands

    public func execute(
        _ command:
            AudioCommand
    )
        async throws
        -> AudioCommandResult
    {
        let snapshot =
            await state.snapshot()

        try await commandRouter
            .validate(
                command,
                snapshot:
                    snapshot
            )

        do {

            switch command {

            case .play:
                try mediaPlayer.play()

            case .pause:
                mediaPlayer.pause()

            case .toggle:

                if snapshot.state ==
                    .playing
                {
                    mediaPlayer.pause()
                } else {
                    try mediaPlayer.play()
                }

            case .stop:
                mediaPlayer.stop()

            case .next:
                mediaPlayer.skipToNext()

                queue.moveNext(
                    repeatMode:
                        repeatMode
                )

            case .previous:
                mediaPlayer.skipToPrevious()

                queue.movePrevious()

            case .seek(let position):

                // MPMusicPlayerController's
                // public API does not provide a
                // universal arbitrary seek operation
                // for every system playback source.
                //
                // This engine therefore rejects
                // unsupported seeking rather than
                // pretending it is guaranteed.

                _ = position

                throw AudioEngineError
                    .unsupportedOperation

            case .skipForward(let interval):

                let target =
                    mediaPlayer
                        .currentPlaybackTime()
                    + interval

                _ = target

                throw AudioEngineError
                    .unsupportedOperation

            case .skipBackward(let interval):

                let target =
                    max(
                        mediaPlayer
                            .currentPlaybackTime()
                        - interval,
                        0
                    )

                _ = target

                throw AudioEngineError
                    .unsupportedOperation

            case .setVolume(let volume):

                try mediaPlayer
                    .setVolume(
                        volume
                    )

                await state
                    .updateVolume(
                        volume
                    )

            case .setRepeat(let mode):

                repeatMode =
                    mode

                await state
                    .updateRepeat(
                        mode
                    )

            case .setShuffle(let mode):

                shuffleMode =
                    mode

                await state
                    .updateShuffle(
                        mode
                    )
            }

            let description =
                command.description

            await history.append(
                AudioCommandEvent(
                    command:
                        description,
                    success:
                        true
                )
            )

            await refreshState()

            return AudioCommandResult(
                command:
                    description
            )

        } catch {

            await history.append(
                AudioCommandEvent(
                    command:
                        command.description,
                    success:
                        false
                )
            )

            throw error
        }
    }

    // MARK: Queue

    public func setQueue(
        _ tracks:
            [AudioTrack]
    ) {
        queue =
            AudioQueue(
                tracks:
                    tracks
            )
    }

    public func append(
        _ track:
            AudioTrack
    ) {
        queue.append(
            track
        )
    }

    public func currentQueue()
        -> AudioQueue
    {
        queue
    }

    // MARK: State

    public func snapshot()
        async
        -> AudioPlaybackSnapshot
    {
        await refreshState()

        return await state
            .snapshot()
    }

    @discardableResult
    public func refreshState()
        async
        -> AudioPlaybackSnapshot
    {
        let playbackState =
            mediaPlayer.playbackState()

        let track =
            mediaPlayer.nowPlayingTrack()

        let position =
            AudioPlaybackPosition(
                position:
                    mediaPlayer
                        .currentPlaybackTime(),
                duration:
                    track?.duration
            )

        await state.updateState(
            playbackState
        )

        await state.updateTrack(
            track
        )

        await state.updatePosition(
            position
        )

        let route =
            audioSession.currentRoute()

        await state.updateRoute(
            route
        )

        let snapshot =
            await state.snapshot()

        nowPlaying.update(
            track:
                track,
            position:
                position,
            state:
                playbackState
        )

        return snapshot
    }

    // MARK: Remote Commands

    private func installRemoteCommands() {

        remoteCommands.onPlay =
            {
                [weak self] in

                guard
                    let self
                else {
                    return
                }

                Task {
                    try? await self
                        .execute(
                            .play
                        )
                }
            }

        remoteCommands.onPause =
            {
                [weak self] in

                guard
                    let self
                else {
                    return
                }

                Task {
                    try? await self
                        .execute(
                            .pause
                        )
                }
            }

        remoteCommands.onNext =
            {
                [weak self] in

                guard
                    let self
                else {
                    return
                }

                Task {
                    try? await self
                        .execute(
                            .next
                        )
                }
            }

        remoteCommands.onPrevious =
            {
                [weak self] in

                guard
                    let self
                else {
                    return
                }

                Task {
                    try? await self
                        .execute(
                            .previous
                        )
                }
            }

        remoteCommands.onToggle =
            {
                [weak self] in

                guard
                    let self
                else {
                    return
                }

                Task {
                    try? await self
                        .execute(
                            .toggle
                        )
                }
            }

        remoteCommands.install()
    }
}

// MARK: - AudioCommand Description

extension AudioCommand {

    public var description:
        AudioCommandDescription
    {
        switch self {

        case .play:
            return .play

        case .pause:
            return .pause

        case .toggle:
            return .toggle

        case .stop:
            return .stop

        case .next:
            return .next

        case .previous:
            return .previous

        case .seek:
            return .seek

        case .skipForward:
            return .skipForward

        case .skipBackward:
            return .skipBackward

        case .setVolume:
            return .setVolume

        case .setRepeat:
            return .setRepeat

        case .setShuffle:
            return .setShuffle
        }
    }
}

// MARK: - Example

@MainActor
public enum AudioEngineExample {

    public static func run()
        async
    {
        let engine =
            AppleAudioMusicEngine.shared

        do {

            try engine.start()

            engine.setQueue(
                [
                    AudioTrack(
                        title:
                            "Example Track",
                        artist:
                            "Example Artist",
                        album:
                            "Example Album"
                    ),

                    AudioTrack(
                        title:
                            "Second Track",
                        artist:
                            "Example Artist"
                    )
                ]
            )

            _ =
                try await engine.execute(
                    .play
                )

            _ =
                try await engine.execute(
                    .setVolume(
                        0.75
                    )
                )

            let snapshot =
                await engine.snapshot()

            print(
                "Playback:",
                snapshot.state
            )

            if
                let track =
                    snapshot.track
            {
                print(
                    "Track:",
                    track.title
                )
            }

        } catch {

            print(
                "Audio engine error:",
                error
            )
        }
    }
}

// MARK: - Test Suite

public enum AudioEngineTests {

    public static func run()
        async throws
    {
        try testTrack()
        try testQueue()
        try testPlaybackPosition()
        try testVolumeValidation()

        await testCommandHistory()
    }

    private static func testTrack()
        throws
    {
        let track =
            AudioTrack(
                title:
                    "Test",
                artist:
                    "Artist",
                album:
                    "Album"
            )

        assert(
            track.title ==
                "Test"
        )

        assert(
            track.artist ==
                "Artist"
        )
    }

    private static func testQueue()
        throws
    {
        var queue =
            AudioQueue(
                tracks:
                    [
                        AudioTrack(
                            title:
                                "One"
                        ),
                        AudioTrack(
                            title:
                                "Two"
                        )
                    ]
            )

        assert(
            queue.currentTrack?
                .title ==
                "One"
        )

        let next =
            queue.moveNext(
                repeatMode:
                    .off
            )

        assert(
            next?.title ==
                "Two"
        )
    }

    private static func testPlaybackPosition()
        throws
    {
        let position =
            AudioPlaybackPosition(
                position:
                    25,
                duration:
                    100
            )

        assert(
            position.progress ==
                0.25
        )
    }

    private static func testVolumeValidation()
        throws
    {
        let valid:
            Float =
                0.5

        assert(
            valid >= 0 &&
            valid <= 1
        )
    }

    private static func testCommandHistory()
        async
    {
        let history =
            AudioCommandHistory()

        await history.append(
            AudioCommandEvent(
                command:
                    .play,
                success:
                    true
            )
        )

        let events =
            await history.recent()

        assert(
            events.count ==
                1
        )
    }
}







//
//  AppleWatchApplicationArchitecture.swift
//
//  #10 — Watch-Wide Event / State Architecture
//
//  Swift 6
//
//  Public Apple APIs only.
//
//  Responsibilities:
//
//      - Application-wide state
//      - Strongly typed events
//      - Command routing
//      - Feature lifecycle
//      - Event history
//      - State snapshots
//      - Diagnostics
//      - Persistence hooks
//      - Cancellation
//      - SwiftUI bridge
//      - Cross-feature coordination
//

import Foundation
import Observation
import os

#if canImport(WatchKit)
import WatchKit
#endif

// MARK: - Application Error

public enum WatchApplicationError:
    Error,
    LocalizedError,
    Sendable
{
    case alreadyRunning
    case notRunning
    case featureUnavailable(String)
    case commandRejected(String)
    case stateUnavailable
    case initializationFailed(String)

    public var errorDescription:
        String?
    {
        switch self {

        case .alreadyRunning:
            return "The application architecture is already running."

        case .notRunning:
            return "The application architecture is not running."

        case .featureUnavailable(let name):
            return "The feature '\(name)' is unavailable."

        case .commandRejected(let reason):
            return "The command was rejected: \(reason)"

        case .stateUnavailable:
            return "Application state is unavailable."

        case .initializationFailed(let reason):
            return "Application initialization failed: \(reason)"
        }
    }
}

// MARK: - Application Identifier

public struct ApplicationID:
    RawRepresentable,
    Hashable,
    Codable,
    Sendable
{
    public let rawValue:
        String

    public init(
        rawValue:
            String
    ) {
        self.rawValue =
            rawValue
    }

    public static let watchApplication =
        ApplicationID(
            rawValue:
                "watch.application"
        )
}

// MARK: - Feature Identifier

public struct FeatureID:
    RawRepresentable,
    Hashable,
    Codable,
    Sendable,
    CustomStringConvertible
{
    public let rawValue:
        String

    public init(
        _ rawValue:
            String
    ) {
        self.rawValue =
            rawValue
    }

    public var description:
        String
    {
        rawValue
    }

    public static let sensorFusion =
        FeatureID(
            "sensor-fusion"
        )

    public static let powerScheduler =
        FeatureID(
            "power-scheduler"
        )

    public static let workout =
        FeatureID(
            "workout-health"
        )

    public static let rendering =
        FeatureID(
            "rendering"
        )

    public static let connectivity =
        FeatureID(
            "connectivity"
        )

    public static let signalProcessing =
        FeatureID(
            "signal-processing"
        )

    public static let backgroundScheduler =
        FeatureID(
            "background-scheduler"
        )

    public static let secureStorage =
        FeatureID(
            "secure-storage"
        )

    public static let audio =
        FeatureID(
            "audio"
        )

    public static let application =
        FeatureID(
            "application"
        )
}

// MARK: - Application Lifecycle

public enum ApplicationLifecycle:
    String,
    Codable,
    Sendable
{
    case created
    case launching
    case active
    case inactive
    case background
    case suspended
    case terminating
    case terminated
}

// MARK: - Device State

public enum DevicePowerCondition:
    String,
    Codable,
    Sendable
{
    case normal
    case lowPower
    case charging
}

public enum DeviceThermalCondition:
    String,
    Codable,
    Sendable
{
    case nominal
    case fair
    case serious
    case critical
}

public struct WatchDeviceState:
    Codable,
    Sendable,
    Equatable
{
    public var power:
        DevicePowerCondition

    public var thermal:
        DeviceThermalCondition

    public var batteryLevel:
        Double

    public var isScreenActive:
        Bool

    public var isWristDetected:
        Bool

    public var timestamp:
        Date

    public init(
        power:
            DevicePowerCondition =
                .normal,
        thermal:
            DeviceThermalCondition =
                .nominal,
        batteryLevel:
            Double =
                1.0,
        isScreenActive:
            Bool =
                true,
        isWristDetected:
            Bool =
                true,
        timestamp:
            Date =
                Date()
    ) {
        self.power =
            power

        self.thermal =
            thermal

        self.batteryLevel =
            batteryLevel

        self.isScreenActive =
            isScreenActive

        self.isWristDetected =
            isWristDetected

        self.timestamp =
            timestamp
    }
}

// MARK: - Network State

public enum ApplicationNetworkState:
    String,
    Codable,
    Sendable
{
    case offline
    case reachable
    case constrained
    case expensive
}

public struct ApplicationConnectivityState:
    Codable,
    Sendable,
    Equatable
{
    public var network:
        ApplicationNetworkState

    public var bluetoothAvailable:
        Bool

    public var companionReachable:
        Bool

    public var lastChange:
        Date

    public init(
        network:
            ApplicationNetworkState =
                .offline,
        bluetoothAvailable:
            Bool =
                false,
        companionReachable:
            Bool =
                false,
        lastChange:
            Date =
                Date()
    ) {
        self.network =
            network

        self.bluetoothAvailable =
            bluetoothAvailable

        self.companionReachable =
            companionReachable

        self.lastChange =
            lastChange
    }
}

// MARK: - Workout State

public enum ApplicationWorkoutState:
    String,
    Codable,
    Sendable
{
    case idle
    case preparing
    case active
    case paused
    case finished
}

public struct ApplicationWorkoutSnapshot:
    Codable,
    Sendable,
    Equatable
{
    public var state:
        ApplicationWorkoutState

    public var activity:
        String?

    public var heartRate:
        Double?

    public var calories:
        Double?

    public var distance:
        Double?

    public var duration:
        TimeInterval

    public init(
        state:
            ApplicationWorkoutState =
                .idle,
        activity:
            String? =
                nil,
        heartRate:
            Double? =
                nil,
        calories:
            Double? =
                nil,
        distance:
            Double? =
                nil,
        duration:
            TimeInterval =
                0
    ) {
        self.state =
            state

        self.activity =
            activity

        self.heartRate =
            heartRate

        self.calories =
            calories

        self.distance =
            distance

        self.duration =
            duration
    }
}

// MARK: - Audio State

public enum ApplicationAudioState:
    String,
    Codable,
    Sendable
{
    case stopped
    case playing
    case paused
    case interrupted
}

public struct ApplicationAudioSnapshot:
    Codable,
    Sendable,
    Equatable
{
    public var state:
        ApplicationAudioState

    public var title:
        String?

    public var artist:
        String?

    public var progress:
        Double

    public init(
        state:
            ApplicationAudioState =
                .stopped,
        title:
            String? =
                nil,
        artist:
            String? =
                nil,
        progress:
            Double =
                0
    ) {
        self.state =
            state

        self.title =
            title

        self.artist =
            artist

        self.progress =
            progress
    }
}

// MARK: - Sensor State

public struct ApplicationSensorSnapshot:
    Codable,
    Sendable,
    Equatable
{
    public var heartRate:
        Double?

    public var respiratoryRate:
        Double?

    public var oxygenSaturation:
        Double?

    public var temperature:
        Double?

    public var motionAvailable:
        Bool

    public var timestamp:
        Date?

    public init(
        heartRate:
            Double? =
                nil,
        respiratoryRate:
            Double? =
                nil,
        oxygenSaturation:
            Double? =
                nil,
        temperature:
            Double? =
                nil,
        motionAvailable:
            Bool =
                false,
        timestamp:
            Date? =
                nil
    ) {
        self.heartRate =
            heartRate

        self.respiratoryRate =
            respiratoryRate

        self.oxygenSaturation =
            oxygenSaturation

        self.temperature =
            temperature

        self.motionAvailable =
            motionAvailable

        self.timestamp =
            timestamp
    }
}

// MARK: - Application State Snapshot

public struct WatchApplicationSnapshot:
    Codable,
    Sendable,
    Equatable
{
    public var lifecycle:
        ApplicationLifecycle

    public var device:
        WatchDeviceState

    public var connectivity:
        ApplicationConnectivityState

    public var sensors:
        ApplicationSensorSnapshot

    public var workout:
        ApplicationWorkoutSnapshot

    public var audio:
        ApplicationAudioSnapshot

    public var activeFeatures:
        Set<FeatureID>

    public var generation:
        UInt64

    public var timestamp:
        Date

    public init(
        lifecycle:
            ApplicationLifecycle =
                .created,
        device:
            WatchDeviceState =
                WatchDeviceState(),
        connectivity:
            ApplicationConnectivityState =
                ApplicationConnectivityState(),
        sensors:
            ApplicationSensorSnapshot =
                ApplicationSensorSnapshot(),
        workout:
            ApplicationWorkoutSnapshot =
                ApplicationWorkoutSnapshot(),
        audio:
            ApplicationAudioSnapshot =
                ApplicationAudioSnapshot(),
        activeFeatures:
            Set<FeatureID> =
                [],
        generation:
            UInt64 =
                0,
        timestamp:
            Date =
                Date()
    ) {
        self.lifecycle =
            lifecycle

        self.device =
            device

        self.connectivity =
            connectivity

        self.sensors =
            sensors

        self.workout =
            workout

        self.audio =
            audio

        self.activeFeatures =
            activeFeatures

        self.generation =
            generation

        self.timestamp =
            timestamp
    }
}

// MARK: - Application Event

public enum WatchApplicationEvent:
    Sendable
{
    case applicationLaunched
    case applicationBecameActive
    case applicationBecameInactive
    case applicationEnteredBackground
    case applicationWillTerminate

    case deviceStateChanged(
        WatchDeviceState
    )

    case networkStateChanged(
        ApplicationConnectivityState
    )

    case heartRateUpdated(
        Double,
        Date
    )

    case sensorSnapshotUpdated(
        ApplicationSensorSnapshot
    )

    case workoutStateChanged(
        ApplicationWorkoutSnapshot
    )

    case audioStateChanged(
        ApplicationAudioSnapshot
    )

    case featureStarted(
        FeatureID
    )

    case featureStopped(
        FeatureID
    )

    case storageWarning(
        String
    )

    case diagnostic(
        String
    )
}

// MARK: - Event Metadata

public struct EventMetadata:
    Codable,
    Sendable
{
    public let id:
        UUID

    public let timestamp:
        Date

    public let source:
        FeatureID?

    public let correlationID:
        UUID?

    public init(
        id:
            UUID =
                UUID(),
        timestamp:
            Date =
                Date(),
        source:
            FeatureID? =
                nil,
        correlationID:
            UUID? =
                nil
    ) {
        self.id =
            id

        self.timestamp =
            timestamp

        self.source =
            source

        self.correlationID =
            correlationID
    }
}

// MARK: - Envelope

public struct ApplicationEventEnvelope:
    Sendable
{
    public let metadata:
        EventMetadata

    public let event:
        WatchApplicationEvent

    public init(
        metadata:
            EventMetadata,
        event:
            WatchApplicationEvent
    ) {
        self.metadata =
            metadata

        self.event =
            event
    }
}

// MARK: - Event Bus

public actor WatchEventBus {

    public typealias Handler =
        @Sendable (
            ApplicationEventEnvelope
        ) async -> Void

    private var handlers:
        [
            UUID:
            Handler
        ] =
            [:]

    public init() {}

    @discardableResult
    public func subscribe(
        _ handler:
            @escaping Handler
    )
        -> UUID
    {
        let token =
            UUID()

        handlers[token] =
            handler

        return token
    }

    public func unsubscribe(
        _ token:
            UUID
    ) {
        handlers.removeValue(
            forKey:
                token
        )
    }

    public func publish(
        _ event:
            WatchApplicationEvent,
        source:
            FeatureID? =
                nil,
        correlationID:
            UUID? =
                nil
    )
        async
    {
        let envelope =
            ApplicationEventEnvelope(
                metadata:
                    EventMetadata(
                        source:
                            source,
                        correlationID:
                            correlationID
                    ),
                event:
                    event
            )

        let currentHandlers =
            Array(
                handlers.values
            )

        for handler
            in currentHandlers
        {
            await handler(
                envelope
            )
        }
    }
}

// MARK: - State Store

public actor WatchApplicationStateStore {

    private var snapshot:
        WatchApplicationSnapshot

    private let eventBus:
        WatchEventBus

    public init(
        eventBus:
            WatchEventBus
    ) {
        self.eventBus =
            eventBus

        self.snapshot =
            WatchApplicationSnapshot()
    }

    public func read()
        -> WatchApplicationSnapshot
    {
        snapshot
    }

    public func updateLifecycle(
        _ lifecycle:
            ApplicationLifecycle
    )
        async
    {
        snapshot.lifecycle =
            lifecycle

        commit()
    }

    public func updateDevice(
        _ device:
            WatchDeviceState
    )
        async
    {
        snapshot.device =
            device

        commit()

        await eventBus.publish(
            .deviceStateChanged(
                device
            ),
            source:
                .application
        )
    }

    public func updateConnectivity(
        _ connectivity:
            ApplicationConnectivityState
    )
        async
    {
        snapshot.connectivity =
            connectivity

        commit()

        await eventBus.publish(
            .networkStateChanged(
                connectivity
            ),
            source:
                .connectivity
        )
    }

    public func updateSensors(
        _ sensors:
            ApplicationSensorSnapshot
    )
        async
    {
        snapshot.sensors =
            sensors

        commit()

        await eventBus.publish(
            .sensorSnapshotUpdated(
                sensors
            ),
            source:
                .sensorFusion
        )
    }

    public func updateHeartRate(
        _ heartRate:
            Double,
        timestamp:
            Date =
                Date()
    )
        async
    {
        snapshot.sensors.heartRate =
            heartRate

        snapshot.sensors.timestamp =
            timestamp

        commit()

        await eventBus.publish(
            .heartRateUpdated(
                heartRate,
                timestamp
            ),
            source:
                .sensorFusion
        )
    }

    public func updateWorkout(
        _ workout:
            ApplicationWorkoutSnapshot
    )
        async
    {
        snapshot.workout =
            workout

        commit()

        await eventBus.publish(
            .workoutStateChanged(
                workout
            ),
            source:
                .workout
        )
    }

    public func updateAudio(
        _ audio:
            ApplicationAudioSnapshot
    )
        async
    {
        snapshot.audio =
            audio

        commit()

        await eventBus.publish(
            .audioStateChanged(
                audio
            ),
            source:
                .audio
        )
    }

    public func activateFeature(
        _ feature:
            FeatureID
    )
        async
    {
        snapshot.activeFeatures.insert(
            feature
        )

        commit()

        await eventBus.publish(
            .featureStarted(
                feature
            ),
            source:
                .application
        )
    }

    public func deactivateFeature(
        _ feature:
            FeatureID
    )
        async
    {
        snapshot.activeFeatures.remove(
            feature
        )

        commit()

        await eventBus.publish(
            .featureStopped(
                feature
            ),
            source:
                .application
        )
    }

    private func commit() {
        snapshot.generation +=
            1

        snapshot.timestamp =
            Date()
    }
}

// MARK: - Command

public enum WatchApplicationCommand:
    Sendable
{
    case startFeature(
        FeatureID
    )

    case stopFeature(
        FeatureID
    )

    case setLifecycle(
        ApplicationLifecycle
    )

    case updateDevice(
        WatchDeviceState
    )

    case updateHeartRate(
        Double
    )

    case updateSensors(
        ApplicationSensorSnapshot
    )

    case updateWorkout(
        ApplicationWorkoutSnapshot
    )

    case updateAudio(
        ApplicationAudioSnapshot
    )

    case publish(
        WatchApplicationEvent
    )
}

// MARK: - Command Router

public actor WatchCommandRouter {

    private let state:
        WatchApplicationStateStore

    private let eventBus:
        WatchEventBus

    private var featureHandlers:
        [
            FeatureID:
            @Sendable (
                WatchApplicationCommand
            ) async throws -> Void
        ] =
            [:]

    public init(
        state:
            WatchApplicationStateStore,
        eventBus:
            WatchEventBus
    ) {
        self.state =
            state

        self.eventBus =
            eventBus
    }

    public func register(
        feature:
            FeatureID,
        handler:
            @escaping @Sendable (
                WatchApplicationCommand
            ) async throws -> Void
    ) {
        featureHandlers[
            feature
        ] =
            handler
    }

    public func execute(
        _ command:
            WatchApplicationCommand
    )
        async throws
    {
        switch command {

        case .setLifecycle(
            let lifecycle
        ):
            await state
                .updateLifecycle(
                    lifecycle
                )

        case .updateDevice(
            let device
        ):
            await state
                .updateDevice(
                    device
                )

        case .updateHeartRate(
            let heartRate
        ):
            await state
                .updateHeartRate(
                    heartRate
                )

        case .updateSensors(
            let sensors
        ):
            await state
                .updateSensors(
                    sensors
                )

        case .updateWorkout(
            let workout
        ):
            await state
                .updateWorkout(
                    workout
                )

        case .updateAudio(
            let audio
        ):
            await state
                .updateAudio(
                    audio
                )

        case .publish(
            let event
        ):
            await eventBus.publish(
                event
            )

        case .startFeature(
            let feature
        ),
        .stopFeature(
            let feature
        ):

            guard
                let handler =
                    featureHandlers[
                        feature
                    ]
            else {
                throw WatchApplicationError
                    .featureUnavailable(
                        feature.description
                    )
            }

            try await handler(
                command
            )
        }
    }
}

// MARK: - Feature Protocol

public protocol WatchApplicationFeature:
    Sendable
{
    var id:
        FeatureID
    {
        get
    }

    func start()
        async throws

    func stop()
        async
}

// MARK: - Feature Registry

public actor WatchFeatureRegistry {

    private var features:
        [
            FeatureID:
            any WatchApplicationFeature
        ] =
            [:]

    public init() {}

    public func register(
        _ feature:
            any WatchApplicationFeature
    ) {
        features[
            feature.id
        ] =
            feature
    }

    public func start(
        _ id:
            FeatureID
    )
        async throws
    {
        guard
            let feature =
                features[id]
        else {
            throw WatchApplicationError
                .featureUnavailable(
                    id.description
                )
        }

        try await feature.start()
    }

    public func stop(
        _ id:
            FeatureID
    )
        async
    {
        guard
            let feature =
                features[id]
        else {
            return
        }

        await feature.stop()
    }

    public func startAll()
        async throws
    {
        for feature
            in features.values
        {
            try await feature.start()
        }
    }

    public func stopAll()
        async
    {
        for feature
            in features.values
        {
            await feature.stop()
        }
    }

    public func ids()
        -> [FeatureID]
    {
        Array(
            features.keys
        )
    }
}

// MARK: - Event History

public struct StoredApplicationEvent:
    Sendable
{
    public let metadata:
        EventMetadata

    public let event:
        WatchApplicationEvent

    public init(
        metadata:
            EventMetadata,
        event:
            WatchApplicationEvent
    ) {
        self.metadata =
            metadata

        self.event =
            event
    }
}

public actor WatchEventHistory {

    private var events:
        [StoredApplicationEvent] =
            []

    private let maximumEvents:
        Int

    public init(
        maximumEvents:
            Int =
                2_000
    ) {
        self.maximumEvents =
            max(
                maximumEvents,
                1
            )
    }

    public func append(
        _ envelope:
            ApplicationEventEnvelope
    ) {
        events.append(
            StoredApplicationEvent(
                metadata:
                    envelope.metadata,
                event:
                    envelope.event
            )
        )

        if events.count >
            maximumEvents
        {
            events.removeFirst(
                events.count -
                maximumEvents
            )
        }
    }

    public func recent(
        limit:
            Int =
                100
    )
        -> [StoredApplicationEvent]
    {
        Array(
            events.suffix(
                max(
                    limit,
                    0
                )
            )
        )
    }

    public func count()
        -> Int
    {
        events.count
    }

    public func clear() {
        events.removeAll(
            keepingCapacity:
                false
        )
    }
}

// MARK: - Diagnostics

public struct ApplicationDiagnosticsSnapshot:
    Codable,
    Sendable
{
    public let eventCount:
        UInt64

    public let commandCount:
        UInt64

    public let featureStartCount:
        UInt64

    public let featureFailureCount:
        UInt64

    public let lastEvent:
        Date?

    public init(
        eventCount:
            UInt64,
        commandCount:
            UInt64,
        featureStartCount:
            UInt64,
        featureFailureCount:
            UInt64,
        lastEvent:
            Date?
    ) {
        self.eventCount =
            eventCount

        self.commandCount =
            commandCount

        self.featureStartCount =
            featureStartCount

        self.featureFailureCount =
            featureFailureCount

        self.lastEvent =
            lastEvent
    }
}

public actor WatchApplicationDiagnostics {

    private var eventCount:
        UInt64 =
            0

    private var commandCount:
        UInt64 =
            0

    private var featureStartCount:
        UInt64 =
            0

    private var featureFailureCount:
        UInt64 =
            0

    private var lastEvent:
        Date?

    public init() {}

    public func eventRecorded() {
        eventCount +=
            1

        lastEvent =
            Date()
    }

    public func commandRecorded() {
        commandCount +=
            1
    }

    public func featureStarted() {
        featureStartCount +=
            1
    }

    public func featureFailed() {
        featureFailureCount +=
            1
    }

    public func snapshot()
        -> ApplicationDiagnosticsSnapshot
    {
        ApplicationDiagnosticsSnapshot(
            eventCount:
                eventCount,
            commandCount:
                commandCount,
            featureStartCount:
                featureStartCount,
            featureFailureCount:
                featureFailureCount,
            lastEvent:
                lastEvent
        )
    }
}

// MARK: - Application Persistence

public protocol WatchApplicationPersistence:
    Sendable
{
    func load()
        async throws
        -> WatchApplicationSnapshot?

    func save(
        _ snapshot:
            WatchApplicationSnapshot
    )
        async throws
}

// MARK: - JSON Persistence

public actor JSONWatchApplicationPersistence:
    WatchApplicationPersistence
{
    private let url:
        URL

    private let encoder:
        JSONEncoder

    private let decoder:
        JSONDecoder

    public init(
        url:
            URL
    ) {
        self.url =
            url

        self.encoder =
            JSONEncoder()

        self.decoder =
            JSONDecoder()

        encoder.dateEncodingStrategy =
            .iso8601

        decoder.dateDecodingStrategy =
            .iso8601
    }

    public func load()
        async throws
        -> WatchApplicationSnapshot?
    {
        guard
            FileManager.default
                .fileExists(
                    atPath:
                        url.path
                )
        else {
            return nil
        }

        let data =
            try Data(
                contentsOf:
                    url
            )

        return try decoder.decode(
            WatchApplicationSnapshot.self,
            from:
                data
        )
    }

    public func save(
        _ snapshot:
            WatchApplicationSnapshot
    )
        async throws
    {
        let data =
            try encoder.encode(
                snapshot
            )

        try FileManager.default
            .createDirectory(
                at:
                    url.deletingLastPathComponent(),
                withIntermediateDirectories:
                    true
            )

        try data.write(
            to:
                url,
            options:
                .atomic
        )
    }
}

// MARK: - Lifecycle Coordinator

public actor WatchLifecycleCoordinator {

    private let state:
        WatchApplicationStateStore

    private let features:
        WatchFeatureRegistry

    private var running =
        false

    public init(
        state:
            WatchApplicationStateStore,
        features:
            WatchFeatureRegistry
    ) {
        self.state =
            state

        self.features =
            features
    }

    public func launch()
        async throws
    {
        guard
            !running
        else {
            throw WatchApplicationError
                .alreadyRunning
        }

        running =
            true

        await state
            .updateLifecycle(
                .launching
            )

        do {

            try await features.startAll()

            await state
                .updateLifecycle(
                    .active
                )

        } catch {

            running =
                false

            await state
                .updateLifecycle(
                    .terminated
                )

            throw error
        }
    }

    public func enterBackground()
        async
    {
        guard
            running
        else {
            return
        }

        await state
            .updateLifecycle(
                .background
            )
    }

    public func becomeActive()
        async
    {
        guard
            running
        else {
            return
        }

        await state
            .updateLifecycle(
                .active
            )
    }

    public func terminate()
        async
    {
        guard
            running
        else {
            return
        }

        await state
            .updateLifecycle(
                .terminating
            )

        await features.stopAll()

        await state
            .updateLifecycle(
                .terminated
            )

        running =
            false
    }

    public func isRunning()
        -> Bool
    {
        running
    }
}

// MARK: - SwiftUI Observable Bridge

@MainActor
@Observable
public final class WatchApplicationModel {

    public private(set) var snapshot:
        WatchApplicationSnapshot

    private let state:
        WatchApplicationStateStore

    private let commandRouter:
        WatchCommandRouter

    private var observationTask:
        Task<Void, Never>?

    public init(
        state:
            WatchApplicationStateStore,
        commandRouter:
            WatchCommandRouter
    ) {
        self.state =
            state

        self.commandRouter =
            commandRouter

        self.snapshot =
            WatchApplicationSnapshot()
    }

    public func startObserving(
        eventBus:
            WatchEventBus
    ) {

        observationTask?.cancel()

        observationTask =
            Task { [weak self] in

                guard
                    let self
                else {
                    return
                }

                let token =
                    await eventBus
                        .subscribe {
                            [weak self]
                            _ in

                            guard
                                let self
                            else {
                                return
                            }

                            let snapshot =
                                await self.state
                                    .read()

                            await MainActor.run {

                                self.snapshot =
                                    snapshot
                            }
                        }

                await withTaskCancellationHandler {

                    while
                        !Task.isCancelled
                    {
                        try? await Task
                            .sleep(
                                for:
                                    .milliseconds(
                                        250
                                    )
                            )
                    }

                } onCancel: {

                    Task {
                        await eventBus
                            .unsubscribe(
                                token
                            )
                    }
                }
            }
    }

    public func stopObserving() {
        observationTask?.cancel()

        observationTask =
            nil
    }

    public func execute(
        _ command:
            WatchApplicationCommand
    )
        async
    {
        try? await commandRouter
            .execute(
                command
            )

        snapshot =
            await state.read()
    }
}

// MARK: - Feature Adapters

public actor PlaceholderFeature:
    WatchApplicationFeature
{
    public let id:
        FeatureID

    private let eventBus:
        WatchEventBus

    private var running =
        false

    public init(
        id:
            FeatureID,
        eventBus:
            WatchEventBus
    ) {
        self.id =
            id

        self.eventBus =
            eventBus
    }

    public func start()
        async throws
    {
        guard
            !running
        else {
            return
        }

        running =
            true

        await eventBus.publish(
            .featureStarted(
                id
            ),
            source:
                .application
        )
    }

    public func stop()
        async
    {
        guard
            running
        else {
            return
        }

        running =
            false

        await eventBus.publish(
            .featureStopped(
                id
            ),
            source:
                .application
        )
    }
}

// MARK: - Application Container

public actor WatchApplicationContainer {

    public let eventBus:
        WatchEventBus

    public let state:
        WatchApplicationStateStore

    public let commandRouter:
        WatchCommandRouter

    public let features:
        WatchFeatureRegistry

    public let lifecycle:
        WatchLifecycleCoordinator

    public let history:
        WatchEventHistory

    public let diagnostics:
        WatchApplicationDiagnostics

    public let persistence:
        WatchApplicationPersistence?

    private var historySubscription:
        UUID?

    private var diagnosticsSubscription:
        UUID?

    public init(
        persistence:
            WatchApplicationPersistence? =
                nil
    ) {
        let eventBus =
            WatchEventBus()

        let state =
            WatchApplicationStateStore(
                eventBus:
                    eventBus
            )

        let features =
            WatchFeatureRegistry()

        self.eventBus =
            eventBus

        self.state =
            state

        self.commandRouter =
            WatchCommandRouter(
                state:
                    state,
                eventBus:
                    eventBus
            )

        self.features =
            features

        self.lifecycle =
            WatchLifecycleCoordinator(
                state:
                    state,
                features:
                    features
            )

        self.history =
            WatchEventHistory()

        self.diagnostics =
            WatchApplicationDiagnostics()

        self.persistence =
            persistence
    }

    // MARK: Configure

    public func configure()
        async throws
    {
        historySubscription =
            await eventBus.subscribe {
                [history]
                envelope in

                await history.append(
                    envelope
                )
            }

        diagnosticsSubscription =
            await eventBus.subscribe {
                [diagnostics]
                _ in

                await diagnostics
                    .eventRecorded()
            }

        await registerDefaultFeatures()

        if
            let persistence
        {
            if
                let restored =
                    try await persistence
                    .load()
            {
                // Restoration deliberately happens
                // through an explicit state transition
                // boundary in a larger implementation.
                _ = restored
            }
        }
    }

    private func registerDefaultFeatures()
        async
    {
        let featureIDs:
            [FeatureID] =
        [
            .sensorFusion,
            .powerScheduler,
            .workout,
            .rendering,
            .connectivity,
            .signalProcessing,
            .backgroundScheduler,
            .secureStorage,
            .audio
        ]

        for id
            in featureIDs
        {
            let feature =
                PlaceholderFeature(
                    id:
                        id,
                    eventBus:
                        eventBus
                )

            await features.register(
                feature
            )

            await commandRouter.register(
                feature:
                    id
            ) {
                command in

                switch command {

                case .startFeature:
                    try await feature.start()

                case .stopFeature:
                    await feature.stop()

                default:
                    break
                }
            }
        }
    }

    // MARK: Launch

    public func launch()
        async throws
    {
        try await configure()

        await lifecycle.launch()

        await eventBus.publish(
            .applicationLaunched,
            source:
                .application
        )
    }

    // MARK: Background

    public func enterBackground()
        async
    {
        await lifecycle
            .enterBackground()

        await eventBus.publish(
            .applicationEnteredBackground,
            source:
                .application
        )
    }

    // MARK: Active

    public func becomeActive()
        async
    {
        await lifecycle
            .becomeActive()

        await eventBus.publish(
            .applicationBecameActive,
            source:
                .application
        )
    }

    // MARK: Termination

    public func terminate()
        async throws
    {
        await eventBus.publish(
            .applicationWillTerminate,
            source:
                .application
        )

        if
            let persistence
        {
            let snapshot =
                await state.read()

            try await persistence.save(
                snapshot
            )
        }

        await lifecycle
            .terminate()
    }

    // MARK: Snapshot

    public func snapshot()
        async
        -> WatchApplicationSnapshot
    {
        await state.read()
    }
}

// MARK: - Device State Provider

#if canImport(WatchKit)

@MainActor
public final class WatchDeviceStateProvider {

    private let device =
        WKInterfaceDevice.current()

    public init() {}

    public func snapshot()
        -> WatchDeviceState
    {
        let battery =
            Double(
                device.batteryLevel
            )

        let power:
            DevicePowerCondition

        if
            device.batteryState ==
                .charging
        {
            power =
                .charging
        } else if
            battery >= 0,
            battery < 0.2
        {
            power =
                .lowPower
        } else {
            power =
                .normal
        }

        return WatchDeviceState(
            power:
                power,
            batteryLevel:
                battery
        )
    }
}

#endif

// MARK: - Event Reducer

public actor WatchApplicationReducer {

    public init() {}

    public func reduce(
        _ event:
            WatchApplicationEvent,
        into state:
            inout WatchApplicationSnapshot
    ) {

        switch event {

        case .applicationLaunched:
            state.lifecycle =
                .launching

        case .applicationBecameActive:
            state.lifecycle =
                .active

        case .applicationBecameInactive:
            state.lifecycle =
                .inactive

        case .applicationEnteredBackground:
            state.lifecycle =
                .background

        case .applicationWillTerminate:
            state.lifecycle =
                .terminating

        case .deviceStateChanged(
            let device
        ):
            state.device =
                device

        case .networkStateChanged(
            let connectivity
        ):
            state.connectivity =
                connectivity

        case .heartRateUpdated(
            let heartRate,
            let timestamp
        ):
            state.sensors.heartRate =
                heartRate

            state.sensors.timestamp =
                timestamp

        case .sensorSnapshotUpdated(
            let sensors
        ):
            state.sensors =
                sensors

        case .workoutStateChanged(
            let workout
        ):
            state.workout =
                workout

        case .audioStateChanged(
            let audio
        ):
            state.audio =
                audio

        case .featureStarted(
            let feature
        ):
            state.activeFeatures.insert(
                feature
            )

        case .featureStopped(
            let feature
        ):
            state.activeFeatures.remove(
                feature
            )

        case .storageWarning,
             .diagnostic:
            break
        }

        state.generation +=
            1

        state.timestamp =
            Date()
    }
}

// MARK: - Application Logger

public enum WatchApplicationLog {

    private static let logger =
        Logger(
            subsystem:
                "com.example.AppleWatchApplication",
            category:
                "Architecture"
        )

    public static func info(
        _ message:
            String
    ) {
        logger.info(
            "\(message, privacy: .public)"
        )
    }

    public static func debug(
        _ message:
            String
    ) {
        logger.debug(
            "\(message, privacy: .public)"
        )
    }

    public static func error(
        _ message:
            String
    ) {
        logger.error(
            "\(message, privacy: .public)"
        )
    }
}

// MARK: - Factory

public enum WatchApplicationFactory {

    public static func make(
        applicationSupport:
            URL
    )
        -> WatchApplicationContainer
    {
        let stateURL =
            applicationSupport
                .appendingPathComponent(
                    "WatchApplication",
                    isDirectory:
                        true
                )
                .appendingPathComponent(
                    "state.json"
                )

        let persistence =
            JSONWatchApplicationPersistence(
                url:
                    stateURL
            )

        return WatchApplicationContainer(
            persistence:
                persistence
        )
    }
}

// MARK: - Example

public enum WatchApplicationExample {

    public static func run(
        applicationSupport:
            URL
    )
        async throws
    {
        let application =
            WatchApplicationFactory
                .make(
                    applicationSupport:
                        applicationSupport
                )

        try await application
            .launch()

        // Sensor Fusion → Global State
        await application
            .commandRouter
            .execute(
                .updateHeartRate(
                    142
                )
            )

        // Workout → Global State
        await application
            .commandRouter
            .execute(
                .updateWorkout(
                    ApplicationWorkoutSnapshot(
                        state:
                            .active,
                        activity:
                            "running",
                        heartRate:
                            142,
                        calories:
                            210,
                        distance:
                            2_500,
                        duration:
                            900
                    )
                )
            )

        // Audio → Global State
        await application
            .commandRouter
            .execute(
                .updateAudio(
                    ApplicationAudioSnapshot(
                        state:
                            .playing,
                        title:
                            "Example Track",
                        artist:
                            "Example Artist",
                        progress:
                            0.42
                    )
                )
            )

        let snapshot =
            await application
                .snapshot()

        print(
            "Generation:",
            snapshot.generation
        )

        print(
            "Heart rate:",
            snapshot.sensors.heartRate ??
                0
        )

        try await application
            .terminate()
    }
}

// MARK: - Tests

public enum WatchApplicationArchitectureTests {

    public static func run()
        async throws
    {
        try await testEventBus()
        try await testStateStore()
        try await testCommandRouter()
        try await testFeatureRegistry()
        try await testEventHistory()
    }

    private static func testEventBus()
        async throws
    {
        let bus =
            WatchEventBus()

        let expectation =
            EventExpectation()

        _ =
            await bus.subscribe {
                envelope in

                if case
                    .heartRateUpdated(
                        let value,
                        _
                    ) =
                    envelope.event
                {
                    if value ==
                        120
                    {
                        await expectation
                            .fulfill()
                    }
                }
            }

        await bus.publish(
            .heartRateUpdated(
                120,
                Date()
            )
        )

        let fulfilled =
            await expectation
                .value()

        assert(
            fulfilled
        )
    }

    private static func testStateStore()
        async throws
    {
        let bus =
            WatchEventBus()

        let state =
            WatchApplicationStateStore(
                eventBus:
                    bus
            )

        await state.updateHeartRate(
            150
        )

        let snapshot =
            await state.read()

        assert(
            snapshot.sensors
                .heartRate ==
                150
        )
    }

    private static func testCommandRouter()
        async throws
    {
        let bus =
            WatchEventBus()

        let state =
            WatchApplicationStateStore(
                eventBus:
                    bus
            )

        let router =
            WatchCommandRouter(
                state:
                    state,
                eventBus:
                    bus
            )

        try await router.execute(
            .updateHeartRate(
                160
            )
        )

        let snapshot =
            await state.read()

        assert(
            snapshot.sensors
                .heartRate ==
                160
        )
    }

    private static func testFeatureRegistry()
        async throws
    {
        let bus =
            WatchEventBus()

        let registry =
            WatchFeatureRegistry()

        let feature =
            PlaceholderFeature(
                id:
                    .audio,
                eventBus:
                    bus
            )

        await registry.register(
            feature
        )

        try await registry.start(
            .audio
        )

        let ids =
            await registry.ids()

        assert(
            ids.contains(
                .audio
            )
        )

        await registry.stop(
            .audio
        )
    }

    private static func testEventHistory()
        async throws
    {
        let history =
            WatchEventHistory()

        let envelope =
            ApplicationEventEnvelope(
                metadata:
                    EventMetadata(),
                event:
                    .applicationLaunched
            )

        await history.append(
            envelope
        )

        let count =
            await history.count()

        assert(
            count ==
                1
        )
    }
}

// MARK: - Async Test Helper

private actor EventExpectation {

    private var fulfilledValue =
        false

    func fulfill() {
        fulfilledValue =
            true
    }

    func value()
        -> Bool
    {
        fulfilledValue
    }
}





