2. App entry point
import SwiftUI

@main
struct AureomWalletApp: App {

    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
        }
    }
}
3. App state
import Foundation
import SwiftUI

@MainActor
final class AppState: ObservableObject {

    @Published var isLocked = true
    @Published var isLoading = false
    @Published var errorMessage: String?

    let bitcoinService: BitcoinService

    init() {
        self.bitcoinService = BitcoinService(
            nodeClient: BitcoinNodeClient(
                apiClient: APIClient(
                    baseURL: URL(
                        string: "https://api.aureom.ai"
                    )!
                )
            )
        )
    }

    func unlock() async {
        do {
            try await BiometricAuthenticator.shared.authenticate(
                reason: "Unlock your Aureom Wallet"
            )

            withAnimation(.easeOut(duration: 0.35)) {
                isLocked = false
            }

        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func lock() {
        withAnimation(.easeOut(duration: 0.25)) {
            isLocked = true
        }
    }
}
4. Root view
import SwiftUI

struct RootView: View {

    @EnvironmentObject private var appState: AppState

    var body: some View {

        Group {
            if appState.isLocked {
                LockedWalletView()
            } else {
                MainWalletView()
            }
        }
        .preferredColorScheme(.dark)
        .alert(
            "Aureom Wallet",
            isPresented: Binding(
                get: {
                    appState.errorMessage != nil
                },
                set: { value in
                    if !value {
                        appState.errorMessage = nil
                    }
                }
            )
        ) {
            Button("OK") {
                appState.errorMessage = nil
            }
        } message: {
            Text(appState.errorMessage ?? "")
        }
    }
}
5. Locked wallet
import SwiftUI

struct LockedWalletView: View {

    @EnvironmentObject private var appState: AppState

    @State private var pulse = false

    var body: some View {

        ZStack {

            AureomBackground()

            VStack(spacing: 30) {

                Spacer()

                ZStack {

                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [
                                    AureomColor.gold.opacity(0.35),
                                    .clear
                                ],
                                center: .center,
                                startRadius: 10,
                                endRadius: 130
                            )
                        )
                        .frame(width: 260, height: 260)
                        .scaleEffect(pulse ? 1.1 : 0.92)
                        .opacity(pulse ? 0.55 : 0.85)

                    Image(systemName: "lock.fill")
                        .font(.system(size: 42, weight: .medium))
                        .foregroundStyle(
                            AureomColor.champagne
                        )
                }

                VStack(spacing: 8) {

                    Text("AUREOM")
                        .font(
                            .system(
                                size: 13,
                                weight: .semibold,
                                design: .rounded
                            )
                        )
                        .tracking(5)

                    Text("Wallet Locked")
                        .font(
                            .system(
                                size: 30,
                                weight: .medium,
                                design: .rounded
                            )
                        )
                }

                Text("Authenticate to continue")
                    .foregroundStyle(.secondary)

                Spacer()

                Button {

                    Task {
                        await appState.unlock()
                    }

                } label: {

                    HStack {
                        Image(systemName: "faceid")
                        Text("Unlock")
                    }
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                }
                .buttonStyle(AureomPrimaryButton())

                Spacer()
                    .frame(height: 30)
            }
            .padding(24)
        }
        .onAppear {

            withAnimation(
                .easeInOut(duration: 2)
                .repeatForever(autoreverses: true)
            ) {
                pulse = true
            }
        }
    }
}
6. Main navigation

Apple's current SwiftUI navigation system supports NavigationStack and TabView, which is exactly what we want here.

import SwiftUI

struct MainWalletView: View {

    @State private var selectedTab = 0

    var body: some View {

        TabView(selection: $selectedTab) {

            NavigationStack {
                WalletHomeView()
            }
            .tabItem {
                Label("Wallet", systemImage: "wallet.pass")
            }
            .tag(0)

            NavigationStack {
                BitcoinWalletView()
            }
            .tabItem {
                Label("Bitcoin", systemImage: "bitcoinsign.circle")
            }
            .tag(1)

            NavigationStack {
                TransactionListView()
            }
            .tabItem {
                Label("Activity", systemImage: "chart.xyaxis.line")
            }
            .tag(2)

            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label("More", systemImage: "ellipsis")
            }
            .tag(3)
        }
        .tint(AureomColor.gold)
    }
}
7. Aureom colours
import SwiftUI

enum AureomColor {

    static let void =
        Color(red: 0.015, green: 0.017, blue: 0.020)

    static let graphite =
        Color(red: 0.045, green: 0.050, blue: 0.060)

    static let titanium =
        Color(red: 0.16, green: 0.17, blue: 0.19)

    static let silver =
        Color(red: 0.72, green: 0.74, blue: 0.77)

    static let white =
        Color.white

    static let gold =
        Color(
            red: 0.86,
            green: 0.67,
            blue: 0.30
        )

    static let champagne =
        Color(
            red: 0.96,
            green: 0.86,
            blue: 0.65
        )

    static let amber =
        Color(
            red: 1.0,
            green: 0.53,
            blue: 0.10
        )

    static let bitcoinOrange =
        Color(
            red: 1.0,
            green: 0.52,
            blue: 0.08
        )

    static let green =
        Color(
            red: 0.30,
            green: 0.85,
            blue: 0.55
        )

    static let red =
        Color(
            red: 0.95,
            green: 0.28,
            blue: 0.30
        )

    static let blue =
        Color(
            red: 0.28,
            green: 0.55,
            blue: 1.0
        )
}
8. Aureom background
import SwiftUI

struct AureomBackground: View {

    var body: some View {

        ZStack {

            AureomColor.void
                .ignoresSafeArea()

            RadialGradient(
                colors: [
                    AureomColor.gold.opacity(0.10),
                    .clear
                ],
                center: .topTrailing,
                startRadius: 0,
                endRadius: 420
            )
            .ignoresSafeArea()

            RadialGradient(
                colors: [
                    AureomColor.bitcoinOrange.opacity(0.045),
                    .clear
                ],
                center: .bottomLeading,
                startRadius: 0,
                endRadius: 500
            )
            .ignoresSafeArea()
        }
    }
}
9. Bitcoin models

