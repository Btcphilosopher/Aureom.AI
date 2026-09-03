//! web3emu-rpc
//!
//! A minimal JSON-RPC 2.0 server (sections 34-36) exposing a *subset* of
//! common Web3 JSON-RPC method names against an `EmulatorNetwork`. This
//! is explicitly NOT a claim of full compatibility with any specific
//! production network's RPC surface - see `docs/COMPATIBILITY.md` for
//! exactly which methods are implemented and how their semantics differ
//! (most importantly: `eth_sendRawTransaction` here expects a hex-encoded
//! JSON `EmulatorTransaction`, not an RLP-encoded production transaction).

use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use web3emu_account::AccountKind;
use web3emu_block::EmulatorBlock;
use web3emu_core::EmulatorNetwork;
use web3emu_events::{EventFilter, EventLog};
use web3emu_tx::{EmulatorTransaction, ExecutionStatus, TransactionReceipt};
use web3emu_types::{Address, Hash256};

/// Methods this server understands, and a one-line note on how faithful
/// each is to common production JSON-RPC semantics. Surfaced by the
/// non-standard `web3emu_compatibility` method and mirrored in
/// `docs/RPC.md` / `docs/COMPATIBILITY.md`.
pub const SUPPORTED_METHODS: &[(&str, &str)] = &[
    ("eth_chainId", "faithful"),
    ("eth_blockNumber", "faithful"),
    ("eth_getBalance", "faithful (only 'latest' tag supported)"),
    ("eth_getTransactionCount", "faithful (only 'latest' tag supported)"),
    ("eth_getBlockByNumber", "partial - no transaction-object expansion"),
    ("eth_getBlockByHash", "partial - no transaction-object expansion"),
    ("eth_getTransactionByHash", "faithful"),
    ("eth_getTransactionReceipt", "faithful"),
    ("eth_sendRawTransaction", "DEVIATES - payload is hex(JSON EmulatorTransaction), not RLP"),
    ("eth_call", "DEVIATES - `data` is hex(JSON ContractCallData), no ABI encoding"),
    ("eth_estimateGas", "DEVIATES - same call-data convention as eth_call"),
    ("eth_getCode", "faithful"),
    ("eth_getLogs", "partial - address/fromBlock/toBlock filters only"),
    ("eth_getStorageAt", "faithful"),
    ("web3emu_mine", "non-standard: mine N blocks now"),
    ("web3emu_status", "non-standard: network summary"),
];

fn hex_u64(v: u64) -> String {
    format!("0x{v:x}")
}
fn hex_u128(v: u128) -> String {
    format!("0x{v:x}")
}
fn hex_bytes(v: &[u8]) -> String {
    format!("0x{}", hex::encode(v))
}
fn parse_hex_u64(s: &str) -> Option<u64> {
    u64::from_str_radix(s.strip_prefix("0x").unwrap_or(s), 16).ok()
}
fn parse_hex_bytes(s: &str) -> Option<Vec<u8>> {
    hex::decode(s.strip_prefix("0x").unwrap_or(s)).ok()
}
fn parse_address(s: &str) -> Option<Address> {
    s.parse().ok()
}
fn parse_hash(s: &str) -> Option<Hash256> {
    s.parse().ok()
}

#[derive(Debug)]
pub struct RpcErr {
    pub code: i64,
    pub message: String,
}

impl RpcErr {
    fn invalid_params(msg: &str) -> Self {
        RpcErr {
            code: -32602,
            message: msg.to_string(),
        }
    }
    fn method_not_found(method: &str) -> Self {
        RpcErr {
            code: -32601,
            message: format!("method not found: {method}"),
        }
    }
    fn internal(msg: impl Into<String>) -> Self {
        RpcErr {
            code: -32603,
            message: msg.into(),
        }
    }
}

fn block_json(block: &EmulatorBlock) -> Value {
    json!({
        "number": hex_u64(block.height),
        "hash": block.block_hash.to_string(),
        "parentHash": block.parent_hash.to_string(),
        "timestamp": hex_u64(block.timestamp),
        "miner": block.proposer.to_string(),
        "gasUsed": hex_u64(block.gas_used),
        "gasLimit": hex_u64(block.gas_limit),
        "baseFeePerGas": hex_u128(block.base_fee),
        "stateRoot": block.state_root.to_string(),
        "transactionsRoot": block.transaction_root.to_string(),
        "receiptsRoot": block.receipt_root.to_string(),
        "logsDigest": block.logs_digest.to_string(),
        "protocolVersion": block.protocol_version,
        "transactions": block.transactions.iter().map(|h| h.to_string()).collect::<Vec<_>>(),
    })
}

