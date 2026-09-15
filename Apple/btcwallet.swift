1. Bitcoin models

Create BitcoinModels.swift.

import Foundation

struct BitcoinAccount: Identifiable, Codable {

    let id: UUID

    var name: String

    var address: String

    var balanceSats: UInt64

    var network: BitcoinNetwork

    var isWatchOnly: Bool

    var createdAt: Date

    var balanceBTC: Double {
        Double(balanceSats) / 100_000_000.0
    }
}

enum BitcoinNetwork: String, Codable {

    case mainnet
    case testnet
    case signet
    case regtest
}

struct BitcoinTransaction:
    Identifiable,
    Codable {

    let id: UUID

    let txid: String

    let amountSats: Int64

    let feeSats: UInt64

    let confirmations: UInt64

    let timestamp: Date

    let status: BitcoinTransactionStatus
}

enum BitcoinTransactionStatus:
    String,
    Codable {

    case pending
    case confirmed
    case failed
}
2. Satoshi utility

Never use floating-point BTC amounts internally.

Use satoshis.

enum BitcoinUnits {

    static let satsPerBTC:
        UInt64 = 100_000_000

    static func btc(
        from sats: UInt64
    ) -> Double {

        Double(sats) /
            Double(satsPerBTC)
    }

    static func sats(
        from btc: Double
    ) -> UInt64? {

        guard btc >= 0 else {
            return nil
        }

        return UInt64(
            btc * Double(satsPerBTC)
        )
    }

    static func formatBTC(
        sats: UInt64
    ) -> String {

        String(
            format: "%.8f BTC",
            btc(from: sats)
        )
    }

    static func formatSats(
        _ sats: UInt64
    ) -> String {

        "\(sats.formatted()) sats"
    }
}
3. Bitcoin wallet service

Create BitcoinService.swift.

import Foundation

@MainActor
final class BitcoinService:
    ObservableObject {

    @Published
    private(set) var account:
        BitcoinAccount?

    @Published
    private(set) var transactions:
        [BitcoinTransaction] = []

    @Published
    var isLoading = false

    @Published
    var errorMessage:
        String?

    init() {

        account =
            BitcoinAccount(
                id: UUID(),
                name: "Bitcoin",
                address: "",
                balanceSats: 0,
                network: .testnet,
                isWatchOnly: true,
                createdAt: Date()
            )
    }

    func refresh() async {

        isLoading = true

        defer {
            isLoading = false
        }

        // Production implementation:
        //
        // 1. Query your Bitcoin backend/node.
        // 2. Retrieve UTXOs.
        // 3. Calculate confirmed balance.
        // 4. Retrieve transactions.
        // 5. Update published state.

        try? await Task.sleep(
            for: .milliseconds(400)
        )
    }

    func setDemoBalance(
        sats: UInt64
    ) {

        guard var account else {
            return
        }

        account.balanceSats = sats

        self.account = account
    }
}
4. Bitcoin portfolio screen
import SwiftUI

struct BitcoinView: View {

    @StateObject
    private var bitcoin =
        BitcoinService()