Use integer satoshis internally.

import Foundation

enum BitcoinNetwork: String, Codable, Sendable {

    case mainnet
    case testnet
    case regtest
}

struct BitcoinBalance: Codable, Sendable {

    let confirmedSats: Int64
    let unconfirmedSats: Int64

    var totalSats: Int64 {
        confirmedSats + unconfirmedSats
    }

    var btc: Decimal {
        Decimal(totalSats) / Decimal(100_000_000)
    }
}

struct BitcoinAddressResponse: Codable, Sendable {

    let address: String
    let network: BitcoinNetwork
}

struct BitcoinFeeEstimate: Codable, Sendable {

    let satPerVByte: Int64
}

struct BitcoinTransaction: Identifiable, Codable, Sendable {

    let id: String
    let txid: String
    let amountSats: Int64
    let feeSats: Int64
    let confirmations: Int
    let timestamp: Date
    let address: String
    let direction: BitcoinDirection
    let status: BitcoinTransactionStatus
}

enum BitcoinDirection: String, Codable, Sendable {

    case incoming
    case outgoing
}

enum BitcoinTransactionStatus: String, Codable, Sendable {

    case pending
    case confirmed
    case failed
}
10. Bitcoin formatting
import Foundation

enum BitcoinFormatter {

    static func btc(
        sats: Int64,
        maximumFractionDigits: Int = 8
    ) -> String {

        let value =
            Decimal(sats) / Decimal(100_000_000)

        let formatter = NumberFormatter()

        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = 2
        formatter.maximumFractionDigits =
            maximumFractionDigits

        return formatter.string(
            from: value as NSDecimalNumber
        ) ?? "0.00"
    }

    static func sats(_ sats: Int64) -> String {

        let formatter = NumberFormatter()

        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0

        return formatter.string(
            from: NSNumber(value: sats)
        ) ?? "0"
    }
}
11. API errors
import Foundation

enum APIError: LocalizedError {

    case invalidURL
    case invalidResponse
    case http(Int)
    case decoding
    case encoding
    case server(String)

    var errorDescription: String? {

        switch self {

        case .invalidURL:
            return "Invalid Aureom API URL."

        case .invalidResponse:
            return "The server returned an invalid response."

        case .http(let status):
            return "Aureom API returned HTTP \(status)."

        case .decoding:
            return "Unable to decode the server response."

        case .encoding:
            return "Unable to encode the request."

        case .server(let message):
            return message
        }
    }
}
12. API client

URLSession is Apple's native mechanism for URL-based network requests.

import Foundation

actor APIClient {

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL) {

        self.baseURL = baseURL

        let configuration =
            URLSessionConfiguration.default

        configuration.timeoutIntervalForRequest = 20
        configuration.timeoutIntervalForResource = 60

        self.session =
            URLSession(configuration: configuration)
    }

    func request<T: Decodable>(
        path: String,
        method: String = "GET",
        body: Data? = nil
    ) async throws -> T {

        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)

        request.httpMethod = method
        request.httpBody = body

        request.setValue(
            "application/json",
            forHTTPHeaderField: "Accept"
        )

        if body != nil {

            request.setValue(
                "application/json",
                forHTTPHeaderField:
                    "Content-Type"
            )
        }

        let token =
            try? KeychainStore.shared.read(
                key: "aureom.api.token"
            )

        if let token {

            request.setValue(
                "Bearer \(token)",
                forHTTPHeaderField: "Authorization"
            )
        }

        let (data, response) =
            try await session.data(for: request)

        guard let http =
                response as? HTTPURLResponse
        else {
            throw APIError.invalidResponse
        }

        guard
            200..<300 ~= http.statusCode
        else {

            if let server =
                try? JSONDecoder().decode(
                    ServerError.self,
                    from: data
                ) {

                throw APIError.server(
                    server.message
                )
            }

            throw APIError.http(
                http.statusCode
            )
        }

        do {

            return try JSONDecoder.aureom.decode(
                T.self,
                from: data
            )

        } catch {

            throw APIError.decoding
        }
    }

    func encode<T: Encodable>(
        _ value: T
    ) throws -> Data {

        do {

            return try JSONEncoder.aureom.encode(
                value
            )

        } catch {

            throw APIError.encoding
        }
    }
}

struct ServerError: Codable {

    let message: String
}

extension JSONDecoder {

    static var aureom: JSONDecoder {

        let decoder = JSONDecoder()

        decoder.dateDecodingStrategy = .iso8601

        return decoder
    }
}

extension JSONEncoder {

    static var aureom: JSONEncoder {

        let encoder = JSONEncoder()

        encoder.dateEncodingStrategy = .iso8601

        return encoder
    }
}
13. Bitcoin node client
import Foundation

actor BitcoinNodeClient {

    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    func health() async throws -> NodeHealth {

        try await api.request(
            path: "v1/bitcoin/health"
        )
    }

    func balance() async throws -> BitcoinBalance {

        try await api.request(
            path: "v1/bitcoin/balance"
        )
    }

    func address() async throws
        -> BitcoinAddressResponse {

        try await api.request(
            path: "v1/bitcoin/address"
        )
    }

    func fee() async throws
        -> BitcoinFeeEstimate {

        try await api.request(
            path: "v1/bitcoin/fee"
        )
    }

    func transactions() async throws
        -> [BitcoinTransaction] {

        try await api.request(
            path: "v1/bitcoin/transactions"
        )
    }

    func prepare(
        request: BitcoinPaymentRequest
    ) async throws -> BitcoinPaymentPreview {

        let body = try await api.encode(request)

        return try await api.request(
            path: "v1/bitcoin/payment/prepare",
            method: "POST",
            body: body
        )
    }

    func broadcast(
        request: BitcoinBroadcastRequest
    ) async throws -> BitcoinBroadcastResponse {

        let body = try await api.encode(request)

        return try await api.request(
            path: "v1/bitcoin/payment/broadcast",
            method: "POST",
            body: body
        )
    }
}