fn tx_json(tx: &EmulatorTransaction, block: Option<&EmulatorBlock>) -> Value {
    json!({
        "hash": tx.hash.to_string(),
        "nonce": hex_u64(tx.nonce),
        "from": tx.sender.to_string(),
        "to": tx.recipient.map(|a| a.to_string()),
        "value": hex_u128(tx.value),
        "gas": hex_u64(tx.gas_limit),
        "maxFeePerGas": hex_u128(tx.max_fee),
        "maxPriorityFeePerGas": hex_u128(tx.priority_fee),
        "input": hex_bytes(&tx.data),
        "chainId": hex_u64(tx.chain_id),
        "blockHash": block.map(|b| b.block_hash.to_string()),
        "blockNumber": block.map(|b| hex_u64(b.height)),
        "type": format!("{:?}", tx.tx_type),
    })
}

fn log_json(log: &EventLog) -> Value {
    json!({
        "address": log.contract.to_string(),
        "eventName": log.event_name,
        "topics": log.topics.iter().map(|t| t.to_string()).collect::<Vec<_>>(),
        "data": hex_bytes(&log.data),
        "blockNumber": hex_u64(log.block),
        "transactionHash": log.transaction.to_string(),
        "logIndex": hex_u64(log.log_index),
    })
}

fn receipt_json(r: &TransactionReceipt) -> Value {
    json!({
        "transactionHash": r.transaction_hash.to_string(),
        "blockHash": r.block_hash.to_string(),
        "blockNumber": hex_u64(r.block_height),
        "status": match r.status { ExecutionStatus::Success => "0x1", ExecutionStatus::Reverted { .. } => "0x0" },
        "gasUsed": hex_u64(r.gas_used),
        "effectiveGasPrice": hex_u128(r.effective_gas_price),
        "contractAddress": r.contract_address.map(|a| a.to_string()),
        "logs": r.logs.iter().map(log_json).collect::<Vec<_>>(),
        "executionTimeMicros": r.execution_time_micros,
        "failureReason": r.failure_reason,
        "returnData": hex_bytes(&r.return_data),
    })
}

