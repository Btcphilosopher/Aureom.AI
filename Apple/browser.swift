Absolutely. If you mean building a Safari-like iPhone browser in pure Swift, I’d make the UI substantially more ambitious than a basic WKWebView: a full-screen browser with a floating address/search surface, fluid tab management, gesture-driven navigation, spatial zoom transitions, animated page loading, glass controls, and an adaptive toolbar.

One important distinction: a third-party iOS app cannot modify Apple's Safari itself. But you can build a high-end Safari-style browser using Apple's WebKit framework.

For an Aureom-style browser, I’d structure it like this:

Aureom Browser
│
├── BrowserShell
│   ├── SpatialBackground
│   ├── WebView
│   ├── FloatingAddressBar
│   ├── BottomToolbar
│   └── GestureLayer
│
├── BrowserEngine
│   ├── WKWebView
│   ├── NavigationController
│   ├── SearchController
│   └── PageState
│
├── TabSystem
│   ├── TabStore
│   ├── TabCard
│   └── TabOverview
│
└── MotionSystem
    ├── SpatialParallax
    ├── HeroZoom
    ├── GlassMaterial
    └── PageTransition
Core browser
import SwiftUI
import WebKit

// MARK: - Browser Model

@MainActor
final class BrowserModel: ObservableObject {

    @Published var urlText: String = ""
    @Published var pageTitle: String = "New Tab"

    @Published var canGoBack = false
    @Published var canGoForward = false
    @Published var isLoading = false

    let webView: WKWebView

    init() {

        let configuration = WKWebViewConfiguration()

        configuration.allowsInlineMediaPlayback = true

        configuration.defaultWebpagePreferences
            .preferredContentMode = .mobile

        webView = WKWebView(
            frame: .zero,
            configuration: configuration
        )

        webView.allowsBackForwardNavigationGestures = true
    }

    func load(_ input: String) {

        let trimmed =
            input.trimmingCharacters(
                in: .whitespacesAndNewlines
            )

        guard !trimmed.isEmpty else {
            return
        }

        let destination: URL?

        if trimmed.contains("://") {

            destination = URL(
                string: trimmed
            )

        } else if trimmed.contains(".") {

            destination = URL(
                string: "https://" + trimmed
            )

        } else {

            let encoded =
                trimmed.addingPercentEncoding(
                    withAllowedCharacters:
                        .urlQueryAllowed
                ) ?? trimmed

            destination = URL(
                string:
                    "https://www.google.com/search?q="
                    + encoded
            )
        }

        guard let destination else {
            return
        }

        webView.load(
            URLRequest(
                url: destination,
                cachePolicy: .useProtocolCachePolicy,
                timeoutInterval: 30
            )
        )
    }

    func back() {

        guard webView.canGoBack else {
            return
        }

        webView.goBack()
    }

    func forward() {

        guard webView.canGoForward else {
            return
        }

        webView.goForward()
    }

    func reload() {
        webView.reload()
    }
}
SwiftUI WebKit bridge
struct BrowserWebView: UIViewRepresentable {

    @ObservedObject
    var browser: BrowserModel

    func makeCoordinator()
        -> Coordinator {

        Coordinator(browser: browser)
    }

    func makeUIView(
        context: Context
    ) -> WKWebView {

        browser.webView.navigationDelegate =
            context.coordinator

        browser.webView.uiDelegate =
            context.coordinator

        return browser.webView
    }

    func updateUIView(
        _ uiView: WKWebView,
        context: Context
    ) {}
}


// MARK: - Coordinator

final class Coordinator:
    NSObject,
    WKNavigationDelegate,
    WKUIDelegate {

    let browser: BrowserModel

    init(browser: BrowserModel) {
        self.browser = browser
    }

    func webView(
        _ webView: WKWebView,
        didStartProvisionalNavigation
        navigation: WKNavigation?
    ) {

        browser.isLoading = true
    }

    func webView(
        _ webView: WKWebView,
        didFinish navigation: WKNavigation?
    ) {

        browser.isLoading = false

        browser.urlText =
            webView.url?.absoluteString ?? ""

        browser.pageTitle =
            webView.title ?? "Untitled"

        browser.canGoBack =
            webView.canGoBack

        browser.canGoForward =
            webView.canGoForward
    }

    func webView(
        _ webView: WKWebView,
        didFail navigation: WKNavigation?,
        withError error: Error
    ) {

        browser.isLoading = false
    }
}
The high-grade UI

Instead of putting a traditional Safari toolbar permanently at the bottom, I'd make it float over the webpage.

struct BrowserScreen: View {

    @StateObject
    private var browser = BrowserModel()

    @FocusState
    private var searchFocused: Bool

    @State
    private var searchScale: CGFloat = 1

    var body: some View {

        ZStack {

            // Web content
            BrowserWebView(
                browser: browser
            )
            .ignoresSafeArea()

            // Ambient UI atmosphere
            VStack {

                LinearGradient(
                    colors: [
                        .black.opacity(0.35),
                        .clear
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 120)

                Spacer()
            }
            .ignoresSafeArea()

            // Floating browser controls
            VStack {

                AddressBar(
                    browser: browser,
                    focused: $searchFocused
                )
                .scaleEffect(searchScale)

                Spacer()

                BrowserToolbar(
                    browser: browser
                )
            }
            .padding(.horizontal, 14)
            .padding(.top, 8)
            .padding(.bottom, 8)
        }
        .preferredColorScheme(.dark)
    }
}
Floating address bar
struct AddressBar: View {

