/*
 * sf_regs_examples.h - firmware examples generated from the definition's example steps
 * GENERATED FILE - DO NOT EDIT.  Edit the register definition instead.
 * generator       : albion_reggen 1.0.0 (definition schema 1)
 * register map    : silicaflux_regs v1.0
 * semantic hash   : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
 * definition hash : 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba
 */

#ifndef SF_REGS_EXAMPLES_H
#define SF_REGS_EXAMPLES_H
#include "sf_regs.h"

/* Each function returns 0 on success, -1 if an expected value differs, -2 if a poll times out. */
/* dma: Run one transfer and collect its completion */
static inline int sf_example_dma_0(void)
{
    sf_dma_src_write(UINT32_C(0x20000000));
    sf_dma_dst_write(UINT32_C(0x80000000));
    sf_dma_len_write(UINT32_C(0x1000));
    sf_dma_tag_set_tag(UINT32_C(0x7));
    sf_dma_start_write(UINT32_C(0x1));
    {
        unsigned polls_ = 0u;
        while (sf_dma_cpl_status_get_valid(sf_dma_cpl_status_read()) != UINT32_C(0x1)) {
            if (++polls_ >= 100000u) { return -2; }
        }
    }
    if (sf_dma_cpl_status_get_err(sf_dma_cpl_status_read()) != UINT32_C(0x0)) { return -1; }
    sf_dma_cpl_pop_write(UINT32_C(0x1));
    return 0;
}

/* dma: Interrupt on completion */
static inline int sf_example_dma_1(void)
{
    sf_dma_int_enable_set_cpl(UINT32_C(0x1));
    sf_dma_int_status_clear_cpl(SF_DMA_INT_STATUS_CPL_MASK >> SF_DMA_INT_STATUS_CPL_SHIFT);
    return 0;
}

/* tensor: Submit a staged GEMM descriptor and retire the completion */
static inline int sf_example_tensor_0(void)
{
    /* stage the 384-bit descriptor in DESC[0..11] (ABI-defined words) */
    sf_tensor_desc_write(0u, UINT32_C(0x1));
    sf_tensor_doorbell_write(UINT32_C(0x1));
    {
        unsigned polls_ = 0u;
        while (sf_tensor_int_status_get_done(sf_tensor_int_status_read()) != UINT32_C(0x1)) {
            if (++polls_ >= 1000000u) { return -2; }
        }
    }
    (void)sf_tensor_cpl_read(0u);
    sf_tensor_cpl_pop_write(UINT32_C(0x1));
    sf_tensor_int_status_clear_done(SF_TENSOR_INT_STATUS_DONE_MASK >> SF_TENSOR_INT_STATUS_DONE_SHIFT);
    return 0;
}

/* tensor: Abort a running command */
static inline int sf_example_tensor_1(void)
{
    sf_tensor_ctrl_pulse_abort(SF_TENSOR_CTRL_ABORT_MASK >> SF_TENSOR_CTRL_ABORT_SHIFT);
    {
        unsigned polls_ = 0u;
        while (sf_tensor_status_get_aborting(sf_tensor_status_read()) != UINT32_C(0x0)) {
            if (++polls_ >= 100000u) { return -2; }
        }
    }
    return 0;
}

/* vector: Submit one command and retire its record */
static inline int sf_example_vector_0(void)
{
    /* stage a 256-bit descriptor in DESC[0..7] (ABI-defined words) */
    sf_vector_desc_write(0u, UINT32_C(0x101));
    sf_vector_doorbell_write(UINT32_C(0x1));
    {
        unsigned polls_ = 0u;
        while (sf_vector_status_get_cpl_valid(sf_vector_status_read()) != UINT32_C(0x1)) {
            if (++polls_ >= 100000u) { return -2; }
        }
    }
    (void)sf_vector_cpl_read(0u);
    sf_vector_cpl_pop_write(UINT32_C(0x1));
    return 0;
}

