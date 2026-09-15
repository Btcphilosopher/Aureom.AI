Node

Create AureomNodeClient.swift:

import Foundation

struct NodeHealth: Codable, Sendable {
    let status: String
    let bitcoinNetwork: String
    let lightning: Bool
    let blockHeight: Int
}

struct WalletBalance: Codable, Sendable {
    let confirmedSats: UInt64
    let pendingSats: UInt64

    var totalSats: UInt64 {
        confirmedSats + pendingSats
    }

    var btc: Double {
        Double(totalSats) / 100_000_000.0
    }
}

struct BitcoinAddressResponse: Codable, Sendable {
    let address: String
    let network: String
}

struct FeeEstimate: Codable, Sendable {
    let satPerVByte: Double
    let targetBlocks: Int
}

struct BroadcastResponse: Codable, Sendable {
    let txid: String
}

struct LightningInvoice: Codable, Sendable {
    let invoice: String
    let paymentHash: String
    let amountMsat: UInt64
    let expiresAt: Date
}

struct LightningPayment: Codable, Sendable {
    let paymentHash: String
    let status: String
    let amountMsat: UInt64
}

enum NodeClientError: Error {
    case invalidResponse
    case server(String)
}

actor AureomNodeClient {

    private let baseURL: URL
    private let session: URLSession

    init(
        baseURL: URL,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session
    }

    private func request<T: Decodable>(
        path: String,
        method: String = "GET",
        body: Data? = nil
    ) async throws -> T {

        let url = baseURL.appendingPathComponent(path)

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue(
            "application/json",
            forHTTPHeaderField: "Content-Type"
        )

        request.httpBody = body

        let (data, response) =
            try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw NodeClientError.invalidResponse
        }

        guard (200..<300).contains(http.statusCode) else {
            let message =
                String(data: data, encoding: .utf8)
                ?? "Unknown server error"

            throw NodeClientError.server(message)
        }

        return try JSONDecoder.aureom.decode(
            T.self,
            from: data
        )
    }

    func health() async throws -> NodeHealth {
        try await request(path: "v1/node/health")
    }

    func balance() async throws -> WalletBalance {
        try await request(path: "v1/bitcoin/balance")
    }

    func newBitcoinAddress() async throws
        -> BitcoinAddressResponse
    {
        try await request(path: "v1/bitcoin/address")
    }

    func feeEstimate(
        targetBlocks: Int = 6
    ) async throws -> FeeEstimate {

        let body = try JSONEncoder.aureom.encode(
            ["targetBlocks": targetBlocks]
        )

        return try await request(
            path: "v1/bitcoin/fee",
            method: "POST",
            body: body
        )
    }

    func broadcast(
        transactionHex: String
    ) async throws -> BroadcastResponse {

        let body = try JSONEncoder.aureom.encode([
            "hex": transactionHex
        ])

        return try await request(
            path: "v1/bitcoin/broadcast",
            method: "POST",
            body: body
        )
    }

    func createLightningInvoice(
        amountMsat: UInt64,
        memo: String
    ) async throws -> LightningInvoice {

        let body = try JSONEncoder.aureom.encode([
            "amountMsat": amountMsat,
            "memo": memo
        ])

        return try await request(
            path: "v1/lightning/invoice",
            method: "POST",
            body: body
        )
    }

    func payLightningInvoice(
        invoice: String
    ) async throws -> LightningPayment {

        let body = try JSONEncoder.aureom.encode([
            "invoice": invoice
        ])

        return try await request(
            path: "v1/lightning/pay",
            method: "POST",
            body: body
        )
    }
}

extension JSONDecoder {

    static let aureom: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}

extension JSONEncoder {

    static let aureom: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}
2. Swift wallet service

Now put the node behind a wallet-facing service.

CryptoWalletService.swift:

import Foundation

@MainActor
final class CryptoWalletService: ObservableObject {

    @Published private(set) var balance:
        WalletBalance?

    @Published private(set) var nodeHealth:
        NodeHealth?

    @Published private(set) var loading = false

    @Published var errorMessage:
        String?

    private let node: AureomNodeClient

    init(node: AureomNodeClient) {
        self.node = node
    }

    func refresh() async {

        loading = true
        errorMessage = nil

        do {

            async let health = node.health()
            async let balance = node.balance()

            self.nodeHealth = try await health
            self.balance = try await balance

        } catch {

            errorMessage =
                error.localizedDescription

        }

        loading = false
    }

    func newAddress()
        async throws -> BitcoinAddressResponse
    {
        try await node.newBitcoinAddress()
    }

    func createInvoice(
        sats: UInt64,
        memo: String
    ) async throws -> LightningInvoice {

        let msats = sats * 1_000

        return try await node.createLightningInvoice(
            amountMsat: msats,
            memo: memo
        )
    }

    func payInvoice(
        _ invoice: String
    ) async throws -> LightningPayment {

        try await node.payLightningInvoice(
            invoice: invoice
        )
    }
}

Your SwiftUI application can then initialise it:

@main
struct AureomWalletApp: App {

