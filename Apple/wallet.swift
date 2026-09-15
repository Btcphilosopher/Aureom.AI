1. SwiftUI — Wallet interface
import SwiftUI

struct WalletCard: Identifiable {
    let id = UUID()
    let name: String
    let issuer: String
    let balance: Double
    let currency: String
    let colour: Color
}

struct Transaction: Identifiable {
    let id = UUID()
    let merchant: String
    let amount: Double
    let category: String
    let date: Date
}

struct ContentView: View {

    let cards = [
        WalletCard(
            name: "Aureom Card",
            issuer: "Aureom Financial",
            balance: 4280.50,
            currency: "GBP",
            colour: .black
        ),
        WalletCard(
            name: "Travel Card",
            issuer: "Transport",
            balance: 184.20,
            currency: "GBP",
            colour: .blue
        )
    ]

    let transactions = [
        Transaction(
            merchant: "TESCO",
            amount: -42.50,
            category: "Groceries",
            date: Date()
        ),
        Transaction(
            merchant: "APPLE",
            amount: -12.99,
            category: "Technology",
            date: Date()
        ),
        Transaction(
            merchant: "TFL",
            amount: -3.20,
            category: "Transport",
            date: Date()
        )
    ]

    var body: some View {

        NavigationStack {

            ScrollView {

                VStack(alignment: .leading, spacing: 20) {

                    Text("Wallet")
                        .font(.largeTitle)
                        .fontWeight(.bold)

                    Text("£4,464.70")
                        .font(.system(size: 42, weight: .bold))

                    Text("Total available")
                        .foregroundStyle(.secondary)

                    ScrollView(.horizontal, showsIndicators: false) {

                        HStack(spacing: 16) {

                            ForEach(cards) { card in

                                VStack(alignment: .leading) {

                                    Text(card.issuer)
                                        .font(.caption)

                                    Spacer()

                                    Text(card.name)
                                        .font(.title3)
                                        .fontWeight(.bold)

                                    Text(
                                        "\(card.currency) \(card.balance, specifier: "%.2f")"
                                    )
                                    .font(.title2)

                                }
                                .padding()
                                .frame(width: 280, height: 170)
                                .background(card.colour)
                                .foregroundStyle(.white)
                                .clipShape(
                                    RoundedRectangle(cornerRadius: 24)
                                )
                            }
                        }
                    }

                    HStack {

                        WalletAction(
                            title: "Pay",
                            icon: "wave.3.right"
                        )

                        WalletAction(
                            title: "Send",
                            icon: "arrow.up.right"
                        )

                        WalletAction(
                            title: "Request",
                            icon: "arrow.down.left"
                        )

                        WalletAction(
                            title: "Add",
                            icon: "plus"
                        )
                    }

                    Text("Recent")
                        .font(.title2)
                        .fontWeight(.bold)

                    ForEach(transactions) { transaction in

                        HStack {

                            VStack(alignment: .leading) {

                                Text(transaction.merchant)
                                    .fontWeight(.semibold)

                                Text(transaction.category)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            Text(
                                "£\(abs(transaction.amount), specifier: "%.2f")"
                            )
                            .fontWeight(.semibold)
                        }
                        .padding(.vertical, 8)
                    }
                }
                .padding()
            }
            .navigationTitle("")
        }
    }
}

struct WalletAction: View {

    let title: String
    let icon: String

    var body: some View {

        VStack {

            Image(systemName: icon)
                .font(.title2)

            Text(title)
                .font(.caption)
        }
        .frame(maxWidth: .infinity)
    }
}
2. C — high-performance wallet core

I'd keep sensitive, deterministic financial logic out of the UI layer.

#ifndef WALLET_CORE_H
#define WALLET_CORE_H

#include <stdint.h>
#include <stddef.h>

typedef struct {

    uint64_t wallet_id;

    double balance;

    uint64_t transaction_count;

} Wallet;

typedef struct {

    uint64_t transaction_id;

    double amount;

    uint64_t timestamp;

    uint32_t merchant_id;

} WalletTransaction;


/*
 * Initialise wallet.
 */
void wallet_init(
    Wallet *wallet,
    uint64_t wallet_id,
    double starting_balance
);


/*
 * Deposit funds.
 */
int wallet_deposit(
    Wallet *wallet,
    double amount
);


/*
 * Spend funds.
 */
int wallet_spend(
    Wallet *wallet,
    double amount
);


/*
 * Return current balance.
 */
double wallet_balance(
    const Wallet *wallet
);


/*
 * Basic transaction validation.
 */
int wallet_validate_transaction(
    const Wallet *wallet,
    double amount
);

#endif

Implementation:

#include "wallet_core.h"

#include <math.h>

void wallet_init(
    Wallet *wallet,
    uint64_t wallet_id,
    double starting_balance
) {
    if (!wallet)
        return;

    wallet->wallet_id = wallet_id;
    wallet->balance = starting_balance;
    wallet->transaction_count = 0;
}

int wallet_validate_transaction(
    const Wallet *wallet,
    double amount
) {

    if (!wallet)
        return 0;

    if (!isfinite(amount))
        return 0;

    if (amount <= 0.0)
        return 0;

    if (amount > wallet->balance)
        return 0;

    return 1;
}

int wallet_deposit(
    Wallet *wallet,
    double amount
) {

    if (!wallet)
        return 0;

    if (!isfinite(amount) || amount <= 0)
        return 0;

    wallet->balance += amount;
    wallet->transaction_count++;

    return 1;
}

int wallet_spend(
    Wallet *wallet,
    double amount
) {

    if (!wallet_validate_transaction(wallet, amount))
        return 0;

    wallet->balance -= amount;
    wallet->transaction_count++;

    return 1;
}

double wallet_balance(
    const Wallet *wallet
) {

    if (!wallet)
        return 0.0;

    return wallet->balance;
}
3. Swift ↔ C bridge

Create a bridging header:

#include "wallet_core.h"

Then Swift can use the C engine:

final class WalletEngine: ObservableObject {

    private var wallet = Wallet()

    @Published var balance: Double = 0

    init() {

        wallet_init(
            &wallet,
            10001,
            5000.00
        )

        refresh()
    }

    func spend(_ amount: Double) {

        if wallet_spend(&wallet, amount) != 0 {
            refresh()
        }
    }

    func deposit(_ amount: Double) {

        if wallet_deposit(&wallet, amount) != 0 {
            refresh()
        }
    }

    private func refresh() {

        balance = wallet_balance(&wallet)
    }
}

That gives you a genuine architecture rather than simply putting everything in Swift.

4. Julia — financial intelligence engine

Julia can sit behind the wallet and analyse transaction history.

module WalletAnalytics

export monthly_spend,
       category_totals,
       average_transaction,
       projected_monthly_spend,
       savings_rate

function monthly_spend(transactions)

    total = 0.0

    for t in transactions
        if t < 0
            total += abs(t)
        end
    end

