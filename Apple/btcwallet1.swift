Motion.swift

import SwiftUI

enum AureomMotion {

    // MARK: - Standard

    static let standard =
        Animation.spring(
            response: 0.42,
            dampingFraction: 0.86,
            blendDuration: 0.12
        )

    // MARK: - Silk

    static let silk =
        Animation.spring(
            response: 0.58,
            dampingFraction: 0.92,
            blendDuration: 0.18
        )

    // MARK: - Snap

    static let snap =
        Animation.spring(
            response: 0.28,
            dampingFraction: 0.82,
            blendDuration: 0.08
        )

    // MARK: - Gentle

    static let gentle =
        Animation.easeInOut(
            duration: 0.32
        )

    // MARK: - Page transition

    static let page =
        Animation.spring(
            response: 0.52,
            dampingFraction: 0.9,
            blendDuration: 0.2
        )
}

The idea is that every animation in the application uses the same physical language.

2. Make the cards feel physical

Your wallet cards shouldn't simply slide.

They should have:

depth
parallax
subtle rotation
scale
shadow movement
glass/highlight response
continuous gesture tracking
struct SilkWalletCard<Content: View>: View {

    let content: Content

    @State private var pressed = false
    @State private var dragX: CGFloat = 0
    @State private var dragY: CGFloat = 0

    init(
        @ViewBuilder content: () -> Content
    ) {
        self.content = content()
    }

    var body: some View {

        content

            .scaleEffect(
                pressed ? 0.975 : 1.0
            )

            .rotation3DEffect(
                .degrees(
                    Double(dragX) * 0.025
                ),
                axis: (
                    x: 0,
                    y: 1,
                    z: 0
                )
            )

            .rotation3DEffect(
                .degrees(
                    Double(dragY) * -0.018
                ),
                axis: (
                    x: 1,
                    y: 0,
                    z: 0
                )
            )

            .shadow(
                color: .black.opacity(
                    pressed ? 0.10 : 0.18
                ),
                radius: pressed ? 12 : 24,
                y: pressed ? 6 : 14
            )

            .gesture(

                DragGesture(
                    minimumDistance: 0
                )

                .onChanged { value in

                    dragX = value.translation.width
                    dragY = value.translation.height

                    withAnimation(
                        AureomMotion.snap
                    ) {
                        pressed = true
                    }
                }

                .onEnded { _ in

                    withAnimation(
                        AureomMotion.silk
                    ) {

                        dragX = 0
                        dragY = 0
                        pressed = false
                    }
                }
            )
    }
}

This makes the card respond during the gesture rather than after it.

That's an important distinction.

3. Fluid card stack

I'd change the existing card carousel into something like this:

struct SilkCardStack: View {

    let cards: [WalletItem]

    @State private var selected = 0

    var body: some View {

        ZStack {

            ForEach(
                Array(cards.enumerated()),
                id: \.element.id
            ) { index, card in

                let distance =
                    index - selected

                WalletCardView(
                    item: card
                )

                .scaleEffect(
                    scale(for: distance)
                )

                .offset(
                    y: offset(for: distance)
                )

                .opacity(
                    opacity(for: distance)
                )

                .zIndex(
                    Double(
                        cards.count -
                        abs(distance)
                    )
                )

                .rotation3DEffect(
                    .degrees(
                        Double(distance) * -2.0
                    ),
                    axis: (
                        x: 0,
                        y: 1,
                        z: 0
                    )
                )

                .animation(
                    AureomMotion.silk,
                    value: selected
                )
            }
        }
    }

    private func scale(
        for distance: Int
    ) -> CGFloat {

        switch abs(distance) {

        case 0:
            return 1.0

        case 1:
            return 0.94

        case 2:
            return 0.89

        default:
            return 0.84
        }
    }

    private func offset(
        for distance: Int
    ) -> CGFloat {

        CGFloat(distance) * 18
    }

    private func opacity(
        for distance: Int
    ) -> Double {

        switch abs(distance) {

        case 0:
            return 1.0

        case 1:
            return 0.82

        case 2:
            return 0.55

        default:
            return 0.0
        }
    }
}

