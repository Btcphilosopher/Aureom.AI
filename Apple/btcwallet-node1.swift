2. API configuration

Create APIConfiguration.swift.

import Foundation

struct APIConfiguration: Sendable {

    let baseURL: URL
    let environment: Environment

    enum Environment: Sendable {
        case development
        case staging
        case production
    }

    static let production =
        APIConfiguration(
            baseURL: URL(
                string: "https://api.aureom.ai"
            )!,
            environment: .production
        )

    static let development =
        APIConfiguration(
            baseURL: URL(
                string: "https://localhost:8443"
            )!,
            environment: .development
        )
}

For an actual device, don't use plaintext HTTP. Apple's ATS is designed to enforce secure network connections.

3. API authentication
import Foundation

struct AuthenticationTokens:
    Codable,
    Sendable {

    let accessToken: String
    let refreshToken: String
    let expiresAt: Date
}

Create a secure token store:

import Foundation

actor AuthenticationStore {

    static let shared =
        AuthenticationStore()

    private let accessKey =
        "aureom.auth.access"

    private let refreshKey =
        "aureom.auth.refresh"

    func save(
        tokens: AuthenticationTokens
    ) throws {

        try KeychainStore.shared.save(
            key: accessKey,
            value: Data(
                tokens.accessToken.utf8
            )
        )

        try KeychainStore.shared.save(
            key: refreshKey,
            value: Data(
                tokens.refreshToken.utf8
            )
        )
    }

    func accessToken() -> String? {

        guard
            let data =
                try? KeychainStore.shared.read(
                    key: accessKey
                )
        else {
            return nil
        }

        return String(
            data: data,
            encoding: .utf8
        )
    }

    func refreshToken() -> String? {

        guard
            let data =
                try? KeychainStore.shared.read(
                    key: refreshKey
                )
        else {
            return nil
        }

        return String(
            data: data,
            encoding: .utf8
        )
    }

    func clear() throws {

        try KeychainStore.shared.delete(
            key: accessKey
        )

        try KeychainStore.shared.delete(
            key: refreshKey
        )
    }
}
4. Proper authenticated API client

Replace the earlier API client with this version.

import Foundation

actor APIClient {

    private let configuration:
        APIConfiguration

    private let session:
        URLSession

    init(
        configuration:
            APIConfiguration
    ) {

        self.configuration =
            configuration

        let config =
            URLSessionConfiguration.default

        config.timeoutIntervalForRequest =
            20

        config.timeoutIntervalForResource =
            60

        config.waitsForConnectivity = true

        self.session =
            URLSession(
                configuration: config
            )
    }

    func request<T: Decodable>(
        path: String,
        method: String = "GET",
        body: Data? = nil,
        authenticated: Bool = true
    ) async throws -> T {

        let url =
            configuration.baseURL
                .appendingPathComponent(path)

        var request =
            URLRequest(url: url)

        request.httpMethod = method

        request.httpBody = body

        request.setValue(
            "application/json",
            forHTTPHeaderField:
                "Accept"
        )

        if body != nil {

            request.setValue(
                "application/json",
                forHTTPHeaderField:
                    "Content-Type"
            )
        }

        if authenticated {

            if let token =
                await AuthenticationStore
                    .shared
                    .accessToken() {

                request.setValue(
                    "Bearer \(token)",
                    forHTTPHeaderField:
                        "Authorization"
                )
            }
        }

        let (
            data,
            response
        ) =
            try await session.data(
                for: request
            )

        guard
            let http =
                response as?
                HTTPURLResponse
        else {
            throw APIError.invalidResponse
        }

        switch http.statusCode {

        case 200...299:

            return try JSONDecoder
                .aureom
                .decode(
                    T.self,
                    from: data
                )

        case 401:

            throw APIError.unauthorized

        case 400...499:

            if let error =
                try? JSONDecoder.aureom.decode(
                    ServerError.self,
                    from: data
                ) {

                throw APIError.server(
                    error.message
                )
            }

            throw APIError.http(
                http.statusCode
            )

        case 500...599:

            throw APIError.serverUnavailable

        default:

            throw APIError.http(
                http.statusCode
            )
        }
    }

    func encode<T: Encodable>(
        _ value: T
    ) throws -> Data {

        try JSONEncoder
            .aureom
            .encode(value)
    }
}

Add:

extension APIError {

    static var unauthorized:
        APIError {
        .server("Authentication required.")
    }

    static var serverUnavailable:
        APIError {
        .server(
            "Aureom node is temporarily unavailable."
        )
    }
}
5. Node status
import Foundation

struct NodeStatus:
    Codable,
    Sendable {

    let connected: Bool
    let network: BitcoinNetwork
    let blockHeight: Int
    let headers: Int
    let verificationProgress: Double
    let peers: Int
    let mempoolTransactions: Int
    let version: String

    var synchronised: Bool {
        verificationProgress >= 0.999999
    }
}
6. UTXOs

The iOS client needs a proper representation of spendable outputs.

import Foundation

struct BitcoinUTXO:
    Identifiable,
    Codable,
    Hashable,
    Sendable {

    var id: String {
        "\(txid):\(vout)"
    }

    let txid: String
    let vout: UInt32

    let amountSats: Int64

    let confirmations: Int

    let scriptPubKey: String

    let address: String?

    let spendable: Bool
}
7. Wallet state
import Foundation

struct WalletState:
    Codable,
    Sendable {

    var balance:
        BitcoinBalance?

    var utxos:
        [BitcoinUTXO]

    var transactions:
        [BitcoinTransaction]

    var fee:
        BitcoinFeeEstimate?

    var node:
        NodeStatus?

    var lightning:
        LightningBalance?

    init(
        balance: BitcoinBalance? = nil,
        utxos: [BitcoinUTXO] = [],
        transactions:
            [BitcoinTransaction] = [],
        fee: BitcoinFeeEstimate? = nil,
        node: NodeStatus? = nil,
        lightning:
            LightningBalance? = nil
    ) {

        self.balance = balance
        self.utxos = utxos
        self.transactions = transactions
        self.fee = fee
        self.node = node
        self.lightning = lightning
    }
}
8. Expand Bitcoin node client
import Foundation

