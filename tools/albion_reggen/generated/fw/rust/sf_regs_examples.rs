// sf_regs_examples.rs - firmware examples generated from the definition's example steps
// GENERATED FILE - DO NOT EDIT.  Edit the register definition instead.
// generator       : albion_reggen 1.0.0 (definition schema 1)
// register map    : silicaflux_regs v1.0
// semantic hash   : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
// definition hash : 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba

// Declare next to sf_regs:   mod sf_regs;  mod sf_regs_examples;
#![allow(dead_code, unused_imports)]
use super::sf_regs as regs;
use regs::RegBus;

#[derive(Debug, PartialEq, Eq)]
pub enum ExampleError {
    Mismatch,
    Timeout,
    Bus(regs::Error),
}

impl From<regs::Error> for ExampleError {
    fn from(e: regs::Error) -> Self {
        ExampleError::Bus(e)
    }
}

/// dma: Run one transfer and collect its completion
pub fn example_dma_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::dma::src::write(bus, regs::dma::src::Value(0x20000000_u32));
    regs::dma::dst::write(bus, regs::dma::dst::Value(0x80000000_u32));
    regs::dma::len::write(bus, regs::dma::len::Value(0x1000_u32));
    regs::dma::tag::set_tag(bus, 0x7_u32)?;
    regs::dma::start::write(bus, regs::dma::start::Value(0x1_u32));
    {
        let mut polls: u32 = 0;
        while regs::dma::cpl_status::read(bus).valid() != 0x1_u32 {
            polls += 1;
            if polls >= 100000 { return Err(ExampleError::Timeout); }
        }
    }
    if regs::dma::cpl_status::read(bus).err() != 0x0_u32 { return Err(ExampleError::Mismatch); }
    regs::dma::cpl_pop::write(bus, regs::dma::cpl_pop::Value(0x1_u32));
    Ok(())
}

/// dma: Interrupt on completion
pub fn example_dma_1<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::dma::int_enable::set_cpl(bus, 0x1_u32)?;
    regs::dma::int_status::clear_cpl(bus, regs::dma::int_status::fields::cpl::MASK >> regs::dma::int_status::fields::cpl::SHIFT)?;
    Ok(())
}

/// tensor: Submit a staged GEMM descriptor and retire the completion
pub fn example_tensor_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    // stage the 384-bit descriptor in DESC[0..11] (ABI-defined words)
    regs::tensor::desc::write(bus, 0, regs::tensor::desc::Value(0x1_u32))?;
    regs::tensor::doorbell::write(bus, regs::tensor::doorbell::Value(0x1_u32));
    {
        let mut polls: u32 = 0;
        while regs::tensor::int_status::read(bus).done() != 0x1_u32 {
            polls += 1;
            if polls >= 1000000 { return Err(ExampleError::Timeout); }
        }
    }
    let _ = regs::tensor::cpl::read(bus, 0)?;
    regs::tensor::cpl_pop::write(bus, regs::tensor::cpl_pop::Value(0x1_u32));
    regs::tensor::int_status::clear_done(bus, regs::tensor::int_status::fields::done::MASK >> regs::tensor::int_status::fields::done::SHIFT)?;
    Ok(())
}

/// tensor: Abort a running command
pub fn example_tensor_1<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::tensor::ctrl::pulse_abort(bus, regs::tensor::ctrl::fields::abort::MASK >> regs::tensor::ctrl::fields::abort::SHIFT)?;
    {
        let mut polls: u32 = 0;
        while regs::tensor::status::read(bus).aborting() != 0x0_u32 {
            polls += 1;
            if polls >= 100000 { return Err(ExampleError::Timeout); }
        }
    }
    Ok(())
}

