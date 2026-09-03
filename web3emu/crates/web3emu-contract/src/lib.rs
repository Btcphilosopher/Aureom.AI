//! web3emu-contract
//!
//! A lightweight, deterministic contract runtime (sections 25-29, 68-69).
//! WEB3EMU does not implement a general-purpose VM. Instead it ships a
//! small `NativeRuntime` with a handful of built-in, hand-written
//! contract kinds (Counter, Token, NFT) plus a narrow Level-1 DSL that
//! compiles simple single-field counter contracts into the same
//! execution model. `ExecutionBackend` is the seam a future, more
//! expressive VM (or an audited EVM implementation, per section 69)
//! would plug into - it is not implemented here, and this crate never
//! pretends otherwise.

pub mod dsl;
pub mod nft;
pub mod token;

use serde::{Deserialize, Serialize};
use web3emu_account::Storage;
use web3emu_crypto::hash;
use web3emu_types::{Address, BlockHeight, Gas, Hash256, Timestamp};

/// An event emitted during a contract call, before the execution engine
/// attaches block/transaction/log-index context (see `web3emu-events`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawEvent {
    pub event_name: String,
    pub topics: Vec<Hash256>,
    pub data: Vec<u8>,
}

impl RawEvent {
    pub fn new(event_name: &str, extra_topics: Vec<Hash256>, data: Vec<u8>) -> Self {
        let mut topics = vec![hash(event_name.as_bytes())];
        topics.extend(extra_topics);
        RawEvent {
            event_name: event_name.to_string(),
            topics,
            data,
        }
    }
}

pub struct CallContext<'a> {
    pub contract_address: Address,
    pub caller: Address,
    pub storage: &'a mut Storage,
    pub block: BlockHeight,
    pub timestamp: Timestamp,
    pub gas_limit: Gas,
}

#[derive(Debug, Clone, Default)]
pub struct CallOutcome {
    pub return_data: Vec<u8>,
    pub events: Vec<RawEvent>,
    pub gas_used: Gas,
}

#[derive(Debug, Clone, thiserror::Error, PartialEq, Eq)]
pub enum ContractError {
    #[error("unknown method '{0}'")]
    UnknownMethod(String),
    #[error("invalid arguments: {0}")]
    InvalidArgs(String),
    #[error("execution reverted: {0}")]
    Reverted(String),
    #[error("gas exhausted: needed {needed}, had {available}")]
    GasExhausted { needed: Gas, available: Gas },
    #[error("execution backend does not support this contract: {0}")]
    Unsupported(String),
}

/// Deterministic gas costs for primitive contract operations (section
/// 22). Shared by every built-in contract so costs are comparable across
/// contract kinds.
pub mod gas_costs {
    use web3emu_types::Gas;
    pub const BASE_CALL: Gas = 500;
    pub const STORAGE_READ: Gas = 50;
    pub const STORAGE_WRITE: Gas = 200;
    pub const EVENT: Gas = 150;
}

fn charge(ctx: &CallContext, used_so_far: Gas, amount: Gas) -> Result<Gas, ContractError> {
    let total = used_so_far + amount;
    if total > ctx.gas_limit {
        return Err(ContractError::GasExhausted {
            needed: total,
            available: ctx.gas_limit,
        });
    }
    Ok(total)
}

/// What a deployed contract's `code` bytes decode to. This is the
/// "compiled" form every deployment produces, whether it came from a
/// built-in constructor or from `dsl::compile`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ContractInit {
    Counter(dsl::CounterSpec),
    Token(token::TokenInit),
    Nft(nft::NftInit),
}

impl ContractInit {
    pub fn encode(&self) -> Vec<u8> {
        serde_json::to_vec(self).expect("ContractInit always serializes")
    }

    pub fn decode(code: &[u8]) -> Result<Self, ContractError> {
        serde_json::from_slice(code)
            .map_err(|e| ContractError::InvalidArgs(format!("corrupt contract code: {e}")))
    }

    pub fn kind_name(&self) -> &'static str {
        match self {
            ContractInit::Counter(_) => "counter",
            ContractInit::Token(_) => "token",
            ContractInit::Nft(_) => "nft",
        }
    }
}

/// Execution backend abstraction (section 69). `NativeRuntime` is the
/// only implementation shipped today. `EvmBackend` / `MockRuntime` are
/// intentionally NOT implemented - integrating a real VM later means
/// adding a new backend behind this trait, not rewriting the core.
pub trait ExecutionBackend: Send + Sync {
    fn call(
        &self,
        init: &ContractInit,
        ctx: &mut CallContext,
        method: &str,
        args: &[u8],
    ) -> Result<CallOutcome, ContractError>;
}