    return total
end


function category_totals(categories, amounts)

    totals = Dict{String,Float64}()

    for i in eachindex(categories)

        category = categories[i]
        amount = abs(amounts[i])

        if !haskey(totals, category)
            totals[category] = 0.0
        end

        totals[category] += amount
    end

    return totals
end


function average_transaction(transactions)

    if isempty(transactions)
        return 0.0
    end

    return mean(abs.(transactions))
end


function projected_monthly_spend(
    current_spend,
    days_elapsed
)

    if days_elapsed <= 0
        return 0.0
    end

    daily_rate = current_spend / days_elapsed

    return daily_rate * 30
end


function savings_rate(
    income,
    spending
)

    if income <= 0
        return 0.0
    end

    return (income - spending) / income
end

end

You could then give the Wallet a financial intelligence layer:

using Statistics
using .WalletAnalytics

transactions = [
    -42.50,
    -12.99,
    -3.20,
    -84.00,
    -17.50,
    -25.00
]

categories = [
    "Groceries",
    "Technology",
    "Transport",
    "Groceries",
    "Transport",
    "Entertainment"
]

println(
    "Monthly spend: ",
    monthly_spend(transactions)
)

println(
    "Average transaction: ",
    average_transaction(transactions)
)

println(
    "Projected monthly spend: ",
    projected_monthly_spend(
        monthly_spend(transactions),
        15
    )
)

println(
    "Category breakdown:"
)

println(
    category_totals(
        categories,
        transactions
    )
)





1. Core Swift models
import Foundation

enum WalletItemType: String, Codable {
    case paymentCard
    case bankAccount
    case transit
    case ticket
    case loyalty
    case identity
    case key
}

enum TransactionCategory: String, Codable {
    case groceries
    case transport
    case entertainment
    case technology
    case restaurants
    case shopping
    case utilities
    case income
    case other
}

struct WalletItem: Identifiable, Codable {
    let id: UUID
    var name: String
    var issuer: String
    var type: WalletItemType
    var lastFour: String?
    var balance: Double?
    var currency: String
    var isDefault: Bool

    init(
        name: String,
        issuer: String,
        type: WalletItemType,
        lastFour: String? = nil,
        balance: Double? = nil,
        currency: String = "GBP",
        isDefault: Bool = false
    ) {
        self.id = UUID()
        self.name = name
        self.issuer = issuer
        self.type = type
        self.lastFour = lastFour
        self.balance = balance
        self.currency = currency
        self.isDefault = isDefault
    }
}

struct WalletTransaction: Identifiable, Codable {
    let id: UUID
    let merchant: String
    let amount: Double
    let currency: String
    let category: TransactionCategory
    let date: Date
    let cardID: UUID?

    init(
        merchant: String,
        amount: Double,
        currency: String = "GBP",
        category: TransactionCategory,
        date: Date = Date(),
        cardID: UUID? = nil
    ) {
        self.id = UUID()
        self.merchant = merchant
        self.amount = amount
        self.currency = currency
        self.category = category
        self.date = date
        self.cardID = cardID
    }
}
2. Wallet store

This becomes the central Swift data layer.

@MainActor
final class WalletStore: ObservableObject {

    @Published var items: [WalletItem] = []
    @Published var transactions: [WalletTransaction] = []

    init() {
        loadDemoData()
    }

    var totalBalance: Double {
        items
            .compactMap { $0.balance }
            .reduce(0, +)
    }

    var defaultCard: WalletItem? {
        items.first {
            $0.type == .paymentCard &&
            $0.isDefault
        }
    }

    func addItem(_ item: WalletItem) {
        items.append(item)
    }

    func removeItem(_ item: WalletItem) {
        items.removeAll {
            $0.id == item.id
        }
    }

    func addTransaction(
        merchant: String,
        amount: Double,
        category: TransactionCategory,
        cardID: UUID? = nil
    ) {

        let transaction = WalletTransaction(
            merchant: merchant,
            amount: amount,
            category: category,
            cardID: cardID
        )

        transactions.insert(
            transaction,
            at: 0
        )
    }

    func loadDemoData() {

        let card = WalletItem(
            name: "Aureom Card",
            issuer: "Aureom Financial",
            type: .paymentCard,
            lastFour: "4821",
            balance: 4280.50,
            isDefault: true
        )

        let travel = WalletItem(
            name: "Transport Card",
            issuer: "Transit",
            type: .transit,
            balance: 184.20
        )

        let ticket = WalletItem(
            name: "London Concert",
            issuer: "Events",
            type: .ticket
        )

        items = [
            card,
            travel,
            ticket
        ]

        transactions = [

            WalletTransaction(
                merchant: "TESCO",
                amount: -42.50,
                category: .groceries,
                date: Date()
            ),

            WalletTransaction(
                merchant: "APPLE",
                amount: -12.99,
                category: .technology,
                date: Date().addingTimeInterval(-3600)
            ),

            WalletTransaction(
                merchant: "TFL",
                amount: -3.20,
                category: .transport,
                date: Date().addingTimeInterval(-7200)
            ),

            WalletTransaction(
                merchant: "UBER",
                amount: -18.40,
                category: .transport,
                date: Date().addingTimeInterval(-86400)
            )
        ]
    }
}
3. Main Wallet screen

Now we can make it feel much closer to a real modern financial app.

struct WalletHomeView: View {

    @StateObject private var wallet =
        WalletStore()

    @State private var showingAdd = false