actor BitcoinNodeClient {

    private let api:
        APIClient

    init(
        apiClient: APIClient
    ) {
        self.api = apiClient
    }

    func status()
        async throws
        -> NodeStatus {

        try await api.request(
            path:
                "v1/bitcoin/node/status"
        )
    }

    func balance()
        async throws
        -> BitcoinBalance {

        try await api.request(
            path:
                "v1/bitcoin/balance"
        )
    }

    func address()
        async throws
        -> BitcoinAddressResponse {

        try await api.request(
            path:
                "v1/bitcoin/address"
        )
    }

    func addresses()
        async throws
        -> [BitcoinAddressResponse] {

        try await api.request(
            path:
                "v1/bitcoin/addresses"
        )
    }

    func utxos()
        async throws
        -> [BitcoinUTXO] {

        try await api.request(
            path:
                "v1/bitcoin/utxos"
        )
    }

    func fee()
        async throws
        -> BitcoinFeeEstimate {

        try await api.request(
            path:
                "v1/bitcoin/fee"
        )
    }

    func transactions()
        async throws
        -> [BitcoinTransaction] {

        try await api.request(
            path:
                "v1/bitcoin/transactions"
        )
    }

    func transaction(
        txid: String
    ) async throws
        -> BitcoinTransaction {

        try await api.request(
            path:
                "v1/bitcoin/transaction/\(txid)"
        )
    }

    func prepare(
        request:
            BitcoinPaymentRequest
    ) async throws
        -> BitcoinPaymentPreview {

        let body =
            try await api.encode(
                request
            )

        return try await api.request(
            path:
                "v1/bitcoin/payment/prepare",
            method: "POST",
            body: body
        )
    }

    func broadcast(
        request:
            BitcoinBroadcastRequest
    ) async throws
        -> BitcoinBroadcastResponse {

        let body =
            try await api.encode(
                request
            )

        return try await api.request(
            path:
                "v1/bitcoin/payment/broadcast",
            method: "POST",
            body: body
        )
    }

    func mempool(
        txid: String
    ) async throws
        -> BitcoinMempoolTransaction {

        try await api.request(
            path:
                "v1/bitcoin/mempool/\(txid)"
        )
    }
}
9. Mempool model
import Foundation

struct BitcoinMempoolTransaction:
    Codable,
    Sendable {

    let txid: String

    let feeSats: Int64

    let vsize: Int

    let ancestorCount: Int

    let descendantCount: Int

    let firstSeen: Date
}
10. BIP-21 payment URI

This is important for QR payments.

import Foundation

struct BitcoinPaymentURI:
    Sendable {

    let address: String

    let amountSats: Int64?

    let label: String?

    let message: String?

    let lightning: String?

    init(
        string: String
    ) throws {

        guard
            let components =
                URLComponents(
                    string: string
                )
        else {
            throw BitcoinURIError.invalidURI
        }

        guard
            components.scheme?
                .lowercased()
                == "bitcoin"
        else {
            throw BitcoinURIError
                .invalidScheme
        }

        guard
            let host =
                components.host,
            !host.isEmpty
        else {
            throw BitcoinURIError
                .missingAddress
        }

        self.address = host

        var sats:
            Int64?

        var label:
            String?

        var message:
            String?

        var lightning:
            String?

        for item in
            components.queryItems ?? [] {

            switch item.name
                .lowercased() {

            case "amount":

                if let value =
                    item.value,
                   let decimal =
                    Decimal(
                        string: value
                    ) {

                    let satsDecimal =
                        decimal
                        * Decimal(
                            100_000_000
                        )

                    sats =
                        NSDecimalNumber(
                            decimal:
                                satsDecimal
                        ).int64Value
                }

            case "label":

                label = item.value

            case "message":

                message = item.value

            case "lightning":

                lightning = item.value

            default:

                break
            }
        }

        self.amountSats = sats
        self.label = label
        self.message = message
        self.lightning = lightning
    }
}

enum BitcoinURIError:
    LocalizedError {

    case invalidURI
    case invalidScheme
    case missingAddress

    var errorDescription: String? {

        switch self {

        case .invalidURI:
            return "Invalid Bitcoin payment URI."

        case .invalidScheme:
            return "Not a Bitcoin URI."

        case .missingAddress:
            return "Bitcoin address is missing."
        }
    }
}
11. QR payment scanner

Add NSCameraUsageDescription to Info.plist.

<key>NSCameraUsageDescription</key>
<string>Use the camera to scan Bitcoin and Lightning payment codes.</string>

<key>NSFaceIDUsageDescription</key>
<string>Face ID is used to unlock Aureom Wallet and authorise payments.</string>

Apple requires the Face ID usage description when biometric authentication is used.

Now:

import AVFoundation
import SwiftUI

struct QRScannerView:
    UIViewControllerRepresentable {

    let onCode:
        (String) -> Void

    func makeUIViewController(
        context:
            Context
    ) -> QRScannerController {

        QRScannerController(
            onCode: onCode
        )
    }

    func updateUIViewController(
        _ controller:
            QRScannerController,
        context:
            Context
    ) {}
}

Controller:

import AVFoundation
import UIKit

final class QRScannerController:
    UIViewController,
    AVCaptureMetadataOutputObjectsDelegate {

    private let session =
        AVCaptureSession()

    private let onCode:
        (String) -> Void

    init(
        onCode:
            @escaping (String) -> Void
    ) {

        self.onCode = onCode

        super.init(
            nibName: nil,
            bundle: nil
        )
    }

    required init?(
        coder:
            NSCoder
    ) {
        fatalError()
    }

    override func viewDidLoad() {

        super.viewDidLoad()

        view.backgroundColor =
            .black

        configureCamera()
    }

    private func configureCamera() {

        guard
            let device =
                AVCaptureDevice.default(
                    for:
                        .video
                ),
            let input =
                try? AVCaptureDeviceInput(
                    device: device
                )
        else {
            return
        }

        guard
            session.canAddInput(input)
        else {
            return
        }

        session.addInput(input)

        let output =
            AVCaptureMetadataOutput()

        guard
            session.canAddOutput(output)
        else {
            return
        }

        session.addOutput(output)

        output.setMetadataObjectsDelegate(
            self,
            queue:
                DispatchQueue.main
        )

        output.metadataObjectTypes = [
            .qr
        ]

        let preview =
            AVCaptureVideoPreviewLayer(
                session: session
            )

        preview.videoGravity =
            .resizeAspectFill

        preview.frame =
            view.bounds

        view.layer.addSublayer(
            preview
        )

        DispatchQueue.global(
            qos: .userInitiated
        ).async {

            self.session.startRunning()
        }
    }

    func metadataOutput(
        _ output:
            AVCaptureMetadataOutput,
        didOutput metadataObjects:
            [AVMetadataObject],
        from connection:
            AVCaptureConnection
    ) {

        guard
            let object =
                metadataObjects
                    .first
                as?
                AVMetadataMachineReadableCodeObject,
            let value =
                object.stringValue
        else {
            return
        }

        session.stopRunning()

        onCode(value)
    }
}
12. Scanner screen
import SwiftUI

