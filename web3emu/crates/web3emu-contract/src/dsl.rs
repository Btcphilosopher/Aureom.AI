//! Level-1 contract DSL (section 26, section 68 Level 1): a narrow,
//! deliberately small grammar for single-integer-field "counter" style
//! contracts, matching the example in the spec exactly:
//!
//! ```text
//! contract Counter
//! state:
//!     value: integer
//! method:
//!     increment()
//! method:
//!     decrement()
//! method:
//!     get()
//! event:
//!     CounterChanged(value)
//! ```
//!
//! This is intentionally NOT a general-purpose language. It supports
//! exactly one state field (`integer`) and exactly the three method
//! names `increment`, `decrement`, `get`, with `decrement` saturating at
//! zero rather than underflowing. See `docs/CONTRACTS.md` for the full
//! grammar and its limits.

use crate::{gas_costs, spend_gas, CallContext, CallOutcome, ContractError, ContractInit, RawEvent};
use serde::{Deserialize, Serialize};
use web3emu_types::Gas;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CounterSpec {
    pub contract_name: String,
    pub field: String,
    pub event: String,
}

#[derive(Debug, thiserror::Error)]
pub enum DslError {
    #[error("expected 'contract <Name>' as the first non-empty line")]
    MissingContractHeader,
    #[error("expected a 'state:' block declaring exactly one integer field")]
    InvalidStateBlock,
    #[error("only 'increment()', 'decrement()' and 'get()' methods are supported in Level 1")]
    UnsupportedMethod(String),
    #[error("expected an 'event:' block referencing the declared state field")]
    InvalidEventBlock,
}

/// Compile Level-1 DSL source into a `ContractInit` ready to deploy.
pub fn compile(source: &str) -> Result<ContractInit, DslError> {
    let lines: Vec<&str> = source
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .collect();
    let mut i = 0;

    let contract_name = lines
        .get(i)
        .and_then(|l| l.strip_prefix("contract "))
        .map(str::trim)
        .ok_or(DslError::MissingContractHeader)?
        .to_string();
    i += 1;

    if lines.get(i) != Some(&"state:") {
        return Err(DslError::InvalidStateBlock);
    }
    i += 1;
    let field_line = lines.get(i).ok_or(DslError::InvalidStateBlock)?;
    let (field, ty) = field_line
        .split_once(':')
        .map(|(f, t)| (f.trim(), t.trim().trim_end_matches(char::is_whitespace)))
        .ok_or(DslError::InvalidStateBlock)?;
    if ty != "integer" {
        return Err(DslError::InvalidStateBlock);
    }
    let field = field.to_string();
    i += 1;

    let mut seen_methods = std::collections::BTreeSet::new();
    while lines.get(i) == Some(&"method:") {
        i += 1;
        let m = lines.get(i).ok_or(DslError::InvalidStateBlock)?;
        let name = m.trim_end_matches("()").trim();
        if !matches!(name, "increment" | "decrement" | "get") {
            return Err(DslError::UnsupportedMethod(name.to_string()));
        }
        seen_methods.insert(name.to_string());
        i += 1;
    }

    if lines.get(i) != Some(&"event:") {
        return Err(DslError::InvalidEventBlock);
    }
    i += 1;
    let event_line = lines.get(i).ok_or(DslError::InvalidEventBlock)?;
    let open = event_line.find('(').ok_or(DslError::InvalidEventBlock)?;
    let event_name = event_line[..open].trim().to_string();
    let arg = event_line[open + 1..]
        .trim_end_matches(')')
        .trim()
        .to_string();
    if arg != field {
        return Err(DslError::InvalidEventBlock);
    }

    Ok(ContractInit::Counter(CounterSpec {
        contract_name,
        field,
        event: event_name,
    }))
}

pub(crate) fn call_counter(
    spec: &CounterSpec,
    ctx: &mut CallContext,
    method: &str,
    _args: &[u8],
) -> Result<CallOutcome, ContractError> {
    let mut used: Gas = 0;
    spend_gas(ctx, &mut used, gas_costs::BASE_CALL)?;

    let key = spec.field.as_bytes().to_vec();
    let current = ctx
        .storage
        .get(&key)
        .map(|v| {
            let mut buf = [0u8; 8];
            let n = v.len().min(8);
            buf[8 - n..].copy_from_slice(&v[v.len() - n..]);
            u64::from_be_bytes(buf)
        })
        .unwrap_or(0);
    spend_gas(ctx, &mut used, gas_costs::STORAGE_READ)?;

    match method {
        "get" => Ok(CallOutcome {
            return_data: current.to_be_bytes().to_vec(),
            events: vec![],
            gas_used: used,
        }),
        "increment" | "decrement" => {
            let next = if method == "increment" {
                current.saturating_add(1)
            } else {
                current.saturating_sub(1)
            };
            ctx.storage.insert(key, next.to_be_bytes().to_vec());
            spend_gas(ctx, &mut used, gas_costs::STORAGE_WRITE)?;
            spend_gas(ctx, &mut used, gas_costs::EVENT)?;
            let event = RawEvent::new(&spec.event, vec![], next.to_be_bytes().to_vec());
            Ok(CallOutcome {
                return_data: next.to_be_bytes().to_vec(),
                events: vec![event],
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
    use web3emu_types::Address;

    const SOURCE: &str = "
        contract Counter
        state:
            value: integer
        method:
            increment()
        method:
            decrement()
        method:
            get()
        event:
            CounterChanged(value)
    ";

    #[test]
    fn compiles_the_spec_example() {
        let init = compile(SOURCE).unwrap();
        match init {
            ContractInit::Counter(spec) => {
                assert_eq!(spec.contract_name, "Counter");
                assert_eq!(spec.field, "value");
                assert_eq!(spec.event, "CounterChanged");
            }
            _ => panic!("expected Counter"),
        }
    }

    #[test]
    fn increment_then_get_round_trips() {
        let init = compile(SOURCE).unwrap();
        let ContractInit::Counter(spec) = init else {
            panic!()
        };
        let mut storage = BTreeMap::new();
        let addr = Address([1u8; 20]);
        let mut ctx = CallContext {
            contract_address: addr,
            caller: addr,
            storage: &mut storage,
            block: 1,
            timestamp: 0,
            gas_limit: 100_000,
        };
        call_counter(&spec, &mut ctx, "increment", &[]).unwrap();
        call_counter(&spec, &mut ctx, "increment", &[]).unwrap();
        let outcome = call_counter(&spec, &mut ctx, "get", &[]).unwrap();
        assert_eq!(u64::from_be_bytes(outcome.return_data.try_into().unwrap()), 2);
    }

    #[test]
    fn rejects_unsupported_method_names() {
        let bad = SOURCE.replace("increment()", "reset()");
        assert!(compile(&bad).is_err());
    }
}
