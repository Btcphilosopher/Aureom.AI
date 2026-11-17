use super::sf_regs as regs;
use regs::RegBus;
use std::cell::Cell;

struct Hash(Cell<u64>);
impl RegBus for Hash {
    fn read32(&self, addr: u64) -> u32 {
        if addr == regs::sysid::regmap_hash::ADDR { self.0.get() as u32 } else { (self.0.get() >> 32) as u32 }
    }
    fn write32(&self, _a: u64, _v: u32) {}
}

#[test]
fn hardware_matches_only_the_hash_it_was_built_from() {
    let bus = Hash(Cell::new(regs::MAP_HASH));
    assert!(regs::hardware_matches(&bus));
    bus.0.set(regs::MAP_HASH ^ (1 << 40));
    assert!(!regs::hardware_matches(&bus));
    bus.0.set(regs::MAP_HASH ^ 1);
    assert!(!regs::hardware_matches(&bus));
}
