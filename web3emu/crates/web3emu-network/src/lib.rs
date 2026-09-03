//! web3emu-network
//!
//! A network *impairment* simulator for a single logical node (sections
//! 41-42, narrowed). Given a seed, it deterministically decides whether
//! a simulated message is delayed, jittered, or dropped.
//!
//! # Scope
//!
//! This crate does NOT implement multi-node simulation (section 40),
//! peer-to-peer message propagation between distinct node processes
//! (section 70), or chain reorganisation (section 72). Those are
//! explicitly tracked as roadmap items in `docs/ARCHITECTURE.md` and are
//! not faked here - `NetworkSimulator` only models the *observable
//! symptoms* (latency, jitter, packet loss, and a few named "chaos"
//! toggles) that a single local node's RPC/mempool would show under
//! imperfect network conditions, which is enough to exercise how a
//! frontend or wallet reacts to a flaky connection.

use rand::Rng;
use rand_chacha::rand_core::SeedableRng;
use rand_chacha::ChaCha20Rng;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct NetworkConfig {
    pub base_latency_ms: u64,
    pub jitter_ms: u64,
    pub packet_loss_percent: f32,
    pub seed: u64,
}

impl Default for NetworkConfig {
    fn default() -> Self {
        NetworkConfig {
            base_latency_ms: 0,
            jitter_ms: 0,
            packet_loss_percent: 0.0,
            seed: 0,
        }
    }
}

/// Named, deterministic-when-seeded failure conditions (section 42,
/// scoped to what a single-node simulator can meaningfully model).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ChaosMode {
    None,
    NodeOffline,
    RpcUnavailable,
    TransactionDelayed,
    TransactionDropped,
}

#[derive(Debug, Clone)]
pub struct NetworkSimulator {
    config: NetworkConfig,
    rng: ChaCha20Rng,
    pub chaos: ChaosMode,
}

/// The outcome of attempting to deliver one simulated message (a
/// transaction reaching the mempool, an event reaching a subscriber,
/// etc.).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Delivery {
    Delivered { delay_ms: u64 },
    Dropped,
    Unavailable,
}

impl NetworkSimulator {
    pub fn new(config: NetworkConfig) -> Self {
        NetworkSimulator {
            rng: ChaCha20Rng::seed_from_u64(config.seed),
            config,
            chaos: ChaosMode::None,
        }
    }

    pub fn set_chaos(&mut self, mode: ChaosMode) {
        self.chaos = mode;
    }

    /// Decide the fate of one simulated message. Deterministic given the
    /// same seed and the same sequence of calls.
    pub fn deliver(&mut self) -> Delivery {
        match self.chaos {
            ChaosMode::NodeOffline | ChaosMode::RpcUnavailable => return Delivery::Unavailable,
            ChaosMode::TransactionDropped => return Delivery::Dropped,
            ChaosMode::None | ChaosMode::TransactionDelayed => {}
        }

        if self.config.packet_loss_percent > 0.0 {
            let roll: f32 = self.rng.gen_range(0.0..100.0);
            if roll < self.config.packet_loss_percent {
                return Delivery::Dropped;
            }
        }

        let jitter = if self.config.jitter_ms > 0 {
            self.rng.gen_range(0..=self.config.jitter_ms)
        } else {
            0
        };
        let extra = if self.chaos == ChaosMode::TransactionDelayed {
            self.config.base_latency_ms.max(1) * 10
        } else {
            0
        };
        Delivery::Delivered {
            delay_ms: self.config.base_latency_ms + jitter + extra,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_seed_same_sequence() {
        let cfg = NetworkConfig {
            base_latency_ms: 10,
            jitter_ms: 5,
            packet_loss_percent: 20.0,
            seed: 42,
        };
        let mut a = NetworkSimulator::new(cfg);
        let mut b = NetworkSimulator::new(cfg);
        let seq_a: Vec<Delivery> = (0..20).map(|_| a.deliver()).collect();
        let seq_b: Vec<Delivery> = (0..20).map(|_| b.deliver()).collect();
        assert_eq!(seq_a, seq_b);
    }

    #[test]
    fn zero_loss_never_drops() {
        let cfg = NetworkConfig {
            base_latency_ms: 5,
            jitter_ms: 0,
            packet_loss_percent: 0.0,
            seed: 1,
        };
        let mut sim = NetworkSimulator::new(cfg);
        for _ in 0..50 {
            assert!(matches!(sim.deliver(), Delivery::Delivered { .. }));
        }
    }

    #[test]
    fn node_offline_always_unavailable() {
        let mut sim = NetworkSimulator::new(NetworkConfig::default());
        sim.set_chaos(ChaosMode::NodeOffline);
        assert_eq!(sim.deliver(), Delivery::Unavailable);
    }
}
