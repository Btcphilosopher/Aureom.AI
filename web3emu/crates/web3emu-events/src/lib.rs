//! web3emu-events
//!
//! Contract event logs (section 30). Emitted by the execution engine
//! during a state transition and attached to the transaction receipt.

use serde::{Deserialize, Serialize};
use web3emu_types::{Address, BlockHeight, Hash256};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EventLog {
    pub contract: Address,
    pub event_name: String,
    /// Indexed topics, analogous to indexed event parameters in common
    /// Web3 event models. Topic 0 is conventionally a hash of the event
    /// signature; see `web3emu-contract`.
    pub topics: Vec<Hash256>,
    /// ABI-agnostic event payload. WEB3EMU does not currently implement
    /// ABI encoding - payloads are the contract runtime's own
    /// serialization (JSON bytes for the native runtime).
    pub data: Vec<u8>,
    pub block: BlockHeight,
    pub transaction: Hash256,
    pub log_index: u64,
}

/// A simple filter, modeled after `eth_getLogs` parameters (section 34).
#[derive(Debug, Clone, Default)]
pub struct EventFilter {
    pub contract: Option<Address>,
    pub event_name: Option<String>,
    pub from_block: Option<BlockHeight>,
    pub to_block: Option<BlockHeight>,
    pub topics: Vec<Hash256>,
}

impl EventFilter {
    pub fn matches(&self, log: &EventLog) -> bool {
        if let Some(c) = self.contract {
            if c != log.contract {
                return false;
            }
        }
        if let Some(name) = &self.event_name {
            if name != &log.event_name {
                return false;
            }
        }
        if let Some(from) = self.from_block {
            if log.block < from {
                return false;
            }
        }
        if let Some(to) = self.to_block {
            if log.block > to {
                return false;
            }
        }
        if !self.topics.is_empty() && !self.topics.iter().all(|t| log.topics.contains(t)) {
            return false;
        }
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_log(block: BlockHeight) -> EventLog {
        EventLog {
            contract: Address([1u8; 20]),
            event_name: "Transfer".into(),
            topics: vec![Hash256([2u8; 32])],
            data: vec![],
            block,
            transaction: Hash256::ZERO,
            log_index: 0,
        }
    }

    #[test]
    fn filter_by_block_range() {
        let log = sample_log(10);
        let filter = EventFilter {
            from_block: Some(5),
            to_block: Some(9),
            ..Default::default()
        };
        assert!(!filter.matches(&log));
        let filter2 = EventFilter {
            from_block: Some(5),
            to_block: Some(10),
            ..Default::default()
        };
        assert!(filter2.matches(&log));
    }

    #[test]
    fn filter_by_event_name() {
        let log = sample_log(1);
        let filter = EventFilter {
            event_name: Some("Approval".into()),
            ..Default::default()
        };
        assert!(!filter.matches(&log));
    }
}