    var body: some View {

        NavigationStack {

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 22
                ) {

                    bitcoinHeader

                    portfolioCard

                    actionButtons

                    bitcoinTransactions
                }
                .padding()
            }
            .navigationTitle("Bitcoin")
            .task {

                await bitcoin.refresh()

                bitcoin.setDemoBalance(
                    sats: 125_000_000
                )
            }
        }
    }

    private var bitcoinHeader:
        some View {

        VStack(
            alignment: .leading,
            spacing: 5
        ) {

            Text("Bitcoin")
                .font(
                    .largeTitle.weight(
                        .bold
                    )
                )

            Text(
                "Bitcoin-native money"
            )
            .foregroundStyle(
                .secondary
            )
        }
    }

    private var portfolioCard:
        some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("BALANCE")
                .font(.caption)
                .fontWeight(.bold)
                .opacity(0.65)

            if let account =
                bitcoin.account {

                Text(
                    BitcoinUnits.formatBTC(
                        sats:
                            account.balanceSats
                    )
                )
                .font(
                    .system(
                        size: 34,
                        weight: .bold
                    )
                )

                Text(
                    BitcoinUnits.formatSats(
                        account.balanceSats
                    )
                )
                .font(.subheadline)
                .opacity(0.7)
            }

            HStack {

                Text("Bitcoin")

                Spacer()

                Image(
                    systemName:
                        "bitcoinsign.circle.fill"
                )
                .font(.title)
            }
        }
        .foregroundStyle(.white)
        .padding(24)
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .background(
            LinearGradient(
                colors: [
                    .black,
                    .gray
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 26
            )
        )
    }

    private var actionButtons:
        some View {

        HStack(spacing: 12) {

            NavigationLink {

                BitcoinSendView()

            } label: {

                BitcoinAction(
                    title: "Send",
                    icon:
                        "arrow.up.right"
                )
            }

            NavigationLink {

                BitcoinReceiveView()

            } label: {

                BitcoinAction(
                    title: "Receive",
                    icon:
                        "arrow.down.left"
                )
            }

            NavigationLink {

                LightningView()

            } label: {

                BitcoinAction(
                    title: "Lightning",
                    icon:
                        "bolt.fill"
                )
            }
        }
        .buttonStyle(.plain)
    }

    private var bitcoinTransactions:
        some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("Bitcoin activity")
                .font(
                    .title2.weight(
                        .bold
                    )
                )

            Text(
                "No transactions loaded."
            )
            .foregroundStyle(
                .secondary
            )
        }
    }
}
5. Bitcoin action button
struct BitcoinAction: View {

    let title: String
    let icon: String

    var body: some View {

        VStack(spacing: 8) {

            Image(systemName: icon)
                .font(.title2)

            Text(title)
                .font(.caption)
                .fontWeight(.medium)
        }
        .frame(
            maxWidth: .infinity
        )
        .padding(.vertical, 15)
        .background(
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 18
            )
        )
    }
}
6. Bitcoin send interface

The important thing here is that the UI doesn't sign transactions itself.

struct BitcoinSendView: View {

    @State private var address = ""
    @State private var sats = ""

    @State private var showingConfirmation =
        false

    var amountSats: UInt64? {
        UInt64(sats)
    }

    var body: some View {

        Form {

            Section("Recipient") {

                TextField(
                    "Bitcoin address",
                    text: $address
                )
                .textInputAutocapitalization(
                    .never
                )
                .autocorrectionDisabled()
            }

            Section("Amount") {

                TextField(
                    "Satoshis",
                    text: $sats
                )
                .keyboardType(
                    .numberPad
                )

                if let value =
                    amountSats {

                    Text(
                        BitcoinUnits.formatBTC(
                            sats: value
                        )
                    )
                    .foregroundStyle(
                        .secondary
                    )
                }
            }

            Section {

                Button(
                    "Review transaction"
                ) {

                    showingConfirmation =
                        true
                }
                .disabled(
                    address.isEmpty ||
                    amountSats == nil
                )
            }
        }
        .navigationTitle(
            "Send Bitcoin"
        )
        .sheet(
            isPresented:
                $showingConfirmation
        ) {

            BitcoinConfirmationView(
                address: address,
                sats: amountSats ?? 0
            )
        }
    }
}
7. Transaction confirmation
struct BitcoinConfirmationView:
    View {

    let address: String
    let sats: UInt64

    @Environment(\.dismiss)
    private var dismiss

    @State private var signing = false

    var body: some View {

        VStack(spacing: 25) {

            Image(
                systemName:
                    "bitcoinsign.circle"
            )
            .font(
                .system(size: 70)
            )

            Text("Confirm Bitcoin payment")
                .font(.title2)
                .fontWeight(.bold)

            Text(
                BitcoinUnits.formatBTC(
                    sats: sats
                )
            )
            .font(
                .system(
                    size: 36,
                    weight: .bold
                )
            )

            Text(address)
                .font(
                    .system(
                        size: 11,
                        design: .monospaced
                    )
                )
                .textSelection(
                    .enabled
                )
                .multilineTextAlignment(
                    .center
                )

            Spacer()

            Button {

                signTransaction()

            } label: {

                if signing {

                    ProgressView()

                } else {

                    Label(
                        "Authorize transaction",
                        systemImage:
                            "faceid"
                    )
                }
            }
            .buttonStyle(
                .borderedProminent
            )
        }
        .padding()
    }

    private func signTransaction() {

        signing = true

        // Production:
        //
        // Authenticate user.
        // Construct PSBT.
        // Ask secure signer to sign.
        // Broadcast through backend/node.

        DispatchQueue.main.asyncAfter(
            deadline:
                .now() + 1
        ) {

            signing = false
            dismiss()
        }
    }
}
8. Receive Bitcoin
struct BitcoinReceiveView:
    View {

    @State private var address =
        "tb1qexampleaddress"

    var body: some View {

        VStack(spacing: 25) {

            Text("Receive Bitcoin")
                .font(.largeTitle)
                .fontWeight(.bold)

            QRCodeView(
                value: address
            )
            .frame(
                width: 250,
                height: 250
            )

            Text(address)
                .font(
                    .system(
                        size: 12,
                        design: .monospaced
                    )
                )
                .textSelection(
                    .enabled
                )
                .multilineTextAlignment(
                    .center
                )

            Button("Copy Address") {

                UIPasteboard.general.string =
                    address
            }
            .buttonStyle(
                .borderedProminent
            )

            Spacer()
        }
        .padding()
        .navigationTitle("Receive")
    }
}
9. Lightning models