struct NodeHealth: Codable, Sendable {

    let network: BitcoinNetwork
    let blockHeight: Int
    let synced: Bool
}
14. Payment API models
import Foundation

struct BitcoinPaymentRequest:
    Codable,
    Sendable {

    let address: String
    let amountSats: Int64
    let feeRateSatsPerVByte: Int64?
}

struct BitcoinPaymentPreview:
    Codable,
    Sendable {

    let paymentID: String
    let address: String
    let amountSats: Int64
    let feeSats: Int64
    let totalSats: Int64
    let feeRateSatsPerVByte: Int64

    let psbt: String
}

struct BitcoinBroadcastRequest:
    Codable,
    Sendable {

    let paymentID: String
    let signedPSBT: String
}

struct BitcoinBroadcastResponse:
    Codable,
    Sendable {

    let txid: String
}
15. Bitcoin service
import Foundation
import SwiftUI

@MainActor
final class BitcoinService:
    ObservableObject {

    @Published private(set) var balance:
        BitcoinBalance?

    @Published private(set) var transactions:
        [BitcoinTransaction] = []

    @Published private(set) var fee:
        BitcoinFeeEstimate?

    @Published private(set) var isLoading = false

    @Published var errorMessage:
        String?

    private let nodeClient:
        BitcoinNodeClient

    init(nodeClient: BitcoinNodeClient) {
        self.nodeClient = nodeClient
    }

    func refresh() async {

        isLoading = true
        defer {
            isLoading = false
        }

        do {

            async let newBalance =
                nodeClient.balance()

            async let newTransactions =
                nodeClient.transactions()

            async let newFee =
                nodeClient.fee()

            balance = try await newBalance
            transactions = try await newTransactions
            fee = try await newFee

        } catch {

            errorMessage =
                error.localizedDescription
        }
    }

    func preparePayment(
        address: String,
        amountSats: Int64
    ) async throws
        -> BitcoinPaymentPreview {

        let request =
            BitcoinPaymentRequest(
                address: address,
                amountSats: amountSats,
                feeRateSatsPerVByte:
                    fee?.satPerVByte
            )

        return try await nodeClient.prepare(
            request: request
        )
    }

    func broadcast(
        paymentID: String,
        signedPSBT: String
    ) async throws
        -> BitcoinBroadcastResponse {

        let request =
            BitcoinBroadcastRequest(
                paymentID: paymentID,
                signedPSBT: signedPSBT
            )

        return try await nodeClient.broadcast(
            request: request
        )
    }
}
16. Bitcoin wallet screen
import SwiftUI

struct BitcoinWalletView: View {

    @EnvironmentObject
    private var appState: AppState

    var body: some View {

        ZStack {

            AureomBackground()

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 24
                ) {

                    header

                    balanceCard

                    actions

                    recentTransactions
                }
                .padding()
            }
        }
        .navigationTitle("Bitcoin")
        .navigationBarTitleDisplayMode(.inline)
        .task {

            await appState.bitcoinService.refresh()
        }
    }

    private var header: some View {

        HStack {

            VStack(
                alignment: .leading,
                spacing: 5
            ) {

                Text("BITCOIN")
                    .font(
                        .system(
                            size: 12,
                            weight: .bold,
                            design: .rounded
                        )
                    )
                    .tracking(3)
                    .foregroundStyle(
                        AureomColor.bitcoinOrange
                    )

                Text("Sovereign money")
                    .font(.title2.weight(.medium))
            }

            Spacer()

            Image(systemName:
                "bitcoinsign.circle.fill"
            )
            .font(.system(size: 34))
            .foregroundStyle(
                AureomColor.bitcoinOrange
            )
        }
    }

    private var balanceCard: some View {

        BitcoinBalanceCard(
            balance:
                appState.bitcoinService.balance
        )
    }

    private var actions: some View {

        HStack(spacing: 12) {

            NavigationLink {
                BitcoinSendView()
            } label: {

                ActionTile(
                    title: "Send",
                    icon: "arrow.up.right",
                    colour:
                        AureomColor.bitcoinOrange
                )
            }

            NavigationLink {
                BitcoinReceiveView()
            } label: {

                ActionTile(
                    title: "Receive",
                    icon: "arrow.down.left",
                    colour:
                        AureomColor.green
                )
            }
        }
    }

    private var recentTransactions: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("Recent activity")
                .font(.headline)

            ForEach(
                appState.bitcoinService
                    .transactions
                    .prefix(5)
            ) { transaction in

                BitcoinTransactionRow(
                    transaction: transaction
                )
            }
        }
    }
}
17. Bitcoin balance card
import SwiftUI

struct BitcoinBalanceCard: View {

    let balance: BitcoinBalance?

