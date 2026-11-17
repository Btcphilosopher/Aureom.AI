// sf_regs.rs - register definitions and safe accessors
// GENERATED FILE - DO NOT EDIT.  Edit the register definition instead.
// generator       : albion_reggen 1.0.0 (definition schema 1)
// register map    : silicaflux_regs v1.0
// semantic hash   : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
// definition hash : 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba

//! Register map `silicaflux_regs`. Include with `mod sf_regs;`.

#![allow(dead_code, unused_imports)]

/// A field value does not fit the field.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldOverflow {
    pub field: &'static str,
    pub value: u64,
    pub max: u64,
}

/// An array register index is out of range.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IndexError {
    pub index: usize,
    pub count: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error {
    Overflow(FieldOverflow),
    Index(IndexError),
}

impl From<FieldOverflow> for Error {
    fn from(e: FieldOverflow) -> Self {
        Error::Overflow(e)
    }
}

impl From<IndexError> for Error {
    fn from(e: IndexError) -> Self {
        Error::Index(e)
    }
}

/// A register bus.  Addresses are 64-bit bus addresses; 32-bit registers are accessed with one
/// naturally aligned 32-bit access.  The 64-bit operations have default implementations made of
/// two 32-bit accesses (two bus transactions: not atomic).  `read64_stable` re-reads until the
/// high word is stable, which is what a free-running counter needs.
pub trait RegBus {
    fn read32(&self, addr: u64) -> u32;
    fn write32(&self, addr: u64, value: u32);

    fn read64(&self, addr: u64) -> u64 {
        let lo = self.read32(addr) as u64;
        let hi = self.read32(addr + 4) as u64;
        (hi << 32) | lo
    }

    fn read64_stable(&self, addr: u64) -> u64 {
        loop {
            let hi = self.read32(addr + 4);
            let lo = self.read32(addr);
            if self.read32(addr + 4) == hi {
                return ((hi as u64) << 32) | lo as u64;
            }
        }
    }

    fn write64(&self, addr: u64, value: u64) {
        self.write32(addr, value as u32);
        self.write32(addr + 4, (value >> 32) as u32);
    }
}

/// Memory-mapped register access: one volatile, naturally aligned access per call.
pub struct Mmio {
    _private: (),
}

impl Mmio {
    /// # Safety
    /// The caller guarantees that every register address of this map is mapped at its bus address
    /// in the current address space, that accessing it has only the documented hardware effects,
    /// and that no other code races on these registers in a way the hardware does not allow.
    pub const unsafe fn new() -> Self {
        Mmio { _private: () }
    }

    fn ptr<T>(addr: u64) -> *mut T {
        let a = usize::try_from(addr).expect("register address does not fit a pointer");
        assert!(a % core::mem::align_of::<T>() == 0, "misaligned register access");
        a as *mut T
    }
}

impl RegBus for Mmio {
    fn read32(&self, addr: u64) -> u32 {
        // SAFETY: Mmio::new's contract; the pointer is aligned and fits usize (checked in ptr).
        unsafe { core::ptr::read_volatile(Self::ptr::<u32>(addr)) }
    }

    fn write32(&self, addr: u64, value: u32) {
        // SAFETY: as above.
        unsafe { core::ptr::write_volatile(Self::ptr::<u32>(addr), value) }
    }

    #[cfg(target_pointer_width = "64")]
    fn read64(&self, addr: u64) -> u64 {
        // SAFETY: as above; 8-byte alignment is checked in ptr.
        unsafe { core::ptr::read_volatile(Self::ptr::<u64>(addr)) }
    }

    #[cfg(target_pointer_width = "64")]
    fn read64_stable(&self, addr: u64) -> u64 {
        self.read64(addr)
    }

    #[cfg(target_pointer_width = "64")]
    fn write64(&self, addr: u64, value: u64) {
        // SAFETY: as above.
        unsafe { core::ptr::write_volatile(Self::ptr::<u64>(addr), value) }
    }
}

/// Address, width and reset value of every register instance (array elements expanded).
#[derive(Debug, Clone, Copy)]
pub struct RegInfo {
    pub periph: &'static str,
    pub name: &'static str,
    pub addr: u64,
    pub width: u32,
    pub reset: u64,
}

#[derive(Debug, Clone, Copy)]
pub struct PeriphInfo {
    pub name: &'static str,
    pub base: u64,
    pub size: u64,
}

pub const MAP_NAME: &str = "silicaflux_regs";
pub const VERSION: (u16, u16) = (1, 0);
/// Equals the value of SYSID.REGMAP_HASH in hardware built from this definition.
pub const MAP_HASH: u64 = 0x99481283139d2dc0;
pub const SEMANTIC_HASH: &str = "99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39";
pub const DEFINITION_HASH: &str = "322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba";

pub const PERIPHS: &[PeriphInfo] = &[
    PeriphInfo { name: "dma", base: 0x120000000, size: 0x1000 },
    PeriphInfo { name: "tensor", base: 0x150000000, size: 0x1000 },
    PeriphInfo { name: "vector", base: 0x150001000, size: 0x1000 },
    PeriphInfo { name: "perf", base: 0x170000000, size: 0x1000 },
    PeriphInfo { name: "sysid", base: 0x180000000, size: 0x1000 },
    PeriphInfo { name: "intc", base: 0x180001000, size: 0x1000 },
    PeriphInfo { name: "clkrst", base: 0x180002000, size: 0x1000 },
    PeriphInfo { name: "sramc", base: 0x180003000, size: 0x1000 },
];