Now we add the second Bitcoin rail.

enum LightningNetwork:
    String,
    Codable {

    case mainnet
    case testnet
}

struct LightningAccount:
    Codable {

    var balanceMsats: UInt64

    var network:
        LightningNetwork

    var nodeAlias: String?

    var channelCount: Int

    var balanceSats: UInt64 {

        balanceMsats / 1_000
    }
}

struct LightningPayment:
    Identifiable,
    Codable {

    let id: UUID

    let paymentHash: String

    let amountMsats: UInt64

    let description: String

    let timestamp: Date

    let status:
        LightningPaymentStatus
}

enum LightningPaymentStatus:
    String,
    Codable {

    case pending
    case succeeded
    case failed
}
10. Lightning service
@MainActor
final class LightningService:
    ObservableObject {

    @Published
    var account =
        LightningAccount(
            balanceMsats: 0,
            network: .testnet,
            nodeAlias: "Aureom Node",
            channelCount: 0
        )

    @Published
    var payments:
        [LightningPayment] = []

    @Published
    var isProcessing = false

    func refresh() async {

        isProcessing = true

        defer {
            isProcessing = false
        }

        // Production implementation:
        //
        // Connect to your Lightning backend.
        // Retrieve node balance.
        // Retrieve invoices/payments.
        // Update channels.

        try? await Task.sleep(
            for: .milliseconds(300)
        )
    }

    func createInvoice(
        amountSats: UInt64,
        description: String
    ) async -> String {

        // Production:
        //
        // Call Lightning node/API
        // to create a BOLT11 invoice.

        return
            "lnbc\(amountSats)example"
    }

    func payInvoice(
        _ invoice: String
    ) async throws {

        isProcessing = true

        defer {
            isProcessing = false
        }

        // Production:
        //
        // Validate invoice.
        // Authenticate.
        // Route payment.
        // Monitor HTLC.
        // Record result.

        try await Task.sleep(
            for: .milliseconds(500)
        )
    }
}
11. Lightning dashboard
struct LightningView: View {

    @StateObject
    private var lightning =
        LightningService()

    var body: some View {

        ScrollView {

            VStack(
                alignment: .leading,
                spacing: 22
            ) {

                Text("Lightning")
                    .font(
                        .largeTitle.weight(
                            .bold
                        )
                    )

                balanceCard

                HStack {

                    NavigationLink {

                        LightningSendView()

                    } label: {

                        BitcoinAction(
                            title: "Pay",
                            icon:
                                "bolt.fill"
                        )
                    }

                    NavigationLink {

                        LightningReceiveView(
                            lightning:
                                lightning
                        )

                    } label: {

                        BitcoinAction(
                            title: "Invoice",
                            icon:
                                "arrow.down.left"
                        )
                    }
                }
                .buttonStyle(.plain)

                nodeCard
            }
            .padding()
        }
        .navigationTitle("Lightning")
        .task {

            await lightning.refresh()
        }
    }