pub struct NativeRuntime;

impl ExecutionBackend for NativeRuntime {
    fn call(
        &self,
        init: &ContractInit,
        ctx: &mut CallContext,
        method: &str,
        args: &[u8],
    ) -> Result<CallOutcome, ContractError> {
        match init {
            ContractInit::Counter(spec) => dsl::call_counter(spec, ctx, method, args),
            ContractInit::Token(t) => token::call_token(t, ctx, method, args),
            ContractInit::Nft(n) => nft::call_nft(n, ctx, method, args),
        }
    }
}

/// A stub for a future, more expressive deterministic VM or an audited
/// EVM integration (section 25 Level 4-5, section 69). Present so the
/// `ExecutionBackend` seam is visible in the API, but calling it always
/// fails loudly rather than silently behaving like `NativeRuntime`.
pub struct UnimplementedBackend {
    pub name: &'static str,
}

impl ExecutionBackend for UnimplementedBackend {
    fn call(
        &self,
        _init: &ContractInit,
        _ctx: &mut CallContext,
        _method: &str,
        _args: &[u8],
    ) -> Result<CallOutcome, ContractError> {
        Err(ContractError::Unsupported(self.name.to_string()))
    }
}

/// Simple positional argument encoding used by the built-in Token and
/// NFT contracts. Not a general ABI - just enough structure to make
/// scenario files and the CLI legible. See `docs/CONTRACTS.md`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ArgValue {
    Address(Address),
    U128(u128),
    Bytes(Vec<u8>),
}

pub fn encode_args(values: &[ArgValue]) -> Vec<u8> {
    let mut out = Vec::new();
    for v in values {
        match v {
            ArgValue::Address(a) => {
                out.push(0u8);
                out.extend_from_slice(&a.0);
            }
            ArgValue::U128(n) => {
                out.push(1u8);
                out.extend_from_slice(&n.to_be_bytes());
            }
            ArgValue::Bytes(b) => {
                out.push(2u8);
                out.extend_from_slice(&(b.len() as u32).to_be_bytes());
                out.extend_from_slice(b);
            }
        }
    }
    out
}

pub fn decode_args(mut bytes: &[u8]) -> Result<Vec<ArgValue>, ContractError> {
    let mut out = Vec::new();
    while !bytes.is_empty() {
        let tag = bytes[0];
        bytes = &bytes[1..];
        match tag {
            0 => {
                if bytes.len() < 20 {
                    return Err(ContractError::InvalidArgs("truncated address".into()));
                }
                let addr = Address::from_slice(&bytes[..20])
                    .map_err(|e| ContractError::InvalidArgs(e.to_string()))?;
                out.push(ArgValue::Address(addr));
                bytes = &bytes[20..];
            }
            1 => {
                if bytes.len() < 16 {
                    return Err(ContractError::InvalidArgs("truncated u128".into()));
                }
                let mut buf = [0u8; 16];
                buf.copy_from_slice(&bytes[..16]);
                out.push(ArgValue::U128(u128::from_be_bytes(buf)));
                bytes = &bytes[16..];
            }
            2 => {
                if bytes.len() < 4 {
                    return Err(ContractError::InvalidArgs("truncated bytes length".into()));
                }
                let mut len_buf = [0u8; 4];
                len_buf.copy_from_slice(&bytes[..4]);
                let len = u32::from_be_bytes(len_buf) as usize;
                bytes = &bytes[4..];
                if bytes.len() < len {
                    return Err(ContractError::InvalidArgs("truncated bytes payload".into()));
                }
                out.push(ArgValue::Bytes(bytes[..len].to_vec()));
                bytes = &bytes[len..];
            }
            _ => return Err(ContractError::InvalidArgs("unknown arg tag".into())),
        }
    }
    Ok(out)
}

pub(crate) fn read_u128(storage: &Storage, key: &[u8]) -> u128 {
    storage
        .get(key)
        .map(|v| {
            let mut buf = [0u8; 16];
            let n = v.len().min(16);
            buf[16 - n..].copy_from_slice(&v[v.len() - n..]);
            u128::from_be_bytes(buf)
        })
        .unwrap_or(0)
}

pub(crate) fn write_u128(storage: &mut Storage, key: Vec<u8>, value: u128) {
    storage.insert(key, value.to_be_bytes().to_vec());
}

pub(crate) fn spend_gas(
    ctx: &CallContext,
    used: &mut Gas,
    amount: Gas,
) -> Result<(), ContractError> {
    *used = charge(ctx, *used, amount)?;
    Ok(())
}