struct ScanPaymentView:
    View {

    @Environment(\.dismiss)
    private var dismiss

    let onPayment:
        (BitcoinPaymentURI) -> Void

    @State private var error:
        String?

    var body: some View {

        ZStack {

            Color.black
                .ignoresSafeArea()

            QRScannerView { value in

                do {

                    let payment =
                        try BitcoinPaymentURI(
                            string: value
                        )

                    onPayment(payment)

                    dismiss()

                } catch {

                    self.error =
                        error.localizedDescription
                }
            }

            RoundedRectangle(
                cornerRadius: 28
            )
            .stroke(
                Color.white.opacity(0.7),
                lineWidth: 2
            )
            .frame(
                width: 280,
                height: 280
            )

            VStack {

                Spacer()

                Text(
                    "Scan Bitcoin or Lightning"
                )
                .font(.headline)
                .padding()
            }
        }
        .alert(
            "Invalid payment code",
            isPresented:
                Binding(
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

            Text(
                error ?? ""
            )
        }
    }
}
13. Lightning models
import Foundation

struct LightningBalance:
    Codable,
    Sendable {

    let confirmedMsats: Int64

    let pendingMsats: Int64

    var totalMsats: Int64 {
        confirmedMsats +
        pendingMsats
    }

    var sats: Int64 {
        totalMsats / 1_000
    }
}

struct LightningInvoice:
    Codable,
    Identifiable,
    Sendable {

    var id: String {
        paymentHash
    }

    let paymentHash: String

    let bolt11: String

    let amountMsats: Int64

    let expiresAt: Date

    let settled: Bool
}

struct LightningPayment:
    Codable,
    Identifiable,
    Sendable {

    var id: String {
        paymentHash
    }

    let paymentHash: String

    let amountMsats: Int64

    let feeMsats: Int64

    let status:
        LightningPaymentStatus

    let preimage: String?
}

enum LightningPaymentStatus:
    String,
    Codable,
    Sendable {

    case pending
    case succeeded
    case failed
}
14. Lightning node client
import Foundation

actor LightningNodeClient {

    private let api:
        APIClient

    init(
        apiClient:
            APIClient
    ) {
        self.api = apiClient
    }

    func status()
        async throws
        -> LightningNodeStatus {

        try await api.request(
            path:
                "v1/lightning/status"
        )
    }

    func balance()
        async throws
        -> LightningBalance {

        try await api.request(
            path:
                "v1/lightning/balance"
        )
    }

    func createInvoice(
        request:
            CreateLightningInvoiceRequest
    ) async throws
        -> LightningInvoice {

        let body =
            try await api.encode(
                request
            )

        return try await api.request(
            path:
                "v1/lightning/invoice",
            method:
                "POST",
            body:
                body
        )
    }

    func pay(
        request:
            PayLightningInvoiceRequest
    ) async throws
        -> LightningPayment {

        let body =
            try await api.encode(
                request
            )

        return try await api.request(
            path:
                "v1/lightning/pay",
            method:
                "POST",
            body:
                body
        )
    }

    func payment(
        hash: String
    ) async throws
        -> LightningPayment {

        try await api.request(
            path:
                "v1/lightning/payment/\(hash)"
        )
    }
}

struct LightningNodeStatus:
    Codable,
    Sendable {

    let connected: Bool
    let peers: Int
    let channels: Int
    let synced: Bool
}

struct CreateLightningInvoiceRequest:
    Codable,
    Sendable {

    let amountMsats: Int64
    let description: String
    let expirySeconds: Int
}

struct PayLightningInvoiceRequest:
    Codable,
    Sendable {

    let bolt11: String
    let maximumFeeMsats: Int64?
}
15. Lightning wallet service
import Foundation
import SwiftUI

@MainActor
final class LightningService:
    ObservableObject {

    @Published private(set)
    var balance:
        LightningBalance?

    @Published private(set)
    var node:
        LightningNodeStatus?

    @Published private(set)
    var payments:
        [LightningPayment] = []

    @Published var errorMessage:
        String?

    private let client:
        LightningNodeClient

    init(
        client:
            LightningNodeClient
    ) {
        self.client = client
    }

    func refresh() async {

        do {

            async let balanceRequest =
                client.balance()

            async let statusRequest =
                client.status()

            balance =
                try await balanceRequest

            node =
                try await statusRequest

        } catch {

            errorMessage =
                error.localizedDescription
        }
    }

    func createInvoice(
        sats: Int64,
        description: String
    ) async throws
        -> LightningInvoice {

        let request =
            CreateLightningInvoiceRequest(
                amountMsats:
                    sats * 1_000,
                description:
                    description,
                expirySeconds:
                    3600
            )

        return try await client
            .createInvoice(
                request: request
            )
    }

    func pay(
        bolt11: String
    ) async throws
        -> LightningPayment {

        let request =
            PayLightningInvoiceRequest(
                bolt11:
                    bolt11,
                maximumFeeMsats:
                    10_000
            )

        return try await client.pay(
            request: request
        )
    }
}
16. Combined wallet repository

Now unify Bitcoin and Lightning.

import Foundation
import SwiftUI

@MainActor
final class WalletRepository:
    ObservableObject {

    @Published private(set)
    var bitcoinBalance:
        BitcoinBalance?

    @Published private(set)
    var lightningBalance:
        LightningBalance?

    @Published private(set)
    var nodeStatus:
        NodeStatus?

    @Published private(set)
    var lightningStatus:
        LightningNodeStatus?

    @Published private(set)
    var bitcoinTransactions:
        [BitcoinTransaction] = []

    @Published private(set)
    var isRefreshing = false

    let bitcoin:
        BitcoinNodeClient

    let lightning:
        LightningNodeClient

    init(
        api:
            APIClient
    ) {

        self.bitcoin =
            BitcoinNodeClient(
                apiClient: api
            )

        self.lightning =
            LightningNodeClient(
                apiClient: api
            )
    }

    func refresh() async {

        isRefreshing = true

        defer {
            isRefreshing = false
        }

        do {

            async let btc =
                bitcoin.balance()

            async let btcNode =
                bitcoin.status()

            async let txs =
                bitcoin.transactions()

            async let ln =
                lightning.balance()

            async let lnNode =
                lightning.status()

            bitcoinBalance =
                try await btc

            nodeStatus =
                try await btcNode

            bitcoinTransactions =
                try await txs

            lightningBalance =
                try await ln

            lightningStatus =
                try await lnNode

        } catch {

            print(
                "Wallet refresh failed:",
                error
            )
        }
    }

    var totalLightningSats:
        Int64 {

        lightningBalance?
            .sats ?? 0
    }
}
17. Wallet engine

This becomes the main object the UI talks to.

import Foundation
import SwiftUI

@MainActor
final class AureomWalletEngine:
    ObservableObject {

    @Published
    private(set)
    var repository:
        WalletRepository

    @Published
    var locked = true

    @Published
    var networkStatus:
        NetworkStatus = .offline

    init() {

        let api =
            APIClient(
                configuration:
                    .production
            )

        self.repository =
            WalletRepository(
                api: api
            )
    }

    func unlock() async throws {

        try await
            BiometricAuthenticator
                .shared
                .authenticate(
                    reason:
                        "Unlock Aureom Wallet"
                )

        locked = false
    }

    func lock() {

        locked = true
    }

    func refresh() async {

        await repository.refresh()
    }
}

enum NetworkStatus:
    Sendable {

    case online
    case offline
    case degraded
}
18. Network monitor
import Foundation
import Network

@MainActor
final class NetworkMonitor:
    ObservableObject {

    @Published
    private(set)
    var isConnected = false

    @Published
    private(set)
    var interface:
        NWInterface.InterfaceType?

    private let monitor =
        NWPathMonitor()

    private let queue =
        DispatchQueue(
            label:
                "aureom.network.monitor"
        )

    init() {

        monitor.pathUpdateHandler = {
            [weak self] path in

            Task { @MainActor in

                self?.isConnected =
                    path.status
                    == .satisfied

                self?.interface =
                    path.availableInterfaces
                        .first {
                            path.usesInterfaceType(
                                $0.type
                            )
                        }?
                        .type
            }
        }

        monitor.start(
            queue: queue
        )
    }

    deinit {
        monitor.cancel()
    }
}
19. Offline queue

This is useful when the user prepares a transaction but temporarily loses connectivity.

Important: never silently send a Bitcoin transaction merely because connectivity returned. The user should explicitly approve broadcast.

import Foundation

struct PendingPayment:
    Identifiable,
    Codable,
    Sendable {

    let id: UUID

    let paymentID: String

    let createdAt: Date

    let amountSats: Int64

    let address: String

    let signedPSBT: String
}

actor PendingPaymentStore {

    static let shared =
        PendingPaymentStore()

    private var payments:
        [PendingPayment] = []

    func add(
        _ payment:
            PendingPayment
    ) {
        payments.append(payment)
    }

    func all()
        -> [PendingPayment] {
        payments
    }

    func remove(
        id: UUID
    ) {

        payments.removeAll {
            $0.id == id
        }
    }
}
20. Transaction monitoring

After broadcast, the wallet should watch the transaction.

import Foundation

@MainActor
final class TransactionMonitor:
    ObservableObject {

    @Published
    private(set)
    var transaction:
        BitcoinTransaction?

    @Published
    private(set)
    var isMonitoring = false

    private let client:
        BitcoinNodeClient

    init(
        client:
            BitcoinNodeClient
    ) {
        self.client = client
    }

    func monitor(
        txid: String
    ) async {

        isMonitoring = true

        defer {
            isMonitoring = false
        }

        for _ in 0..<60 {

            do {

                let tx =
                    try await client
                        .transaction(
                            txid: txid
                        )

                transaction = tx

                if tx.confirmations > 0 {
                    break
                }

            } catch {

                print(
                    "Transaction poll:",
                    error
                )
            }

            try? await Task.sleep(
                for:
                    .seconds(10)
            )
        }
    }
}
21. Send-success screen
import SwiftUI

struct BitcoinSentView:
    View {

    let txid: String

    @State private var scale:
        CGFloat = 0.5

    @State private var opacity:
        Double = 0

    var body: some View {

        ZStack {

            AureomBackground()

            VStack(spacing: 28) {

                ZStack {

                    Circle()
                        .fill(
                            AureomColor
                                .bitcoinOrange
                                .opacity(0.15)
                        )
                        .frame(
                            width: 160,
                            height: 160
                        )
                        .blur(
                            radius: 20
                        )

                    Image(
                        systemName:
                            "checkmark"
                    )
                    .font(
                        .system(
                            size: 55,
                            weight: .medium
                        )
                    )
                    .foregroundStyle(
                        AureomColor.green
                    )
                }
                .scaleEffect(scale)
                .opacity(opacity)

                Text("Bitcoin sent")
                    .font(
                        .system(
                            size: 30,
                            weight: .medium,
                            design: .rounded
                        )
                    )

                Text(txid)
                    .font(
                        .system(
                            size: 12,
                            design: .monospaced
                        )
                    )
                    .foregroundStyle(
                        .secondary
                    )
                    .multilineTextAlignment(
                        .center
                    )
                    .textSelection(
                        .enabled
                    )
                    .padding()
            }
        }
        .onAppear {

            withAnimation(
                .spring(
                    response: 0.6,
                    dampingFraction: 0.7
                )
            ) {

                scale = 1
                opacity = 1
            }
        }
    }
}
22. Node dashboard

Now you can actually expose the state of the Aureom node to the user.

import SwiftUI

struct NodeDashboardView:
    View {

    @EnvironmentObject
    private var wallet:
        AureomWalletEngine

    var body: some View {

        List {

            Section("Bitcoin Node") {

                statusRow(
                    "Network",
                    wallet.repository
                        .nodeStatus?
                        .network
                        .rawValue
                        ?? "—"
                )

                statusRow(
                    "Block height",
                    "\(wallet.repository
                        .nodeStatus?
                        .blockHeight
                        ?? 0)"
                )

                statusRow(
                    "Peers",
                    "\(wallet.repository
                        .nodeStatus?
                        .peers
                        ?? 0)"
                )

                statusRow(
                    "Mempool",
                    "\(wallet.repository
                        .nodeStatus?
                        .mempoolTransactions
                        ?? 0)"
                )

                statusRow(
                    "Sync",
                    wallet.repository
                        .nodeStatus?
                        .synchronised == true
                        ? "Synchronized"
                        : "Syncing"
                )
            }

            Section("Lightning") {

                statusRow(
                    "Status",
                    wallet.repository
                        .lightningStatus?
                        .connected == true
                        ? "Connected"
                        : "Offline"
                )

                statusRow(
                    "Peers",
                    "\(wallet.repository
                        .lightningStatus?
                        .peers
                        ?? 0)"
                )

                statusRow(
                    "Channels",
                    "\(wallet.repository
                        .lightningStatus?
                        .channels
                        ?? 0)"
                )
            }
        }
        .navigationTitle("Node")
        .refreshable {

            await wallet.refresh()
        }
    }

    private func statusRow(
        _ title: String,
        _ value: String
    ) -> some View {

        HStack {

            Text(title)

            Spacer()

            Text(value)
                .foregroundStyle(
                    .secondary
                )
        }
    }
}
23. Background refresh