    private var balanceCard:
        some View {

        VStack(
            alignment: .leading,
            spacing: 10
        ) {

            Text("LIGHTNING BALANCE")
                .font(.caption)
                .fontWeight(.bold)

            Text(
                "\(lightning.account.balanceSats.formatted()) sats"
            )
            .font(
                .system(
                    size: 34,
                    weight: .bold
                )
            )

            Text(
                "\(lightning.account.balanceMsats.formatted()) millisatoshis"
            )
            .font(.caption)
            .foregroundStyle(
                .secondary
            )
        }
        .padding()
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .background(
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 24
            )
        )
    }

    private var nodeCard:
        some View {

        VStack(
            alignment: .leading,
            spacing: 8
        ) {

            Label(
                "Lightning Network",
                systemImage:
                    "bolt.fill"
            )
            .font(.headline)

            Text(
                lightning.account.nodeAlias
                    ?? "Wallet node"
            )

            Text(
                "\(lightning.account.channelCount) channels"
            )
            .font(.caption)
            .foregroundStyle(
                .secondary
            )
        }
        .padding()
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .background(
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 24
            )
        )
    }
}
12. Lightning payment
struct LightningSendView:
    View {

    @StateObject
    private var lightning =
        LightningService()

    @State private var invoice = ""

    @State private var paying = false

    @State private var result:
        String?

    var body: some View {

        VStack(spacing: 25) {

            Image(
                systemName:
                    "bolt.circle.fill"
            )
            .font(
                .system(size: 65)
            )

            Text("Lightning Payment")
                .font(.largeTitle)
                .fontWeight(.bold)

            TextField(
                "Paste Lightning invoice",
                text: $invoice,
                axis: .vertical
            )
            .textInputAutocapitalization(
                .never
            )
            .autocorrectionDisabled()
            .padding()
            .background(
                .thinMaterial
            )
            .clipShape(
                RoundedRectangle(
                    cornerRadius: 16
                )
            )

            Button {

                Task {

                    await pay()
                }

            } label: {

                if paying {

                    ProgressView()

                } else {

                    Label(
                        "Pay Lightning Invoice",
                        systemImage:
                            "bolt.fill"
                    )
                }
            }
            .buttonStyle(
                .borderedProminent
            )
            .disabled(
                invoice.isEmpty
            )

            if let result {

                Text(result)
                    .fontWeight(.semibold)
            }

            Spacer()
        }
        .padding()
        .navigationTitle("Lightning")
    }

    private func pay() async {

        paying = true

        do {

            try await lightning.payInvoice(
                invoice
            )

            result =
                "Payment successful"

        } catch {

            result =
                "Payment failed"
        }

        paying = false
    }
}
13. Lightning receive / invoice generation
struct LightningReceiveView:
    View {

    @ObservedObject
    var lightning:
        LightningService

    @State private var amount = ""

    @State private var invoice:
        String?

    var body: some View {

        VStack(spacing: 25) {

            Text("Receive via Lightning")
                .font(.largeTitle)
                .fontWeight(.bold)

            TextField(
                "Amount in sats",
                text: $amount
            )
            .keyboardType(
                .numberPad
            )

            Button(
                "Create Invoice"
            ) {

                guard
                    let sats =
                        UInt64(amount)
                else {
                    return
                }

                Task {

                    invoice =
                        await lightning
                            .createInvoice(
                                amountSats:
                                    sats,
                                description:
                                    "Aureom Wallet"
                            )
                }
            }
            .buttonStyle(
                .borderedProminent
            )

            if let invoice {

                QRCodeView(
                    value: invoice
                )
                .frame(
                    width: 240,
                    height: 240
                )

                Text(invoice)
                    .font(
                        .system(
                            size: 10,
                            design:
                                .monospaced
                        )
                    )
                    .textSelection(
                        .enabled
                    )
            }

            Spacer()
        }
        .padding()
        .navigationTitle(
            "Receive Lightning"
        )
    }
}
14. Put BTC + Lightning into the main Wallet