    var body: some View {

        NavigationStack {

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 24
                ) {

                    header

                    balanceCard

                    quickActions

                    cardsSection

                    intelligenceSection

                    transactionsSection
                }
                .padding()
            }
            .navigationBarHidden(true)
            .sheet(
                isPresented: $showingAdd
            ) {
                AddWalletItemView(
                    wallet: wallet
                )
            }
        }
    }

    private var header: some View {

        HStack {

            VStack(
                alignment: .leading,
                spacing: 4
            ) {

                Text("Wallet")
                    .font(
                        .system(
                            size: 36,
                            weight: .bold
                        )
                    )

                Text("Your financial world")
                    .foregroundStyle(
                        .secondary
                    )
            }

            Spacer()

            Button {

                showingAdd = true

            } label: {

                Image(
                    systemName: "plus"
                )
                .font(.title2)
                .frame(
                    width: 44,
                    height: 44
                )
                .background(
                    .thinMaterial
                )
                .clipShape(
                    Circle()
                )
            }
        }
    }

    private var balanceCard: some View {

        VStack(
            alignment: .leading,
            spacing: 10
        ) {

            Text("TOTAL BALANCE")
                .font(.caption)
                .fontWeight(.bold)
                .opacity(0.7)

            Text(
                "£\(wallet.totalBalance, specifier: "%.2f")"
            )
            .font(
                .system(
                    size: 42,
                    weight: .bold
                )
            )

            HStack {

                Image(
                    systemName:
                        "arrow.up.right"
                )

                Text(
                    "+4.8% this month"
                )
            }
            .font(.subheadline)
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
                cornerRadius: 28
            )
        )
    }

    private var quickActions: some View {

        HStack(spacing: 12) {

            QuickAction(
                title: "Pay",
                icon: "wave.3.right"
            )

            QuickAction(
                title: "Send",
                icon: "arrow.up.right"
            )

            QuickAction(
                title: "Request",
                icon: "arrow.down.left"
            )

            QuickAction(
                title: "Scan",
                icon: "qrcode.viewfinder"
            )
        }
    }

    private var cardsSection: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            SectionTitle(
                title: "Cards & Passes"
            )

            ForEach(wallet.items) {
                item in

                WalletItemRow(
                    item: item
                )
            }
        }
    }

    private var intelligenceSection: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            SectionTitle(
                title: "Wallet Intelligence"
            )

            HStack {

                Image(
                    systemName:
                        "chart.line.uptrend.xyaxis"
                )
                .font(.title)

                VStack(
                    alignment: .leading
                ) {

                    Text(
                        "Projected monthly spend"
                    )
                    .fontWeight(.semibold)

                    Text("£1,842")
                        .font(.title2)
                        .fontWeight(.bold)

                    Text(
                        "8% below your current trend"
                    )
                    .font(.caption)
                    .foregroundStyle(
                        .secondary
                    )
                }

                Spacer()
            }
            .padding()
            .background(
                .thinMaterial
            )
            .clipShape(
                RoundedRectangle(
                    cornerRadius: 20
                )
            )
        }
    }

    private var transactionsSection: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            SectionTitle(
                title: "Recent Transactions"
            )

            ForEach(
                wallet.transactions
            ) { transaction in

                TransactionRow(
                    transaction:
                        transaction
                )
            }
        }
    }
}
4. Reusable SwiftUI components
struct QuickAction: View {

    let title: String
    let icon: String

    var body: some View {

        VStack(spacing: 8) {

            Image(systemName: icon)
                .font(.title3)

            Text(title)
                .font(.caption)
        }
        .frame(
            maxWidth: .infinity
        )
        .padding(.vertical, 14)
        .background(
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 16
            )
        )
    }
}
struct SectionTitle: View {

    let title: String

    var body: some View {

        Text(title)
            .font(.title2)
            .fontWeight(.bold)
    }
}
struct WalletItemRow: View {

    let item: WalletItem

    var body: some View {

        HStack(spacing: 16) {

            Image(
                systemName:
                    iconForItem
            )
            .font(.title2)
            .frame(
                width: 48,
                height: 48
            )
            .background(
                .quaternary
            )
            .clipShape(
                RoundedRectangle(
                    cornerRadius: 14
                )
            )

            VStack(
                alignment: .leading,
                spacing: 4
            ) {

                Text(item.name)
                    .fontWeight(.semibold)

                Text(item.issuer)
                    .font(.caption)
                    .foregroundStyle(
                        .secondary
                    )

                if let lastFour =
                    item.lastFour {

                    Text("•••• \(lastFour)")
                        .font(.caption)
                        .foregroundStyle(
                            .secondary
                        )
                }
            }

            Spacer()

            if let balance =
                item.balance {

                Text(
                    "£\(balance, specifier: "%.2f")"
                )
                .fontWeight(.semibold)
            }

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
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 18
            )
        )
    }

    private var iconForItem: String {

        switch item.type {

        case .paymentCard:
            return "creditcard"

        case .bankAccount:
            return "building.columns"

        case .transit:
            return "tram"

        case .ticket:
            return "ticket"

        case .loyalty:
            return "star"

        case .identity:
            return "person.text.rectangle"

        case .key:
            return "key"
        }
    }
}
5. Transaction UI
struct TransactionRow: View {

    let transaction:
        WalletTransaction

    var body: some View {

        HStack(spacing: 14) {

            Image(
                systemName:
                    categoryIcon
            )
            .frame(
                width: 44,
                height: 44
            )
            .background(
                .quaternary
            )
            .clipShape(
                Circle()
            )

            VStack(
                alignment: .leading,
                spacing: 3
            ) {

                Text(
                    transaction.merchant
                )
                .fontWeight(.semibold)

                Text(
                    transaction.category
                        .rawValue
                        .capitalized
                )
                .font(.caption)
                .foregroundStyle(
                    .secondary
                )
            }

            Spacer()

            VStack(
                alignment: .trailing
            ) {

                Text(
                    "£\(abs(transaction.amount), specifier: "%.2f")"
                )
                .fontWeight(.semibold)

                Text(
                    transaction.date,
                    style: .time
                )
                .font(.caption)
                .foregroundStyle(
                    .secondary
                )
            }
        }
        .padding(.vertical, 6)
    }

    private var categoryIcon: String {

        switch transaction.category {

        case .groceries:
            return "cart"

        case .transport:
            return "car"

        case .entertainment:
            return "play"

        case .technology:
            return "desktopcomputer"

        case .restaurants:
            return "fork.knife"

        case .shopping:
            return "bag"

        case .utilities:
            return "bolt"

        case .income:
            return "arrow.down"

        case .other:
            return "circle"
        }
    }
}
6. Add-card/pass interface
struct AddWalletItemView: View {

    @Environment(\.dismiss)
    private var dismiss

    @ObservedObject var wallet:
        WalletStore

    @State private var name = ""
    @State private var issuer = ""

    var body: some View {

        NavigationStack {

            Form {

                Section("Wallet item") {

                    TextField(
                        "Name",
                        text: $name
                    )

                    TextField(
                        "Issuer",
                        text: $issuer
                    )
                }

                Section {

                    Button("Add") {

                        let item =
                            WalletItem(
                                name: name,
                                issuer: issuer,
                                type: .paymentCard
                            )

                        wallet.addItem(item)

                        dismiss()
                    }
                    .disabled(
                        name.isEmpty ||
                        issuer.isEmpty
                    )
                }
            }
            .navigationTitle(
                "Add to Wallet"
            )
        }
    }
}
7. A more advanced payment engine

We can now separate what the UI displays from what actually happens during a payment.

enum PaymentStatus {
    case ready
    case authenticating
    case approved
    case declined
}

@MainActor
final class PaymentEngine:
    ObservableObject {

    @Published
    var status:
        PaymentStatus = .ready

    @Published
    var lastAmount: Double = 0

    func preparePayment(
        amount: Double
    ) {

        guard amount > 0 else {
            status = .declined
            return
        }

        lastAmount = amount

        status =
            .authenticating
    }

    func completePayment(
        approved: Bool
    ) {

        status =
            approved
            ? .approved
            : .declined
    }

    func reset() {

        status = .ready
        lastAmount = 0
    }
}

Then the UI could display:

struct PaymentSheet: View {

    @StateObject
    private var engine =
        PaymentEngine()

    @State private var amount = ""