The result is much closer to a physical stack of cards rather than a collection of rectangular views.

4. Apple-style interactive transitions

The biggest improvement would be making the wallet feel spatially continuous.

For example:

Wallet
  │
  │ tap card
  ▼
Card expands from its exact position
  │
  ▼
Card Detail

rather than:

Wallet
  │
  └── fade out
       │
       └── new screen

Use matchedGeometryEffect.

struct WalletCardTransition: View {

    @Namespace private var namespace

    @State private var selected:
        WalletItem?

    let cards: [WalletItem]

    var body: some View {

        ZStack {

            if let selected {

                WalletCardDetailView(
                    item: selected
                )
                .matchedGeometryEffect(
                    id: selected.id,
                    in: namespace
                )
                .transition(
                    .opacity
                )

            } else {

                ScrollView {

                    VStack(spacing: 18) {

                        ForEach(cards) { card in

                            WalletCardView(
                                item: card
                            )
                            .matchedGeometryEffect(
                                id: card.id,
                                in: namespace
                            )
                            .onTapGesture {

                                withAnimation(
                                    AureomMotion.silk
                                ) {

                                    selected = card
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

That gives you the feeling that the card itself becomes the next screen.

5. Add a liquid glass layer

For the 2030 aesthetic, I'd avoid excessive conventional gradients.

Instead:

struct WalletGlassBackground:
    ViewModifier {

    func body(
        content: Content
    ) -> some View {

        content

            .background(
                .ultraThinMaterial,
                in: RoundedRectangle(
                    cornerRadius: 28,
                    style: .continuous
                )
            )

            .overlay {

                RoundedRectangle(
                    cornerRadius: 28,
                    style: .continuous
                )
                .stroke(
                    .white.opacity(0.16),
                    lineWidth: 0.7
                )
            }
    }
}

extension View {

    func walletGlass() -> some View {

        modifier(
            WalletGlassBackground()
        )
    }
}

Use this sparingly.

The future Apple aesthetic should be material-driven, not "everything is glass".

6. Micro-interactions

The wallet should respond to almost everything.

For example, a successful payment:

struct PaymentSuccessAnimation:
    View {

    @State private var scale = 0.4
    @State private var opacity = 0.0

    var body: some View {

        ZStack {

            Circle()
                .stroke(
                    .green.opacity(0.18),
                    lineWidth: 2
                )
                .scaleEffect(scale)

            Image(
                systemName:
                    "checkmark"
            )
            .font(
                .system(
                    size: 38,
                    weight: .semibold
                )
            )
            .scaleEffect(scale)
            .opacity(opacity)
        }

        .onAppear {

            withAnimation(
                AureomMotion.silk
            ) {

                scale = 1.0
                opacity = 1.0
            }
        }
    }
}

But I'd actually go further and make the payment confirmation feel like the wallet has absorbed the transaction.

PAY £42.50
       ↓
card contracts slightly
       ↓
payment pulse
       ↓
✓
       ↓
balance morphs
       ↓
transaction appears

No separate "success page" necessary.

7. Animated balance

This is especially important for a financial application.

Instead of:

£12,450.00

instantly becoming:

£12,407.50

animate the numeric value.

struct AnimatedBalance: View {

    let value: Double

    var body: some View {

        Text(
            value,
            format: .currency(
                code: "GBP"
            )
        )
        .contentTransition(
            .numericText()
        )
        .animation(
            AureomMotion.silk,
            value: value
        )
    }
}

This is one of those tiny things that makes the whole application feel dramatically more expensive.

8. BTC balance

Same mechanism:

struct BitcoinBalance: View {

    let sats: UInt64

    private var btc: Double {
        Double(sats) / 100_000_000
    }

    var body: some View {

        VStack(
            alignment: .leading,
            spacing: 5
        ) {

            Text("BITCOIN")
                .font(.caption2)
                .tracking(1.5)
                .opacity(0.55)

            Text(
                btc,
                format: .number
            )
            .font(
                .system(
                    size: 34,
                    weight: .medium,
                    design: .rounded
                )
            )
            .contentTransition(
                .numericText()
            )

            Text("BTC")
                .font(.caption)
                .opacity(0.5)
        }
        .animation(
            AureomMotion.silk,
            value: sats
        )
    }
}

For the actual wallet engine, however, keep sats as the authoritative value and only convert to presentation values.

9. Haptic + animation synchronization

Don't trigger haptics randomly.

Tie them to meaningful state transitions.

import UIKit

final class WalletHaptics {

    static let shared =
        WalletHaptics()

    private let success =
        UINotificationFeedbackGenerator()

    private let impact =
        UIImpactFeedbackGenerator(
            style: .soft
        )

    func selection() {

        impact.impactOccurred()
    }

    func successPayment() {

        success.notificationOccurred(
            .success
        )
    }
}

Then:

withAnimation(AureomMotion.silk) {

    paymentCompleted = true
}

WalletHaptics.shared.successPayment()

The haptic should happen at the physical moment of completion, not when the network request starts.

10. The really important part: 120 Hz

The animation architecture should be designed around ProMotion-quality rendering, rather than assuming 60 FPS.

That means:

avoid unnecessary GeometryReader
don't perform network/database work on the main actor
don't recalculate expensive analytics during gestures
use Swift concurrency for node requests
keep animation state local
avoid massive view hierarchies
use Canvas for expensive custom effects
use TimelineView only where continuous animation genuinely requires it
keep transaction updates incremental

For example, your node refresh should never block the animation:

Task {

    let result =
        try await node.balance()

    await MainActor.run {

        withAnimation(
            AureomMotion.silk
        ) {

            balance =
                result
        }
    }
}









create semantic colours.

import SwiftUI

enum AureomColor {

    // MARK: Background

    static let background =
        Color(
            red: 0.035,
            green: 0.040,
            blue: 0.050
        )

    static let surface =
        Color(
            red: 0.085,
            green: 0.090,
            blue: 0.105
        )

    static let elevated =
        Color(
            red: 0.13,
            green: 0.135,
            blue: 0.15
        )

    // MARK: Primary

    static let titanium =
        Color(
            red: 0.88,
            green: 0.89,
            blue: 0.91
        )

    static let silver =
        Color(
            red: 0.68,
            green: 0.70,
            blue: 0.74
        )

    // MARK: Aureom Gold

    static let gold =
        Color(
            red: 0.92,
            green: 0.70,
            blue: 0.30
        )

    static let goldSoft =
        Color(
            red: 0.78,
            green: 0.57,
            blue: 0.24
        )

    // MARK: Network

    static let bitcoin =
        Color(
            red: 1.0,
            green: 0.62,
            blue: 0.16
        )

    static let lightning =
        Color(
            red: 0.98,
            green: 0.84,
            blue: 0.30
        )

    // MARK: Semantic

    static let positive =
        Color(
            red: 0.35,
            green: 0.86,
            blue: 0.62
        )

    static let warning =
        Color(
            red: 1.0,
            green: 0.70,
            blue: 0.25
        )

    static let negative =
        Color(
            red: 0.95,
            green: 0.35,
            blue: 0.38
        )
}

The important thing is that gold isn't used everywhere.

Gold becomes the Aureom identity, while the rest of the interface remains restrained.

2. Use gradients as light, not decoration

This is where I'd make a major change.

Don't do:

LinearGradient(
    colors: [.blue, .purple],
    startPoint: .top,
    endPoint: .bottom
)

everywhere.

Instead, make the gradient appear like light passing across a material.

struct AureomAtmosphere: View {

    var body: some View {

        ZStack {

            AureomColor.background
                .ignoresSafeArea()

            RadialGradient(
                colors: [
                    AureomColor.gold
                        .opacity(0.12),

                    Color.clear
                ],
                center: .topTrailing,
                startRadius: 10,
                endRadius: 520
            )

            RadialGradient(
                colors: [
                    AureomColor.silver
                        .opacity(0.055),

                    Color.clear
                ],
                center: .bottomLeading,
                startRadius: 10,
                endRadius: 600
            )
        }
        .ignoresSafeArea()
    }
}

So the background has atmosphere, but you don't immediately notice the gradient.

That's much more Apple-like.

3. Let each card have its own material identity

I'd introduce a card palette.

enum WalletMaterial {

    case titanium
    case midnight
    case gold
    case graphite
    case arctic
    case bitcoin
    case lightning

    var primary: Color {

        switch self {

        case .titanium:
            return Color(
                white: 0.72
            )

        case .midnight:
            return Color(
                red: 0.06,
                green: 0.08,
                blue: 0.12
            )

        case .gold:
            return AureomColor.gold

        case .graphite:
            return Color(
                red: 0.16,
                green: 0.17,
                blue: 0.18
            )

        case .arctic:
            return Color(
                red: 0.70,
                green: 0.82,
                blue: 0.90
            )

        case .bitcoin:
            return AureomColor.bitcoin

        case .lightning:
            return AureomColor.lightning
        }
    }

    var secondary: Color {

        switch self {

        case .titanium:
            return Color.white

        case .midnight:
            return Color(
                red: 0.20,
                green: 0.24,
                blue: 0.32
            )

        case .gold:
            return Color(
                red: 0.45,
                green: 0.25,
                blue: 0.06
            )

        case .graphite:
            return Color(
                red: 0.30,
                green: 0.32,
                blue: 0.34
            )

        case .arctic:
            return Color(
                red: 0.40,
                green: 0.58,
                blue: 0.70
            )

        case .bitcoin:
            return Color(
                red: 0.72,
                green: 0.30,
                blue: 0.04
            )

        case .lightning:
            return Color(
                red: 0.65,
                green: 0.48,
                blue: 0.04
            )
        }
    }
}

Then:

struct AureomCardBackground:
    View {

    let material: WalletMaterial

    var body: some View {

        RoundedRectangle(
            cornerRadius: 30,
            style: .continuous
        )

        .fill(

            LinearGradient(
                colors: [
                    material.primary,
                    material.secondary
                        .opacity(0.75),
                    material.primary
                        .opacity(0.92)
                ],

                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )

        .overlay {

            RoundedRectangle(
                cornerRadius: 30,
                style: .continuous
            )
            .stroke(
                Color.white.opacity(0.18),
                lineWidth: 0.7
            )
        }
    }
}
4. The really nice effect: colour blending

Instead of cards looking like isolated rectangles, allow their colour to bleed very subtly into the surrounding interface.

struct CardGlow: View {

    let color: Color

    var body: some View {

        RoundedRectangle(
            cornerRadius: 60
        )
        .fill(color)
        .blur(radius: 70)
        .opacity(0.12)
        .scaleEffect(0.82)
    }
}

Put this behind the card:

ZStack {

    CardGlow(
        color: material.primary
    )

    AureomCardBackground(
        material: material
    )

    CardContent()
}

Now a gold card produces a very faint warm atmosphere around itself.

A Bitcoin card produces a warm orange ambience.

A titanium card produces a cold silver ambience.

The effect should be subtle.

5. Dynamic card-to-background blending

This is where it starts getting really interesting.

When the user selects a card:

@State private var selected = false

then:

ZStack {

    AureomAtmosphere()

    CardGlow(
        color: material.primary
    )
    .opacity(
        selected ? 1.0 : 0.0
    )
    .animation(
        AureomMotion.silk,
        value: selected
    )

    WalletCard()
}

So:

UNSELECTED

████████████████████
      CARD
████████████████████


SELECTED

░░░░░░░░ GOLD ░░░░░░░
      ┌────────┐
      │  CARD  │
      └────────┘
░░░░░░░░░░░░░░░░░░░░

The interface almost breathes around the selected object.

6. Use blending modes carefully

SwiftUI gives us some excellent compositing tools.

For example:

.blendMode(.screen)

for light:

Circle()
    .fill(AureomColor.gold)
    .blur(radius: 80)
    .opacity(0.15)
    .blendMode(.screen)

And:

.compositingGroup()

when combining multiple translucent layers.

You can build an atmospheric layer:

ZStack {

    AureomColor.background

    Circle()
        .fill(AureomColor.gold)
        .frame(width: 300)
        .blur(radius: 100)
        .offset(x: 120, y: -250)
        .opacity(0.12)
        .blendMode(.screen)

    Circle()
        .fill(AureomColor.bitcoin)
        .frame(width: 240)
        .blur(radius: 110)
        .offset(x: -160, y: 250)
        .opacity(0.07)
        .blendMode(.screen)
}

This creates a deep, photographic colour field.

7. Light mode should also exist

I wouldn't make Aureom Wallet permanently black.

I'd create two colour worlds.

Dark
Near-black
   ↓
Graphite
   ↓
Titanium
   ↓
Muted gold
Light
Warm white
   ↓
Pearl
   ↓
Silver
   ↓
Champagne gold

For example:

struct AureomBackground: View {

    @Environment(
        \.colorScheme
    ) private var scheme

    var body: some View {

        Group {

            if scheme == .dark {

                Color(
                    red: 0.025,
                    green: 0.028,
                    blue: 0.035
                )

            } else {

                Color(
                    red: 0.965,
                    green: 0.958,
                    blue: 0.94
                )
            }
        }
        .ignoresSafeArea()
    }
}

The light version could feel almost like white ceramic/titanium, rather than generic banking-app white.

8. Transaction colours should be semantic, not categorical

I'd avoid making every transaction a different bright colour.

Instead:

Income
  soft green

Payment
  neutral titanium

Bitcoin
  warm amber

Lightning
  warm electric gold

Pending
  desaturated gold

Failed
  muted red

For example:

enum TransactionVisualState {

    case completed
    case pending
    case failed
    case bitcoin
    case lightning

    var accent: Color {

        switch self {

        case .completed:
            return AureomColor.positive

        case .pending:
            return AureomColor.warning

        case .failed:
            return AureomColor.negative

        case .bitcoin:
            return AureomColor.bitcoin

        case .lightning:
            return AureomColor.lightning
        }
    }
}

Then the same colour appears in the icon, tiny glow, animation and status indicator.

That's what makes the system coherent.

9. The Aureom "spectral" effect

For your particular aesthetic, I'd add one distinctive visual signature:

a very thin moving spectral highlight across important surfaces.

struct SpectralHighlight:
    View {

    @State private var phase: CGFloat = -1

    var body: some View {

        LinearGradient(
            colors: [
                Color.clear,
                Color.white.opacity(0.12),
                AureomColor.gold.opacity(0.08),
                Color.clear
            ],
            startPoint: .leading,
            endPoint: .trailing
        )

        .frame(width: 160)

        .blur(radius: 5)

        .offset(
            x: phase * 500
        )

        .onAppear {

            withAnimation(
                .linear(
                    duration: 4
                )
                .repeatForever(
                    autoreverses: false
                )
            ) {

                phase = 1
            }
        }
    }
}

Put it behind a card mask:

ZStack {

    WalletCard()

    SpectralHighlight()
        .mask(
            RoundedRectangle(
                cornerRadius: 30
            )
        )
}



Bitcoin Wallet palette
import SwiftUI

enum BitcoinWalletColor {

    // MARK: - Core

    /// Almost-black base.
    static let black =
        Color(
            red: 0.012,
            green: 0.014,
            blue: 0.018
        )

    /// Slightly raised surface.
    static let surface =
        Color(
            red: 0.035,
            green: 0.038,
            blue: 0.043
        )

    /// Card / panel surface.
    static let elevated =
        Color(
            red: 0.065,
            green: 0.068,
            blue: 0.073
        )

    // MARK: - Bitcoin Orange

    /// Primary Bitcoin orange.
    static let orange =
        Color(
            red: 1.0,
            green: 0.52,
            blue: 0.055
        )

    /// Deeper orange for shadows.
    static let orangeDeep =
        Color(
            red: 0.72,
            green: 0.25,
            blue: 0.025
        )

    /// Soft orange for atmospheric glow.
    static let orangeGlow =
        Color(
            red: 1.0,
            green: 0.42,
            blue: 0.04
        )

    // MARK: - Typography

    static let white =
        Color(
            red: 0.96,
            green: 0.96,
            blue: 0.95
        )

    static let secondary =
        Color(
            red: 0.62,
            green: 0.63,
            blue: 0.64
        )

    static let tertiary =
        Color(
            red: 0.38,
            green: 0.39,
            blue: 0.40
        )

    // MARK: - States

    static let positive =
        Color(
            red: 0.30,
            green: 0.82,
            blue: 0.48
        )

    static let warning =
        orange

    static let negative =
        Color(
            red: 0.92,
            green: 0.25,
            blue: 0.22
        )
}
The visual hierarchy
                    BITCOIN WALLET

                         ₿
                  Bitcoin Orange
                         │
             ┌───────────┴───────────┐
             │                       │
          ORANGE                   BLACK
       transactions              interface
       buttons                   background
       ₿ logo                    navigation
       highlights                typography
       network status             cards
             │                       │
             └───────────┬───────────┘
                         │
                    subtle glow

I would not make the whole app orange. The black should dominate.

Black/orange wallet background
struct BitcoinWalletBackground: View {

    var body: some View {

        ZStack {

            BitcoinWalletColor.black

            // Main orange atmosphere
            RadialGradient(
                colors: [
                    BitcoinWalletColor.orange
                        .opacity(0.13),

                    Color.clear
                ],
                center: .topTrailing,
                startRadius: 20,
                endRadius: 500
            )

            // Secondary deep orange atmosphere
            RadialGradient(
                colors: [
                    BitcoinWalletColor.orangeDeep
                        .opacity(0.10),

                    Color.clear
                ],
                center: .bottomLeading,
                startRadius: 20,
                endRadius: 600
            )
        }
        .ignoresSafeArea()
    }
}

This gives you a black environment illuminated by Bitcoin orange.

The main Bitcoin card
struct BitcoinCard: View {

    let balance: String

    var body: some View {

        ZStack {

            RoundedRectangle(
                cornerRadius: 30,
                style: .continuous
            )
            .fill(
                LinearGradient(
                    colors: [
                        BitcoinWalletColor.elevated,
                        BitcoinWalletColor.surface,
                        BitcoinWalletColor.black
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )

            // Orange light source
            Circle()
                .fill(
                    BitcoinWalletColor.orange
                        .opacity(0.20)
                )
                .frame(width: 220)
                .blur(radius: 80)
                .offset(
                    x: 130,
                    y: -90
                )

            VStack(
                alignment: .leading,
                spacing: 0
            ) {

                HStack {

                    Image(
                        systemName:
                            "bitcoinsign.circle.fill"
                    )
                    .font(.title2)

                    Text("BITCOIN")
                        .font(
                            .system(
                                size: 13,
                                weight: .semibold
                            )
                        )
                        .tracking(2)

                    Spacer()

                    Circle()
                        .fill(
                            BitcoinWalletColor.positive
                        )
                        .frame(
                            width: 7,
                            height: 7
                        )
                }
                .foregroundStyle(
                    BitcoinWalletColor.orange
                )

                Spacer()

                Text(balance)
                    .font(
                        .system(
                            size: 36,
                            weight: .medium,
                            design: .rounded
                        )
                    )
                    .foregroundStyle(
                        BitcoinWalletColor.white
                    )

                Text("BTC")
                    .font(
                        .system(
                            size: 13,
                            weight: .medium
                        )
                    )
                    .tracking(2)
                    .foregroundStyle(
                        BitcoinWalletColor.secondary
                    )
            }
            .padding(26)
        }

        .frame(height: 210)

        .overlay {

            RoundedRectangle(
                cornerRadius: 30,
                style: .continuous
            )
            .stroke(
                BitcoinWalletColor.orange
                    .opacity(0.20),
                lineWidth: 0.8
            )
        }

        .shadow(
            color: BitcoinWalletColor.orange
                .opacity(0.08),
            radius: 30,
            y: 12
        )
    }
}
Orange action buttons

I'd use orange sparingly for actions that actually move Bitcoin:

struct BitcoinActionButton: View {

    let title: String
    let icon: String

    var body: some View {

        Label(
            title,
            systemImage: icon
        )
        .font(
            .system(
                size: 15,
                weight: .semibold
            )
        )
        .foregroundStyle(
            BitcoinWalletColor.black
        )
        .frame(
            maxWidth: .infinity
        )
        .frame(height: 54)
        .background(
            BitcoinWalletColor.orange,
            in: RoundedRectangle(
                cornerRadius: 18,
                style: .continuous
            )
        )
    }
}

So:

HStack(spacing: 12) {

    BitcoinActionButton(
        title: "Send",
        icon: "arrow.up"
    )

    BitcoinActionButton(
        title: "Receive",
        icon: "arrow.down"
    )
}
The really nice part: orange light

For the 2030 iOS look, I'd add an extremely subtle orange bloom behind important Bitcoin objects:

struct BitcoinGlow: View {

    var body: some View {

        Circle()
            .fill(
                BitcoinWalletColor.orange
                    .opacity(0.16)
            )
            .frame(
                width: 180,
                height: 180
            )
            .blur(radius: 70)
            .blendMode(.screen)
    }
}

Then:

ZStack {

    BitcoinWalletBackground()

    BitcoinGlow()

    BitcoinCard(
        balance: "0.24839172"
    )
}

The result is essentially:

black interface → dark graphite material → orange Bitcoin light → white typography.

That's a much stronger visual identity than orange buttons on a black banking interface.

I would make the final Aureom Bitcoin design language:

Black

#030405 — background
#090A0B — surfaces
#111214 — elevated cards

Bitcoin Orange

#FF850D — primary
#B83F06 — deep orange
#FF6B08 — glow

Typography

#F5F5F2 — primary
#9E9FA1 — secondary
#616265 — tertiary

And importantly, orange becomes dynamic: it glows when the wallet is active, pulses during Lightning activity, illuminates the transaction confirmation, and becomes almost invisible when the app is idle. That would make the Bitcoin wallet feel much more like a polished native Apple system experience than a conventional crypto app.







Aureom Spectral palette
import SwiftUI

enum AureomSpectral {

    // MARK: - Base

    static let void =
        Color(
            red: 0.012,
            green: 0.014,
            blue: 0.018
        )

    static let graphite =
        Color(
            red: 0.055,
            green: 0.060,
            blue: 0.068
        )

    static let titanium =
        Color(
            red: 0.78,
            green: 0.79,
            blue: 0.80
        )

    // MARK: - Aureom Gold

    static let gold =
        Color(
            red: 0.96,
            green: 0.70,
            blue: 0.27
        )

    static let champagne =
        Color(
            red: 1.00,
            green: 0.83,
            blue: 0.52
        )

    static let amber =
        Color(
            red: 0.88,
            green: 0.45,
            blue: 0.08
        )

    // MARK: - Spectral tones

    static let cyan =
        Color(
            red: 0.25,
            green: 0.72,
            blue: 0.82
        )

    static let violet =
        Color(
            red: 0.48,
            green: 0.34,
            blue: 0.78
        )

    static let rose =
        Color(
            red: 0.82,
            green: 0.38,
            blue: 0.47
        )

    // MARK: - Text

    static let white =
        Color(
            red: 0.96,
            green: 0.96,
            blue: 0.95
        )

    static let muted =
        Color(
            red: 0.56,
            green: 0.57,
            blue: 0.59
        )
}

The spectral colours should be supporting colours, not competing with Aureom gold.

The Aureom shimmer

This is the main effect I'd use.

struct AureomShimmer: View {

    @State private var phase: CGFloat = -1.2

    var body: some View {

        LinearGradient(
            stops: [

                .init(
                    color: .clear,
                    location: 0.00
                ),

                .init(
                    color: AureomSpectral.cyan
                        .opacity(0.08),
                    location: 0.35
                ),

                .init(
                    color: AureomSpectral.champagne
                        .opacity(0.30),
                    location: 0.47
                ),

                .init(
                    color: .white
                        .opacity(0.18),
                    location: 0.51
                ),

                .init(
                    color: AureomSpectral.violet
                        .opacity(0.08),
                    location: 0.65
                ),

                .init(
                    color: .clear,
                    location: 1.00
                )
            ],
            startPoint: .leading,
            endPoint: .trailing
        )
        .frame(width: 280)
        .blur(radius: 8)
        .offset(x: phase * 700)
        .blendMode(.screen)
        .onAppear {

            withAnimation(
                .linear(duration: 5.5)
                .repeatForever(
                    autoreverses: false
                )
            ) {
                phase = 1.2
            }
        }
    }
}

Then put it inside the card:

struct AureomWalletCard: View {

    var body: some View {

        ZStack {

            RoundedRectangle(
                cornerRadius: 30,
                style: .continuous
            )
            .fill(
                LinearGradient(
                    colors: [
                        AureomSpectral.graphite,
                        AureomSpectral.void,
                        AureomSpectral.graphite
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )

            AureomShimmer()
                .mask(
                    RoundedRectangle(
                        cornerRadius: 30,
                        style: .continuous
                    )
                )

            VStack(
                alignment: .leading
            ) {

                HStack {

                    Text("AUREOM")
                        .font(
                            .system(
                                size: 12,
                                weight: .bold
                            )
                        )
                        .tracking(3)

                    Spacer()

                    Image(
                        systemName:
                            "sparkles"
                    )
                    .foregroundStyle(
                        AureomSpectral.gold
                    )
                }

                Spacer()

                Text("£12,450.72")
                    .font(
                        .system(
                            size: 36,
                            weight: .medium,
                            design: .rounded
                        )
                    )

                Text("AUREOM WALLET")
                    .font(.caption2)
                    .tracking(2)
                    .foregroundStyle(
                        AureomSpectral.muted
                    )
            }
            .foregroundStyle(
                AureomSpectral.white
            )
            .padding(26)
        }
    }
}
Make the whole wallet shimmer

I wouldn't restrict it to cards.

Use a very low-frequency ambient shimmer behind the entire interface.

struct AureomAtmosphericLight:
    View {

    @State private var rotation = 0.0

    var body: some View {

        ZStack {

            AureomSpectral.void

            AngularGradient(
                gradient: Gradient(
                    colors: [
                        AureomSpectral.gold
                            .opacity(0.07),

                        AureomSpectral.cyan
                            .opacity(0.025),

                        AureomSpectral.violet
                            .opacity(0.035),

                        AureomSpectral.gold
                            .opacity(0.07)
                    ]
                ),
                center: .center,
                angle: .degrees(rotation)
            )
            .blur(radius: 90)
            .ignoresSafeArea()
        }
        .onAppear {

            withAnimation(
                .linear(duration: 24)
                .repeatForever(
                    autoreverses: false
                )
            ) {
                rotation = 360
            }
        }
    }
}

This means the colour field is very slowly moving even when the user isn't interacting.

The movement should be almost subconscious.

Shimmer on interaction

This is even better.

When the user touches a card, make the shimmer accelerate.

struct InteractiveAureomCard:
    View {

    @State private var active = false

    var body: some View {

        AureomWalletCard()

            .scaleEffect(
                active ? 0.985 : 1.0
            )

            .shadow(
                color:
                    AureomSpectral.gold
                        .opacity(
                            active ? 0.16 : 0.05
                        ),
                radius:
                    active ? 35 : 18
            )

            .animation(
                AureomMotion.silk,
                value: active
            )

            .onLongPressGesture(
                minimumDuration: 0.01,
                maximumDistance: 30,
                pressing: { pressing in
                    active = pressing
                },
                perform: {}
            )
    }
}