    var body: some View {

        ZStack(alignment: .bottomTrailing) {

            RoundedRectangle(
                cornerRadius: 32,
                style: .continuous
            )
            .fill(
                LinearGradient(
                    colors: [
                        Color.black,
                        AureomColor.graphite,
                        Color.black
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )

            Circle()
                .fill(
                    AureomColor.bitcoinOrange
                        .opacity(0.20)
                )
                .frame(width: 220)
                .blur(radius: 30)
                .offset(
                    x: 80,
                    y: 70
                )

            VStack(
                alignment: .leading,
                spacing: 18
            ) {

                HStack {

                    Text("TOTAL BALANCE")
                        .font(
                            .caption.weight(.semibold)
                        )
                        .tracking(2)
                        .foregroundStyle(.secondary)

                    Spacer()

                    Image(
                        systemName:
                            "bitcoinsign.circle.fill"
                    )
                    .foregroundStyle(
                        AureomColor.bitcoinOrange
                    )
                }

                if let balance {

                    Text(
                        BitcoinFormatter.btc(
                            sats:
                                balance.totalSats
                        )
                    )
                    .font(
                        .system(
                            size: 42,
                            weight: .medium,
                            design: .rounded
                        )
                    )
                    .contentTransition(
                        .numericText()
                    )

                    Text("BTC")
                        .font(.headline)
                        .foregroundStyle(
                            AureomColor.bitcoinOrange
                        )

                    Text(
                        "\(BitcoinFormatter.sats(balance.totalSats)) sats"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)

                } else {

                    ProgressView()
                }
            }
            .frame(
                maxWidth: .infinity,
                alignment: .leading
            )
            .padding(26)
        }
        .frame(height: 220)
        .clipShape(
            RoundedRectangle(
                cornerRadius: 32,
                style: .continuous
            )
        )
        .overlay {

            RoundedRectangle(
                cornerRadius: 32,
                style: .continuous
            )
            .stroke(
                AureomColor.bitcoinOrange
                    .opacity(0.25),
                lineWidth: 1
            )
        }
    }
}
18. Action tile
import SwiftUI

struct ActionTile: View {

    let title: String
    let icon: String
    let colour: Color

    var body: some View {

        VStack(spacing: 10) {

            Image(systemName: icon)
                .font(.title3.weight(.semibold))

            Text(title)
                .font(.subheadline.weight(.semibold))
        }
        .foregroundStyle(.white)
        .frame(maxWidth: .infinity)
        .frame(height: 90)
        .background(
            RoundedRectangle(
                cornerRadius: 22,
                style: .continuous
            )
            .fill(AureomColor.graphite)
        )
        .overlay {

            RoundedRectangle(
                cornerRadius: 22,
                style: .continuous
            )
            .stroke(
                colour.opacity(0.35),
                lineWidth: 1
            )
        }
    }
}
19. Send Bitcoin
import SwiftUI

struct BitcoinSendView: View {

    @EnvironmentObject
    private var appState: AppState

    @State private var address = ""
    @State private var amount = ""

    @State private var preview:
        BitcoinPaymentPreview?

    @State private var isPreparing = false
    @State private var error: String?

    var body: some View {

        ZStack {

            AureomBackground()

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 24
                ) {

                    Text("SEND BITCOIN")
                        .font(
                            .system(
                                size: 13,
                                weight: .bold,
                                design: .rounded
                            )
                        )
                        .tracking(3)
                        .foregroundStyle(
                            AureomColor.bitcoinOrange
                        )

                    addressField

                    amountField

                    feeInformation

                    Spacer(minLength: 20)

                    reviewButton
                }
                .padding()
            }
        }
        .navigationTitle("Send")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(
            item: $preview
        ) { preview in

            BitcoinReviewView(
                preview: preview
            )
        }
        .alert(
            "Unable to prepare payment",
            isPresented: Binding(
                get: {
                    error != nil
                },
                set: {
                    if !$0 {
                        error = nil
                    }
                }
            )
        ) {

            Button("OK") {}
        } message: {

            Text(error ?? "")
        }
    }

    private var addressField: some View {

        VStack(
            alignment: .leading,
            spacing: 8
        ) {

            Text("Bitcoin address")
                .font(.subheadline.weight(.semibold))

            TextField(
                "bc1q...",
                text: $address
            )
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .font(.system(.body, design: .monospaced))
            .padding()
            .background(
                RoundedRectangle(
                    cornerRadius: 18
                )
                .fill(AureomColor.graphite)
            )
        }
    }

    private var amountField: some View {

        VStack(
            alignment: .leading,
            spacing: 8
        ) {

            Text("Amount in satoshis")
                .font(.subheadline.weight(.semibold))

            TextField(
                "100000",
                text: $amount
            )
            .keyboardType(.numberPad)
            .font(
                .system(
                    size: 28,
                    weight: .medium,
                    design: .rounded
                )
            )
            .padding()
            .background(
                RoundedRectangle(
                    cornerRadius: 18
                )
                .fill(AureomColor.graphite)
            )
        }
    }

    private var feeInformation: some View {

        Group {

            if let fee =
                appState.bitcoinService.fee {

                HStack {

                    Text("Current fee")

                    Spacer()

                    Text(
                        "\(fee.satPerVByte) sat/vB"
                    )
                    .foregroundStyle(
                        AureomColor.bitcoinOrange
                    )
                }
                .font(.subheadline)
            }
        }
    }

