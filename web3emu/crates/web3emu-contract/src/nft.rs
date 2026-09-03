//! A lightweight NFT demonstration contract (section 28): ownership,
//! mint, transfer, and a metadata *reference* (a URI string) rather than
//! storing image bytes directly in simulated state.

use crate::{decode_args, gas_costs, spend_gas, ArgValue, CallContext, CallOutcome, ContractError, RawEvent};
use serde::{Deserialize, Serialize};
use web3emu_types::{Address, Gas, Hash256};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NftInit {
    pub name: String,
    pub symbol: String,
    /// Only this address may mint new tokens.
    pub owner: Address,
}

fn address_topic(addr: &Address) -> Hash256 {
    let mut buf = [0u8; 32];
    buf[12..].copy_from_slice(&addr.0);
    Hash256(buf)
}

fn owner_key(token_id: u64) -> Vec<u8> {
    let mut k = b"owner:".to_vec();
    k.extend_from_slice(&token_id.to_be_bytes());
    k
}

fn meta_key(token_id: u64) -> Vec<u8> {
    let mut k = b"meta:".to_vec();
    k.extend_from_slice(&token_id.to_be_bytes());
    k
}

fn expect_addr(args: &[ArgValue], i: usize) -> Result<Address, ContractError> {
    match args.get(i) {
        Some(ArgValue::Address(a)) => Ok(*a),
        _ => Err(ContractError::InvalidArgs(format!("argument {i} must be an address"))),
    }
}

fn expect_token_id(args: &[ArgValue], i: usize) -> Result<u64, ContractError> {
    match args.get(i) {
        Some(ArgValue::U128(n)) => Ok(*n as u64),
        _ => Err(ContractError::InvalidArgs(format!("argument {i} must be a token id"))),
    }
}

pub(crate) fn call_nft(
    init: &NftInit,
    ctx: &mut CallContext,
    method: &str,
    args: &[u8],
) -> Result<CallOutcome, ContractError> {
    let mut used: Gas = 0;
    spend_gas(ctx, &mut used, gas_costs::BASE_CALL)?;
    let args = decode_args(args)?;

    match method {
        "ownerOf" => {
            let token_id = expect_token_id(&args, 0)?;
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            let owner = ctx
                .storage
                .get(&owner_key(token_id))
                .ok_or_else(|| ContractError::Reverted("token does not exist".into()))?;
            Ok(CallOutcome {
                return_data: owner.clone(),
                events: vec![],
                gas_used: used,
            })
        }
        "tokenURI" => {
            let token_id = expect_token_id(&args, 0)?;
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            let uri = ctx.storage.get(&meta_key(token_id)).cloned().unwrap_or_default();
            Ok(CallOutcome {
                return_data: uri,
                events: vec![],
                gas_used: used,
            })
        }
        "mint" => {
            if ctx.caller != init.owner {
                return Err(ContractError::Reverted("only owner may mint".into()));
            }
            let to = expect_addr(&args, 0)?;
            let uri = match args.get(1) {
                Some(ArgValue::Bytes(b)) => b.clone(),
                _ => vec![],
            };
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            let next_id = ctx
                .storage
                .get(b"next_id".as_slice())
                .map(|v| {
                    let mut buf = [0u8; 8];
                    let n = v.len().min(8);
                    buf[8 - n..].copy_from_slice(&v[v.len() - n..]);
                    u64::from_be_bytes(buf)
                })
                .unwrap_or(0);
            ctx.storage
                .insert(b"next_id".to_vec(), (next_id + 1).to_be_bytes().to_vec());
            ctx.storage.insert(owner_key(next_id), to.0.to_vec());
            ctx.storage.insert(meta_key(next_id), uri);
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE * 3)?;
            spend_gas(ctx, &mut used, gas_costs::EVENT)?;
            Ok(CallOutcome {
                return_data: next_id.to_be_bytes().to_vec(),
                events: vec![RawEvent::new(
                    "Transfer",
                    vec![address_topic(&Address::ZERO), address_topic(&to)],
                    next_id.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        "transfer" => {
            let to = expect_addr(&args, 0)?;
            let token_id = expect_token_id(&args, 1)?;
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            let current_owner = ctx
                .storage
                .get(&owner_key(token_id))
                .cloned()
                .ok_or_else(|| ContractError::Reverted("token does not exist".into()))?;
            if current_owner != ctx.caller.0 {
                return Err(ContractError::Reverted("caller does not own token".into()));
            }
            ctx.storage.insert(owner_key(token_id), to.0.to_vec());
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE)?;
            spend_gas(ctx, &mut used, gas_costs::EVENT)?;
            Ok(CallOutcome {
                return_data: vec![],
                events: vec![RawEvent::new(
                    "Transfer",
                    vec![address_topic(&ctx.caller), address_topic(&to)],
                    token_id.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        other => Err(ContractError::UnknownMethod(other.to_string())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn mint_then_transfer() {
        let owner = Address([1u8; 20]);
        let alice = Address([2u8; 20]);
        let bob = Address([3u8; 20]);
        let init = NftInit {
            name: "Test NFT".into(),
            symbol: "TNFT".into(),
            owner,
        };
        let mut storage = BTreeMap::new();
        {
            let mut ctx = CallContext {
                contract_address: Address([9u8; 20]),
                caller: owner,
                storage: &mut storage,
                block: 1,
                timestamp: 0,
                gas_limit: 1_000_000,
            };
            let args = crate::encode_args(&[
                ArgValue::Address(alice),
                ArgValue::Bytes(b"ipfs://token-1".to_vec()),
            ]);
            let outcome = call_nft(&init, &mut ctx, "mint", &args).unwrap();
            assert_eq!(outcome.return_data, 0u64.to_be_bytes().to_vec());
        }
        {
            let mut ctx = CallContext {
                contract_address: Address([9u8; 20]),
                caller: alice,
                storage: &mut storage,
                block: 1,
                timestamp: 0,
                gas_limit: 1_000_000,
            };
            let args = crate::encode_args(&[ArgValue::Address(bob), ArgValue::U128(0)]);
            call_nft(&init, &mut ctx, "transfer", &args).unwrap();
        }
        let owner_bytes = storage.get(&owner_key(0)).unwrap();
        assert_eq!(owner_bytes.as_slice(), &bob.0);
    }
}