    @StateObject
    private var crypto: CryptoWalletService

    init() {

        let client = AureomNodeClient(
            baseURL: URL(
                string: "https://api.example.com/"
            )!
        )

        _crypto = StateObject(
            wrappedValue:
                CryptoWalletService(node: client)
        )
    }

    var body: some Scene {

        WindowGroup {

            MainWalletView()
                .environmentObject(crypto)
        }
    }
}

For development, point this at your local backend instead.

3. Server-side node API

For the server I would use Rust.

It gives us a strong boundary between:

HTTP
 ↓
authentication
 ↓
wallet API
 ↓
Bitcoin RPC
 ↓
Lightning API

A minimal production-oriented project:

aureom-node/
├── Cargo.toml
└── src/
    ├── main.rs
    ├── config.rs
    ├── bitcoin.rs
    ├── lightning.rs
    ├── api.rs
    └── error.rs
Cargo.toml
[package]
name = "aureom-node"
version = "0.1.0"
edition = "2021"

[dependencies]

axum = "0.8"
tokio = { version = "1", features = ["full"] }

serde = { version = "1", features = ["derive"] }
serde_json = "1"

reqwest = {
    version = "0.12",
    features = ["json", "rustls-tls"]
}

anyhow = "1"
thiserror = "2"

tracing = "0.1"
tracing-subscriber = {
    version = "0.3",
    features = ["env-filter"]
}

tower-http = {
    version = "0.6",
    features = ["trace"]
}

uuid = {
    version = "1",
    features = ["v4", "serde"]
}
4. Bitcoin Core RPC client

src/bitcoin.rs:

use anyhow::{anyhow, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Clone)]
pub struct BitcoinRpc {
    client: Client,
    url: String,
    username: String,
    password: String,
}

impl BitcoinRpc {

    pub fn new(
        url: String,
        username: String,
        password: String,
    ) -> Self {

        Self {
            client: Client::new(),
            url,
            username,
            password,
        }
    }

    async fn call(
        &self,
        method: &str,
        params: Value,
    ) -> Result<Value> {

        let payload = json!({
            "jsonrpc": "1.0",
            "id": "aureom",
            "method": method,
            "params": params
        });

        let response = self.client
            .post(&self.url)
            .basic_auth(
                &self.username,
                Some(&self.password)
            )
            .json(&payload)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(anyhow!(
                "Bitcoin RPC HTTP error: {}",
                response.status()
            ));
        }

        let value: Value =
            response.json().await?;

        if !value["error"].is_null() {
            return Err(anyhow!(
                "Bitcoin RPC error: {}",
                value["error"]
            ));
        }