    private var reviewButton: some View {

        Button {

            Task {
                await prepare()
            }

        } label: {

            HStack {

                if isPreparing {
                    ProgressView()
                } else {
                    Text("Review payment")
                    Image(
                        systemName:
                            "arrow.right"
                    )
                }
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(AureomBitcoinButton())
        .disabled(
            address.isEmpty ||
            Int64(amount) == nil ||
            isPreparing
        )
    }

    private func prepare() async {

        guard
            let sats = Int64(amount),
            sats > 0
        else {
            return
        }

        isPreparing = true
        defer {
            isPreparing = false
        }

        do {

            preview =
                try await appState.bitcoinService
                    .preparePayment(
                        address: address,
                        amountSats: sats
                    )

        } catch {

            self.error =
                error.localizedDescription
        }
    }
}
20. Bitcoin review
import SwiftUI

struct BitcoinReviewView: View {

    let preview: BitcoinPaymentPreview

    @EnvironmentObject
    private var appState: AppState

    @State private var isSigning = false
    @State private var result: String?
    @State private var error: String?

    var body: some View {

        ZStack {

            AureomBackground()

            VStack(
                alignment: .leading,
                spacing: 22
            ) {

                Text("CONFIRM PAYMENT")
                    .font(
                        .system(
                            size: 13,
                            weight: .bold,
                            design: .rounded
                        )
                    )
                    .tracking(3)
                    .foregroundStyle(
                        AureomColor.bitcoinOrange
                    )

                AureomCard {

                    VStack(
                        alignment: .leading,
                        spacing: 18
                    ) {

                        row(
                            "Destination",
                            String(
                                preview.address.prefix(18)
                            ) + "..."
                        )

                        row(
                            "Amount",
                            "\(BitcoinFormatter.sats(preview.amountSats)) sats"
                        )

                        row(
                            "Network fee",
                            "\(BitcoinFormatter.sats(preview.feeSats)) sats"
                        )

                        Divider()

                        row(
                            "Total",
                            "\(BitcoinFormatter.sats(preview.totalSats)) sats"
                        )
                    }
                }

                Spacer()

                Button {

                    Task {
                        await authenticateAndSign()
                    }

                } label: {

                    HStack {

                        if isSigning {
                            ProgressView()
                        } else {

                            Image(
                                systemName:
                                    "faceid"
                            )

                            Text("Authenticate & Send")
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(
                    AureomBitcoinButton()
                )
                .disabled(isSigning)
            }
            .padding()
        }
        .navigationTitle("Review")
        .alert(
            "Payment",
            isPresented: Binding(
                get: {
                    result != nil ||
                    error != nil
                },
                set: { value in

                    if !value {
                        result = nil
                        error = nil
                    }
                }
            )
        ) {

            Button("OK") {}

        } message: {

            Text(
                result ??
                error ??
                ""
            )
        }
    }

    private func row(
        _ title: String,
        _ value: String
    ) -> some View {

        HStack {

            Text(title)
                .foregroundStyle(.secondary)

            Spacer()

            Text(value)
                .font(
                    .system(
                        .body,
                        design: .monospaced
                    )
                )
        }
    }

    private func authenticateAndSign()
        async {

        isSigning = true
        defer {
            isSigning = false
        }

        do {

            try await BiometricAuthenticator.shared
                .authenticate(
                    reason:
                        "Authorise this Bitcoin payment"
                )

            /*
             IMPORTANT:

             The next object is deliberately abstract.

             A production Bitcoin signer must create
             a valid secp256k1 signature over the PSBT.

             Do not substitute Curve25519/Ed25519 here:
             Bitcoin transaction signatures use secp256k1.
            */

            let signedPSBT =
                try await WalletSigner.shared
                    .sign(
                        psbt: preview.psbt
                    )

            let broadcast =
                try await appState.bitcoinService
                    .broadcast(
                        paymentID:
                            preview.paymentID,
                        signedPSBT:
                            signedPSBT
                    )

            result =
                "Bitcoin sent.\n\nTXID:\n\(broadcast.txid)"

        } catch {

            self.error =
                error.localizedDescription
        }
    }
}
21. Aureom card
import SwiftUI

struct AureomCard<Content: View>: View {

    let content: Content

    init(
        @ViewBuilder content: () -> Content
    ) {
        self.content = content()
    }

    var body: some View {

        content
            .padding(22)
            .frame(maxWidth: .infinity)
            .background {

                RoundedRectangle(
                    cornerRadius: 26,
                    style: .continuous
                )
                .fill(
                    .ultraThinMaterial
                )
                .overlay {

                    RoundedRectangle(
                        cornerRadius: 26,
                        style: .continuous
                    )
                    .stroke(
                        LinearGradient(
                            colors: [
                                AureomColor.champagne
                                    .opacity(0.25),
                                Color.white
                                    .opacity(0.05),
                                AureomColor.gold
                                    .opacity(0.18)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
                }
            }
    }
}
22. Aureom shimmer

This gives the wallet the spectral/shimmer identity you wanted.

import SwiftUI

struct AureomShimmer: ViewModifier {

    @State private var phase: CGFloat = -1

    func body(
        content: Content
    ) -> some View {

        content
            .overlay {

                GeometryReader { proxy in

                    LinearGradient(
                        colors: [
                            .clear,
                            AureomColor.champagne
                                .opacity(0.05),
                            Color.white
                                .opacity(0.18),
                            AureomColor.blue
                                .opacity(0.06),
                            .clear
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(
                        width:
                            proxy.size.width * 1.5
                    )
                    .offset(
                        x:
                            proxy.size.width
                            * phase
                    )
                    .blendMode(.screen)
                }
                .clipShape(
                    RoundedRectangle(
                        cornerRadius: 26
                    )
                )
                .allowsHitTesting(false)
            }
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

extension View {

    func aureomShimmer() -> some View {

        modifier(AureomShimmer())
    }
}
23. Bitcoin button
import SwiftUI

struct AureomBitcoinButton:
    ButtonStyle {

    func makeBody(
        configuration:
            Configuration
    ) -> some View {

        configuration.label
            .font(
                .headline.weight(.semibold)
            )
            .foregroundStyle(.black)
            .padding(.vertical, 17)
            .background {

                RoundedRectangle(
                    cornerRadius: 20,
                    style: .continuous
                )
                .fill(
                    LinearGradient(
                        colors: [
                            AureomColor.bitcoinOrange,
                            AureomColor.amber
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            }
            .aureomShimmer()
            .scaleEffect(
                configuration.isPressed
                ? 0.97
                : 1
            )
            .animation(
                .spring(
                    response: 0.25,
                    dampingFraction: 0.8
                ),
                value:
                    configuration.isPressed
            )
    }
}
24. Generic Aureom button
import SwiftUI

struct AureomPrimaryButton:
    ButtonStyle {

    func makeBody(
        configuration:
            Configuration
    ) -> some View {

        configuration.label
            .font(.headline)
            .foregroundStyle(.black)
            .padding(.vertical, 17)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(
                    cornerRadius: 20,
                    style: .continuous
                )
                .fill(
                    AureomColor.champagne
                )
            )
            .scaleEffect(
                configuration.isPressed
                ? 0.97
                : 1
            )
    }
}
25. Receive Bitcoin
import SwiftUI

struct BitcoinReceiveView: View {

    @State private var address:
        BitcoinAddressResponse?

    @State private var isLoading = true
    @State private var error: String?

    @EnvironmentObject
    private var appState: AppState

    var body: some View {

        ZStack {

            AureomBackground()

            VStack(spacing: 24) {

                Text("RECEIVE BITCOIN")
                    .font(
                        .system(
                            size: 13,
                            weight: .bold,
                            design: .rounded
                        )
                    )
                    .tracking(3)
                    .foregroundStyle(
                        AureomColor.bitcoinOrange
                    )

                if let address {

                    QRCodeView(
                        string:
                            "bitcoin:\(address.address)"
                    )
                    .frame(
                        width: 260,
                        height: 260
                    )
                    .padding()
                    .background(.white)
                    .clipShape(
                        RoundedRectangle(
                            cornerRadius: 26
                        )
                    )

                    Text(address.address)
                        .font(
                            .system(
                                size: 13,
                                design: .monospaced
                            )
                        )
                        .multilineTextAlignment(.center)
                        .textSelection(.enabled)
                        .padding()

                } else if isLoading {

                    ProgressView()

                } else {

                    Text(
                        error ??
                        "Unable to generate address."
                    )
                    .foregroundStyle(
                        .secondary
                    )
                }

                Spacer()
            }
            .padding()
        }
        .navigationTitle("Receive")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadAddress()
        }
    }

    private func loadAddress() async {

        isLoading = true

        defer {
            isLoading = false
        }

        do {

            address =
                try await appState
                    .bitcoinService
                    .nodeClientAddress()

        } catch {

            self.error =
                error.localizedDescription
        }
    }
}

We need expose address from service:

extension BitcoinService {

    func nodeClientAddress()
        async throws
        -> BitcoinAddressResponse {

        /*
         Add this to BitcoinService:

         return try await nodeClient.address()
        */

        return try await nodeClientAddressInternal()
    }

    private func nodeClientAddressInternal()
        async throws
        -> BitcoinAddressResponse {

        try await nodeClient.address()
    }
}

Or, more simply, put this directly inside BitcoinService:

func receiveAddress()
    async throws
    -> BitcoinAddressResponse {

    try await nodeClient.address()
}

and replace:

appState.bitcoinService.nodeClientAddress()

with:

appState.bitcoinService.receiveAddress()
26. QR code
import SwiftUI
import CoreImage
import CoreImage.CIFilterBuiltins

struct QRCodeView: View {

    let string: String

    private let context =
        CIContext()

    var body: some View {

        if let image =
            generateQRCode(
                from: string
            ) {

            Image(
                uiImage: image
            )
            .interpolation(.none)
            .resizable()
            .scaledToFit()

        } else {

            Color.clear
        }
    }

    private func generateQRCode(
        from string: String
    ) -> UIImage? {

        let filter =
            CIFilter.qrCodeGenerator()

        filter.message =
            Data(
                string.utf8
            )

        filter.correctionLevel = "H"

        guard
            let output =
                filter.outputImage
        else {
            return nil
        }

        let scaled =
            output.transformed(
                by: CGAffineTransform(
                    scaleX: 10,
                    y: 10
                )
            )

        guard
            let cgImage =
                context.createCGImage(
                    scaled,
                    from:
                        scaled.extent
                )
        else {
            return nil
        }

        return UIImage(
            cgImage: cgImage
        )
    }
}
27. Transaction row
import SwiftUI

struct BitcoinTransactionRow:
    View {

    let transaction:
        BitcoinTransaction

    var body: some View {

        HStack(spacing: 14) {

            Image(
                systemName:
                    transaction.direction
                    == .incoming
                    ? "arrow.down.left"
                    : "arrow.up.right"
            )
            .foregroundStyle(
                transaction.direction
                    == .incoming
                    ? AureomColor.green
                    : AureomColor.bitcoinOrange
            )
            .frame(
                width: 42,
                height: 42
            )
            .background(
                Circle()
                    .fill(
                        AureomColor.graphite
                    )
            )

            VStack(
                alignment: .leading,
                spacing: 4
            ) {

                Text(
                    transaction.direction
                        == .incoming
                        ? "Received"
                        : "Sent"
                )
                .font(.headline)

                Text(
                    String(
                        transaction.txid.prefix(16)
                    ) + "..."
                )
                .font(
                    .caption.monospaced()
                )
                .foregroundStyle(
                    .secondary
                )
            }

            Spacer()

            VStack(
                alignment: .trailing,
                spacing: 4
            ) {

                Text(
                    transaction.direction
                        == .incoming
                        ? "+"
                        : "-"
                    +
                    BitcoinFormatter.btc(
                        sats:
                            transaction.amountSats
                    )
                )
                .font(.subheadline.weight(.semibold))

                Text(
                    transaction.status.rawValue
                        .capitalized
                )
                .font(.caption)
                .foregroundStyle(
                    transaction.status
                        == .confirmed
                        ? AureomColor.green
                        : .secondary
                )
            }
        }
        .padding(.vertical, 8)
    }
}
28. Transaction list
import SwiftUI

struct TransactionListView: View {

    @EnvironmentObject
    private var appState: AppState

    var body: some View {

        ZStack {

            AureomBackground()

            List {

                ForEach(
                    appState.bitcoinService
                        .transactions
                ) { transaction in

                    BitcoinTransactionRow(
                        transaction:
                            transaction
                    )
                    .listRowBackground(
                        Color.clear
                    )
                }
            }
            .scrollContentBackground(
                .hidden
            )
        }
        .navigationTitle("Activity")
        .task {

            await appState
                .bitcoinService
                .refresh()
        }
    }
}
29. Keychain

Apple documents using Keychain Services for securely storing key material, including CryptoKit-compatible key representations.

import Foundation
import Security

final class KeychainStore {

    static let shared =
        KeychainStore()

    private init() {}

    func save(
        key: String,
        value: Data
    ) throws {

        let query:
            [String: Any] = [

                kSecClass as String:
                    kSecClassGenericPassword,

                kSecAttrAccount as String:
                    key,

                kSecValueData as String:
                    value,

                kSecAttrAccessible as String:
                    kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            ]

        SecItemDelete(
            query as CFDictionary
        )

        let status =
            SecItemAdd(
                query as CFDictionary,
                nil
            )

        guard
            status == errSecSuccess
        else {

            throw KeychainError
                .saveFailed(status)
        }
    }

    func read(
        key: String
    ) throws -> Data {

        let query:
            [String: Any] = [

                kSecClass as String:
                    kSecClassGenericPassword,

                kSecAttrAccount as String:
                    key,

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

        guard
            status == errSecSuccess,
            let data =
                result as? Data
        else {

            throw KeychainError
                .readFailed(status)
        }

        return data
    }

    func delete(
        key: String
    ) throws {

        let query:
            [String: Any] = [

                kSecClass as String:
                    kSecClassGenericPassword,

                kSecAttrAccount as String:
                    key
            ]

        let status =
            SecItemDelete(
                query as CFDictionary
            )

        guard
            status == errSecSuccess ||
            status == errSecItemNotFound
        else {

            throw KeychainError
                .deleteFailed(status)
        }
    }
}

enum KeychainError:
    LocalizedError {

    case saveFailed(OSStatus)
    case readFailed(OSStatus)
    case deleteFailed(OSStatus)

    var errorDescription: String? {

        switch self {

        case .saveFailed(let status):
            return "Keychain save failed: \(status)"

        case .readFailed(let status):
            return "Keychain read failed: \(status)"

        case .deleteFailed(let status):
            return "Keychain delete failed: \(status)"
        }
    }
}
30. Face ID
import Foundation
import LocalAuthentication

actor BiometricAuthenticator {

    static let shared =
        BiometricAuthenticator()

    func authenticate(
        reason: String
    ) async throws {

        let context =
            LAContext()

        var error:
            NSError?

        guard
            context.canEvaluatePolicy(
                .deviceOwnerAuthentication,
                error: &error
            )
        else {

            throw error ??
                AuthenticationError
                    .unavailable
        }

        let success =
            try await context.evaluatePolicy(
                .deviceOwnerAuthentication,
                localizedReason: reason
            )

        guard success else {

            throw AuthenticationError
                .failed
        }
    }
}

enum AuthenticationError:
    LocalizedError {

    case unavailable
    case failed

    var errorDescription: String? {

        switch self {

        case .unavailable:
            return "Biometric authentication is unavailable."

        case .failed:
            return "Authentication failed."
        }
    }
}
31. Bitcoin signer abstraction

This is important.

Do not pretend that Apple's CryptoKit Curve25519 signing API is a Bitcoin signer. Apple's Curve25519 signing API is Ed25519, while Bitcoin transaction signatures use secp256k1.

So make the Bitcoin signer replaceable:

import Foundation

protocol BitcoinSigner:
    Sendable {

    func sign(
        psbt: String
    ) async throws -> String
}

actor WalletSigner {

    static let shared =
        WalletSigner()

    private let signer:
        BitcoinSigner

    init(
        signer: BitcoinSigner =
            DevelopmentSigner()
    ) {
        self.signer = signer
    }

    func sign(
        psbt: String
    ) async throws -> String {

        try await signer.sign(
            psbt: psbt
        )
    }
}

Development implementation:

struct DevelopmentSigner:
    BitcoinSigner {

    func sign(
        psbt: String
    ) async throws -> String {

        /*
         DEVELOPMENT ONLY.

         Never broadcast this result.

         Replace with a real PSBT signer before
         connecting the app to mainnet.
        */

        throw BitcoinSignerError
            .notConfigured
    }
}

enum BitcoinSignerError:
    LocalizedError {

    case notConfigured
    case invalidPSBT
    case signingFailed

    var errorDescription: String? {

        switch self {

        case .notConfigured:
            return "Bitcoin signer is not configured."

        case .invalidPSBT:
            return "Invalid PSBT."

        case .signingFailed:
            return "Bitcoin signing failed."
        }
    }
}

This is intentional: the application will not accidentally send fake or unsigned Bitcoin transactions.

32. Wallet home
import SwiftUI

struct WalletHomeView: View {

    @EnvironmentObject
    private var appState: AppState

    var body: some View {

        ZStack {

            AureomBackground()

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 26
                ) {

                    HStack {

                        VStack(
                            alignment: .leading,
                            spacing: 5
                        ) {

                            Text("AUREOM")
                                .font(
                                    .system(
                                        size: 12,
                                        weight: .bold,
                                        design: .rounded
                                    )
                                )
                                .tracking(4)
                                .foregroundStyle(
                                    AureomColor.champagne
                                )

                            Text("Wallet")
                                .font(
                                    .largeTitle
                                        .weight(.medium)
                                )
                        }

                        Spacer()

                        Button {

                            appState.lock()

                        } label: {

                            Image(
                                systemName:
                                    "lock.fill"
                            )
                            .font(.headline)
                        }
                    }

                    AureomMasterCard(
                        bitcoin:
                            appState
                            .bitcoinService
                            .balance
                    )

                    VStack(
                        alignment: .leading,
                        spacing: 12
                    ) {

                        Text("Your assets")
                            .font(.headline)

                        NavigationLink {

                            BitcoinWalletView()

                        } label: {

                            AssetRow(
                                title: "Bitcoin",
                                subtitle:
                                    "BTC / Lightning",
                                icon:
                                    "bitcoinsign.circle.fill",
                                colour:
                                    AureomColor
                                        .bitcoinOrange,
                                amount:
                                    appState
                                    .bitcoinService
                                    .balance
                                    .map {
                                        BitcoinFormatter
                                            .btc(
                                                sats:
                                                    $0.totalSats
                                            )
                                    } ??
                                    "—"
                            )
                        }
                    }
                }
                .padding()
            }
        }
        .navigationTitle("")
        .navigationBarHidden(true)
    }
}
33. Master Aureom card
import SwiftUI

struct AureomMasterCard:
    View {

    let bitcoin:
        BitcoinBalance?

    var body: some View {

        ZStack {

            RoundedRectangle(
                cornerRadius: 34,
                style: .continuous
            )
            .fill(
                LinearGradient(
                    colors: [
                        Color(
                            white: 0.14
                        ),
                        Color(
                            white: 0.055
                        ),
                        Color.black
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )

            Circle()
                .fill(
                    AureomColor.champagne
                        .opacity(0.12)
                )
                .frame(
                    width: 300
                )
                .blur(
                    radius: 50
                )
                .offset(
                    x: 120,
                    y: -100
                )

            VStack(
                alignment: .leading,
                spacing: 25
            ) {

                HStack {

                    Text("AUREOM")
                        .font(
                            .system(
                                size: 13,
                                weight: .bold,
                                design: .rounded
                            )
                        )
                        .tracking(4)

                    Spacer()

                    Text("2030")
                        .font(
                            .caption.monospaced()
                        )
                        .foregroundStyle(
                            .secondary
                        )
                }

                Spacer()

                VStack(
                    alignment: .leading,
                    spacing: 7
                ) {

                    Text("TOTAL DIGITAL ASSETS")
                        .font(
                            .caption2.weight(.semibold)
                        )
                        .tracking(2)
                        .foregroundStyle(
                            .secondary
                        )

                    Text(
                        bitcoin.map {
                            BitcoinFormatter.btc(
                                sats:
                                    $0.totalSats
                            )
                        } ?? "—"
                    )
                    .font(
                        .system(
                            size: 38,
                            weight: .medium,
                            design: .rounded
                        )
                    )
                    .contentTransition(
                        .numericText()
                    )
                }

                Spacer()

                HStack {

                    Text("AUREOM WALLET")
                        .font(
                            .caption2.monospaced()
                        )
                        .foregroundStyle(
                            .secondary
                        )

                    Spacer()

                    Image(
                        systemName:
                            "waveform"
                    )
                }
            }
            .padding(28)
        }
        .frame(height: 280)
        .clipShape(
            RoundedRectangle(
                cornerRadius: 34,
                style: .continuous
            )
        )
        .overlay {

            RoundedRectangle(
                cornerRadius: 34,
                style: .continuous
            )
            .stroke(
                AureomColor.champagne
                    .opacity(0.18),
                lineWidth: 1
            )
        }
        .aureomShimmer()
    }
}
34. Asset row
import SwiftUI

struct AssetRow: View {

    let title: String
    let subtitle: String
    let icon: String
    let colour: Color
    let amount: String

    var body: some View {

        HStack(spacing: 14) {

            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(colour)
                .frame(
                    width: 48,
                    height: 48
                )
                .background(
                    Circle()
                        .fill(
                            colour.opacity(0.10)
                        )
                )

            VStack(
                alignment: .leading,
                spacing: 4
            ) {

                Text(title)
                    .font(.headline)

                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(
                        .secondary
                    )
            }

            Spacer()

            Text(amount)
                .font(
                    .system(
                        .body,
                        design: .rounded
                    )
                )

            Image(
                systemName:
                    "chevron.right"
            )
            .font(.caption)
            .foregroundStyle(
                .secondary
            )
        }
        .padding()
        .background(
            RoundedRectangle(
                cornerRadius: 22,
                style: .continuous
            )
            .fill(
                AureomColor.graphite
            )
        )
    }
}
35. Settings
import SwiftUI

struct SettingsView: View {

    @EnvironmentObject
    private var appState: AppState

    var body: some View {

        ZStack {

            AureomBackground()

            List {

                Section("Wallet") {

                    Button("Lock Wallet") {

                        appState.lock()
                    }

                    Label(
                        "Bitcoin",
                        systemImage:
                            "bitcoinsign.circle"
                    )

                    Label(
                        "Lightning",
                        systemImage:
                            "bolt.fill"
                    )
                }

                Section("Security") {

                    Label(
                        "Face ID",
                        systemImage:
                            "faceid"
                    )

                    Label(
                        "Keychain",
                        systemImage:
                            "key.fill"
                    )
                }

                Section("Network") {

                    Label(
                        "Aureom Bitcoin Node",
                        systemImage:
                            "server.rack"
                    )

                    Label(
                        "Bitcoin Mainnet",
                        systemImage:
                            "network"
                    )
                }
            }
            .scrollContentBackground(
                .hidden
            )
        }
        .navigationTitle("More")
    }
}
36. One correction to BitcoinService

Use this final version rather than the earlier service:

import Foundation
import SwiftUI

@MainActor
final class BitcoinService:
    ObservableObject {

    @Published private(set) var balance:
        BitcoinBalance?

    @Published private(set) var transactions:
        [BitcoinTransaction] = []

    @Published private(set) var fee:
        BitcoinFeeEstimate?

    @Published private(set) var isLoading =
        false

    @Published var errorMessage:
        String?

    private let nodeClient:
        BitcoinNodeClient

    init(
        nodeClient: BitcoinNodeClient
    ) {
        self.nodeClient = nodeClient
    }

    func refresh() async {

        isLoading = true

        defer {
            isLoading = false
        }

        do {

            async let balanceRequest =
                nodeClient.balance()

            async let transactionsRequest =
                nodeClient.transactions()

            async let feeRequest =
                nodeClient.fee()

            balance =
                try await balanceRequest

            transactions =
                try await transactionsRequest

            fee =
                try await feeRequest

        } catch {

            errorMessage =
                error.localizedDescription
        }
    }

    func receiveAddress()
        async throws
        -> BitcoinAddressResponse {

        try await nodeClient.address()
    }

    func preparePayment(
        address: String,
        amountSats: Int64
    ) async throws
        -> BitcoinPaymentPreview {

        let request =
            BitcoinPaymentRequest(
                address: address,
                amountSats: amountSats,
                feeRateSatsPerVByte:
                    fee?.satPerVByte
            )

        return try await nodeClient.prepare(
            request: request
        )
    }

    func broadcast(
        paymentID: String,
        signedPSBT: String
    ) async throws
        -> BitcoinBroadcastResponse {

        let request =
            BitcoinBroadcastRequest(
                paymentID: paymentID,
                signedPSBT: signedPSBT
            )

        return try await nodeClient.broadcast(
            request: request
        )
    }
}

And BitcoinReceiveView should call:

address =
    try await appState
        .bitcoinService
        .receiveAddress()
