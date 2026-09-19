1. Apple-style motion engine
import SwiftUI
import UIKit

// MARK: - Apple 2030 Motion

enum AppleMotion {

    // Very responsive spring for direct manipulation
    static let interactive = Animation.spring(
        response: 0.32,
        dampingFraction: 0.82,
        blendDuration: 0.12
    )

    // Elegant UI transition
    static let elegant = Animation.spring(
        response: 0.48,
        dampingFraction: 0.86,
        blendDuration: 0.18
    )

    // Large spatial movement
    static let spatial = Animation.spring(
        response: 0.65,
        dampingFraction: 0.88,
        blendDuration: 0.22
    )

    // Tiny micro-interaction
    static let micro = Animation.spring(
        response: 0.20,
        dampingFraction: 0.78,
        blendDuration: 0.08
    )
}


// MARK: - 2030 Motion Namespace

struct AppleMotionModifier: ViewModifier {

    let depth: CGFloat
    let intensity: CGFloat

    @State private var phase: CGFloat = 0

    func body(content: Content) -> some View {

        content
            .scaleEffect(
                1.0 + sin(phase) * 0.004 * intensity
            )
            .offset(
                x: cos(phase * 0.7) * depth * intensity,
                y: sin(phase * 0.55) * depth * intensity
            )
            .onAppear {

                withAnimation(
                    .easeInOut(duration: 7.0)
                    .repeatForever(autoreverses: true)
                ) {
                    phase = .pi * 2
                }
            }
    }
}

extension View {

    func appleMotion(
        depth: CGFloat = 4,
        intensity: CGFloat = 1
    ) -> some View {

        modifier(
            AppleMotionModifier(
                depth: depth,
                intensity: intensity
            )
        )
    }
}


// MARK: - Atmospheric Background

struct AppleAtmosphere: View {

    @State private var animate = false

    var body: some View {

        GeometryReader { geo in

            ZStack {

                Color.black
                    .ignoresSafeArea()

                // Large atmospheric light
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                Color.white.opacity(0.13),
                                Color.white.opacity(0.025),
                                Color.clear
                            ],
                            center: .center,
                            startRadius: 0,
                            endRadius: 260
                        )
                    )
                    .frame(width: 520, height: 520)
                    .blur(radius: 30)
                    .offset(
                        x: animate
                            ? geo.size.width * 0.28
                            : -geo.size.width * 0.22,

                        y: animate
                            ? -geo.size.height * 0.15
                            : geo.size.height * 0.18
                    )

                // Secondary atmospheric layer
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                Color.blue.opacity(0.08),
                                Color.clear
                            ],
                            center: .center,
                            startRadius: 0,
                            endRadius: 220
                        )
                    )
                    .frame(width: 440, height: 440)
                    .blur(radius: 45)
                    .offset(
                        x: animate
                            ? -geo.size.width * 0.20
                            : geo.size.width * 0.25,

                        y: animate
                            ? geo.size.height * 0.22
                            : -geo.size.height * 0.10
                    )

                // Very subtle moving field
                Rectangle()
                    .fill(
                        LinearGradient(
                            colors: [
                                .clear,
                                .white.opacity(0.015),
                                .clear
                            ],
                            startPoint: animate
                                ? .topLeading
                                : .bottomTrailing,
                            endPoint: animate
                                ? .bottomTrailing
                                : .topLeading
                        )
                    )
                    .blur(radius: 30)
            }
            .animation(
                .easeInOut(duration: 12)
                .repeatForever(autoreverses: true),
                value: animate
            )
            .onAppear {
                animate = true
            }
        }
        .ignoresSafeArea()
    }
}


// MARK: - Depth Zoom

struct DepthZoomModifier: ViewModifier {

    let isActive: Bool

    func body(content: Content) -> some View {

        content
            .scaleEffect(isActive ? 1.0 : 0.94)
            .opacity(isActive ? 1.0 : 0.0)
            .blur(radius: isActive ? 0 : 8)
            .animation(
                AppleMotion.spatial,
                value: isActive
            )
    }
}

