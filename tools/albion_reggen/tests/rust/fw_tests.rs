// Behavioural tests of the generated Rust API (kitchen-sink map) against a mock RegBus.
use super::sf_regs as regs;
use regs::{Error, FieldOverflow, IndexError, RegBus};
use std::cell::RefCell;
use std::collections::HashMap;

#[derive(Default)]
struct Mock {
    mem: RefCell<HashMap<u64, u32>>,
    log: RefCell<Vec<(u64, bool, u32)>>, // (addr, is_write, value) of 32-bit accesses
    script: RefCell<HashMap<u64, Vec<u32>>>,
}

impl Mock {
    fn put(&self, a: u64, v: u32) {
        self.mem.borrow_mut().insert(a, v);
    }
    fn writes(&self) -> Vec<(u64, u32)> {
        self.log.borrow().iter().filter(|e| e.1).map(|e| (e.0, e.2)).collect()
    }
    fn reads(&self) -> usize {
        self.log.borrow().iter().filter(|e| !e.1).count()
    }
}

impl RegBus for Mock {
    fn read32(&self, addr: u64) -> u32 {
        assert_eq!(addr % 4, 0, "misaligned 32-bit access");
        let mut v = *self.mem.borrow().get(&addr).unwrap_or(&0);
        if let Some(s) = self.script.borrow_mut().get_mut(&addr) {
            if !s.is_empty() {
                v = s.remove(0);
            }
        }
        self.log.borrow_mut().push((addr, false, v));
        v
    }
    fn write32(&self, addr: u64, value: u32) {
        assert_eq!(addr % 4, 0, "misaligned 32-bit access");
        self.log.borrow_mut().push((addr, true, value));
        self.mem.borrow_mut().insert(addr, value);
    }
}

#[test]
fn rmw_does_not_clear_a_w1c_flag() {
    let bus = Mock::default();
    bus.put(regs::ks_a::mixed::ADDR, 0x109); // EN = 9, FLAG = 1
    regs::ks_a::mixed::set_en(&bus, 5).unwrap();
    assert_eq!(bus.writes().last().unwrap(), &(regs::ks_a::mixed::ADDR, 0x005));
}

#[test]
fn clear_preserves_rw_bits() {
    let bus = Mock::default();
    bus.put(regs::ks_a::mixed::ADDR, 0x109);
    regs::ks_a::mixed::clear_flag(&bus, 1).unwrap();
    assert_eq!(bus.writes().last().unwrap().1, 0x109);
}

#[test]
fn write_one_only_registers_are_not_read_back() {
    let bus = Mock::default();
    regs::ks_a::flags::clear_c_hw(&bus, 0x3).unwrap();
    regs::ks_a::flags::raise_s_hw(&bus, 0x1).unwrap();
    assert_eq!(bus.writes(), vec![(regs::ks_a::flags::ADDR, 0x3), (regs::ks_a::flags::ADDR, 0x1000)]);
    assert_eq!(bus.reads(), 0);
}

#[test]
fn rw_and_pulse_in_one_register() {
    let bus = Mock::default();
    bus.put(regs::ks_a::gated::ADDR, 0x1BEEF);
    regs::ks_a::gated::pulse_kick(&bus, 1).unwrap();
    assert_eq!(bus.writes().last().unwrap().1, 0x1BEEF);
    let bus = Mock::default();
    bus.put(regs::ks_a::gated::ADDR, 0x1BEEF);
    regs::ks_a::gated::set_data(&bus, 0x1234).unwrap();
    assert_eq!(bus.writes().last().unwrap().1, 0x1234);
}

#[test]
fn values_that_do_not_fit_are_rejected_not_truncated() {
    let bus = Mock::default();
    let e = regs::ks_a::mixed::set_en(&bus, 16).unwrap_err();
    assert_eq!(e, Error::Overflow(FieldOverflow { field: "EN", value: 16, max: 15 }));
    assert!(bus.writes().is_empty(), "nothing is written when the value is rejected");
    assert!(regs::ks_a::mixed::Value(0).with_en(15).is_ok());
    assert!(regs::ks_a::mixed::Value(0).with_en(16).is_err());
    assert!(regs::ks_a::flags::clear_c_hw(&bus, 16).is_err());
}