For wallet information, you can schedule refresh work, but don't design around an assumption that iOS will continuously execute your app in the background. Apple's background URLSession infrastructure is specifically designed for transfers that can continue while the application is suspended; normal background execution is system-controlled.

Add:

import BackgroundTasks

enum AureomBackground {

    static let refreshID =
        "ai.aureom.wallet.refresh"

    static func register() {

        BGTaskScheduler.shared
            .register(
                forTaskWithIdentifier:
                    refreshID,
                using: nil
            ) { task in

                guard
                    let refresh =
                        task as?
                        BGAppRefreshTask
                else {
                    return
                }

                handle(
                    refresh
                )
            }
    }

    static func schedule() {

        let request =
            BGAppRefreshTaskRequest(
                identifier:
                    refreshID
            )

        request.earliestBeginDate =
            Date(
                timeIntervalSinceNow:
                    15 * 60
            )

        try? BGTaskScheduler.shared
            .submit(request)
    }

    private static func handle(
        _ task:
            BGAppRefreshTask
    ) {

        schedule()

        let engine =
            AureomWalletEngine()

        task.expirationHandler = {
            task.setTaskCompleted(
                success: false
            )
        }

        Task {

            await engine.refresh()

            task.setTaskCompleted(
                success: true
            )
        }
    }
}