/// vector: Submit one command and retire its record
pub fn example_vector_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    // stage a 256-bit descriptor in DESC[0..7] (ABI-defined words)
    regs::vector::desc::write(bus, 0, regs::vector::desc::Value(0x101_u32))?;
    regs::vector::doorbell::write(bus, regs::vector::doorbell::Value(0x1_u32));
    {
        let mut polls: u32 = 0;
        while regs::vector::status::read(bus).cpl_valid() != 0x1_u32 {
            polls += 1;
            if polls >= 100000 { return Err(ExampleError::Timeout); }
        }
    }
    let _ = regs::vector::cpl::read(bus, 0)?;
    regs::vector::cpl_pop::write(bus, regs::vector::cpl_pop::Value(0x1_u32));
    Ok(())
}

/// vector: Enable interrupts and clear a stale error
pub fn example_vector_1<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::vector::int_enable::set_err(bus, 0x1_u32)?;
    regs::vector::ctrl::pulse_err_clear(bus, regs::vector::ctrl::fields::err_clear::MASK >> regs::vector::ctrl::fields::err_clear::SHIFT)?;
    regs::vector::int_status::clear_err(bus, regs::vector::int_status::fields::err::MASK >> regs::vector::int_status::fields::err::SHIFT)?;
    Ok(())
}

/// perf: Take a coherent snapshot while the bank is frozen
pub fn example_perf_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::perf::ctrl::set_freeze(bus, 0x1_u32)?;
    {
        let mut polls: u32 = 0;
        while regs::perf::status::read(bus).frozen() != 0x1_u32 {
            polls += 1;
            if polls >= 1000 { return Err(ExampleError::Timeout); }
        }
    }
    let _ = regs::perf::cnt::read(bus, 0)?;
    regs::perf::ctrl::set_freeze(bus, 0x0_u32)?;
    Ok(())
}

/// sysid: Check that the hardware matches the register map this firmware was built from
pub fn example_sysid_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    // ID must read SFLX; REGMAP_HASH must equal SF_REGS_MAP_HASH (see sf_regs_hardware_matches)
    if regs::sysid::regmap_version::read(bus).major() != 0x1_u32 { return Err(ExampleError::Mismatch); }
    if regs::sysid::alp_version::read(bus).major() != 0x1_u32 { return Err(ExampleError::Mismatch); }
    Ok(())
}

/// intc: Enable source 3 at priority 5 and unmask everything above priority 2
pub fn example_intc_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::intc::prio0::set_src3(bus, 0x5_u32)?;
    regs::intc::threshold::set_level(bus, 0x2_u32)?;
    regs::intc::enable::set_en(bus, 0x8_u32)?;
    Ok(())
}

/// clkrst: Check that the system is running and the PLL is locked
pub fn example_clkrst_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    {
        let mut polls: u32 = 0;
        while regs::clkrst::status::read(bus).pll_locked() != 0x1_u32 {
            polls += 1;
            if polls >= 100000 { return Err(ExampleError::Timeout); }
        }
    }
    if regs::clkrst::status::read(bus).run() != 0x1_u32 { return Err(ExampleError::Mismatch); }
    Ok(())
}

/// clkrst: Gate off branch 2's software clock enable
pub fn example_clkrst_1<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::clkrst::clk_en::set_branch_en(bus, 0xfb_u32)?;
    Ok(())
}

/// sramc: Enable all masters, select a counter and read it
pub fn example_sramc_0<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::sramc::ctrl::set_src_en(bus, 0xf_u32)?;
    regs::sramc::perf_ctrl::set_sel(bus, 0x3_u32)?;
    regs::sramc::perf_ctrl::pulse_clear(bus, regs::sramc::perf_ctrl::fields::clear::MASK >> regs::sramc::perf_ctrl::fields::clear::SHIFT)?;
    let _ = regs::sramc::perf_val::read(bus);
    Ok(())
}

/// sramc: Flush the controller and wait until it is idle
pub fn example_sramc_1<B: RegBus>(bus: &B) -> Result<(), ExampleError> {
    regs::sramc::ctrl::set_flush(bus, 0x1_u32)?;
    {
        let mut polls: u32 = 0;
        while regs::sramc::status::read(bus).idle() != 0x1_u32 {
            polls += 1;
            if polls >= 1000 { return Err(ExampleError::Timeout); }
        }
    }
    regs::sramc::ctrl::set_flush(bus, 0x0_u32)?;
    Ok(())
}

