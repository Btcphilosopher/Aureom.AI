//! A standard demonstration token contract (section 27): balanceOf,
//! transfer, approve, allowance, transferFrom, mint, burn. This is a
//! SIMULATED TOKEN for local development and testing - it has no
//! connection to any real-world asset.

use crate::{
    decode_args, gas_costs, read_u128, spend_gas, write_u128, ArgValue, CallContext, CallOutcome,
    ContractError, RawEvent,
};
use serde::{Deserialize, Serialize};
use web3emu_types::{Address, Gas, Hash256};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenInit {
    pub name: String,
    pub symbol: String,
    pub decimals: u8,
    pub initial_supply: u128,
    pub initial_holder: Address,
    /// Only this address may `mint` or `burn` after deployment.
    pub owner: Address,
}

fn address_topic(addr: &Address) -> Hash256 {
    let mut buf = [0u8; 32];
    buf[12..].copy_from_slice(&addr.0);
    Hash256(buf)
}

fn balance_key(addr: &Address) -> Vec<u8> {
    let mut k = b"balance:".to_vec();
    k.extend_from_slice(&addr.0);
    k
}

fn allowance_key(owner: &Address, spender: &Address) -> Vec<u8> {
    let mut k = b"allowance:".to_vec();
    k.extend_from_slice(&owner.0);
    k.extend_from_slice(&spender.0);
    k
}

fn expect_addr(args: &[ArgValue], i: usize) -> Result<Address, ContractError> {
    match args.get(i) {
        Some(ArgValue::Address(a)) => Ok(*a),
        _ => Err(ContractError::InvalidArgs(format!("argument {i} must be an address"))),
    }
}

fn expect_u128(args: &[ArgValue], i: usize) -> Result<u128, ContractError> {
    match args.get(i) {
        Some(ArgValue::U128(n)) => Ok(*n),
        _ => Err(ContractError::InvalidArgs(format!("argument {i} must be a u128"))),
    }
}

/// One-time initialization, called by the execution engine right after
/// deployment (not exposed as a callable method).
pub fn initialize(init: &TokenInit, storage: &mut web3emu_account::Storage) {
    write_u128(storage, b"total_supply".to_vec(), init.initial_supply);
    write_u128(storage, balance_key(&init.initial_holder), init.initial_supply);
}