pub const REGS: &[RegInfo] = &[
    RegInfo { periph: "dma", name: "SRC", addr: 0x120000000, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "DST", addr: 0x120000004, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "LEN", addr: 0x120000008, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "TAG", addr: 0x12000000c, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "CTRL", addr: 0x120000010, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "START", addr: 0x120000014, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "STATUS", addr: 0x120000018, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "BYTES_DONE", addr: 0x12000001c, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "CPL_STATUS", addr: 0x120000020, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "CPL_ERR_ADDR", addr: 0x120000024, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "CPL_BYTES", addr: 0x120000028, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "CPL_POP", addr: 0x12000002c, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_CTRL", addr: 0x120000030, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "INT_ENABLE", addr: 0x120000034, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "INT_STATUS", addr: 0x120000038, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_0", addr: 0x120000040, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_1", addr: 0x120000044, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_2", addr: 0x120000048, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_3", addr: 0x12000004c, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_4", addr: 0x120000050, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_5", addr: 0x120000054, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_6", addr: 0x120000058, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_7", addr: 0x12000005c, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_8", addr: 0x120000060, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_9", addr: 0x120000064, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_10", addr: 0x120000068, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_11", addr: 0x12000006c, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_12", addr: 0x120000070, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_13", addr: 0x120000074, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_14", addr: 0x120000078, width: 32, reset: 0x0 },
    RegInfo { periph: "dma", name: "PERF_15", addr: 0x12000007c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "ID", addr: 0x150000000, width: 32, reset: 0x53465443 },
    RegInfo { periph: "tensor", name: "INFO", addr: 0x150000004, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CAPS", addr: 0x150000008, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "OPBUF", addr: 0x15000000c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "MEM_LO", addr: 0x150000010, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "MEM_LAST", addr: 0x150000014, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CTRL", addr: 0x150000018, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "STATUS", addr: 0x15000001c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "INT_ENABLE", addr: 0x150000020, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "INT_STATUS", addr: 0x150000024, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "SUBMITTED", addr: 0x150000028, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "KMAX", addr: 0x15000002c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_0", addr: 0x150000040, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_1", addr: 0x150000044, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_2", addr: 0x150000048, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_3", addr: 0x15000004c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_4", addr: 0x150000050, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_5", addr: 0x150000054, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_6", addr: 0x150000058, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_7", addr: 0x15000005c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_8", addr: 0x150000060, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_9", addr: 0x150000064, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_10", addr: 0x150000068, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DESC_11", addr: 0x15000006c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DOORBELL", addr: 0x150000070, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_0", addr: 0x150000080, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_1", addr: 0x150000084, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_2", addr: 0x150000088, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_3", addr: 0x15000008c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_4", addr: 0x150000090, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_5", addr: 0x150000094, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "CPL_POP", addr: 0x150000098, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_0", addr: 0x150000100, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_1", addr: 0x150000104, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_2", addr: 0x150000108, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_3", addr: 0x15000010c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_4", addr: 0x150000110, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_5", addr: 0x150000114, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_6", addr: 0x150000118, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_7", addr: 0x15000011c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_8", addr: 0x150000120, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_9", addr: 0x150000124, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_10", addr: 0x150000128, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_11", addr: 0x15000012c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_12", addr: 0x150000130, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_13", addr: 0x150000134, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_14", addr: 0x150000138, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_15", addr: 0x15000013c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_16", addr: 0x150000140, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_17", addr: 0x150000144, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_18", addr: 0x150000148, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "PERF_19", addr: 0x15000014c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_0", addr: 0x150000200, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_1", addr: 0x150000204, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_2", addr: 0x150000208, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_3", addr: 0x15000020c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_4", addr: 0x150000210, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_5", addr: 0x150000214, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_6", addr: 0x150000218, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_7", addr: 0x15000021c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_8", addr: 0x150000220, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_9", addr: 0x150000224, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_10", addr: 0x150000228, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_11", addr: 0x15000022c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_12", addr: 0x150000230, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_13", addr: 0x150000234, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_14", addr: 0x150000238, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_15", addr: 0x15000023c, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_16", addr: 0x150000240, width: 32, reset: 0x0 },
    RegInfo { periph: "tensor", name: "DMA_PERF_17", addr: 0x150000244, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "ID", addr: 0x150001000, width: 32, reset: 0x53464351 },
    RegInfo { periph: "vector", name: "INFO", addr: 0x150001004, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "CTRL", addr: 0x150001008, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "STATUS", addr: 0x15000100c, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "INT_ENABLE", addr: 0x150001010, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "INT_STATUS", addr: 0x150001014, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "SUBMITTED", addr: 0x150001018, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_0", addr: 0x150001020, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_1", addr: 0x150001024, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_2", addr: 0x150001028, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_3", addr: 0x15000102c, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_4", addr: 0x150001030, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_5", addr: 0x150001034, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_6", addr: 0x150001038, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DESC_7", addr: 0x15000103c, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "DOORBELL", addr: 0x150001040, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "CPL_0", addr: 0x150001050, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "CPL_1", addr: 0x150001054, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "CPL_2", addr: 0x150001058, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "CPL_3", addr: 0x15000105c, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "CPL_POP", addr: 0x150001060, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_0", addr: 0x150001080, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_1", addr: 0x150001084, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_2", addr: 0x150001088, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_3", addr: 0x15000108c, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_4", addr: 0x150001090, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_5", addr: 0x150001094, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_6", addr: 0x150001098, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_7", addr: 0x15000109c, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_8", addr: 0x1500010a0, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_9", addr: 0x1500010a4, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_10", addr: 0x1500010a8, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_11", addr: 0x1500010ac, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_12", addr: 0x1500010b0, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_13", addr: 0x1500010b4, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_14", addr: 0x1500010b8, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_15", addr: 0x1500010bc, width: 32, reset: 0x0 },
    RegInfo { periph: "vector", name: "PERF_16", addr: 0x1500010c0, width: 32, reset: 0x0 },
    RegInfo { periph: "perf", name: "CTRL", addr: 0x170000000, width: 32, reset: 0x0 },
    RegInfo { periph: "perf", name: "STATUS", addr: 0x170000004, width: 32, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_0", addr: 0x170000100, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_1", addr: 0x170000108, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_2", addr: 0x170000110, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_3", addr: 0x170000118, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_4", addr: 0x170000120, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_5", addr: 0x170000128, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_6", addr: 0x170000130, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_7", addr: 0x170000138, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_8", addr: 0x170000140, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_9", addr: 0x170000148, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_10", addr: 0x170000150, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_11", addr: 0x170000158, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_12", addr: 0x170000160, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_13", addr: 0x170000168, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_14", addr: 0x170000170, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_15", addr: 0x170000178, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_16", addr: 0x170000180, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_17", addr: 0x170000188, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_18", addr: 0x170000190, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_19", addr: 0x170000198, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_20", addr: 0x1700001a0, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_21", addr: 0x1700001a8, width: 64, reset: 0x0 },
    RegInfo { periph: "perf", name: "CNT_22", addr: 0x1700001b0, width: 64, reset: 0x0 },
    RegInfo { periph: "sysid", name: "ID", addr: 0x180000000, width: 32, reset: 0x53464c58 },
    RegInfo { periph: "sysid", name: "REGMAP_VERSION", addr: 0x180000004, width: 32, reset: 0x10000 },
    RegInfo { periph: "sysid", name: "ALP_VERSION", addr: 0x180000008, width: 32, reset: 0x1 },
    RegInfo { periph: "sysid", name: "LIB_VERSION", addr: 0x18000000c, width: 32, reset: 0x100 },
    RegInfo { periph: "sysid", name: "ALP_CAPS", addr: 0x180000010, width: 64, reset: 0x1040488000020003 },
    RegInfo { periph: "sysid", name: "REGMAP_HASH", addr: 0x180000018, width: 64, reset: 0x99481283139d2dc0 },
    RegInfo { periph: "sysid", name: "BUILD_ID", addr: 0x180000020, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "PENDING", addr: 0x180001000, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "ENABLE", addr: 0x180001004, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "CLAIM", addr: 0x180001008, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "SWPEND", addr: 0x18000100c, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "THRESHOLD", addr: 0x180001010, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "ACTIVE", addr: 0x180001014, width: 32, reset: 0x0 },
    RegInfo { periph: "intc", name: "PRIO0", addr: 0x180001020, width: 32, reset: 0x11111111 },
    RegInfo { periph: "intc", name: "PRIO1", addr: 0x180001024, width: 32, reset: 0x11111111 },
    RegInfo { periph: "clkrst", name: "ID", addr: 0x180002000, width: 32, reset: 0x53464354 },
    RegInfo { periph: "clkrst", name: "CONFIG", addr: 0x180002004, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "STATUS", addr: 0x180002008, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "CAUSE", addr: 0x18000200c, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "RST_INFO", addr: 0x180002010, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "CLK_EN", addr: 0x180002018, width: 32, reset: 0xff },
    RegInfo { periph: "clkrst", name: "CLK_STAT", addr: 0x18000201c, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "WDOG_CNT", addr: 0x18000202c, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "CLK_MEAS", addr: 0x180002030, width: 32, reset: 0x0 },
    RegInfo { periph: "clkrst", name: "IRQ", addr: 0x180002034, width: 32, reset: 0x0 },
    RegInfo { periph: "sramc", name: "CTRL", addr: 0x180003000, width: 32, reset: 0xf },
    RegInfo { periph: "sramc", name: "STATUS", addr: 0x180003008, width: 32, reset: 0x0 },
    RegInfo { periph: "sramc", name: "PERF_CTRL", addr: 0x180003010, width: 32, reset: 0x0 },
    RegInfo { periph: "sramc", name: "PERF_VAL", addr: 0x180003014, width: 32, reset: 0x0 },
];

/// dma: DMA controller (descriptor, completion, status, interrupts, counters)
pub mod dma {
    pub const BASE: u64 = 0x120000000;
    pub const SIZE: u64 = 0x1000;
    /// dma.SRC: 32-bit at offset 0x0 - Descriptor source address (bytes)
    pub mod src {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffffffff_u32;
        pub mod fields {
            /// VALUE [31:0] rw
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
            pub const fn with_value(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::value::MAX {
                    return Err(FieldOverflow { field: "VALUE", value: v as u64, max: fields::value::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::value::MASK) | (v << fields::value::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field VALUE; only rw bits are written back.
        pub fn set_value<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_value(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// dma.DST: 32-bit at offset 0x4 - Descriptor destination address (bytes)
    pub mod dst {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffffffff_u32;
        pub mod fields {
            /// VALUE [31:0] rw
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
            pub const fn with_value(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::value::MAX {
                    return Err(FieldOverflow { field: "VALUE", value: v as u64, max: fields::value::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::value::MASK) | (v << fields::value::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field VALUE; only rw bits are written back.
        pub fn set_value<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_value(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// dma.LEN: 32-bit at offset 0x8 - Descriptor length in bytes
    pub mod len {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffffffff_u32;
        pub mod fields {
            /// VALUE [31:0] rw
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
            pub const fn with_value(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::value::MAX {
                    return Err(FieldOverflow { field: "VALUE", value: v as u64, max: fields::value::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::value::MASK) | (v << fields::value::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field VALUE; only rw bits are written back.
        pub fn set_value<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_value(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// dma.TAG: 32-bit at offset 0xc - Descriptor tag, echoed in the completion record
    pub mod tag {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0xc;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xff_u32;
        pub mod fields {
            /// TAG [7:0] rw
            pub mod tag {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn tag(self) -> u32 { (self.0 & fields::tag::MASK) >> fields::tag::SHIFT }
            pub const fn with_tag(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::tag::MAX {
                    return Err(FieldOverflow { field: "TAG", value: v as u64, max: fields::tag::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::tag::MASK) | (v << fields::tag::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field TAG; only rw bits are written back.
        pub fn set_tag<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_tag(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// dma.CTRL: 32-bit at offset 0x10 - Transfer control
    pub mod ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x1_u32;
        pub mod fields {
            /// ABORT [0:0] rw - Stop the active transfer at the next beat boundary. Level: hold it until the completion arrives, then clear it.
            pub mod abort {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn abort(self) -> u32 { (self.0 & fields::abort::MASK) >> fields::abort::SHIFT }
            pub const fn with_abort(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::abort::MAX {
                    return Err(FieldOverflow { field: "ABORT", value: v as u64, max: fields::abort::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::abort::MASK) | (v << fields::abort::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field ABORT; only rw bits are written back.
        pub fn set_abort<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_abort(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// dma.START: 32-bit at offset 0x14 - Submit the staged descriptor. Refused (TARGET_ERR) while the descriptor queue is full.
    pub mod start {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x14;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// GO [31:0] wo - Any write submits the descriptor; the value is ignored
            pub mod go {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_go(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::go::MAX {
                    return Err(FieldOverflow { field: "GO", value: v as u64, max: fields::go::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::go::MASK) | (v << fields::go::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
    }

    /// dma.STATUS: 32-bit at offset 0x18 - Engine status
    pub mod status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x18;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// BUSY [0:0] ro - A descriptor is queued or in progress
            pub mod busy {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ACTIVE [1:1] ro - The engine is executing a transfer
            pub mod active {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CTL_STATE [3:2] ro - 0 IDLE 1 CHECK 2 RUN
            pub mod ctl_state {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 2;
                pub const MASK: u32 = 0xc_u32;
                pub const MAX: u32 = 0x3_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ENG_STATE [6:4] ro - DataFabric engine state
            pub mod eng_state {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CUR_TAG [15:8] ro - Tag of the descriptor in progress
            pub mod cur_tag {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// FIFO_LEVEL [23:16] ro - Buffered-engine data FIFO occupancy
            pub mod fifo_level {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn busy(self) -> u32 { (self.0 & fields::busy::MASK) >> fields::busy::SHIFT }
            pub const fn active(self) -> u32 { (self.0 & fields::active::MASK) >> fields::active::SHIFT }
            pub const fn ctl_state(self) -> u32 { (self.0 & fields::ctl_state::MASK) >> fields::ctl_state::SHIFT }
            pub const fn eng_state(self) -> u32 { (self.0 & fields::eng_state::MASK) >> fields::eng_state::SHIFT }
            pub const fn cur_tag(self) -> u32 { (self.0 & fields::cur_tag::MASK) >> fields::cur_tag::SHIFT }
            pub const fn fifo_level(self) -> u32 { (self.0 & fields::fifo_level::MASK) >> fields::fifo_level::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// dma.BYTES_DONE: 32-bit at offset 0x1c - Bytes acknowledged so far by the transfer in progress
    pub mod bytes_done {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x1c;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// dma.CPL_STATUS: 32-bit at offset 0x20 - Head completion record
    pub mod cpl_status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x20;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALID [0:0] ro
            pub mod valid {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR [1:1] ro - Completion code is not NONE
            pub mod err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CODE [7:4] ro - 0 NONE 1 ZERO_LENGTH 2 LENGTH 3 SRC_ALIGN 4 DST_ALIGN 5 SRC_OVERFLOW 6 DST_OVERFLOW 7 OVERLAP 8 READ_BUS 9 WRITE_BUS 10 ABORTED 11 REGION
            pub mod code {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf0_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// TAG [15:8] ro
            pub mod tag {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn valid(self) -> u32 { (self.0 & fields::valid::MASK) >> fields::valid::SHIFT }
            pub const fn err(self) -> u32 { (self.0 & fields::err::MASK) >> fields::err::SHIFT }
            pub const fn code(self) -> u32 { (self.0 & fields::code::MASK) >> fields::code::SHIFT }
            pub const fn tag(self) -> u32 { (self.0 & fields::tag::MASK) >> fields::tag::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// dma.CPL_ERR_ADDR: 32-bit at offset 0x24 - Address associated with a bus or region error
    pub mod cpl_err_addr {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x24;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// dma.CPL_BYTES: 32-bit at offset 0x28 - Bytes written and acknowledged (contiguous prefix)
    pub mod cpl_bytes {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x28;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// dma.CPL_POP: 32-bit at offset 0x2c - Release the head completion record. Refused (TARGET_ERR) when there is none.
    pub mod cpl_pop {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x2c;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// POP [31:0] wo - Any write pops the record; the value is ignored
            pub mod pop {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_pop(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::pop::MAX {
                    return Err(FieldOverflow { field: "POP", value: v as u64, max: fields::pop::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::pop::MASK) | (v << fields::pop::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
    }

    /// dma.PERF_CTRL: 32-bit at offset 0x30 - Performance counter control
    pub mod perf_ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x30;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// CLEAR [0:0] w1p - Write 1 to clear the counters
            pub mod clear {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_clear(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::clear::MAX {
                    return Err(FieldOverflow { field: "CLEAR", value: v as u64, max: fields::clear::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::clear::MASK) | (v << fields::clear::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Write 1 to the chosen bits of CLEAR (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_clear<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_clear(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// dma.INT_ENABLE: 32-bit at offset 0x34 - Interrupt enables
    pub mod int_enable {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x34;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xf_u32;
        pub mod fields {
            /// CPL [0:0] rw - Completion record produced
            pub mod cpl {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CPL_ERR [1:1] rw - Completion record with an error code
            pub mod cpl_err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// BUS_ERR [2:2] rw - Bus error response received
            pub mod bus_err {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// TAG_ERR [3:3] rw - Response-ownership violation
            pub mod tag_err {
                pub const SHIFT: u32 = 3;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x8_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn cpl(self) -> u32 { (self.0 & fields::cpl::MASK) >> fields::cpl::SHIFT }
            pub const fn with_cpl(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::cpl::MAX {
                    return Err(FieldOverflow { field: "CPL", value: v as u64, max: fields::cpl::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::cpl::MASK) | (v << fields::cpl::SHIFT)))
            }
            pub const fn cpl_err(self) -> u32 { (self.0 & fields::cpl_err::MASK) >> fields::cpl_err::SHIFT }
            pub const fn with_cpl_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::cpl_err::MAX {
                    return Err(FieldOverflow { field: "CPL_ERR", value: v as u64, max: fields::cpl_err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::cpl_err::MASK) | (v << fields::cpl_err::SHIFT)))
            }
            pub const fn bus_err(self) -> u32 { (self.0 & fields::bus_err::MASK) >> fields::bus_err::SHIFT }
            pub const fn with_bus_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::bus_err::MAX {
                    return Err(FieldOverflow { field: "BUS_ERR", value: v as u64, max: fields::bus_err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::bus_err::MASK) | (v << fields::bus_err::SHIFT)))
            }
            pub const fn tag_err(self) -> u32 { (self.0 & fields::tag_err::MASK) >> fields::tag_err::SHIFT }
            pub const fn with_tag_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::tag_err::MAX {
                    return Err(FieldOverflow { field: "TAG_ERR", value: v as u64, max: fields::tag_err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::tag_err::MASK) | (v << fields::tag_err::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field CPL; only rw bits are written back.
        pub fn set_cpl<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_cpl(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field CPL_ERR; only rw bits are written back.
        pub fn set_cpl_err<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_cpl_err(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field BUS_ERR; only rw bits are written back.
        pub fn set_bus_err<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_bus_err(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field TAG_ERR; only rw bits are written back.
        pub fn set_tag_err<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_tag_err(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// dma.INT_STATUS: 32-bit at offset 0x38 - Interrupt status (write 1 to clear; a same-cycle hardware event wins)
    pub mod int_status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x38;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// CPL [0:0] w1c
            pub mod cpl {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CPL_ERR [1:1] w1c
            pub mod cpl_err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// BUS_ERR [2:2] w1c
            pub mod bus_err {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// TAG_ERR [3:3] w1c
            pub mod tag_err {
                pub const SHIFT: u32 = 3;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x8_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn cpl(self) -> u32 { (self.0 & fields::cpl::MASK) >> fields::cpl::SHIFT }
            pub const fn with_cpl(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::cpl::MAX {
                    return Err(FieldOverflow { field: "CPL", value: v as u64, max: fields::cpl::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::cpl::MASK) | (v << fields::cpl::SHIFT)))
            }
            pub const fn cpl_err(self) -> u32 { (self.0 & fields::cpl_err::MASK) >> fields::cpl_err::SHIFT }
            pub const fn with_cpl_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::cpl_err::MAX {
                    return Err(FieldOverflow { field: "CPL_ERR", value: v as u64, max: fields::cpl_err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::cpl_err::MASK) | (v << fields::cpl_err::SHIFT)))
            }
            pub const fn bus_err(self) -> u32 { (self.0 & fields::bus_err::MASK) >> fields::bus_err::SHIFT }
            pub const fn with_bus_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::bus_err::MAX {
                    return Err(FieldOverflow { field: "BUS_ERR", value: v as u64, max: fields::bus_err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::bus_err::MASK) | (v << fields::bus_err::SHIFT)))
            }
            pub const fn tag_err(self) -> u32 { (self.0 & fields::tag_err::MASK) >> fields::tag_err::SHIFT }
            pub const fn with_tag_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::tag_err::MAX {
                    return Err(FieldOverflow { field: "TAG_ERR", value: v as u64, max: fields::tag_err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::tag_err::MASK) | (v << fields::tag_err::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Write 1 to the chosen bits of CPL (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_cpl<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_cpl(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of CPL_ERR (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_cpl_err<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_cpl_err(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of BUS_ERR (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_bus_err<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_bus_err(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of TAG_ERR (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_tag_err<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_tag_err(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// dma.PERF (array of 16): 32-bit at offset 0x40 - Performance counter i (hpc_dma_perf): 0 CYCLES, 1 ACTIVE, 2 BYTES_RD, 3 BYTES_WR, 4 READS, 5 WRITES, 6 REQ_STALL, 7 RSP_WAIT, 8 OUT_SUM, 9 OUT_MAX, 10 CPL_OK, 11 CPL_ERR, 12 BUS_ERR, 13 TAG_ERR, 14 SPM_REQ, 15 FAB_REQ
    pub mod perf {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x40;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub const COUNT: usize = 16;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
    }

}

/// tensor: Tensor accelerator command interface (GEMM descriptors, completions, counters)
pub mod tensor {
    pub const BASE: u64 = 0x150000000;
    pub const SIZE: u64 = 0x1000;
    /// tensor.ID: 32-bit at offset 0x0 - ASCII "SFTC"
    pub mod id {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x53465443_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x53465443_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.INFO: 32-bit at offset 0x4 - Build configuration (from the instantiation parameters)
    pub mod info {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// ABI_VERSION [3:0] ro
            pub mod abi_version {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// LOG2_QUEUE_DEPTH [7:4] ro
            pub mod log2_queue_depth {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf0_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ARRAY_ROWS [15:8] ro
            pub mod array_rows {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ARRAY_COLS [23:16] ro
            pub mod array_cols {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ENABLE_QUANTIZATION [24:24] ro
            pub mod enable_quantization {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ENABLE_DOUBLE_BUFFERING [25:25] ro
            pub mod enable_double_buffering {
                pub const SHIFT: u32 = 25;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// PERF_EN [26:26] ro
            pub mod perf_en {
                pub const SHIFT: u32 = 26;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn abi_version(self) -> u32 { (self.0 & fields::abi_version::MASK) >> fields::abi_version::SHIFT }
            pub const fn log2_queue_depth(self) -> u32 { (self.0 & fields::log2_queue_depth::MASK) >> fields::log2_queue_depth::SHIFT }
            pub const fn array_rows(self) -> u32 { (self.0 & fields::array_rows::MASK) >> fields::array_rows::SHIFT }
            pub const fn array_cols(self) -> u32 { (self.0 & fields::array_cols::MASK) >> fields::array_cols::SHIFT }
            pub const fn enable_quantization(self) -> u32 { (self.0 & fields::enable_quantization::MASK) >> fields::enable_quantization::SHIFT }
            pub const fn enable_double_buffering(self) -> u32 { (self.0 & fields::enable_double_buffering::MASK) >> fields::enable_double_buffering::SHIFT }
            pub const fn perf_en(self) -> u32 { (self.0 & fields::perf_en::MASK) >> fields::perf_en::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.CAPS: 32-bit at offset 0x8 - Datapath capabilities
    pub mod caps {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// TILE_K [15:0] ro
            pub mod tile_k {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// DATA_WIDTH [23:16] ro
            pub mod data_width {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ACC_WIDTH [31:24] ro
            pub mod acc_width {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff000000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn tile_k(self) -> u32 { (self.0 & fields::tile_k::MASK) >> fields::tile_k::SHIFT }
            pub const fn data_width(self) -> u32 { (self.0 & fields::data_width::MASK) >> fields::data_width::SHIFT }
            pub const fn acc_width(self) -> u32 { (self.0 & fields::acc_width::MASK) >> fields::acc_width::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.OPBUF: 32-bit at offset 0xc - Operand buffer size in bytes
    pub mod opbuf {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0xc;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.MEM_LO: 32-bit at offset 0x10 - First byte of the memory window the unit may access
    pub mod mem_lo {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.MEM_LAST: 32-bit at offset 0x14 - Last byte of the memory window the unit may access
    pub mod mem_last {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x14;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.CTRL: 32-bit at offset 0x18 - Control
    pub mod ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x18;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x1_u32;
        pub mod fields {
            /// ERR_CONT [0:0] rw - 0 stop on error, 1 continue
            pub mod err_cont {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR_CLEAR [1:1] w1p - Clear the sticky error
            pub mod err_clear {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// PERF_CLEAR [2:2] w1p - Clear the performance counters
            pub mod perf_clear {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ABORT [3:3] w1p - Abort the running command
            pub mod abort {
                pub const SHIFT: u32 = 3;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x8_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn err_cont(self) -> u32 { (self.0 & fields::err_cont::MASK) >> fields::err_cont::SHIFT }
            pub const fn with_err_cont(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err_cont::MAX {
                    return Err(FieldOverflow { field: "ERR_CONT", value: v as u64, max: fields::err_cont::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err_cont::MASK) | (v << fields::err_cont::SHIFT)))
            }
            pub const fn with_err_clear(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err_clear::MAX {
                    return Err(FieldOverflow { field: "ERR_CLEAR", value: v as u64, max: fields::err_clear::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err_clear::MASK) | (v << fields::err_clear::SHIFT)))
            }
            pub const fn with_perf_clear(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::perf_clear::MAX {
                    return Err(FieldOverflow { field: "PERF_CLEAR", value: v as u64, max: fields::perf_clear::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::perf_clear::MASK) | (v << fields::perf_clear::SHIFT)))
            }
            pub const fn with_abort(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::abort::MAX {
                    return Err(FieldOverflow { field: "ABORT", value: v as u64, max: fields::abort::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::abort::MASK) | (v << fields::abort::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field ERR_CONT; only rw bits are written back.
        pub fn set_err_cont<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_err_cont(v)?;
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of ERR_CLEAR (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_err_clear<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_err_clear(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of PERF_CLEAR (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_perf_clear<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_perf_clear(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of ABORT (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_abort<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_abort(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// tensor.STATUS: 32-bit at offset 0x1c - Unit status
    pub mod status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x1c;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// BUSY [0:0] ro
            pub mod busy {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR_STICKY [1:1] ro
            pub mod err_sticky {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// Q_FULL [2:2] ro
            pub mod q_full {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// Q_EMPTY [3:3] ro
            pub mod q_empty {
                pub const SHIFT: u32 = 3;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x8_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CPL_VALID [4:4] ro
            pub mod cpl_valid {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x10_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ABORTING [5:5] ro
            pub mod aborting {
                pub const SHIFT: u32 = 5;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x20_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// HALTED [6:6] ro - Quiesce timed out; a hard reset is needed
            pub mod halted {
                pub const SHIFT: u32 = 6;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x40_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// STATE [11:8] ro - Scheduler state: 0 IDLE 1 DECODE 2 PREP 3 RUN 4 QUIESCE 5 SRST 6 RECORD 7 FLUSH 8 HALT
            pub mod state {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf00_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// QCOUNT [23:16] ro
            pub mod qcount {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// QFREE [31:24] ro
            pub mod qfree {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff000000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn busy(self) -> u32 { (self.0 & fields::busy::MASK) >> fields::busy::SHIFT }
            pub const fn err_sticky(self) -> u32 { (self.0 & fields::err_sticky::MASK) >> fields::err_sticky::SHIFT }
            pub const fn q_full(self) -> u32 { (self.0 & fields::q_full::MASK) >> fields::q_full::SHIFT }
            pub const fn q_empty(self) -> u32 { (self.0 & fields::q_empty::MASK) >> fields::q_empty::SHIFT }
            pub const fn cpl_valid(self) -> u32 { (self.0 & fields::cpl_valid::MASK) >> fields::cpl_valid::SHIFT }
            pub const fn aborting(self) -> u32 { (self.0 & fields::aborting::MASK) >> fields::aborting::SHIFT }
            pub const fn halted(self) -> u32 { (self.0 & fields::halted::MASK) >> fields::halted::SHIFT }
            pub const fn state(self) -> u32 { (self.0 & fields::state::MASK) >> fields::state::SHIFT }
            pub const fn qcount(self) -> u32 { (self.0 & fields::qcount::MASK) >> fields::qcount::SHIFT }
            pub const fn qfree(self) -> u32 { (self.0 & fields::qfree::MASK) >> fields::qfree::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.INT_ENABLE: 32-bit at offset 0x20 - Interrupt enables
    pub mod int_enable {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x20;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x7_u32;
        pub mod fields {
            /// IRQ [0:0] rw
            pub mod irq {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR [1:1] rw
            pub mod err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// DONE [2:2] rw
            pub mod done {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn irq(self) -> u32 { (self.0 & fields::irq::MASK) >> fields::irq::SHIFT }
            pub const fn with_irq(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::irq::MAX {
                    return Err(FieldOverflow { field: "IRQ", value: v as u64, max: fields::irq::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::irq::MASK) | (v << fields::irq::SHIFT)))
            }
            pub const fn err(self) -> u32 { (self.0 & fields::err::MASK) >> fields::err::SHIFT }
            pub const fn with_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err::MAX {
                    return Err(FieldOverflow { field: "ERR", value: v as u64, max: fields::err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err::MASK) | (v << fields::err::SHIFT)))
            }
            pub const fn done(self) -> u32 { (self.0 & fields::done::MASK) >> fields::done::SHIFT }
            pub const fn with_done(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::done::MAX {
                    return Err(FieldOverflow { field: "DONE", value: v as u64, max: fields::done::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::done::MASK) | (v << fields::done::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field IRQ; only rw bits are written back.
        pub fn set_irq<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_irq(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field ERR; only rw bits are written back.
        pub fn set_err<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_err(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field DONE; only rw bits are written back.
        pub fn set_done<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_done(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// tensor.INT_STATUS: 32-bit at offset 0x24 - Interrupt status (write 1 to clear; a same-cycle hardware event wins)
    pub mod int_status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x24;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// IRQ [0:0] w1c
            pub mod irq {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR [1:1] w1c
            pub mod err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// DONE [2:2] w1c
            pub mod done {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn irq(self) -> u32 { (self.0 & fields::irq::MASK) >> fields::irq::SHIFT }
            pub const fn with_irq(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::irq::MAX {
                    return Err(FieldOverflow { field: "IRQ", value: v as u64, max: fields::irq::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::irq::MASK) | (v << fields::irq::SHIFT)))
            }
            pub const fn err(self) -> u32 { (self.0 & fields::err::MASK) >> fields::err::SHIFT }
            pub const fn with_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err::MAX {
                    return Err(FieldOverflow { field: "ERR", value: v as u64, max: fields::err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err::MASK) | (v << fields::err::SHIFT)))
            }
            pub const fn done(self) -> u32 { (self.0 & fields::done::MASK) >> fields::done::SHIFT }
            pub const fn with_done(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::done::MAX {
                    return Err(FieldOverflow { field: "DONE", value: v as u64, max: fields::done::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::done::MASK) | (v << fields::done::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Write 1 to the chosen bits of IRQ (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_irq<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_irq(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of ERR (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_err<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_err(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of DONE (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_done<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_done(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// tensor.SUBMITTED: 32-bit at offset 0x28 - Doorbells accepted since reset (glue counter)
    pub mod submitted {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x28;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.KMAX: 32-bit at offset 0x2c - Largest legal K of this build
    pub mod kmax {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x2c;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// tensor.DESC (array of 12): 32-bit at offset 0x40 - Descriptor staging words 0..11 (kept after the doorbell)
    pub mod desc {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x40;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffffffff_u32;
        pub const COUNT: usize = 12;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] rw
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
            pub const fn with_value(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::value::MAX {
                    return Err(FieldOverflow { field: "VALUE", value: v as u64, max: fields::value::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::value::MASK) | (v << fields::value::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
        pub fn write<B: RegBus>(bus: &B, index: usize, value: Value) -> Result<(), Error> {
            bus.write32(addr(index)?, value.0);
            Ok(())
        }
        /// Read-modify-write of rw field VALUE; only rw bits are written back.
        pub fn set_value<B: RegBus>(bus: &B, index: usize, v: u32) -> Result<(), Error> {
            let new = Value(read(bus, index)?.0 & RW_MASK).with_value(v)?;
            write(bus, index, new)?;
            Ok(())
        }
    }

    /// tensor.DOORBELL: 32-bit at offset 0x70 - Submit the staged descriptor. Refused (TARGET_ERR) while the command queue is full.
    pub mod doorbell {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x70;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// RING [31:0] wo - Any write submits the descriptor; the value is ignored
            pub mod ring {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_ring(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::ring::MAX {
                    return Err(FieldOverflow { field: "RING", value: v as u64, max: fields::ring::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::ring::MASK) | (v << fields::ring::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
    }

    /// tensor.CPL (array of 6): 32-bit at offset 0x80 - Head completion record words 0..5 (glue gates them with cpl_valid)
    pub mod cpl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x80;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub const COUNT: usize = 6;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
    }

    /// tensor.CPL_POP: 32-bit at offset 0x98 - Release the head record. Refused (TARGET_ERR) if there is none.
    pub mod cpl_pop {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x98;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// POP [31:0] wo - Any write pops the record; the value is ignored
            pub mod pop {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_pop(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::pop::MAX {
                    return Err(FieldOverflow { field: "POP", value: v as u64, max: fields::pop::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::pop::MASK) | (v << fields::pop::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
    }

    /// tensor.PERF (array of 20): 32-bit at offset 0x100 - Performance counter i (saturating 32-bit): 0 CYCLES, 1 BUSY, 2 CMD_ACCEPT, 3 CMD_DONE, 4 CMD_ERR, 5 GEMM_OK, 6 TILES, 7 CHUNKS, 8 MACS, 9 COMPUTE_CYC, 10 DMA_ACTIVE, 11 OVERLAP, 12 RD_WORDS, 13 WR_WORDS, 14 BUS_STALL, 15 DESC, 16 Q_FULL, 17 CPL_STALL, 18 SAT, 19 ABORTS
    pub mod perf {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x100;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub const COUNT: usize = 20;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
    }

    /// tensor.DMA_PERF (array of 18): 32-bit at offset 0x200 - Tensor DMA adapter counter j (TDMA_PC_*)
    pub mod dma_perf {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x200;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub const COUNT: usize = 18;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
    }

}

/// vector: Vector/DMA command interface (hardware command queue and scheduler)
pub mod vector {
    pub const BASE: u64 = 0x150001000;
    pub const SIZE: u64 = 0x1000;
    /// vector.ID: 32-bit at offset 0x0 - ASCII "SFCQ"
    pub mod id {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x53464351_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x53464351_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// vector.INFO: 32-bit at offset 0x4 - Build configuration (from the instantiation parameters)
    pub mod info {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// ABI_VERSION [3:0] ro
            pub mod abi_version {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// QUEUE_DEPTH [15:8] ro
            pub mod queue_depth {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ROB_DEPTH [23:16] ro
            pub mod rob_depth {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// OPSET_FULL [24:24] ro
            pub mod opset_full {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// OVERLAP_EN [25:25] ro
            pub mod overlap_en {
                pub const SHIFT: u32 = 25;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// PERF_EN [26:26] ro
            pub mod perf_en {
                pub const SHIFT: u32 = 26;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn abi_version(self) -> u32 { (self.0 & fields::abi_version::MASK) >> fields::abi_version::SHIFT }
            pub const fn queue_depth(self) -> u32 { (self.0 & fields::queue_depth::MASK) >> fields::queue_depth::SHIFT }
            pub const fn rob_depth(self) -> u32 { (self.0 & fields::rob_depth::MASK) >> fields::rob_depth::SHIFT }
            pub const fn opset_full(self) -> u32 { (self.0 & fields::opset_full::MASK) >> fields::opset_full::SHIFT }
            pub const fn overlap_en(self) -> u32 { (self.0 & fields::overlap_en::MASK) >> fields::overlap_en::SHIFT }
            pub const fn perf_en(self) -> u32 { (self.0 & fields::perf_en::MASK) >> fields::perf_en::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// vector.CTRL: 32-bit at offset 0x8 - Control
    pub mod ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x1_u32;
        pub mod fields {
            /// ERR_CONT [0:0] rw - 0 stop on error, 1 continue
            pub mod err_cont {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR_CLEAR [1:1] w1p - Clear the sticky error
            pub mod err_clear {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// PERF_CLEAR [2:2] w1p - Clear the performance counters
            pub mod perf_clear {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn err_cont(self) -> u32 { (self.0 & fields::err_cont::MASK) >> fields::err_cont::SHIFT }
            pub const fn with_err_cont(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err_cont::MAX {
                    return Err(FieldOverflow { field: "ERR_CONT", value: v as u64, max: fields::err_cont::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err_cont::MASK) | (v << fields::err_cont::SHIFT)))
            }
            pub const fn with_err_clear(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err_clear::MAX {
                    return Err(FieldOverflow { field: "ERR_CLEAR", value: v as u64, max: fields::err_clear::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err_clear::MASK) | (v << fields::err_clear::SHIFT)))
            }
            pub const fn with_perf_clear(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::perf_clear::MAX {
                    return Err(FieldOverflow { field: "PERF_CLEAR", value: v as u64, max: fields::perf_clear::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::perf_clear::MASK) | (v << fields::perf_clear::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field ERR_CONT; only rw bits are written back.
        pub fn set_err_cont<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_err_cont(v)?;
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of ERR_CLEAR (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_err_clear<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_err_clear(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of PERF_CLEAR (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_perf_clear<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_perf_clear(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// vector.STATUS: 32-bit at offset 0xc - Queue status
    pub mod status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0xc;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// BUSY [0:0] ro
            pub mod busy {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR_STICKY [1:1] ro
            pub mod err_sticky {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// Q_FULL [2:2] ro
            pub mod q_full {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// Q_EMPTY [3:3] ro
            pub mod q_empty {
                pub const SHIFT: u32 = 3;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x8_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CPL_VALID [4:4] ro
            pub mod cpl_valid {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x10_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// DMA_DOWN [5:5] ro
            pub mod dma_down {
                pub const SHIFT: u32 = 5;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x20_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// VEC_DOWN [6:6] ro
            pub mod vec_down {
                pub const SHIFT: u32 = 6;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x40_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// Q_COUNT [15:8] ro
            pub mod q_count {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ROB_COUNT [23:16] ro
            pub mod rob_count {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// Q_FREE [31:24] ro - Doorbells that will be accepted now (glue)
            pub mod q_free {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff000000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn busy(self) -> u32 { (self.0 & fields::busy::MASK) >> fields::busy::SHIFT }
            pub const fn err_sticky(self) -> u32 { (self.0 & fields::err_sticky::MASK) >> fields::err_sticky::SHIFT }
            pub const fn q_full(self) -> u32 { (self.0 & fields::q_full::MASK) >> fields::q_full::SHIFT }
            pub const fn q_empty(self) -> u32 { (self.0 & fields::q_empty::MASK) >> fields::q_empty::SHIFT }
            pub const fn cpl_valid(self) -> u32 { (self.0 & fields::cpl_valid::MASK) >> fields::cpl_valid::SHIFT }
            pub const fn dma_down(self) -> u32 { (self.0 & fields::dma_down::MASK) >> fields::dma_down::SHIFT }
            pub const fn vec_down(self) -> u32 { (self.0 & fields::vec_down::MASK) >> fields::vec_down::SHIFT }
            pub const fn q_count(self) -> u32 { (self.0 & fields::q_count::MASK) >> fields::q_count::SHIFT }
            pub const fn rob_count(self) -> u32 { (self.0 & fields::rob_count::MASK) >> fields::rob_count::SHIFT }
            pub const fn q_free(self) -> u32 { (self.0 & fields::q_free::MASK) >> fields::q_free::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// vector.INT_ENABLE: 32-bit at offset 0x10 - Interrupt enables
    pub mod int_enable {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x3_u32;
        pub mod fields {
            /// IRQ [0:0] rw - An FL_IRQ command committed
            pub mod irq {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR [1:1] rw - An ERROR or SKIPPED record committed
            pub mod err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn irq(self) -> u32 { (self.0 & fields::irq::MASK) >> fields::irq::SHIFT }
            pub const fn with_irq(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::irq::MAX {
                    return Err(FieldOverflow { field: "IRQ", value: v as u64, max: fields::irq::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::irq::MASK) | (v << fields::irq::SHIFT)))
            }
            pub const fn err(self) -> u32 { (self.0 & fields::err::MASK) >> fields::err::SHIFT }
            pub const fn with_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err::MAX {
                    return Err(FieldOverflow { field: "ERR", value: v as u64, max: fields::err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err::MASK) | (v << fields::err::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field IRQ; only rw bits are written back.
        pub fn set_irq<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_irq(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field ERR; only rw bits are written back.
        pub fn set_err<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_err(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// vector.INT_STATUS: 32-bit at offset 0x14 - Interrupt status (write 1 to clear; a same-cycle hardware event wins)
    pub mod int_status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x14;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// IRQ [0:0] w1c
            pub mod irq {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// ERR [1:1] w1c
            pub mod err {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn irq(self) -> u32 { (self.0 & fields::irq::MASK) >> fields::irq::SHIFT }
            pub const fn with_irq(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::irq::MAX {
                    return Err(FieldOverflow { field: "IRQ", value: v as u64, max: fields::irq::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::irq::MASK) | (v << fields::irq::SHIFT)))
            }
            pub const fn err(self) -> u32 { (self.0 & fields::err::MASK) >> fields::err::SHIFT }
            pub const fn with_err(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::err::MAX {
                    return Err(FieldOverflow { field: "ERR", value: v as u64, max: fields::err::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::err::MASK) | (v << fields::err::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Write 1 to the chosen bits of IRQ (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_irq<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_irq(bits)?.0);
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of ERR (w1c); other rw fields keep their value, other write-one fields get 0.
        pub fn clear_err<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(0);
            let new = Value(cur.0 | Value(0).with_err(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// vector.SUBMITTED: 32-bit at offset 0x18 - Doorbells accepted since reset (glue counter)
    pub mod submitted {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x18;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// vector.DESC (array of 8): 32-bit at offset 0x20 - Descriptor staging words 0..7 (kept after the doorbell)
    pub mod desc {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x20;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffffffff_u32;
        pub const COUNT: usize = 8;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] rw
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
            pub const fn with_value(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::value::MAX {
                    return Err(FieldOverflow { field: "VALUE", value: v as u64, max: fields::value::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::value::MASK) | (v << fields::value::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
        pub fn write<B: RegBus>(bus: &B, index: usize, value: Value) -> Result<(), Error> {
            bus.write32(addr(index)?, value.0);
            Ok(())
        }
        /// Read-modify-write of rw field VALUE; only rw bits are written back.
        pub fn set_value<B: RegBus>(bus: &B, index: usize, v: u32) -> Result<(), Error> {
            let new = Value(read(bus, index)?.0 & RW_MASK).with_value(v)?;
            write(bus, index, new)?;
            Ok(())
        }
    }

    /// vector.DOORBELL: 32-bit at offset 0x40 - Submit the staged descriptor. Refused (TARGET_ERR) while the queue is full; nothing is submitted.
    pub mod doorbell {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x40;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// RING [31:0] wo - Any write submits the descriptor; the value is ignored
            pub mod ring {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_ring(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::ring::MAX {
                    return Err(FieldOverflow { field: "RING", value: v as u64, max: fields::ring::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::ring::MASK) | (v << fields::ring::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
    }

    /// vector.CPL (array of 4): 32-bit at offset 0x50 - Head completion record words 0..3 (0 if there is none)
    pub mod cpl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x50;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub const COUNT: usize = 4;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
    }

    /// vector.CPL_POP: 32-bit at offset 0x60 - Release the head record. Refused (TARGET_ERR) if there is none.
    pub mod cpl_pop {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x60;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// POP [31:0] wo - Any write pops the record; the value is ignored
            pub mod pop {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn with_pop(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::pop::MAX {
                    return Err(FieldOverflow { field: "POP", value: v as u64, max: fields::pop::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::pop::MASK) | (v << fields::pop::SHIFT)))
            }
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
    }

    /// vector.PERF (array of 17): 32-bit at offset 0x80 - Performance counter i (hpc_cq_pkg PC_*), low 32 bits
    pub mod perf {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x80;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub const COUNT: usize = 17;
        pub const STRIDE: u64 = 4;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read32(addr(index)?)))
        }
    }

}

/// perf: Performance counter observation window
pub mod perf {
    pub const BASE: u64 = 0x170000000;
    pub const SIZE: u64 = 0x1000;
    /// perf.CTRL: 32-bit at offset 0x0 - Hardware-side counter control
    pub mod ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x1_u32;
        pub mod fields {
            /// FREEZE [0:0] rw - Stop counting (hardware freeze, effective in the same cycle)
            pub mod freeze {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// SNAPSHOT [1:1] w1p - Trigger a coherent snapshot of every counter (one-cycle pulse)
            pub mod snapshot {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn freeze(self) -> u32 { (self.0 & fields::freeze::MASK) >> fields::freeze::SHIFT }
            pub const fn with_freeze(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::freeze::MAX {
                    return Err(FieldOverflow { field: "FREEZE", value: v as u64, max: fields::freeze::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::freeze::MASK) | (v << fields::freeze::SHIFT)))
            }
            pub const fn with_snapshot(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::snapshot::MAX {
                    return Err(FieldOverflow { field: "SNAPSHOT", value: v as u64, max: fields::snapshot::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::snapshot::MASK) | (v << fields::snapshot::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field FREEZE; only rw bits are written back.
        pub fn set_freeze<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_freeze(v)?;
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of SNAPSHOT (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_snapshot<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_snapshot(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// perf.STATUS: 32-bit at offset 0x4 - Counter bank status
    pub mod status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// FROZEN [0:0] ro - Counting is stopped this cycle by a freeze source
            pub mod frozen {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// IRQ [1:1] ro - Overflow interrupt level (OVF and OVF_IE)
            pub mod irq {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn frozen(self) -> u32 { (self.0 & fields::frozen::MASK) >> fields::frozen::SHIFT }
            pub const fn irq(self) -> u32 { (self.0 & fields::irq::MASK) >> fields::irq::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// perf.CNT (array of 23): 64-bit at offset 0x100 - Live counter i (64-bit): 0 CYCLES, 1 CMD_ACCEPTED, 2 CMD_COMPLETED, 3 VEC_ISSUED, 4 VEC_RETIRED, 5 FLOPS_RETIRED, 6 VEC_STALL, 7 DMA_ACTIVE, 8 DMA_BYTES_RD, 9 DMA_BYTES_WR, 10 SPM_READS, 11 SPM_WRITES, 12 SPM_CONFLICTS, 13 CMDQ_FULL, 14 OUT_BP, 15 HW_ERRORS, 16 VEC_BUSY, 17 VEC_OPND_STARVE, 18 CMD_INFLIGHT_SUM, 19 VEC_CMDQ_OCC_SUM, 20 DMA_OUT_SUM, 21 RED_ADDS, 22 VEC_CMD_COMPLETED
    pub mod cnt {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x100;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 64;
        pub const RESET: u64 = 0x0_u64;
        pub const RW_MASK: u64 = 0x0_u64;
        pub const COUNT: usize = 23;
        pub const STRIDE: u64 = 8;
        pub fn addr(index: usize) -> Result<u64, Error> {
            if index >= COUNT {
                return Err(Error::Index(IndexError { index, count: COUNT }));
            }
            Ok(ADDR + (index as u64) * STRIDE)
        }
        pub mod fields {
            /// VALUE [63:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 64;
                pub const MASK: u64 = 0xffffffffffffffff_u64;
                pub const MAX: u64 = 0xffffffffffffffff_u64;
                pub const RESET: u64 = 0x0_u64;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u64);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u64 { self.0 }
            pub const fn value(self) -> u64 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B, index: usize) -> Result<Value, Error> {
            Ok(Value(bus.read64_stable(addr(index)?)))
        }
    }

}

/// sysid: System identification and register-map fingerprint
pub mod sysid {
    pub const BASE: u64 = 0x180000000;
    pub const SIZE: u64 = 0x1000;
    /// sysid.ID: 32-bit at offset 0x0 - ASCII "SFLX"
    pub mod id {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x53464c58_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x53464c58_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// sysid.REGMAP_VERSION: 32-bit at offset 0x4 - Version of this register map (major.minor)
    pub mod regmap_version {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x10000_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// MINOR [15:0] ro
            pub mod minor {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// MAJOR [31:16] ro
            pub mod major {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff0000_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x1_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn minor(self) -> u32 { (self.0 & fields::minor::MASK) >> fields::minor::SHIFT }
            pub const fn major(self) -> u32 { (self.0 & fields::major::MASK) >> fields::major::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// sysid.ALP_VERSION: 32-bit at offset 0x8 - Albion Link Protocol version implemented by the register bank (SF_ALP_VERSION_*)
    pub mod alp_version {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x1_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// MAJOR [7:0] ro
            pub mod major {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// MINOR [15:8] ro
            pub mod minor {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn major(self) -> u32 { (self.0 & fields::major::MASK) >> fields::major::SHIFT }
            pub const fn minor(self) -> u32 { (self.0 & fields::minor::MASK) >> fields::minor::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// sysid.LIB_VERSION: 32-bit at offset 0xc - AlbionCore library version the RTL was generated against (SF_ALBION_LIB_*)
    pub mod lib_version {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0xc;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x100_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// MAJOR [7:0] ro
            pub mod major {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// MINOR [15:8] ro
            pub mod minor {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// PATCH [23:16] ro
            pub mod patch {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn major(self) -> u32 { (self.0 & fields::major::MASK) >> fields::major::SHIFT }
            pub const fn minor(self) -> u32 { (self.0 & fields::minor::MASK) >> fields::minor::SHIFT }
            pub const fn patch(self) -> u32 { (self.0 & fields::patch::MASK) >> fields::patch::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// sysid.ALP_CAPS: 64-bit at offset 0x10 - ALP capability word of this link target, laid out as sf_caps_t. MAX_OUTSTANDING is the capacity of sf_reg_interface (2: it accepts a request in the cycle its predecessor's response leaves); FEATURES is READ|WRITE (no atomics, no out-of-order, no ECC).
    pub mod alp_caps {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 64;
        pub const RESET: u64 = 0x1040488000020003_u64;
        pub const RW_MASK: u64 = 0x0_u64;
        pub mod fields {
            /// FEATURES [15:0] ro
            pub mod features {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u64 = 0xffff_u64;
                pub const MAX: u64 = 0xffff_u64;
                pub const RESET: u64 = 0x3_u64;
            }
            /// MAX_OUTSTANDING [31:16] ro
            pub mod max_outstanding {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 16;
                pub const MASK: u64 = 0xffff0000_u64;
                pub const MAX: u64 = 0xffff_u64;
                pub const RESET: u64 = 0x2_u64;
            }
            /// RSVD [35:32] ro
            pub mod rsvd {
                pub const SHIFT: u32 = 32;
                pub const WIDTH: u32 = 4;
                pub const MASK: u64 = 0xf00000000_u64;
                pub const MAX: u64 = 0xf_u64;
                pub const RESET: u64 = 0x0_u64;
            }
            /// DOM_W [39:36] ro
            pub mod dom_w {
                pub const SHIFT: u32 = 36;
                pub const WIDTH: u32 = 4;
                pub const MASK: u64 = 0xf000000000_u64;
                pub const MAX: u64 = 0xf_u64;
                pub const RESET: u64 = 0x8_u64;
            }
            /// TAG_W [43:40] ro
            pub mod tag_w {
                pub const SHIFT: u32 = 40;
                pub const WIDTH: u32 = 4;
                pub const MASK: u64 = 0xf0000000000_u64;
                pub const MAX: u64 = 0xf_u64;
                pub const RESET: u64 = 0x8_u64;
            }
            /// DATA_BYTES_LOG2 [47:44] ro
            pub mod data_bytes_log2 {
                pub const SHIFT: u32 = 44;
                pub const WIDTH: u32 = 4;
                pub const MASK: u64 = 0xf00000000000_u64;
                pub const MAX: u64 = 0xf_u64;
                pub const RESET: u64 = 0x4_u64;
            }
            /// ADDR_W [55:48] ro
            pub mod addr_w {
                pub const SHIFT: u32 = 48;
                pub const WIDTH: u32 = 8;
                pub const MASK: u64 = 0xff000000000000_u64;
                pub const MAX: u64 = 0xff_u64;
                pub const RESET: u64 = 0x40_u64;
            }
            /// PROTO_MINOR [59:56] ro
            pub mod proto_minor {
                pub const SHIFT: u32 = 56;
                pub const WIDTH: u32 = 4;
                pub const MASK: u64 = 0xf00000000000000_u64;
                pub const MAX: u64 = 0xf_u64;
                pub const RESET: u64 = 0x0_u64;
            }
            /// PROTO_MAJOR [63:60] ro
            pub mod proto_major {
                pub const SHIFT: u32 = 60;
                pub const WIDTH: u32 = 4;
                pub const MASK: u64 = 0xf000000000000000_u64;
                pub const MAX: u64 = 0xf_u64;
                pub const RESET: u64 = 0x1_u64;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u64);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u64 { self.0 }
            pub const fn features(self) -> u64 { (self.0 & fields::features::MASK) >> fields::features::SHIFT }
            pub const fn max_outstanding(self) -> u64 { (self.0 & fields::max_outstanding::MASK) >> fields::max_outstanding::SHIFT }
            pub const fn rsvd(self) -> u64 { (self.0 & fields::rsvd::MASK) >> fields::rsvd::SHIFT }
            pub const fn dom_w(self) -> u64 { (self.0 & fields::dom_w::MASK) >> fields::dom_w::SHIFT }
            pub const fn tag_w(self) -> u64 { (self.0 & fields::tag_w::MASK) >> fields::tag_w::SHIFT }
            pub const fn data_bytes_log2(self) -> u64 { (self.0 & fields::data_bytes_log2::MASK) >> fields::data_bytes_log2::SHIFT }
            pub const fn addr_w(self) -> u64 { (self.0 & fields::addr_w::MASK) >> fields::addr_w::SHIFT }
            pub const fn proto_minor(self) -> u64 { (self.0 & fields::proto_minor::MASK) >> fields::proto_minor::SHIFT }
            pub const fn proto_major(self) -> u64 { (self.0 & fields::proto_major::MASK) >> fields::proto_major::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read64_stable(ADDR))
        }
    }

    /// sysid.REGMAP_HASH: 64-bit at offset 0x18 - First 8 bytes of the SHA-256 semantic hash of the register definition (addresses, widths, access types, reset values, hardware options). Firmware compares it with SF_REGS_MAP_HASH.
    pub mod regmap_hash {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x18;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 64;
        pub const RESET: u64 = 0x99481283139d2dc0_u64;
        pub const RW_MASK: u64 = 0x0_u64;
        pub mod fields {
            /// VALUE [63:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 64;
                pub const MASK: u64 = 0xffffffffffffffff_u64;
                pub const MAX: u64 = 0xffffffffffffffff_u64;
                pub const RESET: u64 = 0x99481283139d2dc0_u64;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u64);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u64 { self.0 }
            pub const fn value(self) -> u64 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read64_stable(ADDR))
        }
    }

    /// sysid.BUILD_ID: 32-bit at offset 0x20 - Build identifier supplied by the integrator (for example a source-control revision)
    pub mod build_id {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x20;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

}

/// intc: Interrupt controller (16 level sources, 7 priority levels, threshold, claim)
pub mod intc {
    pub const BASE: u64 = 0x180001000;
    pub const SIZE: u64 = 0x1000;
    /// intc.PENDING: 32-bit at offset 0x0 - Live source levels OR software-pending bits
    pub mod pending {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// SOURCES [15:0] ro
            pub mod sources {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn sources(self) -> u32 { (self.0 & fields::sources::MASK) >> fields::sources::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// intc.ENABLE: 32-bit at offset 0x4 - Per-source interrupt enable
    pub mod enable {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffff_u32;
        pub mod fields {
            /// EN [15:0] rw
            pub mod en {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn en(self) -> u32 { (self.0 & fields::en::MASK) >> fields::en::SHIFT }
            pub const fn with_en(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::en::MAX {
                    return Err(FieldOverflow { field: "EN", value: v as u64, max: fields::en::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::en::MASK) | (v << fields::en::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field EN; only rw bits are written back.
        pub fn set_en<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_en(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// intc.CLAIM: 32-bit at offset 0x8 - Highest-priority active source (lowest index wins ties); reading has no side effect
    pub mod claim {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// ID [7:0] ro - 1 + source index; 0 = none
            pub mod id {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn id(self) -> u32 { (self.0 & fields::id::MASK) >> fields::id::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// intc.SWPEND: 32-bit at offset 0xc - Software-set pending bits (software interrupts per source)
    pub mod swpend {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0xc;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0xffff_u32;
        pub mod fields {
            /// SW [15:0] rw
            pub mod sw {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn sw(self) -> u32 { (self.0 & fields::sw::MASK) >> fields::sw::SHIFT }
            pub const fn with_sw(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::sw::MAX {
                    return Err(FieldOverflow { field: "SW", value: v as u64, max: fields::sw::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::sw::MASK) | (v << fields::sw::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field SW; only rw bits are written back.
        pub fn set_sw<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_sw(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// intc.THRESHOLD: 32-bit at offset 0x10 - Only priorities greater than LEVEL interrupt
    pub mod threshold {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x7_u32;
        pub mod fields {
            /// LEVEL [2:0] rw
            pub mod level {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn level(self) -> u32 { (self.0 & fields::level::MASK) >> fields::level::SHIFT }
            pub const fn with_level(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::level::MAX {
                    return Err(FieldOverflow { field: "LEVEL", value: v as u64, max: fields::level::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::level::MASK) | (v << fields::level::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field LEVEL; only rw bits are written back.
        pub fn set_level<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_level(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// intc.ACTIVE: 32-bit at offset 0x14 - Pending and enabled and priority above threshold
    pub mod active {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x14;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// ACT [15:0] ro
            pub mod act {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn act(self) -> u32 { (self.0 & fields::act::MASK) >> fields::act::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// intc.PRIO0: 32-bit at offset 0x20 - Priority of sources 0..7, 3 bits each in a 4-bit nibble (0 = never)
    pub mod prio0 {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x20;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x11111111_u32;
        pub const RW_MASK: u32 = 0x77777777_u32;
        pub mod fields {
            /// SRC0 [2:0] rw - Priority of source 0
            pub mod src0 {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC1 [6:4] rw - Priority of source 1
            pub mod src1 {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC2 [10:8] rw - Priority of source 2
            pub mod src2 {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x700_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC3 [14:12] rw - Priority of source 3
            pub mod src3 {
                pub const SHIFT: u32 = 12;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC4 [18:16] rw - Priority of source 4
            pub mod src4 {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC5 [22:20] rw - Priority of source 5
            pub mod src5 {
                pub const SHIFT: u32 = 20;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x700000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC6 [26:24] rw - Priority of source 6
            pub mod src6 {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7000000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC7 [30:28] rw - Priority of source 7
            pub mod src7 {
                pub const SHIFT: u32 = 28;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70000000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn src0(self) -> u32 { (self.0 & fields::src0::MASK) >> fields::src0::SHIFT }
            pub const fn with_src0(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src0::MAX {
                    return Err(FieldOverflow { field: "SRC0", value: v as u64, max: fields::src0::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src0::MASK) | (v << fields::src0::SHIFT)))
            }
            pub const fn src1(self) -> u32 { (self.0 & fields::src1::MASK) >> fields::src1::SHIFT }
            pub const fn with_src1(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src1::MAX {
                    return Err(FieldOverflow { field: "SRC1", value: v as u64, max: fields::src1::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src1::MASK) | (v << fields::src1::SHIFT)))
            }
            pub const fn src2(self) -> u32 { (self.0 & fields::src2::MASK) >> fields::src2::SHIFT }
            pub const fn with_src2(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src2::MAX {
                    return Err(FieldOverflow { field: "SRC2", value: v as u64, max: fields::src2::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src2::MASK) | (v << fields::src2::SHIFT)))
            }
            pub const fn src3(self) -> u32 { (self.0 & fields::src3::MASK) >> fields::src3::SHIFT }
            pub const fn with_src3(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src3::MAX {
                    return Err(FieldOverflow { field: "SRC3", value: v as u64, max: fields::src3::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src3::MASK) | (v << fields::src3::SHIFT)))
            }
            pub const fn src4(self) -> u32 { (self.0 & fields::src4::MASK) >> fields::src4::SHIFT }
            pub const fn with_src4(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src4::MAX {
                    return Err(FieldOverflow { field: "SRC4", value: v as u64, max: fields::src4::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src4::MASK) | (v << fields::src4::SHIFT)))
            }
            pub const fn src5(self) -> u32 { (self.0 & fields::src5::MASK) >> fields::src5::SHIFT }
            pub const fn with_src5(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src5::MAX {
                    return Err(FieldOverflow { field: "SRC5", value: v as u64, max: fields::src5::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src5::MASK) | (v << fields::src5::SHIFT)))
            }
            pub const fn src6(self) -> u32 { (self.0 & fields::src6::MASK) >> fields::src6::SHIFT }
            pub const fn with_src6(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src6::MAX {
                    return Err(FieldOverflow { field: "SRC6", value: v as u64, max: fields::src6::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src6::MASK) | (v << fields::src6::SHIFT)))
            }
            pub const fn src7(self) -> u32 { (self.0 & fields::src7::MASK) >> fields::src7::SHIFT }
            pub const fn with_src7(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src7::MAX {
                    return Err(FieldOverflow { field: "SRC7", value: v as u64, max: fields::src7::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src7::MASK) | (v << fields::src7::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field SRC0; only rw bits are written back.
        pub fn set_src0<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src0(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC1; only rw bits are written back.
        pub fn set_src1<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src1(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC2; only rw bits are written back.
        pub fn set_src2<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src2(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC3; only rw bits are written back.
        pub fn set_src3<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src3(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC4; only rw bits are written back.
        pub fn set_src4<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src4(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC5; only rw bits are written back.
        pub fn set_src5<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src5(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC6; only rw bits are written back.
        pub fn set_src6<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src6(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC7; only rw bits are written back.
        pub fn set_src7<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src7(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// intc.PRIO1: 32-bit at offset 0x24 - Priority of sources 8..15, 3 bits each in a 4-bit nibble (0 = never)
    pub mod prio1 {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x24;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x11111111_u32;
        pub const RW_MASK: u32 = 0x77777777_u32;
        pub mod fields {
            /// SRC8 [2:0] rw - Priority of source 8
            pub mod src8 {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC9 [6:4] rw - Priority of source 9
            pub mod src9 {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC10 [10:8] rw - Priority of source 10
            pub mod src10 {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x700_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC11 [14:12] rw - Priority of source 11
            pub mod src11 {
                pub const SHIFT: u32 = 12;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC12 [18:16] rw - Priority of source 12
            pub mod src12 {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC13 [22:20] rw - Priority of source 13
            pub mod src13 {
                pub const SHIFT: u32 = 20;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x700000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC14 [26:24] rw - Priority of source 14
            pub mod src14 {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x7000000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
            /// SRC15 [30:28] rw - Priority of source 15
            pub mod src15 {
                pub const SHIFT: u32 = 28;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0x70000000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x1_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn src8(self) -> u32 { (self.0 & fields::src8::MASK) >> fields::src8::SHIFT }
            pub const fn with_src8(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src8::MAX {
                    return Err(FieldOverflow { field: "SRC8", value: v as u64, max: fields::src8::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src8::MASK) | (v << fields::src8::SHIFT)))
            }
            pub const fn src9(self) -> u32 { (self.0 & fields::src9::MASK) >> fields::src9::SHIFT }
            pub const fn with_src9(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src9::MAX {
                    return Err(FieldOverflow { field: "SRC9", value: v as u64, max: fields::src9::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src9::MASK) | (v << fields::src9::SHIFT)))
            }
            pub const fn src10(self) -> u32 { (self.0 & fields::src10::MASK) >> fields::src10::SHIFT }
            pub const fn with_src10(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src10::MAX {
                    return Err(FieldOverflow { field: "SRC10", value: v as u64, max: fields::src10::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src10::MASK) | (v << fields::src10::SHIFT)))
            }
            pub const fn src11(self) -> u32 { (self.0 & fields::src11::MASK) >> fields::src11::SHIFT }
            pub const fn with_src11(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src11::MAX {
                    return Err(FieldOverflow { field: "SRC11", value: v as u64, max: fields::src11::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src11::MASK) | (v << fields::src11::SHIFT)))
            }
            pub const fn src12(self) -> u32 { (self.0 & fields::src12::MASK) >> fields::src12::SHIFT }
            pub const fn with_src12(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src12::MAX {
                    return Err(FieldOverflow { field: "SRC12", value: v as u64, max: fields::src12::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src12::MASK) | (v << fields::src12::SHIFT)))
            }
            pub const fn src13(self) -> u32 { (self.0 & fields::src13::MASK) >> fields::src13::SHIFT }
            pub const fn with_src13(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src13::MAX {
                    return Err(FieldOverflow { field: "SRC13", value: v as u64, max: fields::src13::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src13::MASK) | (v << fields::src13::SHIFT)))
            }
            pub const fn src14(self) -> u32 { (self.0 & fields::src14::MASK) >> fields::src14::SHIFT }
            pub const fn with_src14(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src14::MAX {
                    return Err(FieldOverflow { field: "SRC14", value: v as u64, max: fields::src14::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src14::MASK) | (v << fields::src14::SHIFT)))
            }
            pub const fn src15(self) -> u32 { (self.0 & fields::src15::MASK) >> fields::src15::SHIFT }
            pub const fn with_src15(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src15::MAX {
                    return Err(FieldOverflow { field: "SRC15", value: v as u64, max: fields::src15::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src15::MASK) | (v << fields::src15::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field SRC8; only rw bits are written back.
        pub fn set_src8<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src8(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC9; only rw bits are written back.
        pub fn set_src9<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src9(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC10; only rw bits are written back.
        pub fn set_src10<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src10(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC11; only rw bits are written back.
        pub fn set_src11<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src11(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC12; only rw bits are written back.
        pub fn set_src12<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src12(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC13; only rw bits are written back.
        pub fn set_src13<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src13(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC14; only rw bits are written back.
        pub fn set_src14<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src14(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field SRC15; only rw bits are written back.
        pub fn set_src15<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src15(v)?;
            write(bus, new);
            Ok(())
        }
    }

}

/// clkrst: Clock and reset status
pub mod clkrst {
    pub const BASE: u64 = 0x180002000;
    pub const SIZE: u64 = 0x1000;
    /// clkrst.ID: 32-bit at offset 0x0 - ASCII "SFCT"
    pub mod id {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x53464354_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x53464354_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.CONFIG: 32-bit at offset 0x4 - Build configuration of the clock/reset tree
    pub mod config {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x4;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// MC_EN [0:0] ro - Memory-controller domain present
            pub mod mc_en {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// NW [15:8] ro - Number of watchdogs
            pub mod nw {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// NB [23:16] ro - Number of gated branches
            pub mod nb {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff0000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// VERSION [31:24] ro - Clock/reset tree version
            pub mod version {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff000000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn mc_en(self) -> u32 { (self.0 & fields::mc_en::MASK) >> fields::mc_en::SHIFT }
            pub const fn nw(self) -> u32 { (self.0 & fields::nw::MASK) >> fields::nw::SHIFT }
            pub const fn nb(self) -> u32 { (self.0 & fields::nb::MASK) >> fields::nb::SHIFT }
            pub const fn version(self) -> u32 { (self.0 & fields::version::MASK) >> fields::version::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.STATUS: 32-bit at offset 0x8 - Sequencer and clock status (from the coherent snapshot of the reference domain)
    pub mod status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// SEQ_STATE [3:0] ro - 0 OFF 1 WAIT_CLK 2 ROOT_ON 3 REL_FAB 4 REL_CC 5 REL_ACC 6 RUN 7 QUIESCE 8 ASSERT 9 CLK_LOST
            pub mod seq_state {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// MC_STATE [5:4] ro - 0 OFF 1 REL 2 RUN
            pub mod mc_state {
                pub const SHIFT: u32 = 4;
                pub const WIDTH: u32 = 2;
                pub const MASK: u32 = 0x30_u32;
                pub const MAX: u32 = 0x3_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// RUN [6:6] ro
            pub mod run {
                pub const SHIFT: u32 = 6;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x40_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// PLL_LOCKED [7:7] ro
            pub mod pll_locked {
                pub const SHIFT: u32 = 7;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x80_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CORE_CLK_OK [8:8] ro
            pub mod core_clk_ok {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x100_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// MC_CLK_OK [9:9] ro
            pub mod mc_clk_ok {
                pub const SHIFT: u32 = 9;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x200_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// WDOG_WARN [10:10] ro
            pub mod wdog_warn {
                pub const SHIFT: u32 = 10;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x400_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// WDOG_EN [11:11] ro
            pub mod wdog_en {
                pub const SHIFT: u32 = 11;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x800_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// WDOG_LOCK [12:12] ro
            pub mod wdog_lock {
                pub const SHIFT: u32 = 12;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// WDOG_RST_EN [13:13] ro
            pub mod wdog_rst_en {
                pub const SHIFT: u32 = 13;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// QTIMEOUT [14:14] ro - Sticky - a quiesce timed out
            pub mod qtimeout {
                pub const SHIFT: u32 = 14;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CMD_DROP [15:15] ro - Sticky - a command was dropped
            pub mod cmd_drop {
                pub const SHIFT: u32 = 15;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x8000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// WDOG_CFG_REJECTED [16:16] ro - Sticky - a watchdog configuration was rejected
            pub mod wdog_cfg_rejected {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x10000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// DOMAINS_RELEASED [19:17] ro - Domain released {MC, CC, FAB}
            pub mod domains_released {
                pub const SHIFT: u32 = 17;
                pub const WIDTH: u32 = 3;
                pub const MASK: u32 = 0xe0000_u32;
                pub const MAX: u32 = 0x7_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// SNAP_SEEN [31:31] ro - A snapshot has been received since fabric reset
            pub mod snap_seen {
                pub const SHIFT: u32 = 31;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x80000000_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn seq_state(self) -> u32 { (self.0 & fields::seq_state::MASK) >> fields::seq_state::SHIFT }
            pub const fn mc_state(self) -> u32 { (self.0 & fields::mc_state::MASK) >> fields::mc_state::SHIFT }
            pub const fn run(self) -> u32 { (self.0 & fields::run::MASK) >> fields::run::SHIFT }
            pub const fn pll_locked(self) -> u32 { (self.0 & fields::pll_locked::MASK) >> fields::pll_locked::SHIFT }
            pub const fn core_clk_ok(self) -> u32 { (self.0 & fields::core_clk_ok::MASK) >> fields::core_clk_ok::SHIFT }
            pub const fn mc_clk_ok(self) -> u32 { (self.0 & fields::mc_clk_ok::MASK) >> fields::mc_clk_ok::SHIFT }
            pub const fn wdog_warn(self) -> u32 { (self.0 & fields::wdog_warn::MASK) >> fields::wdog_warn::SHIFT }
            pub const fn wdog_en(self) -> u32 { (self.0 & fields::wdog_en::MASK) >> fields::wdog_en::SHIFT }
            pub const fn wdog_lock(self) -> u32 { (self.0 & fields::wdog_lock::MASK) >> fields::wdog_lock::SHIFT }
            pub const fn wdog_rst_en(self) -> u32 { (self.0 & fields::wdog_rst_en::MASK) >> fields::wdog_rst_en::SHIFT }
            pub const fn qtimeout(self) -> u32 { (self.0 & fields::qtimeout::MASK) >> fields::qtimeout::SHIFT }
            pub const fn cmd_drop(self) -> u32 { (self.0 & fields::cmd_drop::MASK) >> fields::cmd_drop::SHIFT }
            pub const fn wdog_cfg_rejected(self) -> u32 { (self.0 & fields::wdog_cfg_rejected::MASK) >> fields::wdog_cfg_rejected::SHIFT }
            pub const fn domains_released(self) -> u32 { (self.0 & fields::domains_released::MASK) >> fields::domains_released::SHIFT }
            pub const fn snap_seen(self) -> u32 { (self.0 & fields::snap_seen::MASK) >> fields::snap_seen::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.CAUSE: 32-bit at offset 0xc - Sticky reset causes (read-only here; clearing goes through a CDC command channel that this register generator does not model). 0 POR, 1 external pin, 2 core clock absent, 3 PLL lock lost, 4 system watchdog, 5 block watchdog, 6 software SYSTEM, 7 software CONTROL, 8 software COMPUTE, 9 software MEMCTL, 10 memory-controller clock absent.
    pub mod cause {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0xc;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// CAUSES [10:0] ro
            pub mod causes {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 11;
                pub const MASK: u32 = 0x7ff_u32;
                pub const MAX: u32 = 0x7ff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn causes(self) -> u32 { (self.0 & fields::causes::MASK) >> fields::causes::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.RST_INFO: 32-bit at offset 0x10 - Reset count, last cause and released branches
    pub mod rst_info {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// RESET_COUNT [15:0] ro - Resets since power-on (saturating)
            pub mod reset_count {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// LAST_CAUSE [19:16] ro - Highest-priority cause of the last reset event
            pub mod last_cause {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf0000_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// BRANCH_RELEASED [31:24] ro - Branch release acknowledgements
            pub mod branch_released {
                pub const SHIFT: u32 = 24;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff000000_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn reset_count(self) -> u32 { (self.0 & fields::reset_count::MASK) >> fields::reset_count::SHIFT }
            pub const fn last_cause(self) -> u32 { (self.0 & fields::last_cause::MASK) >> fields::last_cause::SHIFT }
            pub const fn branch_released(self) -> u32 { (self.0 & fields::branch_released::MASK) >> fields::branch_released::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.CLK_EN: 32-bit at offset 0x18 - Software clock enable per gated branch (the hardware interlock overrides a 0 while a branch is busy)
    pub mod clk_en {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x18;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0xff_u32;
        pub const RW_MASK: u32 = 0xff_u32;
        pub mod fields {
            /// BRANCH_EN [7:0] rw
            pub mod branch_en {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0xff_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn branch_en(self) -> u32 { (self.0 & fields::branch_en::MASK) >> fields::branch_en::SHIFT }
            pub const fn with_branch_en(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::branch_en::MAX {
                    return Err(FieldOverflow { field: "BRANCH_EN", value: v as u64, max: fields::branch_en::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::branch_en::MASK) | (v << fields::branch_en::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field BRANCH_EN; only rw bits are written back.
        pub fn set_branch_en<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_branch_en(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// clkrst.CLK_STAT: 32-bit at offset 0x1c - Actual branch gate state and branch clock requests
    pub mod clk_stat {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x1c;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// GATE_EN [7:0] ro
            pub mod gate_en {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CLK_REQUEST [15:8] ro
            pub mod clk_request {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 8;
                pub const MASK: u32 = 0xff00_u32;
                pub const MAX: u32 = 0xff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn gate_en(self) -> u32 { (self.0 & fields::gate_en::MASK) >> fields::gate_en::SHIFT }
            pub const fn clk_request(self) -> u32 { (self.0 & fields::clk_request::MASK) >> fields::clk_request::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.WDOG_CNT: 32-bit at offset 0x2c - Current watchdog count (snapshot)
    pub mod wdog_cnt {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x2c;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.CLK_MEAS: 32-bit at offset 0x30 - Clock-monitor edge counts per window (snapshot)
    pub mod clk_meas {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x30;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// CORE_EDGES [15:0] ro
            pub mod core_edges {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// MC_EDGES [31:16] ro
            pub mod mc_edges {
                pub const SHIFT: u32 = 16;
                pub const WIDTH: u32 = 16;
                pub const MASK: u32 = 0xffff0000_u32;
                pub const MAX: u32 = 0xffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn core_edges(self) -> u32 { (self.0 & fields::core_edges::MASK) >> fields::core_edges::SHIFT }
            pub const fn mc_edges(self) -> u32 { (self.0 & fields::mc_edges::MASK) >> fields::mc_edges::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// clkrst.IRQ: 32-bit at offset 0x34 - Watchdog warning interrupt level (cleared by servicing the watchdog)
    pub mod irq {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x34;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// WDOG_WARN [0:0] ro
            pub mod wdog_warn {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn wdog_warn(self) -> u32 { (self.0 & fields::wdog_warn::MASK) >> fields::wdog_warn::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

}

/// sramc: SRAM controller control and status
pub mod sramc {
    pub const BASE: u64 = 0x180003000;
    pub const SIZE: u64 = 0x1000;
    /// sramc.CTRL: 32-bit at offset 0x0 - Master enables and flush
    pub mod ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x0;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0xf_u32;
        pub const RW_MASK: u32 = 0x10f_u32;
        pub mod fields {
            /// SRC_EN [3:0] rw - Per-master source enable (bit m = master m). A disabled master's requests are answered with the SRC error.
            pub mod src_en {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 4;
                pub const MASK: u32 = 0xf_u32;
                pub const MAX: u32 = 0xf_u32;
                pub const RESET: u32 = 0xf_u32;
            }
            /// FLUSH [8:8] rw - While 1 the controller accepts no new request and cancels accesses inside a bank (level; software clears it).
            pub mod flush {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x100_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn src_en(self) -> u32 { (self.0 & fields::src_en::MASK) >> fields::src_en::SHIFT }
            pub const fn with_src_en(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::src_en::MAX {
                    return Err(FieldOverflow { field: "SRC_EN", value: v as u64, max: fields::src_en::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::src_en::MASK) | (v << fields::src_en::SHIFT)))
            }
            pub const fn flush(self) -> u32 { (self.0 & fields::flush::MASK) >> fields::flush::SHIFT }
            pub const fn with_flush(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::flush::MAX {
                    return Err(FieldOverflow { field: "FLUSH", value: v as u64, max: fields::flush::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::flush::MASK) | (v << fields::flush::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field SRC_EN; only rw bits are written back.
        pub fn set_src_en<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_src_en(v)?;
            write(bus, new);
            Ok(())
        }
        /// Read-modify-write of rw field FLUSH; only rw bits are written back.
        pub fn set_flush<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_flush(v)?;
            write(bus, new);
            Ok(())
        }
    }

    /// sramc.STATUS: 32-bit at offset 0x8 - Controller status
    pub mod status {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x8;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// IDLE [0:0] ro - No transaction outstanding anywhere.
            pub mod idle {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x1_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// RSP_OVERFLOW [1:1] ro - Sticky until reset - a response FIFO overflowed (documented unreachable).
            pub mod rsp_overflow {
                pub const SHIFT: u32 = 1;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x2_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// BANK_PROTO [2:2] ro - Sticky until reset - a bank answered with nothing outstanding or a tracker overflowed.
            pub mod bank_proto {
                pub const SHIFT: u32 = 2;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x4_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn idle(self) -> u32 { (self.0 & fields::idle::MASK) >> fields::idle::SHIFT }
            pub const fn rsp_overflow(self) -> u32 { (self.0 & fields::rsp_overflow::MASK) >> fields::rsp_overflow::SHIFT }
            pub const fn bank_proto(self) -> u32 { (self.0 & fields::bank_proto::MASK) >> fields::bank_proto::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

    /// sramc.PERF_CTRL: 32-bit at offset 0x10 - Performance counter selection and clear
    pub mod perf_ctrl {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x10;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x7f_u32;
        pub mod fields {
            /// SEL [6:0] rw - Counter index presented on PERF_VAL (0 = first global counter; per-master and per-bank counters follow).
            pub mod sel {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 7;
                pub const MASK: u32 = 0x7f_u32;
                pub const MAX: u32 = 0x7f_u32;
                pub const RESET: u32 = 0x0_u32;
            }
            /// CLEAR [8:8] w1p - Write 1 to clear all counters (one-cycle pulse).
            pub mod clear {
                pub const SHIFT: u32 = 8;
                pub const WIDTH: u32 = 1;
                pub const MASK: u32 = 0x100_u32;
                pub const MAX: u32 = 0x1_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn sel(self) -> u32 { (self.0 & fields::sel::MASK) >> fields::sel::SHIFT }
            pub const fn with_sel(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::sel::MAX {
                    return Err(FieldOverflow { field: "SEL", value: v as u64, max: fields::sel::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::sel::MASK) | (v << fields::sel::SHIFT)))
            }
            pub const fn with_clear(self, v: u32) -> Result<Value, FieldOverflow> {
                if v > fields::clear::MAX {
                    return Err(FieldOverflow { field: "CLEAR", value: v as u64, max: fields::clear::MAX as u64 });
                }
                Ok(Value((self.0 & !fields::clear::MASK) | (v << fields::clear::SHIFT)))
            }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
        pub fn write<B: RegBus>(bus: &B, value: Value) -> () {
            bus.write32(ADDR, value.0)
        }
        /// Read-modify-write of rw field SEL; only rw bits are written back.
        pub fn set_sel<B: RegBus>(bus: &B, v: u32) -> Result<(), Error> {
            let new = Value(read(bus).0 & RW_MASK).with_sel(v)?;
            write(bus, new);
            Ok(())
        }
        /// Write 1 to the chosen bits of CLEAR (w1p); other rw fields keep their value, other write-one fields get 0.
        pub fn pulse_clear<B: RegBus>(bus: &B, bits: u32) -> Result<(), Error> {
            let cur = Value(read(bus).0 & RW_MASK);
            let new = Value(cur.0 | Value(0).with_clear(bits)?.0);
            write(bus, new);
            Ok(())
        }
    }

    /// sramc.PERF_VAL: 32-bit at offset 0x14 - Value of the counter selected by PERF_CTRL.SEL (32 bits, wraps)
    pub mod perf_val {
        use super::super::{Error, FieldOverflow, IndexError, RegBus};
        use super::BASE;
        pub const OFFSET: u64 = 0x14;
        pub const ADDR: u64 = BASE + OFFSET;
        pub const WIDTH: u32 = 32;
        pub const RESET: u32 = 0x0_u32;
        pub const RW_MASK: u32 = 0x0_u32;
        pub mod fields {
            /// VALUE [31:0] ro
            pub mod value {
                pub const SHIFT: u32 = 0;
                pub const WIDTH: u32 = 32;
                pub const MASK: u32 = 0xffffffff_u32;
                pub const MAX: u32 = 0xffffffff_u32;
                pub const RESET: u32 = 0x0_u32;
            }
        }
        #[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
        pub struct Value(pub u32);
        impl Value {
            pub const RESET: Value = Value(RESET);
            pub const fn raw(self) -> u32 { self.0 }
            pub const fn value(self) -> u32 { (self.0 & fields::value::MASK) >> fields::value::SHIFT }
        }
        pub fn read<B: RegBus>(bus: &B) -> Value {
            Value(bus.read32(ADDR))
        }
    }

}

/// True if the hardware's REGMAP_HASH equals the definition this file was generated from.
pub fn hardware_matches<B: RegBus>(bus: &B) -> bool {
    sysid::regmap_hash::read(bus).0 == MAP_HASH
}