Register it in the app:

import SwiftUI

@main
struct AureomWalletApp:
    App {

    @StateObject
    private var wallet =
        AureomWalletEngine()

    init() {

        AureomBackground
            .register()
    }

    var body: some Scene {

        WindowGroup {

            RootWalletView()
                .environmentObject(
                    wallet
                )
        }
    }
}

And schedule it when appropriate:

AureomBackground.schedule()
24. Push transaction notifications

The server should ultimately send a push notification when:

Bitcoin payment:
    broadcast
       ↓
mempool
       ↓
confirmed

The iOS app needs a notification service.

import UserNotifications

@MainActor
final class NotificationService:

    NSObject,
    ObservableObject {

    static let shared =
        NotificationService()

    func requestPermission()
        async throws {

        let center =
            UNUserNotificationCenter
                .current()

        let granted =
            try await center
                .requestAuthorization(
                    options: [
                        .alert,
                        .sound,
                        .badge
                    ]
                )

        guard granted else {
            return
        }
    }

    func notifyTransactionConfirmed(
        txid: String
    ) {

        let content =
            UNMutableNotificationContent()

        content.title =
            "Bitcoin confirmed"

        content.body =
            "Transaction \(txid.prefix(12))… has been confirmed."

        content.sound =
            .default

        let request =
            UNNotificationRequest(
                identifier:
                    UUID().uuidString,
                content:
                    content,
                trigger:
                    nil
            )

        UNUserNotificationCenter
            .current()
            .add(request)
    }
}
25. Secure payment coordinator

This is the important piece tying everything together.

import Foundation

@MainActor
final class BitcoinPaymentCoordinator:
    ObservableObject {

    @Published
    private(set)
    var state:
        PaymentState = .idle

    private let bitcoin:
        BitcoinNodeClient

    init(
        bitcoin:
            BitcoinNodeClient
    ) {
        self.bitcoin = bitcoin
    }

    func prepare(
        address: String,
        sats: Int64
    ) async {

        state = .preparing

        do {

            let request =
                BitcoinPaymentRequest(
                    address:
                        address,
                    amountSats:
                        sats,
                    feeRateSatsPerVByte:
                        nil
                )

            let preview =
                try await bitcoin
                    .prepare(
                        request:
                            request
                    )

            state =
                .ready(preview)

        } catch {

            state =
                .failed(
                    error.localizedDescription
                )
        }
    }

    func signAndBroadcast(
        preview:
            BitcoinPaymentPreview
    ) async {

        state = .authenticating

        do {

            try await
                BiometricAuthenticator
                    .shared
                    .authenticate(
                        reason:
                            "Authorise this Bitcoin payment"
                    )

            state = .signing

            let signed =
                try await
                    WalletSigner
                    .shared
                    .sign(
                        psbt:
                            preview.psbt
                    )

            state = .broadcasting

            let result =
                try await bitcoin
                    .broadcast(
                        request:
                            BitcoinBroadcastRequest(
                                paymentID:
                                    preview.paymentID,
                                signedPSBT:
                                    signed
                            )
                    )

            state =
                .broadcast(
                    result.txid
                )

        } catch {

            state =
                .failed(
                    error.localizedDescription
                )
        }
    }
}

enum PaymentState:
    Sendable {

    case idle
    case preparing
    case ready(
        BitcoinPaymentPreview
    )
    case authenticating
    case signing
    case broadcasting
    case broadcast(String)
    case failed(String)
}
26. Payment progress UI
import SwiftUI