pub(crate) fn call_token(
    init: &TokenInit,
    ctx: &mut CallContext,
    method: &str,
    args: &[u8],
) -> Result<CallOutcome, ContractError> {
    let mut used: Gas = 0;
    spend_gas(ctx, &mut used, gas_costs::BASE_CALL)?;
    let args = decode_args(args)?;

    match method {
        "balanceOf" => {
            let who = expect_addr(&args, 0)?;
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            let bal = read_u128(ctx.storage, &balance_key(&who));
            Ok(CallOutcome {
                return_data: bal.to_be_bytes().to_vec(),
                events: vec![],
                gas_used: used,
            })
        }
        "allowance" => {
            let owner = expect_addr(&args, 0)?;
            let spender = expect_addr(&args, 1)?;
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            let bal = read_u128(ctx.storage, &allowance_key(&owner, &spender));
            Ok(CallOutcome {
                return_data: bal.to_be_bytes().to_vec(),
                events: vec![],
                gas_used: used,
            })
        }
        "transfer" => {
            let to = expect_addr(&args, 0)?;
            let amount = expect_u128(&args, 1)?;
            transfer_internal(ctx, &mut used, ctx.caller, to, amount)?;
            Ok(CallOutcome {
                return_data: vec![],
                events: vec![RawEvent::new(
                    "Transfer",
                    vec![address_topic(&ctx.caller), address_topic(&to)],
                    amount.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        "approve" => {
            let spender = expect_addr(&args, 0)?;
            let amount = expect_u128(&args, 1)?;
            write_u128(ctx.storage, allowance_key(&ctx.caller, &spender), amount);
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE)?;
            spend_gas(ctx, &mut used, gas_costs::EVENT)?;
            Ok(CallOutcome {
                return_data: vec![],
                events: vec![RawEvent::new(
                    "Approval",
                    vec![address_topic(&ctx.caller), address_topic(&spender)],
                    amount.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        "transferFrom" => {
            let from = expect_addr(&args, 0)?;
            let to = expect_addr(&args, 1)?;
            let amount = expect_u128(&args, 2)?;
            let allowed = read_u128(ctx.storage, &allowance_key(&from, &ctx.caller));
            spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;
            if allowed < amount {
                return Err(ContractError::Reverted("allowance exceeded".into()));
            }
            write_u128(
                ctx.storage,
                allowance_key(&from, &ctx.caller),
                allowed - amount,
            );
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE)?;
            transfer_internal(ctx, &mut used, from, to, amount)?;
            Ok(CallOutcome {
                return_data: vec![],
                events: vec![RawEvent::new(
                    "Transfer",
                    vec![address_topic(&from), address_topic(&to)],
                    amount.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        "mint" => {
            if ctx.caller != init.owner {
                return Err(ContractError::Reverted("only owner may mint".into()));
            }
            let to = expect_addr(&args, 0)?;
            let amount = expect_u128(&args, 1)?;
            let bal = read_u128(ctx.storage, &balance_key(&to));
            write_u128(ctx.storage, balance_key(&to), bal + amount);
            let supply = read_u128(ctx.storage, b"total_supply");
            write_u128(ctx.storage, b"total_supply".to_vec(), supply + amount);
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE * 2)?;
            spend_gas(ctx, &mut used, gas_costs::EVENT)?;
            Ok(CallOutcome {
                return_data: vec![],
                events: vec![RawEvent::new(
                    "Transfer",
                    vec![address_topic(&Address::ZERO), address_topic(&to)],
                    amount.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        "burn" => {
            if ctx.caller != init.owner {
                return Err(ContractError::Reverted("only owner may burn".into()));
            }
            let from = expect_addr(&args, 0)?;
            let amount = expect_u128(&args, 1)?;
            let bal = read_u128(ctx.storage, &balance_key(&from));
            if bal < amount {
                return Err(ContractError::Reverted("burn exceeds balance".into()));
            }
            write_u128(ctx.storage, balance_key(&from), bal - amount);
            let supply = read_u128(ctx.storage, b"total_supply");
            write_u128(ctx.storage, b"total_supply".to_vec(), supply - amount);
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE * 2)?;
            spend_gas(ctx, &mut used, gas_costs::EVENT)?;
            Ok(CallOutcome {
                return_data: vec![],
                events: vec![RawEvent::new(
                    "Transfer",
                    vec![address_topic(&from), address_topic(&Address::ZERO)],
                    amount.to_be_bytes().to_vec(),
                )],
                gas_used: used,
            })
        }
        other => Err(ContractError::UnknownMethod(other.to_string())),
    }
}

fn transfer_internal(
    ctx: &mut CallContext,
    used: &mut Gas,
    from: Address,
    to: Address,
    amount: u128,
) -> Result<(), ContractError> {
    let from_bal = read_u128(ctx.storage, &balance_key(&from));
    spend_gas(ctx, used, gas_costs::STORAGE_READ)?;
    if from_bal < amount {
        return Err(ContractError::Reverted("transfer exceeds balance".into()));
    }
    let to_bal = read_u128(ctx.storage, &balance_key(&to));
    write_u128(ctx.storage, balance_key(&from), from_bal - amount);
    write_u128(ctx.storage, balance_key(&to), to_bal + amount);
    spend_gas(ctx, used, gas_costs::STORAGE_WRITE * 2)?;
    spend_gas(ctx, used, gas_costs::EVENT)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ArgValue;
    use std::collections::BTreeMap;

    fn make_init() -> TokenInit {
        TokenInit {
            name: "WEB3EMU Test Token".into(),
            symbol: "W3T".into(),
            decimals: 18,
            initial_supply: 1_000_000,
            initial_holder: Address([1u8; 20]),
            owner: Address([1u8; 20]),
        }
    }

    #[test]
    fn transfer_moves_balance() {
        let init = make_init();
        let mut storage = BTreeMap::new();
        initialize(&init, &mut storage);
        let alice = Address([1u8; 20]);
        let bob = Address([2u8; 20]);
        let mut ctx = CallContext {
            contract_address: Address([9u8; 20]),
            caller: alice,
            storage: &mut storage,
            block: 1,
            timestamp: 0,
            gas_limit: 1_000_000,
        };
        let args = crate::encode_args(&[ArgValue::Address(bob), ArgValue::U128(100)]);
        call_token(&init, &mut ctx, "transfer", &args).unwrap();
        assert_eq!(read_u128(ctx.storage, &balance_key(&alice)), 999_900);
        assert_eq!(read_u128(ctx.storage, &balance_key(&bob)), 100);
    }

    #[test]
    fn transfer_beyond_balance_reverts() {
        let init = make_init();
        let mut storage = BTreeMap::new();
        initialize(&init, &mut storage);
        let alice = Address([1u8; 20]);
        let bob = Address([2u8; 20]);
        let mut ctx = CallContext {
            contract_address: Address([9u8; 20]),
            caller: bob,
            storage: &mut storage,
            block: 1,
            timestamp: 0,
            gas_limit: 1_000_000,
        };
        let args = crate::encode_args(&[ArgValue::Address(alice), ArgValue::U128(1)]);
        assert!(call_token(&init, &mut ctx, "transfer", &args).is_err());
    }

    #[test]
    fn only_owner_may_mint() {
        let init = make_init();
        let mut storage = BTreeMap::new();
        initialize(&init, &mut storage);
        let bob = Address([2u8; 20]);
        let mut ctx = CallContext {
            contract_address: Address([9u8; 20]),
            caller: bob,
            storage: &mut storage,
            block: 1,
            timestamp: 0,
            gas_limit: 1_000_000,
        };
        let args = crate::encode_args(&[ArgValue::Address(bob), ArgValue::U128(1)]);
        assert!(call_token(&init, &mut ctx, "mint", &args).is_err());
    }
}