    var body: some View {

        VStack(spacing: 30) {

            Text("Pay")
                .font(.largeTitle)
                .fontWeight(.bold)

            TextField(
                "Amount",
                text: $amount
            )
            .keyboardType(
                .decimalPad
            )
            .font(.system(size: 48))
            .multilineTextAlignment(
                .center
            )

            Button {

                if let value =
                    Double(amount) {

                    engine.preparePayment(
                        amount: value
                    )
                }

            } label: {

                Text("Continue")
                    .fontWeight(.bold)
                    .frame(
                        maxWidth: .infinity
                    )
                    .padding()
                    .background(
                        .black
                    )
                    .foregroundStyle(
                        .white
                    )
                    .clipShape(
                        Capsule()
                    )
            }

            statusView
        }
        .padding()
    }

    @ViewBuilder
    private var statusView: some View {

        switch engine.status {

        case .ready:
            Text("Ready")

        case .authenticating:
            ProgressView(
                "Authenticating…"
            )

        case .approved:
            Label(
                "Payment approved",
                systemImage:
                    "checkmark.circle.fill"
            )

        case .declined:
            Label(
                "Payment declined",
                systemImage:
                    "xmark.circle.fill"
            )
        }
    }
}






AureomWalletApp.swift
import SwiftUI

@main
struct AureomWalletApp: App {

    @StateObject private var wallet =
        WalletStore()

    var body: some Scene {

        WindowGroup {

            MainWalletView()
                .environmentObject(wallet)
        }
    }
}
MainWalletView.swift
import SwiftUI

struct MainWalletView: View {

    @State private var selectedTab = 0

    var body: some View {

        TabView(selection: $selectedTab) {

            WalletHomeView()
                .tabItem {
                    Label(
                        "Wallet",
                        systemImage: "wallet.pass"
                    )
                }
                .tag(0)

            PaymentView()
                .tabItem {
                    Label(
                        "Pay",
                        systemImage: "wave.3.right"
                    )
                }
                .tag(1)

            TransactionsView()
                .tabItem {
                    Label(
                        "Activity",
                        systemImage: "list.bullet.rectangle"
                    )
                }
                .tag(2)

            IntelligenceView()
                .tabItem {
                    Label(
                        "Intelligence",
                        systemImage:
                            "chart.line.uptrend.xyaxis"
                    )
                }
                .tag(3)

            MoreWalletView()
                .tabItem {
                    Label(
                        "More",
                        systemImage: "ellipsis"
                    )
                }
                .tag(4)
        }
    }
}
Animated Wallet card
import SwiftUI

struct WalletCardView: View {

    let item: WalletItem
    let index: Int

    @State private var pressed = false

    var body: some View {

        ZStack {

            RoundedRectangle(
                cornerRadius: 28
            )
            .fill(
                LinearGradient(
                    colors: [
                        .black,
                        .gray.opacity(0.75)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )

            VStack(
                alignment: .leading
            ) {

                HStack {

                    Text(item.issuer.uppercased())
                        .font(
                            .caption.weight(.bold)
                        )
                        .tracking(2)

                    Spacer()

                    Image(
                        systemName:
                            "wave.3.right"
                    )
                    .font(.title2)
                }

                Spacer()

                Text(item.name)
                    .font(.title2.weight(.semibold))

                if let lastFour = item.lastFour {

                    Text("••••  ••••  ••••  \(lastFour)")
                        .font(.system(
                            size: 17,
                            weight: .medium,
                            design: .monospaced
                        ))
                        .tracking(2)
                        .padding(.top, 4)
                }

                HStack {

                    VStack(alignment: .leading) {

                        Text("BALANCE")
                            .font(.system(size: 9))
                            .opacity(0.65)

                        if let balance = item.balance {

                            Text(
                                "£\(balance, specifier: "%.2f")"
                            )
                            .font(.headline)
                        }
                    }

                    Spacer()

                    Image(systemName: "contactless")
                        .font(.largeTitle)
                }
            }
            .foregroundStyle(.white)
            .padding(24)
        }
        .frame(height: 205)
        .scaleEffect(pressed ? 0.97 : 1)
        .rotation3DEffect(
            .degrees(Double(index) * 0.4),
            axis: (x: 0, y: 1, z: 0)
        )
        .shadow(
            radius: 15,
            y: 8
        )
        .onLongPressGesture(
            minimumDuration: 0.05
        ) {

            withAnimation(.spring) {
                pressed.toggle()
            }
        }
    }
}
Wallet card carousel
struct CardCarouselView: View {

    @EnvironmentObject
    private var wallet: WalletStore

    var body: some View {

        TabView {

            ForEach(
                Array(wallet.items.enumerated()),
                id: \.element.id
            ) { index, item in

                WalletCardView(
                    item: item,
                    index: index
                )
                .padding(.horizontal, 20)
            }
        }
        .frame(height: 235)
        .tabViewStyle(
            .page(indexDisplayMode: .automatic)
        )
    }
}

Then replace the cards section in the home screen with:

CardCarouselView()
    .environmentObject(wallet)
Passes

The Wallet should not just contain bank cards.

struct PassesView: View {

    @EnvironmentObject
    private var wallet: WalletStore

    var passes: [WalletItem] {
        wallet.items.filter {
            $0.type == .ticket ||
            $0.type == .transit ||
            $0.type == .loyalty
        }
    }

    var body: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("Passes")
                .font(.title2.weight(.bold))

            ForEach(passes) { pass in

                PassRow(pass: pass)
            }
        }
    }
}
struct PassRow: View {

    let pass: WalletItem

    var body: some View {

        HStack(spacing: 15) {

            Image(
                systemName:
                    pass.type == .transit
                    ? "tram"
                    : "ticket"
            )
            .font(.title2)
            .frame(
                width: 50,
                height: 50
            )
            .background(.thinMaterial)
            .clipShape(
                RoundedRectangle(
                    cornerRadius: 15
                )
            )

            VStack(
                alignment: .leading
            ) {

                Text(pass.name)
                    .fontWeight(.semibold)

                Text(pass.issuer)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Image(
                systemName:
                    "chevron.right"
            )
            .foregroundStyle(.secondary)
        }
        .padding()
        .background(
            RoundedRectangle(
                cornerRadius: 20
            )
            .fill(.regularMaterial)
        )
    }
}
Activity search
struct TransactionsView: View {

    @EnvironmentObject
    private var wallet: WalletStore

    @State private var searchText = ""

    var filteredTransactions: [WalletTransaction] {

        if searchText.isEmpty {
            return wallet.transactions
        }

        return wallet.transactions.filter {

            $0.merchant.localizedCaseInsensitiveContains(
                searchText
            )
            ||
            $0.category.rawValue
                .localizedCaseInsensitiveContains(
                    searchText
                )
        }
    }