extension View {

    func depthZoom(
        active: Bool
    ) -> some View {

        modifier(
            DepthZoomModifier(
                isActive: active
            )
        )
    }
}


// MARK: - Pressed Spatial Effect

struct SpatialPress: ViewModifier {

    @GestureState private var pressed = false

    func body(content: Content) -> some View {

        content
            .scaleEffect(pressed ? 0.965 : 1.0)
            .brightness(pressed ? 0.035 : 0)
            .shadow(
                color: .black.opacity(
                    pressed ? 0.35 : 0.18
                ),
                radius: pressed ? 8 : 16,
                y: pressed ? 2 : 8
            )
            .animation(
                AppleMotion.micro,
                value: pressed
            )
            .simultaneousGesture(

                LongPressGesture(
                    minimumDuration: 0.01
                )
                .updating($pressed) {
                    value,
                    state,
                    _ in

                    state = value
                }
            )
    }
}

extension View {

    func spatialPress() -> some View {
        modifier(SpatialPress())
    }
}


// MARK: - Glass Surface

struct AppleGlass<Content: View>: View {

    let content: Content

    init(
        @ViewBuilder content: () -> Content
    ) {
        self.content = content()
    }

    var body: some View {

        content
            .padding()
            .background {

                RoundedRectangle(
                    cornerRadius: 28,
                    style: .continuous
                )
                .fill(
                    .ultraThinMaterial
                )
                .overlay {

                    RoundedRectangle(
                        cornerRadius: 28,
                        style: .continuous
                    )
                    .stroke(
                        LinearGradient(
                            colors: [
                                .white.opacity(0.22),
                                .white.opacity(0.035),
                                .white.opacity(0.12)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 0.7
                    )
                }
                .shadow(
                    color: .black.opacity(0.25),
                    radius: 30,
                    y: 15
                )
            }
    }
}


// MARK: - Moving Highlight

struct MovingHighlight: View {

    @State private var position: CGFloat = -1.2

    var body: some View {

        GeometryReader { geo in

            LinearGradient(
                colors: [
                    .clear,
                    .white.opacity(0.10),
                    .white.opacity(0.035),
                    .clear
                ],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(
                width: geo.size.width * 0.65
            )
            .rotationEffect(
                .degrees(15)
            )
            .offset(
                x: position * geo.size.width * 1.6
            )
            .blur(radius: 8)
            .onAppear {

                withAnimation(
                    .linear(duration: 5)
                    .repeatForever(autoreverses: false)
                ) {
                    position = 1.2
                }
            }
        }
        .clipped()
        .allowsHitTesting(false)
    }
}


// MARK: - Floating Card

struct Apple2030Card<Content: View>: View {

    let content: Content

    @State private var hovering = false

    init(
        @ViewBuilder content: () -> Content
    ) {
        self.content = content()
    }

    var body: some View {

        ZStack {

            RoundedRectangle(
                cornerRadius: 32,
                style: .continuous
            )
            .fill(.ultraThinMaterial)

            MovingHighlight()

            content
        }
        .clipShape(
            RoundedRectangle(
                cornerRadius: 32,
                style: .continuous
            )
        )
        .scaleEffect(
            hovering ? 1.015 : 1.0
        )
        .shadow(
            color: .black.opacity(
                hovering ? 0.32 : 0.20
            ),
            radius: hovering ? 38 : 24,
            y: hovering ? 20 : 12
        )
        .animation(
            AppleMotion.elegant,
            value: hovering
        )
    }
}


// MARK: - Hero Zoom Transition

struct HeroZoom<Content: View>: View {

    let content: Content
    let active: Bool

    init(
        active: Bool,
        @ViewBuilder content: () -> Content
    ) {
        self.active = active
        self.content = content()
    }

    var body: some View {

        content
            .scaleEffect(
                active ? 1.0 : 0.72
            )
            .opacity(
                active ? 1.0 : 0.0
            )
            .blur(
                radius: active ? 0 : 14
            )
            .animation(
                .spring(
                    response: 0.58,
                    dampingFraction: 0.84
                ),
                value: active
            )
    }
}
2. A complete animated 2030-style screen

This demonstrates the pieces working together:

struct Apple2030Demo: View {

    @State private var selected = 0
    @State private var showDetail = false

    var body: some View {

        ZStack {

            AppleAtmosphere()

            ScrollView(
                .vertical,
                showsIndicators: false
            ) {

                VStack(
                    alignment: .leading,
                    spacing: 22
                ) {

                    // MARK: Header

                    VStack(
                        alignment: .leading,
                        spacing: 6
                    ) {

                        Text("Good evening")
                            .font(
                                .system(
                                    size: 20,
                                    weight: .medium,
                                    design: .rounded
                                )
                            )
                            .foregroundStyle(
                                .secondary
                            )

                        Text("Aureom")
                            .font(
                                .system(
                                    size: 52,
                                    weight: .bold,
                                    design: .rounded
                                )
                            )
                            .tracking(-2.5)
                    }
                    .appleMotion(
                        depth: 2
                    )

                    // MARK: Hero

                    Button {

                        withAnimation(
                            AppleMotion.spatial
                        ) {
                            showDetail.toggle()
                        }

                    } label: {

                        Apple2030Card {

                            VStack(
                                alignment: .leading,
                                spacing: 18
                            ) {

                                HStack {

                                    Image(
                                        systemName:
                                            "sparkles"
                                    )
                                    .font(.title2)

                                    Spacer()

                                    Image(
                                        systemName:
                                            "arrow.up.right"
                                    )
                                }

                                Spacer()

                                Text("Intelligence")
                                    .font(
                                        .system(
                                            size: 34,
                                            weight: .semibold,
                                            design: .rounded
                                        )
                                    )

                                Text(
                                    "Everything you need, "
                                    + "moving at the speed of thought."
                                )
                                .font(
                                    .system(
                                        size: 17,
                                        weight: .regular,
                                        design: .rounded
                                    )
                                )
                                .foregroundStyle(
                                    .secondary
                                )
                            }
                            .padding(26)
                            .frame(
                                maxWidth: .infinity,
                                minHeight: 260,
                                alignment: .topLeading
                            )
                        }
                    }
                    .buttonStyle(.plain)
                    .spatialPress()

                    // MARK: Cards

                    HStack(spacing: 14) {

                        Apple2030Card {

                            VStack(
                                alignment: .leading,
                                spacing: 12
                            ) {

                                Image(
                                    systemName:
                                        "waveform"
                                )
                                .font(.title)

                                Text("Live")
                                    .font(
                                        .system(
                                            size: 21,
                                            weight: .semibold,
                                            design: .rounded
                                        )
                                    )

                                Text("Active")
                                    .foregroundStyle(
                                        .secondary
                                    )
                            }
                            .padding(20)
                            .frame(
                                width: 160,
                                height: 150,
                                alignment: .topLeading
                            )
                        }

                        Apple2030Card {

                            VStack(
                                alignment: .leading,
                                spacing: 12
                            ) {

                                Image(
                                    systemName:
                                        "bolt.fill"
                                )
                                .font(.title)

                                Text("Fast")
                                    .font(
                                        .system(
                                            size: 21,
                                            weight: .semibold,
                                            design: .rounded
                                        )
                                    )

                                Text("120 Hz")
                                    .foregroundStyle(
                                        .secondary
                                    )
                            }
                            .padding(20)
                            .frame(
                                width: 160,
                                height: 150,
                                alignment: .topLeading
                            )
                        }
                    }
                }
                .padding(22)
            }

            // MARK: Detail Layer

            if showDetail {

                ZStack {

                    Color.black
                        .opacity(0.35)
                        .ignoresSafeArea()
                        .transition(.opacity)

                    HeroZoom(active: showDetail) {

                        Apple2030Card {

                            VStack(
                                alignment: .leading,
                                spacing: 20
                            ) {

                                HStack {

                                    Text("Intelligence")
                                        .font(
                                            .system(
                                                size: 32,
                                                weight: .bold,
                                                design: .rounded
                                            )
                                        )

                                    Spacer()

                                    Button {

                                        withAnimation(
                                            AppleMotion.spatial
                                        ) {
                                            showDetail = false
                                        }

                                    } label: {

                                        Image(
                                            systemName:
                                                "xmark"
                                        )
                                        .font(.title3)
                                        .padding(12)
                                        .background(
                                            .thinMaterial,
                                            in: Circle()
                                        )
                                    }
                                }

                                Text(
                                    "A spatial interface that "
                                    + "responds continuously to you."
                                )
                                .font(
                                    .system(
                                        size: 18,
                                        design: .rounded
                                    )
                                )
                                .foregroundStyle(
                                    .secondary
                                )

                                Spacer()
                            }
                            .padding(28)
                            .frame(
                                maxWidth: .infinity,
                                minHeight: 420
                            )
                        }
                        .padding(22)
                    }
                }
            }
        }
    }
}
3. The really important part: continuous spatial motion

For the “Apple 2030” feeling, don't animate every object independently. Give the interface a single spatial coordinate system.

For example:

struct SpatialEnvironment {

    var scrollDepth: CGFloat = 0
    var deviceTiltX: CGFloat = 0
    var deviceTiltY: CGFloat = 0
    var interaction: CGFloat = 0

    var backgroundParallax: CGFloat {
        deviceTiltX * 0.5
    }

    var foregroundParallax: CGFloat {
        deviceTiltX * 1.8
    }

    var depthScale: CGFloat {
        1.0 + interaction * 0.025
    }
}

Then different layers respond at different rates:

ZStack {

    Background()
        .offset(
            x: environment.backgroundParallax,
            y: environment.deviceTiltY * 0.5
        )

    MiddleLayer()
        .offset(
            x: environment.deviceTiltX,
            y: environment.deviceTiltY
        )

    ForegroundCard()
        .offset(
            x: environment.foregroundParallax,
            y: environment.deviceTiltY * 1.5
        )
        .scaleEffect(
            environment.depthScale
        )
}

That creates the impression that the UI itself has depth, rather than simply having a bunch of animations.

4. Add device-motion parallax

For a more advanced version, use Core Motion:

import CoreMotion
import SwiftUI

@MainActor
final class SpatialMotion: ObservableObject {

    private let manager = CMMotionManager()

    @Published var x: CGFloat = 0
    @Published var y: CGFloat = 0

    init() {

        guard manager.isDeviceMotionAvailable else {
            return
        }

        manager.deviceMotionUpdateInterval = 1.0 / 60.0

        manager.startDeviceMotionUpdates(
            using: .referenceFrameXArbitraryCorrectedZVertical,
            to: .main
        ) { [weak self] motion, _ in

            guard
                let self,
                let motion
            else {
                return
            }

            let roll =
                CGFloat(motion.attitude.roll)

            let pitch =
                CGFloat(motion.attitude.pitch)

            self.x = max(
                -1,
                min(1, roll)
            )

            self.y = max(
                -1,
                min(1, pitch)
            )
        }
    }

    deinit {
        manager.stopDeviceMotionUpdates()
    }
}

Then:

struct SpatialBackground: View {

    @StateObject
    private var motion = SpatialMotion()

    var body: some View {

        ZStack {

            Circle()
                .fill(.white.opacity(0.08))
                .frame(width: 500)
                .blur(radius: 80)
                .offset(
                    x: motion.x * 35,
                    y: motion.y * 25
                )

            Circle()
                .fill(.blue.opacity(0.05))
                .frame(width: 350)
                .blur(radius: 70)
                .offset(
                    x: motion.x * -55,
                    y: motion.y * -35
                )
        }
    }
}