#[test]
fn array_indices_are_checked() {
    let bus = Mock::default();
    assert!(regs::ks_a::word::read(&bus, 3).is_ok());
    assert_eq!(regs::ks_a::word::read(&bus, 4).unwrap_err(), Error::Index(IndexError { index: 4, count: 4 }));
    assert_eq!(regs::ks_a::word::addr(3).unwrap(), regs::ks_a::word::ADDR + 12);
    assert_eq!(regs::ks_a::arr::addr(2).unwrap(), regs::ks_a::arr::ADDR + 16); // stride 8
    assert!(regs::ks_a::word::write(&bus, 9, regs::ks_a::word::Value(1)).is_err());
}

#[test]
fn field_accessors_and_reset_constants() {
    let v = regs::ks_a::rwmix::Value::RESET;
    assert_eq!(v.raw(), 0x00A5_2211);
    assert_eq!(v.f_hw(), 0x11);
    assert_eq!(v.f_sw(), 0x22);
    assert_eq!(v.f_plain(), 0xA5);
    let v = v.with_f_top(0xAB).unwrap();
    assert_eq!(v.raw(), 0xABA5_2211);
    assert_eq!(regs::ks_a::rwmix::RESET, 0x00A5_2211);
}

#[test]
fn sixty_four_bit_registers_split_low_word_first() {
    let bus = Mock::default();
    regs::ks_c::big::write(&bus, regs::ks_c::big::Value(0x1122_3344_5566_7788));
    assert_eq!(bus.writes(), vec![(regs::ks_c::big::ADDR, 0x5566_7788), (regs::ks_c::big::ADDR + 4, 0x1122_3344)]);
    assert_eq!(regs::ks_c::big::read(&bus).0, 0x1122_3344_5566_7788);
}

#[test]
fn a_rolling_counter_never_tears() {
    let bus = Mock::default();
    let a = regs::ks_c::cnt::addr(1).unwrap();
    bus.script.borrow_mut().insert(a + 4, vec![0, 1, 1, 1]);
    bus.script.borrow_mut().insert(a, vec![0xFFFF_FFFE, 3]);
    assert_eq!(regs::ks_c::cnt::read(&bus, 1).unwrap().0, 0x1_0000_0003);
    assert_eq!(bus.reads(), 6); // hi lo hi (mismatch) hi lo hi
}

#[test]
fn every_access_is_naturally_aligned() {
    let bus = Mock::default();
    regs::ks_a::mixed::set_en(&bus, 1).unwrap();
    regs::ks_c::big::write(&bus, regs::ks_c::big::Value(1));
    let _ = regs::ks_c::cnt::read(&bus, 2);
    regs::ks_a::word::write(&bus, 2, regs::ks_a::word::Value(7)).unwrap();
    let _ = regs::ks_a::arr::read(&bus, 1);
    assert!(bus.log.borrow().iter().all(|e| e.0 % 4 == 0)); // the Mock itself asserts this too
}

#[test]
fn mmio_refuses_misaligned_addresses_before_touching_memory() {
    use regs::Mmio;
    let m = unsafe { Mmio::new() };
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| m.read32(0x1001)));
    assert!(r.is_err(), "a misaligned access must panic, not dereference");
    let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| m.write32(0x1002, 0)));
    assert!(r.is_err());
}

#[test]
fn registers_are_independent_of_each_other() {
    // writing one array element does not touch its neighbours
    let bus = Mock::default();
    regs::ks_a::word::write(&bus, 1, regs::ks_a::word::Value(0xDEAD_BEEF)).unwrap();
    assert_eq!(bus.writes(), vec![(regs::ks_a::word::ADDR + 4, 0xDEAD_BEEF)]);
}