/// Dispatch one already-parsed JSON-RPC method call against the network.
pub fn dispatch(network: &mut EmulatorNetwork, method: &str, params: &Value) -> Result<Value, RpcErr> {
    let arr = params.as_array().cloned().unwrap_or_default();
    let get_str = |i: usize| -> Option<String> { arr.get(i).and_then(|v| v.as_str()).map(str::to_string) };

    match method {
        "eth_chainId" => Ok(json!(hex_u64(network.chain_id()))),
        "eth_blockNumber" => Ok(json!(hex_u64(network.block_height()))),
        "eth_getBalance" => {
            let addr = get_str(0)
                .and_then(|s| parse_address(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [address, blockTag]"))?;
            Ok(json!(hex_u128(network.balance_of(&addr))))
        }
        "eth_getTransactionCount" => {
            let addr = get_str(0)
                .and_then(|s| parse_address(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [address, blockTag]"))?;
            Ok(json!(hex_u64(network.nonce_of(&addr))))
        }
        "eth_getBlockByNumber" => {
            let tag = get_str(0).unwrap_or_else(|| "latest".to_string());
            let height = if tag == "latest" {
                network.block_height()
            } else {
                parse_hex_u64(&tag).ok_or_else(|| RpcErr::invalid_params("bad block tag"))?
            };
            Ok(network.get_block(height).map(block_json).unwrap_or(Value::Null))
        }
        "eth_getBlockByHash" => {
            let hash = get_str(0)
                .and_then(|s| parse_hash(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [blockHash]"))?;
            Ok(network.get_block_by_hash(&hash).map(block_json).unwrap_or(Value::Null))
        }
        "eth_getTransactionByHash" => {
            let hash = get_str(0)
                .and_then(|s| parse_hash(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [txHash]"))?;
            let tx = network.get_transaction(&hash);
            let block = network
                .get_receipt(&hash)
                .and_then(|r| network.get_block_by_hash(&r.block_hash));
            Ok(tx.map(|t| tx_json(t, block)).unwrap_or(Value::Null))
        }
        "eth_getTransactionReceipt" => {
            let hash = get_str(0)
                .and_then(|s| parse_hash(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [txHash]"))?;
            Ok(network.get_receipt(&hash).map(receipt_json).unwrap_or(Value::Null))
        }
        "eth_sendRawTransaction" => {
            let raw = get_str(0).ok_or_else(|| RpcErr::invalid_params("expected [hexEncodedTx]"))?;
            let bytes = parse_hex_bytes(&raw).ok_or_else(|| RpcErr::invalid_params("not valid hex"))?;
            let tx: EmulatorTransaction = serde_json::from_slice(&bytes)
                .map_err(|e| RpcErr::invalid_params(&format!("malformed transaction JSON: {e}")))?;
            let hash = tx.hash;
            network.submit_transaction(tx).map_err(|e| RpcErr::internal(e.to_string()))?;
            Ok(json!(hash.to_string()))
        }
        "eth_call" | "eth_estimateGas" => {
            let call = arr.first().cloned().unwrap_or(Value::Null);
            let to = call
                .get("to")
                .and_then(Value::as_str)
                .and_then(parse_address)
                .ok_or_else(|| RpcErr::invalid_params("expected {to, from?, data} object"))?;
            let from = call
                .get("from")
                .and_then(Value::as_str)
                .and_then(parse_address)
                .unwrap_or(Address::ZERO);
            let data_hex = call.get("data").and_then(Value::as_str).unwrap_or("0x");
            let data = parse_hex_bytes(data_hex).ok_or_else(|| RpcErr::invalid_params("bad data hex"))?;
            let call_data: web3emu_execution::ContractCallData = serde_json::from_slice(&data)
                .map_err(|e| RpcErr::invalid_params(&format!("expected hex(JSON ContractCallData): {e}")))?;
            let outcome = network
                .engine
                .simulate_call(
                    &network.state,
                    to,
                    from,
                    &call_data.method,
                    &call_data.args,
                    5_000_000,
                    network.block_height(),
                    network.clock,
                )
                .map_err(RpcErr::internal)?;
            if method == "eth_call" {
                Ok(json!(hex_bytes(&outcome.return_data)))
            } else {
                Ok(json!(hex_u64(outcome.gas_used)))
            }
        }
        "eth_getCode" => {
            let addr = get_str(0)
                .and_then(|s| parse_address(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [address]"))?;
            let code = network
                .get_account(&addr)
                .filter(|a| a.kind == AccountKind::Contract)
                .and_then(|a| a.code.clone())
                .unwrap_or_default();
            Ok(json!(hex_bytes(&code)))
        }
        "eth_getStorageAt" => {
            let addr = get_str(0)
                .and_then(|s| parse_address(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected [address, key]"))?;
            let key = get_str(1)
                .and_then(|s| parse_hex_bytes(&s))
                .ok_or_else(|| RpcErr::invalid_params("expected hex key"))?;
            let value = network
                .get_account(&addr)
                .and_then(|a| a.storage.get(&key))
                .cloned()
                .unwrap_or_default();
            Ok(json!(hex_bytes(&value)))
        }
        "eth_getLogs" => {
            let filter_obj = arr.first().cloned().unwrap_or(Value::Null);
            let filter = EventFilter {
                contract: filter_obj.get("address").and_then(Value::as_str).and_then(parse_address),
                event_name: filter_obj.get("eventName").and_then(Value::as_str).map(str::to_string),
                from_block: filter_obj.get("fromBlock").and_then(Value::as_str).and_then(parse_hex_u64),
                to_block: filter_obj.get("toBlock").and_then(Value::as_str).and_then(parse_hex_u64),
                topics: vec![],
            };
            Ok(json!(network
                .logs_matching(&filter)
                .into_iter()
                .map(log_json)
                .collect::<Vec<_>>()))
        }
        "web3emu_mine" => {
            let n = arr.first().and_then(Value::as_u64).unwrap_or(1);
            let blocks = network.mine_blocks(n, usize::MAX);
            Ok(json!(blocks.iter().map(block_json).collect::<Vec<_>>()))
        }
        "web3emu_status" => Ok(json!({
            "networkId": network.network_id,
            "chainId": hex_u64(network.chain_id()),
            "blockHeight": network.block_height(),
            "mempoolSize": network.mempool.len(),
            "simulation": true,
        })),
        "web3emu_compatibility" => Ok(json!(SUPPORTED_METHODS
            .iter()
            .map(|(m, note)| json!({"method": m, "compatibility": note}))
            .collect::<Vec<_>>())),
        other => Err(RpcErr::method_not_found(other)),
    }
}

fn handle_single(network: &mut EmulatorNetwork, req: &Value) -> Value {
    let id = req.get("id").cloned().unwrap_or(Value::Null);
    let method = match req.get("method").and_then(Value::as_str) {
        Some(m) => m,
        None => {
            return json!({"jsonrpc": "2.0", "id": id, "error": {"code": -32600, "message": "invalid request: missing method"}})
        }
    };
    let params = req.get("params").cloned().unwrap_or(json!([]));
    match dispatch(network, method, &params) {
        Ok(result) => json!({"jsonrpc": "2.0", "id": id, "result": result}),
        Err(e) => json!({"jsonrpc": "2.0", "id": id, "error": {"code": e.code, "message": e.message}}),
    }
}

/// Handle one raw JSON-RPC HTTP body (single request or batch array),
/// returning the raw JSON response body.
pub fn handle_body(network: &Arc<Mutex<EmulatorNetwork>>, body: &str) -> String {
    let parsed: Result<Value, _> = serde_json::from_str(body);
    let mut net = match network.lock() {
        Ok(n) => n,
        Err(poisoned) => poisoned.into_inner(),
    };
    match parsed {
        Ok(Value::Array(reqs)) => {
            let responses: Vec<Value> = reqs.iter().map(|r| handle_single(&mut net, r)).collect();
            serde_json::to_string(&responses).unwrap_or_default()
        }
        Ok(single) => serde_json::to_string(&handle_single(&mut net, &single)).unwrap_or_default(),
        Err(e) => {
            let err = json!({"jsonrpc": "2.0", "id": Value::Null, "error": {"code": -32700, "message": format!("parse error: {e}")}});
            serde_json::to_string(&err).unwrap_or_default()
        }
    }
}

/// Run the local JSON-RPC HTTP server (section 36) until the process is
/// killed. Blocking - callers typically run this on a dedicated thread
/// or as the CLI's main loop for `web3emu start`.
pub fn serve(host: &str, port: u16, network: Arc<Mutex<EmulatorNetwork>>) -> std::io::Result<()> {
    let addr = format!("{host}:{port}");
    let server = tiny_http::Server::http(&addr).map_err(std::io::Error::other)?;
    eprintln!("WEB3EMU RPC (SIMULATION / DEVELOPMENT ONLY) listening on http://{addr}");
    for mut request in server.incoming_requests() {
        let mut body = String::new();
        if request.as_reader().read_to_string(&mut body).is_err() {
            let _ = request.respond(tiny_http::Response::from_string("bad request").with_status_code(400));
            continue;
        }
        let response_body = handle_body(&network, &body);
        let header = tiny_http::Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..])
            .expect("static header is always valid");
        let response = tiny_http::Response::from_string(response_body).with_header(header);
        let _ = request.respond(response);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use web3emu_core::GenesisConfig;
    use web3emu_crypto::Keypair;

    fn network_with_alice() -> (EmulatorNetwork, Keypair) {
        let alice = Keypair::from_label("Alice");
        let genesis = GenesisConfig {
            initial_accounts: vec![(alice.address(), 1_000_000)],
            ..Default::default()
        };
        (EmulatorNetwork::genesis(genesis), alice)
    }

    #[test]
    fn chain_id_and_block_number() {
        let (mut net, _) = network_with_alice();
        let v = dispatch(&mut net, "eth_chainId", &json!([])).unwrap();
        assert_eq!(v, json!(hex_u64(31337)));
        let v = dispatch(&mut net, "eth_blockNumber", &json!([])).unwrap();
        assert_eq!(v, json!("0x0"));
    }

    #[test]
    fn get_balance_reflects_genesis() {
        let (mut net, alice) = network_with_alice();
        let v = dispatch(&mut net, "eth_getBalance", &json!([alice.address().to_string(), "latest"])).unwrap();
        assert_eq!(v, json!(hex_u128(1_000_000)));
    }

    #[test]
    fn send_raw_transaction_then_mine_then_receipt() {
        let (mut net, alice) = network_with_alice();
        let bob = Address([2u8; 20]);
        let mut tx = EmulatorTransaction::new_unsigned(
            net.chain_id(),
            0,
            alice.address(),
            alice.public_key_bytes(),
            Some(bob),
            100,
            1000,
            1,
            0,
            vec![],
            0,
            web3emu_tx::TransactionType::Transfer,
        );
        tx.sign(&alice).unwrap();
        let raw = hex_bytes(&serde_json::to_vec(&tx).unwrap());
        let sent = dispatch(&mut net, "eth_sendRawTransaction", &json!([raw])).unwrap();
        assert_eq!(sent, json!(tx.hash.to_string()));

        dispatch(&mut net, "web3emu_mine", &json!([1])).unwrap();

        let receipt = dispatch(&mut net, "eth_getTransactionReceipt", &json!([tx.hash.to_string()])).unwrap();
        assert_eq!(receipt["status"], json!("0x1"));
    }

    #[test]
    fn unknown_method_is_reported_cleanly() {
        let (mut net, _) = network_with_alice();
        let err = dispatch(&mut net, "eth_totallyMadeUp", &json!([])).unwrap_err();
        assert_eq!(err.code, -32601);
    }

    #[test]
    fn batch_request_via_handle_body() {
        let (net, _) = network_with_alice();
        let shared = Arc::new(Mutex::new(net));
        let body = json!([
            {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
            {"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []},
        ])
        .to_string();
        let response = handle_body(&shared, &body);
        let parsed: Value = serde_json::from_str(&response).unwrap();
        assert!(parsed.is_array());
        assert_eq!(parsed.as_array().unwrap().len(), 2);
    }
}