struct BitcoinPaymentProgress:
    View {

    let state:
        PaymentState

    var body: some View {

        VStack(spacing: 20) {

            switch state {

            case .idle:

                EmptyView()

            case .preparing:

                ProgressView()

                Text(
                    "Preparing transaction…"
                )

            case .ready:

                Image(
                    systemName:
                        "checkmark.circle"
                )

                Text(
                    "Transaction ready"
                )

            case .authenticating:

                Image(
                    systemName:
                        "faceid"
                )
                .font(.system(size: 42))

                Text(
                    "Authenticate payment"
                )

            case .signing:

                ProgressView()

                Text(
                    "Signing securely…"
                )

            case .broadcasting:

                ProgressView()

                Text(
                    "Broadcasting to Bitcoin…"
                )

            case .broadcast(let txid):

                Image(
                    systemName:
                        "checkmark.circle.fill"
                )
                .font(.system(size: 50))
                .foregroundStyle(
                    AureomColor.green
                )

                Text("Sent")

                Text(txid)
                    .font(
                        .caption.monospaced()
                    )

            case .failed(let message):

                Image(
                    systemName:
                        "exclamationmark.triangle"
                )

                Text(message)
            }
        }
        .animation(
            .spring(
                response: 0.35,
                dampingFraction: 0.8
            ),
            value:
                String(
                    describing:
                        state
                )
        )
    }
}
27. Lightning wallet UI
import SwiftUI

struct LightningWalletView:
    View {

    @StateObject
    private var service:
        LightningService

    init(
        api:
            APIClient
    ) {

        _service =
            StateObject(
                wrappedValue:
                    LightningService(
                        client:
                            LightningNodeClient(
                                apiClient:
                                    api
                            )
                    )
            )
    }

    var body: some View {

        ZStack {

            AureomBackground()

            ScrollView {

                VStack(
                    spacing: 24
                ) {

                    LightningBalanceCard(
                        balance:
                            service.balance
                    )

                    HStack {

                        NavigationLink {
                            LightningReceiveView(
                                service:
                                    service
                            )
                        } label: {

                            ActionTile(
                                title:
                                    "Receive",
                                icon:
                                    "arrow.down.left",
                                colour:
                                    AureomColor
                                        .gold
                            )
                        }

                        NavigationLink {
                            LightningSendView(
                                service:
                                    service
                            )
                        } label: {

                            ActionTile(
                                title:
                                    "Pay",
                                icon:
                                    "bolt.fill",
                                colour:
                                    AureomColor
                                        .champagne
                            )
                        }
                    }
                }
                .padding()
            }
        }
        .navigationTitle(
            "Lightning"
        )
        .task {

            await service.refresh()
        }
    }
}
28. Lightning balance
import SwiftUI

struct LightningBalanceCard:
    View {

    let balance:
        LightningBalance?

    var body: some View {

        AureomCard {

            VStack(
                alignment: .leading,
                spacing: 12
            ) {

                HStack {

                    Text("LIGHTNING")
                        .font(
                            .caption.weight(
                                .bold
                            )
                        )
                        .tracking(3)

                    Spacer()

                    Image(
                        systemName:
                            "bolt.fill"
                    )
                    .foregroundStyle(
                        AureomColor.gold
                    )
                }

                if let balance {

                    Text(
                        BitcoinFormatter
                            .btc(
                                sats:
                                    balance.sats
                            )
                    )
                    .font(
                        .system(
                            size: 40,
                            weight: .medium,
                            design: .rounded
                        )
                    )

                    Text("BTC")
                        .foregroundStyle(
                            AureomColor.gold
                        )

                    Text(
                        "\(balance.sats) sats"
                    )
                    .font(
                        .caption.monospaced()
                    )
                    .foregroundStyle(
                        .secondary
                    )

                } else {

                    ProgressView()
                }
            }
        }
        .aureomShimmer()
    }
}
29. Lightning receive
import SwiftUI

struct LightningReceiveView:
    View {

    @ObservedObject
    var service:
        LightningService

    @State private var amount =
        ""

    @State private var description =
        ""

    @State private var invoice:
        LightningInvoice?

    var body: some View {

        ZStack {

            AureomBackground()

            ScrollView {

                VStack(
                    spacing: 20
                ) {

                    TextField(
                        "Amount in sats",
                        text:
                            $amount
                    )
                    .keyboardType(
                        .numberPad
                    )
                    .padding()
                    .background(
                        AureomCardBackground()
                    )

                    TextField(
                        "Description",
                        text:
                            $description
                    )
                    .padding()
                    .background(
                        AureomCardBackground()
                    )

                    Button {

                        Task {
                            await create()
                        }

                    } label: {

                        Text(
                            "Create invoice"
                        )
                        .frame(
                            maxWidth:
                                .infinity
                        )
                    }
                    .buttonStyle(
                        AureomPrimaryButton()
                    )

                    if let invoice {

                        QRCodeView(
                            string:
                                invoice.bolt11
                        )
                        .frame(
                            width: 270,
                            height: 270
                        )
                        .padding()
                        .background(
                            .white
                        )
                        .clipShape(
                            RoundedRectangle(
                                cornerRadius:
                                    24
                            )
                        )

                        Text(
                            invoice.bolt11
                        )
                        .font(
                            .caption.monospaced()
                        )
                        .textSelection(
                            .enabled
                        )
                    }
                }
                .padding()
            }
        }
        .navigationTitle(
            "Receive Lightning"
        )
    }

    private func create() async {

        guard
            let sats =
                Int64(amount),
            sats > 0
        else {
            return
        }

        do {

            invoice =
                try await service
                    .createInvoice(
                        sats:
                            sats,
                        description:
                            description
                    )

        } catch {

            print(error)
        }
    }
}
30. Lightning send
import SwiftUI

struct LightningSendView:
    View {

    @ObservedObject
    var service:
        LightningService

    @State private var invoice =
        ""

    @State private var payment:
        LightningPayment?

    @State private var isPaying =
        false

    var body: some View {

        ZStack {

            AureomBackground()

            VStack(
                spacing: 24
            ) {

                TextField(
                    "Paste Lightning invoice",
                    text:
                        $invoice,
                    axis:
                        .vertical
                )
                .textInputAutocapitalization(
                    .never
                )
                .autocorrectionDisabled()
                .font(
                    .system(
                        .body,
                        design:
                            .monospaced
                    )
                )
                .padding()
                .background(
                    AureomCardBackground()
                )

                Button {

                    Task {
                        await pay()
                    }

                } label: {

                    HStack {

                        if isPaying {
                            ProgressView()
                        }

                        Text(
                            "Pay Lightning invoice"
                        )
                    }
                    .frame(
                        maxWidth:
                            .infinity
                    )
                }
                .buttonStyle(
                    AureomPrimaryButton()
                )

                if let payment {

                    LightningPaymentResult(
                        payment:
                            payment
                    )
                }

                Spacer()
            }
            .padding()
        }
        .navigationTitle(
            "Pay Lightning"
        )
    }

    private func pay() async {

        guard
            !invoice.isEmpty
        else {
            return
        }

        isPaying = true

        defer {
            isPaying = false
        }

        do {

            try await
                BiometricAuthenticator
                    .shared
                    .authenticate(
                        reason:
                            "Authorise Lightning payment"
                    )

            payment =
                try await service
                    .pay(
                        bolt11:
                            invoice
                    )

        } catch {

            print(error)
        }
    }
}
31. Lightning payment result
import SwiftUI