        Ok(value["result"].clone())
    }

    pub async fn blockchain_info(
        &self
    ) -> Result<BlockchainInfo> {

        let value = self
            .call("getblockchaininfo", json!([]))
            .await?;

        Ok(serde_json::from_value(value)?)
    }

    pub async fn balance(&self) -> Result<f64> {

        let value = self
            .call("getbalances", json!([]))
            .await?;

        Ok(
            value["mine"]["trusted"]
                .as_f64()
                .unwrap_or(0.0)
        )
    }

    pub async fn new_address(
        &self
    ) -> Result<String> {

        let value = self
            .call("getnewaddress", json!([]))
            .await?;

        Ok(
            value.as_str()
                .ok_or_else(|| anyhow!("Invalid address"))?
                .to_string()
        )
    }

    pub async fn send_raw_transaction(
        &self,
        hex: &str
    ) -> Result<String> {

        let value = self
            .call(
                "sendrawtransaction",
                json!([hex])
            )
            .await?;

        Ok(
            value.as_str()
                .ok_or_else(|| anyhow!("Invalid txid"))?
                .to_string()
        )
    }

    pub async fn estimatesmartfee(
        &self,
        blocks: u32
    ) -> Result<f64> {

        let value = self
            .call(
                "estimatesmartfee",
                json!([blocks])
            )
            .await?;

        Ok(
            value["feerate"]
                .as_f64()
                .unwrap_or(0.0)
        )
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct BlockchainInfo {

    pub chain: String,

    #[serde(rename = "blocks")]
    pub block_height: u64,

    pub headers: u64,

    pub verificationprogress: f64,
}
5. Lightning node interface

Crucially, don't tie the application to one Lightning implementation.

Create a trait:

src/lightning.rs

use anyhow::Result;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct LightningInvoice {

    pub invoice: String,

    pub payment_hash: String,

    pub amount_msat: u64,

    pub expires_at: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct LightningPayment {

    pub payment_hash: String,

    pub status: String,

    pub amount_msat: u64,
}

#[async_trait]
pub trait LightningNode:
    Send + Sync
{
    async fn create_invoice(
        &self,
        amount_msat: u64,
        memo: &str,
    ) -> Result<LightningInvoice>;

    async fn pay_invoice(
        &self,
        invoice: &str,
    ) -> Result<LightningPayment>;
}

That gives us an abstraction where we can subsequently implement:

LightningNode
       │
       ├── LND
       │
       ├── Core Lightning
       │
       └── Eclair

without rewriting the Swift application.

6. Axum API

src/main.rs:

use axum::{
    extract::State,
    routing::{get, post},
    Json,
    Router,
};

use serde::{Deserialize, Serialize};
use std::sync::Arc;

mod bitcoin;

use bitcoin::BitcoinRpc;

#[derive(Clone)]
struct AppState {

    bitcoin: BitcoinRpc,

    network: String,
}

#[derive(Serialize)]
struct HealthResponse {

    status: String,

    #[serde(rename = "bitcoinNetwork")]
    bitcoin_network: String,

    lightning: bool,

    #[serde(rename = "blockHeight")]
    block_height: u64,
}

#[derive(Serialize)]
struct BalanceResponse {

    #[serde(rename = "confirmedSats")]
    confirmed_sats: u64,

    #[serde(rename = "pendingSats")]
    pending_sats: u64,
}

#[derive(Serialize)]
struct AddressResponse {

    address: String,

    network: String,
}

#[derive(Deserialize)]
struct BroadcastRequest {

    hex: String,
}

#[derive(Serialize)]
struct BroadcastResponse {

    txid: String,
}

#[derive(Deserialize)]
struct FeeRequest {

    #[serde(rename = "targetBlocks")]
    target_blocks: u32,
}

#[derive(Serialize)]
struct FeeResponse {

    #[serde(rename = "satPerVByte")]
    sat_per_vbyte: f64,

    #[serde(rename = "targetBlocks")]
    target_blocks: u32,
}

async fn health(
    State(state): State<Arc<AppState>>
) -> Json<HealthResponse> {

    let info =
        state.bitcoin
            .blockchain_info()
            .await
            .expect("Bitcoin node unavailable");

    Json(
        HealthResponse {

            status: "ok".into(),

            bitcoin_network:
                state.network.clone(),

            lightning: false,

            block_height:
                info.block_height,
        }
    )
}

async fn balance(
    State(state): State<Arc<AppState>>
) -> Json<BalanceResponse> {

    let btc =
        state.bitcoin
            .balance()
            .await
            .unwrap_or(0.0);

    let sats =
        (btc * 100_000_000.0)
            .round() as u64;

    Json(
        BalanceResponse {

            confirmed_sats: sats,

            pending_sats: 0,
        }
    )
}

async fn new_address(
    State(state): State<Arc<AppState>>
) -> Json<AddressResponse> {

    let address =
        state.bitcoin
            .new_address()
            .await
            .expect("Could not create address");

    Json(
        AddressResponse {

            address,

            network:
                state.network.clone(),
        }
    )
}

async fn fee(
    State(state): State<Arc<AppState>>,
    Json(request): Json<FeeRequest>
) -> Json<FeeResponse> {

    let btc_per_kb =
        state.bitcoin
            .estimatesmartfee(
                request.target_blocks
            )
            .await
            .unwrap_or(0.0);

    let sat_per_vbyte =
        btc_per_kb * 100_000_000.0 / 1000.0;

    Json(
        FeeResponse {

            sat_per_vbyte,

            target_blocks:
                request.target_blocks,
        }
    )
}

async fn broadcast(
    State(state): State<Arc<AppState>>,
    Json(request): Json<BroadcastRequest>
) -> Json<BroadcastResponse> {

    let txid =
        state.bitcoin
            .send_raw_transaction(
                &request.hex
            )
            .await
            .expect("Broadcast failed");

    Json(
        BroadcastResponse {
            txid
        }
    )
}

#[tokio::main]
async fn main() {

    tracing_subscriber::
        fmt::init();

    let bitcoin =
        BitcoinRpc::new(
            std::env::var(
                "BITCOIN_RPC_URL"
            )
            .unwrap_or(
                "http://127.0.0.1:18443"
                    .into()
            ),

            std::env::var(
                "BITCOIN_RPC_USER"
            )
            .expect(
                "BITCOIN_RPC_USER required"
            ),

            std::env::var(
                "BITCOIN_RPC_PASSWORD"
            )
            .expect(
                "BITCOIN_RPC_PASSWORD required"
            ),
        );

    let state =
        Arc::new(
            AppState {

                bitcoin,

                network:
                    std::env::var(
                        "BITCOIN_NETWORK"
                    )
                    .unwrap_or(
                        "regtest".into()
                    ),
            }
        );

    let app =
        Router::new()

            .route(
                "/v1/node/health",
                get(health)
            )

            .route(
                "/v1/bitcoin/balance",
                get(balance)
            )

            .route(
                "/v1/bitcoin/address",
                get(new_address)
            )

            .route(
                "/v1/bitcoin/fee",
                post(fee)
            )

            .route(
                "/v1/bitcoin/broadcast",
                post(broadcast)
            )

            .with_state(state);

    let listener =
        tokio::net::TcpListener::bind(
            "0.0.0.0:8080"
        )
        .await
        .unwrap();

    println!(
        "Aureom Node API listening on {}",
        listener.local_addr().unwrap()
    );

    axum::serve(
        listener,
        app
    )
    .await
    .unwrap();
}