    var body: some View {

        NavigationStack {

            List(filteredTransactions) { transaction in

                TransactionRow(
                    transaction: transaction
                )
            }
            .navigationTitle("Activity")
            .searchable(
                text: $searchText,
                prompt: "Search transactions"
            )
        }
    }
}
Payment screen

Now we give the application its central interaction.

struct PaymentView: View {

    @StateObject
    private var payment =
        PaymentEngine()

    @State private var amount = ""

    var body: some View {

        NavigationStack {

            VStack(spacing: 30) {

                Spacer()

                Text("Ready to Pay")
                    .font(.title2)
                    .foregroundStyle(.secondary)

                Text(
                    amount.isEmpty
                    ? "£0.00"
                    : "£\(amount)"
                )
                .font(
                    .system(
                        size: 52,
                        weight: .bold
                    )
                )

                TextField(
                    "Amount",
                    text: $amount
                )
                .keyboardType(.decimalPad)
                .multilineTextAlignment(.center)
                .font(.title)

                Spacer()

                Button {

                    guard
                        let value = Double(amount)
                    else {
                        return
                    }

                    payment.preparePayment(
                        amount: value
                    )

                } label: {

                    HStack {

                        Image(
                            systemName:
                                "wave.3.right"
                        )

                        Text("Tap to Pay")
                            .fontWeight(.bold)
                    }
                    .frame(
                        maxWidth: .infinity
                    )
                    .padding()
                    .background(.black)
                    .foregroundStyle(.white)
                    .clipShape(
                        Capsule()
                    )
                }

                paymentStatus
            }
            .padding()
            .navigationTitle("Pay")
        }
    }

    @ViewBuilder
    private var paymentStatus: some View {

        switch payment.status {

        case .ready:
            Text("Choose an amount")

        case .authenticating:
            ProgressView(
                "Authenticating payment…"
            )

        case .approved:
            Label(
                "Payment approved",
                systemImage:
                    "checkmark.circle.fill"
            )

        case .declined:
            Label(
                "Payment declined",
                systemImage:
                    "xmark.circle.fill"
            )
        }
    }
}
Julia-powered Intelligence screen

This is where the project becomes more interesting than a normal Wallet clone.

struct IntelligenceView: View {

    @EnvironmentObject
    private var wallet: WalletStore

    var spending: Double {

        wallet.transactions
            .filter { $0.amount < 0 }
            .reduce(0) {
                $0 + abs($1.amount)
            }
    }

    var body: some View {

        NavigationStack {

            ScrollView {

                VStack(
                    alignment: .leading,
                    spacing: 20
                ) {

                    Text("Financial Intelligence")
                        .font(
                            .largeTitle.weight(.bold)
                        )

                    forecastCard

                    spendingCard

                    categoryCard
                }
                .padding()
            }
            .navigationTitle("Intelligence")
        }
    }

    private var forecastCard: some View {

        VStack(
            alignment: .leading,
            spacing: 10
        ) {

            Label(
                "FORECAST",
                systemImage:
                    "sparkles"
            )
            .font(.caption.weight(.bold))

            Text("Projected monthly spending")
                .font(.headline)

            Text(
                "£\(spending * 2.1, specifier: "%.0f")"
            )
            .font(
                .system(
                    size: 36,
                    weight: .bold
                )
            )

            Text(
                "Generated by the financial analytics engine"
            )
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding()
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .background(.thinMaterial)
        .clipShape(
            RoundedRectangle(
                cornerRadius: 24
            )
        )
    }

    private var spendingCard: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("This period")
                .font(.headline)

            Text(
                "£\(spending, specifier: "%.2f")"
            )
            .font(.title)
            .fontWeight(.bold)

            ProgressView(
                value: min(
                    spending / 2000,
                    1
                )
            )

            Text("Budget utilisation")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .background(.thinMaterial)
        .clipShape(
            RoundedRectangle(
                cornerRadius: 24
            )
        )
    }

    private var categoryCard: some View {

        VStack(
            alignment: .leading,
            spacing: 12
        ) {

            Text("Spending by category")
                .font(.headline)

            ForEach(
                TransactionCategory.allCases,
                id: \.self
            ) { category in

                let value =
                    wallet.transactions
                    .filter {
                        $0.category == category &&
                        $0.amount < 0
                    }
                    .reduce(0) {
                        $0 + abs($1.amount)
                    }

                if value > 0 {

                    HStack {

                        Text(
                            category.rawValue
                                .capitalized
                        )

                        Spacer()

                        Text(
                            "£\(value, specifier: "%.2f")"
                        )
                    }
                }
            }
        }
        .padding()
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .background(.thinMaterial)
        .clipShape(
            RoundedRectangle(
                cornerRadius: 24
            )
        )
    }
}

Add this to the enum:

extension TransactionCategory: CaseIterable {}
More / identity / settings
struct MoreWalletView: View {

    var body: some View {

        NavigationStack {

            List {

                Section("Identity") {

                    NavigationLink {

                        IdentityView()

                    } label: {

                        Label(
                            "Digital Identity",
                            systemImage:
                                "person.text.rectangle"
                        )
                    }

                    NavigationLink {

                        KeysView()

                    } label: {

                        Label(
                            "Digital Keys",
                            systemImage: "key"
                        )
                    }
                }

                Section("Wallet") {

                    Label(
                        "Default Payment Card",
                        systemImage:
                            "creditcard"
                    )

                    Label(
                        "Security",
                        systemImage:
                            "faceid"
                    )

                    Label(
                        "Notifications",
                        systemImage:
                            "bell"
                    )
                }

                Section("System") {

                    Label(
                        "Wallet Data",
                        systemImage:
                            "externaldrive"
                    )

                    Label(
                        "Connected Services",
                        systemImage:
                            "link"
                    )
                }
            }
            .navigationTitle("More")
        }
    }
}

And the identity screen:

struct IdentityView: View {

    var body: some View {

        VStack(spacing: 25) {

            Image(
                systemName:
                    "person.crop.circle"
            )
            .font(.system(size: 100))

            Text("Digital Identity")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text(
                "Secure credentials and verified identity documents can live here."
            )
            .multilineTextAlignment(.center)
            .foregroundStyle(.secondary)

            Button("Present Identity") {

                // Secure identity presentation
                // would connect to the appropriate
                // Apple identity APIs/backend.
            }
            .buttonStyle(.borderedProminent)

            Spacer()
        }
        .padding()
        .navigationTitle("Identity")
    }
}
struct KeysView: View {

    var body: some View {

        List {

            Label(
                "Home",
                systemImage: "house"
            )

            Label(
                "Car",
                systemImage: "car"
            )

            Label(
                "Office",
                systemImage: "building.2"
            )
        }
        .navigationTitle("Digital Keys")
    }
}
One important correction

For the production version, don't put actual card numbers, private keys, authentication secrets, or payment credentials into ordinary Swift model objects or UserDefaults.

The next layer should therefore be:

                    SwiftUI
                       │
                  ViewModels
                       │
                 Wallet Services
                       │
          ┌────────────┼────────────┐
          │            │            │
      SecureStore   PaymentAPI   PassKit
          │            │            │
       Keychain       Backend      Apple
          │
       C Core
          │
    ┌─────┴─────┐
    │           │
Transaction   Crypto/
 Engine       Validation
    │
    └──────────────┐
                   │
                Julia
                   │
       Financial Intelligence
       
       
       
       
       
       
1. Secure storage with Keychain

Create SecureStore.swift:

import Foundation
import Security

final class SecureStore {

    static let shared = SecureStore()

    private init() {}

    @discardableResult
    func save(
        _ value: String,
        key: String
    ) -> Bool {

        guard let data =
            value.data(using: .utf8)
        else {
            return false
        }

        let query: [String: Any] = [

            kSecClass as String:
                kSecClassGenericPassword,

            kSecAttrAccount as String:
                key,

            kSecValueData as String:
                data,

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

        return status == errSecSuccess
    }

    func read(
        key: String
    ) -> String? {

        let query: [String: Any] = [

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
            AnyObject?

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
            return nil
        }

        return String(
            data: data,
            encoding: .utf8
        )
    }

    @discardableResult
    func delete(
        key: String
    ) -> Bool {

        let query: [String: Any] = [

            kSecClass as String:
                kSecClassGenericPassword,

            kSecAttrAccount as String:
                key
        ]

        let status =
            SecItemDelete(
                query as CFDictionary
            )

        return
            status == errSecSuccess ||
            status == errSecItemNotFound
    }
}
2. Biometric authentication

Create AuthenticationService.swift.

import LocalAuthentication

@MainActor
final class AuthenticationService:
    ObservableObject {

    @Published
    var authenticated = false

    @Published
    var errorMessage:
        String?

    func authenticate() async {

        let context =
            LAContext()

        var error:
            NSError?

        guard context.canEvaluatePolicy(
            .deviceOwnerAuthenticationWithBiometrics,
            error: &error
        ) else {

            errorMessage =
                "Biometric authentication unavailable."

            return
        }

        do {

            let success =
                try await context.evaluatePolicy(
                    .deviceOwnerAuthenticationWithBiometrics,
                    localizedReason:
                        "Authenticate to access your wallet."
                )

            authenticated = success

        } catch {

            authenticated = false

            errorMessage =
                error.localizedDescription
        }
    }
}
3. Lock the Wallet

Now put authentication around the actual application.

struct LockedWalletView: View {

    @StateObject
    private var auth =
        AuthenticationService()

    var body: some View {

        Group {

            if auth.authenticated {

                MainWalletView()

            } else {

                lockScreen
            }
        }
        .task {

            await auth.authenticate()
        }
    }

    private var lockScreen: some View {

        VStack(spacing: 25) {

            Image(
                systemName:
                    "wallet.pass"
            )
            .font(
                .system(size: 80)
            )

            Text("Aureom Wallet")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text(
                "Authenticate to continue"
            )
            .foregroundStyle(
                .secondary
            )

            Button {

                Task {
                    await auth.authenticate()
                }

            } label: {

                Label(
                    "Unlock Wallet",
                    systemImage: "faceid"
                )
                .fontWeight(.semibold)
            }
            .buttonStyle(
                .borderedProminent
            )
        }
        .padding()
    }
}

Then your app becomes:

@main
struct AureomWalletApp: App {

    @StateObject
    private var wallet =
        WalletStore()

    var body: some Scene {

        WindowGroup {

            LockedWalletView()
                .environmentObject(wallet)
        }
    }
}
4. Card detail screen

Now tapping a card can open a proper detail interface.

struct CardDetailView: View {

    let card: WalletItem

    @Environment(\.dismiss)
    private var dismiss