/* vector: Enable interrupts and clear a stale error */
static inline int sf_example_vector_1(void)
{
    sf_vector_int_enable_set_err(UINT32_C(0x1));
    sf_vector_ctrl_pulse_err_clear(SF_VECTOR_CTRL_ERR_CLEAR_MASK >> SF_VECTOR_CTRL_ERR_CLEAR_SHIFT);
    sf_vector_int_status_clear_err(SF_VECTOR_INT_STATUS_ERR_MASK >> SF_VECTOR_INT_STATUS_ERR_SHIFT);
    return 0;
}

/* perf: Take a coherent snapshot while the bank is frozen */
static inline int sf_example_perf_0(void)
{
    sf_perf_ctrl_set_freeze(UINT32_C(0x1));
    {
        unsigned polls_ = 0u;
        while (sf_perf_status_get_frozen(sf_perf_status_read()) != UINT32_C(0x1)) {
            if (++polls_ >= 1000u) { return -2; }
        }
    }
    (void)sf_perf_cnt_read(0u);
    sf_perf_ctrl_set_freeze(UINT32_C(0x0));
    return 0;
}

/* sysid: Check that the hardware matches the register map this firmware was built from */
static inline int sf_example_sysid_0(void)
{
    /* ID must read SFLX; REGMAP_HASH must equal SF_REGS_MAP_HASH (see sf_regs_hardware_matches) */
    if (sf_sysid_regmap_version_get_major(sf_sysid_regmap_version_read()) != UINT32_C(0x1)) { return -1; }
    if (sf_sysid_alp_version_get_major(sf_sysid_alp_version_read()) != UINT32_C(0x1)) { return -1; }
    return 0;
}

/* intc: Enable source 3 at priority 5 and unmask everything above priority 2 */
static inline int sf_example_intc_0(void)
{
    sf_intc_prio0_set_src3(UINT32_C(0x5));
    sf_intc_threshold_set_level(UINT32_C(0x2));
    sf_intc_enable_set_en(UINT32_C(0x8));
    return 0;
}

/* clkrst: Check that the system is running and the PLL is locked */
static inline int sf_example_clkrst_0(void)
{
    {
        unsigned polls_ = 0u;
        while (sf_clkrst_status_get_pll_locked(sf_clkrst_status_read()) != UINT32_C(0x1)) {
            if (++polls_ >= 100000u) { return -2; }
        }
    }
    if (sf_clkrst_status_get_run(sf_clkrst_status_read()) != UINT32_C(0x1)) { return -1; }
    return 0;
}

/* clkrst: Gate off branch 2's software clock enable */
static inline int sf_example_clkrst_1(void)
{
    sf_clkrst_clk_en_set_branch_en(UINT32_C(0xfb));
    return 0;
}

/* sramc: Enable all masters, select a counter and read it */
static inline int sf_example_sramc_0(void)
{
    sf_sramc_ctrl_set_src_en(UINT32_C(0xf));
    sf_sramc_perf_ctrl_set_sel(UINT32_C(0x3));
    sf_sramc_perf_ctrl_pulse_clear(SF_SRAMC_PERF_CTRL_CLEAR_MASK >> SF_SRAMC_PERF_CTRL_CLEAR_SHIFT);
    (void)sf_sramc_perf_val_read();
    return 0;
}

/* sramc: Flush the controller and wait until it is idle */
static inline int sf_example_sramc_1(void)
{
    sf_sramc_ctrl_set_flush(UINT32_C(0x1));
    {
        unsigned polls_ = 0u;
        while (sf_sramc_status_get_idle(sf_sramc_status_read()) != UINT32_C(0x1)) {
            if (++polls_ >= 1000u) { return -2; }
        }
    }
    sf_sramc_ctrl_set_flush(UINT32_C(0x0));
    return 0;
}

#endif /* SF_REGS_EXAMPLES_H */