struct LightningPaymentResult:
    View {

    let payment:
        LightningPayment

    var body: some View {

        AureomCard {

            VStack(spacing: 12) {

                Image(
                    systemName:
                        payment.status
                        == .succeeded
                        ? "checkmark.circle.fill"
                        : "bolt.circle"
                )
                .font(
                    .system(size: 45)
                )
                .foregroundStyle(
                    payment.status
                        == .succeeded
                        ? AureomColor.green
                        : AureomColor.gold
                )

                Text(
                    payment.status
                        .rawValue
                        .capitalized
                )

                Text(
                    "\(payment.amountMsats / 1_000) sats"
                )
                .font(
                    .headline.monospaced()
                )
            }
            .frame(
                maxWidth: .infinity
            )
        }
    }
}
32. Scanner integration

Now add a scan button to the Bitcoin send screen:

@State private var showScanner = false

Button:

Button {

    showScanner = true

} label: {

    Label(
        "Scan QR",
        systemImage:
            "qrcode.viewfinder"
    )
}
.sheet(
    isPresented:
        $showScanner
) {

    ScanPaymentView { payment in

        address =
            payment.address

        if let sats =
            payment.amountSats {

            amount =
                String(sats)
        }
    }
}

Now the user can:

QR
 ↓
bitcoin:bc1q...?amount=0.001
 ↓
BIP-21 parser
 ↓
address = bc1q...
amount = 100000 sats
 ↓
Review
 ↓
Face ID
 ↓
PSBT
 ↓
sign
 ↓
broadcast
33. API request IDs

For financial transactions, add an idempotency key.

import Foundation

struct PaymentHeaders {

    let idempotencyKey:
        String

    let deviceID:
        String

    let requestID:
        String

    init() {

        idempotencyKey =
            UUID().uuidString

        deviceID =
            DeviceIdentity.shared
                .identifier

        requestID =
            UUID().uuidString
    }
}

Device identity:

import Foundation

final class DeviceIdentity {

    static let shared =
        DeviceIdentity()

    private let key =
        "aureom.device.id"

    private(set)
    lazy var identifier: String = {

        if let data =
            try? KeychainStore.shared
                .read(
                    key: key
                ),
           let value =
                String(
                    data: data,
                    encoding: .utf8
                ) {

            return value
        }

        let value =
            UUID().uuidString

        try? KeychainStore.shared
            .save(
                key: key,
                value:
                    Data(
                        value.utf8
                    )
            )

        return value
    }()
}

The server should reject reuse of an idempotency key with different transaction parameters.

34. Add request headers to the API client

Inside APIClient.request:

let headers =
    PaymentHeaders()

request.setValue(
    headers.requestID,
    forHTTPHeaderField:
        "X-Aureom-Request-ID"
)

request.setValue(
    headers.deviceID,
    forHTTPHeaderField:
        "X-Aureom-Device-ID"
)

if method == "POST" {

    request.setValue(
        headers.idempotencyKey,
        forHTTPHeaderField:
            "Idempotency-Key"
    )
}

For production, I would actually generate the idempotency key once per logical payment operation, rather than once per HTTP retry.

35. API authentication refresh

Add:

struct RefreshTokenRequest:
    Codable {

    let refreshToken:
        String
}

struct RefreshTokenResponse:
    Codable {

    let accessToken:
        String

    let refreshToken:
        String

    let expiresAt:
        Date
}

Then:

actor AuthenticationService {

    static let shared =
        AuthenticationService()

    private let session =
        URLSession.shared

    func refreshIfNeeded()
        async throws {

        guard
            let refresh =
                await AuthenticationStore
                    .shared
                    .refreshToken()
        else {
            throw APIError.unauthorized
        }

        let requestBody =
            RefreshTokenRequest(
                refreshToken:
                    refresh
            )

        let data =
            try JSONEncoder
                .aureom
                .encode(
                    requestBody
                )

        var request =
            URLRequest(
                url:
                    URL(
                        string:
                            "https://api.aureom.ai/v1/auth/refresh"
                    )!
            )

        request.httpMethod =
            "POST"

        request.httpBody =
            data

        request.setValue(
            "application/json",
            forHTTPHeaderField:
                "Content-Type"
        )

        let (
            responseData,
            response
        ) =
            try await session.data(
                for: request
            )

        guard
            let http =
                response as?
                HTTPURLResponse,
            200..<300 ~= http.statusCode
        else {
            throw APIError.unauthorized
        }

        let tokens =
            try JSONDecoder
                .aureom
                .decode(
                    RefreshTokenResponse.self,
                    from:
                        responseData
                )

        try await AuthenticationStore
            .shared
            .save(
                tokens:
                    AuthenticationTokens(
                        accessToken:
                            tokens.accessToken,
                        refreshToken:
                            tokens.refreshToken,
                        expiresAt:
                            tokens.expiresAt
                    )
            )
    }
}
36. Wallet activity model

The UI shouldn't care whether something happened on-chain or through Lightning.

import Foundation

enum WalletActivity:
    Identifiable,
    Sendable {

    case bitcoin(
        BitcoinTransaction
    )

    case lightning(
        LightningPayment
    )

    var id: String {

        switch self {

        case .bitcoin(let tx):
            return "btc-\(tx.id)"

        case .lightning(let payment):
            return "ln-\(payment.id)"
        }
    }
}
37. Unified activity screen
import SwiftUI