    var body: some View {

        ScrollView {

            VStack(
                alignment: .leading,
                spacing: 24
            ) {

                WalletCardView(
                    item: card,
                    index: 0
                )
                .padding(.horizontal)

                VStack(
                    alignment: .leading,
                    spacing: 16
                ) {

                    Text("Card information")
                        .font(.title2)
                        .fontWeight(.bold)

                    DetailRow(
                        title: "Issuer",
                        value: card.issuer
                    )

                    if let lastFour =
                        card.lastFour {

                        DetailRow(
                            title: "Card number",
                            value:
                                "•••• \(lastFour)"
                        )
                    }

                    DetailRow(
                        title: "Currency",
                        value: card.currency
                    )

                    DetailRow(
                        title: "Status",
                        value: "Active"
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

                Button {

                    // Connect to payment
                    // management backend.

                } label: {

                    Label(
                        "Manage Card",
                        systemImage:
                            "creditcard"
                    )
                    .frame(
                        maxWidth: .infinity
                    )
                }
                .buttonStyle(
                    .borderedProminent
                )

                Button(
                    role: .destructive
                ) {

                    // Freeze card.

                } label: {

                    Label(
                        "Freeze Card",
                        systemImage:
                            "snowflake"
                    )
                    .frame(
                        maxWidth: .infinity
                    )
                }
                .buttonStyle(
                    .bordered
                )
            }
            .padding(.vertical)
        }
        .navigationTitle(card.name)
        .navigationBarTitleDisplayMode(
            .inline
        )
    }
}

Supporting row:

struct DetailRow: View {

    let title: String
    let value: String

    var body: some View {

        HStack {

            Text(title)
                .foregroundStyle(
                    .secondary
                )

            Spacer()

            Text(value)
                .fontWeight(.medium)
        }
    }
}
5. Make cards clickable

Change the carousel to:

struct CardCarouselView: View {

    @EnvironmentObject
    private var wallet: WalletStore

    var body: some View {

        TabView {

            ForEach(
                Array(
                    wallet.items
                        .enumerated()
                ),
                id: \.element.id
            ) { index, item in

                NavigationLink {

                    CardDetailView(
                        card: item
                    )

                } label: {

                    WalletCardView(
                        item: item,
                        index: index
                    )
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 20)
            }
        }
        .frame(height: 235)
        .tabViewStyle(
            .page(
                indexDisplayMode: .automatic
            )
        )
    }
}
6. QR / barcode pass

For tickets and loyalty cards, we can generate a local representation.

import CoreImage.CIFilterBuiltins

struct QRCodeView: View {

    let value: String

    var body: some View {

        if let image =
            generateQRCode(
                from: value
            ) {

            Image(
                uiImage: image
            )
            .interpolation(.none)
            .resizable()
            .scaledToFit()
        }
    }

    private func generateQRCode(
        from value: String
    ) -> UIImage? {

        let context =
            CIContext()

        let filter =
            CIFilter.qrCodeGenerator()

        filter.message =
            Data(
                value.utf8
            )

        guard
            let output =
                filter.outputImage
        else {
            return nil
        }

        let scaled =
            output.transformed(
                by:
                    CGAffineTransform(
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

Pass screen:

struct TicketView: View {

    let ticket: WalletItem

    var body: some View {

        VStack(spacing: 25) {

            Image(
                systemName: "ticket"
            )
            .font(.system(size: 55))

            Text(ticket.name)
                .font(.largeTitle)
                .fontWeight(.bold)

            Text(ticket.issuer)
                .foregroundStyle(
                    .secondary
                )

            QRCodeView(
                value:
                    ticket.id.uuidString
            )
            .frame(
                width: 230,
                height: 230
            )
            .padding()

            Text(
                "Present this code at the gate"
            )
            .font(.caption)
            .foregroundStyle(
                .secondary
            )

            Spacer()
        }
        .padding()
        .navigationTitle("Ticket")
    }
}
7. Transaction detail
struct TransactionDetailView: View {

    let transaction:
        WalletTransaction

    var body: some View {

        VStack(spacing: 25) {

            Image(
                systemName:
                    "checkmark.circle.fill"
            )
            .font(
                .system(size: 70)
            )

            Text(
                "£\(abs(transaction.amount), specifier: "%.2f")"
            )
            .font(
                .system(
                    size: 44,
                    weight: .bold
                )
            )

            Text(transaction.merchant)
                .font(.title2)
                .fontWeight(.semibold)

            VStack(spacing: 0) {

                DetailRow(
                    title: "Category",
                    value:
                        transaction.category
                            .rawValue
                            .capitalized
                )

                Divider()

                DetailRow(
                    title: "Currency",
                    value:
                        transaction.currency
                )

                Divider()

                DetailRow(
                    title: "Date",
                    value:
                        transaction.date.formatted(
                            date: .abbreviated,
                            time: .shortened
                        )
                )

                Divider()

                DetailRow(
                    title: "Status",
                    value: "Completed"
                )
            }
            .padding()
            .background(
                .thinMaterial
            )
            .clipShape(
                RoundedRectangle(
                    cornerRadius: 20
                )
            )

            Spacer()
        }
        .padding()
        .navigationTitle(
            "Transaction"
        )
    }
}

And make the activity list navigable:

NavigationLink {

    TransactionDetailView(
        transaction: transaction
    )

} label: {

    TransactionRow(
        transaction: transaction
    )
}
8. C engine bridge

Now we can make Swift actually communicate with the C core.

final class NativeWalletEngine {

    private var wallet =
        Wallet()

    init() {

        wallet_init(
            &wallet,
            10001,
            5000.00
        )
    }

    var balance: Double {

        wallet_balance(
            &wallet
        )
    }

    @discardableResult
    func spend(
        amount: Double
    ) -> Bool {

        wallet_spend(
            &wallet,
            amount
        ) != 0
    }

    @discardableResult
    func deposit(
        amount: Double
    ) -> Bool {

        wallet_deposit(
            &wallet,
            amount
        ) != 0
    }
}

That gives us:

                 AUREOM WALLET
                       │
                       ▼
                  SwiftUI
                       │
                 View Models
                       │
              Wallet Services
                       │
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
      Keychain      PassKit       Backend API
          │
          ▼
    Authentication
       Face ID
       Touch ID
          │
          ▼
       C CORE
          │
     ┌────┴────┐
     ▼         ▼
 Payments   Transactions
     │
     ▼
   JULIA
     │
 ┌───┼────────┐
 ▼   ▼        ▼
Spend Cash   Risk
Model Flow   Model












1. Interactive card stack

This gives the cards a more physical, Wallet-like interaction.

import SwiftUI

struct InteractiveCardStack: View {

    let cards: [WalletItem]

    @State private var selectedCard: UUID?

    var body: some View {

        ZStack {

            ForEach(
                Array(cards.enumerated()),
                id: \.element.id
            ) { index, card in

                NavigationLink {

                    CardDetailView(card: card)

                } label: {

                    WalletCardView(
                        item: card,
                        index: index
                    )
                    .frame(
                        width: 340,
                        height: 205
                    )
                }
                .buttonStyle(.plain)
                .offset(
                    y: CGFloat(index) * 12
                )
                .scaleEffect(
                    1.0 -
                    CGFloat(index) * 0.035
                )
                .zIndex(
                    Double(cards.count - index)
                )
            }
        }
        .frame(
            height: 245
        )
    }
}

Use it in WalletHomeView:

InteractiveCardStack(
    cards: wallet.items.filter {
        $0.type == .paymentCard
    }
)
2. Better card model

Let's add a card colour/theme and masked number.

import SwiftUI

struct WalletCardTheme: Codable {

    var primary: String
    var secondary: String
}

extension WalletItem {

    var maskedNumber: String {

        guard let lastFour else {
            return "••••"
        }

        return "••••  ••••  ••••  \(lastFour)"
    }

    var theme: WalletCardTheme {

        switch type {

        case .paymentCard:
            return WalletCardTheme(
                primary: "black",
                secondary: "gray"
            )

        case .transit:
            return WalletCardTheme(
                primary: "blue",
                secondary: "cyan"
            )

        case .ticket:
            return WalletCardTheme(
                primary: "purple",
                secondary: "pink"
            )

        default:
            return WalletCardTheme(
                primary: "gray",
                secondary: "black"
            )
        }
    }
}
3. Payment confirmation

Instead of immediately declaring a payment successful, give the user a proper confirmation stage.

import SwiftUI

struct PaymentConfirmationView: View {

    let amount: Double
    let merchant: String

    @Environment(\.dismiss)
    private var dismiss

    @State private var authenticated = false
    @State private var completed = false

    var body: some View {

        VStack(spacing: 24) {

            Spacer()

            if completed {

                completionView

            } else {

                paymentView
            }

            Spacer()
        }
        .padding()
    }

    private var paymentView: some View {

        VStack(spacing: 20) {

            Image(
                systemName:
                    "wave.3.right"
            )
            .font(
                .system(size: 60)
            )

            Text(merchant)
                .font(.title2)
                .fontWeight(.semibold)

            Text(
                "£\(amount, specifier: "%.2f")"
            )
            .font(
                .system(
                    size: 44,
                    weight: .bold
                )
            )

            Text(
                "Confirm payment"
            )
            .foregroundStyle(
                .secondary
            )

            Button {

                Task {

                    await authenticate()
                }

            } label: {

                Text("Confirm with Face ID")
                    .frame(
                        maxWidth: .infinity
                    )
                    .padding()
            }
            .buttonStyle(
                .borderedProminent
            )
        }
    }

    private var completionView: some View {

        VStack(spacing: 20) {

            Image(
                systemName:
                    "checkmark.circle.fill"
            )
            .font(
                .system(size: 80)
            )

            Text("Payment complete")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text(
                "£\(amount, specifier: "%.2f")"
            )
            .font(.title)

            Button("Done") {
                dismiss()
            }
            .buttonStyle(
                .borderedProminent
            )
        }
    }

    private func authenticate() async {

        let context =
            LAContext()

        do {

            let success =
                try await context.evaluatePolicy(
                    .deviceOwnerAuthenticationWithBiometrics,
                    localizedReason:
                        "Confirm this payment."
                )

            if success {

                withAnimation(.spring) {

                    completed = true
                }
            }

        } catch {

            print(
                "Authentication failed:",
                error
            )
        }
    }
}

Add:

import LocalAuthentication

at the top.

4. Payment merchant interface
import SwiftUI

struct MerchantPaymentView: View {

    @State private var amount = ""
    @State private var showingConfirmation = false

    let merchant: String

    var numericAmount: Double? {
        Double(amount)
    }

    var body: some View {

        VStack(spacing: 25) {

            Image(
                systemName:
                    "storefront"
            )
            .font(
                .system(size: 55)
            )

            Text(merchant)
                .font(.title)
                .fontWeight(.bold)

            TextField(
                "Amount",
                text: $amount
            )
            .keyboardType(
                .decimalPad
            )
            .font(
                .system(
                    size: 48,
                    weight: .bold
                )
            )
            .multilineTextAlignment(
                .center
            )

            Spacer()

            Button {

                if numericAmount != nil {
                    showingConfirmation = true
                }

            } label: {

                Label(
                    "Pay",
                    systemImage:
                        "wave.3.right"
                )
                .fontWeight(.bold)
                .frame(
                    maxWidth: .infinity
                )
                .padding()
            }
            .buttonStyle(
                .borderedProminent
            )
            .disabled(
                numericAmount == nil
            )
        }
        .padding()
        .sheet(
            isPresented:
                $showingConfirmation
        ) {

            if let amount =
                numericAmount {

                PaymentConfirmationView(
                    amount: amount,
                    merchant: merchant
                )
            }
        }
    }
}
5. Spending chart

For the first prototype, Swift Charts is perfect.

import SwiftUI
import Charts

struct SpendingPoint:
    Identifiable {

    let id = UUID()
    let day: String
    let amount: Double
}

struct SpendingChartView: View {

    let points: [
        SpendingPoint
    ]

    var body: some View {

        Chart(points) { point in

            AreaMark(
                x: .value(
                    "Day",
                    point.day
                ),
                y: .value(
                    "Spend",
                    point.amount
                )
            )

            LineMark(
                x: .value(
                    "Day",
                    point.day
                ),
                y: .value(
                    "Spend",
                    point.amount
                )
            )
        }
        .frame(height: 220)
        .chartYAxis {
            AxisMarks(
                position: .leading
            )
        }
    }
}

Example:

SpendingChartView(
    points: [

        SpendingPoint(
            day: "Mon",
            amount: 42
        ),

        SpendingPoint(
            day: "Tue",
            amount: 71
        ),

        SpendingPoint(
            day: "Wed",
            amount: 38
        ),

        SpendingPoint(
            day: "Thu",
            amount: 112
        ),

        SpendingPoint(
            day: "Fri",
            amount: 84
        ),

        SpendingPoint(
            day: "Sat",
            amount: 145
        ),

        SpendingPoint(
            day: "Sun",
            amount: 61
        )
    ]
)
6. Intelligence dashboard

Now combine the chart with financial metrics.

import SwiftUI

struct FinancialDashboard:
    View {

    @EnvironmentObject
    private var wallet: WalletStore

    private var spending: Double {

        wallet.transactions
            .filter {
                $0.amount < 0
            }
            .reduce(0) {
                $0 + abs($1.amount)
            }
    }

    private var average: Double {

        let expenses =
            wallet.transactions.filter {
                $0.amount < 0
            }

        guard !expenses.isEmpty else {
            return 0
        }

        return spending /
            Double(expenses.count)
    }

    var body: some View {

        ScrollView {

            VStack(
                alignment: .leading,
                spacing: 20
            ) {

                Text(
                    "Financial Intelligence"
                )
                .font(
                    .largeTitle.weight(
                        .bold
                    )
                )

                metricGrid

                SpendingChartView(
                    points: demoPoints
                )
                .padding()
                .background(
                    .thinMaterial
                )
                .clipShape(
                    RoundedRectangle(
                        cornerRadius: 24
                    )
                )

                forecast

                merchantInsights
            }
            .padding()
        }
    }

    private var metricGrid:
        some View {

        HStack {

            MetricCard(
                title: "Spend",
                value:
                    "£\(spending, specifier: "%.0f")"
            )

            MetricCard(
                title: "Average",
                value:
                    "£\(average, specifier: "%.2f")"
            )
        }
    }

    private var forecast:
        some View {

        VStack(
            alignment: .leading,
            spacing: 8
        ) {

            Label(
                "FORECAST",
                systemImage:
                    "sparkles"
            )
            .font(
                .caption.weight(
                    .bold
                )
            )

            Text(
                "Projected next 30 days"
            )
            .font(.headline)

            Text(
                "£1,842"
            )
            .font(
                .system(
                    size: 34,
                    weight: .bold
                )
            )

            Text(
                "Your spending trajectory is currently stable."
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

    private var merchantInsights:
        some View {

        VStack(
            alignment: .leading,
            spacing: 10
        ) {

            Text(
                "Merchant intelligence"
            )
            .font(.headline)

            Text(
                "Your largest spending category this period is transport."
            )

            Text(
                "3 recurring payments detected."
            )

            Text(
                "Estimated discretionary spending: £612."
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

    private var demoPoints:
        [SpendingPoint] {

        [
            ("Mon", 42),
            ("Tue", 71),
            ("Wed", 38),
            ("Thu", 112),
            ("Fri", 84),
            ("Sat", 145),
            ("Sun", 61)
        ]
        .map {
            SpendingPoint(
                day: $0.0,
                amount: $0.1
            )
        }
    }
}

Metric card:

struct MetricCard: View {

    let title: String
    let value: String

    var body: some View {

        VStack(
            alignment: .leading
        ) {

            Text(title)
                .font(.caption)
                .foregroundStyle(
                    .secondary
                )

            Text(value)
                .font(
                    .title2.weight(
                        .bold
                    )
                )
        }
        .frame(
            maxWidth: .infinity,
            alignment: .leading
        )
        .padding()
        .background(
            .thinMaterial
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: 20
            )
        )
    }
}
7. Update the transaction model

For the intelligence layer, we need merchant location and payment status.

struct EnhancedTransaction:
    Identifiable,
    Codable {

    let id: UUID

    let merchant: String

    let amount: Double

    let currency: String

    let category:
        TransactionCategory

    let date: Date

    let latitude: Double?

    let longitude: Double?

    let status: TransactionStatus

    let paymentMethod:
        PaymentMethod
}

enum TransactionStatus:
    String,
    Codable {

    case pending
    case completed
    case reversed
    case declined
}

enum PaymentMethod:
    String,
    Codable {

    case card
    case bankTransfer
    case cash
    case digitalAsset
}