Add another action to MainWalletView:

NavigationStack {

    ScrollView {

        VStack(spacing: 20) {

            NavigationLink {

                BitcoinView()

            } label: {

                CryptoAssetCard(
                    title: "Bitcoin",
                    subtitle:
                        "On-chain",
                    icon:
                        "bitcoinsign.circle.fill"
                )
            }

            NavigationLink {

                LightningView()

            } label: {

                CryptoAssetCard(
                    title: "Lightning",
                    subtitle:
                        "Instant payments",
                    icon:
                        "bolt.fill"
                )
            }
        }
        .padding()
    }
}

Component:

struct CryptoAssetCard:
    View {

    let title: String
    let subtitle: String
    let icon: String

    var body: some View {

        HStack(spacing: 16) {

            Image(systemName: icon)
                .font(.title)
                .frame(
                    width: 55,
                    height: 55
                )
                .background(
                    .thinMaterial
                )
                .clipShape(
                    RoundedRectangle(
                        cornerRadius: 16
                    )
                )

            VStack(
                alignment: .leading
            ) {

                Text(title)
                    .font(
                        .headline
                    )

                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(
                        .secondary
                    )
            }

            Spacer()

            Image(
                systemName:
                    "chevron.right"
            )
            .foregroundStyle(
                .secondary
            )
        }
        .padding()
        .background(
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 22
            )
        )
    }
}
15. C layer

I'd make the C side responsible for integer-unit validation, not Swift.

#include <stdint.h>
#include <stdbool.h>

#define SATS_PER_BTC 100000000ULL
#define MSATS_PER_SAT 1000ULL

bool btc_amount_valid(
    uint64_t sats
) {
    return sats > 0;
}

bool lightning_amount_valid(
    uint64_t msats
) {
    return msats > 0;
}

uint64_t btc_to_sats(
    uint64_t btc_whole,
    uint64_t btc_fraction
) {
    return
        btc_whole * SATS_PER_BTC
        + btc_fraction;
}

uint64_t sats_to_msats(
    uint64_t sats
) {
    return
        sats * MSATS_PER_SAT;
}

The production C layer should eventually handle things like:

PSBT
   ↓
Transaction parsing
   ↓
UTXO validation
   ↓
Fee calculation
   ↓
Output validation
   ↓
Transaction serialization
   ↓
Secure signing interface

rather than placing those responsibilities in SwiftUI.

16. Julia Bitcoin intelligence

And now the really interesting part of the original Swift + C + Julia architecture:

module BitcoinAnalytics

export sats_to_btc,
       transaction_fee_rate,
       portfolio_value,
       lightning_liquidity

const SATS_PER_BTC = 100_000_000

function sats_to_btc(sats::Integer)
    return sats / SATS_PER_BTC
end

function transaction_fee_rate(
    fee_sats::Integer,
    vbytes::Integer
)
    vbytes <= 0 && return 0.0

    return fee_sats / vbytes
end

function portfolio_value(
    btc_sats::Integer,
    btc_price::Real
)
    return sats_to_btc(btc_sats) *
           btc_price
end

function lightning_liquidity(
    local_sats::Integer,
    remote_sats::Integer
)

    total =
        local_sats +
        remote_sats

    total == 0 && return 0.0

    return local_sats / total
end

end

So the eventual dashboard can say:

AUREOM WALLET

£18,420.50
Total financial assets

────────────────────────────

BITCOIN

0.12500000 BTC
12,500,000 sats

£8,920.50

────────────────────────────

LIGHTNING

840,000 sats

12 channels
£598.20

────────────────────────────

FINANCIAL INTELLIGENCE

BTC allocation             48.4%
Lightning liquidity        9.7%
30-day BTC P/L             +£412
Average network fee        4.2 sat/vB