struct UnifiedActivityView:
    View {

    let bitcoin:
        [BitcoinTransaction]

    let lightning:
        [LightningPayment]

    var body: some View {

        List {

            Section("Bitcoin") {

                ForEach(
                    bitcoin
                ) { transaction in

                    BitcoinTransactionRow(
                        transaction:
                            transaction
                    )
                }
            }

            Section("Lightning") {

                ForEach(
                    lightning
                ) { payment in

                    HStack {

                        Image(
                            systemName:
                                "bolt.fill"
                        )
                        .foregroundStyle(
                            AureomColor.gold
                        )

                        VStack(
                            alignment:
                                .leading
                        ) {

                            Text(
                                "Lightning payment"
                            )

                            Text(
                                payment.status
                                    .rawValue
                                    .capitalized
                            )
                            .font(
                                .caption
                            )
                            .foregroundStyle(
                                .secondary
                            )
                        }

                        Spacer()

                        Text(
                            "\(payment.amountMsats / 1_000) sats"
                        )
                        .font(
                            .caption.monospaced()
                        )
                    }
                }
            }
        }
        .scrollContentBackground(
            .hidden
        )
        .background(
            AureomColor.void
        )
    }
}
38. Final application root

This replaces the earlier fragmented AppState.

import SwiftUI

@main
struct AureomWalletApp:
    App {

    @StateObject
    private var wallet =
        AureomWalletEngine()

    @StateObject
    private var network =
        NetworkMonitor()

    init() {

        AureomBackground.register()
    }

    var body: some Scene {

        WindowGroup {

            RootWalletView()
                .environmentObject(
                    wallet
                )
                .environmentObject(
                    network
                )
                .preferredColorScheme(
                    .dark
                )
        }
    }
}
39. Root wallet
import SwiftUI

struct RootWalletView:
    View {

    @EnvironmentObject
    private var wallet:
        AureomWalletEngine

    var body: some View {

        Group {

            if wallet.locked {

                LockedWalletView2()

            } else {

                MainWalletView2()
            }
        }
        .task {

            if !wallet.locked {

                await wallet.refresh()
            }
        }
    }
}
40. New locked screen
import SwiftUI

struct LockedWalletView2:
    View {

    @EnvironmentObject
    private var wallet:
        AureomWalletEngine

    @State private var glow =
        false

    var body: some View {

        ZStack {

            AureomBackground()

            VStack(spacing: 30) {

                Spacer()

                ZStack {

                    Circle()
                        .fill(
                            AureomColor
                                .champagne
                                .opacity(
                                    glow
                                    ? 0.18
                                    : 0.08
                                )
                        )
                        .frame(
                            width: 220,
                            height: 220
                        )
                        .blur(
                            radius: 35
                        )

                    Image(
                        systemName:
                            "wallet.pass.fill"
                    )
                    .font(
                        .system(
                            size: 50,
                            weight: .medium
                        )
                    )
                    .foregroundStyle(
                        AureomColor
                            .champagne
                    )
                }

                Text("AUREOM")
                    .font(
                        .system(
                            size: 14,
                            weight: .bold,
                            design: .rounded
                        )
                    )
                    .tracking(6)

                Text("Wallet locked")
                    .font(
                        .title
                            .weight(.medium)
                    )

                Button {

                    Task {

                        try? await
                            wallet.unlock()
                    }

                } label: {

                    Label(
                        "Unlock with Face ID",
                        systemImage:
                            "faceid"
                    )
                    .frame(
                        maxWidth:
                            .infinity
                    )
                }
                .buttonStyle(
                    AureomPrimaryButton()
                )

                Spacer()
            }
            .padding(28)
        }
        .onAppear {

            withAnimation(
                .easeInOut(
                    duration: 2
                )
                .repeatForever(
                    autoreverses: true
                )
            ) {

                glow = true
            }
        }
    }
}
41. Final main wallet
import SwiftUI

struct MainWalletView2:
    View {

    @EnvironmentObject
    private var wallet:
        AureomWalletEngine

    @State private var tab = 0

    var body: some View {

        TabView(
            selection:
                $tab
        ) {

            NavigationStack {

                WalletHomeView2()
            }
            .tabItem {

                Label(
                    "Wallet",
                    systemImage:
                        "wallet.pass"
                )
            }
            .tag(0)

            NavigationStack {

                BitcoinWalletView2()
            }
            .tabItem {

                Label(
                    "Bitcoin",
                    systemImage:
                        "bitcoinsign.circle"
                )
            }
            .tag(1)

            NavigationStack {

                UnifiedActivityView(
                    bitcoin:
                        wallet
                        .repository
                        .bitcoinTransactions,
                    lightning: []
                )
            }
            .tabItem {

                Label(
                    "Activity",
                    systemImage:
                        "clock.arrow.circlepath"
                )
            }
            .tag(2)

            NavigationStack {

                NodeDashboardView()
            }
            .tabItem {

                Label(
                    "Node",
                    systemImage:
                        "server.rack"
                )
            }
            .tag(3)
        }
        .tint(
            AureomColor.champagne
        )
    }
}
42. Bitcoin home
import SwiftUI

struct BitcoinWalletView2:
    View {

    @EnvironmentObject
    private var wallet:
        AureomWalletEngine

    var body: some View {

        ScrollView {

            VStack(
                spacing: 24
            ) {

                BitcoinBalanceCard(
                    balance:
                        wallet
                        .repository
                        .bitcoinBalance
                )

                HStack {

                    NavigationLink {

                        BitcoinSendView()
                    } label: {

                        ActionTile(
                            title:
                                "Send",
                            icon:
                                "arrow.up.right",
                            colour:
                                AureomColor
                                    .bitcoinOrange
                        )
                    }

                    NavigationLink {

                        BitcoinReceiveView()
                    } label: {

                        ActionTile(
                            title:
                                "Receive",
                            icon:
                                "arrow.down.left",
                            colour:
                                AureomColor.green
                        )
                    }
                }

                NavigationLink {

                    ScanPaymentView { payment in

                        print(
                            payment.address
                        )
                    }

                } label: {

                    Label(
                        "Scan payment",
                        systemImage:
                            "qrcode.viewfinder"
                    )
                    .frame(
                        maxWidth:
                            .infinity
                    )
                }
                .buttonStyle(
                    AureomPrimaryButton()
                )

                ForEach(
                    wallet
                        .repository
                        .bitcoinTransactions
                        .prefix(10)
                ) { tx in

                    BitcoinTransactionRow(
                        transaction:
                            tx
                    )
                }
            }
            .padding()
        }
        .background(
            AureomColor.void
        )
        .navigationTitle(
            "Bitcoin"
        )
        .refreshable {

            await wallet.refresh()
        }
    }
}