    @ObservedObject
    var browser: BrowserModel

    @FocusState
    var focused: Bool

    var body: some View {

        HStack(spacing: 12) {

            Image(
                systemName:
                    browser.isLoading
                    ? "progress.indicator"
                    : "lock.fill"
            )
            .font(.system(size: 13, weight: .semibold))

            TextField(
                "Search or enter website",
                text: $browser.urlText
            )
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .focused($focused)
            .submitLabel(.go)
            .onSubmit {

                browser.load(
                    browser.urlText
                )

                focused = false
            }

            if focused {

                Button {

                    browser.urlText = ""

                } label: {

                    Image(
                        systemName:
                            "xmark.circle.fill"
                    )
                }
                .transition(
                    .scale.combined(
                        with: .opacity
                    )
                )
            }

            Button {

                browser.reload()

            } label: {

                Image(
                    systemName:
                        "arrow.clockwise"
                )
            }
        }
        .font(
            .system(
                size: 16,
                weight: .medium,
                design: .rounded
            )
        )
        .foregroundStyle(.primary)
        .padding(.horizontal, 16)
        .frame(height: 50)
        .background {

            Capsule()
                .fill(.ultraThinMaterial)

                .overlay {

                    Capsule()
                        .stroke(
                            .white.opacity(0.16),
                            lineWidth: 0.7
                        )
                }

                .shadow(
                    color: .black.opacity(0.25),
                    radius: 20,
                    y: 8
                )
        }
        .animation(
            .spring(
                response: 0.35,
                dampingFraction: 0.84
            ),
            value: focused
        )
    }
}
Bottom toolbar
struct BrowserToolbar: View {

    @ObservedObject
    var browser: BrowserModel

    var body: some View {

        HStack {

            BrowserButton(
                systemName: "chevron.left",
                enabled: browser.canGoBack
            ) {
                browser.back()
            }

            BrowserButton(
                systemName: "chevron.right",
                enabled: browser.canGoForward
            ) {
                browser.forward()
            }

            Spacer()

            BrowserButton(
                systemName: "square.and.arrow.up"
            ) {
                share()
            }

            BrowserButton(
                systemName: "square.on.square"
            ) {
                // Open tabs
            }

            BrowserButton(
                systemName: "plus"
            ) {
                // New tab
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background {

            Capsule()
                .fill(.ultraThinMaterial)
                .overlay {

                    Capsule()
                        .stroke(
                            .white.opacity(0.12),
                            lineWidth: 0.7
                        )
                }
                .shadow(
                    color: .black.opacity(0.3),
                    radius: 25,
                    y: 12
                )
        }
    }

    private func share() {

        guard let url = browser.webView.url
        else { return }

        let controller =
            UIActivityViewController(
                activityItems: [url],
                applicationActivities: nil
            )

        UIApplication.shared
            .connectedScenes
            .compactMap {
                $0 as? UIWindowScene
            }
            .flatMap {
                $0.windows
            }
            .first?
            .rootViewController?
            .present(
                controller,
                animated: true
            )
    }
}
struct BrowserButton: View {

    let systemName: String
    var enabled: Bool = true
    let action: () -> Void

    @State
    private var pressed = false

    var body: some View {

        Button {

            action()

        } label: {

            Image(systemName: systemName)
                .font(
                    .system(
                        size: 17,
                        weight: .semibold
                    )
                )
                .frame(
                    width: 38,
                    height: 38
                )
                .background {

                    Circle()
                        .fill(
                            .white.opacity(
                                pressed
                                ? 0.13
                                : 0.055
                            )
                        )
                }
                .scaleEffect(
                    pressed ? 0.88 : 1
                )
        }
        .buttonStyle(.plain)
        .foregroundStyle(
            enabled
            ? .primary
            : .secondary.opacity(0.35)
        )
        .disabled(!enabled)
    }
}
Then take it considerably further

The genuinely interesting part would be turning this into a next-generation browser UI, rather than simply copying Safari.

I'd add:

Spatial tab system

Instead of a flat list:

                 ┌───────────────┐
                 │     TAB 1     │
                 │               │
          ┌──────┴───────────────┴──────┐
          │            TAB 2            │
          │                             │
          └─────────────────────────────┘

Cards would zoom outward from the current webpage, with the page itself shrinking into a physical tab.

Gesture-driven navigation
DragGesture(minimumDistance: 8)
    .onChanged { value in

        let x = value.translation.width

        navigationProgress =
            min(
                1,
                abs(x) / 180
            )
    }
    .onEnded { value in

        if value.translation.width > 120 {
            browser.back()
        }

        if value.translation.width < -120 {
            browser.forward()
        }

        withAnimation(.spring(
            response: 0.38,
            dampingFraction: 0.82
        )) {
            navigationProgress = 0
        }
    }
    
